# Purpose:
# - Shared video-result helper for Nuke runners (Python 2.7).
# - After a fal.ai MP4 download, optionally render a DWAB EXR sequence via a
#   temp Read/Write and spawn the graph Read on that sequence.
# - Mode comes from fal.ai Settings (video_output). The MP4 is always kept.
# - Importable without Nuke for path/pattern unit tests.

from __future__ import print_function

import os
import re
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import nuke_fal_config_v1 as fal_config
import nuke_prerender_core_v1 as prerender_core
import nuke_read_video_frames_v1 as video_frames
import nuke_spawn_read_position_v1 as spawn_pos

# OpenEXR DWA: higher dwaCompressionLevel = more compression (smaller files,
# more loss). Format default is 45 (visually lossless). 200 is more compact;
# fal videos are already 8-bit H.264/H.265.
DWAB_COMPRESSION_LEVEL = 200

_HASH_RE = re.compile(r"(#+)")
_PCT_RE = re.compile(r"%0?(\d*)d")


def sequence_paths_for_mp4(mp4_path):
    """
    Return (seq_dir, nuke_pattern) for a DWAB EXR sequence next to the MP4.
    Example: out/foo.mp4 -> out/foo/foo.####.exr
    """
    mp4_path = os.path.abspath(mp4_path or "")
    stem = os.path.splitext(os.path.basename(mp4_path))[0]
    if not stem:
        stem = "video"
    seq_dir = os.path.join(os.path.dirname(mp4_path), stem)
    pattern = os.path.join(seq_dir, "%s.####.exr" % stem)
    return seq_dir, pattern


def expand_frame_pattern(pattern, frame):
    """Replace the first #### or %0Nd token with a padded frame number."""
    pattern = pattern or ""
    frame = int(frame)

    def _hash_repl(m):
        width = len(m.group(1))
        return ("%0" + str(width) + "d") % frame

    if "#" in pattern:
        return _HASH_RE.sub(_hash_repl, pattern, count=1)

    m = _PCT_RE.search(pattern)
    if m is None:
        return pattern
    width_s = m.group(1)
    if width_s:
        token = ("%0" + str(int(width_s)) + "d") % frame
    else:
        token = str(frame)
    return _PCT_RE.sub(token, pattern, count=1)


def _try_set_knob(node, name, value):
    try:
        k = node.knob(name)
    except Exception:
        k = None
    if k is None:
        return False
    try:
        k.setValue(value)
        return True
    except Exception:
        return False


def _enum_values(knob):
    try:
        vals = knob.values()
        if vals:
            return [str(v) for v in list(vals)]
    except Exception:
        pass
    try:
        n = int(knob.numValues())
        out = []
        for i in range(n):
            try:
                out.append(str(knob.enumName(i)))
            except Exception:
                out.append(str(i))
        return out
    except Exception:
        return []


def _set_enum_containing(node, knob_name, needles):
    """Set an enum knob to the first value whose label contains a needle."""
    try:
        k = node.knob(knob_name)
    except Exception:
        k = None
    if k is None:
        return False
    needles_l = [str(n).lower() for n in needles]
    values = _enum_values(k)
    for i, val in enumerate(values):
        sl = str(val).lower()
        for needle in needles_l:
            if needle in sl:
                try:
                    k.setValue(i)
                    return True
                except Exception:
                    try:
                        k.setValue(str(val))
                        return True
                    except Exception:
                        pass
    for needle in needles:
        try:
            k.setValue(needle)
            return True
        except Exception:
            pass
    return False


def _configure_exr_write(write_node, compression_level):
    """
    Set Write knobs for half-float DWAB EXR. Falls back to Zip (16 scanlines)
    when DWAB is missing (older Nuke). Raises if EXR compression cannot be set.
    """
    _try_set_knob(write_node, "file_type", "exr")
    _set_enum_containing(write_node, "datatype", ["half", "16 bit"])
    if not _set_enum_containing(write_node, "compression", ["dwab"]):
        if not _set_enum_containing(
            write_node, "compression", ["zip (16", "zip16", "zip 16"]
        ):
            raise Exception(
                "Write node has no DWAB (or Zip 16) EXR compression knob."
            )
    for name in ("dw_compression_level", "dwaCompressionLevel", "compression_level"):
        if _try_set_knob(write_node, name, float(compression_level)):
            break
    _try_set_knob(write_node, "channels", "rgb")


def _set_read_frame_range(read_node, first, last):
    first = int(first)
    last = int(last)
    for name in ("first", "origfirst"):
        _try_set_knob(read_node, name, first)
    for name in ("last", "origlast"):
        _try_set_knob(read_node, name, last)


def _delete_node(nuke_module, node):
    if node is None:
        return
    try:
        nuke_module.delete(node)
    except Exception:
        pass


def _undo_disable(nuke_module):
    try:
        nuke_module.Undo.disable()
        return True
    except Exception:
        return False


def _undo_enable(nuke_module):
    try:
        nuke_module.Undo.enable()
    except Exception:
        pass


def render_mp4_to_dwab_exr(
    nuke_module, mp4_path, compression_level=None, log_print=None
):
    """
    Read an MP4 in Nuke and Write a DWAB EXR sequence next to it.
    Returns (pattern, first, last). Raises on failure. Temp nodes are deleted.
    """
    mp4_path = os.path.abspath(mp4_path)
    if not os.path.isfile(mp4_path):
        raise Exception("MP4 not found: %s" % prerender_core.norm_slashes(mp4_path))

    n = video_frames.get_video_frame_count(mp4_path)
    if n is None or int(n) < 1:
        raise Exception(
            "Could not probe MP4 frame count (need ffprobe on PATH): %s"
            % prerender_core.norm_slashes(mp4_path)
        )
    first = 1
    last = int(n)
    if compression_level is None:
        compression_level = DWAB_COMPRESSION_LEVEL

    seq_dir, pattern = sequence_paths_for_mp4(mp4_path)
    prerender_core.ensure_dir(seq_dir)
    pattern_nk = prerender_core.norm_slashes(pattern)
    mp4_nk = prerender_core.norm_slashes(mp4_path)

    if log_print:
        try:
            log_print(
                "nuke_video_output_v1: rendering DWAB EXR %s (%d-%d)"
                % (pattern_nk, first, last)
            )
        except Exception:
            pass

    undo_off = _undo_disable(nuke_module)
    read_node = None
    write_node = None
    began_root = False
    try:
        nuke_module.root().begin()
        began_root = True
        read_node = nuke_module.nodes.Read(file=mp4_nk)
        _set_read_frame_range(read_node, first, last)
        try:
            read_node.setXpos(100000)
            read_node.setYpos(100000)
        except Exception:
            pass

        write_node = nuke_module.nodes.Write()
        write_node.setInput(0, read_node)
        if not _try_set_knob(write_node, "file", pattern_nk):
            try:
                write_node["file"].setValue(pattern_nk)
            except Exception:
                raise Exception("Could not set Write file path.")
        _configure_exr_write(write_node, compression_level)
        try:
            write_node.setXpos(100040)
            write_node.setYpos(100000)
        except Exception:
            pass

        prerender_core._execute_write_full_res(nuke_module, write_node, first, last)
    finally:
        _delete_node(nuke_module, write_node)
        _delete_node(nuke_module, read_node)
        if began_root:
            try:
                nuke_module.endGroup()
            except Exception:
                pass
        if undo_off:
            _undo_enable(nuke_module)

    first_file = expand_frame_pattern(pattern, first)
    prerender_core.require_rendered_file(first_file, "DWAB EXR sequence")
    last_file = expand_frame_pattern(pattern, last)
    if last != first and (not os.path.isfile(last_file)):
        raise Exception(
            "DWAB EXR sequence incomplete (missing last frame):\n%s"
            % prerender_core.norm_slashes(last_file)
        )
    return pattern, first, last


def spawn_video_output_read(
    nuke_module,
    group_node,
    mp4_path,
    label,
    read_name,
    y_offset=140,
):
    """
    Spawn a root-graph Read for a downloaded video result.
    Default Settings mode renders a DWAB EXR sequence first; MP4 is kept.
    On EXR failure, falls back to a Read on the MP4 and shows a message.
    Returns the Nuke-slash path shown on the Read.
    """
    mp4_path = os.path.abspath(mp4_path)
    mp4_nk = prerender_core.norm_slashes(mp4_path)
    if not os.path.isfile(mp4_path):
        nuke_module.message("Helper finished, but output file was not found:\n%s" % mp4_nk)
        raise Exception("missing output mp4")

    mode = fal_config.get_video_output()
    file_path = mp4_path
    first = None
    last = None
    is_sequence = False
    warn = None

    if mode == fal_config.VIDEO_OUTPUT_EXR_SEQUENCE:
        try:
            file_path, first, last = render_mp4_to_dwab_exr(nuke_module, mp4_path)
            is_sequence = True
        except Exception as e:
            warn = str(e)
            file_path = mp4_path
            is_sequence = False

    file_nk = prerender_core.norm_slashes(file_path)
    xpos = int(group_node.xpos())
    ypos = int(group_node.ypos())

    nuke_module.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke_module, xpos, ypos + int(y_offset))
        r = nuke_module.nodes.Read(file=file_nk)
        try:
            r.setName(str(read_name), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("%s\n%s" % (label, file_nk))
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
        if is_sequence and first is not None and last is not None:
            _set_read_frame_range(r, first, last)
        else:
            try:
                video_frames.set_read_frame_range_from_video_file(r, mp4_path)
            except Exception:
                pass
    finally:
        nuke_module.endGroup()

    if warn:
        try:
            nuke_module.message(
                "DWAB EXR sequence render failed; spawned a Read on the MP4 "
                "instead.\n\n%s\n\n%s" % (warn, mp4_nk)
            )
        except Exception:
            pass

    return file_nk
