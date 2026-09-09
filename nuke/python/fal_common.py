# Purpose:
# - Shared Python 3 utilities used by multiple `fal_*.py` helper scripts in this folder.
# - Centralizes common logic like: creating directories, atomic downloads with timeout/retry,
#   fal-client subscribe retry, nested fal error unwrapping, retry heuristics, and result sidecars.
# - Helpers do not stream fal queue logs to Nuke (noisy tqdm bars).

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


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


def _parse_jsonish(text):
    """Parse a JSON object/array, or the first JSON blob inside a longer string."""
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    if s[0] in "{[":
        try:
            return json.loads(s)
        except Exception:
            pass
    brace = s.find("{")
    bracket = s.find("[")
    starts = [i for i in (brace, bracket) if i >= 0]
    if not starts:
        return None
    try:
        return json.loads(s[min(starts) :])
    except Exception:
        return None


def _dict_items_from_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if isinstance(payload, str):
        parsed = _parse_jsonish(payload)
        if parsed is not None:
            return _dict_items_from_payload(parsed)
    return []


def extract_fal_error_items(exc: BaseException) -> list[dict]:
    """
    Best-effort extraction of fal error payloads.
    fal_client may store errors on `exc.errors` or as the first arg.
    """
    errors = getattr(exc, "errors", None)
    items = _dict_items_from_payload(errors)
    if items:
        return items

    if getattr(exc, "args", None) and isinstance(exc.args, tuple) and exc.args:
        items = _dict_items_from_payload(exc.args[0])
        if items:
            return items

    return _dict_items_from_payload(str(exc))


def _humanize_fal_payload(obj, depth: int = 0):
    """
    Pull a readable message out of fal error JSON.
    Unwraps nested blobs like:
    {"detail": "Erase API error: {\\"error\\":\\"premium mode has been removed from the API\\"}"}
    """
    if depth > 8:
        return None
    if obj is None:
        return None
    if isinstance(obj, str):
        parsed = _parse_jsonish(obj)
        if parsed is not None:
            inner = _humanize_fal_payload(parsed, depth + 1)
            if inner:
                prefix = obj.strip()
                cut = min((i for i in (prefix.find("{"), prefix.find("[")) if i >= 0), default=-1)
                if cut > 0:
                    prefix = prefix[:cut].strip().rstrip(":").strip()
                    if prefix and inner.lower() not in prefix.lower():
                        return "%s: %s" % (prefix, inner)
                return inner
        stripped = obj.strip()
        return stripped or None
    if isinstance(obj, dict):
        for key in ("error", "detail", "msg", "message"):
            if key not in obj:
                continue
            found = _humanize_fal_payload(obj[key], depth + 1)
            if found:
                return found
        return None
    if isinstance(obj, (list, tuple)):
        parts = []
        for item in obj:
            found = _humanize_fal_payload(item, depth + 1)
            if found and found not in parts:
                parts.append(found)
        if parts:
            return "\n".join(parts)
        return None
    return str(obj)


def format_fal_error_summary(exc: BaseException) -> str:
    items = extract_fal_error_items(exc)
    human = _humanize_fal_payload(items) if items else _humanize_fal_payload(str(exc))
    if human:
        return human
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


_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "bearer",
    "fal_key",
)
_SIDECAR_MAX_STR = 4000
_SIDECAR_MAX_LIST = 50
_SIDECAR_MAX_DEPTH = 8


def _key_looks_secret(key) -> bool:
    k = str(key or "").strip().lower().replace("-", "_")
    for frag in _SECRET_KEY_FRAGMENTS:
        if frag in k:
            return True
    return False


def sanitize_for_sidecar(obj, _depth: int = 0):
    """
    Deep-copy JSON-ish data with secrets redacted and long strings truncated.
    Never write fal keys / tokens into sidecars.
    """
    if _depth > _SIDECAR_MAX_DEPTH:
        return "<max_depth>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        if len(obj) > _SIDECAR_MAX_STR:
            return obj[:_SIDECAR_MAX_STR] + "...<truncated>"
        return obj
    if isinstance(obj, bytes):
        try:
            return sanitize_for_sidecar(obj.decode("utf-8", "replace"), _depth=_depth)
        except Exception:
            return "<bytes>"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key_s = str(k)
            if _key_looks_secret(key_s):
                out[key_s] = "<redacted>"
            else:
                out[key_s] = sanitize_for_sidecar(v, _depth=_depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        items = list(obj)
        trimmed = items[:_SIDECAR_MAX_LIST]
        out_list = [sanitize_for_sidecar(v, _depth=_depth + 1) for v in trimmed]
        if len(items) > _SIDECAR_MAX_LIST:
            out_list.append("<truncated %d more items>" % (len(items) - _SIDECAR_MAX_LIST))
        return out_list
    try:
        return sanitize_for_sidecar(str(obj), _depth=_depth)
    except Exception:
        return "<unserializable>"


def write_result_sidecar(result_path: str, metadata_dict) -> str | None:
    """
    Write a sanitized .json sidecar next to the primary result (same stem).
    Returns the sidecar path, or None if result_path is empty.
    """
    if not result_path:
        return None
    abs_result = os.path.abspath(str(result_path))
    stem, _ext = os.path.splitext(abs_result)
    sidecar_path = stem + ".json"
    ensure_dir(os.path.dirname(sidecar_path) or ".")

    payload = sanitize_for_sidecar(metadata_dict if isinstance(metadata_dict, dict) else {})
    if not isinstance(payload, dict):
        payload = {"data": payload}
    if "timestamp" not in payload:
        payload["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "result_path" not in payload:
        payload["result_path"] = abs_result

    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    tmp_path = sidecar_path + ".part"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp_path, sidecar_path)
    return sidecar_path


def _primary_path_from_summary(summary: dict):
    if not isinstance(summary, dict):
        return None
    for key in ("downloaded", "out", "out_path", "output_file", "result_path"):
        v = summary.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        if isinstance(v, dict):
            for item in v.values():
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def emit_result_summary(summary, result_path=None) -> None:
    """
    Print the helper JSON summary to stdout and write a sanitized sidecar
    next to the primary result file when a path is known.
    """
    path = result_path or _primary_path_from_summary(summary if isinstance(summary, dict) else {})
    if path:
        try:
            write_result_sidecar(path, summary)
        except Exception as e:
            print("WARNING: failed to write result sidecar: %s" % e, file=sys.stderr)
    print(json.dumps(summary))


configure_stdio_utf8()
