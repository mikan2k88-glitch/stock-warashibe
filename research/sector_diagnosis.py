from __future__ import annotations


def diagnose_sectors(robustness_result: dict) -> dict:
    rows = robustness_result.get("robustness", {}).get("sector_metrics") or []
    diagnosed = []
    for row in rows:
        mean_return = float(row.get("mean_champion_return") or 0.0)
        excess = float(row.get("mean_excess_return") or 0.0)
        if mean_return < -0.05:
            classification = "weak"
        elif mean_return < 0 or excess < 0:
            classification = "mixed"
        else:
            classification = "strong"
        diagnosed.append({
            **row,
            "classification": classification,
        })

    diagnosed.sort(key=lambda row: float(row.get("mean_champion_return") or 0.0))
    return {
        "endpoint": "023",
        "status": "diagnosed",
        "weak_sector_count": sum(row["classification"] == "weak" for row in diagnosed),
        "mixed_sector_count": sum(row["classification"] == "mixed" for row in diagnosed),
        "strong_sector_count": sum(row["classification"] == "strong" for row in diagnosed),
        "sectors": diagnosed,
        "automatic_strategy_change": False,
        "paper_trading_allowed": False,
    }
