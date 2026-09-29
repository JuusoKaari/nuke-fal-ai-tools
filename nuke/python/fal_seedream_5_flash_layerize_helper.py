# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Seedream 5.0 Flash Layerize.
# - Uploads one still, calls `bytedance/seedream/v5/flash/layerize`, and downloads the
#   base image plus separated layers into layer_0/, layer_1/, ...
# - Each layer folder gets layer.<ext> and layer_meta.json (z_index, name, description, bbox).
#
# Usage (example):
#   py -3 fal_seedream_5_flash_layerize_helper.py --image "C:/in.png" --out-dir "C:/temp/run" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model:
# - https://fal.ai/models/bytedance/seedream/v5/flash/layerize

from __future__ import annotations

import argparse
import base64
import json
import os
import struct
import sys

from fal_common import (
    download,
    emit_result_summary,
    ensure_dir,
    format_fal_error_summary,
    subscribe_with_retry,
)


_ENDPOINT_ID = "bytedance/seedream/v5/flash/layerize"
# Base image (z_index 0) plus up to 16 separated layers.
_MAX_LAYERS = 17
_IMAGE_SIZE_CHOICES = ("auto", "auto_1K", "auto_1.5K", "auto_2K")
_ENHANCE_PROMPT_MODE_CHOICES = ("standard", "fast")
_CONTENT_TYPE_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}


def _as_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _image_dict(item):
    """Return the Image object from a layer record or a flat gallery image."""
    if not isinstance(item, dict):
        return None
    nested = item.get("image")
    if isinstance(nested, dict) and nested.get("url"):
        return nested
    if item.get("url"):
        return item
    return None


def layer_file_ext(file_name, content_type, default_ext="png"):
    """Pick a file extension from file_name, then mime type."""
    if isinstance(file_name, str) and file_name.strip():
        _base, ext = os.path.splitext(file_name.strip())
        ext = ext.lstrip(".").lower()
        if ext:
            return ext
    if isinstance(content_type, str):
        mime = content_type.split(";")[0].strip().lower()
        mapped = _CONTENT_TYPE_EXT.get(mime)
        if mapped:
            return mapped
    return default_ext.lstrip(".")


def ordered_layer_records(result):
    """
    Return layer records in increasing z_index.
    Prefer `layers` (metadata). Fall back to flat `images` when layers is empty.
    """
    if not isinstance(result, dict):
        return []
    raw_layers = result.get("layers")
    raw_images = result.get("images")
    if isinstance(raw_layers, list) and raw_layers:
        source = raw_layers
    elif isinstance(raw_images, list) and raw_images:
        source = raw_images
    else:
        return []

    records = []
    for index, item in enumerate(source):
        image = _image_dict(item)
        if image is None:
            continue
        url = image.get("url")
        if not url:
            continue
        z_index = index
        name = None
        description = None
        bounding_box = None
        if isinstance(item, dict) and isinstance(item.get("image"), dict):
            parsed_z = _as_int(item.get("z_index"))
            if parsed_z is not None:
                z_index = parsed_z
            raw_name = item.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                name = raw_name.strip()
            raw_desc = item.get("description")
            if isinstance(raw_desc, str) and raw_desc.strip():
                description = raw_desc.strip()
            raw_box = item.get("bounding_box")
            if isinstance(raw_box, dict):
                bounding_box = raw_box
        records.append(
            {
                "url": str(url),
                "file_name": image.get("file_name"),
                "content_type": image.get("content_type"),
                "width": image.get("width"),
                "height": image.get("height"),
                "z_index": z_index,
                "name": name,
                "description": description,
                "bounding_box": bounding_box,
                "_order": index,
            }
        )
    records.sort(key=lambda rec: (rec["z_index"], rec["_order"]))
    return records


def _write_data_uri(data_uri: str, out_path: str) -> None:
    """Write a data:image/...;base64, payload when sync_mode returns inline bytes."""
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
    with open(out_path, "wb") as handle:
        handle.write(data)


def _png_ihdr_size(path: str):
    """Return (width, height) from a PNG header, or None."""
    try:
        with open(path, "rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            handle.read(4)
            if handle.read(4) != b"IHDR":
                return None
            width, height = struct.unpack(">II", handle.read(8))
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def _write_layer_meta(layer_dir: str, index: int, rec: dict) -> None:
    meta = {
        "index": index,
        "z_index": rec.get("z_index"),
        "name": rec.get("name"),
        "description": rec.get("description"),
        "bounding_box": rec.get("bounding_box"),
        "content_type": rec.get("content_type"),
        "width": rec.get("width"),
        "height": rec.get("height"),
        "file_name": rec.get("file_name"),
    }
    path = os.path.join(layer_dir, "layer_meta.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Decompose a still into a base image and layers via Seedream 5.0 Flash Layerize."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to the local input still (png/jpg/webp).")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded layers.")
    parser.add_argument(
        "--prompt",
        default="",
        help="Optional instructions for which elements to separate. Empty lets the model choose.",
    )
    parser.add_argument(
        "--image-size",
        default="auto",
        choices=_IMAGE_SIZE_CHOICES,
        help="Output resolution tier. Default: auto.",
    )
    parser.add_argument(
        "--enhance-prompt-mode",
        default="standard",
        choices=_ENHANCE_PROMPT_MODE_CHOICES,
        help="Prompt optimization. standard favors quality, fast is quicker. Default: standard.",
    )
    parser.add_argument(
        "--enable-safety-checker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable the safety checker. Default: true.",
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

    in_path = os.path.abspath(args.image)
    if not os.path.isfile(in_path):
        print("ERROR: missing input image: %s" % in_path, file=sys.stderr)
        return 5

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as exc:
        print(
            "ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (exc,),
            file=sys.stderr,
        )
        return 3

    user_agent = "nuke-fal-seedream-5-flash-layerize-helper"
    client = fal_client.SyncClient(key=fal_key)

    if args.verbose:
        print("Upload %s" % in_path)
    image_url = client.upload_file(in_path)

    if args.verbose:
        print("Submit %s" % _ENDPOINT_ID)

    api_args = {
        "image_url": image_url,
        "image_size": str(args.image_size),
        "enhance_prompt_mode": str(args.enhance_prompt_mode),
        "enable_safety_checker": bool(args.enable_safety_checker),
        "sync_mode": False,
    }
    prompt = (args.prompt or "").strip()
    if prompt:
        api_args["prompt"] = prompt

    try:
        result = subscribe_with_retry(
            client,
            _ENDPOINT_ID,
            api_args,
            max_retries=args.max_retries,
            retry_base_seconds=args.retry_base_seconds,
            verbose=args.verbose,
        )
    except Exception as exc:
        print(
            "ERROR: Seedream 5.0 Flash Layerize request failed.\n%s" % format_fal_error_summary(exc),
            file=sys.stderr,
        )
        return 5

    records = ordered_layer_records(result)
    if not records:
        print(
            "ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2),
            file=sys.stderr,
        )
        return 4
    if len(records) > _MAX_LAYERS:
        print(
            "WARNING: response had %d layers; keeping %d (lowest z_index)."
            % (len(records), _MAX_LAYERS),
            file=sys.stderr,
        )
        records = records[:_MAX_LAYERS]

    downloaded = []
    for index, rec in enumerate(records):
        layer_dir = os.path.join(out_dir, "layer_%d" % index)
        ensure_dir(layer_dir)
        ext = layer_file_ext(rec.get("file_name"), rec.get("content_type"))
        out_path = os.path.join(layer_dir, "layer.%s" % ext)
        if args.verbose:
            print("Download layer %d -> %s" % (index, out_path))
        url = rec["url"]
        if url.startswith("data:"):
            _write_data_uri(url, out_path)
        else:
            download(url, out_path, user_agent=user_agent)
        measured = _png_ihdr_size(out_path)
        if measured:
            if _as_int(rec.get("width")) is None:
                rec["width"] = measured[0]
            if _as_int(rec.get("height")) is None:
                rec["height"] = measured[1]
        _write_layer_meta(layer_dir, index, rec)
        downloaded.append(out_path)

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": downloaded[0],
        "num_layers": len(downloaded),
        "image_size": str(args.image_size),
        "enhance_prompt_mode": str(args.enhance_prompt_mode),
        "layers": [
            {
                "index": index,
                "z_index": rec.get("z_index"),
                "name": rec.get("name"),
                "path": path,
            }
            for index, (rec, path) in enumerate(zip(records, downloaded))
        ],
    }
    emit_result_summary(summary, result_path=downloaded[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
