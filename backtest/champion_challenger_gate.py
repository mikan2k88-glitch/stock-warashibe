from __future__ import annotations

from backtest.champion_spec import CURRENT_CHAMPION_SPEC


def assess_champion_challengers(candidates: list[dict]) -> dict:
    """Rank research-only challengers without mutating the active G6 champion."""
    rows = []
    for candidate in candidates:
        historical = candidate.get("historical_evaluation") or {}
        synthetic = candidate.get("synthetic_evaluation") or {}
        config = candidate.get("config") or {}
        historical_passed = (
            candidate.get("historical_accepted") is True
            and historical.get("accepted") is True
        )
        synthetic_passed = (
            candidate.get("synthetic_accepted") is True
            and synthetic.get("verdict") == "validated"
            and (synthetic.get("quality_guard") or {}).get("accepted") is True
        )
        dual_gate_passed = historical_passed and synthetic_passed
        rows.append({
            "queue_key": candidate.get("queue_key"),
            "candidate_key": candidate.get("candidate_key"),
            "edge_multiple": config.get("edge_multiple"),
            "historical_passed": historical_passed,
            "synthetic_passed": synthetic_passed,
            "dual_gate_passed": dual_gate_passed,
            "research_eligible": dual_gate_passed,
        })

    eligible = [
        row for row in rows
        if row["research_eligible"] and row["edge_multiple"] is not None
    ]
    eligible.sort(key=lambda row: (float(row["edge_multiple"]), str(row["queue_key"])))
    selected = eligible[0] if eligible else None

    return {
        "endpoint": "052",
        "mode": "champion_challenger_historical_research_gate",
        "status": "research_candidate_available" if selected else "no_research_candidate",
        "champion_strategy_key": CURRENT_CHAMPION_SPEC["strategy_key"],
        "champion_generation": int(CURRENT_CHAMPION_SPEC["generation"]),
        "champion_frozen": True,
        "selection_rule": "lowest_predeclared_edge_multiple_among_dual_gate_passers",
        "selected_research_queue_key": selected["queue_key"] if selected else None,
        "candidates": rows,
        "safety": {
            "prospective_shadow_evidence_consumed": False,
            "prospective_shadow_evidence_modified": False,
            "automatic_strategy_change": False,
            "automatic_promotion": False,
            "paper_gate_reopened": False,
            "paper_trading_allowed_by_endpoint_052": False,
            "live_trading_allowed": False,
            "broker_connection_allowed": False,
        },
        "next_requirement": (
            "independent_prospective_shadow_validation"
            if selected
            else "continue_challenger_research_without_changing_g6"
        ),
    }
