from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

QUEUE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/warashibe-dev-queue"
OIDC_AUDIENCE = "warashibe-supabase"
MAX_CONTENT_BYTES = 100_000
ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".yml", ".yaml", ".json", ".toml"}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def current_head() -> str:
    return run("git", "rev-parse", "HEAD").stdout.strip()


def get_oidc_token() -> str:
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    separator = "&" if "?" in request_url else "?"
    req = urllib.request.Request(
        f"{request_url}{separator}audience={OIDC_AUDIENCE}",
        headers={"Authorization": f"Bearer {request_token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)["value"]


def queue_call(token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        QUEUE_URL,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def allowed_path(raw: str) -> Path:
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe_path")
    if path.suffix not in ALLOWED_SUFFIXES:
        raise ValueError("path_not_allowlisted")
    return path


def verify() -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], text=True, capture_output=True)
    log = (proc.stdout + "\n" + proc.stderr)[-4000:]
    if proc.returncode != 0:
        return False, log
    diff = run("git", "diff", "--check", check=False)
    return diff.returncode == 0, (log + "\n" + diff.stdout + diff.stderr)[-4000:]


def main() -> int:
    token = get_oidc_token()
    result = queue_call(token, {"action": "next"})
    task = result.get("task")
    if not task:
        print("No pending queue item.")
        return 0

    task_id = str(task.get("task_id") or "")
    path = allowed_path(str(task.get("target_path") or ""))
    if task.get("base_sha") and task.get("base_sha") != current_head():
        queue_call(token, {"action": "reject", "task_id": task_id, "error_message": "base_sha_mismatch"})
        return 0

    content = task.get("content")
    if not isinstance(content, str) or len(content.encode()) > MAX_CONTENT_BYTES:
        raise ValueError("invalid_content")

    existed = path.exists()
    old = path.read_text(encoding="utf-8") if existed else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        ok, log = verify()
        if not ok:
            if existed:
                path.write_text(old or "", encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
            queue_call(token, {"action": "fail", "task_id": task_id, "test_result": log, "error_message": "tests_failed"})
            return 1

        run("git", "config", "user.name", "stock-warashibe-queue-bot")
        run("git", "config", "user.email", "actions@users.noreply.github.com")
        run("git", "add", "--", str(path))
        run("git", "commit", "-m", f"queue: {task_id}")
        sha = current_head()
        run("git", "push", "origin", "HEAD:main")
        queue_call(token, {"action": "complete", "task_id": task_id, "commit_sha": sha, "test_result": log})
        print(f"Committed {task_id} as {sha}")
        return 0
    except Exception:
        if existed and old is not None:
            path.write_text(old, encoding="utf-8")
        elif not existed:
            path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
