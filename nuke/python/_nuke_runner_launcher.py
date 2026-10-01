# Purpose: Shared Execute-knob entry point for all fal.ai group nodes.
# Requires a saved Nuke script, resolves runner_path, and runs the runner with Py2/Py3-compatible exec.
# One Execute failure shows one dialog. A runner that already called nuke.message keeps that dialog.
# The exception stays inside the knob script so Nuke does not add its own Python error dialog.

from __future__ import print_function

import _install_help
import _nuke_py_compat
import nuke_prerender_core_v1 as prerender_core

# Bound in _refresh_prerender_core(); isinstance checks use these so a stale
# sys.modules entry cannot break error handling after a toolkit update in a live Nuke session.
UnsavedNukeScriptError = None
ScriptOutputDirError = None

_batch_execute_active = False
EXECUTE_NODE_GLOBAL = "_fal_execute_group_node"
_active_execute_group_node = None
# (exception, dialog_already_shown, recorded nuke.message texts) for the node in flight.
_pending_failure = None


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
    try:
        nuke_module.message(_unsaved_script_text(exc))
    except Exception:
        pass


def _unsaved_script_text(exc):
    action = "running fal.ai nodes"
    try:
        if exc.args:
            action = exc.args[0]
    except Exception:
        pass
    return prerender_core.unsaved_nuke_script_message(action)


def _is_exception_type(exc, exc_type):
    return exc_type is not None and isinstance(exc, exc_type)


def _clear_pending_failure():
    global _pending_failure
    _pending_failure = None


def _take_pending_failure():
    global _pending_failure
    item = _pending_failure
    _pending_failure = None
    return item


def _show_message(nuke_module, text):
    if not text:
        return
    try:
        nuke_module.message(text)
    except Exception:
        pass


def single_execute_followup_message(exc, dialog_already_shown):
    """
    Dialog text for a lone Execute click.
    None when the runner already showed the failure.
    """
    if dialog_already_shown or exc is None:
        return None
    if _is_exception_type(exc, UnsavedNukeScriptError):
        return _unsaved_script_text(exc)
    if _is_exception_type(exc, ScriptOutputDirError):
        return str(exc)
    return "Execute failed:\n%s" % (exc,)


def batch_execute_failure_message(node_name, exc, recorded):
    """One dialog for a failed node inside Execute Selected Nodes."""
    name = node_name or "node"
    if recorded:
        return "%s\n\n%s" % (name, recorded[-1])
    if _is_exception_type(exc, UnsavedNukeScriptError):
        return _unsaved_script_text(exc)
    return "Execute failed on %s:\n%s" % (name, exc)


def _execute_guarded(nuke_module, run):
    """
    Run one Execute attempt.
    Shows at most one dialog for a single-node click, and does not re-raise.
    During Execute Selected Nodes, dialogs are recorded and replayed once by the batch caller.
    """
    global _pending_failure

    real = None
    try:
        real = nuke_module.message
    except Exception:
        real = None

    recorded = []
    shown = [0]

    def wrapped(msg):
        recorded.append(msg)
        if _batch_execute_active:
            return None
        shown[0] += 1
        if real is None:
            return None
        return real(msg)

    replaced = False
    if real is not None:
        try:
            nuke_module.message = wrapped
            replaced = True
        except Exception:
            replaced = False

    exc = None
    try:
        run()
    except Exception as caught:
        exc = caught
    finally:
        if replaced:
            try:
                nuke_module.message = real
            except Exception:
                pass

    if exc is None:
        _pending_failure = None
        return

    dialog_shown = shown[0] > 0
    if (not dialog_shown) and (not _batch_execute_active):
        followup = single_execute_followup_message(exc, False)
        if followup:
            _show_message(nuke_module, followup)
            dialog_shown = True
    _pending_failure = (exc, dialog_shown, list(recorded))


def _report_batch_node_failure(nuke_module, node_name, propagated_exc=None):
    """
    After one node in Execute Selected Nodes.
    Returns True when the batch should stop.
    """
    global _pending_failure
    if _pending_failure is None and propagated_exc is not None:
        _pending_failure = (propagated_exc, False, [])
    pending = _take_pending_failure()
    if pending is None:
        return False
    exc, dialog_shown, recorded = pending
    if not dialog_shown:
        _show_message(
            nuke_module,
            batch_execute_failure_message(node_name, exc, recorded),
        )
    return True


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
    _clear_pending_failure()

    def _run():
        _run_runner_for_node(nuke.thisNode())

    # Stay inside the knob script. An exception that escapes Execute makes Nuke open its own error dialog.
    _execute_guarded(nuke, _run)
    if not _batch_execute_active:
        _clear_pending_failure()


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
            _clear_pending_failure()
            propagated = None
            try:
                execute_node(node)
            except Exception as exc:
                propagated = exc
            if _report_batch_node_failure(nuke, node.name(), propagated):
                return
    finally:
        set_batch_execute_active(False)
        _clear_pending_failure()
