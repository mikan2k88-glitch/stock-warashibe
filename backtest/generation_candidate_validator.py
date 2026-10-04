from __future__ import annotations

from backtest.historical_hypothesis_evaluator import evaluate_historical_candidates
from backtest.hypothesis_runner import run_hypothesis_ab_test
from backtest.readiness_gate import SYNTHETIC_CHAMPION_SPEC
from research.hypothesis_bridge import build_diagnosis_bridge


def _candidate_record(
    bridge: dict,
    historical: dict,
    synthetic: dict | None,
) -> dict:
    change = bridge["proposed_change"]
    edge_multiple = float(change["edge_multiple"])
    synthetic_accepted = bool(
        synthetic
        and synthetic.get("quality_guard", {}).get("accepted") is True
        and synthetic.get("verdict") == "validated"
    )
    return {
        "queue_key": bridge["queue_key"],
        "candidate_key": (
            "mean_reversion_cost_floor:g6-candidate-x"
            + str(int(edge_multiple))
        ),
        "baseline_strategy_key": bridge["baseline_strategy_key"],
        "baseline_generation": bridge["baseline_generation"],
        "proposed_generation": 6,
        "candidate_strategy_name": "mean_reversion_cost_floor",
        "rule": "require_cost_coverage_on_negative_slope",
        "config": historical["candidate_spec"]["config"],
        "bridge_evidence": bridge["bridge_evidence"],
        "historical_evaluation": historical,
        "synthetic_evaluation": synthetic or {
            "verdict": "not_run",
            "reason": "historical_gate_failed",
        },
        "historical_accepted": historical["accepted"],
        "synthetic_accepted": synthetic_accepted,
    }


def run_generation_candidate_validation(
    diagnosis_result: dict,
    *,
    provider=None,
    symbols=None,
    as_of=None,
) -> dict:
    bridge = build_diagnosis_bridge(diagnosis_result)
    historical_kwargs = {
        "provider": provider,
        "as_of": as_of,
    }
    if symbols is not None:
        historical_kwargs["symbols"] = symbols
    historical = evaluate_historical_candidates(
        bridge,
        **historical_kwargs,
    )
    historical_by_key = {row["queue_key"]: row for row in historical}

    candidate_records = []
    for item in bridge:
        h = historical_by_key[item["queue_key"]]
        synthetic = None
        if h["accepted"]:
            synthetic = run_hypothesis_ab_test(
                item["proposed_change"],
                baseline_spec=SYNTHETIC_CHAMPION_SPEC,
            )
        candidate_records.append(_candidate_record(item, h, synthetic))

    dual_passers = [
        row
        for row in candidate_records
        if row["historical_accepted"] and row["synthetic_accepted"]
    ]
    dual_passers.sort(key=lambda row: float(row["config"]["edge_multiple"]))

    if dual_passers:
        selected = dual_passers[0]
        status = "validated_candidate"
        selected_queue_key = selected["queue_key"]
        rationale = (
            "At least one diagnosis-derived candidate passed the predeclared "
            "historical and synthetic gates. The lowest edge_multiple passer was "
            "selected to avoid maximizing observed backtest return."
        )
    else:
        status = "no_validated_candidate"
        selected_queue_key = None
        rationale = (
            "No diagnosis-derived candidate passed both the historical and "
            "synthetic gates. G5 remains the active baseline and no Generation 6 "
            "promotion is permitted."
        )

    return {
        "status": status,
        "baseline_strategy_key": SYNTHETIC_CHAMPION_SPEC["strategy_key"],
        "baseline_generation": SYNTHETIC_CHAMPION_SPEC["generation"],
        "proposed_generation": 6,
        "automatic_promotion": False,
        "selection_rule": (
            "lowest_predeclared_edge_multiple_among_dual_gate_passers"
        ),
        "selected_queue_key": selected_queue_key,
        "rationale": rationale,
        "bridge_candidates": bridge,
        "historical_evaluations": historical,
        "candidates": candidate_records,
    }
