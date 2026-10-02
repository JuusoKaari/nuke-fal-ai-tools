# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai OpenAI GPT Image 2.5 generate or edit.
# - No `--image` calls the text-to-image endpoint. One or more `--image` calls the edit endpoint.
# - Variant `flare` (default) or `sunburst` selects the endpoint pair. Optional `--mask` is edit-only.
#
# Usage (example):
#   py -3 fal_gpt_image_25_helper.py --prompt "A cinematic sunset" --out-dir "C:/temp/run" --verbose
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

_MAX_IMAGES = 16
_VARIANT_FLARE = "flare"
_VARIANT_SUNBURST = "sunburst"
_VARIANTS = (_VARIANT_FLARE, _VARIANT_SUNBURST)
_QUALITY_CHOICES = ("auto", "low", "medium", "high", "xhigh", "max")
_BACKGROUND_CHOICES = ("auto", "transparent", "opaque")
_IMAGE_SIZE_CHOICES = (
    "landscape_4_3",
    "auto",
    "square",
    "landscape_16_9",
    "portrait_16_9",
)
_OUTPUT_FORMAT_CHOICES = ("png", "jpeg", "jpg", "webp")
_EDIT_IMAGE_SIZE = "auto"
_DEFAULT_T2I_IMAGE_SIZE = "landscape_4_3"


def _endpoint_id(variant, is_edit):
    kind = "edit" if is_edit else "text-to-image"
    return "openai/gpt-image-2.5/%s/%s" % (variant, kind)


def _normalize_output_format(fmt):
    fmt = (fmt or "").strip().lower()
    if fmt == "jpg":
        return "jpeg"
    return fmt


def _write_data_uri(data_uri, out_path):
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


def main(argv):
    parser = argparse.ArgumentParser(
        description="Run OpenAI GPT Image 2.5 (generate or edit) via fal.ai and download results."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--prompt", required=True, help="Text prompt describing the image or edit.")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Optional local reference image path (repeatable, max 16). If provided, uses the edit endpoint.",
    )
    parser.add_argument("--mask", default="", help="Optional local mask image path (edit only, uploaded as mask_url).")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded images.")
    parser.add_argument(
        "--variant",
        default=_VARIANT_FLARE,
        choices=list(_VARIANTS),
        help='Model variant. Default: "flare".',
    )
    parser.add_argument(
        "--num-images",
        type=int,
        default=1,
        help="Number of images to generate (1..4). Default: 1.",
    )
    parser.add_argument(
        "--output-format",
        default="png",
        choices=list(_OUTPUT_FORMAT_CHOICES),
        help="Output image format. Default: png.",
    )
    parser.add_argument(
        "--quality",
        default="high",
        choices=list(_QUALITY_CHOICES),
        help='Generation quality. Default: "high".',
    )
    parser.add_argument(
        "--background",
        default="auto",
        choices=list(_BACKGROUND_CHOICES),
        help='Background. Default: "auto".',
    )
    parser.add_argument(
        "--image-size",
        default=_DEFAULT_T2I_IMAGE_SIZE,
        choices=list(_IMAGE_SIZE_CHOICES),
        help="Text-to-image size preset. Ignored on edit (always auto). Default: landscape_4_3.",
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

    image_paths = [os.path.abspath(p) for p in (args.image or []) if (p or "").strip()]
    if len(image_paths) > _MAX_IMAGES:
        print(
            "ERROR: maximum %d --image paths. Got %d." % (_MAX_IMAGES, len(image_paths)),
            file=sys.stderr,
        )
        return 2

    mask_path = (args.mask or "").strip()
    if mask_path and not image_paths:
        print(
            "ERROR: --mask requires at least one --image (edit). Text-to-image does not accept a mask.",
            file=sys.stderr,
        )
        return 2

    for p in image_paths:
        if not os.path.isfile(p):
            print("ERROR: reference image file not found: %s" % p, file=sys.stderr)
            return 2

    if mask_path:
        mask_path = os.path.abspath(mask_path)
        if not os.path.isfile(mask_path):
            print("ERROR: mask file not found: %s" % mask_path, file=sys.stderr)
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
    user_agent = "nuke-fal-gpt-image-25-helper"
    is_edit = bool(image_paths)
    variant = str(args.variant)
    endpoint_id = _endpoint_id(variant, is_edit)

    image_urls = []
    if image_paths:
        if args.verbose:
            print("Uploading %d reference image(s)..." % len(image_paths))
        image_urls = [client.upload_file(p) for p in image_paths]

    mask_url = None
    if mask_path:
        if args.verbose:
            print("Uploading mask: %s" % mask_path)
        mask_url = client.upload_file(mask_path)

    if args.verbose:
        print("Submitting request: %s" % endpoint_id)

    output_format = _normalize_output_format(args.output_format)
    image_size = _EDIT_IMAGE_SIZE if is_edit else str(args.image_size)
    arguments = {
        "prompt": prompt,
        "num_images": int(num_images),
        "output_format": output_format,
        "image_size": image_size,
        "quality": str(args.quality),
        "background": str(args.background),
        "sync_mode": False,
    }
    if is_edit:
        arguments["image_urls"] = image_urls
    if mask_url:
        arguments["mask_url"] = mask_url

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
            "ERROR: GPT Image 2.5 request failed.\n%s"
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

    downloaded = []
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
        "quality": str(args.quality),
        "variant": variant,
    }
    emit_result_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
