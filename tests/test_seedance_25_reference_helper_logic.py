# Purpose: No-network tests for the Seedance 2.5 reference-to-video helper and Group knobs.
# Run: py -3 -m unittest tests.test_seedance_25_reference_helper_logic

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
_GROUP_DIR = os.path.join(_ROOT, "nuke", "groups")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import fal_seedance_25_reference_to_video_helper as helper


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_FAKE_RESULT = {
    "video": {"url": "https://example.invalid/out.mp4"},
}


def _no_network(*_args, **_kwargs):
    raise AssertionError("network is forbidden in helper tests")


def _fake_download(url, out_path, user_agent, timeout_seconds=60):
    del url, user_agent, timeout_seconds
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(b"fake-mp4")


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


class TestSeedance25ReferenceHelperLogic(unittest.TestCase):
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
            "fal_seedance_25_reference_to_video_helper.download",
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

    def test_editing_subscribe_posts_task_duration_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td, "char.png")
            out_path = os.path.join(td, "out.mp4")
            captured = {}

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, kwargs
                captured["endpoint"] = endpoint
                captured["arguments"] = arguments
                return _FAKE_RESULT

            with mock.patch(
                "fal_seedance_25_reference_to_video_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--prompt",
                            "@Image1 walks",
                            "--out",
                            out_path,
                            "--task",
                            "editing",
                            "--duration",
                            "30",
                            "--resolution",
                            "1080p",
                            "--fal-key",
                            "test-key",
                        ]
                    )

        self.assertEqual(rc, 0)
        self.assertEqual(
            captured["endpoint"],
            "bytedance/seedance-2.5/reference-to-video",
        )
        self.assertEqual(captured["arguments"]["task"], "editing")
        self.assertEqual(captured["arguments"]["duration"], "30")
        self.assertEqual(captured["arguments"]["resolution"], "1080p")
        self.assertEqual(
            captured["arguments"]["image_urls"],
            ["https://example.invalid/char.png"],
        )
        self.assertTrue(captured["arguments"]["generate_audio"])
        self.assertFalse(captured["arguments"]["draft"])
        self.assertEqual(captured["arguments"]["codec"], "auto")
        self.assertNotIn("4k", captured["arguments"]["resolution"])
        self.assertIsNotNone(_FakeSyncClient.last)
        self.assertEqual(len(_FakeSyncClient.last.uploaded), 1)

    def test_thirty_first_image_is_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            paths = [self._write_png(td, "img_%02d.png" % i) for i in range(31)]
            args = [
                "--prompt",
                "@Image1 walks",
                "--out",
                os.path.join(td, "out.mp4"),
                "--fal-key",
                "test-key",
            ]
            for path in paths:
                args += ["--image", path]
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_seedance_25_reference_to_video_helper.subscribe_with_retry",
                    side_effect=AssertionError("should not subscribe"),
                ):
                    rc = helper.main(args)
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("30", stderr.getvalue())
        self.assertIn("31", stderr.getvalue())

    def test_draft_id_is_printed_in_result_summary(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td, "char.png")
            out_path = os.path.join(td, "out.mp4")
            stdout = io.StringIO()

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, endpoint, kwargs
                self.assertTrue(arguments["draft"])
                return {
                    "video": {"url": "https://example.invalid/out.mp4"},
                    "draft_id": "draft-abc123",
                }

            with mock.patch(
                "fal_seedance_25_reference_to_video_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", stdout):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--prompt",
                            "@Image1 walks",
                            "--out",
                            out_path,
                            "--draft",
                            "--fal-key",
                            "test-key",
                        ]
                    )

        self.assertEqual(rc, 0)
        self.assertIn("draft-abc123", stdout.getvalue())
        self.assertIn("draft_id", stdout.getvalue())

    def test_nk_duration_includes_30_and_resolution_has_no_4k(self):
        path = os.path.join(_GROUP_DIR, "fal_seedance_25_reference_to_video_v1.nk")
        with open(path, "r") as handle:
            text = handle.read()
        self.assertIn(
            "addUserKnob {4 duration l Duration M {auto 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 \"\"}}",
            text,
        )
        self.assertIn(
            "addUserKnob {4 resolution l Resolution M {480p 720p 1080p \"\"}}",
            text,
        )
        self.assertNotIn("4k", text)
        self.assertIn("9 stills, 3 videos, and 3 audio paths", text)
        self.assertIn("@Image1", text)
        self.assertIn("@Video1", text)
        self.assertIn("@Audio1", text)
        self.assertIn("addUserKnob {4 codec l Codec M {auto H264 H265 \"\"}}", text)
        self.assertNotIn("draft-complete", text)
        self.assertNotIn("reference-to-video/draft", text)


if __name__ == "__main__":
    unittest.main()
