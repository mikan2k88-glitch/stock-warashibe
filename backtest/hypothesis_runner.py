from __future__ import annotations

from config import STARTING_CAPITAL
from backtest.scenario_runner import scenario_bars
from metrics.evaluator import evaluate_capital_path
from simulation.trading_simulator import simulate_one_trade
from strategies.mean_reversion import MeanReversionStrategy
from strategies.mean_reversion_trend_guard import MeanReversionTrendGuardStrategy


def _run(strategy, bars):
    trade = simulate_one_trade(
        symbol="DEMO",
        bars=bars,
        capital=STARTING_CAPITAL,
        strategy=strategy,
    )
    if trade is None:
        return {
            "traded": False,
            "final_capital": STARTING_CAPITAL,
            "total_return": 0.0,
            "trade": None,
        }

    metrics = evaluate_capital_path([STARTING_CAPITAL, trade.capital_after])
    return {
        "traded": True,
        "final_capital": metrics["final_capital"],
        "total_return": metrics["total_return"],
        "trade": trade.to_dict(),
    }


def run_hypothesis_ab_test() -> dict:
    rows = []
    for scenario, bars in scenario_bars().items():
        baseline = _run(MeanReversionStrategy(), bars)
        candidate = _run(MeanReversionTrendGuardStrategy(), bars)
        rows.append(
            {
                "scenario": scenario,
                "baseline": baseline,
                "candidate": candidate,
                "delta_final_capital": round(
                    candidate["final_capital"] - baseline["final_capital"], 2
                ),
            }
        )

    by_scenario = {row["scenario"]: row for row in rows}
    downtrend_improved = (
        by_scenario["downtrend"]["candidate"]["final_capital"]
        > by_scenario["downtrend"]["baseline"]["final_capital"]
    )
    reversal_preserved = (
        by_scenario["reversal"]["candidate"]["final_capital"]
        >= by_scenario["reversal"]["baseline"]["final_capital"]
    )

    verdict = "validated" if downtrend_improved and reversal_preserved else "rejected"
    return {
        "hypothesis_type": "mean_reversion_trend_guard",
        "acceptance_criteria": {
            "downtrend_loss_reduced": True,
            "reversal_gain_preserved": True,
        },
        "observed": {
            "downtrend_improved": downtrend_improved,
            "reversal_preserved": reversal_preserved,
        },
        "verdict": verdict,
        "comparisons": rows,
    }
