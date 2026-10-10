from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from itertools import product
from statistics import mean, median

from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from backtest.walk_forward_runner import (
    FIXED_UNIVERSE,
    _slice_batch,
    _window_slices,
)
from config import (
    DEFAULT_FEE_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_SLIPPAGE_RATE,
    STARTING_CAPITAL,
)
from data.yahoo_chart_provider import YahooChartDailyBarProvider
from risk.policy_engine import evaluate_trade
from strategies.registry import build_strategy


BASELINE_HORIZON_FUTURE_BARS = 5
MIN_COMPARABLE_WINDOWS = 8
MIN_COMPARABLE_TRADES = 20
LARGE_DOWNSIDE_THRESHOLD_YEN = -2000.0
RISK_STAGE_MIN_BETTER_WINDOW_RATIO = 0.50


@dataclass(frozen=True)
class ExitPolicy:
    max_holding_days: int
    hard_stop_loss_pct: float
    profit_target_pct: float | None
    trailing_activation_pct: float
    trailing_stop_pct: float

    @property
    def key(self) -> str:
        target = "none" if self.profit_target_pct is None else f"{self.profit_target_pct:.3f}"
        return (
            f"max{self.max_holding_days}:"
            f"stop{self.hard_stop_loss_pct:.3f}:"
            f"target{target}:"
            f"trail{self.trailing_activation_pct:.3f}/"
            f"{self.trailing_stop_pct:.3f}"
        )


def policy_grid() -> tuple[ExitPolicy, ...]:
    rows = []
    for max_days, stop, target, activation, trail in product(
        (5, 10, 15),
        (0.03, 0.05, 0.07),
        (None, 0.06, 0.10),
        (0.03, 0.05),
        (0.02, 0.03),
    ):
        rows.append(
            ExitPolicy(
                max_holding_days=max_days,
                hard_stop_loss_pct=stop,
                profit_target_pct=target,
                trailing_activation_pct=activation,
                trailing_stop_pct=trail,
            )
        )
    return tuple(rows)


def risk_stage_policy_grid() -> tuple[ExitPolicy, ...]:
    """Narrow second-stage grid derived from the first-stage direction.

    Fixed profit targets are intentionally removed here because the first-stage
    evidence favored letting winners run and protecting them with trailing exits.
    """
    rows = []
    for max_days, stop, activation, trail in product(
        (10, 12, 15),
        (0.05, 0.06, 0.07),
        (0.03, 0.04, 0.05),
        (0.015, 0.02, 0.025, 0.03),
    ):
        rows.append(
            ExitPolicy(
                max_holding_days=max_days,
                hard_stop_loss_pct=stop,
                profit_target_pct=None,
                trailing_activation_pct=activation,
                trailing_stop_pct=trail,
            )
        )
    return tuple(rows)


def _round_lot_shares(entry_price: float) -> int:
    affordable = int(STARTING_CAPITAL // entry_price)
    return (affordable // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE


def _trade_result(
    bars,
    *,
    symbol: str,
    decision_index: int,
    entry_index: int,
    exit_index: int,
    exit_reason: str,
) -> dict | None:
    raw_entry = float(bars[entry_index].open)
    raw_exit = float(bars[exit_index].close)
    buy_price = raw_entry * (1 + DEFAULT_SLIPPAGE_RATE)
    sell_price = raw_exit * (1 - DEFAULT_SLIPPAGE_RATE)
    shares = _round_lot_shares(buy_price)
    if shares < DEFAULT_LOT_SIZE:
        return None

    buy_value = shares * buy_price
    sell_value = shares * sell_price
    fees = (buy_value + sell_value) * DEFAULT_FEE_RATE
    net_pnl = (sell_value - buy_value) - fees
    return {
        "symbol": symbol,
        "decision_date": bars[decision_index].date,
        "entry_date": bars[entry_index].date,
        "exit_date": bars[exit_index].date,
        "exit_reason": exit_reason,
        "holding_trading_days": exit_index - entry_index + 1,
        "shares": shares,
        "net_pnl": round(net_pnl, 2),
    }


def _baseline_exit_index(bars, *, decision_index: int) -> int | None:
    exit_index = decision_index + BASELINE_HORIZON_FUTURE_BARS
    return exit_index if exit_index < len(bars) else None


def _adaptive_exit_index(
    bars,
    *,
    entry_index: int,
    policy: ExitPolicy,
) -> tuple[int, str] | None:
    raw_entry = float(bars[entry_index].open)
    peak_close = float(bars[entry_index].close)
    last_index = min(len(bars) - 1, entry_index + policy.max_holding_days - 1)

    for index in range(entry_index, last_index + 1):
        close = float(bars[index].close)
        peak_close = max(peak_close, close)
        return_from_entry = (close / raw_entry) - 1.0
        peak_return = (peak_close / raw_entry) - 1.0
        drawdown_from_peak = (close / peak_close) - 1.0

        if return_from_entry <= -policy.hard_stop_loss_pct:
            return index, "hard_stop_loss"
        if (
            policy.profit_target_pct is not None
            and return_from_entry >= policy.profit_target_pct
        ):
            return index, "profit_target"
        if (
            peak_return >= policy.trailing_activation_pct
            and drawdown_from_peak <= -policy.trailing_stop_pct
        ):
            return index, "trailing_profit_protection"
        if index == last_index and (index - entry_index + 1) >= policy.max_holding_days:
            return index, "maximum_holding_period"
    return None


def _simulate_window(batch, *, split_index: int, policy: ExitPolicy | None) -> dict:
    bars = list(batch.bars)
    strategy = build_strategy(CURRENT_CHAMPION_SPEC)
    trades = []
    decision_index = max(2, split_index)

    while decision_index + 1 < len(bars):
        history = bars[: decision_index + 1]
        if not evaluate_trade(history).allowed:
            decision_index += 1
            continue
        signal = strategy.evaluate(history)
        if signal.action != "buy":
            decision_index += 1
            continue

        entry_index = decision_index + 1
        if policy is None:
            exit_index = _baseline_exit_index(bars, decision_index=decision_index)
            if exit_index is None:
                break
            exit_reason = "fixed_5_future_bars"
        else:
            resolved = _adaptive_exit_index(
                bars,
                entry_index=entry_index,
                policy=policy,
            )
            if resolved is None:
                break
            exit_index, exit_reason = resolved

        trade = _trade_result(
            bars,
            symbol=batch.symbol,
            decision_index=decision_index,
            entry_index=entry_index,
            exit_index=exit_index,
            exit_reason=exit_reason,
        )
        if trade is not None:
            trades.append(trade)
        decision_index = exit_index + 1

    pnls = [float(row["net_pnl"]) for row in trades]
    holds = [int(row["holding_trading_days"]) for row in trades]
    return {
        "trade_count": len(trades),
        "net_pnl": round(sum(pnls), 2),
        "mean_net_pnl": round(mean(pnls), 4) if pnls else 0.0,
        "win_rate": round(sum(value > 0 for value in pnls) / len(pnls), 6)
        if pnls
        else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "average_holding_days": round(mean(holds), 4) if holds else 0.0,
        "trades": trades,
    }


def _lower_tail_mean(values: list[float], *, fraction: float = 0.20) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    count = max(1, int(len(ordered) * fraction))
    return round(mean(ordered[:count]), 4)


def _summarize_candidate(rows: list[dict], policy: ExitPolicy) -> dict:
    comparable = [
        row
        for row in rows
        if row["baseline"]["trade_count"] > 0
        and row["candidate"]["trade_count"] > 0
    ]
    trade_count = sum(row["candidate"]["trade_count"] for row in comparable)
    improvements = [
        row["candidate"]["net_pnl"] - row["baseline"]["net_pnl"]
        for row in comparable
    ]
    better_count = sum(value > 0 for value in improvements)
    holds = [
        row["candidate"]["average_holding_days"]
        for row in comparable
        if row["candidate"]["trade_count"] > 0
    ]
    large_downside_count = sum(
        value <= LARGE_DOWNSIDE_THRESHOLD_YEN for value in improvements
    )
    return {
        "policy_key": policy.key,
        "policy": asdict(policy),
        "comparable_windows": len(comparable),
        "trade_count": trade_count,
        "better_window_count": better_count,
        "better_window_ratio": round(better_count / len(comparable), 6)
        if comparable
        else 0.0,
        "mean_window_pnl_improvement": round(mean(improvements), 4)
        if improvements
        else 0.0,
        "median_window_pnl_improvement": round(median(improvements), 4)
        if improvements
        else 0.0,
        "worst_window_pnl_improvement": round(min(improvements), 4)
        if improvements
        else 0.0,
        "lower_tail_mean_improvement": _lower_tail_mean(improvements),
        "large_downside_window_count": large_downside_count,
        "average_holding_days": round(mean(holds), 4) if holds else 0.0,
        "eligible": (
            len(comparable) >= MIN_COMPARABLE_WINDOWS
            and trade_count >= MIN_COMPARABLE_TRADES
        ),
    }


def _run_grid(
    loaded: dict,
    *,
    policies: tuple[ExitPolicy, ...],
) -> tuple[list[dict], list[dict]]:
    baseline_windows = []
    candidate_windows = {policy.key: [] for policy in policies}

    for symbol, batch in loaded.items():
        for window_index, (start, end, split_index) in enumerate(
            _window_slices(len(batch.bars)),
            start=1,
        ):
            window_batch = _slice_batch(batch, start, end)
            baseline = _simulate_window(
                window_batch,
                split_index=split_index,
                policy=None,
            )
            baseline_windows.append(
                {
                    "symbol": symbol,
                    "window_index": window_index,
                    "baseline": baseline,
                }
            )
            for policy in policies:
                candidate = _simulate_window(
                    window_batch,
                    split_index=split_index,
                    policy=policy,
                )
                candidate_windows[policy.key].append(
                    {
                        "symbol": symbol,
                        "window_index": window_index,
                        "baseline": baseline,
                        "candidate": candidate,
                    }
                )

    summaries = [
        _summarize_candidate(candidate_windows[policy.key], policy)
        for policy in policies
    ]
    return baseline_windows, summaries


def run_adaptive_exit_optimization(
    *,
    provider=None,
    symbols: tuple[str, ...] = FIXED_UNIVERSE,
    as_of: date | None = None,
) -> dict:
    current_date = as_of or date.today()
    data_provider = provider or YahooChartDailyBarProvider()
    loaded = {}

    for symbol in symbols:
        try:
            loaded[symbol] = data_provider.load_batch(symbol, as_of=current_date)
        except Exception:
            continue

    baseline_windows, summaries = _run_grid(
        loaded,
        policies=policy_grid(),
    )
    eligible = [row for row in summaries if row["eligible"]]
    eligible.sort(
        key=lambda row: (
            -row["better_window_ratio"],
            -row["mean_window_pnl_improvement"],
            -row["worst_window_pnl_improvement"],
            row["average_holding_days"],
            row["policy_key"],
        )
    )
    selected = eligible[0] if eligible else None

    _, risk_summaries = _run_grid(
        loaded,
        policies=risk_stage_policy_grid(),
    )
    risk_eligible = [
        row for row in risk_summaries
        if row["eligible"]
        and row["better_window_ratio"] >= RISK_STAGE_MIN_BETTER_WINDOW_RATIO
        and row["mean_window_pnl_improvement"] > 0
    ]
    risk_eligible.sort(
        key=lambda row: (
            row["large_downside_window_count"],
            -row["lower_tail_mean_improvement"],
            -row["worst_window_pnl_improvement"],
            -row["better_window_ratio"],
            -row["mean_window_pnl_improvement"],
            row["average_holding_days"],
            row["policy_key"],
        )
    )
    risk_shortlist = risk_eligible[:3]

    baseline_trade_count = sum(
        row["baseline"]["trade_count"] for row in baseline_windows
    )
    baseline_net_pnl = round(
        sum(row["baseline"]["net_pnl"] for row in baseline_windows),
        2,
    )

    return {
        "mode": "historical_adaptive_exit_optimization",
        "strategy_key": CURRENT_CHAMPION_SPEC["strategy_key"],
        "champion_frozen": True,
        "prospective_shadow_evidence_consumed": False,
        "live_trading": False,
        "parameter_grid_size": len(summaries),
        "minimum_comparable_windows": MIN_COMPARABLE_WINDOWS,
        "minimum_comparable_trades": MIN_COMPARABLE_TRADES,
        "baseline": {
            "method": "fixed_5_future_bars",
            "window_count": len(baseline_windows),
            "trade_count": baseline_trade_count,
            "aggregate_net_pnl": baseline_net_pnl,
        },
        "selection_rule": (
            "maximize better_window_ratio, then mean improvement, then worst-window "
            "improvement, then minimize average holding days"
        ),
        "selected": selected,
        "top_candidates": eligible[:10],
        "candidate_count_eligible": len(eligible),
        "risk_stage": {
            "mode": "downside_robustness_optimization",
            "parameter_grid_size": len(risk_summaries),
            "fixed_profit_target_removed": True,
            "large_downside_threshold_yen": LARGE_DOWNSIDE_THRESHOLD_YEN,
            "minimum_better_window_ratio": RISK_STAGE_MIN_BETTER_WINDOW_RATIO,
            "selection_rule": (
                "minimize large-downside windows, maximize lower-tail mean, "
                "maximize worst-window improvement, then consistency and mean improvement"
            ),
            "shortlist": risk_shortlist,
            "shortlist_count": len(risk_shortlist),
            "automatic_adoption": False,
        },
        "safety": {
            "automatic_strategy_change": False,
            "automatic_promotion": False,
            "paper_gate_reopened": False,
            "paper_trading_allowed": False,
            "live_trading_allowed": False,
        },
    }
