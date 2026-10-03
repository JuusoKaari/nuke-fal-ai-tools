# Run: py -3 -m unittest tests.test_prerender_video_logic
# Pure-logic tests for nuke_prerender_video_v1 ffmpeg encode args (no Nuke, no ffmpeg).

from __future__ import print_function

import os
import shutil
import sys
import tempfile
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
        self.assertEqual(args[args.index("-crf") + 1], "18")
        self.assertEqual(args[args.index("-start_number") + 1], "7")
        self.assertEqual(args[-1], "C:/tmp/video_1.mp4")

    def test_crf_is_passed_through(self):
        args = prerender_video.ffmpeg_encode_args(
            "frames_%04d.png", 1, 24.0, "out.mp4", crf=28
        )
        self.assertEqual(args[args.index("-crf") + 1], "28")


class TestQualityLadder(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="fal_prerender_")
        self.out_path = os.path.join(self._dir, "out.mp4")

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _writer(self, sizes, calls):
        def encode(crf):
            calls.append(crf)
            with open(self.out_path, "wb") as handle:
                handle.write(b"x" * int(sizes[crf]))

        return encode

    def test_no_cap_encodes_once_at_crf_18(self):
        calls = []
        prerender_video.encode_down_to_size(
            self._writer({18: 10}, calls), self.out_path, None, ladder=(18, 23)
        )
        self.assertEqual(calls, [18])

    def test_steps_down_until_the_file_fits(self):
        calls = []
        sizes = {18: 300, 20: 250, 23: 180}
        prerender_video.encode_down_to_size(
            self._writer(sizes, calls), self.out_path, 200, ladder=(18, 20, 23)
        )
        self.assertEqual(calls, [18, 20, 23])
        self.assertEqual(os.path.getsize(self.out_path), 180)

    def test_raises_when_the_smallest_file_is_still_over_the_cap(self):
        calls = []
        sizes = {18: 500, 23: 400}
        with self.assertRaises(Exception) as caught:
            prerender_video.encode_down_to_size(
                self._writer(sizes, calls), self.out_path, 100, ladder=(18, 23)
            )
        self.assertEqual(calls, [18, 23])
        self.assertIn("upload cap", str(caught.exception))

    def test_split_byte_budget_divides_the_combined_cap(self):
        total = prerender_video.SEEDANCE_20_REFERENCE_TOTAL_BYTES
        self.assertEqual(prerender_video.split_byte_budget(total, 2), int(total // 2))
        self.assertIsNone(prerender_video.split_byte_budget(total, 0))

    def test_kling_cap_matches_schema_bytes(self):
        self.assertEqual(prerender_video.KLING_O3_V2V_MAX_BYTES, 209715200)


if __name__ == "__main__":
    unittest.main()
