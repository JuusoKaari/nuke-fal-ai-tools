# Purpose:
# - Runner script for the Nuke Group node `Finegrain_Eraser_v1` (executes inside Nuke / Python 2.7).
# - Input 0: source plate; input 1: mask (white = region to erase). Pre-renders stills if needed.
# - Calls `fal_finegrain_eraser_helper.py` (Python 3), then spawns a Read node for the downloaded output.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).

from __future__ import print_function

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _path_util
import _install_help
import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_spawn_read_position_v1 as spawn_pos


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 (source_image) is not connected.")
        raise Exception("missing input 0")

    mask_node = g.input(1)
    if not mask_node:
        nuke.message("Input 1 (mask) is not connected.\nWhite in the mask = area to erase.")
        raise Exception("missing input 1")

    mode = (g.knob("mode").value() or "standard").strip().lower()
    seed_s = (g.knob("seed").value() or "").strip()

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="finegrain_eraser",
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
        mask_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=mask_node, frame=frame, run_dir=temp_dir, base_name="mask"
        )
    except Exception as e:
        nuke.message("Failed to prepare image or mask:\n%s" % str(e))
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
        "--mask",
        mask_path,
        "--out-dir",
        out_dir,
        "--mode",
        mode,
        "--verbose",
    ]

    if seed_s:
        try:
            args += ["--seed", str(int(seed_s))]
        except Exception:
            pass

    env = prerender.helper_subprocess_env()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    try:
        returncode, _stdout_lines = prerender.run_helper_subprocess(
            args,
            env=env,
            title="Finegrain Eraser",
        )
    except prerender.FalProgressCancelled:
        nuke.message("Finegrain Eraser request cancelled.")
        raise Exception("cancelled")

    if returncode != 0:
        nuke.message(
            "Finegrain Eraser helper failed (exit %d). Check the Script Editor output for details." % returncode
        )
        raise Exception("Finegrain Eraser helper failed")

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    out_path = os.path.join(out_dir, "erased.jpg")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "erased.png")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "erased.webp")
    if not os.path.isfile(out_path):
        nuke.message("Helper finished, but no output image found in:\n%s" % out_dir)
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
            r.knob("label").setValue("Finegrain Eraser\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Finegrain Eraser output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
