# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai ByteDance Seedream 5.0 Pro *image editing*.
# - Uploads local reference image(s) to fal storage, calls `bytedance/seedream/v5/pro/edit`,
#   downloads result image(s) into a specified output directory, and prints progress/logs to stdout
#   (so Nuke's Script Editor shows it).
#
# Usage (example):
#   py -3 fal_seedream_5_pro_edit_helper.py --image "C:/plate.png" --prompt "Make it dusk" --out-dir "C:/temp/run" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model:
# - https://fal.ai/models/bytedance/seedream/v5/pro/edit

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

_ENDPOINT_ID = "bytedance/seedream/v5/pro/edit"
_MAX_IMAGES = 10
_IMAGE_SIZE_CHOICES = (
    "auto_2K",
    "auto_1K",
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
)
_OUTPUT_FORMAT_CHOICES = ("png", "jpeg", "jpg")


def _normalize_output_format(fmt: str) -> str:
    fmt = (fmt or "").strip().lower()
    if fmt == "jpg":
        return "jpeg"
    return fmt


def _write_data_uri(data_uri: str, out_path: str) -> None:
    """
    Supports `sync_mode=True` responses where `images[].url` may be a data URI.
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
        description="Run Seedream 5.0 Pro edit via fal.ai and download results."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        dest="images",
        help="Local reference image path (repeatable, 1..10). Prompt may refer to them as Figure 1, Figure 2, ...",
    )
    parser.add_argument("--prompt", required=True, help="Text prompt describing the desired edit.")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded images.")
    parser.add_argument(
        "--num-images",
        type=int,
        default=1,
        help="Number of images to generate (1..6). Default: 1.",
    )
    parser.add_argument(
        "--output-format",
        default="png",
        choices=_OUTPUT_FORMAT_CHOICES,
        help="Output image format. Default: png.",
    )
    parser.add_argument(
        "--image-size",
        default="auto_2K",
        choices=_IMAGE_SIZE_CHOICES,
        help="Output size preset. Default: auto_2K.",
    )
    parser.add_argument(
        "--enable-safety-checker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable content moderation. Default: true.",
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

    image_paths = [os.path.abspath(p) for p in (args.images or []) if (p or "").strip()]
    if not image_paths:
        print("ERROR: at least one --image is required for Seedream 5.0 Pro edit.", file=sys.stderr)
        return 2
    if len(image_paths) > _MAX_IMAGES:
        print("ERROR: maximum %d --image paths. Got %d." % (_MAX_IMAGES, len(image_paths)), file=sys.stderr)
        return 2
    for p in image_paths:
        if not os.path.isfile(p):
            print("ERROR: reference image file not found: %s" % p, file=sys.stderr)
            return 2

    num_images = int(args.num_images)
    if num_images < 1 or num_images > 6:
        print("ERROR: --num-images must be in range 1..6", file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-seedream-5-pro-edit-helper"

    if args.verbose:
        print("Uploading %d reference image(s)..." % len(image_paths))
    image_urls = [client.upload_file(p) for p in image_paths]

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

    output_format = _normalize_output_format(args.output_format)
    arguments: dict = {
        "prompt": prompt,
        "image_urls": image_urls,
        "num_images": int(num_images),
        "output_format": output_format,
        "image_size": str(args.image_size),
        "enable_safety_checker": bool(args.enable_safety_checker),
        "sync_mode": False,
    }

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
            "ERROR: Seedream 5.0 Pro edit request failed.\n%s"
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
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": downloaded,
        "num_images": len(downloaded),
        "output_format": output_format,
        "image_size": str(args.image_size),
    }
    emit_result_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
