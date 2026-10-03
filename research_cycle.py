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
CONTROLLER_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-controller"
OIDC_AUDIENCE = "stock-warashibe-supabase"
MAX_QUEUE_ITEMS_PER_CYCLE = 3
MAX_GENERATION = 6
MAX_CONSECUTIVE_VALIDATED = 2


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
    cycle_key = f"controller-{run_id}-{attempt}"

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
    controller_begin = post_json(
        token,
        CONTROLLER_URL,
        {
            "action": "begin",
            "cycle_key": cycle_key,
            "max_items": MAX_QUEUE_ITEMS_PER_CYCLE,
            "max_generation": MAX_GENERATION,
            "max_consecutive_validated": MAX_CONSECUTIVE_VALIDATED,
        },
    )
    seeded = post_json(token, QUEUE_URL, {"action": "seed"})

    processed = []
    stop_reason = None

    for _ in range(MAX_QUEUE_ITEMS_PER_CYCLE):
        decision = post_json(
            token,
            CONTROLLER_URL,
            {"action": "decision", "cycle_key": cycle_key},
        )
        if decision.get("stop"):
            stop_reason = decision.get("reason")
            break

        claimed = post_json(token, QUEUE_URL, {"action": "claim_next"})
        item = claimed.get("item")
        if not item:
            replanned = post_json(token, QUEUE_URL, {"action": "replan_blocked"})
            if replanned.get("created", 0) == 0:
                processed.append(
                    {
                        "processed": False,
                        "claim": claimed,
                        "replan": replanned,
                    }
                )
                stop_reason = "research_exhausted"
                break
            claimed = post_json(token, QUEUE_URL, {"action": "claim_next"})
            item = claimed.get("item")
            if not item:
                processed.append(
                    {
                        "processed": False,
                        "claim": claimed,
                        "replan": replanned,
                    }
                )
                stop_reason = "research_exhausted"
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
        quality_guard = evaluation.get("quality_guard") or {}
        controller_record = post_json(
            token,
            CONTROLLER_URL,
            {
                "action": "record",
                "cycle_key": cycle_key,
                "queue_key": item["queue_key"],
                "outcome": evaluation["verdict"],
                "quality_rejected": (
                    evaluation["verdict"] == "rejected"
                    and quality_guard.get("criteria_passed") is True
                    and quality_guard.get("accepted") is False
                ),
            },
        )

        sweep = None
        replanned = None
        if evaluation["verdict"] == "validated":
            sweep = post_json(token, QUEUE_URL, {"action": "claim_next"})
            replanned = post_json(token, QUEUE_URL, {"action": "replan_blocked"})

        processed.append(
            {
                "processed": True,
                "claim": claimed,
                "evaluation": evaluated,
                "queue_finalized": finalized,
                "registry_sync": registry_after_item,
                "controller_record": controller_record,
                "stale_sweep": sweep,
                "replan": replanned,
            }
        )

    controller_final = post_json(
        token,
        CONTROLLER_URL,
        {
            "action": "finalize",
            "cycle_key": cycle_key,
            "stop_reason": stop_reason,
        },
    )
    queue_after = post_json(token, QUEUE_URL, {"action": "list"})
    active_after = post_json(token, REGISTRY_URL, {"action": "get_active"})

    print(
        json.dumps(
            {
                "stored": stored,
                "strategy_registry_before": registry_before,
                "controller_begin": controller_begin,
                "queue_seed": seeded,
                "processed_queue_items": processed,
                "controller_final": controller_final,
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
