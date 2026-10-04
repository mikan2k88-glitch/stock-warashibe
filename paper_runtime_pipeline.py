from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

from broker.human_gated_adapter import HumanGatedRealTrialAdapter
from paper.human_gate_package import build_human_gate_package
from paper.lifecycle import plan_or_advance_paper_lifecycle
from paper.performance import build_paper_performance
from paper.session import build_paper_session_start
from paper.live_readiness_recheck import assess_live_readiness_recheck


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-paper-runtime-store"
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
    context = post_json(token, {"action": "context"})

    shadow_audit = context.get("shadow_readiness") or {}
    reopen_gate = shadow_audit.get("reopen_gate") or {}
    active_strategy = context.get("active_strategy") or {}
    run_id = os.environ.get("GITHUB_RUN_ID", "local")

    session_result = build_paper_session_start(
        reopen_gate,
        existing_sessions=context.get("paper_sessions") or [],
        run_id=run_id,
        strategy_key=str(active_strategy.get("strategy_key") or ""),
    )

    lifecycle = plan_or_advance_paper_lifecycle(
        session_result,
        existing_orders=context.get("paper_orders") or [],
        observations=context.get("shadow_observations") or [],
        batch=None,
    )

    all_orders = list(context.get("paper_orders") or [])
    if lifecycle.get("order"):
        order_key = lifecycle["order"]["order_key"]
        all_orders = [
            row for row in all_orders
            if row.get("order_key") != order_key
        ] + [lifecycle["order"]]

    performance = build_paper_performance(
        session_result,
        orders=all_orders,
        as_of=date.today(),
    )
    live = assess_live_readiness_recheck(
        reopen_gate,
        performance,
        broker_connected=False,
        live_secret_configured=False,
    )
    human = build_human_gate_package(
        live,
        package_key=f"human-gate-{run_id}",
    )
    intent = HumanGatedRealTrialAdapter().prepare(
        human,
        explicit_human_approval=False,
        broker_connected=False,
    )

    decision = (
        "human_gate_ready"
        if human["status"] == "ready_for_review"
        else "paper_runtime_blocked"
    )
    rationale = (
        "Paper validation qualified; human review package prepared. "
        "No broker connection or live order was performed."
        if decision == "human_gate_ready"
        else "Paper/runtime gates remain blocked; no broker connection or live order was performed."
    )

    stored = post_json(
        token,
        {
            "session": session_result.get("session"),
            "order": lifecycle.get("order"),
            "performance": performance,
            "live_readiness": live,
            "human_gate_package": human,
            "real_trial_intent": intent,
            "decision": decision,
            "rationale": rationale,
        },
    )

    print(json.dumps({
        "development_endpoints": {
            "038": session_result,
            "039": lifecycle,
            "040": performance,
            "041": live,
            "042": human,
            "043": intent,
        },
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
