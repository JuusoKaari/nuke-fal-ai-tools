# Purpose:
# - Runner script for the Nuke Group node `Veo_3_1_Extend_Video_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream video input; if it's a suitable Read node, uses its file directly (no re-render),
#   otherwise pre-renders a temp video from the connected pipe.
# - Writes a timestamped output mp4 path under a writable temp folder, then calls the external Python 3 helper
#   `fal_veo3_1_extend_video_helper.py` via subprocess, and finally creates a Read for the result
#   (DWAB EXR sequence by default; MP4 if chosen in Settings).
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

import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_read_video_frames_v1 as video_frames
import nuke_video_output_v1 as video_out


def _reload_runner_modules():
    """
    Nuke keeps imported modules cached for the session. Reload so runner picks up
    helper changes (e.g. new ffprobe utilities in nuke_read_video_frames_v1).
    """
    import _nuke_py_compat

    for mod in (prerender, video_frames, video_out):
        try:
            _nuke_py_compat.reload_module(mod)
        except Exception:
            pass


_reload_runner_modules()

import nuke_fal_runner_util_v1 as runner_util

_MAX_INPUT_SECONDS = 8.0


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

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        nuke.message("Input 0 (source_video) is not connected.")
        raise Exception("missing input 0")


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

    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)
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
        group_node=g,
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

    extra_args = [
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
        extra_args += ["--generate-audio"]
    else:
        extra_args += ["--no-generate-audio"]

    if negative_prompt:
        extra_args += ["--negative-prompt", negative_prompt]

    if seed_val is not None:
        extra_args += ["--seed", str(seed_val)]

    returncode, helper_lines = runner_util.run_group_helper(
        nuke,
        g,
        extra_args,
        'Veo 3.1 Extend Video',
        failure_formatter=lambda code, lines: (
            "Veo 3.1 extend-video helper failed (exit %d).\n\n%s"
            % (code, _summarize_helper_failure(lines))
        ),
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "Veo 3.1 extend video", "%s_result_%s" % (g.name(), ts)
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        extra = ("\n\n%s" % trim_msg) if trim_msg else ""
        nuke.message("Veo 3.1 extend-video output created:\n%s%s" % (display_path, extra))


if __name__ == "__main__":
    main()
