# Purpose: Pixel-size tests for GPT Image 2.5 Resolution tiers. No network.
# Run: py -3 -m unittest tests.test_gpt_image_25_resolution

from __future__ import print_function

import os
import struct
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import fal_gpt_image_25_resolution as resolution


def _assert_legal(test, width, height):
    test.assertEqual(width % resolution.DIVISOR, 0)
    test.assertEqual(height % resolution.DIVISOR, 0)
    test.assertGreaterEqual(width, resolution.DIVISOR)
    test.assertGreaterEqual(height, resolution.DIVISOR)
    test.assertLessEqual(width, resolution.MAX_EDGE)
    test.assertLessEqual(height, resolution.MAX_EDGE)
    pixels = width * height
    test.assertGreaterEqual(pixels, resolution.MIN_PIXELS)
    test.assertLessEqual(pixels, resolution.MAX_PIXELS)
    long_edge = max(width, height)
    short_edge = min(width, height)
    test.assertLessEqual(long_edge, short_edge * resolution.MAX_ASPECT)


class TestGptImage25Resolution(unittest.TestCase):
    def test_match_input_is_auto_on_edit_and_a_preset_on_generate(self):
        self.assertEqual(
            resolution.resolve_image_size("Match input", True, "square", 1920, 1080),
            "auto",
        )
        self.assertEqual(
            resolution.resolve_image_size("match_input", True, "landscape_16_9", 4096, 2160),
            "auto",
        )
        self.assertEqual(
            resolution.resolve_image_size("Match input", False, "landscape_4_3"),
            "landscape_4_3",
        )

    def test_16x9_tiers(self):
        self.assertEqual(resolution.fit_output_size(1920, 1080, "1K"), (1088, 608))
        self.assertEqual(resolution.fit_output_size(1920, 1080, "2K"), (2048, 1152))
        self.assertEqual(resolution.fit_output_size(1920, 1080, "4K"), (3840, 2160))
        width, height = resolution.fit_output_size(1920, 1080, "4K")
        self.assertNotEqual(width, 4096)
        self.assertEqual(width * height, resolution.MAX_PIXELS)

    def test_portrait_tiers(self):
        self.assertEqual(resolution.fit_output_size(1080, 1920, "1K"), (608, 1088))
        self.assertEqual(resolution.fit_output_size(1080, 1920, "2K"), (1152, 2048))
        self.assertEqual(resolution.fit_output_size(1080, 1920, "4K"), (2160, 3840))
        self.assertEqual(resolution.fit_output_size(100, 200, "2K"), (1024, 2048))
        self.assertEqual(resolution.fit_output_size(100, 200, "4K"), (1920, 3840))

    def test_1k_16x9_meets_minimum_pixels(self):
        width, height = resolution.fit_output_size(1920, 1080, "1K")
        self.assertEqual((width, height), (1088, 608))
        self.assertGreaterEqual(width * height, resolution.MIN_PIXELS)
        self.assertLess(1024 * 576, resolution.MIN_PIXELS)

    def test_odd_aspect_rounds_to_multiples_of_16(self):
        self.assertEqual(resolution.fit_output_size(1000, 700, "2K"), (2048, 1440))
        self.assertEqual(resolution.fit_output_size(700, 1000, "2K"), (1440, 2048))
        self.assertEqual(resolution.fit_output_size(777, 333, "1K"), (1248, 528))
        self.assertEqual(resolution.fit_output_size(1919, 1080, "2K"), (2048, 1152))
        for src_w, src_h, tier in (
            (1000, 700, "1K"),
            (1000, 700, "4K"),
            (777, 333, "2K"),
            (333, 777, "4K"),
            (1920, 1081, "4K"),
            (1919, 1080, "1K"),
        ):
            width, height = resolution.fit_output_size(src_w, src_h, tier)
            _assert_legal(self, width, height)

    def test_max_edge_is_3840(self):
        self.assertEqual(resolution.fit_output_size(4096, 2160, "4K"), (3840, 2032))
        self.assertEqual(resolution.fit_output_size(8000, 4500, "4K"), (3840, 2160))
        self.assertEqual(resolution.fit_output_size(2160, 4096, "4K"), (2032, 3840))
        width, height = resolution.fit_output_size(4096, 2160, "4K")
        self.assertLessEqual(max(width, height), 3840)
        self.assertNotEqual(width, 4096)

    def test_max_pixels(self):
        self.assertEqual(resolution.fit_output_size(1000, 1000, "4K"), (2880, 2880))
        width, height = resolution.fit_output_size(1000, 1000, "4K")
        self.assertEqual(width * height, resolution.MAX_PIXELS)
        wide_w, wide_h = resolution.fit_output_size(1000, 700, "4K")
        self.assertEqual((wide_w, wide_h), (3440, 2400))
        self.assertLessEqual(wide_w * wide_h, resolution.MAX_PIXELS)
        self.assertLess(wide_w, 3840)
        four_three = resolution.fit_output_size(4, 3, "4K")
        self.assertEqual(four_three, (3312, 2496))
        self.assertLessEqual(four_three[0] * four_three[1], resolution.MAX_PIXELS)

    def test_min_pixels_and_aspect_cap(self):
        self.assertEqual(resolution.fit_output_size(4000, 200, "4K"), (3840, 1280))
        self.assertEqual(resolution.fit_output_size(4000, 200, "1K"), (1408, 480))
        self.assertEqual(resolution.fit_output_size(200, 4000, "4K"), (1280, 3840))
        for tier in ("1K", "2K", "4K"):
            width, height = resolution.fit_output_size(4000, 200, tier)
            _assert_legal(self, width, height)
            self.assertLessEqual(max(width, height), min(width, height) * 3)

    def test_generate_tier_uses_preset_aspect(self):
        self.assertEqual(
            resolution.resolve_image_size("4K", False, "landscape_16_9"),
            {"width": 3840, "height": 2160},
        )
        self.assertEqual(
            resolution.resolve_image_size("2K", False, "portrait_16_9"),
            {"width": 1152, "height": 2048},
        )
        self.assertEqual(
            resolution.resolve_image_size("1K", False, "square"),
            {"width": 1024, "height": 1024},
        )
        self.assertEqual(
            resolution.resolve_image_size("4K", False, "auto"),
            "auto",
        )

    def test_edit_tier_ignores_preset_when_pixels_are_known(self):
        self.assertEqual(
            resolution.resolve_image_size("2K", True, "square", 1920, 1080),
            {"width": 2048, "height": 1152},
        )

    def test_png_and_jpeg_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            png_path = os.path.join(folder, "plate.png")
            ihdr = struct.pack(">IIBBBBB", 1920, 1080, 8, 2, 0, 0, 0)
            with open(png_path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\n")
                handle.write(struct.pack(">I", len(ihdr)))
                handle.write(b"IHDR" + ihdr)
                handle.write(b"\x00\x00\x00\x00")
            self.assertEqual(resolution.read_image_size(png_path), (1920, 1080))

            jpeg_path = os.path.join(folder, "plate.jpg")
            app0 = b"JFIF\x00"
            sof = struct.pack(">BHHB", 8, 1080, 1920, 1)
            with open(jpeg_path, "wb") as handle:
                handle.write(b"\xff\xd8")
                handle.write(b"\xff\xe0" + struct.pack(">H", 2 + len(app0)) + app0)
                handle.write(b"\xff\xc0" + struct.pack(">H", 2 + len(sof)) + sof)
                handle.write(b"\xff\xd9")
            self.assertEqual(resolution.read_image_size(jpeg_path), (1920, 1080))

            junk_path = os.path.join(folder, "notes.png")
            with open(junk_path, "wb") as handle:
                handle.write(b"not an image")
            self.assertIsNone(resolution.read_image_size(junk_path))

    def test_half_k_is_not_a_tier(self):
        self.assertIsNone(resolution.normalize_resolution("0.5K"))
        self.assertNotIn("0.5K", resolution.RESOLUTION_CHOICES)


if __name__ == "__main__":
    unittest.main()
