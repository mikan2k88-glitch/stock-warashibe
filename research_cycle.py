from __future__ import annotations

import json
import os
import urllib.request

from backtest.hypothesis_runner import run_hypothesis_ab_test
from backtest.scenario_runner import run_all_scenarios


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-store"
EVALUATOR_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-hypothesis-evaluator"
REGISTRY_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-strategy-registry"
QUEUE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-queue"
OIDC_AUDIENCE = "stock-warashibe-supabase"
MAX_QUEUE_ITEMS_PER_CYCLE = 2


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

    registry_before = post_json(token, REGISTRY_URL, {"action": "sync_validated"})
    seeded = post_json(token, QUEUE_URL, {"action": "seed"})

    processed = []
    for _ in range(MAX_QUEUE_ITEMS_PER_CYCLE):
        claimed = post_json(token, QUEUE_URL, {"action": "claim_next"})
        item = claimed.get("item")
        if not item:
            processed.append({"claim": claimed, "processed": False})
            break

        active = claimed.get("active_strategy")
        evaluation = run_hypothesis_ab_test(
            item["proposed_change"],
            baseline_spec=active,
        )
        evaluated = post_json(
            token,
            EVALUATOR_URL,
            {
                "action": "evaluate_proposed_hypothesis",
                "hypothesis_key": item["hypothesis_key"],
                "evaluation": evaluation,
            },
        )
        finalized = post_json(
            token,
            QUEUE_URL,
            {
                "action": "finalize",
                "queue_key": item["queue_key"],
                "verdict": evaluation["verdict"],
                "result": evaluation,
            },
        )
        registry_after_item = post_json(
            token,
            REGISTRY_URL,
            {"action": "sync_validated"},
        )
        processed.append(
            {
                "claim": claimed,
                "evaluation": evaluated,
                "queue_finalized": finalized,
                "registry_sync": registry_after_item,
                "processed": True,
            }
        )

    queue_after = post_json(token, QUEUE_URL, {"action": "list"})
    active_after = post_json(token, REGISTRY_URL, {"action": "get_active"})

    print(
        json.dumps(
            {
                "stored": stored,
                "strategy_registry_before": registry_before,
                "queue_seed": seeded,
                "processed_queue_items": processed,
                "queue_after": queue_after,
                "active_strategy_after": active_after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
