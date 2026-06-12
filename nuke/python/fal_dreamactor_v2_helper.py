# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai DreamActor v2 (motion transfer).
# - Uploads a local style image + motion video to fal storage, calls `fal-ai/bytedance/dreamactor/v2`,
#   downloads the resulting MP4 to a local output path, and prints progress/logs to stdout.
# - Adds light retry/backoff around transient fal backend 5xx ("downstream_service_error") failures.
#
# Usage (example):
#   py -3 fal_dreamactor_v2_helper.py --image temp_style_image.png --video temp_motion_control.mp4 --out temp_output.mp4
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
    download,
    format_fal_error_summary,
    should_retry_fal_error,
)

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Upload image+video, run DreamActor v2 on fal.ai, download resulting video."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local style/reference image (png/jpg).")
    parser.add_argument("--video", required=True, help="Path to local motion/driving video (mp4/mov/webm).")
    parser.add_argument("--out", required=True, help="Path to output MP4.")
    parser.add_argument(
        "--trim-first-second",
        action="store_true",
        default=False,
        help="If set, trims the 1-second transition at the beginning (DreamActor v2).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient fal backend errors (5xx/downstream_service_error). Default: 3.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base backoff seconds for retries (exponential with jitter). Default: 2.0.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more logs.")
    args = parser.parse_args(argv)

    image_path = os.path.abspath(args.image)
    video_path = os.path.abspath(args.video)
    out_path = os.path.abspath(args.out)

    if not os.path.isfile(image_path):
        print("ERROR: image file not found: %s" % image_path, file=sys.stderr)
        return 2
    if not os.path.isfile(video_path):
        print("ERROR: video file not found: %s" % video_path, file=sys.stderr)
        return 2

    fal_key = args.fal_key or os.environ.get("FAL_KEY")
    if not fal_key:
        print("ERROR: missing FAL key. Provide --fal-key or set FAL_KEY env var.", file=sys.stderr)
        return 2

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

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded image_url=%s" % image_url)
        print("Uploaded video_url=%s" % video_url)

    if args.verbose:
        print("Submitting DreamActor v2 request...")

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.subscribe(
                "fal-ai/bytedance/dreamactor/v2",
                arguments={
                    "image_url": image_url,
                    "video_url": video_url,
                    "trim_first_second": bool(args.trim_first_second),
                },
            )
            last_exc = None
            break
        except FalClientHTTPError as e:  # fal-specific error wrapper
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
            # Unknown error; don't loop forever.
            last_exc = e
            break

    if result is None:
        print(
            "ERROR: DreamActor v2 request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    try:
        video_out_url = result["video"]["url"]
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if args.verbose:
        print("Downloading output video...")

    download(video_out_url, out_path, user_agent="nuke-fal-dreamactor-v2-helper")

    print(
        json.dumps(
            {
                "ok": True,
                "video_url": video_out_url,
                "out_path": out_path,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

