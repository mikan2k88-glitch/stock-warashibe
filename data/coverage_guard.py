from __future__ import annotations

from datetime import date


MIN_BARS = 750
MIN_CALENDAR_DAYS = 365 * 3
MAX_STALE_DAYS = 10
MAX_CALENDAR_GAP_DAYS = 20


def assess_coverage(batch, *, as_of: date) -> dict:
    bars = list(batch.bars)
    if not bars:
        return {"accepted": False, "reasons": ["no_bars"]}

    dates = [date.fromisoformat(bar.date) for bar in bars]
    first_date = dates[0]
    last_date = dates[-1]
    span_days = (last_date - first_date).days
    stale_days = (as_of - last_date).days
    max_gap = max(
        ((right - left).days for left, right in zip(dates, dates[1:])),
        default=0,
    )

    checks = {
        "minimum_bars": len(bars) >= MIN_BARS,
        "minimum_calendar_span": span_days >= MIN_CALENDAR_DAYS,
        "not_stale": 0 <= stale_days <= MAX_STALE_DAYS,
        "calendar_gap_guard": max_gap <= MAX_CALENDAR_GAP_DAYS,
        "chronological": dates == sorted(dates),
        "unique_dates": len(dates) == len(set(dates)),
    }
    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "accepted": all(checks.values()),
        "checks": checks,
        "reasons": reasons,
        "bar_count": len(bars),
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "calendar_span_days": span_days,
        "stale_days": stale_days,
        "max_calendar_gap_days": max_gap,
        "source_sha256": batch.source_sha256,
    }
