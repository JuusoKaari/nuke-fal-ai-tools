# Purpose:
# - Video pre-render helper for Nuke Group-node runner scripts (Python 2.7).
# - Renders a connected pipe to a video file by:
#   - Rendering a temp PNG sequence from Nuke.
#   - Encoding that sequence to H.264 mp4 using ffmpeg.
# - The first encode is CRF 18. When the caller passes max_bytes, a file that is
#   still over that cap is re-encoded down the CRF ladder (20, 23, 28, 32).
# - libx264 + yuv420p need even width and height, so encode snaps odd axes down by 1px.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Used by `nuke_prerender_v1.py` as the implementation behind `prepare_video_input_path`.

from __future__ import print_function

import os
import subprocess

from nuke_prerender_core_v1 import ensure_dir, render_sequence_from_node

# Drop 1px on any odd axis. pad would add a black line; 1px scale is invisible.
_EVEN_DIM_VF = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

# High quality first, then the historical ffmpeg default (23), then smaller files.
_CRF_LADDER = (18, 20, 23, 28, 32)

# fal schema upload caps. Callers pass these as max_bytes.
# Kling max_file_size is 209715200 (200 * 1024 * 1024).
KLING_O3_V2V_MAX_BYTES = 200 * 1024 * 1024
# Seedance 2.0 reference: combined video size under 50 MB.
SEEDANCE_20_REFERENCE_TOTAL_BYTES = 50 * 1024 * 1024
# Seedance 2.5 reference: each video no larger than 200 MB.
SEEDANCE_25_REFERENCE_MAX_BYTES = 200 * 1024 * 1024


def format_mib(num_bytes):
    """Size label in MiB, printed as MB. ASCII-only for Nuke Python 2."""
    try:
        value = float(num_bytes) / float(1024 * 1024)
    except Exception:
        value = 0.0
    return "%.1f MB" % value


def split_byte_budget(total_bytes, count):
    """Equal per-file cap so several videos stay under one combined upload limit."""
    try:
        count = int(count)
        total_bytes = int(total_bytes)
    except Exception:
        return None
    if count < 1 or total_bytes < 1:
        return None
    return int(total_bytes // count)


def _ffmpeg_exists():
    try:
        p = subprocess.Popen(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.communicate()
        return p.returncode == 0
    except Exception:
        return False


def ffmpeg_encode_args(pattern, first, fps, out_path, crf=18):
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(float(fps)),
        "-start_number",
        str(int(first)),
        "-i",
        pattern,
        "-vf",
        _EVEN_DIM_VF,
        "-c:v",
        "libx264",
        "-crf",
        str(int(crf)),
        "-pix_fmt",
        "yuv420p",
        out_path,
    ]


def ffmpeg_transcode_args(in_path, out_path, crf):
    """Recompress an existing movie. Video only, matching the PNG prerender."""
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        in_path,
        "-vf",
        _EVEN_DIM_VF,
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        str(int(crf)),
        "-pix_fmt",
        "yuv420p",
        out_path,
    ]


def _run_ffmpeg(args):
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = []
    while True:
        line = p.stdout.readline()
        if not line:
            break
        try:
            if isinstance(line, bytes):
                line = line.decode("utf-8", "replace")
        except Exception:
            pass
        try:
            out.append((line or "").rstrip("\r\n"))
        except Exception:
            pass
    p.wait()
    return p.returncode, "\n".join(out[-40:])


def _encode_or_raise(args, out_path):
    code, tail = _run_ffmpeg(args)
    if code != 0 or (not os.path.isfile(out_path)):
        raise Exception("ffmpeg encode failed (exit %d).\n%s" % (int(code), tail))


def encode_down_to_size(encode_at_crf, out_path, max_bytes, ladder=None):
    """
    encode_at_crf(crf) writes out_path.
    With no max_bytes, encode once at the first CRF.
    Otherwise step down the ladder until the file fits.
    """
    if not ladder:
        ladder = _CRF_LADDER
    last_size = None
    for index, crf in enumerate(ladder):
        encode_at_crf(crf)
        if not os.path.isfile(out_path):
            raise Exception("ffmpeg encode produced no file: %s" % out_path)
        last_size = int(os.path.getsize(out_path))
        if max_bytes is None or last_size <= int(max_bytes):
            if index > 0:
                print(
                    "Input video fits at CRF %d (%s, cap %s)."
                    % (int(crf), format_mib(last_size), format_mib(max_bytes))
                )
            return out_path
        if index + 1 < len(ladder):
            print(
                "Input video at CRF %d is %s, over the %s cap. Retrying at CRF %d."
                % (
                    int(crf),
                    format_mib(last_size),
                    format_mib(max_bytes),
                    int(ladder[index + 1]),
                )
            )
    raise Exception(
        "Input video is %s at CRF %d, over the %s upload cap. Shorten the frame range."
        % (format_mib(last_size), int(ladder[-1]), format_mib(max_bytes))
    )


def _distinct_out_path(in_path, out_path):
    in_path = os.path.abspath(in_path)
    out_path = os.path.abspath(out_path)
    if in_path != out_path:
        return out_path
    root, ext = os.path.splitext(out_path)
    return root + "_fit" + (ext or ".mp4")


def fit_existing_video(in_path, out_path, max_bytes):
    """
    Recompress an existing movie down the CRF ladder until it fits max_bytes.
    Drops audio. Callers keep the original file when it is already under the cap.
    """
    if not _ffmpeg_exists():
        raise Exception("ffmpeg was not found on PATH (required for video prerender).")
    out_path = _distinct_out_path(in_path, out_path)
    ensure_dir(os.path.dirname(out_path))
    try:
        size = int(os.path.getsize(in_path))
    except Exception:
        size = 0
    print(
        "Input video is %s, over the %s cap. Recompressing to H.264."
        % (format_mib(size), format_mib(max_bytes))
    )

    def _encode(crf):
        _encode_or_raise(ffmpeg_transcode_args(in_path, out_path, crf), out_path)

    return encode_down_to_size(_encode, out_path, max_bytes)


def render_video_from_node(nuke_module, src_node, out_path, first, last, max_bytes=None):
    """
    Render to mp4 by PNG sequence + ffmpeg encode (requires ffmpeg on PATH).
    Starts at CRF 18. When max_bytes is set, lowers quality until the file fits.
    """
    out_path = os.path.abspath(out_path)
    ensure_dir(os.path.dirname(out_path))

    if not _ffmpeg_exists():
        raise Exception("ffmpeg was not found on PATH (required for video prerender).")

    pad = 4
    seq_pattern = os.path.join(os.path.dirname(out_path), "frames_%0" + str(pad) + "d.png")
    render_sequence_from_node(nuke_module, src_node, seq_pattern, first, last)

    try:
        fps = float(nuke_module.root().fps())
    except Exception:
        fps = 25.0

    def _encode(crf):
        _encode_or_raise(ffmpeg_encode_args(seq_pattern, first, fps, out_path, crf), out_path)

    return encode_down_to_size(_encode, out_path, max_bytes)
