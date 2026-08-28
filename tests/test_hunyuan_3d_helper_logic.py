# Purpose: No-network tests for the Hunyuan 3D image-to-3D helper CLI.
# Run: py -3 -m unittest tests.test_hunyuan_3d_helper_logic

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

import fal_hunyuan_3d_image_to_3d_helper as helper

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import test_glb_textures as glb_test


_PNG_BYTES = glb_test._PNG_BYTES
_ENDPOINT = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d"


def _no_network(*_args, **_kwargs):
    raise AssertionError("network is forbidden in helper tests")


def _pbr_glb_bytes():
    png = _PNG_BYTES
    jpeg = glb_test._JPEG_BYTES
    blob = jpeg + png
    views = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(jpeg)},
        {"buffer": 0, "byteOffset": len(jpeg), "byteLength": len(png)},
    ]
    return glb_test.pack_glb(glb_test._pbr_gltf(len(blob), views), blob)


_GLB_BYTES = _pbr_glb_bytes()


def _fake_download(url, out_path, user_agent, timeout_seconds=60):
    del user_agent, timeout_seconds
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = _GLB_BYTES if str(url).endswith(".glb") or str(out_path).endswith(".glb") else b"mesh-bytes"
    with open(out_path, "wb") as handle:
        handle.write(payload)


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
            "model_glb": {
                "url": "https://example.invalid/model.glb",
                "file_name": "model.glb",
            },
            "model_urls": {
                "texture": {
                    "url": "https://example.invalid/texture.png",
                    "file_name": "texture.png",
                },
                "mtl": {
                    "url": "https://example.invalid/material.mtl",
                    "file_name": "material.mtl",
                },
                "obj": {
                    "url": "https://example.invalid/model.obj",
                    "file_name": "model.obj",
                },
                "metallic": {
                    "url": "https://example.invalid/metallic.png",
                    "file_name": "metallic.png",
                    "content_type": "image/png",
                },
            },
            "thumbnail": {
                "url": "https://example.invalid/preview.png",
                "file_name": "preview.png",
            },
            "seed": 11,
        }


class TestHunyuan3dHelperLogic(unittest.TestCase):
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
            "fal_hunyuan_3d_image_to_3d_helper.download",
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

    def _write_ref_png(self, folder):
        path = os.path.join(folder, "ref.png")
        with open(path, "wb") as handle:
            handle.write(_PNG_BYTES)
        return path

    def test_argument_parsing_help_lists_image(self):
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with mock.patch("sys.stdout", buf):
                helper.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = buf.getvalue()
        self.assertIn("--image", text)
        self.assertIn("--out-dir", text)

    def test_missing_image_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            rc = helper.main(
                [
                    "--image",
                    os.path.join(td, "missing.png"),
                    "--out-dir",
                    td,
                    "--fal-key",
                    "test-key",
                ]
            )
        self.assertEqual(rc, 2)
        self.assertIsNone(_FakeSyncClient.last)

    def test_mocked_subscribe_extracts_glb_textures(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_ref_png(td)
            out_dir = os.path.join(td, "out")
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                rc = helper.main(
                    [
                        "--image",
                        image_path,
                        "--out-dir",
                        out_dir,
                        "--fal-key",
                        "test-key",
                        "--face-count",
                        "100000",
                        "--generate-type",
                        "Normal",
                        "--enable-pbr",
                        "--download-obj",
                    ]
                )
            self.assertEqual(rc, 0)
            for name in (
                "model.glb",
                "model.obj",
                "texture.png",
                "material.mtl",
                "preview.png",
                "metallic.png",
                "baseColor.jpg",
                "metallicRoughness.png",
            ):
                self.assertTrue(
                    os.path.isfile(os.path.join(out_dir, name)),
                    "%s was not written" % name,
                )
            summary = None
            for line in reversed(stdout.getvalue().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    summary = json.loads(line)
                    break
            self.assertIsNotNone(summary)
            roles = [item["role"] for item in summary.get("extracted_textures") or []]
            self.assertEqual(roles, ["baseColor", "metallicRoughness"])
            client = _FakeSyncClient.last
            self.assertIsNotNone(client)
            endpoint_id, arguments = client.subscribe_calls[0]
            self.assertEqual(endpoint_id, _ENDPOINT)
            self.assertTrue(arguments.get("enable_pbr"))

    def test_geometry_skips_enable_pbr(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_ref_png(td)
            out_dir = os.path.join(td, "out")
            rc = helper.main(
                [
                    "--image",
                    image_path,
                    "--out-dir",
                    out_dir,
                    "--fal-key",
                    "test-key",
                    "--generate-type",
                    "Geometry",
                    "--enable-pbr",
                ]
            )
            self.assertEqual(rc, 0)
            endpoint_id, arguments = _FakeSyncClient.last.subscribe_calls[0]
            self.assertEqual(endpoint_id, _ENDPOINT)
            self.assertEqual(arguments["generate_type"], "Geometry")
            self.assertNotIn("enable_pbr", arguments)


if __name__ == "__main__":
    unittest.main()
