# Purpose:
# - Runner for the Nuke Group node `SAM_3_1_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts upstream video on input 0; uses Read file when possible, otherwise pre-renders to a temp mp4/mov.
# - Calls `fal_sam_3_1_video_helper.py` (Python 3) via subprocess, then adds a Read for the
#   result movie (DWAB EXR sequence by default; MP4/WebM if chosen in Settings).
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3).

from __future__ import print_function

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_video_output_v1 as video_out

_OUTPUT_TYPE_MP4 = "X264 (.mp4)"
_OUTPUT_TYPE_WEBM = "VP9 (.webm)"
_OUTPUT_TYPE_CHOICES = (_OUTPUT_TYPE_MP4, _OUTPUT_TYPE_WEBM)


def _enum_knob_str(g, knob_name, choices, default):
    try:
        k = g.knob(knob_name)
        v = k.value()
        if isinstance(v, int):
            if 0 <= v < len(choices):
                return choices[v]
            return default
        s = (str(v) or default).strip()
        return s if s in choices else default
    except Exception:
        return default


def _float_knob(g, knob_name, default, lo=None, hi=None):
    try:
        v = float(g.knob(knob_name).value())
    except Exception:
        return default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _int_knob(g, knob_name, default, lo=None):
    try:
        v = int(g.knob(knob_name).value())
    except Exception:
        return default
    if lo is not None and v < lo:
        v = lo
    return v


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        nuke.message("Input 0 (source_video) is not connected.")
        raise Exception("missing input 0")

    prompt = ""
    try:
        prompt = (g.knob("prompt").value() or "").strip()
    except Exception:
        prompt = ""
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    apply_mask = True
    try:
        apply_mask = bool(g.knob("apply_mask").value())
    except Exception:
        apply_mask = True

    detection_threshold = _float_knob(g, "detection_threshold", 0.5, lo=0.0, hi=1.0)
    max_objects = _int_knob(g, "max_objects", 16, lo=1)
    output_type = _enum_knob_str(g, "output_type", _OUTPUT_TYPE_CHOICES, _OUTPUT_TYPE_MP4)
    out_ext = "webm" if output_type == _OUTPUT_TYPE_WEBM else "mp4"

    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="sam_3_1_video",
        group_node=g,
    )

    try:
        video_path = prerender.prepare_video_input_path(
            nuke_module=nuke,
            src_node=src_video_node,
            frame=frame,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="source_video",
        )
    except Exception as e:
        nuke.message("Failed to prepare source video:\n%s" % str(e))
        raise

    out_path = os.path.join(out_dir, "sam_3_1_video_%s.%s" % (ts, out_ext))

    extra_args = [
        "--video",
        video_path,
        "--prompt",
        prompt,
        "--out",
        out_path,
        "--detection-threshold",
        str(detection_threshold),
        "--max-objects",
        str(int(max_objects)),
        "--output-type",
        output_type,
        "--verbose",
    ]
    if apply_mask:
        extra_args += ["--apply-mask"]
    else:
        extra_args += ["--no-apply-mask"]

    runner_util.run_group_helper(
        nuke, g, extra_args, "SAM 3.1 Video"
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "SAM 3.1 Video", "%s_result_%s" % (g.name(), ts)
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("SAM 3.1 Video output created:\n%s" % display_path)


if __name__ == "__main__":
    main()
