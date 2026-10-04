from __future__ import annotations

import json
import urllib.request


STATUS_URL = (
    "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/"
    "stock-warashibe-status-read"
)


def fetch_runtime_dashboard(*, timeout_seconds: int = 10) -> dict:
    request = urllib.request.Request(
        STATUS_URL,
        headers={
            "User-Agent": "stock-warashibe-render/0.3",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    if payload.get("app") != "stock-warashibe":
        raise ValueError("unexpected status payload")
    payload["source"] = "supabase_sanitized_status"
    return payload
