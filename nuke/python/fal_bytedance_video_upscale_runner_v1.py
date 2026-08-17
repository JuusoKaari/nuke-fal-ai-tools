# Purpose:
# - Runner for the Nuke Group node `ByteDance_Video_Upscale_v1` (executes inside Nuke / Python 2.7).
# - Accepts upstream video on input 0; uses Read file when possible, otherwise pre-renders to a temp mp4/mov.
# - Calls `fal_bytedance_video_upscale_helper.py` (Python 3) via subprocess, then adds a Read for the result.
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
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos


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

    def _enum_knob_str(knob_name, choices, default):
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

    target_resolution = _enum_knob_str("target_resolution", ("1080p", "2k", "4k"), "1080p")
    target_fps = _enum_knob_str("target_fps", ("30fps", "60fps"), "30fps")

    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="bytedance_video_upscale",
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

    out_path = os.path.join(out_dir, "bytedance_video_upscale_%s.mp4" % ts)
    out_path_nk = prerender.norm_slashes(out_path)


    extra_args = [
        "--video",
        video_path,
        "--out",
        out_path,
        "--target-resolution",
        target_resolution,
        "--target-fps",
        target_fps,
        "--verbose",
    ]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'ByteDance Video Upscale'
    )

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        r = nuke.nodes.Read(file=out_path_nk)
        try:
            r.setName("%s_result_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("Bytedance video upscale\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
        try:
            video_frames.set_read_frame_range_from_video_file(r, out_path)
        except Exception:
            pass
    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Bytedance upscale output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
