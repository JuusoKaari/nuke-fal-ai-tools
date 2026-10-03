# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Marigold depth estimation on a still image.
# - Uploads a local image to fal storage, calls `fal-ai/imageutils/marigold-depth`,
#   downloads the depth map into a specified output directory, and prints progress to stdout.
#
# API: https://fal.ai/models/fal-ai/imageutils/marigold-depth
#
# Usage (example):
#   py -3 fal_marigold_depth_helper.py --image "C:/in.png" --out-dir "C:/temp/run" --verbose
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

_ENDPOINT_ID = "fal-ai/imageutils/marigold-depth"
_STEPS_MIN = 2
_STEPS_MAX = 50
_ENSEMBLE_MIN = 2
_ENSEMBLE_MAX = 50
_RES_MIN = 0
_RES_MAX = 2048
_DEFAULT_STEPS = 10
_DEFAULT_ENSEMBLE = 10
_DEFAULT_RES = 0


def validate_settings(num_inference_steps, ensemble_size, processing_res):
    """Return an error string when a knob is outside the API range, else None."""
    checks = (
        (num_inference_steps, _STEPS_MIN, _STEPS_MAX, "--num-inference-steps"),
        (ensemble_size, _ENSEMBLE_MIN, _ENSEMBLE_MAX, "--ensemble-size"),
        (processing_res, _RES_MIN, _RES_MAX, "--processing-res"),
    )
    for value, lo, hi, flag in checks:
        if value < lo or value > hi:
            return "ERROR: %s must be an integer in range %s..%s (got %s)" % (
                flag,
                lo,
                hi,
                value,
            )
    return None


def build_arguments(image_url, num_inference_steps, ensemble_size, processing_res):
    """Request body. processing_res 0 means the API keeps the input size."""
    return {
        "image_url": image_url,
        "num_inference_steps": int(num_inference_steps),
        "ensemble_size": int(ensemble_size),
        "processing_res": int(processing_res),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Marigold depth estimation on a still image via fal.ai."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument("--out-dir", required=True, help="Output directory for the downloaded depth map image.")
    parser.add_argument(
        "--num-inference-steps",
        type=int,
        default=_DEFAULT_STEPS,
        help="Denoising steps (2-50). Higher is slower and more accurate. Default: 10.",
    )
    parser.add_argument(
        "--ensemble-size",
        type=int,
        default=_DEFAULT_ENSEMBLE,
        help="Predictions to average (2-50). Higher is slower and more accurate. Default: 10.",
    )
    parser.add_argument(
        "--processing-res",
        type=int,
        default=_DEFAULT_RES,
        help="Max processing resolution (0-2048). 0 uses the input image size. Default: 0.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient fal backend errors (5xx/429). Default: 3.",
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

    range_error = validate_settings(
        args.num_inference_steps,
        args.ensemble_size,
        args.processing_res,
    )
    if range_error:
        print(range_error, file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-marigold-depth-helper"

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    arguments = build_arguments(
        image_url,
        args.num_inference_steps,
        args.ensemble_size,
        args.processing_res,
    )

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
            "ERROR: Marigold Depth request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    try:
        image_obj = result["image"]
        url = image_obj.get("url")
        file_name = image_obj.get("file_name")
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if not url:
        print("ERROR: no image URL in response:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 5

    ext = "png"
    if file_name:
        _, e = os.path.splitext(file_name)
        if e:
            ext = e.lstrip(".").lower() or "png"
    out_name = "depth_map.%s" % ext
    out_path = os.path.join(out_dir, out_name)

    if args.verbose:
        print("Downloading depth map -> %s" % out_path)
    download(str(url), out_path, user_agent=user_agent)

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": out_path,
        "num_inference_steps": arguments["num_inference_steps"],
        "ensemble_size": arguments["ensemble_size"],
        "processing_res": arguments["processing_res"],
    }
    emit_result_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
