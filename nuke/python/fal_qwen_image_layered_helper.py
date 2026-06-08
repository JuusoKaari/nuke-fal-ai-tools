# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Qwen Image Layered on a single still image.
# - Decomposes the image into multiple RGBA layers via fal-ai/qwen-image-layered.
# - Uploads the image to fal storage, downloads output layers into per-layer subdirs (layer_0/, layer_1/, ...),
#   and prints progress.
#
# Usage (example):
#   py -3 fal_qwen_image_layered_helper.py --image "C:/in.png" --out-dir "C:/proj/temp/qwen_layered_20260224_123000"
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

from fal_common import download, ensure_dir


_ENDPOINT_ID = "fal-ai/qwen-image-layered"


def _ext_from_file_name_or_default(file_name: str | None, default_ext: str) -> str:
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext:
            return ext.lstrip(".")
    return default_ext.lstrip(".")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Qwen Image Layered (decompose image into RGBA layers) on a still image via fal.ai."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local input still image (png/jpg/webp).")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded layer images.")
    parser.add_argument("--prompt", default="", help="Optional prompt for the input image.")
    parser.add_argument("--negative-prompt", default="", help="Optional negative prompt.")
    parser.add_argument(
        "--num-layers",
        type=int,
        default=4,
        choices=range(1, 11),
        metavar="1-10",
        help="Number of layers to generate (default 4).",
    )
    parser.add_argument(
        "--num-inference-steps",
        type=int,
        default=28,
        help="Number of inference steps (1-50, default 28).",
    )
    parser.add_argument(
        "--guidance-scale",
        type=float,
        default=5.0,
        help="Guidance scale (1-20, default 5).",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducibility.")
    parser.add_argument(
        "--output-format",
        default="png",
        choices=["png", "webp"],
        help="Output format for layers.",
    )
    parser.add_argument(
        "--acceleration",
        default="regular",
        choices=["none", "regular", "high"],
        help="Acceleration level (default regular).",
    )
    parser.add_argument(
        "--enable-safety-checker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable safety checker.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more logs.")
    args = parser.parse_args(argv)

    fal_key = args.fal_key or os.environ.get("FAL_KEY")
    if not fal_key:
        print("ERROR: missing FAL key. Provide --fal-key or set FAL_KEY env var.", file=sys.stderr)
        return 2

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    in_path = os.path.abspath(args.image)
    if not os.path.isfile(in_path):
        print("ERROR: missing input image: %s" % in_path, file=sys.stderr)
        return 5

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    user_agent = "nuke-fal-qwen-layered-helper"
    client = fal_client.SyncClient(key=fal_key)

    if args.verbose:
        print("Upload %s" % in_path)

    image_url = client.upload_file(in_path)

    def on_queue_update(update) -> None:
        logs = getattr(update, "logs", None)
        if not logs:
            return
        for entry in logs:
            msg = None
            try:
                msg = entry.get("message")
            except Exception:
                msg = None
            if msg:
                print(msg)

    if args.verbose:
        print("Submit %s" % _ENDPOINT_ID)

    api_args = {
        "image_url": image_url,
        "num_layers": args.num_layers,
        "num_inference_steps": args.num_inference_steps,
        "guidance_scale": args.guidance_scale,
        "enable_safety_checker": bool(args.enable_safety_checker),
        "output_format": args.output_format,
        "acceleration": args.acceleration,
        "sync_mode": False,
    }
    if args.prompt:
        api_args["prompt"] = args.prompt
    if args.negative_prompt:
        api_args["negative_prompt"] = args.negative_prompt
    if args.seed is not None:
        api_args["seed"] = args.seed

    result = client.subscribe(
        _ENDPOINT_ID,
        arguments=api_args,
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    try:
        images = result.get("images") or []
    except Exception:
        print(
            "ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2),
            file=sys.stderr,
        )
        return 4

    for layer_idx, img_info in enumerate(images):
        try:
            layer_url = img_info.get("url") if isinstance(img_info, dict) else None
            file_name = img_info.get("file_name") if isinstance(img_info, dict) else None
        except Exception:
            layer_url = None
            file_name = None

        if not layer_url:
            print("ERROR: missing layer %d url" % layer_idx, file=sys.stderr)
            return 4

        layer_dir = os.path.join(out_dir, "layer_%d" % layer_idx)
        ensure_dir(layer_dir)
        ext = _ext_from_file_name_or_default(file_name, args.output_format)
        out_path = os.path.join(layer_dir, "layer.%s" % ext)

        if args.verbose:
            print("Download layer %d -> %s" % (layer_idx, out_path))

        download(layer_url, out_path, user_agent=user_agent)

    layer_count = len(images) if images else args.num_layers
    print(
        json.dumps(
            {
                "ok": True,
                "endpoint": _ENDPOINT_ID,
                "out_dir": out_dir,
                "num_layers": layer_count,
                "output_format": args.output_format,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
