from __future__ import annotations

import json
import os
import urllib.request

from backtest.robustness_runner import run_robustness_validation

STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-store"
OIDC_AUDIENCE = "stock-warashibe-supabase"

def get_oidc_token() -> str:
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    separator = "&" if "?" in request_url else "?"
    url = f"{request_url}{separator}audience={OIDC_AUDIENCE}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {request_token}"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)["value"]

def main() -> int:
    result = run_robustness_validation()
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    run_key = f"g6-robustness-{run_id}-{attempt}"
    req = urllib.request.Request(
        STORE_URL,
        data=json.dumps({
            "run_key": run_key,
            "scenario_key": "g6-robustness-expanded-universe",
            "result": result,
        }).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {get_oidc_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        stored = json.load(response)
    print(json.dumps({
        "development_endpoints": {
            "017": "robustness_universe_expansion",
            "018": "historical_coverage_and_bias_hardening",
            "019": "research_acceptance_gate",
        },
        "result": result,
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
