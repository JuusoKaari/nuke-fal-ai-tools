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


if __name__ == "__main__":
    unittest.main()
