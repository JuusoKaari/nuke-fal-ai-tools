# Run: py -3 -m unittest tests.test_fal_tools_catalog
# Catalog consistency: menu _TOOLS rows match shipped group/helper/runner files.

from __future__ import print_function

import os
import re
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
_GROUP_DIR = os.path.join(_ROOT, "nuke", "groups")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

from _fal_tools import (
    _FAMILY_LABELS,
    _TOOLS,
    family_menu_label,
    iter_categorized_menu_entries,
)


def _nodes_menu_label(label):
    """Nodes / Tab search labels are registered with a fal prefix in menu.py."""
    return "fal %s" % label


def _nk_path_filenames(nk_text):
    helper = None
    runner = None
    for line in nk_text.splitlines():
        line = line.strip()
        m_h = re.match(r'helper_path\s+"([^"]+)"', line)
        if m_h:
            helper = os.path.basename(m_h.group(1).replace("\\", "/"))
        m_r = re.match(r'runner_path\s+"([^"]+)"', line)
        if m_r:
            runner = os.path.basename(m_r.group(1).replace("\\", "/"))
    return helper, runner


def _menu_map():
    """category -> list of ("item", label) or ("submenu", family, [labels])."""
    out = {}
    for category, entries in iter_categorized_menu_entries():
        rows = []
        for entry in entries:
            if entry[0] == "item":
                rows.append(("item", entry[1]))
            else:
                labels = [tool[0] for tool in entry[2]]
                rows.append(("submenu", entry[1], labels))
        out[category] = rows
    return out


class TestFalToolsCatalog(unittest.TestCase):
    def test_tool_files_exist(self):
        missing = []
        for _cat, _family, _label, group_file, helper_py, runner_py in _TOOLS:
            group_path = os.path.join(_GROUP_DIR, group_file)
            helper_path = os.path.join(_PYTHON_DIR, helper_py)
            runner_path = os.path.join(_PYTHON_DIR, runner_py)
            if not os.path.isfile(group_path):
                missing.append(group_path)
            if not os.path.isfile(helper_path):
                missing.append(helper_path)
            if not os.path.isfile(runner_path):
                missing.append(runner_path)
        self.assertEqual(missing, [], "missing catalog files: %s" % missing)

    def test_every_group_nk_is_catalogued(self):
        on_disk = set(
            name for name in os.listdir(_GROUP_DIR)
            if name.startswith("fal_") and name.endswith(".nk")
        )
        in_catalog = set(row[3] for row in _TOOLS)
        self.assertEqual(on_disk, in_catalog)

    def test_every_helper_and_runner_is_catalogued(self):
        helpers_on_disk = set(
            name for name in os.listdir(_PYTHON_DIR)
            if name.startswith("fal_") and name.endswith("_helper.py")
        )
        runners_on_disk = set(
            name for name in os.listdir(_PYTHON_DIR)
            if name.startswith("fal_") and "_runner_" in name and name.endswith(".py")
        )
        helpers_in_catalog = set(row[4] for row in _TOOLS)
        runners_in_catalog = set(row[5] for row in _TOOLS)
        self.assertEqual(helpers_on_disk, helpers_in_catalog)
        self.assertEqual(runners_on_disk, runners_in_catalog)

    def test_nk_helper_runner_paths_match_catalog(self):
        mismatches = []
        for _cat, _family, label, group_file, helper_py, runner_py in _TOOLS:
            nk_path = os.path.join(_GROUP_DIR, group_file)
            with open(nk_path, "r") as f:
                text = f.read()
            nk_helper, nk_runner = _nk_path_filenames(text)
            if nk_helper != helper_py or nk_runner != runner_py:
                mismatches.append(
                    "%s: nk helper=%s runner=%s catalog helper=%s runner=%s"
                    % (label, nk_helper, nk_runner, helper_py, runner_py)
                )
        self.assertEqual(mismatches, [])

    def test_nodes_tab_labels_use_fal_prefix(self):
        for _cat, _family, label, _group, _helper, _runner in _TOOLS:
            prefixed = _nodes_menu_label(label)
            self.assertTrue(prefixed.startswith("fal "))
            self.assertEqual(prefixed, "fal %s" % label)
            self.assertFalse(label.startswith("fal "))

    def test_every_family_has_labels(self):
        unknown = sorted(set(
            family for _cat, family, _label, _g, _h, _r in _TOOLS
            if family not in _FAMILY_LABELS
        ))
        self.assertEqual(unknown, [])

    def test_family_menu_labels(self):
        self.assertEqual(family_menu_label("qwen", True), "fal-qwen")
        self.assertEqual(family_menu_label("qwen", False), "Qwen")
        self.assertEqual(family_menu_label("utility", True), "fal-utility")
        self.assertEqual(family_menu_label("ltx", False), "LTX")

    def test_families_with_two_plus_tools_nest(self):
        menu = _menu_map()
        image_sub = dict(
            (row[1], row[2]) for row in menu["image"] if row[0] == "submenu"
        )
        video_sub = dict(
            (row[1], row[2]) for row in menu["video"] if row[0] == "submenu"
        )
        text_sub = dict(
            (row[1], row[2]) for row in menu["text"] if row[0] == "submenu"
        )
        self.assertEqual(
            image_sub["qwen"],
            ["Qwen Image Inpaint", "Qwen Image Layered", "Qwen Image Max Edit"],
        )
        self.assertEqual(
            image_sub["utility"],
            ["BiRefNet v2 Still", "Depth Anything v2", "Finegrain Eraser", "Image upscale (Topaz Precision)"],
        )
        self.assertEqual(
            video_sub["ltx"],
            ["LTX 2.3 Image to Video", "LTX 2.5 Image to Video Pro"],
        )
        self.assertEqual(
            video_sub["flux"],
            ["FLUX 3 First/Last Frame to Video", "FLUX 3 Keyframes to Video"],
        )
        self.assertEqual(
            video_sub["seedance"],
            ["Seedance 2 Image to Video", "Seedance 2 Reference to Video", "Seedance 2.5 Image to Video"],
        )
        self.assertEqual(
            video_sub["utility"],
            ["BiRefNet v2", "ByteDance Video Upscale"],
        )
        self.assertEqual(text_sub["openrouter"], ["Describe image", "Generate text"])

    def test_single_family_tools_stay_flat(self):
        menu = _menu_map()
        image_items = [row[1] for row in menu["image"] if row[0] == "item"]
        video_items = [row[1] for row in menu["video"] if row[0] == "item"]
        self.assertIn("Nano Banana 2 Generate", image_items)
        self.assertIn("GPT Image 2 Edit", image_items)
        self.assertIn("Hunyuan World", image_items)
        self.assertIn("Kling O3 V2V Edit", video_items)
        self.assertIn("MiniMax H3 Image to Video", video_items)
        self.assertIn("Pika v2.2 Pikaframes", video_items)
        self.assertIn("Veo 3.1 Extend Video", video_items)
        self.assertIn("DreamActor v2 Motion Control", video_items)

    def test_utility_submenu_is_last_in_image_and_video(self):
        menu = _menu_map()
        self.assertEqual(menu["image"][-1][:2], ("submenu", "utility"))
        self.assertEqual(menu["video"][-1][:2], ("submenu", "utility"))


if __name__ == "__main__":
    unittest.main()
