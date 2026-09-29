# Purpose: No-network tests for Seedream 5.0 Flash Layerize layer ordering and downloads.
# Run: py -3 -m unittest tests.test_seedream_5_flash_layerize_helper_logic

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

import fal_seedream_5_flash_layerize_helper as helper
import fal_seedream_5_flash_layerize_runner_v1 as runner


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


_LAYER_RESULT = {
    "images": [{"url": "https://example.invalid/ignored.png"}],
    "layers": [
        {
            "image": {
                "url": "https://example.invalid/sky.png",
                "file_name": "sky.png",
                "content_type": "image/png",
                "width": 64,
                "height": 64,
            },
            "z_index": 2,
            "name": "Sky",
            "description": "Blue sky",
        },
        {
            "image": {
                "url": "https://example.invalid/base.png",
                "file_name": "base.png",
                "content_type": "image/png",
            },
            "z_index": 0,
        },
        {
            "image": {
                "url": "https://example.invalid/tree.webp",
                "file_name": "tree.webp",
                "content_type": "image/webp",
            },
            "z_index": 1,
            "name": " Tree ",
            "description": "  A tree  ",
            "bounding_box": {
                "absolute": [1, 2, 3, 4],
                "normalized": [0, 0, 500, 500],
            },
        },
    ],
}


class TestSeedreamFlashLayerizeRecords(unittest.TestCase):
    def test_layers_sort_by_z_index_and_ignore_flat_images(self):
        records = helper.ordered_layer_records(_LAYER_RESULT)
        self.assertEqual([rec["z_index"] for rec in records], [0, 1, 2])
        self.assertEqual(records[0]["url"], "https://example.invalid/base.png")
        self.assertIsNone(records[0]["name"])
        self.assertEqual(records[1]["name"], "Tree")
        self.assertEqual(records[1]["description"], "A tree")
        self.assertEqual(records[1]["bounding_box"]["absolute"], [1, 2, 3, 4])
        self.assertEqual(records[2]["name"], "Sky")

    def test_flat_images_are_used_when_layers_are_missing(self):
        records = helper.ordered_layer_records(
            {
                "images": [
                    {"url": "https://example.invalid/a.png", "file_name": "a.png"},
                    {"url": "https://example.invalid/b.jpg", "content_type": "image/jpeg"},
                ]
            }
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["z_index"], 0)
        self.assertEqual(records[1]["z_index"], 1)
        self.assertIsNone(records[1]["name"])

    def test_entries_without_a_url_are_skipped(self):
        records = helper.ordered_layer_records(
            {
                "layers": [
                    {"image": {"file_name": "nope.png"}, "z_index": 0},
                    {"image": {"url": "https://example.invalid/ok.png"}, "z_index": 1},
                ]
            }
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["z_index"], 1)

    def test_extension_prefers_file_name_then_mime(self):
        self.assertEqual(helper.layer_file_ext("shot.WEBP", "image/png"), "webp")
        self.assertEqual(helper.layer_file_ext(None, "image/jpeg"), "jpg")
        self.assertEqual(helper.layer_file_ext("", "application/octet-stream"), "png")


class TestSeedreamFlashLayerizeMain(unittest.TestCase):
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
            "fal_seedream_5_flash_layerize_helper.download",
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

    def test_main_downloads_layers_in_z_order_and_writes_meta(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            out_dir = os.path.join(td, "out")
            captured = {}

            def _subscribe(client, endpoint, arguments, **kwargs):
                del client, kwargs
                captured["endpoint"] = endpoint
                captured["arguments"] = arguments
                return _LAYER_RESULT

            with mock.patch(
                "fal_seedream_5_flash_layerize_helper.subscribe_with_retry",
                side_effect=_subscribe,
            ):
                with mock.patch("sys.stdout", io.StringIO()):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--out-dir",
                            out_dir,
                            "--prompt",
                            "separate the tree",
                            "--image-size",
                            "auto_1.5K",
                            "--enhance-prompt-mode",
                            "fast",
                            "--no-enable-safety-checker",
                            "--fal-key",
                            "test-key",
                        ]
                    )

            self.assertEqual(rc, 0)
            self.assertEqual(captured["endpoint"], helper._ENDPOINT_ID)
            self.assertEqual(
                captured["arguments"]["image_url"],
                "https://example.invalid/uploaded.png",
            )
            self.assertEqual(captured["arguments"]["prompt"], "separate the tree")
            self.assertEqual(captured["arguments"]["image_size"], "auto_1.5K")
            self.assertEqual(captured["arguments"]["enhance_prompt_mode"], "fast")
            self.assertFalse(captured["arguments"]["enable_safety_checker"])
            self.assertFalse(captured["arguments"]["sync_mode"])
            self.assertEqual(len(_FakeSyncClient.last.uploaded), 1)

            base = os.path.join(out_dir, "layer_0", "layer.png")
            tree = os.path.join(out_dir, "layer_1", "layer.webp")
            sky = os.path.join(out_dir, "layer_2", "layer.png")
            self.assertTrue(os.path.isfile(base))
            self.assertTrue(os.path.isfile(tree))
            self.assertTrue(os.path.isfile(sky))
            with open(os.path.join(out_dir, "layer_1", "layer_meta.json"), "r") as handle:
                meta = json.load(handle)
            self.assertEqual(meta["z_index"], 1)
            self.assertEqual(meta["name"], "Tree")
            self.assertEqual(meta["description"], "A tree")
            self.assertNotIn("url", meta)
            with open(os.path.join(out_dir, "layer_0", "layer_meta.json"), "r") as handle:
                base_meta = json.load(handle)
            self.assertEqual(base_meta["width"], 1)
            self.assertEqual(base_meta["height"], 1)

    def test_unexpected_shape_exits_4(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = self._write_png(td)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                with mock.patch(
                    "fal_seedream_5_flash_layerize_helper.subscribe_with_retry",
                    return_value={"layers": [], "images": []},
                ):
                    rc = helper.main(
                        [
                            "--image",
                            image_path,
                            "--out-dir",
                            td,
                            "--fal-key",
                            "test-key",
                        ]
                    )
        self.assertEqual(rc, 4)
        self.assertIn("unexpected response shape", stderr.getvalue())


class TestSeedreamFlashLayerizePlacement(unittest.TestCase):
    def test_output_path_skips_json_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "layer.json"), "w") as handle:
                handle.write("{}")
            with open(os.path.join(td, "layer.png"), "wb") as handle:
                handle.write(_PNG_BYTES)
            with open(os.path.join(td, "layer_meta.json"), "w") as handle:
                handle.write("{}")
            picked = runner._layer_output_path(td)
            self.assertTrue(picked.endswith("layer.png"))

    def test_base_plate_has_no_box(self):
        self.assertIsNone(runner.absolute_box({"z_index": 0, "bounding_box": None}))
        box = runner.absolute_box(
            {"bounding_box": {"absolute": [156, 0, 2816, 1584]}}
        )
        self.assertEqual(box, (156, 0, 2816, 1584))

    def test_crop_transform_when_plate_matches_base(self):
        # Base and connected plate are both 2816x1584. Scale is uniform from width.
        # translate_y = plate_h - bottom, because Nuke y is up.
        plate = (2816, 1584)
        cases = (
            ("building", 2660, 1584, (156, 0, 2816, 1584), 1.0, 156.0, 0.0),
            ("bushes", 2166, 932, (0, 901, 1588, 1584), 1588.0 / 2166.0, 0.0, 0.0),
            ("sky", 2324, 1124, (0, 0, 2263, 1095), 2263.0 / 2324.0, 0.0, 489.0),
            ("trees", 2352, 1114, (0, 681, 1907, 1584), 1907.0 / 2352.0, 0.0, 0.0),
        )
        for name, crop_w, crop_h, box, scale, tx, ty in cases:
            got = runner.layer_transform(
                plate[0], plate[1], plate[0], plate[1], crop_w, crop_h, box
            )
            self.assertIsNotNone(got, name)
            self.assertAlmostEqual(got[0], scale, places=6, msg=name)
            self.assertAlmostEqual(got[1], tx, places=6, msg=name)
            self.assertAlmostEqual(got[2], ty, places=6, msg=name)

    def test_base_transform_is_identity_when_plate_matches_base(self):
        got = runner.layer_transform(2816, 1584, 2816, 1584, 2816, 1584, None)
        self.assertEqual(got, (1.0, 0.0, 0.0))

    def test_transform_maps_box_when_plate_size_differs(self):
        # Plate 2000x1000, fal base 2816x1584. sx and sy both apply.
        in_w, in_h = 2000.0, 1000.0
        base_w, base_h = 2816.0, 1584.0
        sx = in_w / base_w
        sy = in_h / base_h
        building = runner.layer_transform(
            in_w, in_h, base_w, base_h, 2660, 1584, (156, 0, 2816, 1584)
        )
        self.assertAlmostEqual(building[0], ((2816.0 - 156.0) * sx) / 2660.0)
        self.assertAlmostEqual(building[1], 156.0 * sx)
        self.assertAlmostEqual(building[2], in_h - (1584.0 * sy))
        sky = runner.layer_transform(
            in_w, in_h, base_w, base_h, 2324, 1124, (0, 0, 2263, 1095)
        )
        self.assertAlmostEqual(sky[0], (2263.0 * sx) / 2324.0)
        self.assertAlmostEqual(sky[1], 0.0)
        self.assertAlmostEqual(sky[2], in_h - (1095.0 * sy))
        base = runner.layer_transform(in_w, in_h, base_w, base_h, base_w, base_h, None)
        self.assertAlmostEqual(base[0], sx)
        self.assertEqual(base[1], 0.0)
        self.assertEqual(base[2], 0.0)

    def test_transform_returns_none_when_size_missing(self):
        self.assertIsNone(
            runner.layer_transform(0, 1584, 2816, 1584, 2660, 1584, (156, 0, 2816, 1584))
        )
        self.assertIsNone(runner.layer_transform(2816, 1584, 0, 1584, 2816, 1584, None))


if __name__ == "__main__":
    unittest.main()
