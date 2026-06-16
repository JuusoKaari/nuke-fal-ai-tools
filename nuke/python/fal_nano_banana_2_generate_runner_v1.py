# Purpose:
# - Runner script for the Nuke Group node `Nano_Banana_2_Generate_v1` (executes inside Nuke / Python 2.7).
# - Reads generation settings from the Group knobs; optionally overrides prompt from Input 2 when a Text node
#   (`message` knob) is connected, including through Dot nodes (wrong node type -> warning and abort).
#   Calls the external Python 3 helper.
# - Optional reference image inputs can come from any pipe: if a suitable Read node is connected, its file
#   is used directly (no re-render), otherwise a still is pre-rendered to a temp folder.
# - Wires downloaded image(s) to in-group preview reads; optionally spawns root Read node(s).
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

import _path_util
import _install_help
import _nuke_runner_launcher

import nuke_group_output_preview_v1 as preview
import nuke_prerender_v1 as prerender
import nuke_prompt_input_v1 as prompt_input
import nuke_spawn_read_position_v1 as spawn_pos


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    prompt = prompt_input.get_prompt_from_input_or_group(nuke, g, input_index=2)
    if not prompt:
        nuke.message("Prompt is empty (and no input Text node message found).")
        raise Exception("missing prompt")

    frame = int(nuke.frame())

    num_images_s = (g.knob("num_images").value() or "1").strip()
    seed_s = (g.knob("seed").value() or "").strip()
    aspect_ratio = (g.knob("aspect_ratio").value() or "auto").strip()
    resolution = (g.knob("resolution").value() or "1K").strip()
    output_format = (g.knob("output_format").value() or "png").strip().lower()
    safety_tolerance = (g.knob("safety_tolerance").value() or "4").strip()
    enable_web_search = bool(g.knob("enable_web_search").value())

    try:
        num_images = int(num_images_s)
    except Exception:
        num_images = 1
    num_images = max(1, min(4, int(num_images)))

    preview_config = preview.get_config_for_group(g)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="nano_banana_2",
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

    python3_cmd = (g.knob("python3_cmd").value() or "").strip() or "py -3"
    helper_path = _install_help.require_helper_path(
        nuke,
        (g.knob("helper_path").value() or "").strip(),
    )

    py_parts = prerender.split_cmd(python3_cmd) or ["py", "-3"]

    args = list(py_parts) + [
        helper_path,
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
        "--verbose",
    ]

    for img in ref_images:
        args += ["--image", img]

    if seed_s:
        try:
            args += ["--seed", str(int(seed_s))]
        except Exception:
            pass

    if enable_web_search:
        args += ["--enable-web-search"]
    else:
        args += ["--no-enable-web-search"]

    # Pass auth via env var (do NOT override env with the placeholder text)
    env = prerender.helper_subprocess_env()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    try:
        returncode, _stdout_lines = prerender.run_helper_subprocess(
            args,
            env=env,
            title="Nano Banana 2",
        )
    except prerender.FalProgressCancelled:
        nuke.message("Nano Banana 2 request cancelled.")
        raise Exception("cancelled")

    if returncode != 0:
        nuke.message("Nano Banana 2 helper failed (exit %d). Check the Script Editor output for details." % returncode)
        raise Exception("Nano Banana 2 helper failed")

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
                    r.knob("label").setValue("Nano Banana 2\n%s" % out_path_nk)
                except Exception:
                    pass
                r.setXpos(fx)
                r.setYpos(fy)
                placed.append(r)
            finally:
                nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Nano Banana 2 output created:\n" + "\n".join(created))


if __name__ == "__main__":
    main()

