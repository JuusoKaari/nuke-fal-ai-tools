# Purpose:
# - Runner script for the Nuke Group node `GPT_Image_25_v1` (executes inside Nuke / Python 2.7).
# - Reads generate/edit settings from the Group knobs; optionally overrides prompt from `prompt_text`
#   when a Text node (`message` knob) is connected, including through Dot nodes. Collects optional
#   stills from `image_1`..`image_4` and optional mask from `mask`. No stills means text-to-image.
#   Resolution Match input / 1K / 2K / 4K is passed through. The helper turns a tier into
#   width and height from the first still. match_input_resolution stays on the Group
#   and only reformats the Nuke preview after generation. It is not sent to fal.
#   Calls the external Python 3 helper, then wires outputs into the baked in-group preview.
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


_IMAGE_INPUTS = (
    ("image_1", 0),
    ("image_2", 1),
    ("image_3", 4),
    ("image_4", 5),
)
_PROMPT_INPUT = ("prompt_text", 2)
_MASK_INPUT = ("mask", 3)
_VARIANT_CHOICES = ("flare", "sunburst")
_QUALITY_CHOICES = ("auto", "low", "medium", "high", "xhigh", "max")
_BACKGROUND_CHOICES = ("auto", "transparent", "opaque")
_IMAGE_SIZE_CHOICES = (
    "landscape_4_3",
    "auto",
    "square",
    "landscape_16_9",
    "portrait_16_9",
)
_RESOLUTION_CHOICES = (
    "Match input",
    "1K",
    "2K",
    "4K",
)
_OUTPUT_FORMAT_CHOICES = ("png", "jpeg", "webp")


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
    Collect 0..4 reference image paths from image_1..image_4.
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


def _prepare_mask_path(nuke_module, group_node, frame, temp_dir):
    """Export optional mask. No ROI on this Group."""
    mask_node = _named_input_node(group_node, _MASK_INPUT[0], _MASK_INPUT[1])
    if mask_node is None:
        return None

    match_node = None
    for input_name, fallback in _IMAGE_INPUTS:
        n = _named_input_node(group_node, input_name, fallback)
        if n is not None:
            match_node = n
            break
    try:
        return prerender.prepare_still_input_path(
            nuke_module=nuke_module,
            src_node=mask_node,
            frame=frame,
            run_dir=temp_dir,
            base_name="mask",
            match_format_node=match_node,
        )
    except Exception as e:
        nuke_module.message("Failed to prepare mask image:\n%s" % str(e))
        raise


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
    variant = _enum_knob_str(g, "variant", _VARIANT_CHOICES, "flare")
    quality = _enum_knob_str(g, "quality", _QUALITY_CHOICES, "high")
    background = _enum_knob_str(g, "background", _BACKGROUND_CHOICES, "auto")
    image_size = _enum_knob_str(g, "image_size", _IMAGE_SIZE_CHOICES, "landscape_4_3")
    resolution = _enum_knob_str(g, "resolution", _RESOLUTION_CHOICES, "Match input")
    output_format = _enum_knob_str(g, "output_format", _OUTPUT_FORMAT_CHOICES, "png")
    try:
        num_images = int(num_images_s)
    except Exception:
        num_images = 1
    num_images = max(1, min(4, int(num_images)))

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="gpt_image_25",
        group_node=g,
    )

    ref_images = _collect_reference_images(nuke, g, frame=frame, temp_dir=temp_dir)
    mask_path = _prepare_mask_path(nuke, g, frame, temp_dir)

    extra_args = [
        "--prompt",
        prompt,
        "--out-dir",
        out_dir,
        "--variant",
        variant,
        "--output-format",
        output_format,
        "--num-images",
        str(int(num_images)),
        "--quality",
        quality,
        "--background",
        background,
        "--image-size",
        image_size,
        "--resolution",
        resolution,
        "--verbose",
    ]

    for img in ref_images:
        extra_args += ["--image", img]

    if mask_path:
        extra_args += ["--mask", mask_path]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, "GPT Image 2.5"
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
                    r.knob("label").setValue("GPT Image 2.5\n%s" % out_path_nk)
                except Exception:
                    pass
                r.setXpos(fx)
                r.setYpos(fy)
                placed.append(r)
            finally:
                nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("GPT Image 2.5 output created:\n" + "\n".join(created))


if __name__ == "__main__":
    main()
