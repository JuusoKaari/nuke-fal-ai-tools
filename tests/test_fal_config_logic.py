# Run: py -3 -m unittest tests.test_fal_config_logic
# Pure-logic tests for nuke_fal_config_v1 and helper_env FAL_KEY precedence (no Nuke).

from __future__ import print_function

import json
import os
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_fal_config_v1 as fal_config
import nuke_fal_runner_util_v1 as runner_util


class _FakeKnob(object):
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _FakeGroup(object):
    def __init__(self, knobs=None):
        self._knobs = knobs or {}

    def knob(self, name):
        return self._knobs.get(name, _FakeKnob(""))


class TestFalConfigLoadSave(unittest.TestCase):
    def test_load_missing_returns_defaults(self):
        home = tempfile.mkdtemp()
        cfg = fal_config.load_config(home=home)
        self.assertEqual(cfg["fal_key"], "")
        self.assertEqual(cfg["output_dir"], "")
        self.assertEqual(cfg["video_output"], fal_config.VIDEO_OUTPUT_EXR_SEQUENCE)

    def test_save_and_load_roundtrip(self):
        home = tempfile.mkdtemp()
        path = fal_config.save_config(
            {"fal_key": "secret-key", "output_dir": "C:/outs"},
            home=home,
        )
        self.assertTrue(os.path.isfile(path))
        with open(path, "r") as f:
            raw = json.load(f)
        self.assertEqual(raw["fal_key"], "secret-key")
        self.assertEqual(raw["output_dir"], "C:/outs")
        loaded = fal_config.load_config(home=home)
        self.assertEqual(loaded["fal_key"], "secret-key")
        self.assertEqual(loaded["output_dir"], "C:/outs")
        self.assertEqual(loaded["video_output"], fal_config.VIDEO_OUTPUT_EXR_SEQUENCE)

    def test_partial_save_preserves_video_output(self):
        home = tempfile.mkdtemp()
        fal_config.save_config(
            {"fal_key": "k", "output_dir": "C:/outs", "video_output": "mp4"},
            home=home,
        )
        fal_config.save_config({"fal_key": "k2"}, home=home)
        loaded = fal_config.load_config(home=home)
        self.assertEqual(loaded["fal_key"], "k2")
        self.assertEqual(loaded["output_dir"], "C:/outs")
        self.assertEqual(loaded["video_output"], fal_config.VIDEO_OUTPUT_MP4)

    def test_normalize_video_output(self):
        self.assertEqual(
            fal_config.normalize_video_output("mp4"), fal_config.VIDEO_OUTPUT_MP4
        )
        self.assertEqual(
            fal_config.normalize_video_output("DWAB EXR"),
            fal_config.VIDEO_OUTPUT_EXR_SEQUENCE,
        )
        self.assertEqual(
            fal_config.normalize_video_output(""),
            fal_config.VIDEO_OUTPUT_EXR_SEQUENCE,
        )
        self.assertEqual(
            fal_config.get_video_output(home=tempfile.mkdtemp()),
            fal_config.VIDEO_OUTPUT_EXR_SEQUENCE,
        )

    def test_invalid_json_returns_defaults(self):
        home = tempfile.mkdtemp()
        path = fal_config.config_path(home=home)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            f.write("{not json")
        cfg = fal_config.load_config(home=home)
        self.assertEqual(cfg["fal_key"], "")

    def test_resolve_fal_key_precedence(self):
        home = tempfile.mkdtemp()
        fal_config.save_config({"fal_key": "from-config"}, home=home)
        cfg_path = fal_config.config_path(home=home)

        self.assertEqual(
            fal_config.resolve_fal_key(
                knob_value="from-knob",
                env={"FAL_KEY": "from-env"},
                home=home,
                config_file=cfg_path,
            ),
            "from-knob",
        )
        self.assertEqual(
            fal_config.resolve_fal_key(
                knob_value="insert your secret here",
                env={"FAL_KEY": "from-env"},
                home=home,
                config_file=cfg_path,
            ),
            "from-config",
        )
        self.assertEqual(
            fal_config.resolve_fal_key(
                knob_value="",
                env={"FAL_KEY": "from-env"},
                home=home,
                config_file=cfg_path,
            ),
            "from-config",
        )
        self.assertEqual(
            fal_config.resolve_fal_key(
                knob_value="",
                env={},
                home=home,
                config_file=cfg_path,
            ),
            "from-config",
        )
        self.assertEqual(
            fal_config.resolve_fal_key(
                knob_value="",
                env={"FAL_KEY": "from-env"},
                home=tempfile.mkdtemp(),
            ),
            "from-env",
        )


class TestHelperEnvPrecedence(unittest.TestCase):
    def test_knob_wins_over_env_and_config(self):
        home = tempfile.mkdtemp()
        fal_config.save_config({"fal_key": "from-config"}, home=home)
        g = _FakeGroup({"FAL": _FakeKnob("from-knob")})
        old = os.environ.get("FAL_KEY")
        os.environ["FAL_KEY"] = "from-env"
        try:
            env = runner_util.helper_env_from_group(
                g, home=home, config_file=fal_config.config_path(home=home)
            )
            self.assertEqual(env.get("FAL_KEY"), "from-knob")
        finally:
            if old is None:
                os.environ.pop("FAL_KEY", None)
            else:
                os.environ["FAL_KEY"] = old

    def test_config_wins_over_env_when_knob_empty(self):
        home = tempfile.mkdtemp()
        fal_config.save_config({"fal_key": "from-config"}, home=home)
        g = _FakeGroup({"FAL": _FakeKnob("")})
        old = os.environ.get("FAL_KEY")
        os.environ["FAL_KEY"] = "from-env"
        try:
            env = runner_util.helper_env_from_group(
                g, home=home, config_file=fal_config.config_path(home=home)
            )
            self.assertEqual(env.get("FAL_KEY"), "from-config")
        finally:
            if old is None:
                os.environ.pop("FAL_KEY", None)
            else:
                os.environ["FAL_KEY"] = old

    def test_env_used_when_knob_and_config_missing(self):
        home = tempfile.mkdtemp()
        g = _FakeGroup({"FAL": _FakeKnob("insert your secret")})
        old = os.environ.get("FAL_KEY")
        os.environ["FAL_KEY"] = "from-env"
        try:
            env = runner_util.helper_env_from_group(
                g, home=home, config_file=fal_config.config_path(home=home)
            )
            self.assertEqual(env.get("FAL_KEY"), "from-env")
        finally:
            if old is None:
                os.environ.pop("FAL_KEY", None)
            else:
                os.environ["FAL_KEY"] = old

    def test_config_used_when_knob_and_env_missing(self):
        home = tempfile.mkdtemp()
        fal_config.save_config({"fal_key": "from-config"}, home=home)
        g = _FakeGroup({"FAL": _FakeKnob("insert your secret")})
        old = os.environ.get("FAL_KEY")
        os.environ.pop("FAL_KEY", None)
        try:
            env = runner_util.helper_env_from_group(
                g, home=home, config_file=fal_config.config_path(home=home)
            )
            self.assertEqual(env.get("FAL_KEY"), "from-config")
        finally:
            if old is not None:
                os.environ["FAL_KEY"] = old


class TestOutputDirResolve(unittest.TestCase):
    def test_get_output_dir_reads_config(self):
        home = tempfile.mkdtemp()
        fal_config.save_config({"output_dir": "C:/outs"}, home=home)
        self.assertEqual(fal_config.get_output_dir(home=home), "C:/outs")

    def test_normalize_expands_home(self):
        home = os.path.abspath(os.path.expanduser("~"))
        resolved = fal_config.normalize_output_dir_path(
            os.path.join("~", "nuke_fal_outs")
        )
        expected = os.path.abspath(os.path.join(home, "nuke_fal_outs"))
        self.assertEqual(resolved, expected)

    def test_resolve_usable_creates_missing_dir(self):
        root = tempfile.mkdtemp()
        target = os.path.join(root, "nested", "outs")
        self.assertFalse(os.path.isdir(target))
        resolved = fal_config.resolve_usable_output_base(configured=target)
        self.assertEqual(resolved, os.path.abspath(target))
        self.assertTrue(os.path.isdir(target))

    def test_resolve_usable_empty_returns_empty(self):
        self.assertEqual(fal_config.resolve_usable_output_base(configured=""), "")
        self.assertEqual(fal_config.resolve_usable_output_base(configured="   "), "")

    def test_resolve_usable_invalid_returns_empty(self):
        # Path under a non-directory file cannot be created.
        root = tempfile.mkdtemp()
        blocker = os.path.join(root, "not_a_dir")
        with open(blocker, "wb") as f:
            f.write(b"x")
        bad = os.path.join(blocker, "child")
        self.assertEqual(fal_config.resolve_usable_output_base(configured=bad), "")


if __name__ == "__main__":
    unittest.main()
