from __future__ import annotations

from collections import Counter
from datetime import date


MIN_OBSERVATION_DAYS = 30
MIN_EVALUATED_BUYS = 20


def audit_evidence_integrity(
    observations: list[dict],
    *,
    as_of: date,
    run_id: str,
) -> dict:
    keys = [str(row.get("observation_key") or "") for row in observations]
    symbol_dates = [
        (str(row.get("symbol") or ""), str(row.get("observation_date") or ""))
        for row in observations
    ]
    evaluated = [row for row in observations if row.get("status") == "evaluated"]
    evaluated_buys = [
        row for row in evaluated
        if row.get("signal") == "buy"
        and (row.get("outcome") or {}).get("counterfactual_only") is not True
    ]

    future_dates = []
    missing_hashes = []
    invalid_outcomes = []
    live_evidence = []

    for row in observations:
        key = str(row.get("observation_key") or "")
        try:
            obs_date = date.fromisoformat(str(row.get("observation_date") or "")[:10])
            if obs_date > as_of:
                future_dates.append(key)
        except ValueError:
            future_dates.append(key)

        source_hash = str(row.get("source_sha256") or "")
        if len(source_hash) != 64:
            missing_hashes.append(key)

        if row.get("live_trading") is True:
            live_evidence.append(key)

        if row.get("status") == "evaluated":
            outcome = row.get("outcome") or {}
            valid = (
                outcome.get("ready") is True
                and outcome.get("horizon_trading_days") == 5
                and bool(outcome.get("entry_date"))
                and bool(outcome.get("exit_date"))
                and outcome.get("live_trading") is False
                and outcome.get("paper_order_created") is False
            )
            if not valid:
                invalid_outcomes.append(key)

    day_count = len({
        str(row.get("observation_date") or "")
        for row in observations
        if row.get("observation_date")
    })

    checks = {
        "observation_keys_unique": len(keys) == len(set(keys)),
        "symbol_date_pairs_unique": len(symbol_dates) == len(set(symbol_dates)),
        "no_future_observations": not future_dates,
        "all_source_hashes_present": not missing_hashes,
        "evaluated_outcomes_well_formed": not invalid_outcomes,
        "no_live_trading_evidence": not live_evidence,
    }
    failures = [name for name, passed in checks.items() if not passed]

    symbol_counts = Counter(str(row.get("symbol") or "") for row in observations)
    sector_counts = Counter(str(row.get("sector") or "") for row in observations)
    max_symbol_share = (
        max(symbol_counts.values()) / len(observations)
        if observations else 0.0
    )
    max_sector_share = (
        max(sector_counts.values()) / len(observations)
        if observations else 0.0
    )

    sample_ready = (
        day_count >= MIN_OBSERVATION_DAYS
        and len(evaluated_buys) >= MIN_EVALUATED_BUYS
    )

    if failures:
        status = "failed"
    elif sample_ready:
        status = "passed"
    else:
        status = "collecting"

    return {
        "endpoint": "046",
        "audit_key": f"evidence-integrity-{run_id}",
        "status": status,
        "observation_count": len(observations),
        "evaluated_count": len(evaluated),
        "checks": checks,
        "metrics": {
            "observation_days": day_count,
            "evaluated_buy_signals": len(evaluated_buys),
            "maximum_symbol_share": round(max_symbol_share, 6),
            "maximum_sector_share": round(max_sector_share, 6),
            "future_observation_count": len(future_dates),
            "missing_source_hash_count": len(missing_hashes),
            "invalid_outcome_count": len(invalid_outcomes),
        },
        "failures": failures,
        "sample_ready": sample_ready,
        "paper_trading_allowed": False,
        "live_trading": False,
    }
