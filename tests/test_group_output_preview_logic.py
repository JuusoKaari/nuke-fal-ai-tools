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
        self.assertTrue(cfg.get("supports_roi"))
        self.assertTrue(cfg.get("accumulate_outputs"))


class TestToolIdResolution(unittest.TestCase):
    def test_resolve_from_fal_tool_id_knob(self):
        tool_id = preview.resolve_tool_id(
            tool_id_knob_value="Nano_Banana_2_Generate_v1",
            runner_path="",
            display_name="Nano_Banana_2_Generate_v3",
        )
        self.assertEqual(tool_id, "Nano_Banana_2_Generate_v1")

    def test_resolve_from_runner_path_when_renamed(self):
        tool_id = preview.resolve_tool_id(
            tool_id_knob_value="",
            runner_path="__INSTALL_ROOT__/nuke/python/fal_nano_banana_2_generate_runner_v1.py",
            display_name="Nano_Banana_2_Generate_v3",
        )
        self.assertEqual(tool_id, "Nano_Banana_2_Generate_v1")

    def test_legacy_display_name_fallback(self):
        tool_id = preview.resolve_tool_id(
            tool_id_knob_value="",
            runner_path="",
            display_name="Nano_Banana_2_Generate_v1",
        )
        self.assertEqual(tool_id, "Nano_Banana_2_Generate_v1")

    def test_unknown_tool_returns_none(self):
        self.assertIsNone(
            preview.resolve_tool_id(
                tool_id_knob_value="",
                runner_path="",
                display_name="Some_Other_Node_v9",
            )
        )

    def test_get_config_for_group_uses_runner_path_not_display_name(self):
        class _Knob(object):
            def __init__(self, value):
                self._value = value

            def value(self):
                return self._value

        class _Group(object):
            def __init__(self, name, knobs):
                self._name = name
                self._knobs = knobs

            def name(self):
                return self._name

            def knob(self, key):
                return self._knobs.get(key)

        group = _Group(
            "Nano_Banana_2_Generate_v3",
            {
                preview.RUNNER_PATH_KNOB: _Knob(
                    "C:/plugins/nuke/python/fal_nano_banana_2_generate_runner_v1.py"
                ),
            },
        )
        cfg = preview.get_config_for_group(group)
        self.assertIsNotNone(cfg)
        self.assertIn("image_a", cfg["preview_inputs"])


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


class TestRoiBboxValidation(unittest.TestCase):
    def test_valid_bbox(self):
        ok, err = preview.validate_roi_bbox((10, 20, 100, 200))
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_invalid_empty_bbox(self):
        ok, err = preview.validate_roi_bbox((100, 200, 100, 300))
        self.assertFalse(ok)
        self.assertIn("invalid", err.lower())

    def test_none_bbox(self):
        ok, err = preview.validate_roi_bbox(None)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
