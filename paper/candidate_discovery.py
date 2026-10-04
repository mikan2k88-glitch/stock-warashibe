from __future__ import annotations

from config import DEFAULT_LOT_SIZE, STARTING_CAPITAL


def discover_daily_candidate(
    robustness_result: dict,
    *,
    capital: float = STARTING_CAPITAL,
) -> dict:
    candidates = []
    for row in robustness_result.get("per_symbol") or []:
        snap = row.get("latest_snapshot") or {}
        if snap.get("action") != "buy":
            continue
        close = float(snap.get("close") or 0.0)
        lot_cost = close * DEFAULT_LOT_SIZE
        if close <= 0 or lot_cost > capital:
            continue
        candidates.append({
            "symbol": row["symbol"],
            "sector": row["sector"],
            "date": snap.get("date"),
            "close": close,
            "lot_cost": round(lot_cost, 2),
            "shares": DEFAULT_LOT_SIZE,
            "score": float(snap.get("score") or 0.0),
            "reason": snap.get("reason"),
        })

    candidates.sort(key=lambda row: (-row["score"], row["symbol"]))
    selected = candidates[0] if candidates else None
    return {
        "endpoint": "027",
        "status": "candidate_found" if selected else "no_candidate",
        "capital": capital,
        "single_stock_only": True,
        "candidate_count": len(candidates),
        "selected": selected,
        "top_candidates": candidates[:5],
        "live_trading": False,
    }
