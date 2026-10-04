from __future__ import annotations

import json
import os
import urllib.request

from backtest.champion_regression import run_champion_synthetic_regression
from backtest.champion_spec import CURRENT_CHAMPION_SPEC

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

def post_json(token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        STORE_URL,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

def main() -> int:
    result = run_champion_synthetic_regression()
    if result["status"] != "passed":
        raise RuntimeError("G6 synthetic regression failed")
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    run_key = f"g6-baseline-reset-{run_id}-{attempt}"
    store_result = {
        "mode": result["mode"],
        "data_source": "deterministic_sample",
        "starting_capital": 30000,
        "live_trading": False,
        "symbol": "SYNTHETIC-G6",
        "summary": {
            "champion_strategy": CURRENT_CHAMPION_SPEC["strategy_key"],
            "regression_status": result["status"],
            "checks": result["checks"],
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "source": {
            "champion_generation": CURRENT_CHAMPION_SPEC["generation"],
            "github_sha": os.environ.get("GITHUB_SHA"),
        },
        "strategies": [],
    }
    stored = post_json(
        get_oidc_token(),
        {"run_key": run_key, "scenario_key": "g6-post-promotion-regression", "result": store_result},
    )
    print(json.dumps({
        "development_endpoint": "016",
        "champion": CURRENT_CHAMPION_SPEC,
        "regression": result,
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
