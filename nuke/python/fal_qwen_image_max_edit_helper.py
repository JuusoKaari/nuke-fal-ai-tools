# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Qwen Image Max *image editing* on a single still image.
# - Uploads a local image to fal storage, calls `fal-ai/qwen-image-max/edit`, downloads the edited image(s)
#   into a specified output directory, and prints progress/logs to stdout (so Nuke's Script Editor shows it).
#
# Usage (example):
#   py -3 fal_qwen_image_max_edit_helper.py --image "C:/in.png" --prompt "Make it sunset" --out-dir "C:/temp/run" --output-format png --num-images 1 --verbose
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
import time

from fal_common import (
    compute_retry_sleep_seconds,
    download,
    ensure_dir,
    format_fal_error_summary,
    should_retry_fal_error,
)


_ENDPOINT_ID = "fal-ai/qwen-image-max/edit"


def _normalize_output_format(fmt: str) -> str:
    fmt = (fmt or "").strip().lower()
    if fmt == "jpg":
        return "jpeg"
    return fmt


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Qwen Image Max edit on a single still image via fal.ai and download results."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument("--prompt", required=True, help="Text prompt describing the desired edit.")
    parser.add_argument("--negative-prompt", default="", help="Optional negative prompt.")
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
        choices=["png", "jpeg", "jpg", "webp"],
        help="Output image format. Default: png.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducibility (0..2147483647).",
    )
    parser.add_argument(
        "--image-size",
        default="",
        help="Optional output size (fal image_size). Leave empty to use input image size.",
    )
    parser.add_argument(
        "--enable-prompt-expansion",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable LLM prompt optimization. Default: true.",
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

    image_path = os.path.abspath(args.image)
    if not os.path.isfile(image_path):
        print("ERROR: image file not found: %s" % image_path, file=sys.stderr)
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
    try:
        from fal_client.client import FalClientHTTPError  # type: ignore
    except Exception:
        FalClientHTTPError = Exception  # type: ignore

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-qwen-image-max-edit-helper"

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)

    output_format = _normalize_output_format(args.output_format)
    arguments: dict = {
        "prompt": args.prompt,
        "negative_prompt": args.negative_prompt or "",
        "image_urls": [image_url],
        "num_images": num_images,
        "output_format": output_format,
        "enable_prompt_expansion": bool(args.enable_prompt_expansion),
        "enable_safety_checker": bool(args.enable_safety_checker),
    }
    if args.seed is not None:
        arguments["seed"] = int(args.seed)
    if (args.image_size or "").strip():
        arguments["image_size"] = (args.image_size or "").strip()

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.subscribe(
                _ENDPOINT_ID,
                arguments=arguments,
            )
            last_exc = None
            break
        except FalClientHTTPError as e:  # fal-specific error wrapper
            last_exc = e
            if (attempt >= max_attempts) or (not should_retry_fal_error(e)):
                break
            sleep_s = compute_retry_sleep_seconds(attempt, float(args.retry_base_seconds))
            print(
                "WARNING: fal request failed (attempt %d/%d). Retrying in %.1fs.\n%s"
                % (attempt, max_attempts, sleep_s, format_fal_error_summary(e)),
                file=sys.stderr,
            )
            time.sleep(sleep_s)
        except Exception as e:
            last_exc = e
            break

    if result is None:
        print(
            "ERROR: Qwen Image Max edit request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
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
        out_name = "image_%03d.%s" % (idx, output_format)
        out_path = os.path.join(out_dir, out_name)
        if args.verbose:
            print("Downloading %d/%d -> %s" % (idx, len(images), out_path))
        download(str(url), out_path, user_agent=user_agent)
        downloaded.append(out_path)

    if not downloaded:
        print("ERROR: no images downloaded. Response:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 5

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": downloaded,
        "seed": result.get("seed"),
        "num_images": len(downloaded),
        "output_format": output_format,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

