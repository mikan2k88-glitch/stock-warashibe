from __future__ import annotations

from calendar import monthrange
from datetime import date

from data.jpx_delisted import DelistedIssue
from data.jpx_listed import ListedIssue
from data.jpx_new_listings import NewListingIssue
from data.universe_provenance import assess_point_in_time_readiness


RECONSTRUCTION_START = date(2022, 1, 1)


def _month_ends(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, monthrange(start.year, start.month)[1])
    result = []
    while cursor <= end:
        result.append(cursor)
        if cursor.month == 12:
            year, month = cursor.year + 1, 1
        else:
            year, month = cursor.year, cursor.month + 1
        cursor = date(year, month, monthrange(year, month)[1])
    return result


def reconstruct_historical_membership(
    current: list[ListedIssue],
    new_listings: list[NewListingIssue],
    delisted: list[DelistedIssue],
    *,
    snapshot_date: date,
    source_completeness_verified: bool,
) -> dict:
    current_by_code = {issue.code: issue for issue in current}
    new_by_code: dict[str, NewListingIssue] = {}
    for issue in new_listings:
        previous = new_by_code.get(issue.code)
        if previous is None or issue.listed_at < previous.listed_at:
            new_by_code[issue.code] = issue

    delisted_by_code: dict[str, DelistedIssue] = {}
    for issue in delisted:
        if date.fromisoformat(issue.delisted_at) < RECONSTRUCTION_START:
            continue
        if date.fromisoformat(issue.delisted_at) > snapshot_date:
            continue
        previous = delisted_by_code.get(issue.code)
        if previous is None or issue.delisted_at > previous.delisted_at:
            delisted_by_code[issue.code] = issue

    all_codes = set(current_by_code) | set(new_by_code) | set(delisted_by_code)
    unresolved_new = []
    lifecycle_records = []

    for code in sorted(all_codes):
        current_issue = current_by_code.get(code)
        new_issue = new_by_code.get(code)
        delisted_issue = delisted_by_code.get(code)

        if new_issue and not current_issue and not delisted_issue:
            unresolved_new.append(code)

        if current_issue:
            status = "current"
            company_name = current_issue.company_name
            market_segment = current_issue.market_segment
        elif delisted_issue:
            status = "delisted"
            company_name = delisted_issue.company_name
            market_segment = delisted_issue.market_segment
        else:
            status = "unknown"
            company_name = new_issue.company_name if new_issue else None
            market_segment = new_issue.market_segment if new_issue else None

        listed_at = new_issue.listed_at if new_issue else None
        delisted_at = delisted_issue.delisted_at if delisted_issue else None
        lifecycle_records.append({
            "lifecycle_key": (
                f"pit:{code}:{RECONSTRUCTION_START.isoformat()}:{snapshot_date.isoformat()}"
            ),
            "symbol": f"{code}.T",
            "company_name": company_name,
            "listed_at": listed_at,
            "delisted_at": delisted_at,
            "market_segment": market_segment,
            "lifecycle_status": status,
            "source_key": "jpx_public_membership_reconstruction",
            "source_url": "https://www.jpx.co.jp/english/",
            "snapshot_date": snapshot_date.isoformat(),
            "evidence": {
                "reconstruction_start": RECONSTRUCTION_START.isoformat(),
                "present_at_start_if_listed_at_null": listed_at is None,
                "current_snapshot_member": current_issue is not None,
                "new_listing_event": new_issue.to_dict() if new_issue else None,
                "delisting_event": delisted_issue.to_dict() if delisted_issue else None,
            },
        })

    def active_on(code: str, target: date) -> bool:
        new_issue = new_by_code.get(code)
        delisted_issue = delisted_by_code.get(code)
        if new_issue and date.fromisoformat(new_issue.listed_at) > target:
            return False
        if delisted_issue and date.fromisoformat(delisted_issue.delisted_at) <= target:
            return False
        return True

    monthly = []
    for month_end in _month_ends(RECONSTRUCTION_START, snapshot_date):
        members = sorted(code for code in all_codes if active_on(code, month_end))
        monthly.append({
            "snapshot_date": month_end.isoformat(),
            "member_count": len(members),
            "sample_codes": members[:10],
        })

    coverage_verified = (
        source_completeness_verified
        and len(current) >= 1000
        and len(monthly) >= 48
        and not unresolved_new
        and snapshot_date >= date(2026, 8, 31)
    )
    readiness = assess_point_in_time_readiness(
        current_manifest_frozen=True,
        current_universe_size=len(current),
        delisted_records_loaded=len(delisted_by_code),
        historical_membership_snapshots_loaded=len(monthly),
        historical_membership_coverage_verified=coverage_verified,
        source_completeness_verified=source_completeness_verified,
        paid_source_enabled=False,
    )

    return {
        "endpoint": "031",
        "status": "verified_public_reconstruction" if readiness["verified"] else "partial_reconstruction",
        "reconstruction_start": RECONSTRUCTION_START.isoformat(),
        "snapshot_date": snapshot_date.isoformat(),
        "current_snapshot_count": len(current),
        "new_listing_event_count": len(new_listings),
        "delisted_record_count": len(delisted_by_code),
        "historical_membership_snapshot_count": len(monthly),
        "unresolved_new_listing_codes": unresolved_new,
        "source_completeness_verified": source_completeness_verified,
        "point_in_time": readiness,
        "monthly_membership": monthly,
        "lifecycle_records": lifecycle_records,
        "paper_trading_allowed": False,
        "live_trading": False,
    }
