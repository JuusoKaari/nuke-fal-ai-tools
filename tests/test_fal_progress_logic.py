# Run: py -3 -m unittest tests.test_fal_progress_logic
# Pure-logic tests for nuke_fal_progress_v1 line parsing (no Nuke required).

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_fal_progress_v1 as fal_progress


class TestFalProgressLogic(unittest.TestCase):
    def test_decode_subprocess_line_bytes(self):
        self.assertEqual(fal_progress.decode_subprocess_line(b"hello"), "hello")

    def test_noise_filters_tqdm(self):
        self.assertTrue(fal_progress.is_progress_noise("100%|##########| 1/1 [00:01<00:00,  1.00s/it]"))

    def test_submit_sets_waiting_phase(self):
        state = {"progress": 0, "message": "x", "phase": "start"}
        changed = fal_progress.progress_update_from_line("Submitting request: fal-ai/nano-banana-2", state)
        self.assertTrue(changed)
        self.assertEqual(state["phase"], "waiting")
        self.assertGreaterEqual(state["progress"], 25)

    def test_download_progress(self):
        state = {"progress": 0, "message": "x", "phase": "waiting"}
        fal_progress.progress_update_from_line("Downloading 2/4 -> C:/tmp/image.png", state)
        self.assertEqual(state["phase"], "download")
        self.assertGreater(state["progress"], 80)

    def test_json_ok_completes(self):
        state = {"progress": 50, "message": "x", "phase": "waiting"}
        changed = fal_progress.progress_update_from_line('{"ok": true, "downloaded": []}', state)
        self.assertTrue(changed)
        self.assertEqual(state["progress"], 100)
        self.assertEqual(state["message"], "Done")


if __name__ == "__main__":
    unittest.main()
