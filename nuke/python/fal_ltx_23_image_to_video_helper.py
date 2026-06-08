# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai LTX 2.3 *image-to-video* (not editing).
# - Uploads local start (and optional end) images, calls `fal-ai/ltx-2.3/image-to-video`, downloads the mp4.
#
# Usage (example):
#   py -3 fal_ltx_23_image_to_video_helper.py --image "C:/start.png" --prompt "..." --out "C:/temp/out.mp4" --verbose
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

_ENDPOINT_ID = "fal-ai/ltx-2.3/image-to-video"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run LTX 2.3 image-to-video via fal.ai and download the resulting mp4."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local start frame image.")
    parser.add_argument("--end-image", default="", help="Optional path to end frame image (transition).")
    parser.add_argument("--prompt", required=True, help="Text prompt describing the motion / scene.")
    parser.add_argument("--out", required=True, help="Output path for the downloaded .mp4 file.")
    parser.add_argument(
        "--duration",
        type=int,
        choices=[6, 8, 10],
        default=6,
        help="Video duration in seconds. Default: 6.",
    )
    parser.add_argument(
        "--resolution",
        default="1080p",
        choices=["1080p", "1440p", "2160p"],
        help="Output resolution. Default: 1080p.",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="auto",
        choices=["auto", "16:9", "9:16"],
        help="Aspect ratio. Default: auto (from input image).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        choices=[24, 25, 48, 50],
        default=25,
        help="Frames per second. Default: 25.",
    )
    parser.add_argument(
        "--generate-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to generate audio. Default: true.",
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

    image_path = os.path.abspath(args.image)
    if not os.path.isfile(image_path):
        print("ERROR: start image file not found: %s" % image_path, file=sys.stderr)
        return 2

    end_image_path = (args.end_image or "").strip()
    if end_image_path:
        end_image_path = os.path.abspath(end_image_path)
        if not os.path.isfile(end_image_path):
            print("ERROR: end image file not found: %s" % end_image_path, file=sys.stderr)
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
    user_agent = "nuke-fal-ltx-23-i2v-helper"

    if args.verbose:
        print("Uploading start image: %s" % image_path)
    image_url = client.upload_file(image_path)

    end_image_url = None
    if end_image_path:
        if args.verbose:
            print("Uploading end image: %s" % end_image_path)
        end_image_url = client.upload_file(end_image_path)

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

    def on_queue_update(update) -> None:
        print_queue_logs(update)

    arguments: dict = {
        "image_url": image_url,
        "prompt": args.prompt,
        "duration": int(args.duration),
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "fps": int(args.fps),
        "generate_audio": bool(args.generate_audio),
    }
    if end_image_url:
        arguments["end_image_url"] = end_image_url

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.subscribe(
                _ENDPOINT_ID,
                arguments=arguments,
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
            "ERROR: LTX 2.3 image-to-video request failed.\n%s"
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
        "video": video,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
