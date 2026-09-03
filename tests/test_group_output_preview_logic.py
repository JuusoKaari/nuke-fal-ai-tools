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
        self.assertEqual(preview.preview_kind_for_config(cfg), "editor")
        self.assertTrue(preview.wants_roi_knobs(cfg))
        self.assertTrue(preview.wants_history_knobs(cfg))
        self.assertEqual(
            preview.viewer_modes_for_config(cfg),
            ["Input", "Generated", "Generated grid"],
        )
        self.assertEqual(preview.VIEWER_MODES, ["Input", "Generated", "Generated grid"])
        knobs = preview.requested_preview_knob_names(cfg)
        self.assertIn(preview.USE_ROI_KNOB, knobs)
        self.assertIn("preview_index", knobs)
        self.assertIn(preview.OUTPUT_PATHS_REGISTRY_KNOB, knobs)


class TestPreviewConfigKinds(unittest.TestCase):
    def test_fake_filter_skips_history_and_roi_knobs(self):
        cfg = {
            "preview_kind": "filter",
            "preview_inputs": ["source_image"],
            "max_outputs": 1,
            "viewer_modes": ["Input", "Generated"],
        }
        self.assertEqual(preview.preview_kind_for_config(cfg), "filter")
        self.assertFalse(preview.wants_roi_knobs(cfg))
        self.assertFalse(preview.wants_history_knobs(cfg))
        self.assertEqual(
            preview.viewer_modes_for_config(cfg), ["Input", "Generated"]
        )
        self.assertEqual(preview.VIEWER_MODES, ["Input", "Generated", "Generated grid"])
        knobs = preview.requested_preview_knob_names(cfg)
        self.assertNotIn("preview_index", knobs)
        self.assertNotIn(preview.EXTRACT_SELECTED_KNOB, knobs)
        self.assertNotIn(preview.CLEAR_HISTORY_KNOB, knobs)
        self.assertNotIn(preview.OUTPUT_PATHS_REGISTRY_KNOB, knobs)
        self.assertNotIn(preview.USE_ROI_KNOB, knobs)
        self.assertNotIn(preview.ROI_AREA_KNOB, knobs)

    def test_filter_without_viewer_modes_still_skips_grid(self):
        cfg = {"preview_kind": "filter", "preview_inputs": ["source_image"]}
        self.assertEqual(
            preview.viewer_modes_for_config(cfg), preview.FILTER_VIEWER_MODES
        )
        self.assertNotIn("Generated grid", preview.viewer_modes_for_config(cfg))

    def test_fake_editor_without_supports_roi_skips_roi_knobs(self):
        cfg = {
            "preview_inputs": ["ref_image_a"],
            "max_outputs": 4,
            "accumulate_outputs": True,
        }
        self.assertEqual(preview.preview_kind_for_config(cfg), "editor")
        self.assertFalse(preview.config_supports_roi(cfg))
        self.assertFalse(preview.wants_roi_knobs(cfg))
        self.assertTrue(preview.wants_history_knobs(cfg))
        knobs = preview.requested_preview_knob_names(cfg)
        self.assertNotIn(preview.USE_ROI_KNOB, knobs)
        self.assertNotIn(preview.ROI_AREA_KNOB, knobs)
        self.assertIn("preview_index", knobs)
        self.assertIn(preview.EXTRACT_SELECTED_KNOB, knobs)
        self.assertIn(preview.CLEAR_HISTORY_KNOB, knobs)
        self.assertIn(preview.OUTPUT_PATHS_REGISTRY_KNOB, knobs)

    def test_layers_skips_roi_keeps_history(self):
        cfg = {
            "preview_kind": "layers",
            "preview_inputs": ["source_image"],
            "max_outputs": 10,
            "supports_roi": True,
        }
        self.assertEqual(preview.preview_kind_for_config(cfg), "layers")
        self.assertFalse(preview.wants_roi_knobs(cfg))
        self.assertTrue(preview.wants_history_knobs(cfg))
        self.assertTrue(preview.spawn_reads_in_graph_default(cfg))
        knobs = preview.requested_preview_knob_names(cfg)
        self.assertNotIn(preview.USE_ROI_KNOB, knobs)
        self.assertIn("preview_index", knobs)

    def test_unknown_preview_kind_defaults_to_editor(self):
        cfg = {"preview_kind": "video"}
        self.assertEqual(preview.preview_kind_for_config(cfg), "editor")
        self.assertFalse(preview.spawn_reads_in_graph_default(cfg))

    def test_production_config_has_nano_banana_and_gpt(self):
        self.assertEqual(
            list(preview.TOOL_PREVIEW_CONFIG.keys()),
            ["Nano_Banana_2_Generate_v1", "GPT_Image_2_Edit_v1"],
        )


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

    def test_resolve_gpt_runner_basename(self):
        tool_id = preview.resolve_tool_id_from_runner_path(
            "__INSTALL_ROOT__/nuke/python/fal_gpt_image_2_edit_runner_v1.py"
        )
        self.assertEqual(tool_id, "GPT_Image_2_Edit_v1")
        cfg = preview.TOOL_PREVIEW_CONFIG[tool_id]
        self.assertFalse(cfg.get("supports_roi"))
        self.assertFalse(preview.config_supports_roi(cfg))
        self.assertFalse(preview.wants_roi_knobs(cfg))


class TestGptImage2EditPreview(unittest.TestCase):
    def _gpt_nk_text(self):
        path = os.path.join(_ROOT, "nuke", "groups", "fal_gpt_image_2_edit_v1.nk")
        with open(path, "r") as f:
            return f.read()

    def test_gpt_config_is_editor_without_roi(self):
        cfg = preview.TOOL_PREVIEW_CONFIG.get("GPT_Image_2_Edit_v1")
        self.assertIsNotNone(cfg)
        self.assertEqual(preview.preview_kind_for_config(cfg), "editor")
        self.assertEqual(cfg["preview_inputs"], ["ref_image_a", "ref_image_b"])
        self.assertEqual(cfg["max_outputs"], 4)
        self.assertFalse(cfg.get("supports_roi"))
        self.assertTrue(cfg.get("accumulate_outputs"))
        self.assertFalse(preview.spawn_reads_in_graph_default(cfg))
        knobs = preview.requested_preview_knob_names(cfg)
        self.assertNotIn(preview.USE_ROI_KNOB, knobs)
        self.assertNotIn(preview.ROI_AREA_KNOB, knobs)
        self.assertIn("preview_index", knobs)

    def test_gpt_nk_has_baked_preview_without_roi(self):
        text = self._gpt_nk_text()
        self.assertIn("viewer_mode_switch", text)
        self.assertIn("generated_read_01", text)
        self.assertIn("fal_tool_id GPT_Image_2_Edit_v1", text)
        self.assertNotIn("ROI_rectangle", text)
        self.assertNotIn("use_roi", text)
        self.assertIn("name ref_image_a", text)
        self.assertIn("name ref_image_b", text)
        self.assertIn("name prompt_text", text)
        self.assertIn("name mask", text)
        self.assertNotIn("name Text1", text)


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

    def test_selected_output_path(self):
        paths = ["C:/a/1.png", "C:/a/2.png", "C:/a/3.png"]
        self.assertEqual(preview.selected_output_path(paths, 1), "C:/a/1.png")
        self.assertEqual(preview.selected_output_path(paths, 3), "C:/a/3.png")
        self.assertIsNone(preview.selected_output_path(paths, 0))
        self.assertIsNone(preview.selected_output_path(paths, 4))
        self.assertIsNone(preview.selected_output_path([], 1))
        self.assertIsNone(preview.selected_output_path(None, 1))
        self.assertIsNone(preview.selected_output_path(paths, "x"))


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
