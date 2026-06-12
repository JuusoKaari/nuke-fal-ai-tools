# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai OpenRouter LLM text generation.
# - Calls `openrouter/router`, writes the response to output.txt, and prints a JSON summary.
#
# Usage (example):
#   py -3 fal_openrouter_generate_text_helper.py --prompt "Hello" --model google/gemini-2.5-flash --out-dir "C:/temp/run" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from fal_common import (
    compute_retry_sleep_seconds,
    ensure_dir,
    format_fal_error_summary,
    should_retry_fal_error,
)

_ENDPOINT_ID = "openrouter/router"


def _write_output_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run OpenRouter LLM text generation via fal.ai."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--prompt", required=True, help="User prompt for the LLM.")
    parser.add_argument("--model", required=True, help="OpenRouter model id (e.g. google/gemini-2.5-flash).")
    parser.add_argument("--system-prompt", default=None, help="Optional system prompt.")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature (0-2).")
    parser.add_argument("--max-tokens", type=int, default=None, help="Max output tokens.")
    parser.add_argument(
        "--reasoning",
        action="store_true",
        help="Include model reasoning in the output when the API returns it.",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for output.txt.")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient fal backend errors (5xx/429). Default: 3.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base backoff seconds for retries (exponential with jitter). Default: 2.0.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more logs.")
    args = parser.parse_args(argv)

    fal_key = args.fal_key or os.environ.get("FAL_KEY")
    if not fal_key:
        print("ERROR: missing FAL key. Provide --fal-key or set FAL_KEY env var.", file=sys.stderr)
        return 2

    prompt = (args.prompt or "").strip()
    if not prompt:
        print("ERROR: prompt is empty.", file=sys.stderr)
        return 2

    model = (args.model or "").strip()
    if not model:
        print("ERROR: model is empty.", file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    try:
        from fal_client.client import FalClientHTTPError  # type: ignore
    except Exception:
        FalClientHTTPError = Exception  # type: ignore

    client = fal_client.SyncClient(key=fal_key)

    arguments: dict = {
        "prompt": prompt,
        "model": model,
    }
    system_prompt = (args.system_prompt or "").strip()
    if system_prompt:
        arguments["system_prompt"] = system_prompt
    if args.temperature is not None:
        arguments["temperature"] = float(args.temperature)
    if args.max_tokens is not None:
        arguments["max_tokens"] = int(args.max_tokens)
    if args.reasoning:
        arguments["reasoning"] = True

    if args.verbose:
        print("Submitting request: %s (model=%s)" % (_ENDPOINT_ID, model))

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.subscribe(
                _ENDPOINT_ID,
                arguments=arguments,
            )
            last_exc = None
            break
        except FalClientHTTPError as e:
            last_exc = e
            if (attempt >= max_attempts) or (not should_retry_fal_error(e)):
                break
            sleep_s = compute_retry_sleep_seconds(attempt, float(args.retry_base_seconds))
            print(
                "WARNING: fal request failed (attempt %d/%d). Retrying in %.1fs.\n%s"
                % (attempt, max_attempts, sleep_s, format_fal_error_summary(e)),
                file=sys.stderr,
            )
            time.sleep(sleep_s)
        except Exception as e:
            last_exc = e
            break

    if result is None:
        print(
            "ERROR: OpenRouter text generation request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    try:
        output_text = result.get("output")
        if output_text is None:
            output_text = ""
        else:
            output_text = str(output_text)
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if args.reasoning:
        reasoning = result.get("reasoning")
        if reasoning:
            reasoning_s = str(reasoning).strip()
            if reasoning_s:
                if output_text.strip():
                    output_text = output_text.rstrip() + "\n\n--- reasoning ---\n" + reasoning_s
                else:
                    output_text = reasoning_s

    out_path = os.path.join(out_dir, "output.txt")
    if args.verbose:
        print("Writing output -> %s" % out_path)
    _write_output_text(out_path, output_text)

    usage = result.get("usage")
    if not isinstance(usage, dict):
        usage = None

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "output_file": out_path,
        "output_text": output_text,
    }
    if usage is not None:
        summary["usage"] = usage
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
