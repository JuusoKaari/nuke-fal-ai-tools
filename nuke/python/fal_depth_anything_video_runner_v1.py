# Purpose:
# - Runner for the Nuke Group node `Depth_Anything_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts upstream video on input 0; uses Read file when possible, otherwise pre-renders to a temp mp4/mov.
# - Calls `fal_depth_anything_video_helper.py` (Python 3) via subprocess, then adds a Read for the
#   depth movie (DWAB EXR sequence by default; MP4 if chosen in Settings).
# - The helper also writes a raw float .npz next to that MP4. This runner does not load it.
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

_MODEL_CHOICES = ("VDA-Small", "VDA-Base", "VDA-Large")
_COLORMAP_CHOICES = ("grayscale", "turbo", "inferno", "magma", "viridis")
_RESOLUTION_CHOICES = ("auto", "360p", "480p", "720p", "1080p")


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

    model = _enum_knob_str(g, "model", _MODEL_CHOICES, "VDA-Large")
    colormap = _enum_knob_str(g, "colormap", _COLORMAP_CHOICES, "grayscale")
    resolution = _enum_knob_str(g, "resolution", _RESOLUTION_CHOICES, "auto")
    side_by_side = False
    try:
        side_by_side = bool(g.knob("side_by_side").value())
    except Exception:
        side_by_side = False

    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="depth_anything_video",
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

    out_path = os.path.join(out_dir, "depth_anything_video_%s.mp4" % ts)

    extra_args = [
        "--video",
        video_path,
        "--out",
        out_path,
        "--model",
        model,
        "--colormap",
        colormap,
        "--resolution",
        resolution,
        "--verbose",
    ]
    if side_by_side:
        extra_args.append("--side-by-side")

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, "Depth Anything Video"
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "Depth Anything Video", "%s_result_%s" % (g.name(), ts)
    )

    raw_path = os.path.splitext(out_path)[0] + ".npz"
    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message(
            "Depth Anything Video output created:\n%s\n\nRaw depths (not loaded in Nuke):\n%s"
            % (display_path, prerender.norm_slashes(raw_path))
        )


if __name__ == "__main__":
    main()
