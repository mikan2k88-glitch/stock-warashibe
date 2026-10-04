from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean, median, pstdev

from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from backtest.historical_runner import _buy_hold_benchmark, _strategy_walk_forward
from backtest.robustness_universe import ROBUSTNESS_UNIVERSE, UNIVERSE_POLICY
from backtest.walk_forward_runner import _entry_lot_cost, _slice_batch, _window_slices
from config import STARTING_CAPITAL
from data.coverage_guard import assess_coverage
from data.yahoo_chart_provider import YahooChartDailyBarProvider
from strategies.registry import build_strategy


MIN_ELIGIBLE_SYMBOLS = 8
MIN_SECTORS = 4
MIN_EVALUATED_WINDOWS = 80
MIN_SOFT_SCORE = 70


def _group_sector(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["sector"]].append(row)
    result = []
    for sector in sorted(grouped):
        items = grouped[sector]
        returns = [window["champion_return"] for item in items for window in item["windows"]]
        benchmark = [window["benchmark_return"] for item in items for window in item["windows"]]
        result.append({
            "sector": sector,
            "symbol_count": len(items),
            "window_count": len(returns),
            "mean_champion_return": round(mean(returns), 6),
            "mean_benchmark_return": round(mean(benchmark), 6),
            "mean_excess_return": round(
                mean(c - b for c, b in zip(returns, benchmark)), 6
            ),
        })
    return result


def _gate(summary: dict, sector_rows: list[dict], coverage_rows: list[dict]) -> dict:
    worst_sector = min(
        (row["mean_champion_return"] for row in sector_rows),
        default=-1.0,
    )
    hard_checks = {
        "eligible_symbols_at_least_8": summary["eligible_symbol_count"] >= MIN_ELIGIBLE_SYMBOLS,
        "sector_count_at_least_4": summary["sector_count"] >= MIN_SECTORS,
        "windows_at_least_80": summary["evaluated_window_count"] >= MIN_EVALUATED_WINDOWS,
        "long_coverage_all_eligible": all(row["accepted"] for row in coverage_rows),
        "point_in_time_universe_verified": False,
        "no_parameter_tuning": True,
        "live_trading_disabled": True,
    }
    soft_checks = {
        "mean_return_not_below_minus_1pct": summary["champion_mean_return"] >= -0.01,
        "positive_window_ratio_at_least_40pct": summary["positive_window_ratio"] >= 0.40,
        "benchmark_outperform_ratio_at_least_45pct": (
            summary["outperformed_benchmark_window_ratio"] >= 0.45
        ),
        "worst_sector_mean_above_minus_8pct": worst_sector >= -0.08,
        "return_stdev_below_20pct": summary["champion_return_stdev"] <= 0.20,
    }
    score = round(100 * sum(soft_checks.values()) / len(soft_checks))
    operational_checks = {
        key: value
        for key, value in hard_checks.items()
        if key != "point_in_time_universe_verified"
    }
    metrics_pass = all(operational_checks.values()) and score >= MIN_SOFT_SCORE

    if not hard_checks["point_in_time_universe_verified"]:
        decision = "research_hold_bias_guard"
        rationale = (
            "Robustness metrics are recorded, but paper-trading progression is blocked "
            "because the expanded universe is not a verified historical point-in-time universe."
        )
    elif metrics_pass:
        decision = "research_accept"
        rationale = "Predeclared robustness and bias checks passed."
    else:
        decision = "research_hold_metrics"
        rationale = "One or more predeclared robustness thresholds failed."

    return {
        "decision": decision,
        "rationale": rationale,
        "soft_score": score,
        "minimum_soft_score": MIN_SOFT_SCORE,
        "hard_checks": hard_checks,
        "soft_checks": soft_checks,
        "metrics_pass": metrics_pass,
        "paper_trading_allowed": decision == "research_accept",
        "automatic_strategy_change": False,
        "next_action": (
            "Obtain or construct a defensible point-in-time universe before paper trading."
            if decision == "research_hold_bias_guard"
            else "Continue according to gate decision."
        ),
    }


def run_robustness_validation(
    *,
    provider=None,
    universe=ROBUSTNESS_UNIVERSE,
    as_of: date | None = None,
) -> dict:
    current_date = as_of or date.today()
    data_provider = provider or YahooChartDailyBarProvider(range_value="5y")

    eligible = []
    excluded = []
    coverage = []

    for member in universe:
        try:
            batch = data_provider.load_batch(member.symbol, as_of=current_date)
            coverage_result = assess_coverage(batch, as_of=current_date)
            coverage_result = {"symbol": member.symbol, "sector": member.sector, **coverage_result}
            if not coverage_result["accepted"]:
                excluded.append({
                    "symbol": member.symbol,
                    "sector": member.sector,
                    "reason": "coverage_guard_failed",
                    "details": coverage_result["reasons"],
                })
                continue

            bars = list(batch.bars)
            latest_lot_cost = bars[-1].close * 100
            if latest_lot_cost > STARTING_CAPITAL:
                excluded.append({
                    "symbol": member.symbol,
                    "sector": member.sector,
                    "reason": "current_100_share_lot_unaffordable",
                    "estimated_lot_cost": round(latest_lot_cost, 2),
                })
                continue

            windows = []
            for window_index, (start, end, split_index) in enumerate(
                _window_slices(len(bars)),
                start=1,
            ):
                window_batch = _slice_batch(batch, start, end)
                if _entry_lot_cost(window_batch, split_index) > STARTING_CAPITAL:
                    continue
                champion = _strategy_walk_forward(
                    window_batch,
                    split_index=split_index,
                    champion_spec=CURRENT_CHAMPION_SPEC,
                )
                benchmark = _buy_hold_benchmark(
                    window_batch,
                    split_index=split_index,
                )
                if not benchmark["traded"]:
                    continue
                cr = float(champion["metrics"]["total_return"])
                br = float(benchmark["metrics"]["total_return"])
                windows.append({
                    "window_index": window_index,
                    "champion_return": cr,
                    "benchmark_return": br,
                    "excess_return": round(cr - br, 6),
                    "champion_final_capital": champion["metrics"]["final_capital"],
                    "benchmark_final_capital": benchmark["metrics"]["final_capital"],
                    "champion_max_drawdown": champion["metrics"]["max_drawdown"],
                    "champion_trade_count": champion["metrics"]["trade_count"],
                    "champion_win_rate": champion["metrics"]["win_rate"],
                    "positive_return": cr > 0,
                    "outperformed_benchmark": cr > br,
                })

            if not windows:
                excluded.append({
                    "symbol": member.symbol,
                    "sector": member.sector,
                    "reason": "no_affordable_walk_forward_windows",
                })
                continue

            latest_signal = build_strategy(CURRENT_CHAMPION_SPEC).evaluate(bars[-3:])
            coverage.append(coverage_result)
            eligible.append({
                "symbol": member.symbol,
                "sector": member.sector,
                "source_sha256": batch.source_sha256,
                "bar_count": len(bars),
                "window_count": len(windows),
                "mean_return": round(mean(w["champion_return"] for w in windows), 6),
                "benchmark_mean_return": round(mean(w["benchmark_return"] for w in windows), 6),
                "latest_snapshot": {
                    "date": bars[-1].date,
                    "close": bars[-1].close,
                    "action": latest_signal.action,
                    "score": latest_signal.score,
                    "reason": latest_signal.reason,
                },
                "windows": windows,
            })
        except Exception as exc:
            excluded.append({
                "symbol": member.symbol,
                "sector": member.sector,
                "reason": "data_unavailable_or_invalid",
                "detail": type(exc).__name__,
            })

    if len(eligible) < 3:
        raise RuntimeError(f"robustness validation has too few eligible symbols: {len(eligible)}")

    all_windows = [window for item in eligible for window in item["windows"]]
    champion_returns = [row["champion_return"] for row in all_windows]
    benchmark_returns = [row["benchmark_return"] for row in all_windows]
    positive = sum(int(row["positive_return"]) for row in all_windows)
    outperform = sum(int(row["outperformed_benchmark"]) for row in all_windows)
    sector_rows = _group_sector(eligible)

    summary = {
        "champion_strategy": CURRENT_CHAMPION_SPEC["strategy_key"],
        "candidate_symbol_count": len(universe),
        "eligible_symbol_count": len(eligible),
        "excluded_symbol_count": len(excluded),
        "sector_count": len({row["sector"] for row in eligible}),
        "evaluated_window_count": len(all_windows),
        "positive_window_count": positive,
        "outperformed_benchmark_window_count": outperform,
        "positive_window_ratio": round(positive / len(all_windows), 6),
        "outperformed_benchmark_window_ratio": round(outperform / len(all_windows), 6),
        "champion_mean_return": round(mean(champion_returns), 6),
        "champion_median_return": round(median(champion_returns), 6),
        "champion_return_stdev": round(pstdev(champion_returns), 6),
        "benchmark_mean_return": round(mean(benchmark_returns), 6),
        "champion_average_final_capital": round(
            mean(row["champion_final_capital"] for row in all_windows), 2
        ),
        "benchmark_average_final_capital": round(
            mean(row["benchmark_final_capital"] for row in all_windows), 2
        ),
    }
    gate = _gate(summary, sector_rows, coverage)

    champion = {
        "strategy": CURRENT_CHAMPION_SPEC["strategy_key"],
        "traded": True,
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": summary["champion_average_final_capital"],
            "total_return": summary["champion_mean_return"],
            "max_drawdown": round(
                mean(row["champion_max_drawdown"] for row in all_windows), 6
            ),
            "trade_count": sum(row["champion_trade_count"] for row in all_windows),
            "win_rate": round(mean(row["champion_win_rate"] for row in all_windows), 6),
        },
        "trade": None,
        "trades": [],
    }
    benchmark = {
        "strategy": "buy_hold_100_lot_benchmark",
        "traded": True,
        "metrics": {
            "start_capital": STARTING_CAPITAL,
            "final_capital": summary["benchmark_average_final_capital"],
            "total_return": summary["benchmark_mean_return"],
            "max_drawdown": 0.0,
            "trade_count": len(all_windows),
            "win_rate": round(sum(int(v > 0) for v in benchmark_returns) / len(all_windows), 6),
        },
        "trade": None,
        "trades": [],
    }

    return {
        "mode": "g6_robustness_acceptance_gate",
        "data_source": "yahoo_chart_public_endpoint_5y",
        "starting_capital": STARTING_CAPITAL,
        "live_trading": False,
        "symbol": "EXPANDED-MULTI",
        "universe": {
            **UNIVERSE_POLICY,
            "candidate_symbols": [
                {"symbol": member.symbol, "sector": member.sector}
                for member in universe
            ],
            "eligible_symbols": [row["symbol"] for row in eligible],
            "excluded": excluded,
        },
        "coverage": {
            "range": "5y",
            "minimum_bars": 750,
            "minimum_calendar_years": 3,
            "eligible": coverage,
        },
        "robustness": {
            "parameter_tuning": False,
            "champion_frozen": CURRENT_CHAMPION_SPEC["strategy_key"],
            "sector_metrics": sector_rows,
            "gate": gate,
        },
        "per_symbol": eligible,
        "summary": {
            **summary,
            "gate_decision": gate["decision"],
            "gate_score": gate["soft_score"],
            "paper_trading_allowed": gate["paper_trading_allowed"],
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "strategies": [champion, benchmark],
    }
