# Run: py -3 -m unittest tests.test_prerender_video_logic
# Pure-logic tests for nuke_prerender_video_v1 ffmpeg encode args (no Nuke, no ffmpeg).

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_prerender_video_v1 as prerender_video


class TestFfmpegEncodeArgs(unittest.TestCase):
    def test_even_dimension_scale_filter_is_present(self):
        args = prerender_video.ffmpeg_encode_args(
            "frames_%04d.png", 1, 24.0, "out.mp4"
        )
        self.assertIn("-vf", args)
        vf = args[args.index("-vf") + 1]
        self.assertEqual(vf, prerender_video._EVEN_DIM_VF)
        self.assertIn("trunc(iw/2)*2", vf)
        self.assertIn("trunc(ih/2)*2", vf)

    def test_encoder_and_pixel_format(self):
        args = prerender_video.ffmpeg_encode_args(
            "frames_%04d.png", 7, 25.0, "C:/tmp/video_1.mp4"
        )
        self.assertEqual(args[0], "ffmpeg")
        self.assertIn("libx264", args)
        self.assertIn("yuv420p", args)
        self.assertEqual(args[args.index("-start_number") + 1], "7")
        self.assertEqual(args[-1], "C:/tmp/video_1.mp4")


if __name__ == "__main__":
    unittest.main()
