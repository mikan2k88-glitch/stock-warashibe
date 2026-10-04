from __future__ import annotations

import json
import os
import urllib.request

from paper.reopen_gate import assess_paper_reopen_gate
from research.prospective_acceptance import assess_prospective_acceptance
from research.shadow_failure_diagnosis import diagnose_shadow_failure
from research.shadow_readiness import aggregate_shadow_readiness


SHADOW_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-shadow-store"
READINESS_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-shadow-readiness-store"
OIDC_AUDIENCE = "stock-warashibe-supabase"


def get_oidc_token() -> str:
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    separator = "&" if "?" in request_url else "?"
    url = f"{request_url}{separator}audience={OIDC_AUDIENCE}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {request_token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)["value"]


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def main() -> int:
    token = get_oidc_token()
    shadow_data = post_json(SHADOW_URL, token, {"action": "readiness_data"})
    context = post_json(READINESS_URL, token, {"action": "context"})

    observations = shadow_data.get("observations") or []
    readiness = aggregate_shadow_readiness(observations)
    acceptance = assess_prospective_acceptance(readiness)
    failure = diagnose_shadow_failure(readiness, acceptance)

    latest_session = context.get("latest_paper_session") or {}
    session_readiness = latest_session.get("readiness") or {}
    session_checks = session_readiness.get("checks") or {}
    active_strategy = context.get("active_strategy") or {}

    reopen = assess_paper_reopen_gate(
        readiness,
        acceptance,
        point_in_time_verified=bool(
            session_checks.get("point_in_time_verified")
        ),
        data_fresh=bool(session_checks.get("data_fresh")),
        active_strategy_key=str(active_strategy.get("strategy_key") or ""),
    )

    stored = post_json(
        READINESS_URL,
        token,
        {
            "readiness": readiness,
            "acceptance": acceptance,
            "failure_diagnosis": failure,
            "reopen_gate": reopen,
        },
    )

    print(json.dumps({
        "development_endpoints": {
            "034": readiness,
            "035": acceptance,
            "036": failure,
            "037": reopen,
        },
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
