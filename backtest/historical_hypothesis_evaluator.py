from __future__ import annotations

from datetime import date, timedelta
from math import floor
from statistics import mean

from backtest.historical_runner import _buy_hold_benchmark, _strategy_walk_forward
from backtest.multi_stock_runner import FIXED_UNIVERSE, STALE_AFTER_DAYS
from backtest.readiness_gate import SYNTHETIC_CHAMPION_SPEC
from backtest.walk_forward_runner import (
    MIN_ELIGIBLE_SYMBOLS,
    MIN_WINDOWS_PER_SYMBOL,
    _slice_batch,
    _window_slices,
)
from config import STARTING_CAPITAL
from data.yahoo_chart_provider import YahooChartDailyBarProvider


MIN_TURNOVER_REDUCTION = 0.10


def _candidate_spec(item: dict) -> dict:
    change = item["proposed_change"]
    config_keys = {
        "minimum_volume_ratio",
        "deep_discount_threshold",
        "moderate_discount_threshold",
        "secondary_volume_ratio",
        "shallow_discount_threshold",
        "shallow_discount_ceiling",
        "tertiary_volume_ratio",
        "edge_multiple",
    }
    return {
        "strategy_key": (
            "mean_reversion_cost_floor:g6-candidate-x"
            + str(int(float(change["edge_multiple"])))
        ),
        "strategy_name": "mean_reversion_cost_floor",
        "generation": 6,
        "rule": "require_cost_coverage_on_negative_slope",
        "config": {
            key: change[key]
            for key in config_keys
            if key in change
        },
    }


def evaluate_historical_candidates(
    bridge_candidates: list[dict],
    *,
    provider=None,
    symbols: tuple[str, ...] = FIXED_UNIVERSE,
    as_of: date | None = None,
) -> list[dict]:
    current_date = as_of or date.today()
    data_provider = provider or YahooChartDailyBarProvider()

    batches = {}
    for symbol in symbols:
        batch = data_provider.load_batch(symbol, as_of=current_date)
        bars = list(batch.bars)
        last_date = date.fromisoformat(bars[-1].date)
        if current_date - last_date > timedelta(days=STALE_AFTER_DAYS):
            continue
        batches[symbol] = batch

    if len(batches) < MIN_ELIGIBLE_SYMBOLS:
        raise RuntimeError(
            f"historical hypothesis evaluation requires {MIN_ELIGIBLE_SYMBOLS} "
            f"eligible symbols; got {len(batches)}"
        )

    results = []
    for item in bridge_candidates:
        candidate_spec = _candidate_spec(item)
        rows = []

        for symbol, batch in batches.items():
            evaluated_for_symbol = 0
            for window_index, (start, end, split_index) in enumerate(
                _window_slices(len(batch.bars)),
                start=1,
            ):
                window_batch = _slice_batch(batch, start, end)
                benchmark = _buy_hold_benchmark(
                    window_batch,
                    split_index=split_index,
                )
                if not benchmark["traded"]:
                    continue

                baseline = _strategy_walk_forward(
                    window_batch,
                    split_index=split_index,
                    champion_spec=SYNTHETIC_CHAMPION_SPEC,
                )
                candidate = _strategy_walk_forward(
                    window_batch,
                    split_index=split_index,
                    champion_spec=candidate_spec,
                )
                rows.append(
                    {
                        "symbol": symbol,
                        "window_index": window_index,
                        "baseline_return": float(baseline["metrics"]["total_return"]),
                        "candidate_return": float(candidate["metrics"]["total_return"]),
                        "baseline_max_drawdown": float(
                            baseline["metrics"]["max_drawdown"]
                        ),
                        "candidate_max_drawdown": float(
                            candidate["metrics"]["max_drawdown"]
                        ),
                        "baseline_trade_count": int(
                            baseline["metrics"]["trade_count"]
                        ),
                        "candidate_trade_count": int(
                            candidate["metrics"]["trade_count"]
                        ),
                    }
                )
                evaluated_for_symbol += 1

            if evaluated_for_symbol < MIN_WINDOWS_PER_SYMBOL:
                rows = [row for row in rows if row["symbol"] != symbol]

        eligible_symbols = sorted({row["symbol"] for row in rows})
        if len(eligible_symbols) < MIN_ELIGIBLE_SYMBOLS:
            raise RuntimeError("candidate evaluation lost minimum window coverage")

        baseline_returns = [row["baseline_return"] for row in rows]
        candidate_returns = [row["candidate_return"] for row in rows]
        baseline_dd = [row["baseline_max_drawdown"] for row in rows]
        candidate_dd = [row["candidate_max_drawdown"] for row in rows]
        baseline_trades = sum(row["baseline_trade_count"] for row in rows)
        candidate_trades = sum(row["candidate_trade_count"] for row in rows)

        turnover_reduction = (
            1.0 - candidate_trades / baseline_trades
            if baseline_trades
            else 0.0
        )
        baseline_loss_windows = sum(int(value < 0) for value in baseline_returns)
        candidate_loss_windows = sum(int(value < 0) for value in candidate_returns)

        criteria = {
            "mean_return_not_worse": mean(candidate_returns) >= mean(baseline_returns),
            "mean_drawdown_not_worse": mean(candidate_dd) <= mean(baseline_dd),
            "loss_windows_not_increased": (
                candidate_loss_windows <= baseline_loss_windows
            ),
            "turnover_reduced_at_least_10pct": (
                candidate_trades <= floor(baseline_trades * (1 - MIN_TURNOVER_REDUCTION))
            ),
        }
        accepted = all(criteria.values())

        results.append(
            {
                "queue_key": item["queue_key"],
                "candidate_strategy_key": candidate_spec["strategy_key"],
                "candidate_spec": candidate_spec,
                "accepted": accepted,
                "criteria": criteria,
                "window_count": len(rows),
                "eligible_symbols": eligible_symbols,
                "baseline_mean_return": round(mean(baseline_returns), 6),
                "candidate_mean_return": round(mean(candidate_returns), 6),
                "baseline_mean_max_drawdown": round(mean(baseline_dd), 6),
                "candidate_mean_max_drawdown": round(mean(candidate_dd), 6),
                "baseline_loss_windows": baseline_loss_windows,
                "candidate_loss_windows": candidate_loss_windows,
                "baseline_trade_count": baseline_trades,
                "candidate_trade_count": candidate_trades,
                "turnover_reduction": round(turnover_reduction, 6),
                "selection_policy": (
                    "Historical gate is pass/fail only. Final selection must use the "
                    "lowest predeclared edge_multiple among dual-gate passers."
                ),
            }
        )

    return results
