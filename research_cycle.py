from __future__ import annotations

import json
import os
import urllib.request

from backtest.scenario_runner import run_all_scenarios


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-store"
PLANNER_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-planner"
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


def post_json(token: str, url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main() -> int:
    token = get_oidc_token()
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")

    stored = []
    for result in run_all_scenarios():
        scenario = result["scenario"]
        run_key = f"synthetic-{scenario}-{run_id}-{attempt}"
        stored.append(
            post_json(
                token,
                STORE_URL,
                {
                    "run_key": run_key,
                    "scenario_key": f"synthetic-{scenario}",
                    "result": result,
                },
            )
        )

    hypothesis = post_json(
        token,
        PLANNER_URL,
        {
            "action": "plan_next_experiment",
            "source_run_id": run_id,
            "attempt": attempt,
        },
    )

    print(
        json.dumps(
            {"stored": stored, "next_hypothesis": hypothesis},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
