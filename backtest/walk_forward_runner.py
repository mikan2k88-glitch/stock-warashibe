from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from statistics import mean, median, pstdev

from backtest.historical_runner import _buy_hold_benchmark, _strategy_walk_forward
from backtest.multi_stock_runner import FIXED_UNIVERSE, STALE_AFTER_DAYS
from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from config import DEFAULT_LOT_SIZE, DEFAULT_SLIPPAGE_RATE, STARTING_CAPITAL
from data.remote_market_data import MarketDataBatch
from data.yahoo_chart_provider import YahooChartDailyBarProvider


HISTORY_BARS = 120
TEST_BARS = 60
STEP_BARS = 60
MIN_WINDOWS_PER_SYMBOL = 3
MIN_ELIGIBLE_SYMBOLS = 3


def _window_slices(bar_count: int) -> list[tuple[int, int, int]]:
    windows = []
    start = 0
    while start + HISTORY_BARS + TEST_BARS <= bar_count:
        split_index = HISTORY_BARS
        end = start + HISTORY_BARS + TEST_BARS
        windows.append((start, end, split_index))
        start += STEP_BARS
    return windows


def _slice_batch(batch: MarketDataBatch, start: int, end: int) -> MarketDataBatch:
    return replace(
        batch,
        bars=batch.bars[start:end],
        adjusted_close=batch.adjusted_close[start:end],
    )


def _entry_lot_cost(batch: MarketDataBatch, split_index: int) -> float:
    bars = list(batch.bars)
    entry_index = split_index + 1
    if entry_index >= len(bars):
        raise ValueError("window has no entry bar")
    return (
        bars[entry_index].open
        * (1 + DEFAULT_SLIPPAGE_RATE)
        * DEFAULT_LOT_SIZE
    )


def run_walk_forward_validation(
    *,
    provider=None,
    symbols: tuple[str, ...] = FIXED_UNIVERSE,
    as_of: date | None = None,
    champion_spec: dict | None = None,
) -> dict:
    current_date = as_of or date.today()
    data_provider = provider or YahooChartDailyBarProvider()
    spec = champion_spec or CURRENT_CHAMPION_SPEC

    symbol_rows = []
    excluded = []

    for symbol in symbols:
        try:
            batch = data_provider.load_batch(symbol, as_of=current_date)
            bars = list(batch.bars)
            last_date = date.fromisoformat(bars[-1].date)
            if current_date - last_date > timedelta(days=STALE_AFTER_DAYS):
                excluded.append({
                    "symbol": symbol,
                    "reason": "stale_data",
                    "last_date": bars[-1].date,
                })
                continue

            windows = []
            for window_index, (start, end, split_index) in enumerate(
                _window_slices(len(bars)),
                start=1,
            ):
                window_batch = _slice_batch(batch, start, end)
                lot_cost = _entry_lot_cost(window_batch, split_index)
                if lot_cost > STARTING_CAPITAL:
                    windows.append({
                        "window_index": window_index,
                        "status": "skipped",
                        "reason": "unaffordable_100_share_lot",
                        "estimated_lot_cost": round(lot_cost, 2),
                    })
                    continue

                champion = _strategy_walk_forward(
                    window_batch,
                    split_index=split_index,
                    champion_spec=spec,
                )
                benchmark = _buy_hold_benchmark(
                    window_batch,
                    split_index=split_index,
                )
                window_bars = list(window_batch.bars)
                champion_return = float(champion["metrics"]["total_return"])
                benchmark_return = float(benchmark["metrics"]["total_return"])
                windows.append({
                    "window_index": window_index,
                    "status": "evaluated",
                    "history_start": window_bars[0].date,
                    "history_end": window_bars[split_index - 1].date,
                    "test_start": window_bars[split_index].date,
                    "test_end": window_bars[-1].date,
                    "champion_final_capital": champion["metrics"]["final_capital"],
                    "benchmark_final_capital": benchmark["metrics"]["final_capital"],
                    "champion_return": champion_return,
                    "benchmark_return": benchmark_return,
                    "champion_max_drawdown": champion["metrics"]["max_drawdown"],
                    "champion_trade_count": champion["metrics"]["trade_count"],
                    "champion_win_rate": champion["metrics"]["win_rate"],
                    "positive_return": champion_return > 0,
                    "outperformed_benchmark": champion_return > benchmark_return,
                })

            evaluated = [row for row in windows if row["status"] == "evaluated"]
            if len(evaluated) < MIN_WINDOWS_PER_SYMBOL:
                excluded.append({
                    "symbol": symbol,
                    "reason": "insufficient_walk_forward_coverage",
                    "evaluated_windows": len(evaluated),
                })
                continue

            returns = [row["champion_return"] for row in evaluated]
            benchmark_returns = [row["benchmark_return"] for row in evaluated]
            symbol_rows.append({
                "symbol": symbol,
                "source_sha256": batch.source_sha256,
                "last_date": bars[-1].date,
                "window_count": len(evaluated),
                "positive_window_count": sum(
                    int(row["positive_return"]) for row in evaluated
                ),
                "outperformed_window_count": sum(
                    int(row["outperformed_benchmark"]) for row in evaluated
                ),
                "median_return": round(median(returns), 6),
                "mean_return": round(mean(returns), 6),
                "return_stdev": round(pstdev(returns), 6),
                "benchmark_mean_return": round(mean(benchmark_returns), 6),
                "windows": evaluated,
            })
        except Exception as exc:
            excluded.append({
                "symbol": symbol,
                "reason": "data_unavailable_or_invalid",
                "detail": type(exc).__name__,
            })

    if len(symbol_rows) < MIN_ELIGIBLE_SYMBOLS:
        raise RuntimeError(
            f"walk-forward validation requires {MIN_ELIGIBLE_SYMBOLS} eligible symbols; "
            f"got {len(symbol_rows)}"
        )

    all_windows = [
        window
        for row in symbol_rows
        for window in row["windows"]
    ]
    champion_returns = [row["champion_return"] for row in all_windows]
    benchmark_returns = [row["benchmark_return"] for row in all_windows]
    positive_windows = sum(int(row["positive_return"]) for row in all_windows)
    outperform_windows = sum(
        int(row["outperformed_benchmark"]) for row in all_windows
    )

    champion_average_final = round(
        mean(row["champion_final_capital"] for row in all_windows),
        2,
    )
    benchmark_average_final = round(
        mean(row["benchmark_final_capital"] for row in all_windows),
        2,
    )

    aggregate_champion = {
        "strategy": spec["strategy_key"],
        "traded": True,
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": champion_average_final,
            "total_return": round(mean(champion_returns), 6),
            "max_drawdown": round(
                mean(row["champion_max_drawdown"] for row in all_windows),
                6,
            ),
            "trade_count": sum(
                int(row["champion_trade_count"]) for row in all_windows
            ),
            "win_rate": round(
                mean(row["champion_win_rate"] for row in all_windows),
                6,
            ),
        },
        "trade": None,
        "trades": [],
    }
    aggregate_benchmark = {
        "strategy": "buy_hold_100_lot_benchmark",
        "traded": True,
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": benchmark_average_final,
            "total_return": round(mean(benchmark_returns), 6),
            "max_drawdown": 0.0,
            "trade_count": len(all_windows),
            "win_rate": round(
                sum(int(value > 0) for value in benchmark_returns)
                / len(benchmark_returns),
                6,
            ),
        },
        "trade": None,
        "trades": [],
    }

    return {
        "mode": "historical_walk_forward_validation",
        "data_source": "yahoo_chart_public_endpoint",
        "starting_capital": STARTING_CAPITAL,
        "live_trading": False,
        "symbol": "MULTI-WALK-FORWARD",
        "walk_forward": {
            "method": "rolling_fixed_parameter",
            "history_bars": HISTORY_BARS,
            "test_bars": TEST_BARS,
            "step_bars": STEP_BARS,
            "parameter_tuning": False,
            "champion_frozen": spec["strategy_key"],
            "minimum_windows_per_symbol": MIN_WINDOWS_PER_SYMBOL,
            "eligible_symbols": [row["symbol"] for row in symbol_rows],
            "excluded": excluded,
            "survivor_bias_eliminated": False,
            "point_in_time_universe": False,
        },
        "source": {
            "provider": "Yahoo Finance chart JSON",
            "range": "2y",
            "per_symbol_sha256": {
                row["symbol"]: row["source_sha256"] for row in symbol_rows
            },
        },
        "per_symbol": symbol_rows,
        "summary": {
            "champion_strategy": spec["strategy_key"],
            "eligible_symbol_count": len(symbol_rows),
            "evaluated_window_count": len(all_windows),
            "positive_window_count": positive_windows,
            "outperformed_benchmark_window_count": outperform_windows,
            "positive_window_ratio": round(
                positive_windows / len(all_windows),
                6,
            ),
            "outperformed_benchmark_window_ratio": round(
                outperform_windows / len(all_windows),
                6,
            ),
            "champion_mean_return": round(mean(champion_returns), 6),
            "champion_median_return": round(median(champion_returns), 6),
            "champion_return_stdev": round(pstdev(champion_returns), 6),
            "benchmark_mean_return": round(mean(benchmark_returns), 6),
            "champion_average_final_capital": champion_average_final,
            "benchmark_average_final_capital": benchmark_average_final,
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "strategies": [aggregate_champion, aggregate_benchmark],
    }
