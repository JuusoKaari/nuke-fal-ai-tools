# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Depth Anything v2 preprocessor on a still image.
# - Uploads a local image to fal storage, calls `fal-ai/image-preprocessors/depth-anything/v2`,
#   downloads the depth map image into a specified output directory, and prints progress to stdout.
#
# Usage (example):
#   py -3 fal_depth_anything_v2_helper.py --image "C:/in.png" --out-dir "C:/temp/run" --verbose
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
    ensure_dir,
    format_fal_error_summary,
    print_queue_logs,
    should_retry_fal_error,
)

_ENDPOINT_ID = "fal-ai/image-preprocessors/depth-anything/v2"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Depth Anything v2 depth map preprocessor on a still image via fal.ai."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument("--out-dir", required=True, help="Output directory for the downloaded depth map image.")
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

    image_path = os.path.abspath(args.image)
    if not os.path.isfile(image_path):
        print("ERROR: image file not found: %s" % image_path, file=sys.stderr)
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
    user_agent = "nuke-fal-depth-anything-v2-helper"

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

    def on_queue_update(update) -> None:
        print_queue_logs(update)

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.subscribe(
                _ENDPOINT_ID,
                arguments={"image_url": image_url},
                with_logs=True,
                on_queue_update=on_queue_update,
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
            "ERROR: Depth Anything v2 request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    try:
        image_obj = result["image"]
        url = image_obj.get("url")
        file_name = image_obj.get("file_name")
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if not url:
        print("ERROR: no image URL in response:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 5

    ext = "png"
    if file_name:
        _, e = os.path.splitext(file_name)
        if e:
            ext = e.lstrip(".").lower() or "png"
    out_name = "depth_map.%s" % ext
    out_path = os.path.join(out_dir, out_name)

    if args.verbose:
        print("Downloading depth map -> %s" % out_path)
    download(str(url), out_path, user_agent=user_agent)

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": out_path,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
