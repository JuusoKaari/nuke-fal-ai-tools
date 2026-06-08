# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Nano Banana 2 generation/edit.
# - If no `--image` inputs are provided, calls `fal-ai/nano-banana-2` (text-to-image).
# - If any `--image` inputs are provided, calls `fal-ai/nano-banana-2/edit` (image-to-image) using uploaded `image_urls`.
# - Downloads the resulting image(s) into a specified output directory,
#   and prints progress/logs to stdout (so Nuke's Script Editor shows it).
#
# Usage (example):
#   py -3 fal_nano_banana_2_generate_helper.py --prompt "A cinematic sunset" --out-dir "C:/temp/run" --num-images 1 --verbose
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
import time

from fal_common import (
    compute_retry_sleep_seconds,
    download,
    ensure_dir,
    format_fal_error_summary,
    print_queue_logs,
    should_retry_fal_error,
)

_ENDPOINT_T2I = "fal-ai/nano-banana-2"
_ENDPOINT_EDIT = "fal-ai/nano-banana-2/edit"


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
    is_base64 = (";base64" in header)
    data = base64.b64decode(payload) if is_base64 else payload.encode("utf-8")
    ensure_dir(os.path.dirname(os.path.abspath(out_path)))
    with open(out_path, "wb") as f:
        f.write(data)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run Nano Banana 2 (generate or edit) via fal.ai and download results.")
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--prompt", required=True, help="Text prompt describing the image to generate.")
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
        "--aspect-ratio",
        default="auto",
        choices=["auto", "21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16"],
        help='Aspect ratio (or "auto"). Default: auto.',
    )
    parser.add_argument(
        "--resolution",
        default="1K",
        choices=["0.5K", "1K", "2K", "4K"],
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
    try:
        from fal_client.client import FalClientHTTPError  # type: ignore
    except Exception:
        FalClientHTTPError = Exception  # type: ignore

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-nano-banana-2-helper"

    image_paths = [os.path.abspath(p) for p in (args.image or []) if (p or "").strip()]
    for p in image_paths:
        if not os.path.isfile(p):
            print("ERROR: reference image file not found: %s" % p, file=sys.stderr)
            return 2

    endpoint_id = _ENDPOINT_EDIT if image_paths else _ENDPOINT_T2I

    if args.verbose:
        print("Submitting request: %s" % endpoint_id)

    def on_queue_update(update) -> None:
        print_queue_logs(update)

    output_format = _normalize_output_format(args.output_format)
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
    }
    if args.seed is not None:
        arguments["seed"] = int(args.seed)

    if image_paths:
        if args.verbose:
            print("Uploading %d reference image(s)..." % len(image_paths))
        image_urls = [client.upload_file(p) for p in image_paths]
        arguments["image_urls"] = image_urls

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.subscribe(
                endpoint_id,
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update,
            )
            last_exc = None
            break
        except FalClientHTTPError as e:
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
            "ERROR: Nano Banana 2 request failed.\n%s"
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
        "seed": result.get("seed"),
        "num_images": len(downloaded),
        "output_format": output_format,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

