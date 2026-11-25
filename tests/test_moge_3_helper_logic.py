# Purpose: No-network tests for the MoGe-3 helper (camera math, payload, OBJ convert).
# Run: py -3 -m unittest tests.test_moge_3_helper_logic

from __future__ import print_function

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

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import fal_moge_3_helper as helper
import test_glb_to_obj as glb_fixture


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00IEND\xaeB`\x82"
)


def _no_network(*_args, **_kwargs):
    raise AssertionError("network is forbidden in helper tests")


class _FakeSyncClient(object):
    last = None

    def __init__(self, key=None):
        self.key = key
        self.uploaded = []
        self.subscribe_calls = []
        _FakeSyncClient.last = self

    def upload_file(self, path):
        self.uploaded.append(path)
        return "https://example.invalid/uploaded.png"

    def subscribe(self, endpoint_id, arguments=None):
        self.subscribe_calls.append((endpoint_id, arguments))
        return {
            "model_mesh": {
                "url": "https://example.invalid/model.glb",
                "file_name": "model.glb",
            },
            "depth_map": {"url": "https://example.invalid/depth.png"},
            "normal_map": {"url": "https://example.invalid/normal.png"},
            "mask": {"url": "https://example.invalid/mask.png"},
            "point_cloud": {"url": "https://example.invalid/cloud.ply"},
            "fov_x": 90.0,
            "fov_y": 90.0,
            "intrinsics": [
                [1.0, 0.0, 0.6],
                [0.0, 1.0, 0.4],
                [0.0, 0.0, 1.0],
            ],
        }


def _fake_download(url, out_path, user_agent, timeout_seconds=60):
    del user_agent, timeout_seconds
    if not str(url).endswith(".glb"):
        raise AssertionError("helper downloaded a non-mesh file: %s" % url)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(glb_fixture._triangle_glb())


class TestMoge3HelperLogic(unittest.TestCase):
    def setUp(self):
        self._prev_fal = sys.modules.get("fal_client")
        self._prev_fal_client = sys.modules.get("fal_client.client")
        fake_pkg = types.ModuleType("fal_client")
        fake_pkg.SyncClient = _FakeSyncClient
        fake_client = types.ModuleType("fal_client.client")

        class FalClientHTTPError(Exception):
            pass

        fake_client.FalClientHTTPError = FalClientHTTPError
        sys.modules["fal_client"] = fake_pkg
        sys.modules["fal_client.client"] = fake_client
        _FakeSyncClient.last = None
        self._urlopen_patch = mock.patch(
            "fal_common.urllib.request.urlopen",
            side_effect=_no_network,
        )
        self._urlopen_patch.start()
        self._download_patch = mock.patch(
            "fal_moge_3_helper.download",
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
        if self._prev_fal_client is None:
            sys.modules.pop("fal_client.client", None)
        else:
            sys.modules["fal_client.client"] = self._prev_fal_client

    def test_camera_matches_nuke_film_back(self):
        camera = helper.nuke_camera_from_fov(
            90.0,
            90.0,
            [[1.0, 0.0, 0.6], [0.0, 1.0, 0.4], [0.0, 0.0, 1.0]],
        )
        self.assertAlmostEqual(camera["haperture"], 24.576)
        self.assertAlmostEqual(camera["focal"], 12.288)
        self.assertAlmostEqual(camera["vaperture"], 24.576)
        self.assertAlmostEqual(camera["win_translate"][0], -0.2)
        self.assertAlmostEqual(camera["win_translate"][1], -0.2)
        self.assertAlmostEqual(camera["near"], 0.001)

    def test_centered_principal_point_has_no_window_shift(self):
        camera = helper.nuke_camera_from_fov(
            60.0,
            40.0,
            [[0.8, 0.0, 0.5], [0.0, 0.8, 0.5], [0.0, 0.0, 1.0]],
        )
        self.assertEqual(camera["win_translate"], [0.0, 0.0])
        self.assertGreater(camera["focal"], camera["haperture"] / 2.0)

    def test_pixel_intrinsics_do_not_shift_the_window(self):
        camera = helper.nuke_camera_from_fov(
            50.0,
            40.0,
            [[1200.0, 0.0, 960.0], [0.0, 1200.0, 540.0], [0.0, 0.0, 1.0]],
        )
        self.assertEqual(camera["win_translate"], [0.0, 0.0])

    def test_payload_skips_point_cloud_and_optional_fov(self):
        args = helper.build_arguments("https://example.invalid/a.png", 9, 3, 0.04, True, None)
        self.assertEqual(args["export_glb"], True)
        self.assertEqual(args["export_ply"], False)
        self.assertNotIn("fov_x", args)
        with_fov = helper.build_arguments("https://example.invalid/a.png", 4, 0, 0.04, False, 48.5)
        self.assertEqual(with_fov["fov_x"], 48.5)
        self.assertEqual(with_fov["resolution_level"], 4)
        self.assertEqual(with_fov["apply_mask"], False)
        self.assertIsNone(helper.validate_settings(9, 3, 0.04, None))
        self.assertIsNotNone(helper.validate_settings(10, 3, 0.04, None))
        self.assertIsNotNone(helper.validate_settings(9, 3, 0.04, 180.0))

    def test_main_writes_obj_and_camera_without_depth(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = os.path.join(td, "plate.png")
            with open(image_path, "wb") as handle:
                handle.write(_PNG_BYTES)
            out_dir = os.path.join(td, "out")
            code = helper.main(
                ["--fal-key", "test-key", "--image", image_path, "--out-dir", out_dir, "--fov-x", "48"]
            )
            self.assertEqual(code, 0)
            client = _FakeSyncClient.last
            self.assertEqual(client.subscribe_calls[0][0], "microsoft/moge-3")
            sent = client.subscribe_calls[0][1]
            self.assertEqual(sent["export_ply"], False)
            self.assertEqual(sent["fov_x"], 48.0)
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "model.obj")))
            self.assertFalse(os.path.isfile(os.path.join(out_dir, "depth.png")))
            self.assertFalse(os.path.isfile(os.path.join(out_dir, "cloud.ply")))


if __name__ == "__main__":
    unittest.main()
