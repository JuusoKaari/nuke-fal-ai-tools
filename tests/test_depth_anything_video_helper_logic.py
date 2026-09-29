# Purpose: No-network tests for Depth Anything Video request payloads.
# Run: py -3 -m unittest tests.test_depth_anything_video_helper_logic

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import fal_depth_anything_video_helper as helper


class TestDepthAnythingVideoPayload(unittest.TestCase):
    def test_defaults_match_the_comp_pass(self):
        payload = helper.build_arguments(
            "https://example.invalid/in.mp4",
            "VDA-Large",
            "grayscale",
            "auto",
            False,
        )
        self.assertEqual(
            payload,
            {
                "video_url": "https://example.invalid/in.mp4",
                "model": "VDA-Large",
                "colormap": "grayscale",
                "resolution": "auto",
                "side_by_side": False,
                "include_raw_depths": True,
            },
        )
        self.assertNotIn("output_fps", payload)
        self.assertNotIn("max_frames", payload)

    def test_raw_depths_sit_next_to_the_mp4(self):
        self.assertEqual(
            helper.raw_depths_path_for_mp4(r"C:\jobs\out\depth_anything_video_20260101.mp4"),
            os.path.abspath(r"C:\jobs\out\depth_anything_video_20260101.npz"),
        )

    def test_side_by_side_is_sent_when_enabled(self):
        payload = helper.build_arguments(
            "https://example.invalid/in.mp4",
            "VDA-Small",
            "turbo",
            "720p",
            True,
        )
        self.assertEqual(payload["model"], "VDA-Small")
        self.assertEqual(payload["colormap"], "turbo")
        self.assertEqual(payload["resolution"], "720p")
        self.assertTrue(payload["side_by_side"])

    def test_unknown_choice_is_rejected(self):
        with self.assertRaises(ValueError):
            helper.build_arguments("https://example.invalid/in.mp4", "huge", "grayscale", "auto", False)
        with self.assertRaises(ValueError):
            helper.build_arguments("https://example.invalid/in.mp4", "VDA-Large", "jet", "auto", False)
        with self.assertRaises(ValueError):
            helper.build_arguments("https://example.invalid/in.mp4", "VDA-Large", "grayscale", "4k", False)


if __name__ == "__main__":
    unittest.main()
