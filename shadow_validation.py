from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

from backtest.robustness_runner import run_robustness_validation
from research.shadow_validation import build_shadow_observations


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-shadow-store"
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


def main() -> int:
    robustness = run_robustness_validation(as_of=date.today())
    shadow = build_shadow_observations(robustness)
    req = urllib.request.Request(
        STORE_URL,
        data=json.dumps({
            "observations": shadow["observations"],
            "summary": {
                key: value
                for key, value in shadow.items()
                if key != "observations"
            },
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
        "development_endpoint": "032",
        "shadow": {
            key: value
            for key, value in shadow.items()
            if key != "observations"
        },
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
