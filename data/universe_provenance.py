from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceSource:
    key: str
    name: str
    url: str
    coverage_note: str
    access: str
    point_in_time_capable: bool


POINT_IN_TIME_SOURCE_PLAN = (
    ProvenanceSource(
        key="jpx_delisted",
        name="JPX List of Delisted Companies",
        url="https://www.jpx.co.jp/english/listing/stocks/delisted/index.html",
        coverage_note="Official delisting history; public page states data older than 11 years is not available there.",
        access="public",
        point_in_time_capable=True,
    ),
    ProvenanceSource(
        key="jpx_public_listed_issues",
        name="JPX List of TSE-listed Issues",
        url="https://www.jpx.co.jp/english/markets/statistics-equities/misc/01.html",
        coverage_note="Official month-end TSE-listed issues snapshot published as Excel.",
        access="public",
        point_in_time_capable=True,
    ),
    ProvenanceSource(
        key="jpx_public_new_listings",
        name="JPX New Listings Archives",
        url="https://www.jpx.co.jp/english/listing/stocks/new/",
        coverage_note="Official public listing-event archives used with current membership and delistings to reconstruct historical membership.",
        access="public",
        point_in_time_capable=True,
    ),
    ProvenanceSource(
        key="jpx_index_data_service",
        name="JPX Index Data Service / constituent master",
        url="https://www.jpx.co.jp/english/markets/paid-info-equities/reference/01.html",
        coverage_note="Official constituent-history capable service, but access may be paid and must not be enabled automatically.",
        access="paid_or_contractual",
        point_in_time_capable=True,
    ),
)


def assess_point_in_time_readiness(
    *,
    current_manifest_frozen: bool,
    current_universe_size: int,
    delisted_records_loaded: int = 0,
    historical_membership_snapshots_loaded: int = 0,
    historical_membership_coverage_verified: bool = False,
    source_completeness_verified: bool = False,
    paid_source_enabled: bool = False,
) -> dict:
    checks = {
        "manifest_frozen_before_evaluation": current_manifest_frozen,
        "expanded_universe_present": current_universe_size >= 8,
        "delisted_records_loaded": delisted_records_loaded > 0,
        "historical_membership_snapshots_loaded": historical_membership_snapshots_loaded > 0,
        "historical_membership_coverage_verified": historical_membership_coverage_verified,
        "source_completeness_verified": source_completeness_verified,
        "paid_source_not_auto_enabled": paid_source_enabled is False,
    }
    verified = (
        checks["manifest_frozen_before_evaluation"]
        and checks["expanded_universe_present"]
        and checks["delisted_records_loaded"]
        and checks["historical_membership_snapshots_loaded"]
        and checks["historical_membership_coverage_verified"]
        and checks["source_completeness_verified"]
    )
    return {
        "verified": verified,
        "checks": checks,
        "delisted_records_loaded": delisted_records_loaded,
        "historical_membership_snapshots_loaded": historical_membership_snapshots_loaded,
        "sources": [source.__dict__ for source in POINT_IN_TIME_SOURCE_PLAN],
        "decision": (
            "point_in_time_ready"
            if verified
            else "point_in_time_data_required"
        ),
        "next_action": (
            "Use public JPX delisting history plus a defensible historical membership source. "
            "Do not enable paid JPX data services without explicit Human Gate approval."
        ),
    }
