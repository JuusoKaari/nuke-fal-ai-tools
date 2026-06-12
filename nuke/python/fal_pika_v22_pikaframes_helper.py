# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Pika 2.2 Pikaframes keyframe interpolation.
# - Uploads 2-5 local keyframe images, calls `fal-ai/pika/v2.2/pikaframes`, downloads the mp4.
#
# Usage (example):
#   py -3 fal_pika_v22_pikaframes_helper.py --image a.png --image b.png --prompt "smooth transition" --out out.mp4 --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model:
# - https://fal.ai/models/fal-ai/pika/v2.2/pikaframes

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from fal_common import (
    compute_retry_sleep_seconds,
    download,
    ensure_dir,
    format_fal_error_summary,
    should_retry_fal_error,
)

_ENDPOINT_ID = "fal-ai/pika/v2.2/pikaframes"
_MAX_TOTAL_TRANSITION_SECONDS = 25


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Pika 2.2 Pikaframes (multi-keyframe image-to-video) via fal.ai and download the mp4."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument(
        "--image",
        action="append",
        required=True,
        dest="images",
        help="Path to a keyframe image. Repeat for each keyframe (2-5 total, in order).",
    )
    parser.add_argument("--prompt", default="", help="Default prompt for all transitions.")
    parser.add_argument("--negative-prompt", default="", help="Negative prompt.")
    parser.add_argument("--out", required=True, help="Output path for the downloaded .mp4 file.")
    parser.add_argument(
        "--resolution",
        default="720p",
        choices=["720p", "1080p"],
        help="Output resolution. Default: 720p.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed.")
    parser.add_argument(
        "--transition-duration",
        type=int,
        default=5,
        help="Duration in seconds for each transition (1-25). Default: 5.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient fal backend errors. Default: 3.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base backoff seconds for retries. Default: 2.0.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more logs.")
    args = parser.parse_args(argv)

    fal_key = args.fal_key or os.environ.get("FAL_KEY")
    if not fal_key:
        print("ERROR: missing FAL key. Provide --fal-key or set FAL_KEY env var.", file=sys.stderr)
        return 2

    image_paths = [os.path.abspath(p) for p in (args.images or [])]
    if len(image_paths) < 2 or len(image_paths) > 5:
        print("ERROR: provide 2-5 keyframe images via repeated --image.", file=sys.stderr)
        return 2
    for p in image_paths:
        if not os.path.isfile(p):
            print("ERROR: keyframe image not found: %s" % p, file=sys.stderr)
            return 2

    duration = int(args.transition_duration)
    if duration < 1 or duration > 25:
        print("ERROR: transition duration must be between 1 and 25 seconds.", file=sys.stderr)
        return 2

    num_transitions = len(image_paths) - 1
    total_duration = duration * num_transitions
    if total_duration > _MAX_TOTAL_TRANSITION_SECONDS:
        print(
            "ERROR: total transition duration is %d seconds (%d transitions x %d s), max is %d."
            % (total_duration, num_transitions, duration, _MAX_TOTAL_TRANSITION_SECONDS),
            file=sys.stderr,
        )
        return 2

    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path) or ".")

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
    user_agent = "nuke-fal-pika-v22-pikaframes-helper"

    image_urls = []
    for i, p in enumerate(image_paths):
        if args.verbose:
            print("Uploading keyframe %d: %s" % (i + 1, p))
        image_urls.append(client.upload_file(p))

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

    prompt = (args.prompt or "").strip()
    negative_prompt = (args.negative_prompt or "").strip()

    arguments: dict = {
        "image_urls": image_urls,
        "transitions": [{"duration": duration} for _ in range(num_transitions)],
        "resolution": args.resolution,
        "negative_prompt": negative_prompt,
    }
    if prompt:
        arguments["prompt"] = prompt
    if args.seed is not None:
        arguments["seed"] = int(args.seed)

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
            "ERROR: Pika 2.2 Pikaframes request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    video = None
    try:
        video = result["video"]
    except Exception:
        video = None
    if not isinstance(video, dict) or not video.get("url"):
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    url = str(video["url"])
    if args.verbose:
        print("Downloading video -> %s" % out_path)
    download(url, out_path, user_agent=user_agent)

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out": out_path,
        "num_keyframes": len(image_paths),
        "video": video,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
