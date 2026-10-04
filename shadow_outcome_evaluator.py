from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

from data.yahoo_chart_provider import YahooChartDailyBarProvider
from research.shadow_outcome import evaluate_shadow_observation


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
    pending_response = post_json(token, {"action": "pending"})
    pending = pending_response.get("pending") or []

    provider = YahooChartDailyBarProvider(range_value="2y")
    batches = {}
    outcomes = []
    deferred = []

    for observation in pending:
        symbol = str(observation["symbol"])
        if symbol not in batches:
            batches[symbol] = provider.load_batch(symbol, as_of=date.today())

        result = evaluate_shadow_observation(
            observation,
            batches[symbol],
        )
        if not result["ready"]:
            deferred.append({
                "observation_key": observation["observation_key"],
                "symbol": symbol,
                **result,
            })
            continue

        outcomes.append({
            "observation_key": observation["observation_key"],
            "outcome": result,
        })

    stored = post_json(
        token,
        {
            "action": "update_outcomes",
            "outcomes": outcomes,
        },
    )

    print(json.dumps({
        "development_endpoint": "033",
        "mode": "shadow_outcome_evaluator",
        "pending_count": len(pending),
        "matured_count": len(outcomes),
        "deferred_count": len(deferred),
        "deferred_reasons": {
            reason: sum(1 for row in deferred if row["reason"] == reason)
            for reason in sorted({row["reason"] for row in deferred})
        },
        "stored": stored,
        "paper_order_created": False,
        "live_trading": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
