# Purpose:
# - Python 2.7 helpers for Nuke runner scripts: set `Read` node `first`/`last` from real video length.
# - Movie files often default to frame 1-1 until metadata is applied; we probe with `ffprobe` (same family as
#   `ffmpeg`, already required by `nuke_prerender_video_v1.py`).
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - If `ffprobe` is missing or probing fails, leaves the Read node unchanged.

from __future__ import print_function

import json
import os
import subprocess


def _ffprobe_on_path():
    try:
        p = subprocess.Popen(["ffprobe", "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.communicate()
        return p.returncode == 0
    except Exception:
        return False


def _parse_rational_fps(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        if "/" in s:
            a, b = s.split("/", 1)
            return float(a) / float(b)
        return float(s)
    except Exception:
        return None


def _int_from_ffprobe_field(val):
    if val is None:
        return None
    try:
        s = str(val).strip()
    except Exception:
        return None
    if not s or s.upper() in ("N/A", "NA"):
        return None
    try:
        f = float(s)
        if f <= 0:
            return None
        return int(round(f))
    except Exception:
        return None


def get_video_duration_seconds(path):
    """
    Return video duration in seconds from ffprobe, or None if unknown.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    if not _ffprobe_on_path():
        return None

    args = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=duration",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        path,
    ]
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
    except Exception:
        return None
    if p.returncode != 0:
        return None

    try:
        if out is None:
            return None
        if isinstance(out, bytes):
            text = out.decode("utf-8", "replace")
        else:
            text = out
        data = json.loads(text)
    except Exception:
        return None

    streams = data.get("streams")
    if isinstance(streams, list) and streams:
        st = streams[0]
        if isinstance(st, dict) and st.get("duration") is not None:
            try:
                dur = float(st.get("duration"))
                if dur > 0:
                    return dur
            except Exception:
                pass

    fmt = data.get("format")
    if isinstance(fmt, dict) and fmt.get("duration") is not None:
        try:
            dur = float(fmt.get("duration"))
            if dur > 0:
                return dur
        except Exception:
            pass
    return None


def get_video_width_height(path):
    """
    Return (width, height) of the first video stream, or (None, None) if unknown.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None, None
    if not _ffprobe_on_path():
        return None, None

    args = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        path,
    ]
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
    except Exception:
        return None, None
    if p.returncode != 0:
        return None, None

    try:
        if isinstance(out, bytes):
            text = out.decode("utf-8", "replace")
        else:
            text = out
        data = json.loads(text)
    except Exception:
        return None, None

    streams = data.get("streams")
    if not isinstance(streams, list) or not streams:
        return None, None
    st = streams[0]
    if not isinstance(st, dict):
        return None, None
    try:
        w = int(st.get("width"))
        h = int(st.get("height"))
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return None, None


def get_video_frame_count(path):
    """
    Return the number of frames in the video stream, or None if unknown.
    Uses ffprobe JSON (nb_frames when reliable, else duration * frame rate).
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    if not _ffprobe_on_path():
        return None

    args = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_frames,duration,avg_frame_rate,r_frame_rate",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        path,
    ]
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
    except Exception:
        return None
    if p.returncode != 0:
        return None

    try:
        if out is None:
            return None
        if isinstance(out, bytes):
            text = out.decode("utf-8", "replace")
        else:
            text = out
        data = json.loads(text)
    except Exception:
        return None

    streams = data.get("streams")
    if not isinstance(streams, list) or not streams:
        return None
    st = streams[0]
    if not isinstance(st, dict):
        return None

    n = _int_from_ffprobe_field(st.get("nb_frames"))
    if n is not None and n > 0:
        return n

    fmt = data.get("format")
    fmt_dur = None
    if isinstance(fmt, dict):
        fmt_dur = fmt.get("duration")

    dur_s = None
    try:
        if st.get("duration") is not None:
            dur_s = float(st.get("duration"))
        elif fmt_dur is not None:
            dur_s = float(fmt_dur)
    except Exception:
        dur_s = None

    fps = _parse_rational_fps(st.get("avg_frame_rate"))
    if fps is None or fps <= 0:
        fps = _parse_rational_fps(st.get("r_frame_rate"))
    if dur_s is None or fps is None or fps <= 0:
        return None

    try:
        n = int(round(float(dur_s) * float(fps)))
    except Exception:
        return None
    if n < 1:
        return None
    return n


def set_read_frame_range_from_video_file(read_node, path, log_print=None):
    """
    Set `first` to 1 and `last` to the probed frame count for a video `Read` node.
    Returns True if knobs were updated.
    """
    n = get_video_frame_count(path)
    if n is None or n < 1:
        if log_print:
            try:
                log_print(
                    "nuke_read_video_frames_v1: could not probe frame count for %s (need ffprobe on PATH?)"
                    % path
                )
            except Exception:
                pass
        return False
    try:
        read_node.knob("first").setValue(1)
        read_node.knob("last").setValue(int(n))
        return True
    except Exception:
        return False
