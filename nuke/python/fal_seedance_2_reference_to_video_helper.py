# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai ByteDance Seedance 2.0 *reference-to-video*.
# - Uploads local reference images/videos/audio, calls `bytedance/seedance-2.0/reference-to-video`, downloads the mp4.
#
# Usage (example):
#   py -3 fal_seedance_2_reference_to_video_helper.py --image "C:/char.png" --prompt "@Image1 walks" --out "C:/temp/out.mp4" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model:
# - https://fal.ai/models/bytedance/seedance-2.0/reference-to-video

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

_ENDPOINT_ID = "bytedance/seedance-2.0/reference-to-video"
_DURATION_CHOICES = ["auto"] + [str(i) for i in range(4, 16)]
_MAX_IMAGES = 9
_MAX_VIDEOS = 3
_MAX_AUDIO = 3
_MAX_TOTAL_FILES = 12
_VIDEO_EXTS = ("mp4", "mov")
_AUDIO_EXTS = ("mp3", "wav")


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def _abspath_existing(paths: list[str], kind: str) -> list[str]:
    out: list[str] = []
    for raw in paths or []:
        p = (raw or "").strip()
        if not p:
            continue
        p = os.path.abspath(p)
        if not os.path.isfile(p):
            raise ValueError("%s file not found: %s" % (kind, p))
        out.append(p)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Seedance 2.0 reference-to-video via fal.ai and download the resulting mp4."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        dest="images",
        help="Reference image path. Repeat up to 9 times (prompt: @Image1, @Image2, ...).",
    )
    parser.add_argument(
        "--video",
        action="append",
        default=[],
        dest="videos",
        help="Reference video path (.mp4/.mov). Repeat up to 3 times (prompt: @Video1, @Video2, ...).",
    )
    parser.add_argument(
        "--audio",
        action="append",
        default=[],
        dest="audios",
        help="Reference audio path (.mp3/.wav). Repeat up to 3 times (prompt: @Audio1, @Audio2, ...).",
    )
    parser.add_argument("--prompt", required=True, help="Text prompt describing the motion / scene.")
    parser.add_argument("--out", required=True, help="Output path for the downloaded .mp4 file.")
    parser.add_argument(
        "--duration",
        default="auto",
        choices=_DURATION_CHOICES,
        help='Duration: "auto" or 4-15 seconds (string values as required by the API). Default: auto.',
    )
    parser.add_argument(
        "--resolution",
        default="720p",
        choices=["480p", "720p", "1080p", "4k"],
        help="Output resolution. Default: 720p.",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="auto",
        choices=["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        help="Aspect ratio. Default: auto.",
    )
    parser.add_argument(
        "--bitrate-mode",
        default="standard",
        choices=["standard", "high"],
        help="Output bitrate mode. Default: standard.",
    )
    parser.add_argument(
        "--generate-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to generate synchronized audio. Default: true.",
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

    prompt = (args.prompt or "").strip()
    if not prompt:
        print("ERROR: prompt is empty.", file=sys.stderr)
        return 2

    try:
        image_paths = _abspath_existing(args.images, "image")
        video_paths = _abspath_existing(args.videos, "video")
        audio_paths = _abspath_existing(args.audios, "audio")
    except ValueError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2

    if len(image_paths) > _MAX_IMAGES:
        print("ERROR: maximum %d --image paths. Got %d." % (_MAX_IMAGES, len(image_paths)), file=sys.stderr)
        return 2
    if len(video_paths) > _MAX_VIDEOS:
        print("ERROR: maximum %d --video paths. Got %d." % (_MAX_VIDEOS, len(video_paths)), file=sys.stderr)
        return 2
    if len(audio_paths) > _MAX_AUDIO:
        print("ERROR: maximum %d --audio paths. Got %d." % (_MAX_AUDIO, len(audio_paths)), file=sys.stderr)
        return 2

    total_files = len(image_paths) + len(video_paths) + len(audio_paths)
    if total_files > _MAX_TOTAL_FILES:
        print(
            "ERROR: total files across images/videos/audio must not exceed %d. Got %d."
            % (_MAX_TOTAL_FILES, total_files),
            file=sys.stderr,
        )
        return 2
    if not image_paths and not video_paths:
        print("ERROR: at least one --image or --video is required.", file=sys.stderr)
        return 2

    for p in video_paths:
        if _norm_ext(p) not in _VIDEO_EXTS:
            print("ERROR: video must be .mp4 or .mov. Got: %s" % p, file=sys.stderr)
            return 2
    for p in audio_paths:
        if _norm_ext(p) not in _AUDIO_EXTS:
            print("ERROR: audio must be .mp3 or .wav. Got: %s" % p, file=sys.stderr)
            return 2

    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path) or ".")

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-seedance-2-r2v-helper"

    image_urls: list[str] = []
    for i, p in enumerate(image_paths):
        if args.verbose:
            print("Uploading image %d: %s" % (i + 1, p))
        image_urls.append(client.upload_file(p))

    video_urls: list[str] = []
    for i, p in enumerate(video_paths):
        if args.verbose:
            print("Uploading video %d: %s" % (i + 1, p))
        video_urls.append(client.upload_file(p))

    audio_urls: list[str] = []
    for i, p in enumerate(audio_paths):
        if args.verbose:
            print("Uploading audio %d: %s" % (i + 1, p))
        audio_urls.append(client.upload_file(p))

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

    arguments: dict = {
        "prompt": prompt,
        "duration": args.duration,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "bitrate_mode": args.bitrate_mode,
        "generate_audio": bool(args.generate_audio),
    }
    if image_urls:
        arguments["image_urls"] = image_urls
    if video_urls:
        arguments["video_urls"] = video_urls
    if audio_urls:
        arguments["audio_urls"] = audio_urls

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
            "ERROR: Seedance 2.0 reference-to-video request failed.\n%s"
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
        "endpoint": _ENDPOINT_ID,
        "out": out_path,
        "num_images": len(image_urls),
        "num_videos": len(video_urls),
        "num_audio": len(audio_urls),
        "video": video,
    }
    emit_result_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
