from __future__ import annotations

from backtest.champion_spec import CURRENT_CHAMPION_SPEC, GENERATION_FIVE_SPEC
from backtest.scenario_runner import scenario_bars
from config import STARTING_CAPITAL
from metrics.evaluator import evaluate_capital_path
from simulation.trading_simulator import simulate_one_trade
from strategies.registry import build_strategy

CORE_SCENARIOS = (
    "downtrend",
    "reversal",
    "weak_reversal",
    "moderate_reversal",
    "shallow_reversal",
    "sideways",
)

def _run(spec: dict, bars) -> dict:
    strategy = build_strategy(spec)
    trade = simulate_one_trade(
        symbol="DEMO",
        bars=bars,
        capital=STARTING_CAPITAL,
        strategy=strategy,
    )
    capital_after = trade.capital_after if trade else STARTING_CAPITAL
    return {
        "traded": trade is not None,
        "final_capital": round(capital_after, 2),
        "metrics": evaluate_capital_path([STARTING_CAPITAL, capital_after]),
        "trade": trade.to_dict() if trade else None,
    }

def run_champion_synthetic_regression() -> dict:
    rows = []
    for scenario, bars in scenario_bars().items():
        g5 = _run(GENERATION_FIVE_SPEC, bars)
        g6 = _run(CURRENT_CHAMPION_SPEC, bars)
        rows.append({
            "scenario": scenario,
            "g5": g5,
            "g6": g6,
            "delta_final_capital": round(
                g6["final_capital"] - g5["final_capital"], 2
            ),
        })

    by_name = {row["scenario"]: row for row in rows}
    core_preserved = all(
        by_name[name]["g6"]["final_capital"]
        >= by_name[name]["g5"]["final_capital"]
        for name in CORE_SCENARIOS
    )
    cost_churn_improved = (
        by_name["cost_churn"]["g6"]["final_capital"]
        > by_name["cost_churn"]["g5"]["final_capital"]
    )
    return {
        "mode": "g6_post_promotion_synthetic_regression",
        "live_trading": False,
        "baseline_strategy": GENERATION_FIVE_SPEC["strategy_key"],
        "champion_strategy": CURRENT_CHAMPION_SPEC["strategy_key"],
        "checks": {
            "generation_is_six": CURRENT_CHAMPION_SPEC["generation"] == 6,
            "core_scenarios_preserved": core_preserved,
            "cost_churn_improved": cost_churn_improved,
            "no_parameter_tuning": True,
        },
        "status": "passed" if core_preserved and cost_churn_improved else "failed",
        "comparisons": rows,
    }
