# Run: py -3 -m unittest tests.test_group_output_preview_logic
# Pure-logic tests for nuke_group_output_preview_v1 (no Nuke required).

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_group_output_preview_v1 as preview


class TestViewerModeMapping(unittest.TestCase):
    def test_all_modes_map_to_expected_index(self):
        for i, mode in enumerate(preview.VIEWER_MODES):
            self.assertEqual(preview.viewer_mode_to_switch_index(mode), i)

    def test_unknown_mode_defaults_to_guide(self):
        self.assertEqual(preview.viewer_mode_to_switch_index("invalid"), 0)

    def test_read_viewer_mode_from_index(self):
        class _Knob(object):
            def __init__(self, value):
                self._value = value

            def value(self):
                return self._value

        class _Group(object):
            def __init__(self, value):
                self._value = value

            def knob(self, name):
                return _Knob(self._value)

        self.assertEqual(preview._read_viewer_mode(_Group(1)), "Generated")
        self.assertEqual(preview._read_viewer_mode(_Group("Generated")), "Generated")


class TestContactSheetLayout(unittest.TestCase):
    def test_single_item(self):
        self.assertEqual(preview.contactsheet_rows_cols(1), (1, 1))

    def test_two_items(self):
        self.assertEqual(preview.contactsheet_rows_cols(2), (1, 2))

    def test_four_items(self):
        self.assertEqual(preview.contactsheet_rows_cols(4), (2, 2))

    def test_six_items(self):
        rows, cols = preview.contactsheet_rows_cols(6)
        self.assertGreaterEqual(rows * cols, 6)


class TestLabels(unittest.TestCase):
    def test_preview_index_range_max(self):
        self.assertEqual(preview.preview_index_range_max(1), 1.999)
        self.assertEqual(preview.preview_index_range_max(4), 4.999)

    def test_preview_index_labels(self):
        self.assertEqual(preview.preview_index_labels(3), ["1", "2", "3"])

    def test_ai_input_letters(self):
        self.assertEqual(preview.ai_input_letter_labels(3), ["A", "B", "C"])


class TestGridMode(unittest.TestCase):
    def test_single_item_hides_grid(self):
        self.assertFalse(preview.should_show_grid_mode(1))
        self.assertFalse(preview.should_show_grid_mode(0))

    def test_multiple_items_show_grid(self):
        self.assertTrue(preview.should_show_grid_mode(2))


class TestToolConfig(unittest.TestCase):
    def test_nano_banana_config_exists(self):
        cfg = preview.TOOL_PREVIEW_CONFIG.get("Nano_Banana_2_Generate_v1")
        self.assertIsNotNone(cfg)
        self.assertIn("image_a", cfg["preview_inputs"])
        self.assertEqual(cfg["max_outputs"], 4)
        self.assertTrue(cfg.get("accumulate_outputs"))


class TestOutputRegistry(unittest.TestCase):
    def test_parse_empty_registry(self):
        self.assertEqual(preview.parse_output_paths_registry(""), [])
        self.assertEqual(preview.parse_output_paths_registry(None), [])

    def test_parse_and_serialize_roundtrip(self):
        raw = "C:/a/out1.png\nC:/a/out2.png\n"
        paths = preview.parse_output_paths_registry(raw)
        self.assertEqual(paths, ["C:/a/out1.png", "C:/a/out2.png"])
        self.assertEqual(
            preview.serialize_output_paths_registry(paths),
            "C:/a/out1.png\nC:/a/out2.png",
        )

    def test_merge_appends_without_duplicates(self):
        merged = preview.merge_output_paths(
            ["C:/a/1.png"],
            ["C:/a/2.png", "C:/a/1.png", "C:/a/3.png"],
            max_stored=10,
        )
        self.assertEqual(merged, ["C:/a/1.png", "C:/a/2.png", "C:/a/3.png"])

    def test_merge_caps_stored_outputs(self):
        merged = preview.merge_output_paths(
            ["C:/a/%d.png" % i for i in range(1, 6)],
            ["C:/a/6.png", "C:/a/7.png"],
            max_stored=5,
        )
        self.assertEqual(len(merged), 5)
        self.assertEqual(merged[0], "C:/a/3.png")
        self.assertEqual(merged[-1], "C:/a/7.png")

    def test_generated_read_node_name(self):
        self.assertEqual(preview.generated_read_node_name(1), "generated_read_01")
        self.assertEqual(preview.generated_read_node_name(99), "generated_read_99")
        self.assertEqual(preview.generated_read_node_name(100), "generated_read_100")


if __name__ == "__main__":
    unittest.main()
