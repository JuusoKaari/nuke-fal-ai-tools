# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai SAM 3.1 Image on a still.
# - Uploads a local image, calls `fal-ai/sam-3-1/image` with a required text prompt,
#   downloads one still (mask by default, RGBA cutout when apply_mask is on).
# - Empty `image`/`masks` is a no-match, not a schema error. Short noun prompts work;
#   instructional placeholders are rejected before upload.
#
# API: https://fal.ai/models/fal-ai/sam-3-1/image
#
# Usage (example):
#   py -3 fal_sam_3_1_image_helper.py --image "C:/in.png" --prompt "the red car" --out-dir "C:/temp/run" --verbose
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

_ENDPOINT_ID = "fal-ai/sam-3-1/image"
_OUTPUT_FORMAT = "png"
_PLACEHOLDER_PROMPT_PREFIX = "describe the object to segment"
_PROMPT_HINT = "Use a short noun or noun phrase (person, car, wheel). Long sentences and instructions usually return no mask."


def _ext_from_file_name_or_default(file_name: str | None, default_ext: str) -> str:
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext:
            return ext.lstrip(".").lower() or default_ext
    return default_ext.lstrip(".").lower()


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


def _looks_like_placeholder_prompt(prompt):
    lowered = (prompt or "").strip().lower()
    return lowered.startswith(_PLACEHOLDER_PROMPT_PREFIX)


def _primary_still(result):
    url, name = _file_url_and_name((result or {}).get("image"))
    if url:
        return url, name
    masks = (result or {}).get("masks") or []
    if isinstance(masks, list) and masks:
        return _file_url_and_name(masks[0])
    return None, None


def _is_empty_sam_result(result):
    if not isinstance(result, dict):
        return False
    if "image" not in result and "masks" not in result:
        return False
    masks = result.get("masks")
    if masks is None:
        masks = []
    if not isinstance(masks, list) or masks:
        return False
    url, _name = _file_url_and_name(result.get("image"))
    return not url


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Segment a still image via fal.ai SAM 3.1 Image (text prompt, one mask)."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument(
        "--prompt",
        required=True,
        help="Short noun or noun phrase to segment (person, car, wheel). Required; never empty.",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for the downloaded still.")
    parser.add_argument(
        "--apply-mask",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Apply the mask on the image (RGBA cutout). Default: off (mask still).",
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
    if _looks_like_placeholder_prompt(prompt):
        print(
            "ERROR: prompt is the node placeholder, not an object to segment.\n%s"
            % _PROMPT_HINT,
            file=sys.stderr,
        )
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

    user_agent = "nuke-fal-sam-3-1-image-helper"
    client = fal_client.SyncClient(key=fal_key)

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    apply_mask = bool(args.apply_mask)
    arguments = {
        "image_url": image_url,
        "prompt": prompt,
        "apply_mask": apply_mask,
        "output_format": _OUTPUT_FORMAT,
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
            "ERROR: SAM 3.1 Image request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    image_out_url, image_file_name = _primary_still(result)
    if not image_out_url:
        if _is_empty_sam_result(result):
            print(
                "ERROR: SAM 3.1 found no objects matching prompt: %s\n%s"
                % (prompt, _PROMPT_HINT),
                file=sys.stderr,
            )
        else:
            print(
                "ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2),
                file=sys.stderr,
            )
        return 4

    image_ext = _ext_from_file_name_or_default(image_file_name, _OUTPUT_FORMAT)
    stem = "cutout" if apply_mask else "mask"
    out_path = os.path.join(out_dir, "%s.%s" % (stem, image_ext))

    if args.verbose:
        print("Downloading image -> %s" % out_path)
    download(image_out_url, out_path, user_agent=user_agent)

    emit_result_summary(
        {
            "ok": True,
            "endpoint": _ENDPOINT_ID,
            "out_dir": out_dir,
            "downloaded": out_path,
            "prompt": prompt,
            "apply_mask": apply_mask,
            "output_format": _OUTPUT_FORMAT,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
