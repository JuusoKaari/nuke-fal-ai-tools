# Purpose: No-network tests for LTX 2.5 Alpha Gen request payloads and downloads.
# Run: py -3 -m unittest tests.test_ltx_25_alpha_gen_helper_logic

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

import fal_ltx_25_alpha_gen_helper as helper


_FAKE_RESULT = {
    "matte_video": {
        "url": "https://example.invalid/matte.mp4",
        "content_type": "video/mp4",
        "file_name": "matte.mp4",
    },
    "cutout_video": {
        "url": "https://example.invalid/cutout.mov",
        "content_type": "video/quicktime",
        "file_name": "cutout.mov",
    },
}


def _no_network(*_args, **_kwargs):
    raise AssertionError("network is forbidden in helper tests")


_DOWNLOADED = []


def _fake_download(url, out_path, user_agent, timeout_seconds=60):
    del user_agent, timeout_seconds
    _DOWNLOADED.append(str(url))
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = b"fake-mov" if "cutout" in str(url) else b"fake-mp4"
    with open(out_path, "wb") as handle:
        handle.write(payload)


class _FakeSyncClient(object):
    last = None

    def __init__(self, key=None):
        self.key = key
        self.uploaded = []
        _FakeSyncClient.last = self

    def upload_file(self, path):
        self.uploaded.append(path)
        return "https://example.invalid/uploaded.mp4"


class TestLTX25AlphaGenPayload(unittest.TestCase):
    def test_payload_sends_video_url_and_safety_checker(self):
        payload = helper.build_arguments("https://example.invalid/in.mp4", True)
        self.assertEqual(
            payload,
            {
                "video_url": "https://example.invalid/in.mp4",
                "enable_safety_checker": True,
            },
        )

    def test_safety_checker_off_is_sent(self):
        payload = helper.build_arguments("https://example.invalid/in.mp4", False)
        self.assertFalse(payload["enable_safety_checker"])

    def test_blank_video_url_is_rejected(self):
        with self.assertRaises(ValueError):
            helper.build_arguments("   ", True)

    def test_output_mode_defaults_to_alpha_and_is_not_an_api_field(self):
        self.assertEqual(helper.normalize_output_mode(""), "alpha")
        self.assertEqual(helper.normalize_output_mode("Alpha only"), "alpha")
        self.assertEqual(helper.normalize_output_mode("RGBA"), "rgba")
        self.assertEqual(helper.result_key_for_mode("alpha"), "matte_video")
        self.assertEqual(helper.result_key_for_mode("rgba"), "cutout_video")
        self.assertEqual(helper.expected_ext_for_mode("alpha"), "mp4")
        self.assertEqual(helper.expected_ext_for_mode("rgba"), "mov")
        payload = helper.build_arguments("https://example.invalid/in.mp4", True)
        self.assertNotIn("output_mode", payload)
        with self.assertRaises(ValueError):
            helper.normalize_output_mode("both")


class TestLTX25AlphaGenHelper(unittest.TestCase):
    def setUp(self):
        self._prev_fal = sys.modules.get("fal_client")
        fake_pkg = types.ModuleType("fal_client")
        fake_pkg.SyncClient = _FakeSyncClient
        sys.modules["fal_client"] = fake_pkg
        _FakeSyncClient.last = None
        del _DOWNLOADED[:]
        self._urlopen_patch = mock.patch(
            "fal_common.urllib.request.urlopen",
            side_effect=_no_network,
        )
        self._urlopen_patch.start()
        self._download_patch = mock.patch(
            "fal_ltx_25_alpha_gen_helper.download",
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

    def _write_video(self, folder, name):
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(b"fake-source")
        return path

    def test_default_mode_downloads_only_the_matte(self):
        with tempfile.TemporaryDirectory() as td:
            video_path = self._write_video(td, "source.mp4")
            out_path = os.path.join(td, "alpha.mp4")
            captured = {}

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, kwargs
                captured["endpoint"] = endpoint
                captured["arguments"] = arguments
                return _FAKE_RESULT

            with mock.patch(
                "fal_ltx_25_alpha_gen_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--video",
                            video_path,
                            "--out",
                            out_path,
                            "--no-enable-safety-checker",
                            "--fal-key",
                            "test-key",
                        ]
                    )
            self.assertEqual(rc, 0)
            with open(out_path, "rb") as handle:
                self.assertEqual(handle.read(), b"fake-mp4")

        self.assertEqual(captured["endpoint"], "lightricks/ltx-2.5/alpha-gen")
        self.assertEqual(
            captured["arguments"],
            {
                "video_url": "https://example.invalid/uploaded.mp4",
                "enable_safety_checker": False,
            },
        )
        self.assertNotIn("output_mode", captured["arguments"])
        self.assertEqual(_DOWNLOADED, ["https://example.invalid/matte.mp4"])
        self.assertEqual(len(_FakeSyncClient.last.uploaded), 1)

    def test_rgba_mode_downloads_only_the_cutout(self):
        with tempfile.TemporaryDirectory() as td:
            video_path = self._write_video(td, "source.mp4")
            out_path = os.path.join(td, "cutout.mov")
            with mock.patch(
                "fal_ltx_25_alpha_gen_helper.subscribe_with_retry",
                return_value=_FAKE_RESULT,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--video",
                            video_path,
                            "--output-mode",
                            "rgba",
                            "--out",
                            out_path,
                            "--fal-key",
                            "test-key",
                        ]
                    )
            self.assertEqual(rc, 0)
            with open(out_path, "rb") as handle:
                self.assertEqual(handle.read(), b"fake-mov")
        self.assertEqual(_DOWNLOADED, ["https://example.invalid/cutout.mov"])

    def test_rgba_fails_when_the_cutout_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            video_path = self._write_video(td, "source.mov")
            out_path = os.path.join(td, "cutout.mov")
            stderr = io.StringIO()

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, endpoint, arguments, kwargs
                return {"matte_video": {"url": "https://example.invalid/matte.mp4"}}

            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_ltx_25_alpha_gen_helper.subscribe_with_retry",
                    side_effect=_subscribe,
                ):
                    rc = helper.main(
                        [
                            "--video",
                            video_path,
                            "--output-mode",
                            "rgba",
                            "--out",
                            out_path,
                            "--fal-key",
                            "test-key",
                        ]
                    )
            self.assertFalse(os.path.isfile(out_path))
        self.assertEqual(rc, 4)
        self.assertEqual(_DOWNLOADED, [])
        self.assertIn("unexpected response", stderr.getvalue().lower())

    def test_wrong_output_extension_fails_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            video_path = self._write_video(td, "source.mp4")
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_ltx_25_alpha_gen_helper.subscribe_with_retry",
                    side_effect=AssertionError("should not subscribe"),
                ):
                    rc = helper.main(
                        [
                            "--video",
                            video_path,
                            "--out",
                            os.path.join(td, "alpha.mov"),
                            "--fal-key",
                            "test-key",
                        ]
                    )
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)
        self.assertIn("mp4", stderr.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
