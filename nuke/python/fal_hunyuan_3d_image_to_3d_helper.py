# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai Hunyuan 3D Pro image-to-3D on a still image.
# - Uploads a local front-view image, calls `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d`,
#   downloads GLB, texture PNG, MTL, OBJ (optional), and preview thumbnail into one output folder.
#
# Usage (example):
#   py -3 fal_hunyuan_3d_image_to_3d_helper.py --image "C:/in.png" --out-dir "C:/temp/run" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model: https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/pro/image-to-3d

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

_ENDPOINT_ID = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d"
_FACE_COUNT_MIN = 40000
_FACE_COUNT_MAX = 1500000
_DEFAULT_FACE_COUNT = 100000


def _file_obj_url(obj) -> tuple[str | None, str | None]:
    if not isinstance(obj, dict):
        return None, None
    return obj.get("url"), obj.get("file_name")


def _download_file_obj(obj, out_path: str, user_agent: str, verbose: bool) -> str | None:
    url, file_name = _file_obj_url(obj)
    if not url:
        return None
    if verbose:
        print("Downloading -> %s" % out_path)
    download(str(url), out_path, user_agent=user_agent)
    return out_path


def _out_path_for_model_url(key: str, file_obj: dict, out_dir: str) -> str:
    """Preserve API file names so OBJ/MTL texture references stay valid."""
    file_name = file_obj.get("file_name")
    if file_name:
        return os.path.join(out_dir, os.path.basename(str(file_name)))
    defaults = {
        "texture": "texture.png",
        "mtl": "material.mtl",
        "obj": "model.obj",
        "glb": "model.glb",
        "fbx": "model.fbx",
        "usdz": "model.usdz",
    }
    return os.path.join(out_dir, defaults.get(key, "%s.bin" % key))


def _download_model_urls(
    model_urls: dict,
    out_dir: str,
    user_agent: str,
    verbose: bool,
    keys: tuple[str, ...],
    downloaded: dict[str, str],
    skip_if_exists: bool = True,
) -> None:
    for key in keys:
        file_obj = model_urls.get(key)
        if not isinstance(file_obj, dict):
            continue
        out_path = _out_path_for_model_url(key, file_obj, out_dir)
        if skip_if_exists and os.path.isfile(out_path):
            downloaded[key] = out_path
            continue
        saved = _download_file_obj(file_obj, out_path, user_agent, verbose)
        if saved:
            downloaded[key] = saved


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run Hunyuan 3D Pro image-to-3D on a still image via fal.ai and download model files."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to local front-view input image (png/jpg/webp).")
    parser.add_argument("--out-dir", required=True, help="Output directory for downloaded model files.")
    parser.add_argument(
        "--face-count",
        type=int,
        default=_DEFAULT_FACE_COUNT,
        help="Target polygon face count (%d..%d). Default: %d."
        % (_FACE_COUNT_MIN, _FACE_COUNT_MAX, _DEFAULT_FACE_COUNT),
    )
    parser.add_argument(
        "--generate-type",
        default="Normal",
        choices=["Normal", "Geometry"],
        help='Generation type: "Normal" (textured) or "Geometry" (white mesh, no textures). Default: Normal.',
    )
    parser.add_argument(
        "--enable-pbr",
        action="store_true",
        help="Enable PBR material generation (metallic, roughness, normal). Ignored for Geometry.",
    )
    parser.add_argument(
        "--download-obj",
        action="store_true",
        default=True,
        help="Also download OBJ/FBX/USDZ from model_urls when available. Default: on.",
    )
    parser.add_argument(
        "--no-download-obj",
        action="store_false",
        dest="download_obj",
        help="Skip extra mesh formats (GLB + texture/MTL still downloaded).",
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

    face_count = int(args.face_count)
    if face_count < _FACE_COUNT_MIN or face_count > _FACE_COUNT_MAX:
        print(
            "ERROR: face_count must be between %d and %d (got %d)."
            % (_FACE_COUNT_MIN, _FACE_COUNT_MAX, face_count),
            file=sys.stderr,
        )
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
    user_agent = "nuke-fal-hunyuan-3d-image-to-3d-helper"

    if args.verbose:
        print("Uploading image: %s" % image_path)
    input_image_url = client.upload_file(image_path)

    arguments = {
        "input_image_url": input_image_url,
        "generate_type": args.generate_type,
        "face_count": face_count,
    }
    if args.enable_pbr and args.generate_type != "Geometry":
        arguments["enable_pbr"] = True

    if args.verbose:
        print("Submitting request: %s" % _ENDPOINT_ID)
        print("Arguments: %s" % json.dumps({k: v for k, v in arguments.items() if k != "input_image_url"}))

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
            "ERROR: Hunyuan 3D image-to-3D request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    downloaded: dict[str, str] = {}

    glb_obj = result.get("model_glb")
    glb_path = os.path.join(out_dir, "model.glb")
    if _download_file_obj(glb_obj, glb_path, user_agent, args.verbose):
        downloaded["glb"] = glb_path

    model_urls = result.get("model_urls") if isinstance(result.get("model_urls"), dict) else {}

    if not downloaded.get("glb") and model_urls:
        glb_from_urls = model_urls.get("glb")
        if _download_file_obj(glb_from_urls, glb_path, user_agent, args.verbose):
            downloaded["glb"] = glb_path

    if not downloaded.get("glb"):
        print("ERROR: no GLB model in response:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    # Texture + MTL are separate files referenced by OBJ; always fetch when present.
    if model_urls:
        _download_model_urls(
            model_urls,
            out_dir,
            user_agent,
            args.verbose,
            keys=("texture", "mtl"),
            downloaded=downloaded,
        )
        if args.download_obj:
            _download_model_urls(
                model_urls,
                out_dir,
                user_agent,
                args.verbose,
                keys=("obj", "fbx", "usdz"),
                downloaded=downloaded,
            )

    thumb_obj = result.get("thumbnail")
    preview_path = os.path.join(out_dir, "preview.png")
    if _download_file_obj(thumb_obj, preview_path, user_agent, args.verbose):
        downloaded["preview"] = preview_path

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "face_count": face_count,
        "generate_type": args.generate_type,
        "enable_pbr": bool(args.enable_pbr and args.generate_type != "Geometry"),
        "downloaded": downloaded,
        "seed": result.get("seed"),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
