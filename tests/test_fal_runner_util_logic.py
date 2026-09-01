# Run: py -3 -m unittest tests.test_fal_runner_util_logic
# Pure-logic tests for nuke_fal_runner_util_v1 (no Nuke required).

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

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


class _FakeRoot(object):
    def __init__(self, first, last):
        self._first = first
        self._last = last

    def firstFrame(self):
        return self._first

    def lastFrame(self):
        return self._last


class _FakeNuke(object):
    def __init__(self, frame=7, first=1001, last=1100):
        self._frame = frame
        self._root = _FakeRoot(first, last)

    def frame(self):
        return self._frame

    def root(self):
        return self._root


class TestResolvePython3Cmd(unittest.TestCase):
    def test_empty_on_windows_uses_py_dash_3(self):
        g = _FakeGroup({"python3_cmd": _FakeKnob("  ")})
        self.assertEqual(runner_util.resolve_python3_cmd(g, platform="win32"), ["py", "-3"])

    def test_empty_on_posix_uses_python3(self):
        g = _FakeGroup({"python3_cmd": _FakeKnob("")})
        self.assertEqual(runner_util.resolve_python3_cmd(g, platform="darwin"), ["python3"])
        self.assertEqual(runner_util.resolve_python3_cmd(g, platform="linux"), ["python3"])

    def test_baked_py_dash_3_on_posix_becomes_python3(self):
        g = _FakeGroup({"python3_cmd": _FakeKnob("py -3")})
        self.assertEqual(runner_util.resolve_python3_cmd(g, platform="darwin"), ["python3"])
        self.assertEqual(runner_util.resolve_python3_cmd(g, platform="win32"), ["py", "-3"])

    def test_custom_path_is_split(self):
        g = _FakeGroup({"python3_cmd": _FakeKnob("/usr/bin/python3")})
        self.assertEqual(
            runner_util.resolve_python3_cmd(g, platform="linux"),
            ["/usr/bin/python3"],
        )


class TestFrameRangeFromKnobs(unittest.TestCase):
    def test_root_uses_nuke_root_range(self):
        g = _FakeGroup({"frame_range": _FakeKnob("root")})
        nuke = _FakeNuke(first=1001, last=1100)
        self.assertEqual(runner_util.frame_range_from_knobs(g, nuke), (1001, 1100))

    def test_current_uses_current_frame(self):
        g = _FakeGroup({"frame_range": _FakeKnob("current")})
        nuke = _FakeNuke(frame=42, first=1, last=99)
        self.assertEqual(runner_util.frame_range_from_knobs(g, nuke), (42, 42))

    def test_custom_uses_start_end_and_swaps_if_needed(self):
        g = _FakeGroup(
            {
                "frame_range": _FakeKnob("custom"),
                "custom_start": _FakeKnob("20"),
                "custom_end": _FakeKnob("10"),
            }
        )
        nuke = _FakeNuke()
        self.assertEqual(runner_util.frame_range_from_knobs(g, nuke), (10, 20))

    def test_missing_mode_defaults_to_root(self):
        g = _FakeGroup()
        nuke = _FakeNuke(first=1, last=24)
        self.assertEqual(runner_util.frame_range_from_knobs(g, nuke), (1, 24))


class TestSummarizeHelperOutput(unittest.TestCase):
    def test_includes_json_body_after_error_line(self):
        lines = [
            "Uploading image: C:/tmp/source.png",
            "Submitting request: fal-ai/finegrain-eraser/mask (mode=premium)",
            "ERROR: Finegrain Eraser request failed.",
            "Erase API error: premium mode has been removed from the API",
        ]
        text = runner_util.summarize_helper_output(lines)
        self.assertTrue(text.startswith("ERROR: Finegrain Eraser request failed."))
        self.assertIn("premium mode has been removed from the API", text)
        self.assertNotIn("Uploading image", text)

    def test_falls_back_to_tail_when_no_error_line(self):
        lines = ["one", "", "two", "three"]
        self.assertEqual(runner_util.summarize_helper_output(lines), "one\ntwo\nthree")

    def test_empty_output_mentions_script_editor(self):
        self.assertIn("Script Editor", runner_util.summarize_helper_output([]))

    def test_failure_message_includes_exit_code_and_error(self):
        msg = runner_util.format_helper_failure_message(
            "Finegrain Eraser",
            5,
            ["ERROR: Finegrain Eraser request failed.", "premium mode has been removed from the API"],
        )
        self.assertIn("Finegrain Eraser helper failed (exit 5).", msg)
        self.assertIn("premium mode has been removed from the API", msg)


if __name__ == "__main__":
    unittest.main()
