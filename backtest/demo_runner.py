from __future__ import annotations

from config import STARTING_CAPITAL
from data.stock_data_adapter import Bar
from metrics.evaluator import evaluate_capital_path
from simulation.trading_simulator import simulate_one_trade
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.random_strategy import RandomStrategy


def demo_bars() -> list[Bar]:
    return [
        Bar("2026-01-01", 100, 102, 99, 100, 50_000),
        Bar("2026-01-02", 101, 104, 100, 102, 55_000),
        Bar("2026-01-03", 103, 106, 102, 105, 60_000),
        Bar("2026-01-04", 106, 109, 105, 108, 70_000),
    ]


def run_demo_comparison() -> dict:
    bars = demo_bars()
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
            results.append(
                {
                    "strategy": strategy.name,
                    "traded": False,
                    "metrics": evaluate_capital_path(
                        [STARTING_CAPITAL, STARTING_CAPITAL]
                    ),
                    "trade": None,
                }
            )
            continue

        results.append(
            {
                "strategy": strategy.name,
                "traded": True,
                "metrics": evaluate_capital_path(
                    [STARTING_CAPITAL, trade.capital_after]
                ),
                "trade": trade.to_dict(),
            }
        )

    return {
        "mode": "demo_backtest",
        "data_source": "deterministic_sample",
        "starting_capital": STARTING_CAPITAL,
        "strategies": results,
    }
