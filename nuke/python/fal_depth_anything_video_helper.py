# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to estimate video depth via fal.ai Depth Anything Video.
# - Uploads a local video to fal storage, calls `fal-ai/depth-anything-video`, downloads the MP4
#   and the raw float32 depths as a .npz next to that MP4. Nuke does not load the .npz.
# - API reference: https://fal.ai/models/fal-ai/depth-anything-video
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

_ENDPOINT_ID = "fal-ai/depth-anything-video"

_MODEL_CHOICES = ("VDA-Small", "VDA-Base", "VDA-Large")
_COLORMAP_CHOICES = ("grayscale", "turbo", "inferno", "magma", "viridis")
_RESOLUTION_CHOICES = ("auto", "360p", "480p", "720p", "1080p")


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def raw_depths_path_for_mp4(mp4_path: str) -> str:
    """Sibling .npz for a depth MP4. Same folder, same stem."""
    stem, _ext = os.path.splitext(os.path.abspath(mp4_path or ""))
    return stem + ".npz"


def build_arguments(video_url, model, colormap, resolution, side_by_side):
    """Payload for fal-ai/depth-anything-video. Output fps stays at the source rate."""
    if model not in _MODEL_CHOICES:
        raise ValueError("model must be one of: %s" % ", ".join(_MODEL_CHOICES))
    if colormap not in _COLORMAP_CHOICES:
        raise ValueError("colormap must be one of: %s" % ", ".join(_COLORMAP_CHOICES))
    if resolution not in _RESOLUTION_CHOICES:
        raise ValueError("resolution must be one of: %s" % ", ".join(_RESOLUTION_CHOICES))
    return {
        "video_url": video_url,
        "model": model,
        "colormap": colormap,
        "resolution": resolution,
        "side_by_side": bool(side_by_side),
        "include_raw_depths": True,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Estimate depth for a video using fal.ai Depth Anything Video and download the result."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local input video (.mp4/.mov).")
    parser.add_argument(
        "--model",
        default="VDA-Large",
        choices=_MODEL_CHOICES,
        help="Model size. VDA-Large is best quality, VDA-Small is fastest. Default: VDA-Large.",
    )
    parser.add_argument(
        "--colormap",
        default="grayscale",
        choices=_COLORMAP_CHOICES,
        help="Depth visualization. grayscale is normalized depth. Default: grayscale.",
    )
    parser.add_argument(
        "--resolution",
        default="auto",
        choices=_RESOLUTION_CHOICES,
        help="Output resolution. auto preserves the input, capped at 1080p. Default: auto.",
    )
    parser.add_argument(
        "--side-by-side",
        action="store_true",
        help="Write original and depth side by side in one video.",
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
    user_agent = "nuke-fal-depth-anything-video-helper"

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded video_url=%s" % video_url)

    try:
        arguments = build_arguments(
            video_url,
            args.model,
            args.colormap,
            args.resolution,
            args.side_by_side,
        )
    except ValueError as e:
        print("ERROR: %s" % (e,), file=sys.stderr)
        return 2

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
            "ERROR: Depth Anything Video request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    try:
        video_out_url = result["video"]["url"]
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    raw_obj = result.get("raw_depths") if isinstance(result, dict) else None
    raw_url = raw_obj.get("url") if isinstance(raw_obj, dict) else None
    if not raw_url:
        print(
            "ERROR: response did not include raw_depths:\n%s" % json.dumps(result, indent=2),
            file=sys.stderr,
        )
        return 4

    if args.verbose:
        print("Downloading output video -> %s" % out_path)
    download(str(video_out_url), out_path, user_agent=user_agent)

    raw_path = raw_depths_path_for_mp4(out_path)
    if args.verbose:
        print("Downloading raw depths -> %s" % raw_path)
    download(str(raw_url), raw_path, user_agent=user_agent)

    emit_result_summary(
        {
            "ok": True,
            "endpoint": _ENDPOINT_ID,
            "out_path": out_path,
            "video_url": video_out_url,
            "raw_depths_path": raw_path,
            "raw_depths_url": raw_url,
            "model": args.model,
            "colormap": args.colormap,
            "resolution": args.resolution,
            "side_by_side": bool(args.side_by_side),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
