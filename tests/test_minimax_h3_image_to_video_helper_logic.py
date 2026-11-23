# Purpose: No-network tests for MiniMax H3 image-to-video prompt expansion mode.
# Run: py -3 -m unittest tests.test_minimax_h3_image_to_video_helper_logic

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

import fal_minimax_h3_image_to_video_helper as helper
import fal_minimax_h3_image_to_video_runner_v1 as runner


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
    def __init__(self, key=None):
        self.key = key

    def upload_file(self, path):
        del path
        return "https://example.invalid/uploaded.png"


class TestPromptExpansionMode(unittest.TestCase):
    def test_explicit_mode_wins_over_legacy_checkbox(self):
        self.assertEqual(helper.resolve_prompt_expansion_mode("fast", True), "fast")
        self.assertEqual(helper.resolve_prompt_expansion_mode("disabled", True), "disabled")
        self.assertEqual(helper.resolve_prompt_expansion_mode("quality", False), "quality")

    def test_legacy_checkbox_maps_true_to_balanced_and_false_to_disabled(self):
        self.assertEqual(helper.resolve_prompt_expansion_mode(None, True), "balanced")
        self.assertEqual(helper.resolve_prompt_expansion_mode(None, False), "disabled")
        self.assertEqual(helper.resolve_prompt_expansion_mode(None, None), "balanced")

    def test_runner_knob_mapping_matches_helper(self):
        self.assertEqual(runner.prompt_expansion_mode_from_knobs("fast", False), "fast")
        self.assertEqual(runner.prompt_expansion_mode_from_knobs(None, True), "balanced")
        self.assertEqual(runner.prompt_expansion_mode_from_knobs(None, False), "disabled")
        self.assertEqual(runner.prompt_expansion_mode_from_knobs(None, None), "balanced")
        self.assertEqual(runner.prompt_expansion_mode_from_knobs(1, True), "fast")
        self.assertEqual(runner.prompt_expansion_mode_from_knobs("", None), "balanced")

    def test_nk_uses_enum_including_fast(self):
        path = os.path.join(_GROUP_DIR, "fal_minimax_h3_image_to_video_v1.nk")
        with open(path, "r") as handle:
            text = handle.read()
        self.assertIn("prompt_expansion_mode balanced", text)
        self.assertIn("disabled fast balanced quality", text)
        self.assertNotIn("enable_prompt_expansion", text)


class TestMiniMaxH3HelperPayload(unittest.TestCase):
    def setUp(self):
        self._prev_fal = sys.modules.get("fal_client")
        fake_pkg = types.ModuleType("fal_client")
        fake_pkg.SyncClient = _FakeSyncClient
        sys.modules["fal_client"] = fake_pkg
        self._urlopen_patch = mock.patch(
            "fal_common.urllib.request.urlopen",
            side_effect=_no_network,
        )
        self._urlopen_patch.start()
        self._download_patch = mock.patch(
            "fal_minimax_h3_image_to_video_helper.download",
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

    def _run(self, extra):
        captured = {}

        def _subscribe(client, endpoint, arguments, **kwargs):
            del client, kwargs
            captured["endpoint"] = endpoint
            captured["arguments"] = arguments
            return {"video": {"url": "https://example.invalid/out.mp4"}}

        with tempfile.TemporaryDirectory() as td:
            image_path = os.path.join(td, "start.png")
            with open(image_path, "wb") as handle:
                handle.write(b"png")
            out_path = os.path.join(td, "out.mp4")
            with mock.patch(
                "fal_minimax_h3_image_to_video_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--prompt",
                            "a slow push in",
                            "--out",
                            out_path,
                            "--fal-key",
                            "test-key",
                        ]
                        + extra
                    )
        self.assertEqual(rc, 0)
        return captured

    def test_default_payload_is_balanced_and_omits_legacy_field(self):
        captured = self._run([])
        args = captured["arguments"]
        self.assertEqual(captured["endpoint"], "minimax/h3/image-to-video")
        self.assertEqual(args["prompt_expansion_mode"], "balanced")
        self.assertNotIn("enable_prompt_expansion", args)

    def test_legacy_off_flag_sends_disabled(self):
        captured = self._run(["--no-enable-prompt-expansion"])
        args = captured["arguments"]
        self.assertEqual(args["prompt_expansion_mode"], "disabled")
        self.assertNotIn("enable_prompt_expansion", args)

    def test_explicit_fast_wins_over_legacy_on(self):
        captured = self._run(
            ["--prompt-expansion-mode", "fast", "--enable-prompt-expansion"]
        )
        self.assertEqual(captured["arguments"]["prompt_expansion_mode"], "fast")


if __name__ == "__main__":
    unittest.main()
