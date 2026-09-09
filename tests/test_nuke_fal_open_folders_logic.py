# Run: py -3 -m unittest tests.test_nuke_fal_open_folders_logic
# Pure-logic tests for nuke_fal_open_folders_v1 (no Nuke required).

from __future__ import print_function

import os
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
_GROUP_DIR = os.path.join(_ROOT, "nuke", "groups")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_fal_config_v1 as fal_config
import nuke_fal_open_folders_v1 as open_folders
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
        self.messages = []

    def root(self):
        return self._root

    def scriptName(self):
        if self._script_name is None:
            return self._root.name()
        return self._script_name

    def script_directory(self):
        return self._script_directory

    def message(self, text):
        self.messages.append(text)


class TestFolderRevealSpec(unittest.TestCase):
    def test_windows_uses_startfile(self):
        kind, payload = open_folders.folder_reveal_spec("C:/outs", "win32")
        self.assertEqual(kind, "startfile")
        self.assertEqual(payload, "C:/outs")

    def test_macos_uses_open(self):
        kind, payload = open_folders.folder_reveal_spec("/tmp/outs", "darwin")
        self.assertEqual(kind, "argv")
        self.assertEqual(payload, ["open", "/tmp/outs"])

    def test_linux_uses_xdg_open(self):
        kind, payload = open_folders.folder_reveal_spec("/tmp/outs", "linux")
        self.assertEqual(kind, "argv")
        self.assertEqual(payload, ["xdg-open", "/tmp/outs"])


class TestRevealFolder(unittest.TestCase):
    def test_windows_calls_startfile(self):
        called = []
        nuke = _FakeNuke()
        ok = open_folders.reveal_folder(
            "C:/outs",
            nuke_module=nuke,
            platform_name="win32",
            startfile_fn=lambda path: called.append(path),
        )
        self.assertTrue(ok)
        self.assertEqual(called, ["C:/outs"])
        self.assertEqual(nuke.messages, [])

    def test_darwin_calls_popen_open(self):
        called = []
        nuke = _FakeNuke()
        ok = open_folders.reveal_folder(
            "/tmp/outs",
            nuke_module=nuke,
            platform_name="darwin",
            popen_fn=lambda argv: called.append(list(argv)),
        )
        self.assertTrue(ok)
        self.assertEqual(called, [["open", "/tmp/outs"]])

    def test_linux_calls_popen_xdg_open(self):
        called = []
        nuke = _FakeNuke()
        ok = open_folders.reveal_folder(
            "/tmp/outs",
            nuke_module=nuke,
            platform_name="linux",
            popen_fn=lambda argv: called.append(list(argv)),
        )
        self.assertTrue(ok)
        self.assertEqual(called, [["xdg-open", "/tmp/outs"]])

    def test_failure_shows_path_in_message(self):
        def _boom(_path):
            raise OSError("access denied")

        nuke = _FakeNuke()
        ok = open_folders.reveal_folder(
            "C:/missing",
            nuke_module=nuke,
            platform_name="win32",
            startfile_fn=_boom,
        )
        self.assertFalse(ok)
        self.assertEqual(len(nuke.messages), 1)
        self.assertIn("C:/missing", nuke.messages[0].replace("\\", "/"))
        self.assertIn("access denied", nuke.messages[0])
        self.assertNotIn("\u2014", nuke.messages[0])
        self.assertNotIn("\u2013", nuke.messages[0])


class TestOpenFolderPathResolution(unittest.TestCase):
    def test_settings_folder_wins(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            cfg_home = os.path.join(td, "home")
            cfg_out = os.path.join(td, "from_config")
            os.makedirs(cfg_out)
            fal_config.save_config({"output_dir": cfg_out}, home=cfg_home)
            nuke = _FakeNuke(root_name=script_path)
            opened = []
            ok = open_folders.open_folder(
                "temp",
                nuke_module=nuke,
                home=cfg_home,
                config_file=fal_config.config_path(home=cfg_home),
                platform_name="win32",
                startfile_fn=lambda path: opened.append(path),
            )
            self.assertTrue(ok)
            self.assertEqual(opened, [os.path.join(cfg_out, "nuke_fal_temp")])
            self.assertTrue(os.path.isdir(opened[0]))
            self.assertFalse(os.path.isdir(os.path.join(td, "nuke_fal_temp")))

    def test_script_folder_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            cfg_home = os.path.join(td, "home")
            fal_config.save_config({"output_dir": ""}, home=cfg_home)
            nuke = _FakeNuke(root_name=script_path)
            opened = []
            ok = open_folders.open_folder(
                "output",
                nuke_module=nuke,
                home=cfg_home,
                config_file=fal_config.config_path(home=cfg_home),
                platform_name="win32",
                startfile_fn=lambda path: opened.append(path),
            )
            self.assertTrue(ok)
            self.assertEqual(opened, [os.path.join(td, "nuke_fal_output")])
            self.assertTrue(os.path.isdir(opened[0]))

    def test_unsaved_without_settings_shows_message(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_home = os.path.join(td, "home")
            fal_config.save_config({"output_dir": ""}, home=cfg_home)
            nuke = _FakeNuke(root_name="", script_directory="")
            opened = []
            ok = open_folders.open_folder(
                "temp",
                nuke_module=nuke,
                home=cfg_home,
                config_file=fal_config.config_path(home=cfg_home),
                platform_name="win32",
                startfile_fn=lambda path: opened.append(path),
            )
            self.assertFalse(ok)
            self.assertEqual(opened, [])
            self.assertEqual(len(nuke.messages), 1)
            self.assertIn("not saved", nuke.messages[0])
            self.assertIn("Settings", nuke.messages[0])
            self.assertIn("system temp", nuke.messages[0])
            self.assertNotIn("\u2014", nuke.messages[0])

    def test_unsaved_with_settings_opens_settings_folder(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_home = os.path.join(td, "home")
            cfg_out = os.path.join(td, "from_config")
            os.makedirs(cfg_out)
            fal_config.save_config({"output_dir": cfg_out}, home=cfg_home)
            nuke = _FakeNuke(root_name="", script_directory="")
            opened = []
            ok = open_folders.open_folder(
                "output",
                nuke_module=nuke,
                home=cfg_home,
                config_file=fal_config.config_path(home=cfg_home),
                platform_name="win32",
                startfile_fn=lambda path: opened.append(path),
            )
            self.assertTrue(ok)
            self.assertEqual(opened, [os.path.join(cfg_out, "nuke_fal_output")])
            self.assertEqual(nuke.messages, [])

    def test_explicit_run_base_dir_used_by_settings_panel(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            panel_out = os.path.join(td, "panel_out")
            os.makedirs(panel_out)
            nuke = _FakeNuke(root_name=script_path)
            opened = []
            ok = open_folders.open_folder(
                "temp",
                nuke_module=nuke,
                run_base_dir=panel_out,
                platform_name="win32",
                startfile_fn=lambda path: opened.append(path),
            )
            self.assertTrue(ok)
            self.assertEqual(opened, [os.path.join(panel_out, "nuke_fal_temp")])

    def test_opens_parent_not_timestamped_run_dir(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            nuke = _FakeNuke(root_name=script_path)
            opened = []
            open_folders.open_folder(
                "temp",
                nuke_module=nuke,
                platform_name="win32",
                startfile_fn=lambda path: opened.append(path),
            )
            self.assertEqual(os.path.basename(opened[0]), "nuke_fal_temp")
            self.assertEqual(os.listdir(opened[0]), [])


class TestEnsureParentRunDirsSharedWithExecute(unittest.TestCase):
    def test_make_run_dirs_uses_same_parents(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "shot.nk")
            open(script_path, "wb").close()
            cfg_home = os.path.join(td, "home")
            cfg_out = os.path.join(td, "from_config")
            os.makedirs(cfg_out)
            fal_config.save_config({"output_dir": cfg_out}, home=cfg_home)
            nuke = _FakeNuke(root_name=script_path)
            cfg_path = fal_config.config_path(home=cfg_home)
            temp_base, out_base = prerender.ensure_parent_run_dirs(
                nuke, home=cfg_home, config_file=cfg_path
            )
            temp_dir, out_dir, _ts = prerender.make_run_dirs(
                nuke, "test", home=cfg_home, config_file=cfg_path
            )
            self.assertEqual(temp_base, os.path.join(cfg_out, "nuke_fal_temp"))
            self.assertEqual(out_base, os.path.join(cfg_out, "nuke_fal_output"))
            self.assertTrue(temp_dir.startswith(temp_base + os.sep))
            self.assertTrue(out_dir.startswith(out_base + os.sep))
            self.assertNotEqual(temp_dir, temp_base)
            self.assertNotEqual(out_dir, out_base)


class TestShippedUiHasOpenFolderButtons(unittest.TestCase):
    def test_every_group_nk_has_open_folder_knobs(self):
        missing = []
        names = [
            name
            for name in os.listdir(_GROUP_DIR)
            if name.startswith("fal_") and name.endswith(".nk")
        ]
        self.assertGreaterEqual(len(names), 32)
        for name in names:
            path = os.path.join(_GROUP_DIR, name)
            with open(path, "r") as f:
                text = f.read()
            if 'addUserKnob {22 open_temp_folder l "Open temp folder"' not in text:
                missing.append("%s: open_temp_folder" % name)
            if 'addUserKnob {22 open_output_folder l "Open output folder"' not in text:
                missing.append("%s: open_output_folder" % name)
            if "nuke_fal_open_folders_v1" not in text:
                missing.append("%s: shared module" % name)
            if "endAdvanced" not in text:
                missing.append("%s: Advanced tab" % name)
        self.assertEqual(missing, [])

    def test_settings_panel_defines_open_folder_buttons(self):
        path = os.path.join(_PYTHON_DIR, "nuke_fal_settings_v1.py")
        with open(path, "r") as f:
            text = f.read()
        self.assertIn('PyScript_Knob("open_temp_folder", "Open temp folder")', text)
        self.assertIn('PyScript_Knob("open_output_folder", "Open output folder")', text)
        self.assertIn("_on_open_folder", text)
        self.assertIn("nuke_fal_open_folders_v1", text)


if __name__ == "__main__":
    unittest.main()
