# Purpose: No-network tests for the Qwen Image Max Edit helper endpoint and payload.
# Run: py -3 -m unittest tests.test_qwen_image_max_edit_helper_logic

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

import fal_qwen_image_max_edit_helper as helper


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


class TestQwenImageMaxEditHelperLogic(unittest.TestCase):
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
            "fal_qwen_image_max_edit_helper.download",
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

    def test_endpoint_is_qwen_image_3_edit(self):
        self.assertEqual(helper._ENDPOINT_ID, "alibaba/qwen-image-3/edit")
        self.assertNotIn("qwen-image-max", helper._ENDPOINT_ID)

    def test_subscribe_sends_image_3_payload(self):
        captured = {}

        def _subscribe(client, endpoint, arguments, **kwargs):
            del client, kwargs
            captured["endpoint"] = endpoint
            captured["arguments"] = arguments
            return {
                "images": [{"url": "https://example.invalid/out.png"}],
                "seed": 7,
            }

        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                with mock.patch(
                    "fal_qwen_image_max_edit_helper.subscribe_with_retry",
                    side_effect=_subscribe,
                ):
                    rc = helper.main(
                    [
                        "--image",
                        image_path,
                        "--prompt",
                        "Make it sunset",
                        "--negative-prompt",
                        "blur",
                        "--out-dir",
                        td,
                        "--num-images",
                        "2",
                        "--output-format",
                        "png",
                        "--seed",
                        "11",
                        "--image-size",
                        "square_hd",
                        "--no-enable-prompt-expansion",
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 0)
        self.assertEqual(captured["endpoint"], "alibaba/qwen-image-3/edit")
        arguments = captured["arguments"]
        self.assertEqual(arguments["prompt"], "Make it sunset")
        self.assertEqual(arguments["negative_prompt"], "blur")
        self.assertEqual(arguments["image_urls"], ["https://example.invalid/uploaded.png"])
        self.assertEqual(arguments["num_images"], 2)
        self.assertEqual(arguments["output_format"], "png")
        self.assertEqual(arguments["seed"], 11)
        self.assertEqual(arguments["image_size"], "square_hd")
        self.assertFalse(arguments["enable_prompt_expansion"])
        self.assertTrue(arguments["enable_safety_checker"])
        self.assertNotIn("sync_mode", arguments)
        self.assertEqual(len(_FakeSyncClient.last.uploaded), 1)

    def test_empty_image_size_is_omitted(self):
        captured = {}

        def _subscribe(client, endpoint, arguments, **kwargs):
            del client, endpoint, kwargs
            captured["arguments"] = arguments
            return {"images": [{"url": "https://example.invalid/out.png"}], "seed": 1}

        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                with mock.patch(
                    "fal_qwen_image_max_edit_helper.subscribe_with_retry",
                    side_effect=_subscribe,
                ):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--prompt",
                            "Make it sunset",
                            "--out-dir",
                            td,
                            "--fal-key",
                            "test-key",
                        ]
                    )
        self.assertEqual(rc, 0)
        self.assertNotIn("image_size", captured["arguments"])
        self.assertNotIn("seed", captured["arguments"])

    def test_num_images_out_of_range_does_not_upload(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                rc = helper.main(
                    [
                        "--image",
                        image_path,
                        "--prompt",
                        "Make it sunset",
                        "--out-dir",
                        td,
                        "--num-images",
                        "7",
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("1..6", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
