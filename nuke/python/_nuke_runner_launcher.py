# Purpose: Shared Execute-knob entry point for all fal.ai group nodes.
# Requires a saved Nuke script, resolves runner_path, and runs the runner with Py2/Py3-compatible exec.

from __future__ import print_function

import _install_help
import _nuke_py_compat
import nuke_prerender_core_v1 as prerender_core


def _show_unsaved_script_message(nuke_module, exc):
    action = "running fal.ai nodes"
    try:
        if exc.args:
            action = exc.args[0]
    except Exception:
        pass
    try:
        nuke_module.message(prerender_core.unsaved_nuke_script_message(action))
    except Exception:
        pass


def _run_runner_for_node(node):
    import nuke

    prerender_core.require_saved_nuke_script(nuke)

    raw_runner = ""
    try:
        raw_runner = node.knob("runner_path").value()
    except Exception:
        pass

    runner = _install_help.require_runner_path(nuke, raw_runner)
    _nuke_py_compat.exec_script(runner, {"__file__": runner, "__name__": "__main__"})


def execute_this_node():
    """Called from each group's Execute knob."""
    import nuke

    try:
        _run_runner_for_node(nuke.thisNode())
    except prerender_core.UnsavedNukeScriptError as exc:
        _show_unsaved_script_message(nuke, exc)


def execute_node(node):
    """Run Execute on a single fal.ai group node (uses its Execute knob)."""
    knob = node.knob("execute")
    if knob is None:
        raise Exception("Not a fal.ai node (no Execute knob): %s" % node.name())
    knob.execute()


def execute_selected_nodes():
    """Execute all selected fal.ai group nodes, in selection order."""
    import nuke

    nodes = [n for n in nuke.selectedNodes() if n.knob("runner_path") is not None]
    if not nodes:
        nuke.message("No fal.ai nodes selected.")
        return

    try:
        prerender_core.require_saved_nuke_script(nuke)
    except prerender_core.UnsavedNukeScriptError as exc:
        _show_unsaved_script_message(nuke, exc)
        return

    for node in nodes:
        try:
            execute_node(node)
        except Exception as exc:
            nuke.message("Execute failed on %s:\n%s" % (node.name(), exc))
            raise
