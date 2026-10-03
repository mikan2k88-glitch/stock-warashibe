from __future__ import annotations


def evaluate_capital_path(values: list[float]) -> dict:
    if not values:
        raise ValueError("capital path must not be empty")
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    total_return = values[-1] / values[0] - 1.0 if values[0] else 0.0
    return {
        "start_capital": round(values[0], 2),
        "final_capital": round(values[-1], 2),
        "total_return": round(total_return, 6),
        "max_drawdown": round(max_dd, 6),
    }
