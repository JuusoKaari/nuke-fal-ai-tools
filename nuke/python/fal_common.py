# Purpose:
# - Shared Python 3 utilities used by multiple `fal_*.py` helper scripts in this folder.
# - Centralizes common logic like: creating directories, atomic downloads with timeout/retry,
#   fal-client subscribe retry, error parsing, and retry heuristics.
# - Helpers do not stream fal queue logs to Nuke (noisy tqdm bars).

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request


def configure_stdio_utf8() -> None:
    """Avoid Windows cp1252 crashes when fal/tqdm prints Unicode progress bars."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def safe_print(msg: str, file=None) -> None:
    target = file if file is not None else sys.stdout
    try:
        print(msg, file=target)
    except UnicodeEncodeError:
        enc = getattr(target, "encoding", None) or "utf-8"
        sanitized = str(msg).encode(enc, errors="replace").decode(enc, errors="replace")
        try:
            print(sanitized, file=target)
        except Exception:
            pass


def ensure_dir(path: str) -> None:
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def download(url: str, out_path: str, user_agent: str, timeout_seconds: float = 60) -> None:
    out_dir = os.path.dirname(os.path.abspath(out_path))
    ensure_dir(out_dir)

    tmp_path = out_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    max_attempts = 4
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
            os.replace(tmp_path, out_path)
            return
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last_exc = e
            if attempt >= max_attempts:
                raise
            sleep_s = compute_retry_sleep_seconds(attempt, 2.0)
            print(
                "WARNING: download failed (attempt %d/%d). Retrying in %.1fs.\n%s"
                % (attempt, max_attempts, sleep_s, e),
                file=sys.stderr,
            )
            time.sleep(sleep_s)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("download: no result")


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


def subscribe_with_retry(
    client,
    endpoint_id,
    arguments,
    max_retries=3,
    retry_base_seconds=2.0,
    verbose=False,
):
    """
    Call client.subscribe with the same retry policy copied across fal helpers.
    --max-retries 3 means 4 tries. Retries only FalClientHTTPError when
    should_retry_fal_error is true. Other exceptions are re-raised immediately.
    verbose is accepted so helpers can pass args.verbose; retry warnings
    always go to stderr.
    """
    try:
        from fal_client.client import FalClientHTTPError
    except Exception:
        FalClientHTTPError = Exception

    max_attempts = max(1, int(max_retries) + 1)
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return client.subscribe(endpoint_id, arguments=arguments)
        except FalClientHTTPError as e:
            last_exc = e
            if (attempt >= max_attempts) or (not should_retry_fal_error(e)):
                raise
            sleep_s = compute_retry_sleep_seconds(attempt, float(retry_base_seconds))
            print(
                "WARNING: fal request failed (attempt %d/%d). Retrying in %.1fs.\n%s"
                % (attempt, max_attempts, sleep_s, format_fal_error_summary(e)),
                file=sys.stderr,
            )
            time.sleep(sleep_s)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("subscribe_with_retry: no result")


configure_stdio_utf8()
