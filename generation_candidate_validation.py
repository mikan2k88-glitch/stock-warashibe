from __future__ import annotations

import json
import os
import urllib.request

from backtest.generation_candidate_validator import (
    run_generation_candidate_validation,
)
from backtest.strategy_diagnosis import run_strategy_diagnosis


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-generation-research"
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
    diagnosis = run_strategy_diagnosis()
    validation = run_generation_candidate_validation(diagnosis)
    token = get_oidc_token()
    stored = post_json(
        token,
        {
            "bridge_candidates": validation["bridge_candidates"],
            "historical_evaluations": validation["historical_evaluations"],
            "generation_validation": validation,
        },
    )
    print(
        json.dumps(
            {
                "development_endpoints": {
                    "012": "diagnosis_to_hypothesis_bridge",
                    "013": "historical_hypothesis_evaluation",
                    "014": "generation_6_candidate_validation",
                },
                "validation": validation,
                "stored": stored,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
