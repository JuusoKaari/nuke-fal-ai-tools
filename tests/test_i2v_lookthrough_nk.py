# Inspect still-to-video Group .nk files for look-through (no Nuke).
# Run: py -3 -m unittest tests.test_i2v_lookthrough_nk

from __future__ import print_function

import os
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_GROUP_DIR = os.path.join(_ROOT, "nuke", "groups")

# filename, primary still Input name
_LOOKTHROUGH_GROUPS = (
    ("fal_seedance_25_image_to_video_v1.nk", "start_image"),
    ("fal_seedance_2_image_to_video_v1.nk", "start_image"),
    ("fal_ltx_23_image_to_video_v1.nk", "start_image"),
    ("fal_ltx_25_image_to_video_pro_v1.nk", "start_image"),
    ("fal_minimax_h3_image_to_video_v1.nk", "start_image"),
    ("fal_minimax_h3_max_image_to_video_v1.nk", "start_image"),
    ("fal_flux_3_first_last_frame_to_video_v1.nk", "start_image"),
    ("fal_flux_3_keyframes_to_video_v1.nk", "keyframe_1"),
    ("fal_pika_v22_pikaframes_v1.nk", "keyframe_1"),
    ("fal_seedance_2_reference_to_video_v1.nk", "image_1"),
    ("fal_seedance_25_reference_to_video_v1.nk", "image_1"),
)

_IMAGE_PREVIEW_MARKERS = (
    "viewer_mode_switch",
    "generated_read_01",
)


def _read_nk(filename):
    path = os.path.join(_GROUP_DIR, filename)
    with open(path, "r") as handle:
        return handle.read()


def _name_token(node_name):
    return " name %s\n" % node_name


def _input_indices(text):
    """Map each Input node name to its external index. Omitted number means 0."""
    indices = {}
    for block in text.split("Input {")[1:]:
        body = block.split("}", 1)[0]
        name = None
        number = 0
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("name "):
                name = line.split(" ", 1)[1].strip()
            elif line.startswith("number "):
                number = int(line.split(" ", 1)[1].strip())
        if name:
            indices[name] = number
    return indices


class TestI2VLookthroughNk(unittest.TestCase):
    def test_each_group_looks_through_primary_still(self):
        for filename, primary in _LOOKTHROUGH_GROUPS:
            text = _read_nk(filename)
            with self.subTest(filename=filename):
                self.assertIn("addUserKnob {26 guide_info", text)
                self.assertIn(_name_token("Output1"), text)
                self.assertIn(_name_token(primary), text)
                self.assertNotIn("name Text1", text)
                self.assertNotIn("\nText {", text)
                for marker in _IMAGE_PREVIEW_MARKERS:
                    self.assertNotIn(marker, text)
                primary_pos = text.find(_name_token(primary))
                output_pos = text.find(_name_token("Output1"))
                self.assertLess(
                    primary_pos,
                    output_pos,
                    "%s: primary Input %s must precede Output1 on the stack"
                    % (filename, primary),
                )

    def test_optional_inputs_keep_original_names(self):
        seedance = _read_nk("fal_seedance_25_image_to_video_v1.nk")
        self.assertIn(_name_token("end_image"), seedance)
        flux_fl = _read_nk("fal_flux_3_first_last_frame_to_video_v1.nk")
        self.assertIn(_name_token("end_image"), flux_fl)
        flux_kf = _read_nk("fal_flux_3_keyframes_to_video_v1.nk")
        self.assertIn(_name_token("keyframe_10"), flux_kf)
        pika = _read_nk("fal_pika_v22_pikaframes_v1.nk")
        self.assertIn(_name_token("keyframe_5"), pika)
        ref = _read_nk("fal_seedance_2_reference_to_video_v1.nk")
        self.assertIn(_name_token("image_9"), ref)
        self.assertIn(_name_token("video_1"), ref)
        self.assertIn(_name_token("video_3"), ref)
        self.assertEqual(
            _input_indices(ref),
            {
                "image_1": 0,
                "image_2": 1,
                "video_1": 2,
                "video_2": 3,
                "image_3": 4,
                "image_4": 5,
                "image_5": 6,
                "image_6": 7,
                "image_7": 8,
                "image_8": 9,
                "image_9": 10,
                "video_3": 11,
            },
        )
        ref25 = _read_nk("fal_seedance_25_reference_to_video_v1.nk")
        self.assertIn(_name_token("image_1"), ref25)
        self.assertIn(_name_token("image_9"), ref25)
        self.assertIn(_name_token("video_1"), ref25)
        self.assertIn(_name_token("video_3"), ref25)
        self.assertEqual(
            _input_indices(ref25),
            {
                "image_1": 0,
                "image_2": 1,
                "video_1": 2,
                "video_2": 3,
                "image_3": 4,
                "image_4": 5,
                "image_5": 6,
                "image_6": 7,
                "image_7": 8,
                "image_8": 9,
                "image_9": 10,
                "video_3": 11,
            },
        )


if __name__ == "__main__":
    unittest.main()
