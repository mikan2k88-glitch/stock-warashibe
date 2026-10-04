from __future__ import annotations


def _failed_soft_checks(gate: dict) -> list[str]:
    return [
        name
        for name, passed in (gate.get("soft_checks") or {}).items()
        if not passed
    ]


def diagnose_robustness_failure(
    robustness_result: dict,
    provenance_result: dict,
) -> dict:
    summary = robustness_result.get("summary") or {}
    robustness = robustness_result.get("robustness") or {}
    gate = robustness.get("gate") or {}
    sector_rows = robustness.get("sector_metrics") or []

    weak_sectors = sorted(
        [
            {
                "sector": row.get("sector"),
                "mean_champion_return": row.get("mean_champion_return"),
                "mean_excess_return": row.get("mean_excess_return"),
                "window_count": row.get("window_count"),
            }
            for row in sector_rows
            if float(row.get("mean_champion_return") or 0.0) < 0
        ],
        key=lambda row: float(row["mean_champion_return"]),
    )

    causes = []
    mean_return = float(summary.get("champion_mean_return") or 0.0)
    positive_ratio = float(summary.get("positive_window_ratio") or 0.0)
    outperform_ratio = float(summary.get("outperformed_benchmark_window_ratio") or 0.0)
    stdev = float(summary.get("champion_return_stdev") or 0.0)

    if mean_return < -0.01:
        causes.append("negative_mean_return")
    if positive_ratio < 0.40:
        causes.append("low_positive_window_ratio")
    if outperform_ratio < 0.45:
        causes.append("low_benchmark_outperformance")
    if stdev > 0.20:
        causes.append("high_return_dispersion")
    if weak_sectors:
        causes.append("sector_concentration_of_weakness")
    if provenance_result.get("verified") is not True:
        causes.append("point_in_time_universe_unverified")

    priority = []
    if "point_in_time_universe_unverified" in causes:
        priority.append("reconstruct_point_in_time_universe")
    if "high_return_dispersion" in causes:
        priority.append("diagnose_tail_windows_and_regime_dependence")
    if "sector_concentration_of_weakness" in causes:
        priority.append("diagnose_sector_specific_failure")
    if "negative_mean_return" in causes or "low_positive_window_ratio" in causes:
        priority.append("retain_g6_without_parameter_tuning_and_collect_more_evidence")

    return {
        "mode": "g6_robustness_failure_diagnosis",
        "champion_strategy": summary.get("champion_strategy"),
        "paper_trading_allowed": False,
        "automatic_strategy_change": False,
        "gate_decision": gate.get("decision"),
        "gate_score": gate.get("soft_score"),
        "failed_soft_checks": _failed_soft_checks(gate),
        "root_causes": causes,
        "weak_sectors": weak_sectors[:5],
        "priority_actions": priority,
        "point_in_time": provenance_result,
        "decision": "research_hold_root_cause_confirmed",
        "rationale": (
            "G6 remains blocked from paper trading because the expanded historical evidence "
            "shows weak aggregate robustness and the point-in-time universe is still unverified."
        ),
    }
