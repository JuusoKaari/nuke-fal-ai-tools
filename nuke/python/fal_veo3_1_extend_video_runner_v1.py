# Purpose:
# - Runner script for the Nuke Group node `Veo_3_1_Extend_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream video input; if it's a suitable Read node, uses its file directly (no re-render),
#   otherwise pre-renders a temp video from the connected pipe.
# - Writes a timestamped output mp4 path under a writable temp folder, then calls the external Python 3 helper
#   `fal_veo3_1_extend_video_helper.py` via subprocess, and finally creates a Read node in the main graph
#   pointing at the resulting video (frame range set via `nuke_read_video_frames_v1`).
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import os
import subprocess
import time

import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _path_util
import _install_help
import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos


def _reload_runner_modules():
    """
    Nuke keeps imported modules cached for the session. Reload so runner picks up
    helper changes (e.g. new ffprobe utilities in nuke_read_video_frames_v1).
    """
    import _nuke_py_compat

    for mod in (prerender, video_frames, spawn_pos):
        try:
            _nuke_py_compat.reload_module(mod)
        except Exception:
            pass


_reload_runner_modules()

_MAX_INPUT_SECONDS = 8.0


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
    lines = []
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
            text = line.rstrip("\r\n")
            lines.append(text)
            print(text)
        except Exception:
            pass
    return lines


def _cap_frame_range_to_max_seconds(first, last, fps, max_seconds):
    try:
        max_frames = max(1, int(round(float(max_seconds) * float(fps))))
    except Exception:
        max_frames = max(1, int(max_seconds * 25.0))
    span = int(last) - int(first) + 1
    if span > max_frames:
        first = int(last) - max_frames + 1
    return int(first), int(last)


def _probe_video_duration_seconds(path):
    fn = getattr(video_frames, "get_video_duration_seconds", None)
    if callable(fn):
        return fn(path)
    return None


def _trim_video_tail_if_needed(in_path, temp_dir, base_name, max_seconds):
    """
    Veo extend accepts input clips up to 8s. Keep the tail (continuation point) if longer.
    Returns (path_to_use, info_message_or_None).
    """
    dur = _probe_video_duration_seconds(in_path)
    if dur is None or dur <= float(max_seconds) + 0.05:
        return in_path, None

    out_path = os.path.join(temp_dir, "%s_tail_%ds.mp4" % (base_name, int(max_seconds)))
    start = max(0.0, float(dur) - float(max_seconds))
    args = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(start),
        "-i",
        in_path,
        "-t",
        str(float(max_seconds)),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        out_path,
    ]
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.communicate()[0]
        if p.returncode != 0:
            tail = ""
            try:
                if isinstance(out, bytes):
                    tail = out.decode("utf-8", "replace")
                else:
                    tail = str(out or "")
            except Exception:
                tail = ""
            raise Exception("ffmpeg trim failed (exit %d):\n%s" % (p.returncode, tail[-800:]))
    except Exception as e:
        raise Exception("Failed to trim input video to last %.0fs:\n%s" % (max_seconds, str(e)))

    if not os.path.isfile(out_path):
        raise Exception("Trimmed video was not created: %s" % out_path)

    msg = "Input was %.1fs; sent last %.0fs to Veo extend API." % (dur, max_seconds)
    print(msg)
    return out_path, msg


def _summarize_helper_failure(lines):
    err_lines = []
    for ln in lines or []:
        s = (ln or "").strip()
        if not s:
            continue
        if s.startswith("ERROR:") or s.startswith("WARNING:"):
            err_lines.append(s)
    if err_lines:
        return "\n".join(err_lines[-12:])
    tail = [ln for ln in (lines or []) if (ln or "").strip()][-8:]
    if tail:
        return "\n".join(tail)
    return "No helper output captured. Check Script Editor."


def main():
    import nuke  # imported inside for Nuke environment

    g = nuke.thisNode()
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        nuke.message("Input 0 (source_video) is not connected.")
        raise Exception("missing input 0")

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

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    aspect_ratio = (g.knob("aspect_ratio").value() or "auto").strip()
    generate_audio = bool(g.knob("generate_audio").value())
    negative_prompt = (g.knob("negative_prompt").value() or "").strip()
    safety_tolerance = (g.knob("safety_tolerance").value() or "4").strip()

    seed_raw = (g.knob("seed").value() or "").strip()
    seed_val = None
    if seed_raw:
        try:
            seed_val = int(float(seed_raw))
        except Exception:
            nuke.message("Seed must be an integer (or leave empty).")
            raise Exception("invalid seed")

    default_first, default_last = _get_frame_range_from_knobs(g, nuke)
    try:
        fps = float(nuke.root().fps())
    except Exception:
        fps = 25.0
    default_first, default_last = _cap_frame_range_to_max_seconds(
        default_first, default_last, fps, _MAX_INPUT_SECONDS
    )

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="veo3_1_extend_video",
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

    trim_msg = None
    try:
        video_path, trim_msg = _trim_video_tail_if_needed(
            video_path, temp_dir, "source_video", _MAX_INPUT_SECONDS
        )
    except Exception as e:
        nuke.message("Failed to trim source video for Veo extend:\n%s" % str(e))
        raise

    wh_fn = getattr(video_frames, "get_video_width_height", None)
    w, h = (wh_fn(video_path) if callable(wh_fn) else (None, None))
    allowed = {(1280, 720), (1920, 1080), (720, 1280), (1080, 1920)}
    if w and h and (w, h) not in allowed:
        nuke.message(
            "Source video is %dx%d.\n\n"
            "Veo 3.1 extend requires 720p or 1080p in 16:9 or 9:16 "
            "(1280x720, 1920x1080, 720x1280, or 1080x1920).\n"
            "Reformat the plate before extending."
            % (w, h)
        )
        raise Exception("unsupported input resolution")

    out_path = os.path.join(out_dir, "veo3_1_extend_video_%s.mp4" % ts)
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
        "--prompt",
        prompt,
        "--out",
        out_path,
        "--aspect-ratio",
        aspect_ratio,
        "--max-input-seconds",
        str(_MAX_INPUT_SECONDS),
        "--safety-tolerance",
        safety_tolerance,
        "--verbose",
    ]

    if generate_audio:
        args += ["--generate-audio"]
    else:
        args += ["--no-generate-audio"]

    if negative_prompt:
        args += ["--negative-prompt", negative_prompt]

    if seed_val is not None:
        args += ["--seed", str(seed_val)]

    env = prerender.helper_subprocess_env()
    fal_knob = (g.knob("FAL").value() or "").strip()
    if fal_knob and ("insert your secret" not in fal_knob.lower()):
        env.update({"FAL_KEY": fal_knob})

    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, env=env)
    helper_lines = _stream_process_output(p)
    p.wait()

    if p.returncode != 0:
        summary = _summarize_helper_failure(helper_lines)
        nuke.message(
            "Veo 3.1 extend-video helper failed (exit %d).\n\n%s"
            % (p.returncode, summary)
        )
        raise Exception("Veo 3.1 extend-video helper failed")

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
            r.knob("label").setValue("Veo 3.1 extend video\n%s" % out_path_nk)
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

    if _nuke_runner_launcher.should_show_success_popup(g):
        extra = ("\n\n%s" % trim_msg) if trim_msg else ""
        nuke.message("Veo 3.1 extend-video output created:\n%s%s" % (out_path_nk, extra))


if __name__ == "__main__":
    main()
