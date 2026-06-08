# Purpose: Bootstrap nuke-fal-ai-tools - locate repo root from this file and add nuke/python to sys.path.

from __future__ import print_function

import os
import sys


def _get_install_root():
    root = os.path.normpath(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
    python_dir = os.path.join(root, "nuke", "python")
    if not os.path.isdir(python_dir):
        try:
            import nuke

            nuke.message(
                "nuke-fal-ai-tools install layout is invalid.\n\n"
                "Expected folder:\n  %s\n\n"
                "Download and install nuke-fal-ai-tools:\n"
                "  Latest release zip:\n"
                "    https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest\n"
                "  Or clone:\n"
                "    https://github.com/JuusoKaari/nuke-fal-ai-tools\n\n"
                "Extract (or clone) to a stable folder, add that folder to NUKE_PATH, "
                "then restart Nuke.\n"
                "Full steps: docs/INSTALL.md in the install folder."
                % python_dir
            )
        except Exception:
            pass
        raise Exception("nuke-fal-ai-tools: missing nuke/python under %s" % root)
    return root


_ROOT = _get_install_root()
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

os.environ["NUKE_FAL_AI_TOOLS_ROOT"] = _ROOT
