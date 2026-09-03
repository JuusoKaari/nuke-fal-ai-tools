# Purpose:
# - Runner script for the Nuke Group node `Hunyuan_World_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream image input; if it's a suitable Read node, uses its file directly (no re-render),
#   otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_hunyuan_world_helper.py` via subprocess, then wires the
#   panorama into the baked in-group preview. Root Reads spawn only when spawn_reads_in_graph is on.
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

import nuke_group_output_preview_v1 as preview
import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_spawn_read_position_v1 as spawn_pos


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 is not connected.")
        raise Exception("missing input 0")

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="hunyuan_world",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
    except Exception as e:
        nuke.message("Failed to prepare input image:\n%s" % str(e))
        raise


    extra_args = [
        "--image",
        image_path,
        "--prompt",
        prompt,
        "--out-dir",
        out_dir,
        "--verbose",
    ]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Hunyuan World'
    )

    out_path = os.path.join(out_dir, "panorama.png")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "panorama.jpg")
    if not os.path.isfile(out_path):
        out_path = os.path.join(out_dir, "panorama.webp")
    if not os.path.isfile(out_path):
        nuke.message("Helper finished, but no output panorama found in:\n%s" % out_dir)
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
                r.knob("label").setValue("Hunyuan World\n%s" % out_path_nk)
            except Exception:
                pass
            r.setXpos(fx)
            r.setYpos(fy)
        finally:
            nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Hunyuan World panorama created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
