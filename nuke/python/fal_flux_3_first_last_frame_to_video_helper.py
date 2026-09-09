# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai FLUX 3 *first-last-frame-to-video*.
# - Uploads local start and end images, calls the main or draft endpoint, downloads the mp4.
#
# Usage (example):
#   py -3 fal_flux_3_first_last_frame_to_video_helper.py --image "C:/start.png" --end-image "C:/end.png" --prompt "..." --out "C:/temp/out.mp4" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model:
# - https://fal.ai/models/blackforestlabs/flux-3/first-last-frame-to-video
# - Draft: https://fal.ai/models/blackforestlabs/flux-3/first-last-frame-to-video/draft

from __future__ import annotations

import argparse
import json
import os
import sys

from fal_common import (
    download,
    emit_result_summary,
    ensure_dir,
    format_fal_error_summary,
    subscribe_with_retry,
)

_ENDPOINT_ID = "blackforestlabs/flux-3/first-last-frame-to-video"
_DRAFT_ENDPOINT_ID = "blackforestlabs/flux-3/first-last-frame-to-video/draft"
_DURATION_CHOICES = list(range(5, 21))
_ASPECT_RATIO_CHOICES = ["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
_SAFETY_TOLERANCE_CHOICES = [0, 1, 2, 3, 4]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run FLUX 3 first-last-frame-to-video via fal.ai and download the resulting mp4."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local start frame image.")
    parser.add_argument("--end-image", required=True, help="Path to local end frame image.")
    parser.add_argument("--prompt", required=True, help="Text prompt describing the motion / scene.")
    parser.add_argument("--out", required=True, help="Output path for the downloaded .mp4 file.")
    parser.add_argument(
        "--duration",
        type=int,
        default=5,
        choices=_DURATION_CHOICES,
        help="Duration in seconds (5-20). Default: 5.",
    )
    parser.add_argument(
        "--resolution",
        default="720p",
        choices=["720p", "1080p"],
        help="Output resolution for the main endpoint. Ignored for draft. Default: 720p.",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="auto",
        choices=_ASPECT_RATIO_CHOICES,
        help="Aspect ratio. Default: auto.",
    )
    parser.add_argument(
        "--generate-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to generate synchronized audio. Default: true.",
    )
    parser.add_argument(
        "--safety-tolerance",
        type=int,
        default=2,
        choices=_SAFETY_TOLERANCE_CHOICES,
        help="Safety tolerance (0=strictest, 4=most permissive). Default: 2.",
    )
    parser.add_argument(
        "--draft",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use the draft endpoint instead of full quality. Default: false.",
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

    end_image_path = os.path.abspath((args.end_image or "").strip())
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

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-flux-3-first-last-helper"
    endpoint_id = _DRAFT_ENDPOINT_ID if args.draft else _ENDPOINT_ID

    if args.verbose:
        print("Uploading start image: %s" % image_path)
    image_url = client.upload_file(image_path)

    if args.verbose:
        print("Uploading end image: %s" % end_image_path)
    end_image_url = client.upload_file(end_image_path)

    if args.verbose:
        print("Submitting request: %s" % endpoint_id)

    arguments: dict = {
        "start_image_url": image_url,
        "end_image_url": end_image_url,
        "prompt": args.prompt,
        "duration": int(args.duration),
        "aspect_ratio": args.aspect_ratio,
        "generate_audio": bool(args.generate_audio),
        "safety_tolerance": int(args.safety_tolerance),
    }
    if not args.draft:
        arguments["resolution"] = args.resolution

    try:
        result = subscribe_with_retry(
            client,
            endpoint_id,
            arguments,
            max_retries=args.max_retries,
            retry_base_seconds=args.retry_base_seconds,
            verbose=args.verbose,
        )
    except Exception as e:
        print(
            "ERROR: FLUX 3 first-last-frame-to-video request failed.\n%s"
            % format_fal_error_summary(e),
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
        "endpoint": endpoint_id,
        "out": out_path,
        "video": video,
    }
    if isinstance(result, dict) and "seed" in result:
        summary["seed"] = result["seed"]
    if isinstance(result, dict) and "draft_cache" in result:
        summary["draft_cache"] = result["draft_cache"]
    emit_result_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
