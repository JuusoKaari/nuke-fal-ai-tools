# Purpose:
# - Runner script for the Nuke Group node `BiRefNet_v2_Still_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream image input; if it's a suitable Read node, uses its file directly (no re-render),
#   otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_birefnet_v2_still_helper.py` via subprocess, then creates
#   a Read node in the main graph for the downloaded output image.
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


def _find_output_path(out_dir, output_format):
    fmt = (output_format or "png").strip().lower()
    candidates = [
        os.path.join(out_dir, "output.%s" % fmt),
        os.path.join(out_dir, "output.png"),
        os.path.join(out_dir, "output.webp"),
        os.path.join(out_dir, "output.gif"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def main():
    import nuke  # imported inside for Nuke environment

    g = nuke.thisNode()

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 (source_image) is not connected.")
        raise Exception("missing input 0")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="birefnet_v2_still",
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

    model = g.knob("model").value()
    operating_resolution = g.knob("operating_resolution").value()
    output_format = (g.knob("output_format").value() or "png").strip().lower()
    output_mask = bool(g.knob("output_mask").value())
    refine_foreground = bool(g.knob("refine_foreground").value())

    py_parts = prerender.split_cmd(python3_cmd) or ["py", "-3"]

    args = list(py_parts) + [
        helper_path,
        "--image",
        image_path,
        "--out-dir",
        out_dir,
        "--model",
        model,
        "--operating-resolution",
        operating_resolution,
        "--output-format",
        output_format,
        "--verbose",
    ]
    if output_mask:
        args += ["--output-mask"]
    if not refine_foreground:
        args += ["--no-refine-foreground"]

    env = prerender.helper_subprocess_env()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message(
            "BiRefNet v2 still helper failed (exit %d). Check the Script Editor output for details."
            % p.returncode
        )
        raise Exception("BiRefNet v2 still helper failed")

    out_path = _find_output_path(out_dir, output_format)
    if not out_path:
        nuke.message("Helper finished, but no output image found in:\n%s" % out_dir)
        raise Exception("no output")

    out_path_nk = prerender.norm_slashes(out_path)

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
            r.knob("label").setValue("BiRefNet v2 Still\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("BiRefNet v2 Still output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
