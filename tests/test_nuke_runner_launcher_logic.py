# Run: py -3 -m unittest tests.test_nuke_runner_launcher_logic
# Pure-logic tests for _nuke_runner_launcher and prerender group context helpers.

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import _nuke_runner_launcher as launcher
import nuke_prerender_core_v1 as prerender_core


class _FakeGroup(object):
    def __init__(self, name):
        self._name = name
        self._open = False

    def name(self):
        return self._name

    def begin(self):
        self._open = True

    def end(self):
        self._open = False


class _FakeNuke(object):
    def __init__(self, this_node=None, active_group=None):
        self._this_node = this_node
        self._active_group = active_group
        self.end_group_calls = 0

    def thisNode(self):
        return self._this_node

    def thisGroup(self):
        return self._active_group

    def endGroup(self):
        self.end_group_calls += 1
        self._active_group = None


class TestRefreshPrerenderCore(unittest.TestCase):
    def test_binds_exception_types(self):
        launcher._refresh_prerender_core()
        self.assertIs(launcher.UnsavedNukeScriptError, prerender_core.UnsavedNukeScriptError)
        self.assertIs(launcher.ScriptOutputDirError, prerender_core.ScriptOutputDirError)


class TestGetExecuteGroupNode(unittest.TestCase):
    def setUp(self):
        launcher._active_execute_group_node = None

    def tearDown(self):
        launcher._active_execute_group_node = None

    def test_prefers_active_stash(self):
        stash = _FakeGroup("stash")
        wrong = _FakeGroup("wrong")
        launcher._active_execute_group_node = stash
        got = launcher.get_execute_group_node(_FakeNuke(this_node=wrong))
        self.assertIs(got, stash)

    def test_falls_back_to_exec_globals(self):
        injected = _FakeGroup("injected")
        wrong = _FakeNuke(this_node=_FakeGroup("wrong"))
        got = launcher.get_execute_group_node(
            wrong,
            caller_globals={launcher.EXECUTE_NODE_GLOBAL: injected},
        )
        self.assertIs(got, injected)

    def test_last_resort_is_this_node(self):
        node = _FakeGroup("clicked")
        got = launcher.get_execute_group_node(_FakeNuke(this_node=node))
        self.assertIs(got, node)


class TestResetToRootGraph(unittest.TestCase):
    def test_clears_active_group_context(self):
        nuke = _FakeNuke(active_group=_FakeGroup("inside"))
        prerender_core.reset_to_root_graph(nuke)
        self.assertIsNone(nuke.thisGroup())
        self.assertGreaterEqual(nuke.end_group_calls, 1)

    def test_noop_when_already_at_root(self):
        nuke = _FakeNuke(active_group=None)
        prerender_core.reset_to_root_graph(nuke)
        self.assertEqual(nuke.end_group_calls, 0)


class _FakeMessageNuke(object):
    def __init__(self):
        self.messages = []

    def message(self, msg):
        self.messages.append(msg)


class TestExecuteFailureDialogs(unittest.TestCase):
    def tearDown(self):
        launcher.set_batch_execute_active(False)
        launcher._clear_pending_failure()

    def test_model_error_keeps_the_runner_dialog_only(self):
        nuke = _FakeMessageNuke()

        def run():
            nuke.message(
                "GPT Image 2 Edit helper failed (exit 1).\n\nERROR: content policy"
            )
            raise Exception("GPT Image 2 Edit helper failed")

        launcher._execute_guarded(nuke, run)
        self.assertEqual(
            nuke.messages,
            ["GPT Image 2 Edit helper failed (exit 1).\n\nERROR: content policy"],
        )

    def test_unshown_exception_gets_one_execute_failed_dialog(self):
        nuke = _FakeMessageNuke()

        def run():
            raise RuntimeError("disk full")

        launcher._execute_guarded(nuke, run)
        self.assertEqual(nuke.messages, ["Execute failed:\ndisk full"])

    def test_unsaved_script_gets_one_dialog(self):
        nuke = _FakeMessageNuke()

        def run():
            raise launcher.UnsavedNukeScriptError("running fal.ai nodes")

        launcher._execute_guarded(nuke, run)
        self.assertEqual(len(nuke.messages), 1)
        self.assertIn("not saved", nuke.messages[0])

    def test_script_output_dir_keeps_the_existing_dialog(self):
        nuke = _FakeMessageNuke()

        def run():
            nuke.message("Could not create the fal.ai folder")
            raise launcher.ScriptOutputDirError("C:/scripts", "nuke_fal_temp")

        launcher._execute_guarded(nuke, run)
        self.assertEqual(nuke.messages, ["Could not create the fal.ai folder"])

    def test_batch_replays_one_dialog_with_the_node_name(self):
        nuke = _FakeMessageNuke()
        launcher.set_batch_execute_active(True)

        def run():
            nuke.message("ERROR: premium mode has been removed")
            raise Exception("GPT Image 2 Edit helper failed")

        launcher._execute_guarded(nuke, run)
        self.assertEqual(nuke.messages, [])
        stopped = launcher._report_batch_node_failure(nuke, "GPT_Image_2_Edit1")
        self.assertTrue(stopped)
        self.assertEqual(len(nuke.messages), 1)
        self.assertIn("GPT_Image_2_Edit1", nuke.messages[0])
        self.assertIn("premium mode has been removed", nuke.messages[0])
        self.assertNotIn("Execute failed:", nuke.messages[0])

    def test_batch_unshown_exception_is_one_dialog(self):
        nuke = _FakeMessageNuke()
        launcher.set_batch_execute_active(True)

        def run():
            raise RuntimeError("disk full")

        launcher._execute_guarded(nuke, run)
        stopped = launcher._report_batch_node_failure(nuke, "Nano_Banana1")
        self.assertTrue(stopped)
        self.assertEqual(
            nuke.messages,
            ["Execute failed on Nano_Banana1:\ndisk full"],
        )

    def test_batch_success_does_not_stop(self):
        nuke = _FakeMessageNuke()
        launcher.set_batch_execute_active(True)

        def run():
            return None

        launcher._execute_guarded(nuke, run)
        self.assertFalse(launcher._report_batch_node_failure(nuke, "Nano_Banana1"))
        self.assertEqual(nuke.messages, [])


class TestGroupScope(unittest.TestCase):
    def test_enters_and_returns_to_root(self):
        group = _FakeGroup("Nano_Banana_2_Generate_v1")
        nuke = _FakeNuke(active_group=None)
        with prerender_core.group_scope(nuke, group):
            self.assertTrue(group._open)
        self.assertFalse(group._open)
        self.assertIsNone(nuke.thisGroup())


if __name__ == "__main__":
    unittest.main()
