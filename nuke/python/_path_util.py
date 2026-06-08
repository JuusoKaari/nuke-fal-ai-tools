# Purpose: Resolve __INSTALL_ROOT__ placeholder paths to the repo root.
# Python 2.7 / 3.x compatible (used by runners inside Nuke).

from __future__ import print_function

import os

INSTALL_ROOT_PLACEHOLDER = "__INSTALL_ROOT__"


def get_install_root():
    """Return repo root (set by init.py at startup, or derived from this file's location)."""
    root = os.environ.get("NUKE_FAL_AI_TOOLS_ROOT", "").strip()
    if root:
        return os.path.normpath(root).replace("\\", "/")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..")).replace("\\", "/")


def resolve_install_path(path):
    """Return absolute filesystem path; expand __INSTALL_ROOT__ from repo root."""
    root = get_install_root()
    path = (path or "").strip()
    if not path:
        return path
    if INSTALL_ROOT_PLACEHOLDER in path:
        path = path.replace(INSTALL_ROOT_PLACEHOLDER, root.replace("\\", "/"))
    elif not os.path.isabs(path):
        path = os.path.join(root, path)
    return os.path.normpath(path).replace("\\", "/")
