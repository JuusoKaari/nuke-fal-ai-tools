# Purpose:
# - Runner script for the Nuke Group node `Qwen_Image_Layered_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream image input; if it's a suitable Read node, uses its file at the current frame directly
#   (no re-render), otherwise pre-renders a still to a temp folder.
# - Calls the external Python 3 helper `fal_qwen_image_layered_helper.py` to decompose the image into
#   RGBA layers via fal.ai, and creates multiple Read nodes (one per layer) in the main graph.
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

import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_spawn_read_position_v1 as spawn_pos


def _layer_output_path(layer_dir, output_format):
    fmt = (output_format or "png").strip().lower()
    preferred = os.path.join(layer_dir, "layer.%s" % fmt)
    if os.path.isfile(preferred):
        return preferred
    if os.path.isdir(layer_dir):
        for name in sorted(os.listdir(layer_dir)):
            p = os.path.join(layer_dir, name)
            if os.path.isfile(p):
                return p
    return preferred


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

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="qwen_layered",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
    except Exception as e:
        nuke.message("Failed to prepare input image:\n%s" % str(e))
        raise


    num_layers = (g.knob("num_layers").value() or "4").strip()
    num_inference_steps = (g.knob("num_inference_steps").value() or "28").strip()
    guidance_scale = (g.knob("guidance_scale").value() or "5").strip()
    output_format = (g.knob("output_format").value() or "png").strip().lower()
    acceleration = (g.knob("acceleration").value() or "regular").strip().lower()
    prompt = (g.knob("prompt").value() or "").strip()
    negative_prompt = (g.knob("negative_prompt").value() or "").strip()
    seed = (g.knob("seed").value() or "").strip()
    enable_safety_checker = bool(g.knob("enable_safety_checker").value())


    extra_args = [
        "--image",
        image_path,
        "--out-dir",
        out_dir,
        "--num-layers",
        str(int(num_layers)),
        "--num-inference-steps",
        str(int(num_inference_steps)),
        "--guidance-scale",
        str(float(guidance_scale)),
        "--output-format",
        output_format,
        "--acceleration",
        acceleration,
        "--verbose",
    ]
    if prompt:
        extra_args += ["--prompt", prompt]
    if negative_prompt:
        extra_args += ["--negative-prompt", negative_prompt]
    if seed:
        try:
            extra_args += ["--seed", str(int(seed))]
        except (ValueError, TypeError):
            pass
    if not enable_safety_checker:
        extra_args += ["--no-enable-safety-checker"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Qwen Image Layered'
    )

    # Discover actual layer count from output dir (layer_0, layer_1, ...)
    layer_indices = []
    for name in (os.listdir(out_dir) if os.path.isdir(out_dir) else []):
        if name.startswith("layer_"):
            try:
                layer_indices.append(int(name.split("_")[1]))
            except (ValueError, IndexError):
                pass
    layer_indices.sort()

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    nuke.root().begin()
    try:
        read_nodes = []
        for layer_idx in layer_indices:
            layer_dir = os.path.join(out_dir, "layer_%d" % layer_idx)
            out_path = _layer_output_path(layer_dir, output_format)
            out_path_nk = prerender.norm_slashes(out_path)

            if not os.path.isfile(out_path):
                continue

            bx = xpos + (layer_idx * 120)
            by = ypos + 140
            fx, fy = spawn_pos.resolve_spawn_xy(nuke, bx, by, exclude_nodes=read_nodes)
            r = nuke.nodes.Read(file=out_path_nk)
            try:
                r.setName("%s_layer_%d_%s" % (g.name(), layer_idx, ts), unique=True)
            except Exception:
                pass
            try:
                r.knob("label").setValue("Layer %d\n%s" % (layer_idx, out_path_nk))
            except Exception:
                pass
            r.setXpos(fx)
            r.setYpos(fy)
            read_nodes.append(r)

        if not read_nodes:
            nuke.message("No layer output found. Check the helper script output.")

    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message(
            "Qwen Image Layered: created %d Read node(s).\n%s"
            % (len(read_nodes), prerender.norm_slashes(out_dir))
        )


if __name__ == "__main__":
    main()
