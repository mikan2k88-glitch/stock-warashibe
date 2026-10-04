from __future__ import annotations

from config import DEFAULT_LOT_SIZE, STARTING_CAPITAL


def build_human_gate_package(
    live_readiness: dict,
    *,
    package_key: str,
) -> dict:
    ready = live_readiness.get("research_ready_for_human_gate") is True
    return {
        "endpoint": "042",
        "package_key": package_key,
        "strategy_key": "mean_reversion_cost_floor:g6",
        "status": "ready_for_review" if ready else "blocked",
        "limits": {
            "maximum_initial_capital_yen": STARTING_CAPITAL,
            "maximum_open_positions": 1,
            "shares_per_order": DEFAULT_LOT_SIZE,
            "automatic_live_order": False,
            "automatic_broker_connection": False,
        },
        "safeguards": {
            "approval_code_required": "8888",
            "explicit_human_approval_required": True,
            "duplicate_order_guard": True,
            "price_deviation_guard": True,
            "kill_switch_required": True,
            "audit_log_required": True,
            "live_secret_manual_configuration_required": True,
        },
        "evidence": {
            "live_readiness_status": live_readiness.get("status"),
            "checks": live_readiness.get("checks") or {},
        },
        "explicit_human_approval": False,
        "approved_at": None,
        "live_trading_allowed": False,
    }
