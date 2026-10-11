# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Nano Banana 2.1 generation/edit.
# - If no `--image` inputs are provided, calls `google/nano-banana-2.1` (text-to-image).
# - If any `--image` inputs are provided, calls `google/nano-banana-2.1/edit` with uploaded `image_urls`.
# - Downloads the resulting image(s) into a specified output directory,
#   and prints progress/logs to stdout (so Nuke's Script Editor shows it).
#
# Usage (example):
#   py -3 fal_nano_banana_21_helper.py --prompt "A cinematic sunset" --out-dir "C:/temp/run" --num-images 1 --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.

from __future__ import annotations

import argparse
import base64
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

_ENDPOINT_T2I = "google/nano-banana-2.1"
_ENDPOINT_EDIT = "google/nano-banana-2.1/edit"
_ASPECT_RATIOS = (
    "auto",
    "21:9",
    "16:9",
    "3:2",
    "4:3",
    "5:4",
    "1:1",
    "4:5",
    "3:4",
    "2:3",
    "9:16",
    "4:1",
    "1:4",
    "8:1",
    "1:8",
)
_RESOLUTIONS = ("1K", "2K", "4K")
_THINKING_LEVELS = ("minimal", "medium", "high")
_OUTPUT_FORMATS = ("png", "jpeg", "jpg", "webp")


def _normalize_output_format(fmt: str) -> str:
    fmt = (fmt or "").strip().lower()
    if fmt == "jpg":
        return "jpeg"
    return fmt


def _write_data_uri(data_uri: str, out_path: str) -> None:
    """
    Supports responses where `images[].url` is a data URI.
    Example: data:image/png;base64,....
    """
    if not data_uri.startswith("data:"):
        raise ValueError("not a data uri")
    comma = data_uri.find(",")
    if comma < 0:
        raise ValueError("malformed data uri")
    header = data_uri[:comma].lower()
    payload = data_uri[comma + 1 :]
    is_base64 = ";base64" in header
    data = base64.b64decode(payload) if is_base64 else payload.encode("utf-8")
    ensure_dir(os.path.dirname(os.path.abspath(out_path)))
    with open(out_path, "wb") as f:
        f.write(data)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Nano Banana 2.1 (generate or edit) via fal.ai and download results."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--prompt", required=True, help="Text prompt describing the image to generate or the edit.")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Optional local reference image path (repeatable). If provided, uses the /edit endpoint.",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded images.")
    parser.add_argument(
        "--num-images",
        type=int,
        default=1,
        help="Number of images to generate (1..4). Default: 1.",
    )
    parser.add_argument(
        "--output-format",
        default="png",
        choices=list(_OUTPUT_FORMATS),
        help="Output image format. Default: png.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed.",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="auto",
        choices=list(_ASPECT_RATIOS),
        help='Aspect ratio (or "auto"). Default: auto.',
    )
    parser.add_argument(
        "--resolution",
        default="1K",
        choices=list(_RESOLUTIONS),
        help='Resolution. Default: "1K".',
    )
    parser.add_argument(
        "--safety-tolerance",
        type=int,
        default=4,
        choices=[1, 2, 3, 4, 5, 6],
        help="Safety tolerance (1=strict, 6=relaxed). Default: 4.",
    )
    parser.add_argument(
        "--system-prompt",
        default="",
        help="Optional system instruction. Blank omits the field.",
    )
    parser.add_argument(
        "--thinking-level",
        default="medium",
        choices=list(_THINKING_LEVELS),
        help='How much the model reasons first. Default: "medium".',
    )
    parser.add_argument(
        "--enable-web-search",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable web search during generation. Default: false.",
    )
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
        print("ERROR: prompt is empty.", file=sys.stderr)
        return 2

    num_images = int(args.num_images)
    if num_images < 1 or num_images > 4:
        print("ERROR: --num-images must be in range 1..4", file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-nano-banana-21-helper"

    image_paths = [os.path.abspath(p) for p in (args.image or []) if (p or "").strip()]
    for p in image_paths:
        if not os.path.isfile(p):
            print("ERROR: reference image file not found: %s" % p, file=sys.stderr)
            return 2

    endpoint_id = _ENDPOINT_EDIT if image_paths else _ENDPOINT_T2I

    if args.verbose:
        print("Submitting request: %s" % endpoint_id)

    output_format = _normalize_output_format(args.output_format)
    # sync_mode stays false so fal returns URLs the helper can download.
    # limit_generations stays true, the API default, same as Nano Banana 2.
    arguments: dict = {
        "prompt": prompt,
        "num_images": int(num_images),
        "aspect_ratio": str(args.aspect_ratio),
        "output_format": output_format,
        "safety_tolerance": str(int(args.safety_tolerance)),
        "sync_mode": False,
        "resolution": str(args.resolution),
        "limit_generations": True,
        "enable_web_search": bool(args.enable_web_search),
        "thinking_level": str(args.thinking_level),
    }
    if args.seed is not None:
        arguments["seed"] = int(args.seed)
    system_prompt = (args.system_prompt or "").strip()
    if system_prompt:
        arguments["system_prompt"] = system_prompt

    if image_paths:
        if args.verbose:
            print("Uploading %d reference image(s)..." % len(image_paths))
        arguments["image_urls"] = [client.upload_file(p) for p in image_paths]

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
            "ERROR: Nano Banana 2.1 request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    images = None
    try:
        images = result["images"]
    except Exception:
        images = None
    if not isinstance(images, list) or not images:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    downloaded: list[str] = []
    for idx, item in enumerate(images, start=1):
        if not isinstance(item, dict) or "url" not in item:
            continue
        url = item.get("url")
        if not url:
            continue
        url_s = str(url)
        out_name = "image_%03d.%s" % (idx, output_format)
        out_path = os.path.join(out_dir, out_name)
        if args.verbose:
            print("Downloading %d/%d -> %s" % (idx, len(images), out_path))
        if url_s.startswith("data:"):
            _write_data_uri(url_s, out_path)
        else:
            download(url_s, out_path, user_agent=user_agent)
        downloaded.append(out_path)

    if not downloaded:
        print("ERROR: no images downloaded. Response:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 5

    summary = {
        "ok": True,
        "endpoint": endpoint_id,
        "out_dir": out_dir,
        "downloaded": downloaded,
        "num_images": len(downloaded),
        "output_format": output_format,
    }
    description = result.get("description") if isinstance(result, dict) else None
    if isinstance(description, str):
        summary["description"] = description
    emit_result_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
