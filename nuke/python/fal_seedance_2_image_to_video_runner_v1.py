# Purpose:
# - Runner script for the Nuke Group node `Seedance_2_Image_To_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts a start image on input 0; optional end image on input 1 for start/end transition.
# - If upstream is a suitable Read node, uses its file directly; otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_seedance_2_image_to_video_helper.py` via subprocess, then creates
#   a Read node in the main graph for the downloaded mp4 (frame range set via `nuke_read_video_frames_v1`).
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

import nuke_prerender_v1 as prerender
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos


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


def main():
    import nuke  # imported inside for Nuke environment

    g = nuke.thisNode()

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
    out_path_nk = prerender.norm_slashes(out_path)

    python3_cmd = (g.knob("python3_cmd").value() or "").strip() or "py -3"
    helper_path = _install_help.require_helper_path(
        nuke,
        (g.knob("helper_path").value() or "").strip(),
    )

    py_parts = prerender.split_cmd(python3_cmd) or ["py", "-3"]
    args = list(py_parts) + [
        helper_path,
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
        args += ["--end-image", end_image_path]

    if generate_audio:
        args += ["--generate-audio"]
    else:
        args += ["--no-generate-audio"]

    env = os.environ.copy()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message(
            "Seedance 2.0 image-to-video helper failed (exit %d). Check the Script Editor output for details."
            % p.returncode
        )
        raise Exception("Seedance 2.0 helper failed")

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
            r.knob("label").setValue("Seedance 2.0 image-to-video\n%s" % out_path_nk)
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

    if bool(g.knob("show_success_popup").value()):
        nuke.message("Seedance 2.0 image-to-video output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
