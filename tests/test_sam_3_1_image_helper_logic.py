# Purpose: No-network tests for the SAM 3.1 Image helper (empty match vs bad shape).
# Run: py -3 -m unittest tests.test_sam_3_1_image_helper_logic

from __future__ import print_function

import io
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import fal_sam_3_1_image_helper as helper


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_EMPTY_RESULT = {
    "image": None,
    "masks": [],
    "metadata": None,
    "scores": None,
    "boxes": None,
}


def _no_network(*_args, **_kwargs):
    raise AssertionError("network is forbidden in helper tests")


def _fake_download(url, out_path, user_agent, timeout_seconds=60):
    del url, user_agent, timeout_seconds
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(_PNG_BYTES)


class _FakeSyncClient(object):
    last = None

    def __init__(self, key=None):
        self.key = key
        self.uploaded = []
        _FakeSyncClient.last = self

    def upload_file(self, path):
        self.uploaded.append(path)
        return "https://example.invalid/uploaded.png"


class TestSAM31ImageHelperLogic(unittest.TestCase):
    def setUp(self):
        self._prev_fal = sys.modules.get("fal_client")
        fake_pkg = types.ModuleType("fal_client")
        fake_pkg.SyncClient = _FakeSyncClient
        sys.modules["fal_client"] = fake_pkg
        _FakeSyncClient.last = None
        self._urlopen_patch = mock.patch(
            "fal_common.urllib.request.urlopen",
            side_effect=_no_network,
        )
        self._urlopen_patch.start()
        self._download_patch = mock.patch(
            "fal_sam_3_1_image_helper.download",
            side_effect=_fake_download,
        )
        self._download_patch.start()

    def tearDown(self):
        self._download_patch.stop()
        self._urlopen_patch.stop()
        if self._prev_fal is None:
            sys.modules.pop("fal_client", None)
        else:
            sys.modules["fal_client"] = self._prev_fal

    def _write_png(self, folder):
        path = os.path.join(folder, "source.png")
        with open(path, "wb") as handle:
            handle.write(_PNG_BYTES)
        return path

    def test_primary_still_prefers_image_then_first_mask(self):
        url, name = helper._primary_still(
            {
                "image": {"url": "https://example.invalid/cutout.png", "file_name": "cutout.png"},
                "masks": [{"url": "https://example.invalid/mask.png"}],
            }
        )
        self.assertEqual(url, "https://example.invalid/cutout.png")
        self.assertEqual(name, "cutout.png")
        url, name = helper._primary_still(
            {"image": None, "masks": [{"url": "https://example.invalid/mask.png", "file_name": "mask.png"}]}
        )
        self.assertEqual(url, "https://example.invalid/mask.png")
        self.assertEqual(name, "mask.png")

    def test_empty_sam_result_is_not_unexpected_shape(self):
        self.assertTrue(helper._is_empty_sam_result(_EMPTY_RESULT))
        self.assertIsNone(helper._primary_still(_EMPTY_RESULT)[0])
        self.assertFalse(
            helper._is_empty_sam_result({"image": {"url": "https://example.invalid/a.png"}, "masks": []})
        )
        self.assertFalse(helper._is_empty_sam_result({"unexpected": True}))

    def test_placeholder_prompt_is_rejected(self):
        self.assertTrue(
            helper._looks_like_placeholder_prompt(
                "Describe the object to segment (e.g. the red car)"
            )
        )
        self.assertFalse(helper._looks_like_placeholder_prompt("person"))
        self.assertFalse(helper._looks_like_placeholder_prompt("the red car"))

    def test_placeholder_prompt_exits_2_without_upload(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                rc = helper.main(
                    [
                        "--image",
                        image_path,
                        "--prompt",
                        "Describe the object to segment (e.g. the red car)",
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("placeholder", stderr.getvalue().lower())

    def test_empty_result_exits_4_with_no_match_message(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_sam_3_1_image_helper.subscribe_with_retry",
                    return_value=_EMPTY_RESULT,
                ):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--prompt",
                            "a glowing neon bicycle that is not in the plate",
                            "--out-dir",
                            td,
                            "--fal-key",
                            "test-key",
                        ]
                    )
        self.assertEqual(rc, 4)
        text = stderr.getvalue()
        self.assertIn("found no objects matching prompt", text)
        self.assertNotIn("unexpected response shape", text)
        self.assertIsNotNone(_FakeSyncClient.last)
        self.assertEqual(len(_FakeSyncClient.last.uploaded), 1)

    def test_unexpected_shape_still_dumps_json(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_sam_3_1_image_helper.subscribe_with_retry",
                    return_value={"detail": "wat"},
                ):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--prompt",
                            "person",
                            "--out-dir",
                            td,
                            "--fal-key",
                            "test-key",
                        ]
                    )
        self.assertEqual(rc, 4)
        self.assertIn("unexpected response shape", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
