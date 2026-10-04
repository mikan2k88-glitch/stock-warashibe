from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev

from backtest.historical_runner import _buy_hold_benchmark, _strategy_walk_forward
from backtest.multi_stock_runner import FIXED_UNIVERSE, STALE_AFTER_DAYS
from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from backtest.walk_forward_runner import (
    HISTORY_BARS,
    MIN_ELIGIBLE_SYMBOLS,
    MIN_WINDOWS_PER_SYMBOL,
    TEST_BARS,
    _slice_batch,
    _window_slices,
)
from config import STARTING_CAPITAL
from data.yahoo_chart_provider import YahooChartDailyBarProvider


MIN_REGIME_SAMPLES = 3


def _returns(bars) -> list[float]:
    values = []
    for previous, current in zip(bars, bars[1:]):
        if previous.close <= 0:
            continue
        values.append(current.close / previous.close - 1.0)
    return values


def classify_regime(history_bars, test_bars) -> dict:
    history_return = history_bars[-1].close / history_bars[0].close - 1.0
    test_return = test_bars[-1].close / test_bars[0].close - 1.0
    test_returns = _returns(test_bars)
    volatility = pstdev(test_returns) if len(test_returns) >= 2 else 0.0

    if history_return >= 0.05:
        trend = "up"
    elif history_return <= -0.05:
        trend = "down"
    else:
        trend = "sideways"

    if volatility < 0.015:
        volatility_regime = "low"
    elif volatility < 0.03:
        volatility_regime = "medium"
    else:
        volatility_regime = "high"

    history_volume = mean(bar.volume for bar in history_bars)
    test_volume = mean(bar.volume for bar in test_bars)
    volume_ratio = test_volume / history_volume if history_volume else 1.0
    if volume_ratio >= 1.10:
        volume_regime = "expanding"
    elif volume_ratio <= 0.90:
        volume_regime = "contracting"
    else:
        volume_regime = "stable"

    return {
        "trend": trend,
        "volatility": volatility_regime,
        "volume": volume_regime,
        "history_return": round(history_return, 6),
        "test_market_return": round(test_return, 6),
        "daily_volatility": round(volatility, 6),
        "volume_ratio": round(volume_ratio, 6),
    }


def _cost_attribution(trades: list[dict]) -> dict:
    fees = sum(float(trade.get("fees") or 0.0) for trade in trades)
    slippage = 0.0
    raw_gross = 0.0
    adjusted_gross = 0.0
    for trade in trades:
        shares = int(trade.get("shares") or 0)
        raw_entry = float(trade.get("raw_entry_price") or 0.0)
        raw_exit = float(trade.get("raw_exit_price") or 0.0)
        buy_price = float(trade.get("buy_price") or raw_entry)
        sell_price = float(trade.get("sell_price") or raw_exit)
        raw_gross += shares * (raw_exit - raw_entry)
        adjusted_gross += shares * (sell_price - buy_price)
        slippage += shares * ((buy_price - raw_entry) + (raw_exit - sell_price))

    net = adjusted_gross - fees
    return {
        "fees": round(fees, 2),
        "fee_drag_ratio": round(fees / STARTING_CAPITAL, 6),
        "slippage_drag": round(slippage, 2),
        "slippage_drag_ratio": round(slippage / STARTING_CAPITAL, 6),
        "raw_gross_pnl": round(raw_gross, 2),
        "adjusted_gross_pnl": round(adjusted_gross, 2),
        "estimated_net_pnl": round(net, 2),
    }


def _trade_frequency(trade_count: int) -> str:
    ratio = trade_count / TEST_BARS
    if ratio >= 0.20:
        return "high"
    if ratio >= 0.10:
        return "medium"
    return "low"


def _group(rows: list[dict], key: str) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["regime"][key]].append(row)

    result = []
    for label in sorted(grouped):
        items = grouped[label]
        champion_returns = [float(row["champion_return"]) for row in items]
        excess_returns = [
            float(row["champion_return"]) - float(row["benchmark_return"])
            for row in items
        ]
        result.append({
            "label": label,
            "sample_count": len(items),
            "mean_champion_return": round(mean(champion_returns), 6),
            "mean_excess_return": round(mean(excess_returns), 6),
            "positive_ratio": round(
                sum(int(value > 0) for value in champion_returns) / len(items),
                6,
            ),
            "benchmark_outperform_ratio": round(
                sum(int(value > 0) for value in excess_returns) / len(items),
                6,
            ),
        })
    return result


def _research_input(rows: list[dict], groups: dict) -> dict:
    loss_rows = [row for row in rows if row["champion_return"] < 0]
    cost_drag = mean(
        row["costs"]["fee_drag_ratio"] + row["costs"]["slippage_drag_ratio"]
        for row in rows
    )

    weak_regimes = []
    for dimension, values in groups.items():
        for value in values:
            if (
                value["sample_count"] >= MIN_REGIME_SAMPLES
                and value["mean_excess_return"] < 0
            ):
                weak_regimes.append({
                    "dimension": dimension,
                    **value,
                })

    high_frequency_losses = [
        row for row in loss_rows if row["trade_frequency"] == "high"
    ]
    if high_frequency_losses and len(high_frequency_losses) >= MIN_REGIME_SAMPLES:
        primary_hypothesis = "investigate_turnover_and_entry_quality_before_new_generation"
    elif weak_regimes:
        primary_hypothesis = "investigate_regime_guard_before_new_generation"
    else:
        primary_hypothesis = "insufficient_common_failure_pattern_keep_current_champion_and_collect_more_data"

    return {
        "automatic_strategy_change": False,
        "primary_hypothesis": primary_hypothesis,
        "loss_window_count": len(loss_rows),
        "mean_cost_drag_ratio": round(cost_drag, 6),
        "high_frequency_loss_count": len(high_frequency_losses),
        "weak_regimes": weak_regimes,
        "next_step": (
            "Use these diagnostics as Research Queue input. "
            "Do not tune the active champion in place; any change must be a new hypothesis/generation."
        ),
    }


def run_strategy_diagnosis(
    *,
    provider=None,
    symbols: tuple[str, ...] = FIXED_UNIVERSE,
    as_of: date | None = None,
    champion_spec: dict | None = None,
) -> dict:
    current_date = as_of or date.today()
    data_provider = provider or YahooChartDailyBarProvider()
    spec = champion_spec or CURRENT_CHAMPION_SPEC

    rows = []
    excluded = []
    source_hashes = {}

    for symbol in symbols:
        try:
            batch = data_provider.load_batch(symbol, as_of=current_date)
            bars = list(batch.bars)
            last_date = date.fromisoformat(bars[-1].date)
            if current_date - last_date > timedelta(days=STALE_AFTER_DAYS):
                excluded.append({"symbol": symbol, "reason": "stale_data"})
                continue

            source_hashes[symbol] = batch.source_sha256
            evaluated_for_symbol = 0
            for window_index, (start, end, split_index) in enumerate(
                _window_slices(len(bars)),
                start=1,
            ):
                window_batch = _slice_batch(batch, start, end)
                window_bars = list(window_batch.bars)
                history_bars = window_bars[:split_index]
                test_bars = window_bars[split_index:]

                champion = _strategy_walk_forward(
                    window_batch,
                    split_index=split_index,
                    champion_spec=spec,
                )
                benchmark = _buy_hold_benchmark(
                    window_batch,
                    split_index=split_index,
                )
                if not benchmark["traded"]:
                    continue

                regime = classify_regime(history_bars, test_bars)
                trades = champion.get("trades") or []
                costs = _cost_attribution(trades)
                champion_return = float(champion["metrics"]["total_return"])
                benchmark_return = float(benchmark["metrics"]["total_return"])
                rows.append({
                    "symbol": symbol,
                    "window_index": window_index,
                    "test_start": test_bars[0].date,
                    "test_end": test_bars[-1].date,
                    "regime": regime,
                    "trade_frequency": _trade_frequency(
                        int(champion["metrics"]["trade_count"])
                    ),
                    "champion_return": champion_return,
                    "benchmark_return": benchmark_return,
                    "excess_return": round(champion_return - benchmark_return, 6),
                    "max_drawdown": champion["metrics"]["max_drawdown"],
                    "trade_count": champion["metrics"]["trade_count"],
                    "win_rate": champion["metrics"]["win_rate"],
                    "costs": costs,
                })
                evaluated_for_symbol += 1

            if evaluated_for_symbol < MIN_WINDOWS_PER_SYMBOL:
                excluded.append({
                    "symbol": symbol,
                    "reason": "insufficient_diagnostic_coverage",
                    "evaluated_windows": evaluated_for_symbol,
                })
                rows = [row for row in rows if row["symbol"] != symbol]
        except Exception as exc:
            excluded.append({
                "symbol": symbol,
                "reason": "data_unavailable_or_invalid",
                "detail": type(exc).__name__,
            })

    eligible_symbols = sorted({row["symbol"] for row in rows})
    if len(eligible_symbols) < MIN_ELIGIBLE_SYMBOLS:
        raise RuntimeError(
            f"diagnosis requires {MIN_ELIGIBLE_SYMBOLS} eligible symbols; "
            f"got {len(eligible_symbols)}"
        )

    groups = {
        "trend": _group(rows, "trend"),
        "volatility": _group(rows, "volatility"),
        "volume": _group(rows, "volume"),
    }
    research_input = _research_input(rows, groups)

    champion_returns = [row["champion_return"] for row in rows]
    benchmark_returns = [row["benchmark_return"] for row in rows]
    aggregate_champion = {
        "strategy": spec["strategy_key"],
        "traded": True,
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": round(
                STARTING_CAPITAL * (1 + mean(champion_returns)),
                2,
            ),
            "total_return": round(mean(champion_returns), 6),
            "max_drawdown": round(mean(row["max_drawdown"] for row in rows), 6),
            "trade_count": sum(int(row["trade_count"]) for row in rows),
            "win_rate": round(mean(row["win_rate"] for row in rows), 6),
        },
        "trade": None,
        "trades": [],
    }
    aggregate_benchmark = {
        "strategy": "buy_hold_100_lot_benchmark",
        "traded": True,
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": round(
                STARTING_CAPITAL * (1 + mean(benchmark_returns)),
                2,
            ),
            "total_return": round(mean(benchmark_returns), 6),
            "max_drawdown": 0.0,
            "trade_count": len(rows),
            "win_rate": round(
                sum(int(value > 0) for value in benchmark_returns) / len(rows),
                6,
            ),
        },
        "trade": None,
        "trades": [],
    }

    return {
        "mode": "historical_strategy_diagnosis",
        "data_source": "yahoo_chart_public_endpoint",
        "starting_capital": STARTING_CAPITAL,
        "live_trading": False,
        "symbol": "MULTI-DIAGNOSIS",
        "source": {
            "provider": "Yahoo Finance chart JSON",
            "range": "2y",
            "per_symbol_sha256": source_hashes,
        },
        "diagnosis": {
            "champion_frozen": spec["strategy_key"],
            "parameter_tuning": False,
            "eligible_symbols": eligible_symbols,
            "excluded": excluded,
            "window_count": len(rows),
            "grouped_regimes": groups,
            "research_input": research_input,
        },
        "per_window_diagnostics": rows,
        "summary": {
            "champion_strategy": spec["strategy_key"],
            "eligible_symbol_count": len(eligible_symbols),
            "diagnosed_window_count": len(rows),
            "loss_window_count": sum(
                int(row["champion_return"] < 0) for row in rows
            ),
            "benchmark_loss_window_count": sum(
                int(row["excess_return"] < 0) for row in rows
            ),
            "mean_champion_return": round(mean(champion_returns), 6),
            "mean_benchmark_return": round(mean(benchmark_returns), 6),
            "primary_hypothesis": research_input["primary_hypothesis"],
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "strategies": [aggregate_champion, aggregate_benchmark],
    }
