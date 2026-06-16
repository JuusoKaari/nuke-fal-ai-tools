# Purpose: Shared Execute-knob entry point for all fal.ai group nodes.
# Requires a saved Nuke script, resolves runner_path, and runs the runner with Py2/Py3-compatible exec.

from __future__ import print_function

import _install_help
import _nuke_py_compat
import nuke_prerender_core_v1 as prerender_core

# Bound in _refresh_prerender_core(); used in except clauses so stale sys.modules
# entries cannot break error handling after a toolkit update in a live Nuke session.
UnsavedNukeScriptError = None
ScriptOutputDirError = None

_batch_execute_active = False
EXECUTE_NODE_GLOBAL = "_fal_execute_group_node"
_active_execute_group_node = None


def _refresh_prerender_core():
    """
    Reload nuke_prerender_core_v1 when Nuke already cached an older copy.
    Runners reload their own imports; the launcher must do the same for shared errors.
    """
    global prerender_core, UnsavedNukeScriptError, ScriptOutputDirError
    import sys

    mod = sys.modules.get("nuke_prerender_core_v1")
    if mod is not None:
        prerender_core = _nuke_py_compat.reload_module(mod)
    UnsavedNukeScriptError = prerender_core.UnsavedNukeScriptError
    ScriptOutputDirError = prerender_core.ScriptOutputDirError


_refresh_prerender_core()


def set_batch_execute_active(active):
    global _batch_execute_active
    _batch_execute_active = bool(active)


def should_show_success_popup(group_node):
    """Honor show_success_popup on the group; suppress during Execute Selected Nodes."""
    if _batch_execute_active:
        return False
    try:
        knob = group_node.knob("show_success_popup")
        if knob is None:
            return True
        return bool(knob.value())
    except Exception:
        return True


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


def get_execute_group_node(nuke_module, caller_globals=None):
    """
    Return the Group node whose Execute knob launched the current runner.
    Resolution order:
    1. Launcher module stash (set for the duration of exec_script).
    2. EXECUTE_NODE_GLOBAL injected into the runner exec globals dict.
    3. nuke.thisNode() (last resort; unreliable after a prior execute).
    """
    global _active_execute_group_node
    if _active_execute_group_node is not None:
        return _active_execute_group_node
    if caller_globals is not None:
        try:
            node = caller_globals.get(EXECUTE_NODE_GLOBAL)
            if node is not None:
                return node
        except Exception:
            pass
    return nuke_module.thisNode()


def _run_runner_for_node(node):
    import nuke

    global _active_execute_group_node

    prerender_core.require_saved_nuke_script(nuke)
    prerender_core.reset_to_root_graph(nuke)

    raw_runner = ""
    try:
        raw_runner = node.knob("runner_path").value()
    except Exception:
        pass

    runner = _install_help.require_runner_path(nuke, raw_runner)
    _active_execute_group_node = node
    try:
        _nuke_py_compat.exec_script(
            runner,
            {
                "__file__": runner,
                "__name__": "__main__",
                EXECUTE_NODE_GLOBAL: node,
            },
        )
    finally:
        _active_execute_group_node = None
        prerender_core.reset_to_root_graph(nuke)


def execute_this_node():
    """Called from each group's Execute knob."""
    import nuke

    _refresh_prerender_core()
    try:
        _run_runner_for_node(nuke.thisNode())
    except UnsavedNukeScriptError as exc:
        _show_unsaved_script_message(nuke, exc)
    except ScriptOutputDirError:
        pass
    except Exception as exc:
        try:
            nuke.message("Execute failed:\n%s" % str(exc))
        except Exception:
            pass
        raise


def execute_node(node):
    """Run Execute on a single fal.ai group node (uses its Execute knob)."""
    knob = node.knob("execute")
    if knob is None:
        raise Exception("Not a fal.ai node (no Execute knob): %s" % node.name())
    knob.execute()


def execute_selected_nodes():
    """Execute all selected fal.ai group nodes, in selection order."""
    import nuke

    _refresh_prerender_core()
    nodes = [n for n in nuke.selectedNodes() if n.knob("runner_path") is not None]
    if not nodes:
        nuke.message("No fal.ai nodes selected.")
        return

    try:
        prerender_core.require_saved_nuke_script(nuke)
    except UnsavedNukeScriptError as exc:
        _show_unsaved_script_message(nuke, exc)
        return

    set_batch_execute_active(True)
    try:
        for node in nodes:
            try:
                execute_node(node)
            except ScriptOutputDirError:
                return
            except Exception as exc:
                nuke.message("Execute failed on %s:\n%s" % (node.name(), exc))
                raise
    finally:
        set_batch_execute_active(False)
