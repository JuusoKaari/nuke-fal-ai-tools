# Purpose:
# - Runner script for the Nuke Group node `BiRefNet_v2` (executes inside Nuke / Python 2.7).
# - Accepts any upstream image input; if it's a suitable Read node of a sequence, uses its pattern directly
#   (no re-render), otherwise pre-renders a temporary PNG sequence from the connected pipe.
# - Calls the external Python 3 helper `fal_birefnet_v2_helper.py` to process an image sequence via fal.ai,
#   and finally creates a Read node in the main graph pointing at the resulting output sequence.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import os
import re
import subprocess
import time

import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _path_util
import _install_help

import nuke_prerender_v1 as prerender
import nuke_spawn_read_position_v1 as spawn_pos


def _ensure_dir(path):
    if path and (not os.path.isdir(path)):
        try:
            os.makedirs(path)
        except Exception:
            pass


def _norm_slashes(p):
    return (p or "").replace("\\", "/")


def _infer_pad_from_pattern(pattern):
    m_hash = re.search(r"(#+)", pattern or "")
    if m_hash:
        return len(m_hash.group(1))
    m_pct = re.search(r"%0?(\d+)d", pattern or "")
    if m_pct:
        try:
            return int(m_pct.group(1))
        except Exception:
            return 4
    return 4


def _split_cmd(cmd):
    cmd = (cmd or "").strip()
    if not cmd:
        return []
    try:
        import shlex

        return shlex.split(cmd)
    except Exception:
        return cmd.split()


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


def main():
    import nuke  # imported inside for Nuke environment

    g = nuke.thisNode()

    try:
        default_first = int(nuke.root().firstFrame())
        default_last = int(nuke.root().lastFrame())
    except Exception:
        default_first = 1
        default_last = 1

    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 is not connected.")
        raise Exception("missing input 0")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="birefnet_v2",
    )

    try:
        pattern, first, last = prerender.prepare_sequence_input_pattern(
            nuke_module=nuke,
            src_node=src_node,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="source_seq",
            pad=4,
        )
    except Exception as e:
        nuke.message("Failed to prepare input sequence:\n%s" % str(e))
        raise

    pad = _infer_pad_from_pattern(pattern)

    python3_cmd = (g.knob("python3_cmd").value() or "").strip() or "py -3"
    helper_path = _install_help.require_helper_path(
        nuke,
        (g.knob("helper_path").value() or "").strip(),
    )

    model = g.knob("model").value()
    operating_resolution = g.knob("operating_resolution").value()
    output_format = (g.knob("output_format").value() or "png").strip().lower()
    output_mask = bool(g.knob("output_mask").value())
    refine_foreground = bool(g.knob("refine_foreground").value())

    py_parts = _split_cmd(python3_cmd) or ["py", "-3"]

    args = list(py_parts) + [
        helper_path,
        "--in-pattern",
        pattern,
        "--first",
        str(int(first)),
        "--last",
        str(int(last)),
        "--out-dir",
        out_dir,
        "--model",
        model,
        "--operating-resolution",
        operating_resolution,
        "--output-format",
        output_format,
        "--pad",
        str(int(pad)),
        "--verbose",
    ]
    if output_mask:
        args += ["--output-mask"]
    if not refine_foreground:
        args += ["--no-refine-foreground"]

    # Pass auth via env var (do NOT override env with the placeholder text)
    env = os.environ.copy()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message("BiRefNet helper failed (exit %d). Check the Script Editor output for details." % p.returncode)
        raise Exception("BiRefNet helper failed")

    # Create a new Read node in the main node graph (not inside the group)
    xpos = int(g.xpos())
    ypos = int(g.ypos())

    out_pattern = os.path.join(out_dir, ("frame_%%0%dd.%s" % (int(pad), output_format)))
    out_pattern_nk = _norm_slashes(out_pattern)

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        r = nuke.nodes.Read(file=out_pattern_nk)
        try:
            r.setName("%s_result_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            r.knob("first").setValue(int(first))
            r.knob("last").setValue(int(last))
        except Exception:
            pass
        try:
            r.knob("label").setValue("BiRefNet v2\n%s" % out_pattern_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
    finally:
        nuke.endGroup()

    nuke.message("BiRefNet v2 output created:\n%s" % out_pattern_nk)


if __name__ == "__main__":
    main()

