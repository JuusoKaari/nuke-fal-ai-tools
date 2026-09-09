# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to upscale video via fal.ai Bytedance upscaler.
# - Uploads a local video to fal storage, calls `fal-ai/bytedance-upscaler/upscale/video`, downloads the MP4.
# - API reference: https://fal.ai/models/fal-ai/bytedance-upscaler/upscale/video
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

from fal_common import (
    download,
    emit_result_summary,
    ensure_dir,
    format_fal_error_summary,
    subscribe_with_retry,
)

_ENDPOINT_ID = "fal-ai/bytedance-upscaler/upscale/video"

_RESOLUTION_CHOICES = ("1080p", "2k", "4k")
_FPS_CHOICES = ("30fps", "60fps")


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Upscale a video using fal.ai Bytedance video upscaler and download the result."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local input video (.mp4/.mov).")
    parser.add_argument(
        "--target-resolution",
        default="1080p",
        choices=_RESOLUTION_CHOICES,
        help="Output resolution. Default: 1080p.",
    )
    parser.add_argument(
        "--target-fps",
        default="30fps",
        choices=_FPS_CHOICES,
        help="Output frame rate mode. Default: 30fps.",
    )
    parser.add_argument("--out", required=True, help="Path to output MP4 file to write.")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient fal backend errors (5xx/429/downstream_service_error). Default: 3.",
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

    video_path = os.path.abspath(args.video)
    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path))

    if not os.path.isfile(video_path):
        print("ERROR: video file not found: %s" % video_path, file=sys.stderr)
        return 2

    video_ext = _norm_ext(video_path)
    if video_ext not in {"mp4", "mov"}:
        print(
            "ERROR: video must be .mp4 or .mov for this model. Got: %s" % video_path,
            file=sys.stderr,
        )
        return 2

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-bytedance-video-upscale-helper"

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded video_url=%s" % video_url)

    arguments: dict = {
        "video_url": video_url,
        "target_resolution": args.target_resolution,
        "target_fps": args.target_fps,
    }

    if args.verbose:
        print("Submitting request: %s" % (_ENDPOINT_ID,))
    try:
        result = subscribe_with_retry(
            client,
            _ENDPOINT_ID,
            arguments,
            max_retries=args.max_retries,
            retry_base_seconds=args.retry_base_seconds,
            verbose=args.verbose,
        )
    except Exception as e:
        print(
            "ERROR: Bytedance upscale request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    try:
        video_out_url = result["video"]["url"]
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    duration = result.get("duration")

    if args.verbose:
        print("Downloading output video -> %s" % out_path)
    download(str(video_out_url), out_path, user_agent=user_agent)

    out_obj: dict = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_path": out_path,
        "video_url": video_out_url,
        "target_resolution": args.target_resolution,
        "target_fps": args.target_fps,
    }
    if duration is not None:
        out_obj["duration"] = duration
    emit_result_summary(out_obj)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
