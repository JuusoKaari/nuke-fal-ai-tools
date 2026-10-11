# Purpose: No-network tests for the Nano Banana 2.1 text-to-image helper.
# Run: py -3 -m unittest tests.test_nano_banana_21_helper_logic

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

import fal_nano_banana_21_helper as helper


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


class TestNanoBanana21HelperLogic(unittest.TestCase):
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
            "fal_nano_banana_21_helper.download",
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

    def _run(self, args, result=None):
        if result is None:
            result = {
                "images": [{"url": "https://example.invalid/out.png"}],
                "description": "a generated still",
            }
        captured = {}
        stdout = io.StringIO()

        def _subscribe(client, endpoint, arguments, **kwargs):
            del client, kwargs
            captured["endpoint"] = endpoint
            captured["arguments"] = arguments
            return result

        with mock.patch(
            "fal_nano_banana_21_helper.subscribe_with_retry",
            side_effect=_subscribe,
        ):
            with mock.patch("sys.stdout", stdout):
                rc = helper.main(args)
        return rc, captured, stdout.getvalue()

    def test_default_text_to_image_body(self):
        with tempfile.TemporaryDirectory() as td:
            rc, captured, stdout = self._run(
                [
                    "--prompt",
                    "a cinematic landscape",
                    "--out-dir",
                    td,
                    "--fal-key",
                    "test-key",
                ]
            )
            self.assertTrue(os.path.isfile(os.path.join(td, "image_001.png")))

        self.assertEqual(rc, 0)
        self.assertEqual(captured["endpoint"], "google/nano-banana-2.1")
        body = captured["arguments"]
        self.assertEqual(body["prompt"], "a cinematic landscape")
        self.assertEqual(body["num_images"], 1)
        self.assertEqual(body["aspect_ratio"], "auto")
        self.assertEqual(body["output_format"], "png")
        self.assertEqual(body["safety_tolerance"], "4")
        self.assertFalse(body["sync_mode"])
        self.assertEqual(body["resolution"], "1K")
        self.assertTrue(body["limit_generations"])
        self.assertFalse(body["enable_web_search"])
        self.assertEqual(body["thinking_level"], "medium")
        self.assertNotIn("system_prompt", body)
        self.assertNotIn("seed", body)
        self.assertNotIn("image_urls", body)
        self.assertEqual(_FakeSyncClient.last.uploaded, [])
        summary = json.loads(stdout.strip().splitlines()[-1])
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["description"], "a generated still")
        self.assertEqual(summary["endpoint"], "google/nano-banana-2.1")

    def test_custom_knobs_and_blank_system_prompt_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            rc, captured, _stdout = self._run(
                [
                    "--prompt",
                    "poster with the word OPEN",
                    "--out-dir",
                    td,
                    "--fal-key",
                    "test-key",
                    "--num-images",
                    "3",
                    "--aspect-ratio",
                    "8:1",
                    "--resolution",
                    "4K",
                    "--output-format",
                    "webp",
                    "--safety-tolerance",
                    "1",
                    "--thinking-level",
                    "high",
                    "--seed",
                    "17",
                    "--system-prompt",
                    "   ",
                    "--enable-web-search",
                ],
                result={
                    "images": [
                        {"url": "https://example.invalid/a.webp"},
                        {"url": "https://example.invalid/b.webp"},
                        {"url": "https://example.invalid/c.webp"},
                    ],
                    "description": "",
                },
            )
            self.assertTrue(os.path.isfile(os.path.join(td, "image_001.webp")))
            self.assertTrue(os.path.isfile(os.path.join(td, "image_002.webp")))
            self.assertTrue(os.path.isfile(os.path.join(td, "image_003.webp")))

        self.assertEqual(rc, 0)
        body = captured["arguments"]
        self.assertEqual(body["num_images"], 3)
        self.assertEqual(body["aspect_ratio"], "8:1")
        self.assertEqual(body["resolution"], "4K")
        self.assertEqual(body["output_format"], "webp")
        self.assertEqual(body["safety_tolerance"], "1")
        self.assertEqual(body["thinking_level"], "high")
        self.assertEqual(body["seed"], 17)
        self.assertTrue(body["enable_web_search"])
        self.assertNotIn("system_prompt", body)

    def test_system_prompt_is_sent_when_set(self):
        with tempfile.TemporaryDirectory() as td:
            rc, captured, _stdout = self._run(
                [
                    "--prompt",
                    "a red kettle",
                    "--system-prompt",
                    "Product photo, plain background.",
                    "--aspect-ratio",
                    "1:4",
                    "--out-dir",
                    td,
                    "--fal-key",
                    "test-key",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(
            captured["arguments"]["system_prompt"],
            "Product photo, plain background.",
        )
        self.assertEqual(captured["arguments"]["aspect_ratio"], "1:4")

    def test_num_images_out_of_range(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("sys.stderr", io.StringIO()):
                rc = helper.main(
                    [
                        "--prompt",
                        "a cup",
                        "--num-images",
                        "5",
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 2)

    def test_empty_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("sys.stderr", io.StringIO()):
                rc = helper.main(
                    [
                        "--prompt",
                        "   ",
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 2)

    def test_missing_key(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("sys.stderr", io.StringIO()):
                    rc = helper.main(
                        [
                            "--prompt",
                            "a cup",
                            "--out-dir",
                            td,
                        ]
                    )
        self.assertEqual(rc, 2)

    def test_edit_uploads_images_and_uses_edit_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            img_a = os.path.join(td, "a.png")
            img_b = os.path.join(td, "b.png")
            with open(img_a, "wb") as handle:
                handle.write(_PNG_BYTES)
            with open(img_b, "wb") as handle:
                handle.write(_PNG_BYTES)
            rc, captured, _stdout = self._run(
                [
                    "--prompt",
                    "make the kettle red",
                    "--image",
                    img_a,
                    "--image",
                    img_b,
                    "--out-dir",
                    td,
                    "--fal-key",
                    "test-key",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(captured["endpoint"], "google/nano-banana-2.1/edit")
        self.assertEqual(
            captured["arguments"]["image_urls"],
            [
                "https://example.invalid/uploaded.png",
                "https://example.invalid/uploaded.png",
            ],
        )
        self.assertNotIn("video_url", captured["arguments"])
        self.assertNotIn("pdf_url", captured["arguments"])
        self.assertEqual(_FakeSyncClient.last.uploaded, [img_a, img_b])

    def test_missing_reference_image(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("sys.stderr", io.StringIO()):
                rc = helper.main(
                    [
                        "--prompt",
                        "a cup",
                        "--image",
                        os.path.join(td, "missing.png"),
                        "--out-dir",
                        td,
                        "--fal-key",
                        "test-key",
                    ]
                )
        self.assertEqual(rc, 2)
