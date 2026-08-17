# Purpose:
# - Runner script for the Nuke Group node `Kling_O3_V2V_Edit_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream video input; if it's a suitable Read node, uses its file directly (no re-render),
#   otherwise pre-renders a temp video from the connected pipe.
# - Also accepts optional reference image inputs from any pipe (Read fast-path; otherwise prerender still).
# - Writes a timestamped output mp4 path under a writable temp folder, then calls the external Python 3 helper
#   `fal_kling_o3_v2v_edit_helper.py` via subprocess, and finally creates a Read node in the main graph
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
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        nuke.message("Input 0 (source_video) is not connected.")
        raise Exception("missing input 0")

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    keep_audio = bool(g.knob("keep_audio").value())
    shot_type = (g.knob("shot_type").value() or "").strip()

    # Render/resolve inputs
    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="kling_o3_v2v_edit",
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

    # Optional reference images (inputs 1..4)
    image_paths = []
    for idx in range(1, 5):
        rn = g.input(idx)
        if not rn:
            continue
        try:
            p = prerender.prepare_still_input_path(
                nuke_module=nuke, src_node=rn, frame=frame, run_dir=temp_dir, base_name="ref_image_%d" % idx
            )
        except Exception as e:
            nuke.message("Failed to prepare reference image input %d:\n%s" % (idx, str(e)))
            raise
        image_paths.append(p)

    out_path = os.path.join(out_dir, "kling_o3_v2v_edit_%s.mp4" % ts)
    out_path_nk = prerender.norm_slashes(out_path)


    extra_args = [
        "--video",
        video_path,
        "--prompt",
        prompt,
        "--out",
        out_path,
        "--verbose",
    ]

    if keep_audio:
        extra_args += ["--keep-audio"]
    else:
        extra_args += ["--no-keep-audio"]

    if shot_type:
        extra_args += ["--shot-type", shot_type]

    for p in image_paths:
        extra_args += ["--image", p]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Kling O3 V2V Edit'
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
            r.knob("label").setValue("Kling O3 v2v edit\n%s" % out_path_nk)
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
        nuke.message("Kling O3 output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()

