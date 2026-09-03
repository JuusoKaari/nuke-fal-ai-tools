# Purpose:
# - Runner script for the Nuke Group node `Qwen_Image_Edit_Inpaint_v1` (executes inside Nuke / Python 2.7).
# - Input 0: source plate; input 1: mask (white = region to inpaint). Pre-renders stills if needed.
# - Calls `fal_qwen_image_inpaint_helper.py` (Python 3), then wires outputs into the baked in-group preview.
# - Root Reads spawn only when spawn_reads_in_graph is on (default off).
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


def _ext_for_output_format(output_format):
    f = (output_format or "png").strip().lower()
    if f in ("jpg", "jpeg"):
        return "jpg"
    return "png"


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
        nuke.message("Input 1 (mask) is not connected.\nWhite in the mask = area to inpaint.")
        raise Exception("missing input 1")

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    negative_prompt = (g.knob("negative_prompt").value() or "").strip()
    output_format = (g.knob("output_format").value() or "png").strip().lower()
    enable_safety_checker = bool(g.knob("enable_safety_checker").value())
    num_images_s = (g.knob("num_images").value() or "1").strip()
    seed_s = (g.knob("seed").value() or "").strip()
    image_size = (g.knob("image_size").value() or "").strip()
    num_inference_steps_s = (g.knob("num_inference_steps").value() or "30").strip()
    guidance_scale_s = (g.knob("guidance_scale").value() or "4").strip()
    strength_s = (g.knob("strength").value() or "0.93").strip()
    acceleration = (g.knob("acceleration").value() or "regular").strip().lower()

    try:
        num_images = int(num_images_s)
    except Exception:
        num_images = 1
    num_images = max(1, min(4, int(num_images)))

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="qwen_image_inpaint",
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
        "--prompt",
        prompt,
        "--out-dir",
        out_dir,
        "--output-format",
        output_format,
        "--num-images",
        str(int(num_images)),
        "--num-inference-steps",
        num_inference_steps_s,
        "--guidance-scale",
        guidance_scale_s,
        "--strength",
        strength_s,
        "--acceleration",
        acceleration,
        "--verbose",
    ]

    if negative_prompt:
        extra_args += ["--negative-prompt", negative_prompt]
    if image_size:
        extra_args += ["--image-size", image_size]
    if seed_s:
        try:
            extra_args += ["--seed", str(int(seed_s))]
        except Exception:
            pass

    if enable_safety_checker:
        extra_args += ["--enable-safety-checker"]
    else:
        extra_args += ["--no-enable-safety-checker"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Qwen Image Inpaint'
    )

    out_ext = _ext_for_output_format(output_format)

    created = []
    for i in range(1, int(num_images) + 1):
        out_name = "image_%03d.%s" % (i, out_ext)
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
                    r.knob("label").setValue("Qwen Image Edit Inpaint\n%s" % out_path_nk)
                except Exception:
                    pass
                r.setXpos(fx)
                r.setYpos(fy)
                placed.append(r)
            finally:
                nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Qwen Image Edit inpaint output created:\n" + "\n".join(created))


if __name__ == "__main__":
    main()
