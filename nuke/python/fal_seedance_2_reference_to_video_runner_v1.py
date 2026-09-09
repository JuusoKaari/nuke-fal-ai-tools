# Purpose:
# - Runner script for the Nuke Group node `Seedance_2_Reference_To_Video_v1` (executes inside Nuke / Python 2.7).
# - Collects named still inputs image_1..image_9, optional video_1..video_3, and optional audio file knobs.
# - Stills use Read fast-path or prerender; videos use Read fast-path or prerender via prepare_video_input_path.
# - Calls `fal_seedance_2_reference_to_video_helper.py` via subprocess, then creates a Read for the result
#   (DWAB EXR sequence by default; MP4 if chosen in Settings).
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
import nuke_video_output_v1 as video_out

_IMAGE_INPUTS = tuple(("image_%d" % i, i - 1) for i in range(1, 10))
_VIDEO_INPUTS = tuple(("video_%d" % i, 8 + i) for i in range(1, 4))
_MAX_TOTAL_FILES = 12


def _named_input_index(group_node, input_name, fallback):
    try:
        return int(group_node.inputIndex(input_name))
    except Exception:
        return int(fallback)


def _named_input_node(group_node, input_name, fallback):
    idx = _named_input_index(group_node, input_name, fallback)
    try:
        return group_node.input(idx)
    except Exception:
        return None


def _collect_images(nuke_module, group_node, frame, temp_dir):
    images = []
    for input_name, fallback in _IMAGE_INPUTS:
        n = _named_input_node(group_node, input_name, fallback)
        if n is None:
            continue
        try:
            images.append(
                prerender.prepare_still_input_path(
                    nuke_module=nuke_module,
                    src_node=n,
                    frame=frame,
                    run_dir=temp_dir,
                    base_name=input_name,
                )
            )
        except Exception as e:
            raise Exception("%s error: %s" % (input_name, str(e)))
    return images


def _collect_videos(nuke_module, group_node, frame, default_first, default_last, temp_dir):
    videos = []
    for input_name, fallback in _VIDEO_INPUTS:
        n = _named_input_node(group_node, input_name, fallback)
        if n is None:
            continue
        try:
            videos.append(
                prerender.prepare_video_input_path(
                    nuke_module=nuke_module,
                    src_node=n,
                    frame=frame,
                    default_first=default_first,
                    default_last=default_last,
                    run_dir=temp_dir,
                    base_name=input_name,
                )
            )
        except Exception as e:
            raise Exception("%s error: %s" % (input_name, str(e)))
    return videos


def _collect_audio_paths(group_node):
    paths = []
    for i in range(1, 4):
        raw = ""
        try:
            raw = (group_node.knob("audio_%d" % i).value() or "").strip()
        except Exception:
            raw = ""
        if raw:
            paths.append(raw)
    return paths


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    prompt = (g.knob("prompt").value() or "").strip()
    if not prompt:
        nuke.message("Prompt is empty.")
        raise Exception("missing prompt")

    duration_s = (g.knob("duration").value() or "auto").strip()
    resolution = (g.knob("resolution").value() or "720p").strip()
    aspect_ratio = (g.knob("aspect_ratio").value() or "auto").strip()
    bitrate_mode = (g.knob("bitrate_mode").value() or "standard").strip()
    generate_audio = bool(g.knob("generate_audio").value())

    frame = int(nuke.frame())
    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="seedance_2_r2v",
        group_node=g,
    )

    try:
        image_paths = _collect_images(nuke, g, frame, temp_dir)
        video_paths = _collect_videos(
            nuke, g, frame, default_first, default_last, temp_dir
        )
    except Exception as e:
        nuke.message("Failed to prepare reference inputs:\n%s" % str(e))
        raise

    audio_paths = _collect_audio_paths(g)
    for p in audio_paths:
        if not os.path.isfile(p):
            nuke.message("Audio file not found:\n%s" % p)
            raise Exception("missing audio file")

    if not image_paths and not video_paths:
        nuke.message(
            "Connect at least one still (image_1..) or video (video_1..).\n"
            "Refer to connected files in the prompt as @Image1, @Video1, @Audio1, ..."
        )
        raise Exception("missing reference image or video")

    total_files = len(image_paths) + len(video_paths) + len(audio_paths)
    if total_files > _MAX_TOTAL_FILES:
        nuke.message(
            "Total files across images, videos, and audio must not exceed %d.\nGot %d."
            % (_MAX_TOTAL_FILES, total_files)
        )
        raise Exception("too many reference files")

    out_path = os.path.join(out_dir, "seedance_2_r2v_%s.mp4" % ts)

    extra_args = [
        "--prompt",
        prompt,
        "--out",
        out_path,
        "--duration",
        duration_s,
        "--resolution",
        resolution,
        "--aspect-ratio",
        aspect_ratio,
        "--bitrate-mode",
        bitrate_mode,
        "--verbose",
    ]
    for p in image_paths:
        extra_args += ["--image", p]
    for p in video_paths:
        extra_args += ["--video", p]
    for p in audio_paths:
        extra_args += ["--audio", p]

    if generate_audio:
        extra_args += ["--generate-audio"]
    else:
        extra_args += ["--no-generate-audio"]

    returncode, _stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Seedance 2 Reference to Video'
    )

    display_path = video_out.spawn_video_output_read(
        nuke, g, out_path, "Seedance 2.0 reference-to-video", "%s_%s" % (g.name(), ts)
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("Seedance 2.0 reference-to-video output created:\n%s" % display_path)


if __name__ == "__main__":
    main()
