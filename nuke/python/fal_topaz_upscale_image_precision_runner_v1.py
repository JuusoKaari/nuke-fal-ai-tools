# Purpose:
# - Runner for the Nuke Group node `Topaz_Upscale_Image_Precision_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream still on input 0; uses a Read file directly when possible, otherwise pre-renders.
# - Calls `fal_topaz_upscale_image_precision_helper.py` (Python 3) via subprocess, then spawns a Read
#   for the downloaded upscaled still.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_spawn_read_position_v1 as spawn_pos

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


def _enum_knob_str(group_node, knob_name, choices, default):
    try:
        k = group_node.knob(knob_name)
        v = k.value()
        if isinstance(v, int):
            if 0 <= v < len(choices):
                return choices[v]
            return default
        s = (str(v) or default).strip()
        return s if s in choices else default
    except Exception:
        return default


def _float_knob(group_node, knob_name, default, lo=None, hi=None):
    try:
        v = float(group_node.knob(knob_name).value())
    except Exception:
        return default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _optional_float_knob(group_node, knob_name):
    try:
        raw = group_node.knob(knob_name).value()
    except Exception:
        return None
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _find_output_path(out_dir, output_format):
    fmt = (output_format or "png").strip().lower()
    preferred = "jpg" if fmt == "jpeg" else fmt
    names = [
        "upscaled.%s" % preferred,
        "upscaled.png",
        "upscaled.jpg",
        "upscaled.jpeg",
        "upscaled.webp",
    ]
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        path = os.path.join(out_dir, name)
        if os.path.isfile(path):
            return path
    return None


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 (source_image) is not connected.")
        raise Exception("missing input 0")

    model = _enum_knob_str(g, "model", _MODEL_CHOICES, "Standard V2")
    upscale_factor = _float_knob(g, "upscale_factor", 2.0, lo=1.0, hi=4.0)
    output_format = _enum_knob_str(g, "output_format", _OUTPUT_FORMAT_CHOICES, "png")
    subject_detection = _enum_knob_str(g, "subject_detection", _SUBJECT_DETECTION_CHOICES, "All")
    crop_to_fill = bool(g.knob("crop_to_fill").value())
    face_enhancement = bool(g.knob("face_enhancement").value())
    face_creativity = _float_knob(g, "face_enhancement_creativity", 0.0, lo=0.0, hi=1.0)
    face_strength = _float_knob(g, "face_enhancement_strength", 0.8, lo=0.0, hi=1.0)
    sharpen = _optional_float_knob(g, "sharpen")
    denoise = _optional_float_knob(g, "denoise")
    fix_compression = _optional_float_knob(g, "fix_compression")
    strength = _optional_float_knob(g, "strength")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="topaz_upscale_image_precision",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
    except Exception as e:
        nuke.message("Failed to prepare input image:\n%s" % str(e))
        raise

    extra_args = [
        "--image",
        image_path,
        "--out-dir",
        out_dir,
        "--model",
        model,
        "--upscale-factor",
        str(upscale_factor),
        "--output-format",
        output_format,
        "--subject-detection",
        subject_detection,
        "--face-enhancement-creativity",
        str(face_creativity),
        "--face-enhancement-strength",
        str(face_strength),
        "--verbose",
    ]
    if crop_to_fill:
        extra_args += ["--crop-to-fill"]
    else:
        extra_args += ["--no-crop-to-fill"]
    if face_enhancement:
        extra_args += ["--face-enhancement"]
    else:
        extra_args += ["--no-face-enhancement"]
    if sharpen is not None:
        extra_args += ["--sharpen", str(sharpen)]
    if denoise is not None:
        extra_args += ["--denoise", str(denoise)]
    if fix_compression is not None:
        extra_args += ["--fix-compression", str(fix_compression)]
    if strength is not None:
        extra_args += ["--strength", str(strength)]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Image upscale (Topaz Precision)'
    )

    out_path = _find_output_path(out_dir, output_format)
    if not out_path:
        nuke.message("Helper finished, but no output image found in:\n%s" % out_dir)
        raise Exception("no output")

    out_path_nk = prerender.norm_slashes(out_path)
    xpos = int(g.xpos())
    ypos = int(g.ypos())

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        r = nuke.nodes.Read(file=out_path_nk)
        try:
            r.setName("%s_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("Topaz Precision\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Topaz Precision output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
