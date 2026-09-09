# Purpose:
# - Runner script for the Nuke Group node `Finegrain_Eraser_v1` (executes inside Nuke / Python 2.7).
# - Input 0: source plate; input 1: mask (white = region to erase). Pre-renders stills if needed.
# - If the mask pipe has an alpha channel, that alpha is copied to RGB before the Write.
# - Prefers in-group `mask_for_execute` (Shuffle + format match). Old groups fall back to a temp
#   Shuffle on the upstream mask, then Reformat to the source node's format (not the script root).
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

_MASK_EXECUTE_NODE = "mask_for_execute"


def _node_channels(node):
    try:
        return list(node.channels() or [])
    except Exception:
        return []


def _make_alpha_to_rgb_shuffle(nuke_module, src_node):
    sh = nuke_module.nodes.Shuffle()
    try:
        sh["in"].setValue("rgba")
    except Exception:
        pass
    for knob_name in ("red", "green", "blue", "alpha"):
        try:
            sh[knob_name].setValue("alpha")
        except Exception:
            pass
    sh.setInput(0, src_node)
    return sh


def _prepare_mask_path(nuke_module, group_node, mask_node, src_node, frame, temp_dir):
    """
    Pre-render the erase mask. New groups use in-group mask_for_execute (alpha Shuffle +
    format match). Older pasted groups fall back to a temp Shuffle on the upstream pipe.
    """
    out_path = os.path.join(temp_dir, "mask.png")
    with prerender.group_scope(nuke_module, group_node):
        inside = nuke_module.toNode(_MASK_EXECUTE_NODE)
        if inside is not None:
            prerender.render_still_inside_group(
                nuke_module, group_node, inside, out_path, frame
            )
            return prerender.norm_slashes(out_path)

    shuffle = None
    try:
        mask_src = mask_node
        if prerender.channel_list_has_alpha(_node_channels(mask_node)):
            shuffle = _make_alpha_to_rgb_shuffle(nuke_module, mask_node)
            mask_src = shuffle
        return prerender.prepare_still_input_path(
            nuke_module=nuke_module,
            src_node=mask_src,
            frame=frame,
            run_dir=temp_dir,
            base_name="mask",
            match_format_node=src_node,
        )
    finally:
        if shuffle is not None:
            try:
                nuke_module.delete(shuffle)
            except Exception:
                pass


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
        mask_path = _prepare_mask_path(
            nuke, g, mask_node, src_node, frame, temp_dir
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
