# Purpose:
# - Runner script for the Nuke Group node `Seedream_5_Pro_Edit_v1` (executes inside Nuke / Python 2.7).
# - Reads edit settings from the Group knobs; optionally overrides prompt from `prompt_text` when a Text
#   node (`message` knob) is connected, including through Dot nodes. Collects reference stills from
#   named inputs `image_1`..`image_10` (at least one required; skips gaps). Primary plate is input 0.
# - Calls the external Python 3 helper, then wires outputs into the baked in-group preview.
#   Root Reads spawn only when spawn_reads_in_graph is on.
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

_IMAGE_INPUTS = tuple(("image_%d" % i, i - 1) for i in range(1, 11))
_PROMPT_INPUT = ("prompt_text", 10)
_IMAGE_SIZE_CHOICES = (
    "auto_2K",
    "auto_1K",
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
)
_OUTPUT_FORMAT_CHOICES = ("png", "jpeg")


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


def _enum_knob_str(group_node, knob_name, choices, default):
    try:
        k = group_node.knob(knob_name)
        v = k.value()
        if isinstance(v, int):
            if 0 <= v < len(choices):
                return choices[v]
            return default
        s = (str(v) or default).strip()
        return s if s in choices else default
    except Exception:
        return default


def _collect_reference_images(nuke_module, group_node, frame, temp_dir):
    """
    Collect 1..10 reference image paths from image_1..image_10.
    If the input is a suitable Read, use its resolved file directly; otherwise pre-render a still.
    """
    images = []
    for input_name, fallback in _IMAGE_INPUTS:
        n = _named_input_node(group_node, input_name, fallback)
        if n is None:
            continue
        idx = _named_input_index(group_node, input_name, fallback)
        try:
            images.append(
                prerender.prepare_still_input_path(
                    nuke_module=nuke_module,
                    src_node=n,
                    frame=frame,
                    run_dir=temp_dir,
                    base_name=input_name,
                )
            )
        except Exception as e:
            raise Exception("Reference image %s (input %d) error: %s" % (input_name, idx, str(e)))
    return images


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    prompt_idx = _named_input_index(g, _PROMPT_INPUT[0], _PROMPT_INPUT[1])
    prompt = prompt_input.get_prompt_from_input_or_group(
        nuke, g, input_index=prompt_idx, input_label=_PROMPT_INPUT[0]
    )
    if not prompt:
        nuke.message("Prompt is empty (and no input Text node message found).")
        raise Exception("missing prompt")

    frame = int(nuke.frame())

    num_images_s = (g.knob("num_images").value() or "1").strip()
    image_size = _enum_knob_str(g, "image_size", _IMAGE_SIZE_CHOICES, "auto_2K")
    output_format = _enum_knob_str(g, "output_format", _OUTPUT_FORMAT_CHOICES, "png")
    enable_safety_checker = bool(g.knob("enable_safety_checker").value())
    try:
        num_images = int(num_images_s)
    except Exception:
        num_images = 1
    num_images = max(1, min(6, int(num_images)))

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="seedream_5_pro_edit",
        group_node=g,
    )

    ref_images = _collect_reference_images(nuke, g, frame=frame, temp_dir=temp_dir)
    if not ref_images:
        nuke.message(
            "At least one reference image is required.\n\n"
            "Connect a still image to input 0 (image_1), and optionally image_2..image_10."
        )
        raise Exception("missing reference image")

    extra_args = [
        "--prompt",
        prompt,
        "--out-dir",
        out_dir,
        "--output-format",
        output_format,
        "--num-images",
        str(int(num_images)),
        "--image-size",
        image_size,
        "--verbose",
    ]

    for img in ref_images:
        extra_args += ["--image", img]

    if enable_safety_checker:
        extra_args += ["--enable-safety-checker"]
    else:
        extra_args += ["--no-enable-safety-checker"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, "Seedream 5.0 Pro Edit"
    )

    created = []
    for i in range(1, int(num_images) + 1):
        out_name = "image_%03d.%s" % (i, output_format)
        out_path = os.path.join(out_dir, out_name)
        if not os.path.isfile(out_path):
            continue
        created.append(prerender.norm_slashes(out_path))

    if not created:
        nuke.message("Helper finished, but no output images were found in:\n%s" % out_dir)
        raise Exception("no outputs")

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
        placed = []
        for i, out_path_nk in enumerate(created, start=1):
            nuke.root().begin()
            try:
                bx = xpos + (i - 1) * 120
                by = ypos + 140
                fx, fy = spawn_pos.resolve_spawn_xy(nuke, bx, by, exclude_nodes=placed)
                r = nuke.nodes.Read(file=out_path_nk)
                try:
                    r.setName("%s_%s_%02d" % (g.name(), ts, i), unique=True)
                except Exception:
                    pass
                try:
                    r.knob("label").setValue("Seedream 5.0 Pro Edit\n%s" % out_path_nk)
                except Exception:
                    pass
                r.setXpos(fx)
                r.setYpos(fy)
                placed.append(r)
            finally:
                nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Seedream 5.0 Pro edit output created:\n" + "\n".join(created))


if __name__ == "__main__":
    main()
