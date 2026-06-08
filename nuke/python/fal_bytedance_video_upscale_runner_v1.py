# Purpose:
# - Runner for the Nuke Group node `ByteDance_Video_Upscale_v1` (executes inside Nuke / Python 2.7).
# - Accepts upstream video on input 0; uses Read file when possible, otherwise pre-renders to a temp mp4/mov.
# - Calls `fal_bytedance_video_upscale_helper.py` (Python 3) via subprocess, then adds a Read for the result.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3).

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
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos


def _norm_slashes(p):
    return (p or "").replace("\\", "/")


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


def _get_frame_range_from_knobs(group_node, nuke_module):
    try:
        mode = (group_node.knob("frame_range").value() or "root").strip().lower()
    except Exception:
        mode = "root"

    if mode == "current":
        f = int(nuke_module.frame())
        return f, f

    if mode == "custom":
        try:
            start = int(float((group_node.knob("custom_start").value() or "1").strip()))
            end = int(float((group_node.knob("custom_end").value() or "1").strip()))
            if end < start:
                start, end = end, start
            return start, end
        except Exception:
            pass

    try:
        start = int(nuke_module.root().firstFrame())
        end = int(nuke_module.root().lastFrame())
    except Exception:
        start = 1
        end = 1
    if end < start:
        start, end = end, start
    return start, end


def main():
    import nuke

    g = nuke.thisNode()
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        nuke.message("Input 0 (source_video) is not connected.")
        raise Exception("missing input 0")

    def _enum_knob_str(knob_name, choices, default):
        try:
            k = g.knob(knob_name)
            v = k.value()
            if isinstance(v, int):
                if 0 <= v < len(choices):
                    return choices[v]
                return default
            s = (str(v) or default).strip()
            return s if s in choices else default
        except Exception:
            return default

    target_resolution = _enum_knob_str("target_resolution", ("1080p", "2k", "4k"), "1080p")
    target_fps = _enum_knob_str("target_fps", ("30fps", "60fps"), "30fps")

    default_first, default_last = _get_frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="bytedance_video_upscale",
    )

    try:
        video_path = prerender.prepare_video_input_path(
            nuke_module=nuke,
            src_node=src_video_node,
            frame=frame,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="source_video",
        )
    except Exception as e:
        nuke.message("Failed to prepare source video:\n%s" % str(e))
        raise

    out_path = os.path.join(out_dir, "bytedance_video_upscale_%s.mp4" % ts)
    out_path_nk = _norm_slashes(out_path)

    python3_cmd = (g.knob("python3_cmd").value() or "").strip() or "py -3"
    helper_path = _install_help.require_helper_path(
        nuke,
        (g.knob("helper_path").value() or "").strip(),
    )

    py_parts = _split_cmd(python3_cmd) or ["py", "-3"]
    args = list(py_parts) + [
        helper_path,
        "--video",
        video_path,
        "--out",
        out_path,
        "--target-resolution",
        target_resolution,
        "--target-fps",
        target_fps,
        "--verbose",
    ]

    env = os.environ.copy()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        nuke.message(
            "Bytedance video upscale helper failed (exit %d). Check the Script Editor output for details."
            % p.returncode
        )
        raise Exception("Bytedance upscale helper failed")

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        r = nuke.nodes.Read(file=out_path_nk)
        try:
            r.setName("%s_result_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("Bytedance video upscale\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
        try:
            video_frames.set_read_frame_range_from_video_file(r, out_path)
        except Exception:
            pass
    finally:
        nuke.endGroup()

    if bool(g.knob("show_success_popup").value()):
        nuke.message("Bytedance upscale output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
