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
