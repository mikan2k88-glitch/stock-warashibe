from __future__ import annotations

from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from config import DEFAULT_LOT_SIZE, STARTING_CAPITAL


def build_shadow_observations(robustness_result: dict) -> dict:
    if robustness_result.get("live_trading") is not False:
        raise ValueError("shadow validation requires live trading disabled")
    if robustness_result.get("summary", {}).get("champion_strategy") != CURRENT_CHAMPION_SPEC["strategy_key"]:
        raise ValueError("shadow validation requires the active G6 champion")

    observations = []
    for row in robustness_result.get("per_symbol") or []:
        snap = row.get("latest_snapshot") or {}
        close = float(snap.get("close") or 0.0)
        if close <= 0:
            continue
        lot_cost = close * DEFAULT_LOT_SIZE
        signal = str(snap.get("action") or "skip")
        if signal not in {"buy", "skip"}:
            signal = "skip"

        observations.append({
            "observation_key": (
                f"g6-shadow:{row['symbol']}:{snap.get('date')}"
            ),
            "observation_date": snap.get("date"),
            "strategy_key": CURRENT_CHAMPION_SPEC["strategy_key"],
            "symbol": row["symbol"],
            "sector": row.get("sector"),
            "signal": signal,
            "score": float(snap.get("score") or 0.0),
            "reference_close": close,
            "lot_cost": round(lot_cost, 2),
            "shares": DEFAULT_LOT_SIZE,
            "reason": snap.get("reason"),
            "source_sha256": row.get("source_sha256"),
            "affordable": lot_cost <= STARTING_CAPITAL,
            "live_trading": False,
        })

    observations.sort(key=lambda row: row["symbol"])
    return {
        "endpoint": "032",
        "mode": "prospective_shadow_validation",
        "strategy_key": CURRENT_CHAMPION_SPEC["strategy_key"],
        "observation_count": len(observations),
        "buy_signal_count": sum(row["signal"] == "buy" for row in observations),
        "affordable_buy_signal_count": sum(
            row["signal"] == "buy" and row["affordable"]
            for row in observations
        ),
        "prospective_only": True,
        "parameter_tuning": False,
        "paper_order_created": False,
        "live_trading": False,
        "observations": observations,
        "acceptance_protocol": {
            "minimum_future_observation_days": 30,
            "minimum_closed_shadow_signals": 20,
            "no_same_sample_parameter_tuning": True,
            "paper_trading_gate_remains_separate": True,
            "live_trading_gate_remains_separate": True,
        },
    }
