# Purpose:
# - Core shared Python 2.7 utilities for Nuke Group-node runners to accept *any* upstream input pipe.
# - If the input is a suitable `Read` node with a valid format (PNG/JPG for images, MP4/MOV for video),
#   returns its file/pattern directly (no re-render).
# - Otherwise, pre-renders a still image or image sequence to a writable temp folder (`nuke_fal_temp`) and returns that path/pattern.
# - `make_run_dirs()` also creates a paired output folder (`nuke_fal_output`) for FAL API results.
# - `require_saved_nuke_script()` blocks runners when the script has no saved path on disk.
# - Temp/output folders are always created next to the saved .nk script; no home/temp fallbacks.
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


class ScriptOutputDirError(Exception):
    """Raised when temp/output folders cannot be created next to the saved .nk script."""

    def __init__(self, script_dir, leaf_dir_name):
        self.script_dir = script_dir
        self.leaf_dir_name = leaf_dir_name
        Exception.__init__(self, script_output_dir_not_writable_message(script_dir, leaf_dir_name))


def unsaved_nuke_script_message(action="running fal.ai nodes"):
    return (
        "This Nuke script is not saved yet.\n\n"
        "Please save the script before %s.\n"
        "fal.ai temp and output folders are created next to the saved .nk file."
        % action
    )


def script_output_dir_not_writable_message(script_dir, leaf_dir_name):
    target = os.path.join(script_dir, leaf_dir_name)
    return (
        "Could not create the fal.ai folder next to this Nuke script.\n\n"
        "Script folder:\n%s\n\n"
        "Expected folder:\n%s\n\n"
        "Check that the drive is available and you have write permission, then try again."
        % (script_dir, target)
    )


def _clean_nuke_path(path):
    p = (path or "").strip()
    if p.lower().startswith("file://"):
        p = p[7:]
    return p.strip()


def _path_to_existing_dir(path):
    """
    Normalize a Nuke script path or directory path to an absolute existing directory.
    Returns an empty string when the path cannot be resolved.
    """
    p = _clean_nuke_path(path)
    if not p:
        return ""
    try:
        if os.path.isfile(p):
            return os.path.dirname(os.path.abspath(p))
        if os.path.isdir(p):
            return os.path.abspath(p)
    except Exception:
        return ""
    return ""


def _nuke_script_path_candidates(nuke_module):
    """Return saved script file paths from Nuke APIs, in preference order."""
    paths = []

    try:
        root_name = _clean_nuke_path(nuke_module.root().name())
    except Exception:
        root_name = ""
    if root_name:
        paths.append(root_name)

    try:
        script_name = _clean_nuke_path(nuke_module.scriptName())
    except Exception:
        script_name = ""
    if script_name and script_name not in paths:
        paths.append(script_name)

    return paths


def _nuke_script_dir_candidates(nuke_module):
    """
    Return absolute script directories from Nuke APIs, in preference order.
    `root().name()` is preferred over `script_directory()` because the latter can be empty
    or occasionally return the `.nk` file path instead of its parent folder.
    """
    dirs = []
    seen = set()

    def _add_dir(path):
        d = _path_to_existing_dir(path)
        if not d:
            return
        key = os.path.normcase(d)
        if key in seen:
            return
        seen.add(key)
        dirs.append(d)

    for script_path in _nuke_script_path_candidates(nuke_module):
        _add_dir(script_path)

    try:
        sd = _clean_nuke_path(nuke_module.script_directory())
    except Exception:
        sd = ""
    if sd:
        _add_dir(sd)

    return dirs


def is_nuke_script_saved(nuke_module):
    """True when the root script has a saved path that exists on disk."""
    for script_path in _nuke_script_path_candidates(nuke_module):
        try:
            if os.path.isfile(script_path):
                return True
        except Exception:
            pass
    return False


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
            f.write(b"x")
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


def _show_nuke_message(nuke_module, message):
    try:
        nuke_module.message(message)
    except Exception:
        pass


def pick_writable_temp_dir(nuke_module, leaf_dir_name, env_subdir_name=None):
    """
    Return `<script_dir>/<leaf_dir_name>` for the saved Nuke script.
    Raises UnsavedNukeScriptError or ScriptOutputDirError when the folder cannot be used.
    """
    del env_subdir_name  # kept for backward compatibility; no alternate locations are used.

    script_dirs = _nuke_script_dir_candidates(nuke_module)
    if not script_dirs:
        _show_nuke_message(nuke_module, unsaved_nuke_script_message())
        raise UnsavedNukeScriptError("running fal.ai nodes")

    for sd in script_dirs:
        target = os.path.join(sd, leaf_dir_name)
        if _can_write_dir(target):
            return target

    exc = ScriptOutputDirError(script_dirs[0], leaf_dir_name)
    _show_nuke_message(nuke_module, str(exc))
    raise exc


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
    The source node must live on the root graph (use render_still_inside_group for in-group nodes).
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


def render_still_inside_group(nuke_module, group, src_node, out_path, frame):
    """
    Render a single frame from a node inside a Group via a temporary internal Write.
    Caller must already be inside group.begin().
    """
    out_path = os.path.abspath(out_path)
    ensure_dir(os.path.dirname(out_path))

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


def helper_subprocess_env(base_env=None):
    """
    Environment for spawning Python 3 fal helpers from Nuke.
    On Windows, default console encoding (cp1252) cannot print tqdm/fal Unicode progress bars.
    """
    env = (base_env or os.environ).copy()
    if "PYTHONUTF8" not in env:
        env["PYTHONUTF8"] = "1"
    if "PYTHONIOENCODING" not in env:
        env["PYTHONIOENCODING"] = "utf-8:replace"
    return env

