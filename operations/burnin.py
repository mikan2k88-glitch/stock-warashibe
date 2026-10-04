from __future__ import annotations

from datetime import date


TARGET_OPERATIONAL_DAYS = 5
MAX_OBSERVATION_GAP_DAYS = 5


def _date_value(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def evaluate_operational_burnin(
    context: dict,
    *,
    as_of: date,
    run_id: str,
) -> dict:
    observations = list(context.get("observations") or [])
    runtime_history = list(context.get("runtime_history") or [])
    integrity_history = list(context.get("integrity_history") or [])

    observation_dates = sorted({
        parsed
        for row in observations
        if (parsed := _date_value(row.get("observation_date"))) is not None
        and parsed <= as_of
    })
    runtime_dates = {
        parsed
        for row in runtime_history
        if (parsed := _date_value(row.get("created_at"))) is not None
    }
    integrity_dates = {
        parsed
        for row in integrity_history
        if (parsed := _date_value(row.get("created_at"))) is not None
    }

    gaps = [
        (later - earlier).days
        for earlier, later in zip(observation_dates, observation_dates[1:])
    ]
    max_gap = max(gaps, default=0)

    recent_operational_dates = observation_dates[-TARGET_OPERATIONAL_DAYS:]
    runtime_coverage = sum(day in runtime_dates for day in recent_operational_dates)
    integrity_coverage = sum(day in integrity_dates for day in recent_operational_dates)

    checks = {
        "at_least_one_observation_day": bool(observation_dates),
        "no_large_observation_gap": max_gap <= MAX_OBSERVATION_GAP_DAYS,
        "runtime_snapshots_cover_observed_days": (
            not recent_operational_dates
            or runtime_coverage == len(recent_operational_dates)
        ),
        "integrity_audits_cover_observed_days": (
            not recent_operational_dates
            or integrity_coverage == len(recent_operational_dates)
        ),
        "no_degraded_runtime_snapshot": not any(
            row.get("status") == "degraded"
            for row in runtime_history[:20]
        ),
        "no_failed_integrity_audit": not any(
            row.get("status") == "failed"
            for row in integrity_history[:20]
        ),
    }
    hard_failures = [
        name for name, passed in checks.items()
        if passed is False and name not in {
            "runtime_snapshots_cover_observed_days",
            "integrity_audits_cover_observed_days",
        }
    ]

    observed_days = len(observation_dates)
    if hard_failures:
        status = "failed"
    elif observed_days >= TARGET_OPERATIONAL_DAYS and all(checks.values()):
        status = "passed"
    else:
        status = "collecting"

    return {
        "endpoint": "048",
        "audit_key": f"burnin-{run_id}",
        "status": status,
        "observed_business_days": observed_days,
        "target_business_days": TARGET_OPERATIONAL_DAYS,
        "checks": checks,
        "metrics": {
            "first_observation_date": (
                observation_dates[0].isoformat() if observation_dates else None
            ),
            "latest_observation_date": (
                observation_dates[-1].isoformat() if observation_dates else None
            ),
            "maximum_observation_gap_days": max_gap,
            "recent_runtime_coverage_days": runtime_coverage,
            "recent_integrity_coverage_days": integrity_coverage,
        },
        "failures": hard_failures,
        "paper_trading_allowed": False,
        "live_trading": False,
    }
