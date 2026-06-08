# Purpose:
# - Core shared Python 2.7 utilities for Nuke Group-node runners to accept *any* upstream input pipe.
# - If the input is a suitable `Read` node with a valid format (PNG/JPG for images, MP4/MOV for video),
#   returns its file/pattern directly (no re-render).
# - Otherwise, pre-renders a still image or image sequence to a writable temp folder (`nuke_fal_temp`) and returns that path/pattern.
# - `make_run_dirs()` also creates a paired output folder (`nuke_fal_output`) for FAL API results.
# - `require_saved_nuke_script()` blocks runners when the script has no saved path on disk.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Video rendering lives in `nuke_prerender_video_v1.py` to keep modules small.

from __future__ import print_function

import os
import time


def ensure_dir(path):
    if path and (not os.path.isdir(path)):
        try:
            os.makedirs(path)
        except Exception:
            pass


def norm_slashes(p):
    return (p or "").replace("\\", "/")


class UnsavedNukeScriptError(Exception):
    """Raised when fal.ai runners need a saved .nk path on disk."""


def unsaved_nuke_script_message(action="running fal.ai nodes"):
    return (
        "This Nuke script is not saved yet.\n\n"
        "Please save the script before %s.\n"
        "Otherwise Nuke may try to write temporary outputs into a non-writable folder."
        % action
    )


def is_nuke_script_saved(nuke_module):
    """True when the root script has a saved path that exists on disk."""
    try:
        root_name = (nuke_module.root().name() or "").strip()
    except Exception:
        root_name = ""
    return bool(root_name) and os.path.isfile(root_name)


def require_saved_nuke_script(nuke_module, action="running fal.ai nodes"):
    """Abort when the Nuke script is unsaved; temp/output dirs need a script location."""
    if is_nuke_script_saved(nuke_module):
        return
    raise UnsavedNukeScriptError(action)


def is_read_node(n):
    try:
        return (n is not None) and (n.Class() == "Read")
    except Exception:
        return False


def looks_like_sequence_pattern(pat):
    s = (pat or "").strip()
    return ("#" in s) or ("%" in s and "d" in s)


def _get_ext(path_or_pattern):
    """Return lowercase extension (no dot) from path or sequence pattern."""
    try:
        ext = os.path.splitext((path_or_pattern or "").strip())[1]
        return (ext or "").lstrip(".").lower()
    except Exception:
        return ""


def _is_valid_image_extension(path_or_pattern):
    """True if extension is png, jpg, or jpeg (for still/sequence Read fast-path)."""
    return _get_ext(path_or_pattern) in ("png", "jpg", "jpeg")


def _is_valid_video_extension(path_or_pattern):
    """True if extension is mp4 or mov (for video Read fast-path)."""
    return _get_ext(path_or_pattern) in ("mp4", "mov")


def split_cmd(cmd):
    cmd = (cmd or "").strip()
    if not cmd:
        return []
    try:
        import shlex

        return shlex.split(cmd)
    except Exception:
        return cmd.split()


def _can_write_dir(path):
    try:
        ensure_dir(path)
        test_path = os.path.join(path, ".__nuke_ai_gen_write_test")
        f = open(test_path, "wb")
        try:
            f.write("x")
        finally:
            try:
                f.close()
            except Exception:
                pass
        try:
            os.remove(test_path)
        except Exception:
            pass
        return True
    except Exception:
        return False


def pick_writable_temp_dir(nuke_module, leaf_dir_name, env_subdir_name):
    """
    Prefer `<script_dir>/<leaf_dir_name>` when the script is saved; otherwise fall back to a user-writable temp.
    """
    cands = []

    try:
        sd = (nuke_module.script_directory() or "").strip()
    except Exception:
        sd = ""
    if sd:
        cands.append(os.path.join(sd, leaf_dir_name))

    try:
        root_name = (nuke_module.root().name() or "").strip()
    except Exception:
        root_name = ""
    if root_name and os.path.isfile(root_name):
        cands.append(os.path.join(os.path.dirname(root_name), leaf_dir_name))

    for k in ("TEMP", "TMP"):
        v = (os.environ.get(k) or "").strip()
        if v:
            cands.append(os.path.join(v, env_subdir_name))

    home = (os.path.expanduser("~") or "").strip()
    if home and home != "~":
        cands.append(os.path.join(home, env_subdir_name))

    try:
        cands.append(os.path.join(os.getcwd(), leaf_dir_name))
    except Exception:
        pass

    for d in cands:
        if _can_write_dir(d):
            return d

    return os.path.join(os.path.expanduser("~") or ".", env_subdir_name)


def make_run_dir(nuke_module, prefix, leaf_dir_name="nuke_fal_temp", env_subdir_name="nuke_fal_temp"):
    base = pick_writable_temp_dir(nuke_module, leaf_dir_name=leaf_dir_name, env_subdir_name=env_subdir_name)
    ensure_dir(base)
    ts = time.strftime("%Y%m%d_%H%M%S") + ("_%03d" % (int(time.time() * 1000) % 1000))
    run_dir = os.path.join(base, "%s_%s" % (prefix, ts))
    ensure_dir(run_dir)
    return run_dir, ts


def make_run_dirs(
    nuke_module,
    prefix,
    temp_leaf_dir_name="nuke_fal_temp",
    temp_env_subdir_name="nuke_fal_temp",
    output_leaf_dir_name="nuke_fal_output",
    output_env_subdir_name="nuke_fal_output",
):
    """
    Create paired run folders sharing the same timestamp suffix:
    - temp_dir under nuke_fal_temp (prerenders / scratch)
    - out_dir under nuke_fal_output (FAL API downloads / final outputs)
    """
    ts = time.strftime("%Y%m%d_%H%M%S") + ("_%03d" % (int(time.time() * 1000) % 1000))
    sub = "%s_%s" % (prefix, ts)
    temp_base = pick_writable_temp_dir(
        nuke_module, leaf_dir_name=temp_leaf_dir_name, env_subdir_name=temp_env_subdir_name
    )
    out_base = pick_writable_temp_dir(
        nuke_module, leaf_dir_name=output_leaf_dir_name, env_subdir_name=output_env_subdir_name
    )
    ensure_dir(temp_base)
    ensure_dir(out_base)
    temp_dir = os.path.join(temp_base, sub)
    out_dir = os.path.join(out_base, sub)
    ensure_dir(temp_dir)
    ensure_dir(out_dir)
    return temp_dir, out_dir, ts


def resolve_read_file_at_frame(nuke_module, read_node, frame):
    try:
        return nuke_module.filename(read_node, int(frame))
    except Exception:
        try:
            return (read_node.knob("file").value() or "").strip()
        except Exception:
            return ""


def render_still_from_node(nuke_module, src_node, out_path, frame):
    """
    Render a single frame from any node to `out_path` by creating a temporary Write node.
    """
    out_path = os.path.abspath(out_path)
    ensure_dir(os.path.dirname(out_path))

    nuke_module.root().begin()
    w = None
    try:
        w = nuke_module.nodes.Write()
        w.setInput(0, src_node)
        try:
            w["file"].setValue(norm_slashes(out_path))
        except Exception:
            w.knob("file").setValue(norm_slashes(out_path))
        try:
            if "file_type" in w.knobs():
                w["file_type"].setValue(os.path.splitext(out_path)[1].lstrip(".").lower() or "png")
        except Exception:
            pass
        try:
            if "channels" in w.knobs():
                w["channels"].setValue("rgb")
        except Exception:
            pass
        nuke_module.execute(w, int(frame), int(frame))
    finally:
        try:
            if w is not None:
                nuke_module.delete(w)
        except Exception:
            pass
        nuke_module.endGroup()

    return out_path


def render_sequence_from_node(nuke_module, src_node, out_pattern, first, last):
    """
    Render an image sequence from any node to `out_pattern` (should contain %0Nd or ####).
    """
    out_pattern = os.path.abspath(out_pattern)
    ensure_dir(os.path.dirname(out_pattern))

    nuke_module.root().begin()
    w = None
    try:
        w = nuke_module.nodes.Write()
        w.setInput(0, src_node)
        try:
            w["file"].setValue(norm_slashes(out_pattern))
        except Exception:
            w.knob("file").setValue(norm_slashes(out_pattern))
        try:
            if "file_type" in w.knobs():
                ext = os.path.splitext(out_pattern)[1].lstrip(".").lower() or "png"
                w["file_type"].setValue(ext)
        except Exception:
            pass
        try:
            if "channels" in w.knobs():
                w["channels"].setValue("rgb")
        except Exception:
            pass
        nuke_module.execute(w, int(first), int(last))
    finally:
        try:
            if w is not None:
                nuke_module.delete(w)
        except Exception:
            pass
        nuke_module.endGroup()

    return out_pattern


def prepare_still_input_path(nuke_module, src_node, frame, run_dir, base_name):
    """
    Return a single still image path for any upstream node.
    - Read with PNG/JPG: resolves to the file at `frame` (no re-render).
    - Read with other format, or non-Read: renders a single PNG at `frame` under `run_dir`.
    """
    if is_read_node(src_node):
        p = resolve_read_file_at_frame(nuke_module, src_node, frame)
        if p and os.path.isfile(p) and _is_valid_image_extension(p):
            return p
        if p and os.path.isfile(p):
            pass  # wrong format, fall through to prerender
        else:
            raise Exception("Resolved Read file not found: %s" % (p or "<empty>"))

    out_path = os.path.join(run_dir, "%s.png" % base_name)
    return render_still_from_node(nuke_module, src_node, out_path, frame)


def prepare_sequence_input_pattern(nuke_module, src_node, default_first, default_last, run_dir, base_name, pad=4):
    """
    Return `(pattern, first, last)` for any upstream node.
    - Read with sequence pattern and PNG/JPG extension: returns Read.file and Read's first/last (no re-render).
    - Otherwise: renders a PNG sequence under `run_dir` and returns that pattern.
    """
    if is_read_node(src_node):
        try:
            pat = (src_node.knob("file").value() or "").strip()
        except Exception:
            pat = ""
        if looks_like_sequence_pattern(pat) and _is_valid_image_extension(pat):
            try:
                first = int(src_node.knob("first").value())
                last = int(src_node.knob("last").value())
            except Exception:
                first = int(default_first)
                last = int(default_last)
            return pat, first, last

    first = int(default_first)
    last = int(default_last)
    if last < first:
        first, last = last, first

    pattern = os.path.join(run_dir, ("%s_%%0%dd.png" % (base_name, int(pad))))
    return render_sequence_from_node(nuke_module, src_node, pattern, first, last), first, last

