# Purpose:
# - Runner script for the Nuke Group node `Depth_Anything_v2` (executes inside Nuke / Python 2.7).
# - Accepts any upstream image input; if it's a suitable Read node, uses its file directly (no re-render),
#   otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_depth_anything_v2_helper.py` via subprocess, then creates
#   a Read node in the main graph for the downloaded depth map image.
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
        nuke.message("Input 0 is not connected.")
        raise Exception("missing input 0")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="depth_anything_v2",
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
    except Exception as e:
        nuke.message("Failed to prepare input image:\n%s" % str(e))
        raise

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
        "--out-dir",
        out_dir,
        "--verbose",
    ]

    # Pass auth via env var (do NOT override env with the placeholder text)
    env = prerender.helper_subprocess_env()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message(
            "Depth Anything v2 helper failed (exit %d). Check the Script Editor output for details."
            % p.returncode
        )
        raise Exception("Depth Anything v2 helper failed")

    # Create Read node in the main node graph (not inside the group)
    xpos = int(g.xpos())
    ypos = int(g.ypos())

    # Helper outputs depth_map.png (or depth_map.<ext>)
    out_path = os.path.join(out_dir, "depth_map.png")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "depth_map.jpg")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "depth_map.webp")
    if not os.path.isfile(out_path):
        nuke.message("Helper finished, but no output depth map found in:\n%s" % out_dir)
        raise Exception("no output")

    out_path_nk = prerender.norm_slashes(out_path)

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        r = nuke.nodes.Read(file=out_path_nk)
        try:
            r.setName("%s_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("Depth Anything v2\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Depth map output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
