# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Bria Extract Object on a still image.
# - Uploads a local image, calls `bria/extract-object` with a prompt, downloads the RGBA cutout
#   (and optional mask) into a specified output directory.
#
# API: https://fal.ai/models/bria/extract-object
#
# Usage (example):
#   py -3 fal_bria_extract_object_helper.py --image "C:/in.png" --prompt "the red car" --out-dir "C:/temp/run" --verbose
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

_ENDPOINT_ID = "bria/extract-object"


def _ext_from_file_name_or_default(file_name: str | None, default_ext: str) -> str:
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext:
            return ext.lstrip(".").lower() or default_ext
    return default_ext.lstrip(".").lower()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a named object from a still image via fal.ai Bria Extract Object."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument(
        "--prompt",
        required=True,
        help="Natural-language description of the object to extract (e.g. the red car).",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded image(s).")
    parser.add_argument(
        "--autocrop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Tighten the output canvas to the extracted object. Default: off.",
    )
    parser.add_argument(
        "--remove-background",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Refine the cutout alpha with RMBG. Default: off (SAM mask alpha).",
    )
    parser.add_argument(
        "--output-mask",
        action="store_true",
        default=False,
        help="Also download the segmentation mask image.",
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
        print("ERROR: --prompt is empty.", file=sys.stderr)
        return 2

    image_path = os.path.abspath(args.image)
    if not os.path.isfile(image_path):
        print("ERROR: image file not found: %s" % image_path, file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    user_agent = "nuke-fal-bria-extract-object-helper"
    client = fal_client.SyncClient(key=fal_key)

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    arguments = {
        "image_url": image_url,
        "prompt": prompt,
        "autocrop": bool(args.autocrop),
        "remove_background": bool(args.remove_background),
    }

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
            "ERROR: Bria Extract Object request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    try:
        image_out_url = result["image"]["url"]
        image_file_name = result["image"].get("file_name")
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    image_ext = _ext_from_file_name_or_default(image_file_name, "png")
    out_path = os.path.join(out_dir, "extracted.%s" % image_ext)

    if args.verbose:
        print("Downloading image -> %s" % out_path)
    download(image_out_url, out_path, user_agent=user_agent)

    mask_path = None
    if args.output_mask and result.get("mask"):
        try:
            mask_out_url = result["mask"]["url"]
            mask_file_name = result["mask"].get("file_name")
        except Exception:
            mask_out_url = None
            mask_file_name = None

        if mask_out_url:
            mask_ext = _ext_from_file_name_or_default(mask_file_name, "png")
            mask_path = os.path.join(out_dir, "mask.%s" % mask_ext)
            if args.verbose:
                print("Downloading mask -> %s" % mask_path)
            download(mask_out_url, mask_path, user_agent=user_agent)

    emit_result_summary(
        {
            "ok": True,
            "endpoint": _ENDPOINT_ID,
            "out_dir": out_dir,
            "downloaded": out_path,
            "mask": mask_path,
            "prompt": prompt,
            "autocrop": bool(args.autocrop),
            "remove_background": bool(args.remove_background),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
