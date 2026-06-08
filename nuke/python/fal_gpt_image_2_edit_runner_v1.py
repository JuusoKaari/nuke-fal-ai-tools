# Purpose:
# - Runner script for the Nuke Group node `GPT_Image_2_Edit_v1` (executes inside Nuke / Python 2.7).
# - Reads edit settings from the Group knobs; optionally overrides prompt from Input 0 when a Text node
#   (`message` knob) is connected. Collects reference image(s) from inputs 1-2 (required) and optional
#   mask from input 3. Calls the external Python 3 helper, then creates Read node(s) in the main graph.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import os
import subprocess

import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _path_util
import _install_help

import nuke_prerender_v1 as prerender
import nuke_spawn_read_position_v1 as spawn_pos


def _stream_process_output(p):
    while True:
        line = p.stdout.readline()
        if not line:
            break
        try:
            if isinstance(line, bytes):
                try:
                    line = line.decode("utf-8", "replace")
                except Exception:
                    line = str(line)
            print(line.rstrip("\r\n"))
        except Exception:
            pass


def _get_prompt_from_input_or_group(nuke_module, g):
    prompt = (g.knob("prompt").value() or "").strip()

    try:
        src = g.input(0)
    except Exception:
        src = None

    if src is not None:
        try:
            k = src.knob("message")
        except Exception:
            k = None
        if k is not None:
            try:
                msg = (k.value() or "").strip()
            except Exception:
                msg = ""
            if msg:
                return msg
        else:
            try:
                cls = src.Class()
            except Exception:
                cls = "<unknown>"
            try:
                nuke_module.message(
                    "Input 0 (prompt_text) is connected, but it's not a Text node (missing 'message' knob).\n\n"
                    "Connected node class: %s\n\n"
                    "Disconnect it or plug a Text node here. Execution cancelled." % cls
                )
            except Exception:
                pass
            raise Exception("prompt_input_not_text_node")

    return prompt


def _collect_reference_images(nuke_module, group_node, frame, temp_dir):
    """
    Collect 1..2 reference image paths from external inputs 1 and 2.
    If the input is a suitable Read, use its resolved file directly; otherwise pre-render a still.
    """
    images = []
    for idx in (1, 2):
        try:
            n = group_node.input(idx)
        except Exception:
            n = None
        if n is None:
            continue
        try:
            images.append(
                prerender.prepare_still_input_path(
                    nuke_module=nuke_module,
                    src_node=n,
                    frame=frame,
                    run_dir=temp_dir,
                    base_name="ref_image_%d" % idx,
                )
            )
        except Exception as e:
            raise Exception("Reference image input %d error: %s" % (idx, str(e)))
    return images


def main():
    import nuke  # imported inside for Nuke environment

    g = nuke.thisNode()

    prompt = _get_prompt_from_input_or_group(nuke, g)
    if not prompt:
        nuke.message("Prompt is empty (and no input Text node message found).")
        raise Exception("missing prompt")

    frame = int(nuke.frame())

    num_images_s = (g.knob("num_images").value() or "1").strip()
    image_size = (g.knob("image_size").value() or "auto").strip() or "auto"
    quality = (g.knob("quality").value() or "high").strip()
    output_format = (g.knob("output_format").value() or "png").strip().lower()
    try:
        num_images = int(num_images_s)
    except Exception:
        num_images = 1
    num_images = max(1, min(4, int(num_images)))

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="gpt_image_2_edit",
    )

    ref_images = _collect_reference_images(nuke, g, frame=frame, temp_dir=temp_dir)
    if not ref_images:
        nuke.message(
            "At least one reference image is required.\n\n"
            "Connect a still image to input 1 (ref_image_a), and optionally input 2 (ref_image_b)."
        )
        raise Exception("missing reference image")

    mask_path = None
    try:
        mask_node = g.input(3)
    except Exception:
        mask_node = None
    if mask_node is not None:
        try:
            mask_path = prerender.prepare_still_input_path(
                nuke_module=nuke,
                src_node=mask_node,
                frame=frame,
                run_dir=temp_dir,
                base_name="mask",
            )
        except Exception as e:
            nuke.message("Failed to prepare mask image:\n%s" % str(e))
            raise

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
        "--image-size",
        image_size,
        "--quality",
        quality,
        "--verbose",
    ]

    for img in ref_images:
        args += ["--image", img]

    if mask_path:
        args += ["--mask", mask_path]

    env = os.environ.copy()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message(
            "GPT Image 2 helper failed (exit %d). Check the Script Editor output for details." % p.returncode
        )
        raise Exception("GPT Image 2 helper failed")

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    created = []
    placed = []
    for i in range(1, int(num_images) + 1):
        out_name = "image_%03d.%s" % (i, output_format)
        out_path = os.path.join(out_dir, out_name)
        if not os.path.isfile(out_path):
            continue
        out_path_nk = prerender.norm_slashes(out_path)

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
                r.knob("label").setValue("GPT Image 2 Edit\n%s" % out_path_nk)
            except Exception:
                pass
            r.setXpos(fx)
            r.setYpos(fy)
            placed.append(r)
            created.append(out_path_nk)
        finally:
            nuke.endGroup()

    if not created:
        nuke.message("Helper finished, but no output images were found in:\n%s" % out_dir)
        raise Exception("no outputs")

    if bool(g.knob("show_success_popup").value()):
        nuke.message("GPT Image 2 edit output created:\n" + "\n".join(created))


if __name__ == "__main__":
    main()
