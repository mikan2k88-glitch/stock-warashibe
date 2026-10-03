from __future__ import annotations

from config import STARTING_CAPITAL
from backtest.scenario_runner import scenario_bars
from metrics.evaluator import evaluate_capital_path
from metrics.quality_guard import evaluate_quality
from simulation.trading_simulator import simulate_one_trade
from strategies.mean_reversion_adaptive_confirmation import (
    MeanReversionAdaptiveConfirmationStrategy,
)
from strategies.mean_reversion_band_volume import MeanReversionBandVolumeStrategy
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
    if rule in {
        "allow_shallow_discount_band_with_tertiary_volume",
        "lower_shallow_discount_floor",
        "lower_tertiary_volume_ratio",
    }:
        return MeanReversionBandVolumeStrategy(
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
            shallow_discount_threshold=float(
                proposed_change.get("shallow_discount_threshold", 0.025)
            ),
            shallow_discount_ceiling=float(
                proposed_change.get("shallow_discount_ceiling", 0.035)
            ),
            tertiary_volume_ratio=float(
                proposed_change.get("tertiary_volume_ratio", 1.08)
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

    core_preserved = [
        "downtrend",
        "reversal",
        "weak_reversal",
        "moderate_reversal",
        "shallow_reversal",
        "sideways",
    ]
    preservation = {name: preserved(name) for name in core_preserved}

    if rule == "allow_shallow_discount_band_with_tertiary_volume":
        target = "shallow_reversal"
    elif rule == "lower_shallow_discount_floor":
        target = "micro_reversal"
    elif rule == "lower_tertiary_volume_ratio":
        target = "thin_volume_reversal"
    elif rule == "allow_moderate_discount_with_secondary_volume_confirmation":
        target = "moderate_reversal"
    elif rule == "allow_deep_discount_without_volume_confirmation":
        target = "weak_reversal"
    else:
        target = "downtrend"

    target_improved = (
        by_scenario[target]["candidate"]["final_capital"]
        > by_scenario[target]["baseline"]["final_capital"]
    )

    if rule in {
        "allow_shallow_discount_band_with_tertiary_volume",
        "lower_shallow_discount_floor",
        "lower_tertiary_volume_ratio",
    }:
        criteria_passed = target_improved and all(preservation.values())
        acceptance_criteria = {
            f"{target}_improved": True,
            **{f"{name}_preserved": True for name in core_preserved},
        }
        observed = {
            f"{target}_improved": target_improved,
            **{f"{name}_preserved": value for name, value in preservation.items()},
        }
    elif rule == "allow_moderate_discount_with_secondary_volume_confirmation":
        criteria_passed = target_improved and all(preservation.values())
        acceptance_criteria = {
            "moderate_reversal_improved": True,
            **{f"{name}_preserved": True for name in core_preserved},
        }
        observed = {
            "moderate_reversal_improved": target_improved,
            **{f"{name}_preserved": value for name, value in preservation.items()},
        }
    elif rule == "allow_deep_discount_without_volume_confirmation":
        criteria_passed = (
            target_improved
            and preservation["downtrend"]
            and preservation["reversal"]
            and preservation["sideways"]
        )
        acceptance_criteria = {
            "weak_reversal_improved": True,
            "downtrend_preserved": True,
            "reversal_preserved": True,
            "sideways_preserved": True,
        }
        observed = {
            "weak_reversal_improved": target_improved,
            "downtrend_preserved": preservation["downtrend"],
            "reversal_preserved": preservation["reversal"],
            "sideways_preserved": preservation["sideways"],
        }
    else:
        criteria_passed = (
            target_improved
            and preservation["reversal"]
            and preservation["sideways"]
        )
        acceptance_criteria = {
            "downtrend_loss_reduced": True,
            "reversal_preserved": True,
            "sideways_preserved": True,
        }
        observed = {
            "downtrend_improved": target_improved,
            "reversal_preserved": preservation["reversal"],
            "sideways_preserved": preservation["sideways"],
        }

    quality_guard = evaluate_quality(
        comparisons=rows,
        baseline_spec=baseline_spec,
        proposed_change=proposed_change,
        criteria_passed=criteria_passed,
    )
    verdict = "validated" if quality_guard["accepted"] else "rejected"

    return {
        "hypothesis_type": rule,
        "baseline_strategy": baseline_spec or {
            "strategy_key": "mean_reversion:g1",
            "strategy_name": "mean_reversion",
            "generation": 1,
            "config": {},
        },
        "acceptance_criteria": acceptance_criteria,
        "observed": observed,
        "quality_guard": quality_guard,
        "verdict": verdict,
        "comparisons": rows,
    }
