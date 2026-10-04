from __future__ import annotations

from datetime import date

from backtest.robustness_universe import ROBUSTNESS_UNIVERSE, UNIVERSE_POLICY
from data.jpx_delisted import JPX_DELISTED_URL, DelistedIssue
from data.universe_provenance import assess_point_in_time_readiness


def build_lifecycle_snapshot(
    delisted: list[DelistedIssue],
    *,
    snapshot_date: date,
) -> dict:
    current_rows = [
        {
            "lifecycle_key": f"current:{member.symbol}:{snapshot_date.isoformat()}",
            "symbol": member.symbol,
            "company_name": None,
            "listed_at": None,
            "delisted_at": None,
            "market_segment": None,
            "lifecycle_status": "current",
            "source_key": "warashibe_predeclared_universe",
            "source_url": "repository:backtest/robustness_universe.py",
            "snapshot_date": snapshot_date.isoformat(),
            "evidence": {
                "sector": member.sector,
                "declared_before_evaluation": True,
                "performance_used_for_selection": False,
            },
        }
        for member in ROBUSTNESS_UNIVERSE
    ]

    delisted_rows = [
        {
            "lifecycle_key": issue.lifecycle_key,
            "symbol": issue.symbol,
            "company_name": issue.company_name,
            "listed_at": None,
            "delisted_at": issue.delisted_at,
            "market_segment": issue.market_segment,
            "lifecycle_status": "delisted",
            "source_key": "jpx_delisted",
            "source_url": JPX_DELISTED_URL,
            "snapshot_date": snapshot_date.isoformat(),
            "evidence": {"reason": issue.reason},
        }
        for issue in delisted
    ]

    readiness = assess_point_in_time_readiness(
        current_manifest_frozen=UNIVERSE_POLICY["declared_before_evaluation"],
        current_universe_size=len(ROBUSTNESS_UNIVERSE),
        delisted_records_loaded=len(delisted_rows),
        historical_membership_snapshots_loaded=0,
        paid_source_enabled=False,
    )
    return {
        "endpoint": "021",
        "status": "partial_reconstruction",
        "current_snapshot_count": len(current_rows),
        "delisted_record_count": len(delisted_rows),
        "historical_membership_snapshot_count": 0,
        "point_in_time": readiness,
        "lifecycle_records": current_rows + delisted_rows,
        "paper_trading_allowed": False,
        "live_trading": False,
    }
