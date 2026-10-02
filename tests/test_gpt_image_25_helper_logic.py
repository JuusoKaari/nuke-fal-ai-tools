# Purpose: No-network tests for the GPT Image 2.5 helper (t2i vs edit, mask, 16-image cap).
# Run: py -3 -m unittest tests.test_gpt_image_25_helper_logic

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

import fal_gpt_image_25_helper as helper


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_FAKE_RESULT = {
    "images": [{"url": "https://example.invalid/out.png"}],
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
        name = os.path.basename(path).replace("\\", "/")
        return "https://example.invalid/%s" % name


class TestGptImage25HelperLogic(unittest.TestCase):
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
            "fal_gpt_image_25_helper.download",
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

    def _write_png(self, folder, name="source.png"):
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(_PNG_BYTES)
        return path

    def test_flare_text_to_image_default_size(self):
        with tempfile.TemporaryDirectory() as td:
            captured = {}

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, kwargs
                captured["endpoint"] = endpoint
                captured["arguments"] = arguments
                return _FAKE_RESULT

            with mock.patch(
                "fal_gpt_image_25_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--prompt",
                            "a cinematic landscape",
                            "--out-dir",
                            td,
                            "--fal-key",
                            "test-key",
                        ]
                    )

        self.assertEqual(rc, 0)
        self.assertEqual(
            captured["endpoint"],
            "openai/gpt-image-2.5/flare/text-to-image",
        )
        self.assertEqual(captured["arguments"]["image_size"], "landscape_4_3")
        self.assertNotIn("image_urls", captured["arguments"])
        self.assertNotIn("mask_url", captured["arguments"])
        self.assertEqual(captured["arguments"]["quality"], "high")
        self.assertEqual(captured["arguments"]["background"], "auto")
        self.assertIsNotNone(_FakeSyncClient.last)
        self.assertEqual(_FakeSyncClient.last.uploaded, [])

    def test_sunburst_edit_with_two_images_and_mask(self):
        with tempfile.TemporaryDirectory() as td:
            img_a = self._write_png(td, "a.png")
            img_b = self._write_png(td, "b.png")
            mask = self._write_png(td, "mask.png")
            captured = {}

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, kwargs
                captured["endpoint"] = endpoint
                captured["arguments"] = arguments
                return _FAKE_RESULT

            with mock.patch(
                "fal_gpt_image_25_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--prompt",
                            "add sunset lighting",
                            "--image",
                            img_a,
                            "--image",
                            img_b,
                            "--mask",
                            mask,
                            "--variant",
                            "sunburst",
                            "--image-size",
                            "square",
                            "--out-dir",
                            td,
                            "--fal-key",
                            "test-key",
                        ]
                    )

        self.assertEqual(rc, 0)
        self.assertEqual(
            captured["endpoint"],
            "openai/gpt-image-2.5/sunburst/edit",
        )
        self.assertEqual(captured["arguments"]["image_size"], "auto")
        self.assertEqual(
            captured["arguments"]["image_urls"],
            [
                "https://example.invalid/a.png",
                "https://example.invalid/b.png",
            ],
        )
        self.assertEqual(captured["arguments"]["mask_url"], "https://example.invalid/mask.png")
        self.assertEqual(len(_FakeSyncClient.last.uploaded), 3)

    def test_seventeenth_image_is_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            paths = [self._write_png(td, "img_%02d.png" % i) for i in range(17)]
            args = ["--prompt", "edit", "--out-dir", td, "--fal-key", "test-key"]
            for path in paths:
                args += ["--image", path]
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_gpt_image_25_helper.subscribe_with_retry",
                    side_effect=AssertionError("should not subscribe"),
                ):
                    rc = helper.main(args)
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("16", stderr.getvalue())
        self.assertIn("17", stderr.getvalue())

    def test_mask_without_image_is_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            mask = self._write_png(td, "mask.png")
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                rc = helper.main(
                    [
                        "--prompt",
                        "generate",
                        "--mask",
                        mask,
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("mask", stderr.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
