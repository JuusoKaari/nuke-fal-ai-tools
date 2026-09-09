# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to upscale a still via fal.ai Topaz Precision.
# - Uploads a local image, calls `topaz/upscale/image/precision`, downloads the result.
#
# API: https://fal.ai/models/fal-ai/topaz/upscale/image/precision
#
# Usage (example):
#   py -3 fal_topaz_upscale_image_precision_helper.py --image "C:/in.png" --out-dir "C:/temp/run" --verbose
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

_ENDPOINT_ID = "topaz/upscale/image/precision"

_MODEL_CHOICES = (
    "Standard V2",
    "High Fidelity V3",
    "High Fidelity V2",
    "Low Resolution V2",
    "CGI",
    "Text Refine",
)
_OUTPUT_FORMAT_CHOICES = ("jpeg", "png")
_SUBJECT_DETECTION_CHOICES = ("All", "Foreground", "Background")


def _ext_from_file_name_or_default(file_name: str | None, default_ext: str) -> str:
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext:
            return ext.lstrip(".").lower() or default_ext
    return default_ext.lstrip(".").lower()


def _in_range(value: float, lo: float, hi: float, flag: str) -> str | None:
    if value < lo or value > hi:
        return "ERROR: %s must be in range %s..%s" % (flag, lo, hi)
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Upscale a still image using fal.ai Topaz Precision and download the result."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument("--out-dir", required=True, help="Output directory for the downloaded upscaled image.")
    parser.add_argument(
        "--model",
        default="Standard V2",
        choices=_MODEL_CHOICES,
        help="Precision upscaling model. Default: Standard V2.",
    )
    parser.add_argument(
        "--upscale-factor",
        type=float,
        default=2.0,
        help="Factor to upscale width and height (1-4). Default: 2.",
    )
    parser.add_argument(
        "--output-format",
        default="png",
        choices=_OUTPUT_FORMAT_CHOICES,
        help="Output format. Default: png (Nuke stills; API default is jpeg).",
    )
    parser.add_argument(
        "--crop-to-fill",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Crop the result to fill. Default: off.",
    )
    parser.add_argument(
        "--subject-detection",
        default="All",
        choices=_SUBJECT_DETECTION_CHOICES,
        help="Subject detection mode. Default: All.",
    )
    parser.add_argument(
        "--face-enhancement",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply face enhancement. Default: on.",
    )
    parser.add_argument(
        "--face-enhancement-creativity",
        type=float,
        default=0.0,
        help="Face enhancement creativity (0-1). Ignored if face enhancement is off. Default: 0.",
    )
    parser.add_argument(
        "--face-enhancement-strength",
        type=float,
        default=0.8,
        help="Face enhancement strength (0-1). Ignored if face enhancement is off. Default: 0.8.",
    )
    parser.add_argument(
        "--sharpen",
        type=float,
        default=None,
        help="Optional sharpening (0-1). Omit to use the model default.",
    )
    parser.add_argument(
        "--denoise",
        type=float,
        default=None,
        help="Optional denoising (0-1). Omit to use the model default.",
    )
    parser.add_argument(
        "--fix-compression",
        type=float,
        default=None,
        help="Optional compression-artifact removal (0-1). Not supported by CGI. Omit for model default.",
    )
    parser.add_argument(
        "--strength",
        type=float,
        default=None,
        help="Optional enhancement strength (0.01-1). Text Refine model only.",
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

    for err in (
        _in_range(args.upscale_factor, 1.0, 4.0, "--upscale-factor"),
        _in_range(args.face_enhancement_creativity, 0.0, 1.0, "--face-enhancement-creativity"),
        _in_range(args.face_enhancement_strength, 0.0, 1.0, "--face-enhancement-strength"),
    ):
        if err:
            print(err, file=sys.stderr)
            return 2
    if args.sharpen is not None:
        err = _in_range(args.sharpen, 0.0, 1.0, "--sharpen")
        if err:
            print(err, file=sys.stderr)
            return 2
    if args.denoise is not None:
        err = _in_range(args.denoise, 0.0, 1.0, "--denoise")
        if err:
            print(err, file=sys.stderr)
            return 2
    if args.fix_compression is not None:
        err = _in_range(args.fix_compression, 0.0, 1.0, "--fix-compression")
        if err:
            print(err, file=sys.stderr)
            return 2
    if args.strength is not None:
        err = _in_range(args.strength, 0.01, 1.0, "--strength")
        if err:
            print(err, file=sys.stderr)
            return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-topaz-upscale-image-precision-helper"

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)

    arguments: dict = {
        "image_url": image_url,
        "model": args.model,
        "upscale_factor": float(args.upscale_factor),
        "crop_to_fill": bool(args.crop_to_fill),
        "output_format": args.output_format,
        "subject_detection": args.subject_detection,
        "face_enhancement": bool(args.face_enhancement),
        "face_enhancement_creativity": float(args.face_enhancement_creativity),
        "face_enhancement_strength": float(args.face_enhancement_strength),
    }
    if args.sharpen is not None:
        arguments["sharpen"] = float(args.sharpen)
    if args.denoise is not None:
        arguments["denoise"] = float(args.denoise)
    if args.fix_compression is not None:
        arguments["fix_compression"] = float(args.fix_compression)
    if args.strength is not None:
        arguments["strength"] = float(args.strength)

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
            "ERROR: Topaz Precision upscale request failed.\n%s"
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

    default_ext = "jpg" if args.output_format == "jpeg" else args.output_format
    ext = _ext_from_file_name_or_default(file_name, default_ext)
    out_path = os.path.join(out_dir, "upscaled.%s" % ext)

    if args.verbose:
        print("Downloading upscaled image -> %s" % out_path)
    download(str(url), out_path, user_agent=user_agent)

    emit_result_summary(
        {
            "ok": True,
            "endpoint": _ENDPOINT_ID,
            "out_dir": out_dir,
            "downloaded": out_path,
            "model": args.model,
            "upscale_factor": args.upscale_factor,
            "output_format": args.output_format,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
