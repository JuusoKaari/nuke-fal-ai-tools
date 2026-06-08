# Purpose: Python 2.7 / 3.x compatibility helpers for code running inside Nuke.
# Detects Nuke's embedded interpreter version and provides portable exec/reload utilities.

from __future__ import print_function

import sys

PY2 = sys.version_info[0] < 3
PY3 = not PY2


def nuke_python_version():
    """Return (major, minor) for the interpreter running inside Nuke."""
    return sys.version_info[0], sys.version_info[1]


def exec_script(path, globals_dict=None):
    """
    Run a Python script file the way Nuke runners expect (as __main__).
    Uses execfile on Python 2.7; compile+exec on Python 3.
    """
    path = (path or "").strip()
    if not path:
        raise Exception("exec_script: empty path")

    g = dict(globals_dict) if globals_dict else {}
    g.setdefault("__file__", path)
    g.setdefault("__name__", "__main__")

    if PY2:
        execfile(path, g)  # noqa: F821 - Py2 builtin
        return

    with open(path, "rb") as f:
        source = f.read()
    try:
        source = source.decode("utf-8")
    except Exception:
        source = source.decode("latin-1")
    code = compile(source, path, "exec")
    exec(code, g)


def reload_module(mod):
    """Reload an imported module (session cache busting in long-lived Nuke)."""
    if mod is None:
        return mod
    if PY2:
        reload(mod)  # noqa: F821 - Py2 builtin
        return mod
    import importlib

    return importlib.reload(mod)
