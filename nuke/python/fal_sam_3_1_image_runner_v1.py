# Purpose:
# - Runner script for the Nuke Group node `SAM_3_1_Image_v1` (executes inside Nuke / Python 2.7).
# - Input 0: source plate. Optional input 1: prompt_text (Text node `message` overrides the prompt knob,
#   including through Dot nodes). Pre-renders a still if needed.
# - Calls `fal_sam_3_1_image_helper.py` (Python 3), then wires the mask or RGBA cutout into the baked
#   in-group preview. Root Reads spawn only when spawn_reads_in_graph is on.
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
import nuke_prompt_input_v1 as prompt_input
import nuke_spawn_read_position_v1 as spawn_pos

_SOURCE_INPUT = ("source_image", 0)
_PROMPT_INPUT = ("prompt_text", 1)


def _named_input_index(group_node, input_name, fallback):
    try:
        return int(group_node.inputIndex(input_name))
    except Exception:
        return int(fallback)


def _named_input_node(group_node, input_name, fallback):
    idx = _named_input_index(group_node, input_name, fallback)
    try:
        return group_node.input(idx)
    except Exception:
        return None


def _find_output_path(out_dir, apply_mask):
    stems = ["cutout", "mask"] if apply_mask else ["mask", "cutout"]
    exts = ["png", "webp", "jpg", "jpeg"]
    for stem in stems:
        for ext in exts:
            path = os.path.join(out_dir, "%s.%s" % (stem, ext))
            if os.path.isfile(path):
                return path
    return None


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    src_idx = _named_input_index(g, _SOURCE_INPUT[0], _SOURCE_INPUT[1])
    src_node = _named_input_node(g, _SOURCE_INPUT[0], _SOURCE_INPUT[1])
    if not src_node:
        nuke.message("Input %d (%s) is not connected." % (src_idx, _SOURCE_INPUT[0]))
        raise Exception("missing input 0")

    prompt_idx = _named_input_index(g, _PROMPT_INPUT[0], _PROMPT_INPUT[1])
    prompt = prompt_input.get_prompt_from_input_or_group(
        nuke, g, input_index=prompt_idx, input_label=_PROMPT_INPUT[0]
    )
    if not prompt:
        nuke.message("Prompt is empty (and no input Text node message found).")
        raise Exception("missing prompt")

    frame = int(nuke.frame())
    apply_mask = bool(g.knob("apply_mask").value())

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="sam_3_1_image",
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
    if apply_mask:
        extra_args += ["--apply-mask"]
    else:
        extra_args += ["--no-apply-mask"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, "SAM 3.1 Image"
    )

    out_path = _find_output_path(out_dir, apply_mask)
    if not out_path:
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
                r.knob("label").setValue("SAM 3.1 Image\n%s" % out_path_nk)
            except Exception:
                pass
            r.setXpos(fx)
            r.setYpos(fy)
        finally:
            nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("SAM 3.1 Image output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
