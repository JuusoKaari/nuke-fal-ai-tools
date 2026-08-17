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

from _fal_tools import _TOOLS


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


class TestFalToolsCatalog(unittest.TestCase):
    def test_tool_files_exist(self):
        missing = []
        for _cat, _label, group_file, helper_py, runner_py in _TOOLS:
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
        in_catalog = set(row[2] for row in _TOOLS)
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
        helpers_in_catalog = set(row[3] for row in _TOOLS)
        runners_in_catalog = set(row[4] for row in _TOOLS)
        self.assertEqual(helpers_on_disk, helpers_in_catalog)
        self.assertEqual(runners_on_disk, runners_in_catalog)

    def test_nk_helper_runner_paths_match_catalog(self):
        mismatches = []
        for _cat, label, group_file, helper_py, runner_py in _TOOLS:
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
        for _cat, label, _group, _helper, _runner in _TOOLS:
            prefixed = _nodes_menu_label(label)
            self.assertTrue(prefixed.startswith("fal "))
            self.assertEqual(prefixed, "fal %s" % label)
            self.assertFalse(label.startswith("fal "))


if __name__ == "__main__":
    unittest.main()
