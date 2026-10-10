from __future__ import annotations

import json
import os
import urllib.request

from backtest.adaptive_exit_optimizer import run_adaptive_exit_optimization
from backtest.historical_gate import assess_historical_gate
from backtest.walk_forward_runner import run_walk_forward_validation


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-store"
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
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main() -> int:
    result = run_walk_forward_validation()
    result["historical_gate"] = assess_historical_gate(result)
    result["adaptive_exit_optimization"] = run_adaptive_exit_optimization()

    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    run_key = f"historical-walk-forward-{run_id}-{attempt}"

    token = get_oidc_token()
    stored = post_json(
        token,
        {
            "run_key": run_key,
            "scenario_key": "historical-walk-forward-oos",
            "result": result,
        },
    )
    print(
        json.dumps(
            {"run_key": run_key, "result": result, "stored": stored},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
