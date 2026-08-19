# Purpose:
# - Runner script for the Nuke Group node `FLUX_3_First_Last_Frame_To_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts a start image on input 0 and a required end image on input 1.
# - If upstream is a suitable Read node, uses its file directly; otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_flux_3_first_last_frame_to_video_helper.py` via subprocess, then creates
#   a Read for the result (DWAB EXR sequence by default; MP4 if chosen in Settings).
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
import nuke_video_output_v1 as video_out


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 (start_image) is not connected.")
        raise Exception("missing input 0")

    end_node = g.input(1)
    if not end_node:
        nuke.message("Input 1 (end_image) is not connected.")
        raise Exception("missing input 1")

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    duration_s = (g.knob("duration").value() or "5").strip()
    resolution = (g.knob("resolution").value() or "720p").strip()
    aspect_ratio = (g.knob("aspect_ratio").value() or "auto").strip()
    generate_audio = bool(g.knob("generate_audio").value())
    safety_tolerance = (g.knob("safety_tolerance").value() or "2").strip()
    use_draft = bool(g.knob("use_draft").value())

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="flux_3_first_last",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="start_image"
        )
    except Exception as e:
        nuke.message("Failed to prepare start image:\n%s" % str(e))
        raise

    try:
        end_image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=end_node, frame=frame, run_dir=temp_dir, base_name="end_image"
        )
    except Exception as e:
        nuke.message("Failed to prepare end image:\n%s" % str(e))
        raise

    out_path = os.path.join(out_dir, "flux_3_first_last_%s.mp4" % ts)

    extra_args = [
        "--image",
        image_path,
        "--end-image",
        end_image_path,
        "--prompt",
        prompt,
        "--out",
        out_path,
        "--duration",
        duration_s,
        "--resolution",
        resolution,
        "--aspect-ratio",
        aspect_ratio,
        "--safety-tolerance",
        safety_tolerance,
        "--verbose",
    ]

    if generate_audio:
        extra_args += ["--generate-audio"]
    else:
        extra_args += ["--no-generate-audio"]

    if use_draft:
        extra_args += ["--draft"]
    else:
        extra_args += ["--no-draft"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'FLUX 3 First/Last Frame to Video'
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "FLUX 3 first-last-frame-to-video", "%s_%s" % (g.name(), ts)
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("FLUX 3 first-last-frame-to-video output created:\n%s" % display_path)


if __name__ == "__main__":
    main()
