# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to convert SDR video to HDR via fal.ai Topaz.
# - Uploads a local video to fal storage, calls `topaz/sdr-to-hdr/video`, downloads the result.
# - API reference: https://fal.ai/models/topaz/sdr-to-hdr/video
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

_ENDPOINT_ID = "topaz/sdr-to-hdr/video"

_OUTPUT_FORMAT_CHOICES = ("mp4", "prores")


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Convert an SDR video to HDR using fal.ai Topaz and download the result."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local input video (.mp4/.mov).")
    parser.add_argument(
        "--output-format",
        default="mp4",
        choices=_OUTPUT_FORMAT_CHOICES,
        help="mp4 is 10-bit H.265 HDR10. prores is 10-bit ProRes 422 HQ in a .mov. Default: mp4.",
    )
    parser.add_argument("--out", required=True, help="Path to the output video file to write.")
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

    out_ext = _norm_ext(out_path)
    expected_ext = "mov" if args.output_format == "prores" else "mp4"
    if out_ext != expected_ext:
        print(
            "ERROR: --out extension must be .%s when --output-format is %s. Got: %s"
            % (expected_ext, args.output_format, out_path),
            file=sys.stderr,
        )
        return 2

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-topaz-sdr-to-hdr-video-helper"

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded video_url=%s" % video_url)

    arguments: dict = {
        "video_url": video_url,
        "output_format": args.output_format,
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
            "ERROR: Topaz SDR to HDR request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    try:
        video_out_url = result["video"]["url"]
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if args.verbose:
        print("Downloading output video -> %s" % out_path)
    download(str(video_out_url), out_path, user_agent=user_agent)

    emit_result_summary(
        {
            "ok": True,
            "endpoint": _ENDPOINT_ID,
            "out_path": out_path,
            "video_url": video_out_url,
            "output_format": args.output_format,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
