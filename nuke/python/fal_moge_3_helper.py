# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to run fal.ai MoGe-3 on a still.
# - Downloads the textured GLB, converts it to OBJ for ReadGeo, and reports a
#   Nuke Camera2 (focal length, apertures, window translate) from the returned
#   FOV and normalized intrinsics. Depth, normals, and the point cloud are not
#   downloaded. The mesh is already in camera space (Y up, scene toward -Z).
#
# Usage (example):
#   py -3 fal_moge_3_helper.py --image "C:/in.png" --out-dir "C:/temp/run" --verbose
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.
#
# Model: https://fal.ai/models/microsoft/moge-3

from __future__ import annotations

import argparse
import math
import os
import sys

from fal_common import (
    download,
    emit_result_summary,
    ensure_dir,
    format_fal_error_summary,
    subscribe_with_retry,
)
from fal_glb_to_obj import glb_to_obj

_ENDPOINT_ID = "microsoft/moge-3"
# Nuke Camera2 default horizontal film back, in millimetres.
_HAPERTURE_MM = 24.576
_NEAR = 0.001
_FAR = 10000.0
_RES_MIN = 0
_RES_MAX = 9
_REFINE_MIN = 0
_REFINE_MAX = 20
_EDGE_MIN = 0.0
_EDGE_MAX = 1.0


def validate_settings(resolution_level, num_refinement_steps, edge_threshold, fov_x):
    """Return an error string when a knob is outside the accepted range, else None."""
    if resolution_level < _RES_MIN or resolution_level > _RES_MAX:
        return "ERROR: --resolution-level must be an integer in range %d..%d (got %s)" % (
            _RES_MIN,
            _RES_MAX,
            resolution_level,
        )
    if num_refinement_steps < _REFINE_MIN or num_refinement_steps > _REFINE_MAX:
        return "ERROR: --num-refinement-steps must be an integer in range %d..%d (got %s)" % (
            _REFINE_MIN,
            _REFINE_MAX,
            num_refinement_steps,
        )
    if edge_threshold < _EDGE_MIN or edge_threshold > _EDGE_MAX:
        return "ERROR: --edge-threshold must be in range %s..%s (got %s)" % (
            _EDGE_MIN,
            _EDGE_MAX,
            edge_threshold,
        )
    if fov_x is not None and (fov_x <= 0.0 or fov_x >= 180.0):
        return "ERROR: --fov-x must be between 0 and 180 degrees (got %s)" % fov_x
    return None


def build_arguments(image_url, resolution_level, num_refinement_steps, edge_threshold, apply_mask, fov_x):
    """Request body. export_ply stays off: the point cloud is not part of this node."""
    arguments = {
        "image_url": image_url,
        "resolution_level": int(resolution_level),
        "num_refinement_steps": int(num_refinement_steps),
        "edge_threshold": float(edge_threshold),
        "apply_mask": bool(apply_mask),
        "export_glb": True,
        "export_ply": False,
    }
    if fov_x is not None:
        arguments["fov_x"] = float(fov_x)
    return arguments


def _principal_point(intrinsics):
    """Return (cx, cy) in 0-1 image fractions, or None when the matrix is not normalized."""
    if not isinstance(intrinsics, list) or len(intrinsics) < 2:
        return None
    row0 = intrinsics[0]
    row1 = intrinsics[1]
    if not isinstance(row0, list) or not isinstance(row1, list):
        return None
    if len(row0) < 3 or len(row1) < 3:
        return None
    try:
        cx = float(row0[2])
        cy = float(row1[2])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(cx) and math.isfinite(cy)):
        return None
    # Pixel intrinsics (cx around 960) are not the normalized matrix fal documents.
    if cx < -0.25 or cx > 1.25 or cy < -0.25 or cy > 1.25:
        return None
    return cx, cy


def nuke_camera_from_fov(fov_x_deg, fov_y_deg, intrinsics=None):
    """
    Camera2 numbers that match MoGe's lens.

    fov = 2 * atan(aperture / (2 * focal)), with haperture fixed at Nuke's
    default 24.576 mm. vaperture is then solved from fov_y.

    win_translate is a fraction of the film back: 1.0 shifts the projection by
    half the frame. MoGe's principal point uses a top-left origin, so
    win_x = -2 * (cx - 0.5) and win_y = 2 * (cy - 0.5).
    """
    fov_x = math.radians(float(fov_x_deg))
    fov_y = math.radians(float(fov_y_deg))
    if not (0.0 < fov_x < math.pi and 0.0 < fov_y < math.pi):
        raise ValueError("FOV must be between 0 and 180 degrees")
    focal = _HAPERTURE_MM / (2.0 * math.tan(fov_x / 2.0))
    vaperture = 2.0 * focal * math.tan(fov_y / 2.0)
    win_x = 0.0
    win_y = 0.0
    point = _principal_point(intrinsics)
    if point is not None:
        cx, cy = point
        win_x = -2.0 * (cx - 0.5)
        win_y = 2.0 * (cy - 0.5)
    return {
        "focal": focal,
        "haperture": _HAPERTURE_MM,
        "vaperture": vaperture,
        "win_translate": [win_x, win_y],
        "near": _NEAR,
        "far": _FAR,
    }


def _file_url(obj):
    if not isinstance(obj, dict):
        return None
    url = obj.get("url")
    if not url:
        return None
    return str(url)


def _parse_fov_x(text):
    raw = (text or "").strip()
    if not raw:
        return None
    return float(raw)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run MoGe-3 on a still via fal.ai, convert the GLB to OBJ, and report a Nuke camera."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--image", required=True, help="Path to the local input still.")
    parser.add_argument("--out-dir", required=True, help="Output directory for the OBJ, MTL, and texture.")
    parser.add_argument(
        "--resolution-level",
        type=int,
        default=_RES_MAX,
        help="Processing resolution level 0-9. Higher is finer and slower. Default: 9.",
    )
    parser.add_argument(
        "--num-refinement-steps",
        type=int,
        default=3,
        help="Sparse refinement passes. 0 skips the refiner. Default: 3.",
    )
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=0.04,
        help="Depth-edge removal. Smaller removes more edges. Default: 0.04.",
    )
    parser.add_argument(
        "--fov-x",
        default=None,
        help="Known horizontal FOV in degrees. Omit to let MoGe estimate it.",
    )
    parser.add_argument(
        "--apply-mask",
        action="store_true",
        default=True,
        help="Mask out sky and uncertain regions. Default: on.",
    )
    parser.add_argument(
        "--no-apply-mask",
        action="store_false",
        dest="apply_mask",
        help="Keep unmasked geometry, including background.",
    )
    parser.add_argument("--max-retries", type=int, default=3, help="Retries for transient fal errors. Default: 3.")
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base backoff seconds for retries. Default: 2.0.",
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

    try:
        fov_x = _parse_fov_x(args.fov_x)
    except ValueError:
        print("ERROR: --fov-x must be a number of degrees, or omitted.", file=sys.stderr)
        return 2

    range_error = validate_settings(
        args.resolution_level,
        args.num_refinement_steps,
        args.edge_threshold,
        fov_x,
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
    user_agent = "nuke-fal-moge-3-helper"

    if args.verbose:
        print("Uploading image: %s" % image_path)
    image_url = client.upload_file(image_path)
    arguments = build_arguments(
        image_url,
        args.resolution_level,
        args.num_refinement_steps,
        args.edge_threshold,
        args.apply_mask,
        fov_x,
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
            "ERROR: MoGe-3 request failed.\n%s" % format_fal_error_summary(e),
            file=sys.stderr,
        )
        return 5

    if not isinstance(result, dict):
        print("ERROR: unexpected response shape.", file=sys.stderr)
        return 4

    mesh_url = _file_url(result.get("model_mesh"))
    if not mesh_url:
        print("ERROR: response did not include model_mesh. export_glb was requested.", file=sys.stderr)
        return 4

    glb_path = os.path.join(out_dir, "model.glb")
    if args.verbose:
        print("Downloading mesh -> %s" % glb_path)
    download(mesh_url, glb_path, user_agent=user_agent)

    try:
        converted = glb_to_obj(glb_path, out_dir)
    except Exception as e:
        print("ERROR: could not convert GLB to OBJ: %s" % e, file=sys.stderr)
        print("GLB kept at: %s" % glb_path, file=sys.stderr)
        return 4

    try:
        fov_x_out = float(result.get("fov_x"))
        fov_y_out = float(result.get("fov_y"))
        camera = nuke_camera_from_fov(fov_x_out, fov_y_out, result.get("intrinsics"))
    except (TypeError, ValueError) as e:
        print("ERROR: response camera FOV could not be read: %s" % e, file=sys.stderr)
        return 4

    summary = {
        "ok": True,
        "endpoint": _ENDPOINT_ID,
        "out_dir": out_dir,
        "downloaded": converted["obj"],
        "glb": os.path.abspath(glb_path),
        "obj": converted["obj"],
        "mtl": converted["mtl"],
        "texture": converted["texture"],
        "triangles": converted["triangles"],
        "fov_x": fov_x_out,
        "fov_y": fov_y_out,
        "intrinsics": result.get("intrinsics"),
        "camera": camera,
        "resolution_level": arguments["resolution_level"],
        "num_refinement_steps": arguments["num_refinement_steps"],
        "apply_mask": arguments["apply_mask"],
        "export_ply": False,
    }
    if fov_x is not None:
        summary["fov_x_sent"] = fov_x
    emit_result_summary(summary, result_path=converted["obj"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
