# Purpose:
# - Shared Python 3 utilities used by multiple `fal_*.py` helper scripts in this folder.
# - Centralizes common logic like: creating directories, atomic downloads, fal-client error parsing,
#   retry heuristics, and printing queue log messages.

from __future__ import annotations

import json
import os
import random
import urllib.request
from typing import Callable, Iterable


def ensure_dir(path: str) -> None:
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def download(url: str, out_path: str, user_agent: str) -> None:
    out_dir = os.path.dirname(os.path.abspath(out_path))
    ensure_dir(out_dir)

    tmp_path = out_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req) as resp:
        with open(tmp_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

    os.replace(tmp_path, out_path)


def extract_fal_error_items(exc: BaseException) -> list[dict]:
    """
    Best-effort extraction of fal error payloads.
    fal_client may store errors on `exc.errors` or as the first arg.
    """
    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        return [e for e in errors if isinstance(e, dict)]

    if getattr(exc, "args", None) and isinstance(exc.args, tuple) and exc.args:
        first = exc.args[0]
        if isinstance(first, list):
            return [e for e in first if isinstance(e, dict)]

    return []


def format_fal_error_summary(exc: BaseException) -> str:
    items = extract_fal_error_items(exc)
    if items:
        try:
            return json.dumps(items, indent=2)
        except Exception:
            return str(items)
    return str(exc)


def should_retry_fal_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status >= 500 or status == 429):
        return True

    for item in extract_fal_error_items(exc):
        if item.get("type") in {"downstream_service_error", "internal_server_error", "rate_limit_error"}:
            return True

    msg = str(exc).lower()
    return (
        (" 500 " in msg)
        or (" 429 " in msg)
        or ("internal server error" in msg)
        or ("downstream service error" in msg)
        or ("rate limit" in msg)
        or ("too many requests" in msg)
    )


def compute_retry_sleep_seconds(attempt: int, retry_base_seconds: float) -> float:
    base = max(0.25, float(retry_base_seconds))
    sleep_s = base * (2 ** max(0, int(attempt) - 1))
    return sleep_s * (0.75 + (0.5 * random.random()))


def iter_queue_log_messages(update) -> Iterable[str]:
    logs = getattr(update, "logs", None)
    if not logs:
        return
    for entry in logs:
        msg = None
        try:
            msg = entry.get("message")
        except Exception:
            msg = None
        if msg:
            yield str(msg)


def print_queue_logs(update, printer: Callable[[str], None] = print) -> None:
    for msg in iter_queue_log_messages(update):
        printer(msg)

