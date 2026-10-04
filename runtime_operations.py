from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

from operations.alert_engine import build_runtime_alerts
from operations.burnin import evaluate_operational_burnin
from operations.evidence_integrity import audit_evidence_integrity
from operations.recovery_controller import build_recovery_plan
from operations.status_monitor import build_runtime_status
from operations.transition_controller import run_transition_controller


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-operations-store"
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


def post_json(token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        STORE_URL,
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
    context = post_json(token, {"action": "context"})
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    today = date.today()

    integrity = audit_evidence_integrity(
        context.get("observations") or [],
        as_of=today,
        run_id=run_id,
    )
    runtime_status = build_runtime_status(
        context,
        as_of=today,
        run_id=run_id,
    )
    alerts = build_runtime_alerts(
        context,
        runtime_status,
        integrity,
        as_of=today,
        run_id=run_id,
    )
    burnin = evaluate_operational_burnin(
        context,
        as_of=today,
        run_id=run_id,
    )
    recovery = build_recovery_plan(
        alerts,
        burnin,
        runtime_status,
        run_id=run_id,
    )
    transition = run_transition_controller(
        context,
        integrity,
        alerts,
        run_id=run_id,
    )

    if any(
        row.get("status") == "open" and row.get("severity") == "critical"
        for row in alerts
    ):
        runtime_status["status"] = "degraded"

    stored = post_json(
        token,
        {
            "runtime_status": runtime_status,
            "alerts": alerts,
            "integrity_audit": integrity,
            "transition": transition,
            "burnin": burnin,
            "recovery": recovery,
            "session": transition.get("session"),
        },
    )

    print(json.dumps({
        "development_endpoints": {
            "044": runtime_status,
            "045": {
                "endpoint": "045",
                "open_alerts": [
                    row for row in alerts if row.get("status") == "open"
                ],
                "open_alert_count": sum(
                    row.get("status") == "open" for row in alerts
                ),
            },
            "046": integrity,
            "047": transition,
            "048": burnin,
            "049": recovery,
        },
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
