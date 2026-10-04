from __future__ import annotations


def build_promotion_request(candidate: dict, active_strategy: dict) -> dict:
    if candidate.get("status") != "validated_candidate":
        raise ValueError("candidate must be validated_candidate")
    if candidate.get("selected") is not True:
        raise ValueError("candidate must be selected")

    historical = candidate.get("historical_evaluation") or {}
    synthetic = candidate.get("synthetic_evaluation") or {}
    if historical.get("accepted") is not True:
        raise ValueError("historical gate not passed")
    if (synthetic.get("quality_guard") or {}).get("accepted") is not True:
        raise ValueError("synthetic quality gate not passed")

    if active_strategy.get("strategy_key") != candidate.get("baseline_strategy_key"):
        raise ValueError("active baseline mismatch")
    if int(active_strategy.get("generation", -1)) != int(
        candidate.get("baseline_generation", -2)
    ):
        raise ValueError("active baseline generation mismatch")
    if int(candidate.get("proposed_generation", -1)) != (
        int(active_strategy.get("generation", -1)) + 1
    ):
        raise ValueError("invalid generation transition")

    return {
        "candidate_key": candidate["candidate_key"],
        "expected_active_strategy": active_strategy["strategy_key"],
        "expected_generation": candidate["proposed_generation"],
        "live_trading": False,
        "promotion_policy": "validated_selected_candidate_only",
    }
