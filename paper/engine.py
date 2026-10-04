from __future__ import annotations

from dataclasses import dataclass

from config import DEFAULT_FEE_RATE, DEFAULT_LOT_SIZE


@dataclass(frozen=True)
class PaperState:
    capital: float
    position_symbol: str | None = None
    position_shares: int = 0
    entry_price: float | None = None


def propose_paper_buy(candidate_result: dict, readiness: dict, *, session_key: str) -> dict:
    selected = candidate_result.get("selected")
    if readiness.get("paper_trading_allowed") is not True:
        return {
            "endpoint": "026",
            "status": "blocked",
            "session_key": session_key,
            "reason": readiness.get("reason") or "paper_readiness_blocked",
            "order": None,
            "live_order": False,
        }
    if not selected:
        return {
            "endpoint": "026",
            "status": "no_candidate",
            "session_key": session_key,
            "order": None,
            "live_order": False,
        }
    if int(selected["shares"]) != DEFAULT_LOT_SIZE:
        raise ValueError("paper engine requires one 100-share lot")

    return {
        "endpoint": "026",
        "status": "proposed",
        "session_key": session_key,
        "order": {
            "order_key": f"{session_key}:buy:{selected['symbol']}:{selected['date']}",
            "symbol": selected["symbol"],
            "decision_date": selected["date"],
            "side": "buy",
            "shares": DEFAULT_LOT_SIZE,
            "expected_price": selected["close"],
            "fees_estimate": round(
                selected["close"] * DEFAULT_LOT_SIZE * DEFAULT_FEE_RATE, 2
            ),
            "status": "proposed",
            "approval_required": True,
            "live_order": False,
        },
        "live_order": False,
    }
