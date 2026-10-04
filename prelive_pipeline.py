from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

from backtest.champion_spec import CURRENT_CHAMPION_SPEC
from backtest.robustness_runner import run_robustness_validation
from data.jpx_delisted import fetch_delisted_issues
from paper.accounting import close_position, open_position
from paper.candidate_discovery import discover_daily_candidate
from paper.engine import propose_paper_buy
from paper.live_readiness import assess_live_readiness
from paper.notifications import build_approval_request
from paper.readiness import assess_paper_readiness
from research.expanded_retest import build_expanded_retest
from research.point_in_time_universe import build_lifecycle_snapshot
from research.sector_diagnosis import diagnose_sectors
from research.tail_analysis import analyze_tail_windows


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-prelive-store"
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
    today = date.today()
    robustness = run_robustness_validation(as_of=today)

    delisted, jpx_source = fetch_delisted_issues(as_of=today)
    lifecycle = build_lifecycle_snapshot(delisted, snapshot_date=today)

    tail = analyze_tail_windows(robustness)
    sectors = diagnose_sectors(robustness)
    retest = build_expanded_retest(robustness, lifecycle, tail, sectors)

    freshness = all(
        int(row.get("stale_days") or 0) <= 10
        for row in robustness.get("coverage", {}).get("eligible", [])
    )
    readiness = assess_paper_readiness(
        retest,
        data_fresh=freshness,
        active_strategy_key=CURRENT_CHAMPION_SPEC["strategy_key"],
    )

    candidate = discover_daily_candidate(robustness)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    session_key = f"paper-prelive-{run_id}-{attempt}"
    proposal = propose_paper_buy(candidate, readiness, session_key=session_key)
    approval = build_approval_request(
        candidate,
        proposal,
        request_key=f"{session_key}:approval",
        session_key=session_key,
    )

    # Endpoint 029 is implemented and unit-tested, but no virtual fill is created
    # while the paper readiness gate is blocked.
    accounting_preview = {
        "endpoint": "029",
        "status": "blocked" if not readiness["paper_trading_allowed"] else "awaiting_human_approval",
        "capital_before": 30000,
        "capital_after": 30000,
        "position_open": False,
        "paper_only": True,
    }

    live = assess_live_readiness(
        readiness,
        closed_paper_trades=0,
        paper_days=0,
        broker_connected=False,
        live_secret_configured=False,
    )

    result = {
        "endpoints": {
            "021": lifecycle,
            "022": tail,
            "023": sectors,
            "024": retest,
            "025": readiness,
            "026": proposal,
            "027": candidate,
            "028": approval,
            "029": accounting_preview,
            "030": live,
        },
        "jpx_source": jpx_source,
        "champion": CURRENT_CHAMPION_SPEC,
        "live_trading": False,
        "paper_session": {
            "session_key": session_key,
            "strategy_key": CURRENT_CHAMPION_SPEC["strategy_key"],
            "starting_capital": 30000,
            "current_capital": 30000,
            "status": "ready" if readiness["paper_trading_allowed"] else "blocked",
            "readiness": readiness,
            "ledger": accounting_preview,
            "live_trading": False,
        },
        "paper_order": proposal.get("order"),
        "approval_request": approval,
        "live_readiness": live,
        "lifecycle_records": lifecycle["lifecycle_records"],
        "summary": {
            "endpoint_from": 21,
            "endpoint_to": 30,
            "point_in_time_verified": lifecycle["point_in_time"]["verified"],
            "delisted_records_loaded": lifecycle["delisted_record_count"],
            "robustness_gate_score": retest["robustness_gate_score"],
            "paper_trading_allowed": readiness["paper_trading_allowed"],
            "live_trading_allowed": live["live_trading_allowed"],
            "human_gate_required": live["human_gate_required"],
        },
    }

    req = urllib.request.Request(
        STORE_URL,
        data=json.dumps(result).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {get_oidc_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        stored = json.load(response)

    print(json.dumps({"result": result["summary"], "stored": stored}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
