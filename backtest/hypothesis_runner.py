from __future__ import annotations

from config import STARTING_CAPITAL
from backtest.scenario_runner import scenario_bars
from metrics.evaluator import evaluate_capital_path
from simulation.trading_simulator import simulate_one_trade
from strategies.mean_reversion_adaptive_confirmation import (
    MeanReversionAdaptiveConfirmationStrategy,
)
from strategies.mean_reversion_secondary_volume import (
    MeanReversionSecondaryVolumeStrategy,
)
from strategies.mean_reversion_trend_guard import MeanReversionTrendGuardStrategy
from strategies.mean_reversion_volume_confirmation import (
    MeanReversionVolumeConfirmationStrategy,
)
from strategies.registry import build_strategy


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


def _candidate_for_rule(rule: str, proposed_change: dict):
    if rule == "require_non_negative_short_slope_before_mean_reversion_entry":
        return MeanReversionTrendGuardStrategy()
    if rule == "require_volume_acceleration_on_negative_slope":
        return MeanReversionVolumeConfirmationStrategy(
            minimum_volume_ratio=float(proposed_change.get("minimum_volume_ratio", 1.20))
        )
    if rule == "allow_deep_discount_without_volume_confirmation":
        return MeanReversionAdaptiveConfirmationStrategy(
            minimum_volume_ratio=float(proposed_change.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(
                proposed_change.get("deep_discount_threshold", 0.04)
            ),
        )
    if rule == "allow_moderate_discount_with_secondary_volume_confirmation":
        return MeanReversionSecondaryVolumeStrategy(
            minimum_volume_ratio=float(proposed_change.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(
                proposed_change.get("deep_discount_threshold", 0.04)
            ),
            moderate_discount_threshold=float(
                proposed_change.get("moderate_discount_threshold", 0.03)
            ),
            secondary_volume_ratio=float(
                proposed_change.get("secondary_volume_ratio", 1.09)
            ),
        )
    if rule == "lower_deep_discount_threshold":
        return MeanReversionAdaptiveConfirmationStrategy(
            minimum_volume_ratio=float(proposed_change.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(
                proposed_change.get("deep_discount_threshold", 0.035)
            ),
        )
    raise ValueError(f"unsupported hypothesis rule: {rule}")


def run_hypothesis_ab_test(
    proposed_change: dict,
    baseline_spec: dict | None = None,
) -> dict:
    rule = str(proposed_change["rule"])
    baseline_strategy = build_strategy(baseline_spec)
    candidate_strategy = _candidate_for_rule(rule, proposed_change)

    rows = []
    for scenario, bars in scenario_bars().items():
        baseline = _run(baseline_strategy, bars)
        candidate = _run(candidate_strategy, bars)
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

    def preserved(name: str) -> bool:
        return (
            by_scenario[name]["candidate"]["final_capital"]
            >= by_scenario[name]["baseline"]["final_capital"]
        )

    downtrend_preserved = preserved("downtrend")
    reversal_preserved = preserved("reversal")
    weak_reversal_preserved = preserved("weak_reversal")
    sideways_preserved = preserved("sideways")
    moderate_reversal_improved = (
        by_scenario["moderate_reversal"]["candidate"]["final_capital"]
        > by_scenario["moderate_reversal"]["baseline"]["final_capital"]
    )

    if rule == "allow_moderate_discount_with_secondary_volume_confirmation":
        verdict = (
            "validated"
            if (
                moderate_reversal_improved
                and downtrend_preserved
                and reversal_preserved
                and weak_reversal_preserved
                and sideways_preserved
            )
            else "rejected"
        )
        acceptance_criteria = {
            "moderate_reversal_improved": True,
            "downtrend_result_preserved": True,
            "reversal_gain_preserved": True,
            "weak_reversal_gain_preserved": True,
            "sideways_result_preserved": True,
        }
    elif rule == "allow_deep_discount_without_volume_confirmation":
        weak_reversal_improved = (
            by_scenario["weak_reversal"]["candidate"]["final_capital"]
            > by_scenario["weak_reversal"]["baseline"]["final_capital"]
        )
        verdict = (
            "validated"
            if (
                weak_reversal_improved
                and downtrend_preserved
                and reversal_preserved
                and sideways_preserved
            )
            else "rejected"
        )
        acceptance_criteria = {
            "weak_reversal_improved": True,
            "downtrend_result_preserved": True,
            "reversal_gain_preserved": True,
            "sideways_result_preserved": True,
        }
    else:
        downtrend_improved = (
            by_scenario["downtrend"]["candidate"]["final_capital"]
            > by_scenario["downtrend"]["baseline"]["final_capital"]
        )
        verdict = (
            "validated"
            if downtrend_improved and reversal_preserved and sideways_preserved
            else "rejected"
        )
        acceptance_criteria = {
            "downtrend_loss_reduced": True,
            "reversal_gain_preserved": True,
            "sideways_result_preserved": True,
        }

    return {
        "hypothesis_type": rule,
        "baseline_strategy": baseline_spec or {
            "strategy_key": "mean_reversion:g1",
            "strategy_name": "mean_reversion",
            "generation": 1,
            "config": {},
        },
        "acceptance_criteria": acceptance_criteria,
        "observed": {
            "downtrend_preserved": downtrend_preserved,
            "reversal_preserved": reversal_preserved,
            "weak_reversal_preserved": weak_reversal_preserved,
            "sideways_preserved": sideways_preserved,
            "moderate_reversal_improved": moderate_reversal_improved,
        },
        "verdict": verdict,
        "comparisons": rows,
    }
