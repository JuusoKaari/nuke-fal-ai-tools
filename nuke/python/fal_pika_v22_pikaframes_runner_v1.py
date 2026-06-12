# Purpose:
# - Runner script for the Nuke Group node `Pika_22_Pikaframes_v1` (executes inside Nuke / Python 2.7).
# - Accepts 2-5 keyframe images on inputs 0-4 (contiguous from keyframe_1; stop at first gap).
# - If upstream is a suitable Read node, uses its file directly; otherwise pre-renders stills to a temp folder.
# - Calls the external Python 3 helper `fal_pika_v22_pikaframes_helper.py` via subprocess, then creates
#   a Read node in the main graph for the downloaded mp4.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _path_util
import _install_help
import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos

_MAX_KEYFRAMES = 5
_MAX_TOTAL_TRANSITION_SECONDS = 25


def _stream_process_output(p):
    while True:
        line = p.stdout.readline()
        if not line:
            break
        try:
            if isinstance(line, bytes):
                try:
                    line = line.decode("utf-8", "replace")
                except Exception:
                    line = str(line)
            print(line.rstrip("\r\n"))
        except Exception:
            pass


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

    g = nuke.thisNode()

    frame = int(nuke.frame())
    try:
        transition_duration = _read_transition_duration(g)
    except Exception as e:
        nuke.message("Invalid transition duration:\n%s" % str(e))
        raise

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="pika_v22_pikaframes",
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
    out_path_nk = prerender.norm_slashes(out_path)

    python3_cmd = (g.knob("python3_cmd").value() or "").strip() or "py -3"
    helper_path = _install_help.require_helper_path(
        nuke,
        (g.knob("helper_path").value() or "").strip(),
    )

    py_parts = prerender.split_cmd(python3_cmd) or ["py", "-3"]
    args = list(py_parts) + [
        helper_path,
        "--out",
        out_path,
        "--resolution",
        resolution,
        "--transition-duration",
        str(int(transition_duration)),
        "--verbose",
    ]
    for image_path in image_paths:
        args += ["--image", image_path]
    if prompt:
        args += ["--prompt", prompt]
    if negative_prompt:
        args += ["--negative-prompt", negative_prompt]

    seed_s = (g.knob("seed").value() or "").strip()
    if seed_s:
        try:
            args += ["--seed", str(int(float(seed_s)))]
        except Exception:
            nuke.message("Invalid seed value.")
            raise Exception("invalid seed")

    env = prerender.helper_subprocess_env()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message(
            "Pika 2.2 Pikaframes helper failed (exit %d). Check the Script Editor output for details."
            % p.returncode
        )
        raise Exception("Pika 2.2 Pikaframes helper failed")

    if not os.path.isfile(out_path):
        nuke.message("Helper finished, but output file was not found:\n%s" % out_path_nk)
        raise Exception("missing output mp4")

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
            r.knob("label").setValue("Pika 2.2 Pikaframes\n%s" % out_path_nk)
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
        nuke.message("Pika 2.2 Pikaframes output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
