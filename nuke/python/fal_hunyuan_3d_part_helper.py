# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Hunyuan 3D Part Splitter.
# - Uploads a local FBX, calls `fal-ai/hunyuan-3d/v3.1/part`, downloads each
#   result_files FBX into one output folder.
#
# Usage (example):
#   py -3 fal_hunyuan_3d_part_helper.py --input-file "C:/in.fbx" --out-dir "C:/temp/run" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model: https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/part

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

_ENDPOINT_ID = "fal-ai/hunyuan-3d/v3.1/part"
_MAX_INPUT_BYTES = 100 * 1024 * 1024
_FBX_EXT = ".fbx"


def _file_obj_url(obj) -> tuple[str | None, str | None]:
    if not isinstance(obj, dict):
        return None, None
    return obj.get("url"), obj.get("file_name")


def _download_file_obj(obj, out_path: str, user_agent: str, verbose: bool) -> str | None:
    url, _file_name = _file_obj_url(obj)
    if not url:
        return None
    if verbose:
        print("Downloading -> %s" % out_path)
    download(str(url), out_path, user_agent=user_agent)
    return out_path


def _validate_input_fbx(path: str) -> str | None:
    if not os.path.isfile(path):
        return "input FBX not found: %s" % path
    ext = os.path.splitext(path)[1].lower()
    if ext != _FBX_EXT:
        return "input must be an FBX file (got %s)" % (ext or "no extension")
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return "could not read input FBX size: %s" % exc
    if size > _MAX_INPUT_BYTES:
        return "input FBX is larger than 100MB (%d bytes)" % size
    return None


def _part_out_path(file_obj, out_dir: str, index: int, used_names: set[str]) -> str:
    file_name = None
    if isinstance(file_obj, dict):
        raw = file_obj.get("file_name")
        if raw:
            file_name = os.path.basename(str(raw))
    if not file_name:
        file_name = "part_%d.fbx" % index
    root, ext = os.path.splitext(file_name)
    if ext.lower() != _FBX_EXT:
        file_name = (root or "part_%d" % index) + _FBX_EXT
        root, ext = os.path.splitext(file_name)
    candidate = file_name
    n = 1
    while candidate.lower() in used_names:
        candidate = "%s_%d%s" % (root, n, ext or _FBX_EXT)
        n += 1
    used_names.add(candidate.lower())
    return os.path.join(out_dir, candidate)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Split an FBX into parts via fal.ai Hunyuan 3D Part and download the FBX files."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--input-file", required=True, help="Path to local input FBX (max 100MB).")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded part FBX files.")
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

    input_path = os.path.abspath(args.input_file)
    err = _validate_input_fbx(input_path)
    if err:
        print("ERROR: %s" % err, file=sys.stderr)
        return 2

    out_dir = os.path.abspath(args.out_dir)
    ensure_dir(out_dir)

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-hunyuan-3d-part-helper"

    if args.verbose:
        print("Uploading FBX: %s" % input_path)
    input_file_url = client.upload_file(input_path)

    arguments = {"input_file_url": input_file_url}

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
            "ERROR: Hunyuan 3D Part request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    result_files = result.get("result_files") if isinstance(result, dict) else None
    if not isinstance(result_files, list) or not result_files:
        print("ERROR: no result_files in response:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    parts = []
    used_names = set()
    for index, file_obj in enumerate(result_files):
        out_path = _part_out_path(file_obj, out_dir, index, used_names)
        saved = _download_file_obj(file_obj, out_path, user_agent, args.verbose)
        if saved:
            parts.append(saved)

    if not parts:
        print("ERROR: result_files had no downloadable FBX URLs.", file=sys.stderr)
        return 4

    downloaded = {"parts": parts}
    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": downloaded,
        "part_count": len(parts),
    }
    emit_result_summary(summary, result_path=parts[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
