# Purpose:
# - Shared unexpected-error dialog for Nuke UI callbacks that would otherwise only print to the Script Editor.
# - Suggests restarting Nuke when a live session may have stale Python modules.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - `import nuke` stays inside report_unexpected_ui_error so unit tests can import without Nuke.

from __future__ import print_function

import traceback

_RESTART_HINT = (
    "If this keeps happening, fully quit and restart Nuke. "
    "That often fixes stale Python modules from a long session or a plugin update."
)


def unexpected_ui_error_message(action, exc):
    """Return ASCII dialog text for an unexpected callback failure."""
    action = (action or "").strip() or "complete this action"
    if exc is None:
        err_line = "Error"
    else:
        detail = str(exc).strip()
        name = type(exc).__name__
        if detail:
            err_line = "%s: %s" % (name, detail)
        else:
            err_line = name
    return (
        "Could not %s.\n\n"
        "%s\n\n"
        "%s\n\n"
        "The Script Editor has the full traceback."
        % (action, err_line, _RESTART_HINT)
    )


def report_unexpected_ui_error(action, exc, nuke_module=None, print_traceback=True):
    """Print the traceback and show a Nuke dialog. Never raises."""
    if print_traceback:
        traceback.print_exc()
    try:
        if nuke_module is None:
            import nuke as nuke_module
        nuke_module.message(unexpected_ui_error_message(action, exc))
    except Exception:
        pass
