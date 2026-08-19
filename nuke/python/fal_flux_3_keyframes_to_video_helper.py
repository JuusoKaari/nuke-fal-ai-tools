# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai FLUX 3 *keyframes-to-video*.
# - Uploads 1-10 local keyframe images, pins them to 24 fps frame indices, calls the
#   main or draft endpoint, downloads the mp4.
#
# Usage (example):
#   py -3 fal_flux_3_keyframes_to_video_helper.py --image a.png --image b.png --prompt "..." --out out.mp4 --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model:
# - https://fal.ai/models/blackforestlabs/flux-3/keyframes-to-video
# - Draft: https://fal.ai/models/blackforestlabs/flux-3/keyframes-to-video/draft

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

_ENDPOINT_ID = "blackforestlabs/flux-3/keyframes-to-video"
_DRAFT_ENDPOINT_ID = "blackforestlabs/flux-3/keyframes-to-video/draft"
_DURATION_CHOICES = list(range(5, 21))
_ASPECT_RATIO_CHOICES = ["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
_SAFETY_TOLERANCE_CHOICES = [0, 1, 2, 3, 4]
_MAX_KEYFRAMES = 10
_FPS = 24


def even_frame_indices(count, duration, fps=_FPS):
    """Spread keyframes from frame 0 to duration*fps (inclusive). Unique ints."""
    max_frame = int(duration) * int(fps)
    if count < 1:
        raise ValueError("need at least 1 keyframe")
    if count > max_frame + 1:
        raise ValueError(
            "too many keyframes (%d) for duration %ds at %d fps (max %d unique frames)"
            % (count, int(duration), int(fps), max_frame + 1)
        )
    if count == 1:
        return [0]
    out = []
    for i in range(count):
        out.append(int(round(i * float(max_frame) / float(count - 1))))
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1
    if out[-1] > max_frame:
        out[-1] = max_frame
        for i in range(len(out) - 2, -1, -1):
            if out[i] >= out[i + 1]:
                out[i] = out[i + 1] - 1
    out[0] = 0
    return out


def parse_frame_indices(raw, count, duration, fps=_FPS):
    """Parse comma-separated frame_index values. Empty -> even spacing."""
    text = (raw or "").strip()
    if not text:
        return even_frame_indices(count, duration, fps=fps)
    parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    if len(parts) != count:
        raise ValueError(
            "frame_indices has %d values but %d keyframes were provided"
            % (len(parts), count)
        )
    max_frame = int(duration) * int(fps)
    indices = []
    seen = set()
    for part in parts:
        try:
            idx = int(float(part))
        except Exception:
            raise ValueError("invalid frame_index: %s" % part)
        if idx < 0 or idx > max_frame:
            raise ValueError(
                "frame_index %d is outside 0..%d (duration %ds at %d fps)"
                % (idx, max_frame, int(duration), int(fps))
            )
        if idx in seen:
            raise ValueError("duplicate frame_index: %d" % idx)
        seen.add(idx)
        indices.append(idx)
    return indices


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run FLUX 3 keyframes-to-video via fal.ai and download the resulting mp4."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument(
        "--image",
        action="append",
        required=True,
        dest="images",
        help="Path to a keyframe image. Repeat for each keyframe (1-10 total, in order).",
    )
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
        "--frame-indices",
        default="",
        help="Optional comma-separated 24 fps frame_index values (one per --image). Empty = even spacing from 0 to duration*24.",
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

    image_paths = [os.path.abspath(p) for p in (args.images or [])]
    if len(image_paths) < 1 or len(image_paths) > _MAX_KEYFRAMES:
        print("ERROR: provide 1-%d keyframe images via repeated --image." % _MAX_KEYFRAMES, file=sys.stderr)
        return 2
    for p in image_paths:
        if not os.path.isfile(p):
            print("ERROR: keyframe image not found: %s" % p, file=sys.stderr)
            return 2

    try:
        frame_indices = parse_frame_indices(
            args.frame_indices, len(image_paths), int(args.duration), fps=_FPS
        )
    except ValueError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2

    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path) or ".")

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-flux-3-keyframes-helper"
    endpoint_id = _DRAFT_ENDPOINT_ID if args.draft else _ENDPOINT_ID

    image_urls = []
    for i, p in enumerate(image_paths):
        if args.verbose:
            print("Uploading keyframe %d: %s" % (i + 1, p))
        image_urls.append(client.upload_file(p))

    if args.verbose:
        print("Submitting request: %s" % endpoint_id)

    keyframes = []
    for image_url, frame_index in zip(image_urls, frame_indices):
        keyframes.append({"image_url": image_url, "frame_index": int(frame_index)})

    arguments: dict = {
        "prompt": args.prompt,
        "duration": int(args.duration),
        "aspect_ratio": args.aspect_ratio,
        "generate_audio": bool(args.generate_audio),
        "safety_tolerance": int(args.safety_tolerance),
        "keyframes": keyframes,
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
            "ERROR: FLUX 3 keyframes-to-video request failed.\n%s"
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
        "num_keyframes": len(image_paths),
        "frame_indices": frame_indices,
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
