from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from backtest.historical_runner import IN_SAMPLE_RATIO, run_historical_market_backtest
from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from config import DEFAULT_LOT_SIZE, DEFAULT_SLIPPAGE_RATE, STARTING_CAPITAL
from data.yahoo_chart_provider import YahooChartDailyBarProvider


FIXED_UNIVERSE = (
    "9432.T",
    "6740.T",
    "2370.T",
    "9973.T",
    "8107.T",
)
MIN_ELIGIBLE_STOCKS = 3
STALE_AFTER_DAYS = 10


def _candidate_entry_price(batch) -> float:
    bars = list(batch.bars)
    split_index = max(3, int(len(bars) * IN_SAMPLE_RATIO))
    entry_index = min(split_index + 1, len(bars) - 1)
    return bars[entry_index].open * (1 + DEFAULT_SLIPPAGE_RATE)


def _aggregate_strategy(stock_results: list[dict], strategy_index: int) -> dict:
    rows = [row["result"]["strategies"][strategy_index] for row in stock_results]
    metrics = [row["metrics"] for row in rows]
    return {
        "strategy": rows[0]["strategy"],
        "traded": any(row["traded"] for row in rows),
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": round(mean(m["final_capital"] for m in metrics), 2),
            "total_return": round(mean(m["total_return"] for m in metrics), 6),
            "max_drawdown": round(mean(m["max_drawdown"] for m in metrics), 6),
            "trade_count": sum(int(m["trade_count"]) for m in metrics),
            "win_rate": round(
                sum(
                    float(m["win_rate"]) * int(m["trade_count"])
                    for m in metrics
                )
                / max(1, sum(int(m["trade_count"]) for m in metrics)),
                6,
            ),
        },
        "trade": None,
        "trades": [],
    }


def run_multi_stock_validation(
    *,
    provider=None,
    symbols: tuple[str, ...] = FIXED_UNIVERSE,
    as_of: date | None = None,
    champion_spec: dict | None = None,
) -> dict:
    current_date = as_of or date.today()
    data_provider = provider or YahooChartDailyBarProvider()
    spec = champion_spec or CURRENT_CHAMPION_SPEC

    eligible = []
    excluded = []

    for symbol in symbols:
        try:
            batch = data_provider.load_batch(symbol, as_of=current_date)
            bars = list(batch.bars)
            last_date = date.fromisoformat(bars[-1].date)
            stale = current_date - last_date > timedelta(days=STALE_AFTER_DAYS)
            entry_price = _candidate_entry_price(batch)
            lot_cost = entry_price * DEFAULT_LOT_SIZE

            if stale:
                excluded.append(
                    {
                        "symbol": symbol,
                        "reason": "stale_data",
                        "last_date": bars[-1].date,
                    }
                )
                continue
            if lot_cost > STARTING_CAPITAL:
                excluded.append(
                    {
                        "symbol": symbol,
                        "reason": "unaffordable_100_share_lot",
                        "estimated_lot_cost": round(lot_cost, 2),
                    }
                )
                continue

            result = run_historical_market_backtest(
                batch=batch,
                champion_spec=spec,
                as_of=current_date,
            )
            eligible.append(
                {
                    "symbol": symbol,
                    "entry_price_for_filter": round(entry_price, 4),
                    "estimated_lot_cost": round(lot_cost, 2),
                    "source_sha256": batch.source_sha256,
                    "source_url": batch.source_url,
                    "last_date": bars[-1].date,
                    "result": result,
                }
            )
        except Exception as exc:
            excluded.append(
                {
                    "symbol": symbol,
                    "reason": "data_unavailable_or_invalid",
                    "detail": type(exc).__name__,
                }
            )

    if len(eligible) < MIN_ELIGIBLE_STOCKS:
        raise RuntimeError(
            f"multi-stock validation requires {MIN_ELIGIBLE_STOCKS} eligible stocks; "
            f"got {len(eligible)}"
        )

    champion = _aggregate_strategy(eligible, 0)
    benchmark = _aggregate_strategy(eligible, 1)

    per_symbol = []
    outperform_count = 0
    positive_count = 0
    for row in eligible:
        champion_metrics = row["result"]["strategies"][0]["metrics"]
        benchmark_metrics = row["result"]["strategies"][1]["metrics"]
        outperformed = (
            champion_metrics["final_capital"] > benchmark_metrics["final_capital"]
        )
        positive = champion_metrics["final_capital"] > STARTING_CAPITAL
        outperform_count += int(outperformed)
        positive_count += int(positive)
        per_symbol.append(
            {
                "symbol": row["symbol"],
                "champion_final_capital": champion_metrics["final_capital"],
                "benchmark_final_capital": benchmark_metrics["final_capital"],
                "champion_return": champion_metrics["total_return"],
                "benchmark_return": benchmark_metrics["total_return"],
                "champion_max_drawdown": champion_metrics["max_drawdown"],
                "champion_trade_count": champion_metrics["trade_count"],
                "champion_win_rate": champion_metrics["win_rate"],
                "outperformed_benchmark": outperformed,
                "positive_return": positive,
                "source_sha256": row["source_sha256"],
                "last_date": row["last_date"],
            }
        )

    return {
        "mode": "historical_multi_stock_validation",
        "data_source": "yahoo_chart_public_endpoint",
        "starting_capital": STARTING_CAPITAL,
        "live_trading": False,
        "symbol": "MULTI",
        "universe": {
            "fixed_before_evaluation": True,
            "performance_used_for_selection": False,
            "candidate_symbols": list(symbols),
            "eligible_symbols": [row["symbol"] for row in eligible],
            "excluded": excluded,
            "minimum_eligible_stocks": MIN_ELIGIBLE_STOCKS,
            "affordability_rule": (
                f"{DEFAULT_LOT_SIZE}-share estimated entry lot <= {STARTING_CAPITAL} JPY"
            ),
            "survivor_bias_eliminated": False,
            "survivor_bias_note": (
                "Fixed predeclared tickers reduce performance-selection bias, "
                "but this is not a point-in-time constituent universe."
            ),
        },
        "split": {
            "method": "per_symbol_chronological_70_30",
            "in_sample_ratio": IN_SAMPLE_RATIO,
            "in_sample_used_for_tuning": False,
        },
        "price_policy": {
            "execution_prices": "unadjusted_ohlc",
            "adjusted_close_use": "corporate_action_detection_only",
            "lot_size": DEFAULT_LOT_SIZE,
        },
        "source": {
            "provider": "Yahoo Finance chart JSON",
            "range": "2y",
            "per_symbol_sha256": {
                row["symbol"]: row["source_sha256"] for row in eligible
            },
        },
        "per_symbol": per_symbol,
        "summary": {
            "champion_strategy": spec["strategy_key"],
            "eligible_stock_count": len(eligible),
            "candidate_stock_count": len(symbols),
            "positive_stock_count": positive_count,
            "outperformed_benchmark_count": outperform_count,
            "champion_average_final_capital": champion["metrics"]["final_capital"],
            "benchmark_average_final_capital": benchmark["metrics"]["final_capital"],
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "strategies": [champion, benchmark],
    }
