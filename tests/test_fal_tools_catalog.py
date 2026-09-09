# Run: py -3 -m unittest tests.test_fal_tools_catalog
# Catalog consistency: menu _TOOLS rows match shipped group/helper/runner files,
# nk helper/runner paths use the install-root prefix, menu nesting matches family
# counts, and README lists every catalog label with the same grouping.

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
    _TOP_CATEGORY_LABELS,
    _family_counts,
    family_menu_label,
    iter_categorized_menu_entries,
)

_INSTALL_PYTHON_PREFIX = "__INSTALL_ROOT__/nuke/python/"


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
            helper = m_h.group(1).replace("\\", "/")
        m_r = re.match(r'runner_path\s+"([^"]+)"', line)
        if m_r:
            runner = m_r.group(1).replace("\\", "/")
    return helper, runner


def _expected_readme_cell(category):
    parts = []
    for row in _menu_map()[category]:
        if row[0] == "item":
            parts.append(row[1])
        else:
            display = _FAMILY_LABELS[row[1]][1]
            parts.append("**%s** (%s)" % (display, ", ".join(row[2])))
    return ", ".join(parts)


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

    def test_catalog_rows_are_unique(self):
        labels = [row[2] for row in _TOOLS]
        groups = [row[3] for row in _TOOLS]
        helpers = [row[4] for row in _TOOLS]
        runners = [row[5] for row in _TOOLS]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(groups), len(set(groups)))
        self.assertEqual(len(helpers), len(set(helpers)))
        self.assertEqual(len(runners), len(set(runners)))

    def test_every_group_nk_is_catalogued(self):
        on_disk = set(
            name for name in os.listdir(_GROUP_DIR)
            if name.startswith("fal_") and name.endswith(".nk")
        )
        in_catalog = set(row[3] for row in _TOOLS)
        self.assertEqual(on_disk, in_catalog)
        self.assertEqual(
            sorted(os.listdir(_GROUP_DIR)),
            sorted(row[3] for row in _TOOLS),
        )

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
            expected_helper = _INSTALL_PYTHON_PREFIX + helper_py
            expected_runner = _INSTALL_PYTHON_PREFIX + runner_py
            if nk_helper != expected_helper or nk_runner != expected_runner:
                mismatches.append(
                    "%s: nk helper=%s runner=%s catalog helper=%s runner=%s"
                    % (label, nk_helper, nk_runner, expected_helper, expected_runner)
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
        unused = sorted(set(_FAMILY_LABELS) - set(row[1] for row in _TOOLS))
        self.assertEqual(unused, [])

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
            [
                "BiRefNet v2 Still",
                "Depth Anything v2",
                "Finegrain Eraser",
                "Image upscale (Topaz Precision)",
                "SAM 3.1 Image",
            ],
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
            video_sub["minimax"],
            ["MiniMax H3 Image to Video", "MiniMax H3 Max Image to Video"],
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
        three_d_sub = dict(
            (row[1], row[2]) for row in menu["3d"] if row[0] == "submenu"
        )
        self.assertEqual(
            three_d_sub["hunyuan-3d"],
            ["Hunyuan 3D Image to 3D", "Hunyuan 3D Part"],
        )

    def test_single_family_tools_stay_flat(self):
        menu = _menu_map()
        image_items = [row[1] for row in menu["image"] if row[0] == "item"]
        video_items = [row[1] for row in menu["video"] if row[0] == "item"]
        self.assertIn("Bria Extract Object", image_items)
        self.assertIn("Nano Banana 2 Generate", image_items)
        self.assertIn("GPT Image 2 Edit", image_items)
        self.assertIn("Hunyuan World", image_items)
        self.assertIn("Seedream 5.0 Pro Edit", image_items)
        self.assertIn("Kling O3 V2V Edit", video_items)
        self.assertIn("Pika v2.2 Pikaframes", video_items)
        self.assertIn("Veo 3.1 Extend Video", video_items)
        self.assertIn("DreamActor v2 Motion Control", video_items)

    def test_menu_nesting_matches_family_counts(self):
        counts = _family_counts()
        menu = _menu_map()
        seen = set()
        for category, entries in menu.items():
            nested = set(row[1] for row in entries if row[0] == "submenu")
            expected_nested = set(
                family for (cat, family), n in counts.items()
                if cat == category and n >= 2
            )
            self.assertEqual(nested, expected_nested)
            for row in entries:
                if row[0] == "item":
                    seen.add(row[1])
                else:
                    seen.update(row[2])
        self.assertEqual(seen, set(row[2] for row in _TOOLS))

    def test_utility_submenu_is_last_in_image_and_video(self):
        menu = _menu_map()
        self.assertEqual(menu["image"][-1][:2], ("submenu", "utility"))
        self.assertEqual(menu["video"][-1][:2], ("submenu", "utility"))

    def test_readme_tool_count_matches_catalog(self):
        readme_path = os.path.join(_ROOT, "README.md")
        with open(readme_path, "r") as f:
            text = f.read()
        self.assertIn("%s tools under" % len(_TOOLS), text)
        for _cat, _family, label, _group, _helper, _runner in _TOOLS:
            self.assertIn(label, text, "README missing catalog label: %s" % label)
        cells = dict(
            re.findall(
                r"\|\s+\*\*(Image|Video|3D|Text)\*\*\s+\|\s+(.+?)\s+\|",
                text,
            )
        )
        for category in ("image", "video", "3d", "text"):
            heading = _TOP_CATEGORY_LABELS[category]
            self.assertIn(heading, cells)
            self.assertEqual(
                cells[heading],
                _expected_readme_cell(category),
                "README %s tools cell drifted from catalog menu grouping" % heading,
            )


if __name__ == "__main__":
    unittest.main()
