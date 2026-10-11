# Purpose:
# - Runner script for the Nuke Group node `Nano_Banana_21_v1` (executes inside Nuke / Python 2.7).
# - No stills: text-to-image (`google/nano-banana-2.1`).
#   image_a and optional image_b: edit (`google/nano-banana-2.1/edit`).
# - Reads generation settings from the Group knobs. A Text node on prompt_text
#   (input 2, including through Dot nodes) overrides the prompt knob.
# - Baked preview Groups export image_a and image_b via prepare_ai_inputs, so Use ROI
#   crops image_a to roi_area.
# - Calls the external Python 3 helper, then wires downloaded images into the
#   baked in-group preview. Root Reads spawn only when spawn_reads_in_graph is on.
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


_ASPECT_RATIOS = (
    "auto",
    "21:9",
    "16:9",
    "3:2",
    "4:3",
    "5:4",
    "1:1",
    "4:5",
    "3:4",
    "2:3",
    "9:16",
    "4:1",
    "1:4",
    "8:1",
    "1:8",
)
_RESOLUTIONS = ("1K", "2K", "4K")
_THINKING_LEVELS = ("minimal", "medium", "high")
_OUTPUT_FORMATS = ("png", "jpeg", "webp")
_SAFETY = ("1", "2", "3", "4", "5", "6")


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


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    prompt = prompt_input.get_prompt_from_input_or_group(
        nuke, g, input_index=2, input_label="prompt_text"
    )
    if not prompt:
        nuke.message("Prompt is empty (and no input Text node message found).")
        raise Exception("missing prompt")

    frame = int(nuke.frame())

    num_images_s = (g.knob("num_images").value() or "1").strip()
    seed_s = (g.knob("seed").value() or "").strip()
    aspect_ratio = _enum_knob_str(g, "aspect_ratio", _ASPECT_RATIOS, "auto")
    resolution = _enum_knob_str(g, "resolution", _RESOLUTIONS, "1K")
    output_format = _enum_knob_str(g, "output_format", _OUTPUT_FORMATS, "png")
    safety_tolerance = _enum_knob_str(g, "safety_tolerance", _SAFETY, "4")
    thinking_level = _enum_knob_str(g, "thinking_level", _THINKING_LEVELS, "medium")
    enable_web_search = bool(g.knob("enable_web_search").value())
    try:
        system_prompt = (g.knob("system_prompt").value() or "").strip()
    except Exception:
        system_prompt = ""

    try:
        num_images = int(num_images_s)
    except Exception:
        num_images = 1
    num_images = max(1, min(4, int(num_images)))

    preview_config = preview.get_config_for_group(g)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="nano_banana_21",
        group_node=g,
    )

    if preview_config is not None:
        try:
            ref_images = [
                path for _, path in preview.prepare_ai_inputs(
                    g, preview_config, frame, temp_dir
                )
            ]
        except preview.AiInputExportError:
            raise
        except Exception as exc:
            nuke.message("Failed to prepare AI input images:\n%s" % str(exc))
            raise
    else:
        ref_images = []

    extra_args = [
        "--prompt",
        prompt,
        "--out-dir",
        out_dir,
        "--output-format",
        output_format,
        "--num-images",
        str(int(num_images)),
        "--aspect-ratio",
        aspect_ratio,
        "--resolution",
        resolution,
        "--safety-tolerance",
        str(safety_tolerance),
        "--thinking-level",
        thinking_level,
        "--verbose",
    ]

    for img in ref_images:
        extra_args += ["--image", img]

    if system_prompt:
        extra_args += ["--system-prompt", system_prompt]

    if seed_s:
        try:
            extra_args += ["--seed", str(int(seed_s))]
        except Exception:
            pass

    if enable_web_search:
        extra_args += ["--enable-web-search"]
    else:
        extra_args += ["--no-enable-web-search"]

    runner_util.run_group_helper(
        nuke, g, extra_args, "Nano Banana 2.1"
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

    if preview_config is not None:
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
                    r.knob("label").setValue("Nano Banana 2.1\n%s" % out_path_nk)
                except Exception:
                    pass
                r.setXpos(fx)
                r.setYpos(fy)
                placed.append(r)
            finally:
                nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Nano Banana 2.1 output created:\n" + "\n".join(created))


if __name__ == "__main__":
    main()
