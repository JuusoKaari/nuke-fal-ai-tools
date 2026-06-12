# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai BiRefNet v2 background removal on an image sequence.
# - Expands a Nuke-style sequence pattern (#### or %0Nd), uploads each frame to fal storage, calls `fal-ai/birefnet/v2`,
#   downloads the output frame(s) into a per-run output directory, and prints progress/logs to stdout.
#
# Usage (example):
#   py -3 fal_birefnet_v2_helper.py --in-pattern "C:/seq/plate.%04d.png" --first 1001 --last 1100 --out-dir "C:/proj/temp/birefnet_v2_20260224_123000"
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
import re
import sys

from fal_common import download, ensure_dir


_ENDPOINT_ID = "fal-ai/birefnet/v2"


def _infer_pad_from_pattern(pattern: str) -> int:
    m_hash = re.search(r"(#+)", pattern)
    if m_hash:
        return len(m_hash.group(1))

    m_pct = re.search(r"%0?(\d+)d", pattern)
    if m_pct:
        try:
            return int(m_pct.group(1))
        except Exception:
            return 4

    return 4


def _resolve_frame_path(pattern: str, frame: int, pad: int) -> str:
    if "#" in pattern:
        return re.sub(r"(#+)", lambda m: ("%0" + str(len(m.group(1))) + "d") % frame, pattern, count=1)

    if re.search(r"%0?\d*d", pattern):
        try:
            return pattern % frame
        except Exception:
            pass

    return pattern


def _ext_from_file_name_or_default(file_name: str | None, default_ext: str) -> str:
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext:
            return ext.lstrip(".")
    return default_ext.lstrip(".")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run BiRefNet v2 background removal on an image sequence via fal.ai and download results."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--in-pattern", required=True, help="Input image sequence pattern (#### or %0Nd).")
    parser.add_argument("--first", required=True, type=int, help="First frame (inclusive).")
    parser.add_argument("--last", required=True, type=int, help="Last frame (inclusive).")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded frames.")
    parser.add_argument(
        "--model",
        default="General Use (Light)",
        choices=[
            "General Use (Light)",
            "General Use (Light 2K)",
            "General Use (Heavy)",
            "Matting",
            "Portrait",
            "General Use (Dynamic)",
        ],
        help="BiRefNet v2 model variant.",
    )
    parser.add_argument(
        "--operating-resolution",
        default="1024x1024",
        choices=["1024x1024", "2048x2048", "2304x2304"],
        help="Operating resolution (higher is more accurate but slower).",
    )
    parser.add_argument("--output-mask", action="store_true", default=False, help="Also download the mask image.")
    parser.add_argument(
        "--refine-foreground",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refine the foreground using the estimated mask.",
    )
    parser.add_argument(
        "--output-format",
        default="png",
        choices=["png", "webp", "gif"],
        help="Output format for the composited image.",
    )
    parser.add_argument(
        "--pad",
        type=int,
        default=None,
        help="Frame padding for output filenames. If omitted, inferred from input pattern (default 4).",
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

    pattern = os.path.normpath(args.in_pattern)
    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    first = int(args.first)
    last = int(args.last)
    if last < first:
        print("ERROR: invalid frame range: first=%d last=%d" % (first, last), file=sys.stderr)
        return 2

    pad = int(args.pad) if args.pad is not None else _infer_pad_from_pattern(pattern)
    user_agent = "nuke-fal-birefnet-v2-helper"

    client = fal_client.SyncClient(key=fal_key)

    mask_dir = os.path.join(out_dir, "mask")
    if args.output_mask:
        ensure_dir(mask_dir)

    for frame in range(first, last + 1):
        in_path = _resolve_frame_path(pattern, frame, pad)
        in_path = os.path.abspath(in_path)

        if not os.path.isfile(in_path):
            print("ERROR: missing input frame: %s" % in_path, file=sys.stderr)
            return 5

        if args.verbose:
            print("Frame %d: upload %s" % (frame, in_path))

        image_url = client.upload_file(in_path)

        if args.verbose:
            print("Frame %d: submit %s" % (frame, _ENDPOINT_ID))

        result = client.subscribe(
            _ENDPOINT_ID,
            arguments={
                "image_url": image_url,
                "model": args.model,
                "operating_resolution": args.operating_resolution,
                "output_mask": bool(args.output_mask),
                "refine_foreground": bool(args.refine_foreground),
                "output_format": args.output_format,
            },
        )

        try:
            image_out_url = result["image"]["url"]
            image_file_name = result["image"].get("file_name")
        except Exception:
            print(
                "ERROR: unexpected response shape on frame %d:\n%s"
                % (frame, json.dumps(result, indent=2)),
                file=sys.stderr,
            )
            return 4

        image_ext = _ext_from_file_name_or_default(image_file_name, args.output_format)
        out_path = os.path.join(out_dir, ("frame_%0" + str(pad) + "d.%s") % (frame, image_ext))

        if args.verbose:
            print("Frame %d: download image -> %s" % (frame, out_path))

        download(image_out_url, out_path, user_agent=user_agent)

        if args.output_mask and result.get("mask_image"):
            try:
                mask_out_url = result["mask_image"]["url"]
                mask_file_name = result["mask_image"].get("file_name")
            except Exception:
                mask_out_url = None
                mask_file_name = None

            if mask_out_url:
                mask_ext = _ext_from_file_name_or_default(mask_file_name, "png")
                mask_path = os.path.join(mask_dir, ("mask_%0" + str(pad) + "d.%s") % (frame, mask_ext))
                if args.verbose:
                    print("Frame %d: download mask -> %s" % (frame, mask_path))
                download(mask_out_url, mask_path, user_agent=user_agent)

    print(
        json.dumps(
            {
                "ok": True,
                "endpoint": _ENDPOINT_ID,
                "first": first,
                "last": last,
                "out_dir": out_dir,
                "output_format": args.output_format,
                "pad": pad,
                "mask_dir": mask_dir if args.output_mask else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

