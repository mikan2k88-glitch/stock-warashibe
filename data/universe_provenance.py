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
        key="jpx_data_portal_listed",
        name="JPxData Portal List of TSE-listed Issues",
        url="https://clientportal.jpx.co.jp/ClientPortalEN/s/datacatalog/a085j00000Ip93WAAR/a017",
        coverage_note="Useful for current listed-issue reference data; by itself it is not a historical point-in-time archive.",
        access="portal",
        point_in_time_capable=False,
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
    paid_source_enabled: bool = False,
) -> dict:
    checks = {
        "manifest_frozen_before_evaluation": current_manifest_frozen,
        "expanded_universe_present": current_universe_size >= 8,
        "delisted_records_loaded": delisted_records_loaded > 0,
        "historical_membership_snapshots_loaded": historical_membership_snapshots_loaded > 0,
        "paid_source_not_auto_enabled": paid_source_enabled is False,
    }
    verified = (
        checks["manifest_frozen_before_evaluation"]
        and checks["expanded_universe_present"]
        and checks["delisted_records_loaded"]
        and checks["historical_membership_snapshots_loaded"]
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
