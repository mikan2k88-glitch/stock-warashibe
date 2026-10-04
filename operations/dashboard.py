from __future__ import annotations

import json
import time
import urllib.request


STATUS_URL = (
    "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/"
    "stock-warashibe-status-read"
)


def fetch_runtime_dashboard(
    *,
    timeout_seconds: int = 10,
    maximum_attempts: int = 3,
    retry_delay_seconds: float = 0.25,
) -> dict:
    if maximum_attempts < 1 or maximum_attempts > 3:
        raise ValueError("maximum_attempts must be between 1 and 3")

    last_error: Exception | None = None
    for attempt in range(1, maximum_attempts + 1):
        request = urllib.request.Request(
            STATUS_URL,
            headers={
                "User-Agent": "stock-warashibe-render/0.3",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                payload = json.load(response)
            if payload.get("app") != "stock-warashibe":
                raise ValueError("unexpected status payload")
            payload["source"] = "supabase_sanitized_status"
            return payload
        except Exception as exc:
            last_error = exc
            if attempt == maximum_attempts:
                break
            time.sleep(retry_delay_seconds)

    assert last_error is not None
    raise last_error
