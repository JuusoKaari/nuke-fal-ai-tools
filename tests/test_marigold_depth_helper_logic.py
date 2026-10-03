# Purpose: No-network tests for the Marigold Depth helper (ranges and request body).
# Run: py -3 -m unittest tests.test_marigold_depth_helper_logic

from __future__ import print_function

import io
import json
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

import fal_marigold_depth_helper as helper


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


class TestMarigoldDepthHelperLogic(unittest.TestCase):
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
            "fal_marigold_depth_helper.download",
            side_effect=_fake_download,
        )
        self._download_patch.start()
        self._captured = {}

        def _capture(_client, endpoint_id, arguments, **_kwargs):
            self._captured["endpoint"] = endpoint_id
            self._captured["arguments"] = arguments
            return {
                "image": {
                    "url": "https://example.invalid/depth.png",
                    "file_name": "depth.png",
                }
            }

        self._subscribe_patch = mock.patch(
            "fal_marigold_depth_helper.subscribe_with_retry",
            side_effect=_capture,
        )
        self._subscribe_patch.start()

    def tearDown(self):
        self._subscribe_patch.stop()
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

    def test_defaults_include_processing_res_zero(self):
        body = helper.build_arguments("https://example.invalid/in.png", 10, 10, 0)
        self.assertEqual(
            body,
            {
                "image_url": "https://example.invalid/in.png",
                "num_inference_steps": 10,
                "ensemble_size": 10,
                "processing_res": 0,
            },
        )
        self.assertIsNone(helper.validate_settings(10, 10, 0))
        self.assertIsNone(helper.validate_settings(2, 50, 2048))

    def test_out_of_range_is_rejected_before_upload(self):
        self.assertIn("--num-inference-steps", helper.validate_settings(1, 10, 0))
        self.assertIn("--ensemble-size", helper.validate_settings(10, 51, 0))
        self.assertIn("--processing-res", helper.validate_settings(10, 10, 2049))
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                rc = helper.main(
                    [
                        "--image",
                        image_path,
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                        "--num-inference-steps",
                        "1",
                    ]
                )
        self.assertEqual(rc, 2)
        self.assertIn("--num-inference-steps", stderr.getvalue())
        self.assertIsNone(_FakeSyncClient.last)
        self.assertEqual(self._captured, {})

    def test_execute_sends_knobs_and_writes_depth_map(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                rc = helper.main(
                    [
                        "--image",
                        image_path,
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                        "--num-inference-steps",
                        "12",
                        "--ensemble-size",
                        "4",
                        "--processing-res",
                        "768",
                    ]
                )
            out_path = os.path.join(td, "depth_map.png")
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(out_path))
            summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(self._captured["endpoint"], "fal-ai/imageutils/marigold-depth")
        self.assertEqual(
            self._captured["arguments"],
            {
                "image_url": "https://example.invalid/uploaded.png",
                "num_inference_steps": 12,
                "ensemble_size": 4,
                "processing_res": 768,
            },
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["num_inference_steps"], 12)
        self.assertEqual(summary["ensemble_size"], 4)
        self.assertEqual(summary["processing_res"], 768)
        self.assertTrue(summary["downloaded"].endswith("depth_map.png"))


if __name__ == "__main__":
    unittest.main()
