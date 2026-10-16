# Purpose: No-network tests for the Marigold Normal helper (request body and download name).
# Run: py -3 -m unittest tests.test_marigold_normal_helper_logic

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

import fal_marigold_normal_helper as helper


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


class TestMarigoldNormalHelperLogic(unittest.TestCase):
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
            "fal_marigold_normal_helper.download",
            side_effect=_fake_download,
        )
        self._download_patch.start()
        self._captured = {}

        def _capture(_client, endpoint_id, arguments, **_kwargs):
            self._captured["endpoint"] = endpoint_id
            self._captured["arguments"] = arguments
            return {
                "image": {
                    "url": "https://example.invalid/normal.png",
                    "file_name": "normal.png",
                },
                "seed": 17,
            }

        self._subscribe_patch = mock.patch(
            "fal_marigold_normal_helper.subscribe_with_retry",
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

    def test_default_body_is_normals_without_seed_or_image_size(self):
        body = helper.build_arguments("https://example.invalid/in.png")
        self.assertEqual(
            body,
            {
                "image_url": "https://example.invalid/in.png",
                "prediction_type": "normals",
            },
        )
        self.assertNotIn("seed", body)
        self.assertNotIn("image_size", body)
        self.assertNotIn("enable_safety_checker", body)

    def test_seed_is_included_when_set(self):
        body = helper.build_arguments("https://example.invalid/in.png", 0)
        self.assertEqual(body["seed"], 0)
        self.assertEqual(body["prediction_type"], "normals")

    def test_execute_sends_normals_and_writes_normal_map(self):
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
                        "--seed",
                        "42",
                    ]
                )
            out_path = os.path.join(td, "normal_map.png")
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(out_path))
            summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(self._captured["endpoint"], "fal-ai/marigold-v2")
        self.assertEqual(
            self._captured["arguments"],
            {
                "image_url": "https://example.invalid/uploaded.png",
                "prediction_type": "normals",
                "seed": 42,
            },
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["prediction_type"], "normals")
        self.assertEqual(summary["seed"], 42)
        self.assertEqual(summary["response_seed"], 17)
        self.assertTrue(summary["downloaded"].endswith("normal_map.png"))


if __name__ == "__main__":
    unittest.main()
