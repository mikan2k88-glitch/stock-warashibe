from __future__ import annotations

import json
import os
import urllib.request

from backtest.robustness_runner import run_robustness_validation
from data.universe_provenance import assess_point_in_time_readiness
from research.robustness_failure_diagnosis import diagnose_robustness_failure


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-research-store"
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
    robustness = run_robustness_validation()
    provenance = assess_point_in_time_readiness(
        current_manifest_frozen=True,
        current_universe_size=int(robustness["summary"]["candidate_symbol_count"]),
        delisted_records_loaded=0,
        historical_membership_snapshots_loaded=0,
        paid_source_enabled=False,
    )
    diagnosis = diagnose_robustness_failure(robustness, provenance)

    result = {
        "mode": "g6_robustness_failure_and_provenance_gate",
        "data_source": robustness["data_source"],
        "starting_capital": robustness["starting_capital"],
        "live_trading": False,
        "symbol": "EXPANDED-MULTI-DIAGNOSIS",
        "universe": robustness["universe"],
        "coverage": robustness["coverage"],
        "robustness": robustness["robustness"],
        "failure_diagnosis": diagnosis,
        "universe_provenance": provenance,
        "per_symbol": robustness["per_symbol"],
        "summary": {
            **robustness["summary"],
            "endpoint": "020",
            "failure_decision": diagnosis["decision"],
            "point_in_time_verified": provenance["verified"],
            "paper_trading_allowed": False,
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "strategies": robustness["strategies"],
    }

    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    run_key = f"g6-failure-diagnosis-{run_id}-{attempt}"

    req = urllib.request.Request(
        STORE_URL,
        data=json.dumps({
            "run_key": run_key,
            "scenario_key": "g6-robustness-failure-diagnosis",
            "result": result,
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
        "development_endpoint": "020",
        "diagnosis": diagnosis,
        "stored": stored,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
