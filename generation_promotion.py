from __future__ import annotations

import json
import os
import urllib.request

from backtest.champion_spec import CURRENT_CHAMPION_SPEC


PROMOTION_URL = (
    "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/"
    "stock-warashibe-generation-promotion"
)
OIDC_AUDIENCE = "stock-warashibe-supabase"
CANDIDATE_KEY = "mean_reversion_cost_floor:g6-candidate-x4"


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


def promote(token: str) -> dict:
    req = urllib.request.Request(
        PROMOTION_URL,
        data=json.dumps({"candidate_key": CANDIDATE_KEY}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main() -> int:
    if int(CURRENT_CHAMPION_SPEC["generation"]) >= 6:
        print(json.dumps({
            "development_endpoint": "015",
            "status": "skipped",
            "reason": "generation_6_already_promoted",
            "active_champion": CURRENT_CHAMPION_SPEC["strategy_key"],
            "live_trading": False,
        }, ensure_ascii=False, indent=2))
        return 0

    token = get_oidc_token()
    result = promote(token)
    print(
        json.dumps(
            {
                "development_endpoint": "015",
                "candidate_key": CANDIDATE_KEY,
                "live_trading": False,
                "promotion": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
