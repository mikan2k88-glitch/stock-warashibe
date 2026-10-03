from __future__ import annotations

from config import STARTING_CAPITAL
from data.stock_data_adapter import Bar
from metrics.evaluator import evaluate_capital_path
from simulation.trading_simulator import simulate_one_trade
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.random_strategy import RandomStrategy


def scenario_bars() -> dict[str, list[Bar]]:
    return {
        "uptrend": [
            Bar("2026-01-01", 100, 102, 99, 100, 50_000),
            Bar("2026-01-02", 101, 104, 100, 102, 55_000),
            Bar("2026-01-03", 103, 106, 102, 105, 60_000),
            Bar("2026-01-04", 106, 109, 105, 108, 70_000),
        ],
        "downtrend": [
            Bar("2026-01-01", 110, 111, 108, 110, 60_000),
            Bar("2026-01-02", 108, 109, 105, 106, 62_000),
            Bar("2026-01-03", 105, 106, 101, 102, 65_000),
            Bar("2026-01-04", 101, 102, 97, 98, 68_000),
        ],
        "reversal": [
            Bar("2026-01-01", 105, 106, 101, 104, 55_000),
            Bar("2026-01-02", 102, 103, 97, 99, 61_000),
            Bar("2026-01-03", 97, 99, 93, 95, 72_000),
            Bar("2026-01-04", 96, 104, 95, 103, 85_000),
        ],
        "weak_reversal": [
            Bar("2026-01-01", 106, 107, 103, 105, 60_000),
            Bar("2026-01-02", 102, 103, 98, 100, 63_000),
            Bar("2026-01-03", 97, 98, 93, 95, 66_000),
            Bar("2026-01-04", 96, 104, 95, 103, 74_000),
        ],
        "moderate_reversal": [
            Bar("2026-01-01", 105, 106, 102, 104, 60_000),
            Bar("2026-01-02", 102, 103, 99, 101, 63_000),
            Bar("2026-01-03", 98, 99, 95, 97, 66_000),
            Bar("2026-01-04", 98, 104, 97, 103, 74_000),
        ],
        "shallow_reversal": [
            Bar("2026-01-01", 105, 106, 102, 104, 60_000),
            Bar("2026-01-02", 102, 103, 99, 101, 62_000),
            Bar("2026-01-03", 99, 100, 96, 98, 65_000),
            Bar("2026-01-04", 99, 104, 98, 103, 74_000),
        ],
        "micro_reversal": [
            Bar("2026-01-01", 105, 106, 102, 104, 60_000),
            Bar("2026-01-02", 103, 104, 100, 102, 62_000),
            Bar("2026-01-03", 100, 101, 98, 99.5, 65_000),
            Bar("2026-01-04", 100, 102, 99, 100.5, 74_000),
        ],
        "thin_volume_reversal": [
            Bar("2026-01-01", 105, 106, 102, 104, 60_000),
            Bar("2026-01-02", 102, 103, 99, 101, 62_000),
            Bar("2026-01-03", 99, 100, 96, 98, 64_600),
            Bar("2026-01-04", 99, 101, 98, 99, 74_000),
        ],
        "sideways": [
            Bar("2026-01-01", 100, 102, 99, 100, 50_000),
            Bar("2026-01-02", 101, 102, 99, 101, 51_000),
            Bar("2026-01-03", 100, 102, 99, 100, 52_000),
            Bar("2026-01-04", 100, 102, 99, 101, 53_000),
        ],
    }


def run_scenario(name: str, bars: list[Bar]) -> dict:
    strategies = [
        MomentumStrategy(),
        MeanReversionStrategy(),
        RandomStrategy(seed=7),
    ]
    results = []
    for strategy in strategies:
        trade = simulate_one_trade(
            symbol="DEMO",
            bars=bars,
            capital=STARTING_CAPITAL,
            strategy=strategy,
        )
        if trade is None:
            results.append({
                "strategy": strategy.name,
                "traded": False,
                "metrics": evaluate_capital_path([STARTING_CAPITAL, STARTING_CAPITAL]),
                "trade": None,
            })
        else:
            results.append({
                "strategy": strategy.name,
                "traded": True,
                "metrics": evaluate_capital_path([STARTING_CAPITAL, trade.capital_after]),
                "trade": trade.to_dict(),
            })

    best = max(results, key=lambda item: item["metrics"]["final_capital"])
    return {
        "mode": "synthetic_scenario_backtest",
        "data_source": "deterministic_sample",
        "scenario": name,
        "starting_capital": STARTING_CAPITAL,
        "summary": {
            "best_strategy": best["strategy"],
            "best_final_capital": best["metrics"]["final_capital"],
            "strategy_count": len(results),
        },
        "strategies": results,
    }


def run_all_scenarios() -> list[dict]:
    return [run_scenario(name, bars) for name, bars in scenario_bars().items()]
