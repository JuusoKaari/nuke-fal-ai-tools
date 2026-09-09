# Purpose:
# - Shared Nuke callbacks to reveal fal.ai parent temp/output folders.
# - Used by Group Advanced knobs and fal.ai -> Settings... (no fal.ai API calls).
# - Resolves the same parent dirs Execute uses via ensure_parent_run_dirs.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Importable without Nuke for unit tests when nuke_module is passed in.

from __future__ import print_function

import os
import subprocess
import sys

import nuke_prerender_core_v1 as prerender


KIND_TEMP = "temp"
KIND_OUTPUT = "output"

_VALID_KINDS = (KIND_TEMP, KIND_OUTPUT)


def unsaved_open_folder_message():
    """Dialog when the script is unsaved and Settings has no usable output folder."""
    return (
        "Cannot open the fal.ai folder yet.\n\n"
        "This Nuke script is not saved, and Settings has no usable "
        "default output folder.\n\n"
        "Save the script, or set Default output folder in fal.ai -> Settings..., "
        "then try again.\n"
        "fal.ai does not fall back to the system temp folder."
    )


def open_folder_failed_message(path, exc):
    """Dialog when the OS could not reveal an existing folder."""
    detail = str(exc).strip() or type(exc).__name__
    return (
        "Could not open folder:\n%s\n\n%s"
        % (prerender.norm_slashes(path), detail)
    )


def folder_reveal_spec(folder, platform_name):
    """
    How to reveal `folder` on this OS.

    Returns ('startfile', folder) on Windows, or ('argv', [cmd, folder]) elsewhere.
    """
    plat = (platform_name or "").lower()
    if plat.startswith("win"):
        return "startfile", folder
    if plat == "darwin":
        return "argv", ["open", folder]
    return "argv", ["xdg-open", folder]


def _show_message(nuke_module, text):
    if nuke_module is None:
        return
    try:
        nuke_module.message(text)
    except Exception:
        pass


def reveal_folder(
    folder,
    nuke_module=None,
    platform_name=None,
    startfile_fn=None,
    popen_fn=None,
):
    """
    Open `folder` in the OS file manager. Returns True on success.
    Failures show a Nuke message that includes the path.
    """
    if platform_name is None:
        platform_name = sys.platform
    kind, payload = folder_reveal_spec(folder, platform_name)
    try:
        if kind == "startfile":
            fn = startfile_fn
            if fn is None:
                fn = getattr(os, "startfile", None)
            if fn is None:
                raise Exception("os.startfile is not available on this platform")
            fn(payload)
        else:
            runner = popen_fn if popen_fn is not None else subprocess.Popen
            runner(payload)
    except Exception as exc:
        _show_message(nuke_module, open_folder_failed_message(folder, exc))
        return False
    return True


def open_folder(
    kind,
    nuke_module=None,
    run_base_dir=None,
    home=None,
    config_file=None,
    platform_name=None,
    startfile_fn=None,
    popen_fn=None,
):
    """
    Resolve the Execute parent dir for `kind` ('temp' or 'output'), create it
    when writable, and reveal it. Never bills fal.ai.
    """
    kind = (kind or "").strip().lower()
    if kind not in _VALID_KINDS:
        raise ValueError("kind must be %s or %s" % (KIND_TEMP, KIND_OUTPUT))

    if nuke_module is None:
        import nuke as nuke_module

    try:
        temp_base, out_base = prerender.ensure_parent_run_dirs(
            nuke_module,
            run_base_dir=run_base_dir,
            home=home,
            config_file=config_file,
            show_messages=False,
        )
    except prerender.UnsavedNukeScriptError:
        _show_message(nuke_module, unsaved_open_folder_message())
        return False
    except prerender.ScriptOutputDirError as exc:
        _show_message(nuke_module, str(exc))
        return False

    path = temp_base if kind == KIND_TEMP else out_base
    return reveal_folder(
        path,
        nuke_module=nuke_module,
        platform_name=platform_name,
        startfile_fn=startfile_fn,
        popen_fn=popen_fn,
    )


def open_temp_folder():
    """PyScript callback: Open temp folder."""
    try:
        return open_folder(KIND_TEMP)
    except Exception as exc:
        import nuke_ui_error_v1 as ui_error

        ui_error.report_unexpected_ui_error("open the temp folder", exc)
        return False


def open_output_folder():
    """PyScript callback: Open output folder."""
    try:
        return open_folder(KIND_OUTPUT)
    except Exception as exc:
        import nuke_ui_error_v1 as ui_error

        ui_error.report_unexpected_ui_error("open the output folder", exc)
        return False
