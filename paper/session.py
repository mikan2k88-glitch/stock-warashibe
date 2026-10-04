from __future__ import annotations

from config import STARTING_CAPITAL


def build_paper_session_start(
    reopen_gate: dict,
    *,
    existing_sessions: list[dict],
    run_id: str,
    strategy_key: str,
) -> dict:
    active = next(
        (
            row
            for row in existing_sessions
            if row.get("status") in {"ready", "active"}
        ),
        None,
    )

    if reopen_gate.get("paper_trading_allowed") is not True:
        return {
            "endpoint": "038",
            "status": "blocked",
            "reason": reopen_gate.get("decision") or "paper_gate_closed",
            "session": None,
            "paper_trading_allowed": False,
            "live_trading": False,
        }

    if active:
        return {
            "endpoint": "038",
            "status": "idempotent_existing_session",
            "reason": None,
            "session": active,
            "paper_trading_allowed": True,
            "live_trading": False,
        }

    session_key = f"paper-live-sim-{run_id}"
    session = {
        "session_key": session_key,
        "strategy_key": strategy_key,
        "starting_capital": STARTING_CAPITAL,
        "current_capital": STARTING_CAPITAL,
        "status": "active",
        "readiness": {
            "source_endpoint": "037",
            "paper_gate_reopened": True,
            "human_approval_for_live_required": True,
        },
        "ledger": {
            "closed_trades": 0,
            "open_position": None,
            "capital_history": [STARTING_CAPITAL],
        },
        "live_trading": False,
    }
    return {
        "endpoint": "038",
        "status": "started",
        "reason": None,
        "session": session,
        "paper_trading_allowed": True,
        "live_trading": False,
    }
