# Run: py -3 -m unittest tests.test_prerender_temp_dir_logic
# Pure-logic tests for nuke_prerender_core_v1 script-dir resolution (no Nuke required).

from __future__ import print_function

import os
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_prerender_core_v1 as prerender


class _RootNode(object):
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeNuke(object):
    def __init__(self, root_name="", script_name=None, script_directory=""):
        self._root = _RootNode(root_name)
        self._script_name = script_name
        self._script_directory = script_directory

    def root(self):
        return self._root

    def scriptName(self):
        if self._script_name is None:
            return self._root.name()
        return self._script_name

    def script_directory(self):
        return self._script_directory


class TestScriptDirResolution(unittest.TestCase):
    def test_root_name_file_path(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            nuke = _FakeNuke(root_name=script_path)
            dirs = prerender._nuke_script_dir_candidates(nuke)
            self.assertEqual(dirs, [td])

    def test_script_directory_file_path_instead_of_dir(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            nuke = _FakeNuke(root_name="", script_directory=script_path)
            dirs = prerender._nuke_script_dir_candidates(nuke)
            self.assertEqual(dirs, [td])

    def test_prefers_root_name_over_script_directory(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            other_dir = os.path.join(td, "other")
            os.makedirs(other_dir)
            nuke = _FakeNuke(root_name=script_path, script_directory=other_dir)
            dirs = prerender._nuke_script_dir_candidates(nuke)
            self.assertEqual(dirs[0], td)
            self.assertIn(other_dir, dirs)

    def test_script_name_fallback_when_root_name_missing(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            nuke = _FakeNuke(root_name="", script_name=script_path)
            self.assertTrue(prerender.is_nuke_script_saved(nuke))
            dirs = prerender._nuke_script_dir_candidates(nuke)
            self.assertEqual(dirs, [td])

    def test_relative_root_name_resolves_via_abspath(self):
        with tempfile.TemporaryDirectory() as td:
            script_name = "shot.nk"
            script_path = os.path.join(td, script_name)
            open(script_path, "wb").close()
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                nuke = _FakeNuke(root_name=script_name)
                dirs = prerender._nuke_script_dir_candidates(nuke)
                self.assertEqual(dirs, [td])
            finally:
                os.chdir(old_cwd)


class TestPickWritableTempDir(unittest.TestCase):
    def test_uses_script_dir_when_saved(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            nuke = _FakeNuke(root_name=script_path, script_directory="")
            picked = prerender.pick_writable_temp_dir(nuke, "nuke_fal_output", "nuke_fal_output")
            self.assertEqual(picked, os.path.join(td, "nuke_fal_output"))

    def test_raises_when_script_dir_not_writable(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            nuke = _FakeNuke(root_name=script_path, script_directory="")
            original = prerender._can_write_dir

            def _deny_script_output(path):
                if path == os.path.join(td, "nuke_fal_output"):
                    return False
                return original(path)

            prerender._can_write_dir = _deny_script_output
            try:
                with self.assertRaises(prerender.ScriptOutputDirError) as ctx:
                    prerender.pick_writable_temp_dir(nuke, "nuke_fal_output", "nuke_fal_output")
                self.assertEqual(ctx.exception.script_dir, td)
            finally:
                prerender._can_write_dir = original

    def test_raises_unsaved_when_no_script_dir(self):
        nuke = _FakeNuke(root_name="", script_directory="")
        with self.assertRaises(prerender.UnsavedNukeScriptError):
            prerender.pick_writable_temp_dir(nuke, "nuke_fal_output", "nuke_fal_output")


if __name__ == "__main__":
    unittest.main()
