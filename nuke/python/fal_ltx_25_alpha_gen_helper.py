# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to pull a video foreground matte via fal.ai.
# - Uploads a local video, calls `lightricks/ltx-2.5/alpha-gen`, and downloads one result.
#   alpha (default) is the grayscale matte MP4. rgba is the ProRes 4444 cutout MOV
#   with straight alpha. The API always returns both; this helper keeps the chosen one.
# - API reference: https://fal.ai/models/lightricks/ltx-2.5/alpha-gen
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

_ENDPOINT_ID = "lightricks/ltx-2.5/alpha-gen"

_OUTPUT_MODES = ("alpha", "rgba")
_RESULT_KEY = {"alpha": "matte_video", "rgba": "cutout_video"}
_RESULT_EXT = {"alpha": "mp4", "rgba": "mov"}


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def normalize_output_mode(mode):
    """alpha (grayscale matte) or rgba (ProRes 4444 cutout). Default alpha."""
    key = (mode or "").strip().lower().replace("-", " ").replace("_", " ")
    key = " ".join(key.split())
    if key in ("", "alpha", "alpha only"):
        return "alpha"
    if key == "rgba":
        return "rgba"
    raise ValueError("output mode must be alpha or rgba")


def result_key_for_mode(mode):
    return _RESULT_KEY[normalize_output_mode(mode)]


def expected_ext_for_mode(mode):
    return _RESULT_EXT[normalize_output_mode(mode)]


def build_arguments(video_url, enable_safety_checker):
    """Payload for lightricks/ltx-2.5/alpha-gen. video_url is required."""
    url = (video_url or "").strip()
    if not url:
        raise ValueError("video_url is required")
    return {
        "video_url": url,
        "enable_safety_checker": bool(enable_safety_checker),
    }


def _file_url(result, key):
    if not isinstance(result, dict):
        return None
    obj = result.get(key)
    if isinstance(obj, dict):
        url = obj.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
        return None
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a foreground matte or RGBA cutout from a video using fal.ai LTX 2.5 Alpha Gen."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local input video (.mp4/.mov).")
    parser.add_argument(
        "--output-mode",
        default="alpha",
        choices=_OUTPUT_MODES,
        help="alpha writes the grayscale matte MP4. rgba writes the ProRes 4444 cutout MOV. Default: alpha.",
    )
    parser.add_argument("--out", required=True, help="Path to the chosen output. .mp4 for alpha, .mov for rgba.")
    parser.add_argument(
        "--enable-safety-checker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the fal safety checker. Default: on.",
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

    video_path = os.path.abspath(args.video)
    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path))
    try:
        output_mode = normalize_output_mode(args.output_mode)
    except ValueError as e:
        print("ERROR: %s" % (e,), file=sys.stderr)
        return 2
    result_key = result_key_for_mode(output_mode)
    expected_ext = expected_ext_for_mode(output_mode)

    if not os.path.isfile(video_path):
        print("ERROR: video file not found: %s" % video_path, file=sys.stderr)
        return 2

    video_ext = _norm_ext(video_path)
    if video_ext not in {"mp4", "mov"}:
        print(
            "ERROR: video must be .mp4 or .mov for this model. Got: %s" % video_path,
            file=sys.stderr,
        )
        return 2

    if _norm_ext(out_path) != expected_ext:
        print(
            "ERROR: --out must be a .%s path when --output-mode is %s. Got: %s"
            % (expected_ext, output_mode, out_path),
            file=sys.stderr,
        )
        return 2

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-ltx-25-alpha-gen-helper"

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded video_url=%s" % video_url)

    try:
        arguments = build_arguments(video_url, args.enable_safety_checker)
    except ValueError as e:
        print("ERROR: %s" % (e,), file=sys.stderr)
        return 2

    if args.verbose:
        print("Submitting request: %s" % (_ENDPOINT_ID,))
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
            "ERROR: LTX 2.5 Alpha Gen request failed.\n%s"
            % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    out_url = _file_url(result, result_key)
    if not out_url:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if args.verbose:
        print("Downloading %s -> %s" % (output_mode, out_path))
    download(str(out_url), out_path, user_agent=user_agent)

    emit_result_summary(
        {
            "ok": True,
            "endpoint": _ENDPOINT_ID,
            "out_path": out_path,
            "out_url": out_url,
            "output_mode": output_mode,
            "enable_safety_checker": bool(args.enable_safety_checker),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
