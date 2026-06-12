# Purpose:
# - Compatibility wrapper for shared Nuke (Python 2.7) prerender utilities used by runner scripts.
# - Keeps the public API stable while implementation is split into smaller modules:
#   - `nuke_prerender_core_v1.py` (temp/output dirs, still/sequence prerender, Read fast-paths)
#   - `nuke_prerender_video_v1.py` (video prerender with ffmpeg fallback)
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Designed to be imported by runner scripts in this repository (also Python 2.7).

from __future__ import print_function

from nuke_prerender_core_v1 import (
    ensure_dir,
    helper_subprocess_env,
    is_read_node,
    looks_like_sequence_pattern,
    make_run_dir,
    make_run_dirs,
    norm_slashes,
    pick_writable_temp_dir,
    prepare_sequence_input_pattern,
    prepare_still_input_path,
    render_sequence_from_node,
    render_still_from_node,
    resolve_read_file_at_frame,
    split_cmd,
    _is_valid_video_extension,
)

from nuke_prerender_video_v1 import render_video_from_node


def prepare_video_input_path(nuke_module, src_node, frame, default_first, default_last, run_dir, base_name):
    """
    Return a video file path for any upstream node.
    - Read pointing at a single MP4/MOV file: resolves and returns it (no re-render).
    - Read with other format, or non-Read: renders a temp mp4 under `run_dir` for `default_first..default_last`.
    """
    import os

    if is_read_node(src_node):
        try:
            pat = (src_node.knob("file").value() or "").strip()
        except Exception:
            pat = ""
        if not looks_like_sequence_pattern(pat) and _is_valid_video_extension(pat):
            p = resolve_read_file_at_frame(nuke_module, src_node, frame)
            if p and os.path.isfile(p):
                return p
            raise Exception("Resolved Read video file not found: %s" % (p or "<empty>"))

    first = int(default_first)
    last = int(default_last)
    if last < first:
        first, last = last, first

    out_path = os.path.join(run_dir, "%s.mp4" % base_name)
    return render_video_from_node(nuke_module, src_node, out_path, first, last)

