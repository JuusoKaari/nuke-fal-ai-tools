# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai SAM 3.1 Video on a movie.
# - Uploads a local video, calls `fal-ai/sam-3-1/video` with a required text prompt,
#   downloads the result movie only (ignores boundingbox_frames_zip).
# - Text prompt only. Commas can name several objects. No box or point prompts.
#
# API: https://fal.ai/models/fal-ai/sam-3-1/video
#
# Usage (example):
#   py -3 fal_sam_3_1_video_helper.py --video "C:/in.mp4" --prompt "person" --out "C:/temp/run/out.mp4" --verbose
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

_ENDPOINT_ID = "fal-ai/sam-3-1/video"
_OUTPUT_TYPE_MP4 = "X264 (.mp4)"
_OUTPUT_TYPE_WEBM = "VP9 (.webm)"
_OUTPUT_TYPE_CHOICES = (_OUTPUT_TYPE_MP4, _OUTPUT_TYPE_WEBM)


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def _file_url_and_name(obj):
    if obj is None:
        return None, None
    if isinstance(obj, str):
        url = obj.strip()
        return (url, None) if url else (None, None)
    if isinstance(obj, dict):
        url = obj.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip(), obj.get("file_name")
    return None, None


def _clamp_detection_threshold(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.5
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _normalize_max_objects(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 16
    if v < 1:
        return 1
    return v


def _normalize_output_type(output_type):
    s = (output_type or "").strip()
    if s not in _OUTPUT_TYPE_CHOICES:
        raise ValueError(
            "output type must be one of: %s" % ", ".join(_OUTPUT_TYPE_CHOICES)
        )
    return s


def output_ext_for_type(output_type):
    """File extension for an output_type choice (.mp4 or .webm, no leading dot)."""
    normalized = _normalize_output_type(output_type)
    if normalized == _OUTPUT_TYPE_WEBM:
        return "webm"
    return "mp4"


def build_arguments(
    video_url,
    prompt,
    apply_mask,
    detection_threshold,
    max_objects,
    output_type,
):
    """Payload for fal-ai/sam-3-1/video. Text prompt only; no boxes or points."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is empty")
    return {
        "video_url": video_url,
        "prompt": prompt,
        "apply_mask": bool(apply_mask),
        "detection_threshold": _clamp_detection_threshold(detection_threshold),
        "max_num_objects": _normalize_max_objects(max_objects),
        "output_type": _normalize_output_type(output_type),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Segment a video via fal.ai SAM 3.1 Video (text prompt, one movie)."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local input video (.mp4/.mov).")
    parser.add_argument(
        "--prompt",
        default="person",
        help="Short noun or comma-separated objects to segment. Default: person.",
    )
    parser.add_argument(
        "--apply-mask",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply the mask on the video. Default: on.",
    )
    parser.add_argument(
        "--detection-threshold",
        type=float,
        default=0.5,
        help="Detection threshold, clamped to 0..1. Default: 0.5.",
    )
    parser.add_argument(
        "--max-objects",
        type=int,
        default=16,
        help="Maximum number of objects (at least 1). Default: 16.",
    )
    parser.add_argument(
        "--output-type",
        default=_OUTPUT_TYPE_MP4,
        choices=_OUTPUT_TYPE_CHOICES,
        help="X264 (.mp4) or VP9 (.webm). Default: X264 (.mp4).",
    )
    parser.add_argument("--out", required=True, help="Path to output video file to write.")
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

    prompt = (args.prompt or "").strip()
    if not prompt:
        print("ERROR: --prompt is empty.", file=sys.stderr)
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
        output_type = _normalize_output_type(args.output_type)
        expected_ext = output_ext_for_type(output_type)
    except ValueError as e:
        print("ERROR: %s" % (e,), file=sys.stderr)
        return 2

    out_ext = _norm_ext(out_path)
    if out_ext != expected_ext:
        print(
            "ERROR: --out extension must be .%s when --output-type is %s. Got: %s"
            % (expected_ext, output_type, out_path),
            file=sys.stderr,
        )
        return 2

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    user_agent = "nuke-fal-sam-3-1-video-helper"
    client = fal_client.SyncClient(key=fal_key)

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded video_url=%s" % video_url)

    try:
        arguments = build_arguments(
            video_url,
            prompt,
            args.apply_mask,
            args.detection_threshold,
            args.max_objects,
            output_type,
        )
    except ValueError as e:
        print("ERROR: %s" % (e,), file=sys.stderr)
        return 2

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

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
            "ERROR: SAM 3.1 Video request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    video_out_url, _video_file_name = _file_url_and_name((result or {}).get("video"))
    if not video_out_url:
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
            "prompt": prompt,
            "apply_mask": bool(args.apply_mask),
            "detection_threshold": arguments["detection_threshold"],
            "max_num_objects": arguments["max_num_objects"],
            "output_type": output_type,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
