from __future__ import annotations


APPROVAL_CODE = "8888"


def build_approval_request(
    candidate_result: dict,
    paper_proposal: dict,
    *,
    request_key: str,
    session_key: str,
) -> dict:
    selected = candidate_result.get("selected")
    if paper_proposal.get("status") != "proposed" or not selected:
        return {
            "endpoint": "028",
            "request_key": request_key,
            "session_key": session_key,
            "symbol": selected.get("symbol") if selected else None,
            "status": "blocked",
            "approval_code_hint": APPROVAL_CODE,
            "payload": {
                "reason": paper_proposal.get("reason") or paper_proposal.get("status"),
                "paper_only": True,
                "live_order": False,
            },
        }

    return {
        "endpoint": "028",
        "request_key": request_key,
        "session_key": session_key,
        "symbol": selected["symbol"],
        "status": "pending",
        "approval_code_hint": APPROVAL_CODE,
        "payload": {
            "message": (
                f"Paper candidate {selected['symbol']} / "
                f"{selected['shares']} shares / reference {selected['close']:.2f}"
            ),
            "reason": selected["reason"],
            "lot_cost": selected["lot_cost"],
            "paper_only": True,
            "live_order": False,
            "requires_human_confirmation": True,
        },
    }


def approval_matches(code: str) -> bool:
    return code == APPROVAL_CODE
