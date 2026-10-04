# Run: py -3 -m unittest tests.test_video_output_logic
# Pure-logic tests for nuke_video_output_v1 path/pattern helpers (no Nuke).

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_video_output_v1 as video_out


class TestSequencePaths(unittest.TestCase):
    def test_sequence_dir_sits_next_to_mp4(self):
        seq_dir, pattern = video_out.sequence_paths_for_mp4(
            os.path.join("C:/outs", "nuke_fal_output", "seedance_25_i2v_20260819.mp4")
        )
        self.assertEqual(
            os.path.basename(seq_dir), "seedance_25_i2v_20260819"
        )
        self.assertTrue(pattern.replace("\\", "/").endswith(
            "seedance_25_i2v_20260819/seedance_25_i2v_20260819.####.exr"
        ))

    def test_expand_hash_pattern(self):
        self.assertEqual(
            video_out.expand_frame_pattern("seq.####.exr", 1),
            "seq.0001.exr",
        )
        self.assertEqual(
            video_out.expand_frame_pattern("seq.%04d.exr", 12),
            "seq.0012.exr",
        )

    def test_dwab_level_is_200(self):
        self.assertEqual(video_out.DWAB_COMPRESSION_LEVEL, 200)


class _EnumKnob(object):
    def __init__(self, values):
        self._values = list(values)
        self.index = 0

    def values(self):
        return list(self._values)

    def setValue(self, v):
        if isinstance(v, int) and not isinstance(v, bool):
            self.index = v
            return
        self.index = self._values.index(str(v))


class _ValueKnob(object):
    def __init__(self):
        self.value = None

    def setValue(self, v):
        self.value = v


class _FakeRead(object):
    def __init__(self):
        self._knobs = {
            "frame_mode": _EnumKnob(["expression", "start at", "offset"]),
            "frame": _ValueKnob(),
        }

    def knob(self, name):
        return self._knobs.get(name)


class _FakeKnob(object):
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _FakeGroup(object):
    def __init__(self, knobs=None):
        self._knobs = knobs or {}

    def knob(self, name):
        return self._knobs.get(name)


class _FakeRoot(object):
    def __init__(self, first, last):
        self._first = first
        self._last = last

    def firstFrame(self):
        return self._first

    def lastFrame(self):
        return self._last


class _FakeNuke(object):
    def __init__(self, frame=1, first=1, last=100):
        self._frame = frame
        self._root = _FakeRoot(first, last)

    def frame(self):
        return self._frame

    def root(self):
        return self._root


class TestReadStartAt(unittest.TestCase):
    def test_custom_range_starts_output_at_first_frame(self):
        g = _FakeGroup(
            {
                "frame_range": _FakeKnob("custom"),
                "custom_start": _FakeKnob("151"),
                "custom_end": _FakeKnob("200"),
            }
        )
        nuke = _FakeNuke(first=1, last=100)
        self.assertEqual(video_out.launched_start_frame(nuke, g), 151)

    def test_explicit_start_frame_overrides_knobs(self):
        g = _FakeGroup({"frame_range": _FakeKnob("custom"), "custom_start": _FakeKnob("151"), "custom_end": _FakeKnob("200")})
        nuke = _FakeNuke()
        self.assertEqual(video_out.launched_start_frame(nuke, g, start_frame=180), 180)

    def test_missing_range_knob_uses_root(self):
        nuke = _FakeNuke(first=1001, last=1100)
        self.assertEqual(video_out.launched_start_frame(nuke, _FakeGroup()), 1001)

    def test_set_read_start_at_sets_mode_then_frame(self):
        read = _FakeRead()
        self.assertTrue(video_out._set_read_start_at(read, 151))
        mode = read.knob("frame_mode")
        self.assertEqual(mode.values()[mode.index], "start at")
        self.assertEqual(read.knob("frame").value, 151)


if __name__ == "__main__":
    unittest.main()
