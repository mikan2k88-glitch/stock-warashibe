from __future__ import annotations

MIN_ELIGIBLE_SYMBOLS = 3
MIN_EVALUATED_WINDOWS = 9


def assess_historical_gate(validation: dict) -> dict:
    """Assess whether walk-forward evidence is usable without opening Paper Gate.

    Endpoint #051 deliberately separates historical research evidence from the
    prospective Shadow/Paper transition. Historical evidence may be marked
    usable for research while still being blocked for promotion when the
    universe is not point-in-time and survivor bias has not been eliminated.
    """
    summary = validation.get("summary", {})
    walk_forward = validation.get("walk_forward", {})
    source = validation.get("source", {})
    strategy = summary.get("champion_strategy")
    frozen_strategy = walk_forward.get("champion_frozen")
    hashes = source.get("per_symbol_sha256", {})

    eligible_symbol_count = int(summary.get("eligible_symbol_count", 0) or 0)
    evaluated_window_count = int(summary.get("evaluated_window_count", 0) or 0)
    eligible_symbols = list(walk_forward.get("eligible_symbols", []))

    evidence_checks = {
        "historical_mode": (
            validation.get("mode") == "historical_walk_forward_validation"
        ),
        "live_trading_disabled": validation.get("live_trading") is False,
        "parameters_frozen": walk_forward.get("parameter_tuning") is False,
        "champion_consistent": bool(strategy) and strategy == frozen_strategy,
        "minimum_eligible_symbols": (
            eligible_symbol_count >= MIN_ELIGIBLE_SYMBOLS
        ),
        "minimum_evaluated_windows": (
            evaluated_window_count >= MIN_EVALUATED_WINDOWS
        ),
        "source_hashes_complete": (
            bool(eligible_symbols)
            and all(
                isinstance(hashes.get(symbol), str)
                and len(hashes[symbol]) == 64
                for symbol in eligible_symbols
            )
        ),
    }
    historical_research_usable = all(evidence_checks.values())

    promotion_checks = {
        "point_in_time_universe": (
            walk_forward.get("point_in_time_universe") is True
        ),
        "survivor_bias_eliminated": (
            walk_forward.get("survivor_bias_eliminated") is True
        ),
    }
    promotion_ready = (
        historical_research_usable
        and all(promotion_checks.values())
    )

    if promotion_ready:
        status = "passed"
    elif historical_research_usable:
        status = "research_usable_not_promotion_ready"
    else:
        status = "blocked"

    return {
        "endpoint": "051",
        "mode": "historical_walk_forward_gate",
        "status": status,
        "strategy": strategy,
        "historical_research_usable": historical_research_usable,
        "historical_gate_passed": promotion_ready,
        "evidence_checks": evidence_checks,
        "promotion_checks": promotion_checks,
        "descriptive_metrics": {
            "positive_window_ratio": summary.get("positive_window_ratio"),
            "outperformed_benchmark_window_ratio": summary.get(
                "outperformed_benchmark_window_ratio"
            ),
            "champion_mean_return": summary.get("champion_mean_return"),
            "benchmark_mean_return": summary.get("benchmark_mean_return"),
        },
        "safety": {
            "performance_metrics_are_descriptive_not_gate_thresholds": True,
            "automatic_strategy_change": False,
            "paper_gate_reopened": False,
            "paper_trading_allowed_by_endpoint_051": False,
            "live_trading_allowed": False,
            "broker_connection_allowed": False,
        },
        "next_requirement": (
            "prospective_shadow_gate_037"
            if promotion_ready
            else (
                "point_in_time_universe_and_survivor_bias_control"
                if historical_research_usable
                else "repair_historical_evidence_quality"
            )
        ),
    }
