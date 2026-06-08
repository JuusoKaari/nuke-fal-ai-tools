# Purpose: Shared install guidance when toolkit files or env vars are missing.

from __future__ import print_function

import os

import _path_util
from _repo_urls import GITHUB_RELEASES_URL, GITHUB_REPO_URL

_INSTALL_HINT = (
    "\n\nDownload and install nuke-fal-ai-tools:\n"
    "  Latest release zip: %s\n"
    "  Or clone: %s\n\n"
    "Extract (or clone) to a stable folder, add that folder to NUKE_PATH, "
    "then restart Nuke.\n"
    "Full steps: docs/INSTALL.md in the install folder."
) % (GITHUB_RELEASES_URL, GITHUB_REPO_URL)


def install_hint():
    return _INSTALL_HINT


def _require_tool_path(nuke_module, raw_path, label):
    path = _path_util.resolve_install_path((raw_path or "").strip())
    if not path:
        nuke_module.message(
            "%s path is empty. Re-create the node from the fal.ai menu.%s"
            % (label, _INSTALL_HINT)
        )
        raise Exception("%s_path not set" % label.lower())
    if not os.path.isfile(path):
        nuke_module.message(
            "Missing %s script:\n%s%s" % (label.lower(), path, _INSTALL_HINT)
        )
        raise Exception("%s not found" % label.lower())
    return path


def require_runner_path(nuke_module, raw_path):
    return _require_tool_path(nuke_module, raw_path, "Runner")


def require_helper_path(nuke_module, raw_path):
    return _require_tool_path(nuke_module, raw_path, "Helper")
