# Purpose:
# - Runner script for the Nuke Group node `Finegrain_Eraser_v1` (executes inside Nuke / Python 2.7).
# - Input 0: source plate; input 1: mask (white = region to erase). Pre-renders stills if needed.
# - Mask prerender is reformatted to the source node's format (not the script root format).
# - Calls `fal_finegrain_eraser_helper.py` (Python 3), then wires the erased still into the baked
#   in-group preview. Root Reads spawn only when spawn_reads_in_graph is on.
# - fal.ai removed premium mode; that knob value is remapped to standard.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).

from __future__ import print_function

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_group_output_preview_v1 as preview
import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
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
    if mode == "premium":
        print("Finegrain premium mode was removed by fal.ai. Using standard.")
        mode = "standard"
    if mode not in ("express", "standard"):
        mode = "standard"
    seed_s = (g.knob("seed").value() or "").strip()

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="finegrain_eraser",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
        mask_path = prerender.prepare_still_input_path(
            nuke_module=nuke,
            src_node=mask_node,
            frame=frame,
            run_dir=temp_dir,
            base_name="mask",
            match_format_node=src_node,
        )
    except Exception as e:
        nuke.message("Failed to prepare image or mask:\n%s" % str(e))
        raise


    extra_args = [
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
            extra_args += ["--seed", str(int(seed_s))]
        except Exception:
            pass

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Finegrain Eraser'
    )

    out_path = os.path.join(out_dir, "erased.jpg")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "erased.png")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "erased.webp")
    if not os.path.isfile(out_path):
        nuke.message("Helper finished, but no output image found in:\n%s" % out_dir)
        raise Exception("no output")

    out_path_nk = prerender.norm_slashes(out_path)
    created = [out_path_nk]

    try:
        preview.wire_group_outputs(g, created)
    except Exception as e:
        nuke.message("Failed to wire in-group preview outputs:\n%s" % str(e))
        raise

    spawn_reads = False
    try:
        sk = g.knob("spawn_reads_in_graph")
        if sk is not None:
            spawn_reads = bool(sk.value())
    except Exception:
        spawn_reads = False

    if spawn_reads:
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
