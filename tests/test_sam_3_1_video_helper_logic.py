# Purpose: No-network tests for the SAM 3.1 Video helper (subscribe payload, empty prompt).
# Run: py -3 -m unittest tests.test_sam_3_1_video_helper_logic

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

import fal_sam_3_1_video_helper as helper
import nuke_group_output_preview_config_v1 as preview_cfg


_FAKE_RESULT = {
    "video": {"url": "https://example.invalid/out.mp4", "file_name": "out.mp4"},
    "boundingbox_frames_zip": {"url": "https://example.invalid/boxes.zip"},
}


def _no_network(*_args, **_kwargs):
    raise AssertionError("network is forbidden in helper tests")


def _fake_download(url, out_path, user_agent, timeout_seconds=60):
    del user_agent, timeout_seconds
    if "boxes.zip" in str(url):
        raise AssertionError("boundingbox_frames_zip must not be downloaded")
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
        return "https://example.invalid/uploaded.mp4"


class TestSAM31VideoHelperLogic(unittest.TestCase):
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
            "fal_sam_3_1_video_helper.download",
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

    def _write_mp4(self, folder):
        path = os.path.join(folder, "source.mp4")
        with open(path, "wb") as handle:
            handle.write(b"fake-source-mp4")
        return path

    def test_subscribe_posts_prompt_mask_threshold_and_max_objects(self):
        with tempfile.TemporaryDirectory() as td:
            video_path = self._write_mp4(td)
            out_path = os.path.join(td, "out.mp4")
            captured = {}

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, kwargs
                captured["endpoint"] = endpoint
                captured["arguments"] = arguments
                return _FAKE_RESULT

            with mock.patch(
                "fal_sam_3_1_video_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--video",
                            video_path,
                            "--prompt",
                            "person, cloth",
                            "--out",
                            out_path,
                            "--fal-key",
                            "test-key",
                        ]
                    )
            self.assertTrue(os.path.isfile(out_path))

        self.assertEqual(rc, 0)
        self.assertEqual(captured["endpoint"], "fal-ai/sam-3-1/video")
        args = captured["arguments"]
        self.assertEqual(args["prompt"], "person, cloth")
        self.assertTrue(args["apply_mask"])
        self.assertEqual(args["detection_threshold"], 0.5)
        self.assertEqual(args["max_num_objects"], 16)
        self.assertEqual(args["output_type"], "X264 (.mp4)")
        self.assertEqual(args["video_url"], "https://example.invalid/uploaded.mp4")
        self.assertNotIn("box_prompts", args)
        self.assertNotIn("point_prompts", args)
        self.assertIsNotNone(_FakeSyncClient.last)
        self.assertEqual(len(_FakeSyncClient.last.uploaded), 1)

    def test_empty_prompt_fails_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            video_path = self._write_mp4(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_sam_3_1_video_helper.subscribe_with_retry",
                    side_effect=AssertionError("should not subscribe"),
                ):
                    rc = helper.main(
                        [
                            "--video",
                            video_path,
                            "--prompt",
                            "   ",
                            "--out",
                            os.path.join(td, "out.mp4"),
                            "--fal-key",
                            "test-key",
                        ]
                    )
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("empty", stderr.getvalue().lower())

    def test_build_arguments_clamps_threshold_and_max_objects(self):
        payload = helper.build_arguments(
            "https://example.invalid/in.mp4",
            "person",
            True,
            1.7,
            0,
            "VP9 (.webm)",
        )
        self.assertEqual(payload["detection_threshold"], 1.0)
        self.assertEqual(payload["max_num_objects"], 1)
        self.assertEqual(payload["output_type"], "VP9 (.webm)")
        self.assertNotIn("box_prompts", payload)
        self.assertNotIn("point_prompts", payload)
        with self.assertRaises(ValueError):
            helper.build_arguments(
                "https://example.invalid/in.mp4",
                "   ",
                True,
                0.5,
                16,
                "X264 (.mp4)",
            )

    def test_nk_defaults_and_preview_config_has_no_sam_video(self):
        path = os.path.join(_GROUP_DIR, "fal_sam_3_1_video_v1.nk")
        with open(path, "r") as handle:
            text = handle.read()
        self.assertIn('prompt "person"', text)
        self.assertIn("apply_mask true", text)
        self.assertIn("detection_threshold 0.5", text)
        self.assertIn("max_objects 16", text)
        self.assertIn("X264 (.mp4)", text)
        self.assertIn("VP9 (.webm)", text)
        self.assertIn("name source_video", text)
        self.assertNotIn("box_prompts", text)
        self.assertNotIn("point_prompts", text)
        self.assertNotIn("fal_tool_id", text)
        self.assertNotIn("viewer_mode_switch", text)
        self.assertNotIn("SAM_3_1_Video_v1", preview_cfg.TOOL_PREVIEW_CONFIG)
        self.assertNotIn(
            "fal_sam_3_1_video_runner_v1.py",
            preview_cfg.RUNNER_BASENAME_TO_TOOL_ID,
        )


if __name__ == "__main__":
    unittest.main()
