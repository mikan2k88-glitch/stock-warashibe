from __future__ import annotations

from collections import Counter
from math import ceil
from statistics import mean


def analyze_tail_windows(robustness_result: dict) -> dict:
    windows = []
    for symbol_row in robustness_result.get("per_symbol") or []:
        for window in symbol_row.get("windows") or []:
            windows.append({
                "symbol": symbol_row["symbol"],
                "sector": symbol_row["sector"],
                **window,
            })

    if not windows:
        raise ValueError("no robustness windows")

    windows.sort(key=lambda row: float(row["champion_return"]))
    tail_count = max(1, ceil(len(windows) * 0.10))
    tail = windows[:tail_count]
    sectors = Counter(row["sector"] for row in tail)

    return {
        "endpoint": "022",
        "status": "diagnosed",
        "window_count": len(windows),
        "tail_window_count": len(tail),
        "tail_fraction": round(len(tail) / len(windows), 6),
        "tail_mean_return": round(mean(float(row["champion_return"]) for row in tail), 6),
        "tail_mean_excess_return": round(mean(float(row["excess_return"]) for row in tail), 6),
        "tail_mean_drawdown": round(mean(float(row["champion_max_drawdown"]) for row in tail), 6),
        "tail_mean_trade_count": round(mean(int(row["champion_trade_count"]) for row in tail), 3),
        "sector_counts": dict(sectors.most_common()),
        "worst_windows": [
            {
                "symbol": row["symbol"],
                "sector": row["sector"],
                "window_index": row["window_index"],
                "champion_return": row["champion_return"],
                "benchmark_return": row["benchmark_return"],
                "excess_return": row["excess_return"],
                "max_drawdown": row["champion_max_drawdown"],
                "trade_count": row["champion_trade_count"],
            }
            for row in tail[:20]
        ],
        "automatic_strategy_change": False,
        "paper_trading_allowed": False,
    }
