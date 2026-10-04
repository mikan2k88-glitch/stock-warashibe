from __future__ import annotations

from backtest.readiness_gate import SYNTHETIC_CHAMPION_SPEC


EDGE_MULTIPLES = (2.0, 3.0, 4.0)


def build_diagnosis_bridge(diagnosis_result: dict) -> list[dict]:
    diagnosis = diagnosis_result.get("diagnosis") or {}
    research_input = diagnosis.get("research_input") or {}
    source_summary = diagnosis_result.get("summary") or {}

    if diagnosis.get("champion_frozen") != "mean_reversion_band_volume:g5":
        raise ValueError("diagnosis bridge requires frozen G5 baseline")
    if research_input.get("automatic_strategy_change") is not False:
        raise ValueError("diagnosis must forbid automatic strategy changes")

    base = SYNTHETIC_CHAMPION_SPEC
    common = {
        **base["config"],
        "rule": "require_cost_coverage_on_negative_slope",
        "candidate_strategy_name": "mean_reversion_cost_floor",
        "baseline_strategy_key": base["strategy_key"],
        "baseline_generation": base["generation"],
        "live_trading": False,
    }

    bridge_evidence = {
        "diagnosis_mode": diagnosis_result.get("mode"),
        "diagnosed_window_count": source_summary.get("diagnosed_window_count"),
        "loss_window_count": research_input.get("loss_window_count"),
        "high_frequency_loss_count": research_input.get("high_frequency_loss_count"),
        "mean_cost_drag_ratio": research_input.get("mean_cost_drag_ratio"),
        "primary_hypothesis": research_input.get("primary_hypothesis"),
        "parameter_tuning": diagnosis.get("parameter_tuning"),
    }

    items = []
    for priority, multiple in enumerate(EDGE_MULTIPLES, start=1):
        label = str(int(multiple))
        items.append(
            {
                "queue_key": f"diag-g5-cost-floor-x{label}",
                "baseline_strategy_key": base["strategy_key"],
                "baseline_generation": base["generation"],
                "priority": priority * 10,
                "target_strategy": "mean_reversion_cost_floor",
                "target_scenario": "synthetic-cost_churn",
                "question": (
                    "Can a cost-derived minimum edge filter reduce diagnosis-observed "
                    "turnover drag without weakening G5 core behavior?"
                ),
                "hypothesis": (
                    f"Require negative-slope entries to cover {multiple:.0f}x the configured "
                    "round-trip fee+slippage rate before buying."
                ),
                "proposed_change": {
                    **common,
                    "edge_multiple": multiple,
                },
                "expected_effect": (
                    "Reduce low-edge negative-slope entries and transaction-cost drag "
                    "without tuning G5 thresholds to observed market returns."
                ),
                "bridge_evidence": {
                    **bridge_evidence,
                    "candidate_edge_multiple": multiple,
                    "selection_rule": (
                        "Choose the lowest predeclared edge_multiple that passes both "
                        "historical and synthetic gates; do not choose maximum backtest return."
                    ),
                },
            }
        )
    return items
