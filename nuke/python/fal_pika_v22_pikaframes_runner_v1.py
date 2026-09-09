# Purpose:
# - Runner script for the Nuke Group node `Pika_22_Pikaframes_v1` (executes inside Nuke / Python 2.7).
# - Accepts 2-5 keyframe images on inputs 0-4 (contiguous from keyframe_1; stop at first gap).
# - If upstream is a suitable Read node, uses its file directly; otherwise pre-renders stills to a temp folder.
# - Calls the external Python 3 helper `fal_pika_v22_pikaframes_helper.py` via subprocess, then creates
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

_MAX_KEYFRAMES = 5
_MAX_TOTAL_TRANSITION_SECONDS = 25


def _read_transition_duration(g):
    raw = (g.knob("transition_duration").value() or "5").strip()
    try:
        val = int(float(raw))
    except Exception:
        raise Exception("invalid transition_duration")
    if val < 1 or val > 25:
        raise Exception("transition_duration must be between 1 and 25")
    return val


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    try:
        transition_duration = _read_transition_duration(g)
    except Exception as e:
        nuke.message("Invalid transition duration:\n%s" % str(e))
        raise

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="pika_v22_pikaframes",
        group_node=g,
    )

    image_paths = []
    for i in range(_MAX_KEYFRAMES):
        src_node = g.input(i)
        if not src_node:
            break
        base_name = "keyframe_%02d" % (i + 1)
        try:
            image_path = prerender.prepare_still_input_path(
                nuke_module=nuke,
                src_node=src_node,
                frame=frame,
                run_dir=temp_dir,
                base_name=base_name,
            )
        except Exception as e:
            nuke.message("Failed to prepare %s:\n%s" % (base_name, str(e)))
            raise
        image_paths.append(image_path)

    if len(image_paths) < 2:
        nuke.message(
            "Connect at least 2 keyframes in order (keyframe_1, keyframe_2, ...).\n"
            "Inputs must be contiguous from keyframe_1."
        )
        raise Exception("need at least 2 keyframes")

    num_transitions = len(image_paths) - 1
    total_duration = transition_duration * num_transitions
    if total_duration > _MAX_TOTAL_TRANSITION_SECONDS:
        nuke.message(
            "Total transition duration is %d seconds (%d transitions x %d s).\n"
            "Maximum allowed is %d seconds."
            % (total_duration, num_transitions, transition_duration, _MAX_TOTAL_TRANSITION_SECONDS)
        )
        raise Exception("transition duration too long")

    prompt = (g.knob("prompt").value() or "").strip()
    negative_prompt = (g.knob("negative_prompt").value() or "").strip()
    resolution = (g.knob("resolution").value() or "720p").strip()

    out_path = os.path.join(out_dir, "pika_v22_pikaframes_%s.mp4" % ts)

    extra_args = [
        "--out",
        out_path,
        "--resolution",
        resolution,
        "--transition-duration",
        str(int(transition_duration)),
        "--verbose",
    ]
    for image_path in image_paths:
        extra_args += ["--image", image_path]
    if prompt:
        extra_args += ["--prompt", prompt]
    if negative_prompt:
        extra_args += ["--negative-prompt", negative_prompt]

    seed_s = (g.knob("seed").value() or "").strip()
    if seed_s:
        try:
            extra_args += ["--seed", str(int(float(seed_s)))]
        except Exception:
            nuke.message("Invalid seed value.")
            raise Exception("invalid seed")

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Pika 2.2 Pikaframes'
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "Pika 2.2 Pikaframes", "%s_%s" % (g.name(), ts)
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Pika 2.2 Pikaframes output created:\n%s" % display_path)


if __name__ == "__main__":
    main()
