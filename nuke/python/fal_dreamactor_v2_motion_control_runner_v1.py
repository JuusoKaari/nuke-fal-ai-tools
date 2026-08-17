# Purpose:
# - Runner script for the Nuke Group node `DreamActor_V2_Motion_Control_v1` (executes inside Nuke).
# - Accepts any upstream motion-video + style-image inputs; if they're suitable Read nodes, uses their
#   file directly (no re-render), otherwise pre-renders temp media from the connected pipes.
# - Writes a timestamped output mp4 path under a writable temp folder, then calls the external Python 3
#   helper `fal_dreamactor_v2_helper.py` via subprocess, and finally creates a Read node in the main graph
#   pointing at the resulting video (frame range set via `nuke_read_video_frames_v1`).
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
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    motion_node = g.input(0)
    style_node = g.input(1)

    if not motion_node:
        nuke.message("Input 0 (motion_source) is not connected.")
        raise Exception("missing motion_source")
    if not style_node:
        nuke.message("Input 1 (style_image) is not connected.")
        raise Exception("missing style_image")

    frame = int(nuke.frame())

    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="dreamactor_v2",
        group_node=g,
    )

    try:
        motion_path = prerender.prepare_video_input_path(
            nuke_module=nuke,
            src_node=motion_node,
            frame=frame,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="motion_source",
        )
        style_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=style_node, frame=frame, run_dir=temp_dir, base_name="style_image"
        )
    except Exception as e:
        nuke.message("Failed to prepare inputs:\n%s" % str(e))
        raise

    out_path = os.path.join(out_dir, "dreamactor_v2_%s.mp4" % ts)
    out_path_nk = prerender.norm_slashes(out_path)


    trim_first_second = bool(g.knob("trim_first_second").value())

    extra_args = [
        "--image",
        style_path,
        "--video",
        motion_path,
        "--out",
        out_path,
        "--verbose",
    ]
    if trim_first_second:
        extra_args += ["--trim-first-second"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'DreamActor v2'
    )

    # Create a new Read node in the main node graph (not inside the group)
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
            r.knob("label").setValue("DreamActor v2\n%s" % out_path_nk)
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
        nuke.message("DreamActor v2 output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()

