# Purpose:
# - Runner script for the Nuke Group node `Seedance_2_Image_To_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts a start image on input 0; optional end image on input 1 for start/end transition.
# - If upstream is a suitable Read node, uses its file directly; otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_seedance_2_image_to_video_helper.py` via subprocess, then creates
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

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    duration_s = (g.knob("duration").value() or "auto").strip()
    resolution = (g.knob("resolution").value() or "720p").strip()
    aspect_ratio = (g.knob("aspect_ratio").value() or "auto").strip()
    generate_audio = bool(g.knob("generate_audio").value())

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="seedance_2_i2v",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="start_image"
        )
    except Exception as e:
        nuke.message("Failed to prepare start image:\n%s" % str(e))
        raise

    end_node = g.input(1)
    end_image_path = ""
    if end_node:
        try:
            end_image_path = prerender.prepare_still_input_path(
                nuke_module=nuke, src_node=end_node, frame=frame, run_dir=temp_dir, base_name="end_image"
            )
        except Exception as e:
            nuke.message("Failed to prepare end image:\n%s" % str(e))
            raise

    out_path = os.path.join(out_dir, "seedance_2_i2v_%s.mp4" % ts)

    extra_args = [
        "--image",
        image_path,
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
        "--verbose",
    ]

    if end_image_path:
        extra_args += ["--end-image", end_image_path]

    if generate_audio:
        extra_args += ["--generate-audio"]
    else:
        extra_args += ["--no-generate-audio"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Seedance 2 Image to Video'
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "Seedance 2.0 image-to-video", "%s_%s" % (g.name(), ts)
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Seedance 2.0 image-to-video output created:\n%s" % display_path)


if __name__ == "__main__":
    main()
