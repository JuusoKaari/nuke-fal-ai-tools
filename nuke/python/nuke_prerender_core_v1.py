# Purpose:
# - Core shared Python 2.7 utilities for Nuke Group-node runners to accept *any* upstream input pipe.
# - If the input is a suitable `Read` node with a valid format (PNG/JPG for images, MP4/MOV for video),
#   returns its file/pattern directly (no re-render).
# - Otherwise, pre-renders a still image or image sequence to a writable temp folder (`nuke_fal_temp`) and returns that path/pattern.
# - Mask / paired stills can pass `match_format_node` so Write uses that node's format (not root).
# - `make_run_dirs()` also creates a paired output folder (`nuke_fal_output`) for FAL API results.
# - `require_saved_nuke_script()` blocks runners when the script has no saved path on disk.
# - Temp/output folders are always created next to the saved .nk script; no home/temp fallbacks.
# - `group_scope()` resets to root, enters a Group, and always returns to root afterward.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Video rendering lives in `nuke_prerender_video_v1.py` to keep modules small.

from __future__ import print_function

import os
import time

try:
    from contextlib import contextmanager
except ImportError:
    contextmanager = None


def ensure_dir(path):
    if path and (not os.path.isdir(path)):
        try:
            os.makedirs(path)
        except Exception:
            pass


def norm_slashes(p):
    return (p or "").replace("\\", "/")


def current_group_context(nuke_module):
    """Return the Group node for the active DAG context, or None at root."""
    try:
        return nuke_module.thisGroup()
    except Exception:
        return None


def reset_to_root_graph(nuke_module):
    """Return to the root DAG after accidental nested group.begin() leaks."""
    for _ in range(64):
        if current_group_context(nuke_module) is None:
            break
        try:
            nuke_module.endGroup()
        except Exception:
            break


if contextmanager is not None:

    @contextmanager
    def group_scope(nuke_module, group):
        """
        Enter a Group DAG context from root and always return to root afterward.
        Use for any in-group node lookup or temporary in-group writes.
        """
        reset_to_root_graph(nuke_module)
        group.begin()
        try:
            yield group
        finally:
            try:
                group.end()
            except Exception:
                pass
            reset_to_root_graph(nuke_module)

else:

    class group_scope(object):
        """Py2 fallback when contextlib is unavailable."""

        def __init__(self, nuke_module, group):
            self._nuke = nuke_module
            self._group = group

        def __enter__(self):
            reset_to_root_graph(self._nuke)
            self._group.begin()
            return self._group

        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                self._group.end()
            except Exception:
                pass
            reset_to_root_graph(self._nuke)
            return False


def format_size_from_node(node):
    """
    Return (width, height, pixel_aspect) for a Nuke node's full-res format, or None.
    Prefers fullSizeFormat() so proxy mode does not shrink paired mask renders.
    """
    if node is None:
        return None
    fmt = None
    for getter in ("fullSizeFormat", "format"):
        try:
            candidate = getattr(node, getter)
        except Exception:
            candidate = None
        if not callable(candidate):
            continue
        try:
            fmt = candidate()
        except Exception:
            fmt = None
        if fmt is not None:
            break
    if fmt is None:
        return None
    try:
        width = int(fmt.width())
        height = int(fmt.height())
    except Exception:
        return None
    if width < 1 or height < 1:
        return None
    pixel_aspect = 1.0
    try:
        pixel_aspect = float(fmt.pixelAspect())
    except Exception:
        pass
    if pixel_aspect <= 0:
        pixel_aspect = 1.0
    return width, height, pixel_aspect


def _set_reformat_to_size(nuke_module, reformat_node, width, height, pixel_aspect):
    """
    Point a Reformat at an exact pixel size with resize none and center off.
    Format box changes; pixels are not scaled or recentered.
    """
    fmt_name = "fal_still_%dx%d" % (int(width), int(height))
    fmt_line = "%d %d 0 0 %d %d %g %s" % (
        int(width),
        int(height),
        int(width),
        int(height),
        float(pixel_aspect),
        fmt_name,
    )
    try:
        nuke_module.addFormat(fmt_line)
    except Exception:
        pass
    for type_val in ("to format", 0):
        try:
            reformat_node["type"].setValue(type_val)
            break
        except Exception:
            continue
    try:
        reformat_node["format"].setValue(fmt_name)
    except Exception:
        for type_val in ("to box", 2, 1):
            try:
                reformat_node["type"].setValue(type_val)
                break
            except Exception:
                continue
        try:
            reformat_node["box"].setValue(0, 0, int(width), int(height))
        except Exception:
            try:
                reformat_node["box"].setValue([0, 0, int(width), int(height)])
            except Exception:
                pass
    for resize_val in ("none", 0):
        try:
            reformat_node["resize"].setValue(resize_val)
            break
        except Exception:
            continue
    for center_val in (False, 0):
        try:
            reformat_node["center"].setValue(center_val)
            break
        except Exception:
            continue


def _execute_write_full_res(nuke_module, write_node, first, last):
    """Execute a Write at full resolution even if the script is in proxy mode."""
    root = nuke_module.root()
    was_proxy = False
    try:
        was_proxy = bool(root.proxy())
    except Exception:
        was_proxy = False
    if was_proxy:
        try:
            root.setProxy(False)
        except Exception:
            was_proxy = False
    try:
        nuke_module.execute(write_node, int(first), int(last))
    finally:
        if was_proxy:
            try:
                root.setProxy(True)
            except Exception:
                pass


def require_rendered_file(out_path, context="Render"):
    """
    Raise if `out_path` was not written or is empty.
    Nuke execute() can succeed while a broken graph writes nothing.
    """
    out_path = os.path.abspath(out_path)
    if not os.path.isfile(out_path):
        raise Exception(
            "%s failed: output file was not created:\n%s"
            % (context, norm_slashes(out_path))
        )
    try:
        if os.path.getsize(out_path) <= 0:
            raise Exception(
                "%s failed: output file is empty:\n%s"
                % (context, norm_slashes(out_path))
            )
    except OSError as exc:
        raise Exception(
            "%s failed: could not read output file:\n%s\n(%s)"
            % (context, norm_slashes(out_path), exc)
        )
    return out_path


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
    group_node=None,
):
    """
    Create paired run folders sharing the same timestamp suffix:
    - temp_dir under nuke_fal_temp (prerenders / scratch)
    - out_dir under nuke_fal_output (FAL API downloads / final outputs)

    When group_node is given, its name is included so parallel executes on
    multiple Group instances do not share the same folder.
    """
    ts = time.strftime("%Y%m%d_%H%M%S") + ("_%03d" % (int(time.time() * 1000) % 1000))
    group_token = ""
    if group_node is not None:
        try:
            safe_name = "".join(
                (c if (c.isalnum() or c in ("_", "-")) else "_")
                for c in (group_node.name() or "group")
            )
            group_token = "_%s_%d" % (safe_name[:40], id(group_node) % 10000)
        except Exception:
            group_token = "_group_%d" % (id(group_node) % 10000)
    sub = "%s%s_%s" % (prefix, group_token, ts)
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


def render_still_from_node(nuke_module, src_node, out_path, frame, match_format_node=None):
    """
    Render a single frame from any node to `out_path` by creating a temporary Write node.
    The source node must live on the root graph (use render_still_inside_group for in-group nodes).
    When `match_format_node` is set, insert a Reformat to that node's full-res format so
    Roto/mask pipes are not written at the script root format.
    """
    out_path = os.path.abspath(out_path)
    ensure_dir(os.path.dirname(out_path))
    match_size = format_size_from_node(match_format_node)

    nuke_module.root().begin()
    w = None
    rf = None
    try:
        write_src = src_node
        if match_size is not None:
            rf = nuke_module.nodes.Reformat()
            rf.setInput(0, src_node)
            _set_reformat_to_size(
                nuke_module, rf, match_size[0], match_size[1], match_size[2]
            )
            write_src = rf
        w = nuke_module.nodes.Write()
        w.setInput(0, write_src)
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
        _execute_write_full_res(nuke_module, w, int(frame), int(frame))
    finally:
        try:
            if w is not None:
                nuke_module.delete(w)
        except Exception:
            pass
        try:
            if rf is not None:
                nuke_module.delete(rf)
        except Exception:
            pass
        nuke_module.endGroup()

    return require_rendered_file(out_path, "Render still")


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

    return require_rendered_file(out_path, "Render still (in group)")


def render_still_inside_group_with_crop(nuke_module, src_node, out_path, frame, box):
    """
    Render a single frame from `src_node` cropped to `box` (x, y, r, t).
    Creates temporary in-group Crop and Write nodes, then deletes them.
    Caller must already be inside group.begin().
    """
    out_path = os.path.abspath(out_path)
    ensure_dir(os.path.dirname(out_path))

    crop = None
    w = None
    try:
        crop = nuke_module.nodes.Crop()
        crop.setInput(0, src_node)
        try:
            crop["box"].setValue(float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        except Exception:
            crop.knob("box").setValue(
                [float(box[0]), float(box[1]), float(box[2]), float(box[3])]
            )
        try:
            crop["reformat"].setValue(True)
        except Exception:
            pass
        w = nuke_module.nodes.Write()
        w.setInput(0, crop)
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
        try:
            if crop is not None:
                nuke_module.delete(crop)
        except Exception:
            pass

    return require_rendered_file(out_path, "Render still (ROI crop)")


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
        _execute_write_full_res(nuke_module, w, int(first), int(last))
    finally:
        try:
            if w is not None:
                nuke_module.delete(w)
        except Exception:
            pass
        nuke_module.endGroup()

    return out_pattern


def prepare_still_input_path(nuke_module, src_node, frame, run_dir, base_name, match_format_node=None):
    """
    Return a single still image path for any upstream node.
    - Read with PNG/JPG: resolves to the file at `frame` (no re-render).
    - Read with other format, or non-Read: renders a single PNG at `frame` under `run_dir`.
    - When `match_format_node` is set, always prerender and Reformat to that node's format
      so a Roto mask is not written at script root size while the plate stays native.
    """
    if match_format_node is None and is_read_node(src_node):
        p = resolve_read_file_at_frame(nuke_module, src_node, frame)
        if p and os.path.isfile(p) and _is_valid_image_extension(p):
            return p
        if p and os.path.isfile(p):
            pass  # wrong format, fall through to prerender
        else:
            raise Exception("Resolved Read file not found: %s" % (p or "<empty>"))

    out_path = os.path.join(run_dir, "%s.png" % base_name)
    return render_still_from_node(
        nuke_module,
        src_node,
        out_path,
        frame,
        match_format_node=match_format_node,
    )


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

