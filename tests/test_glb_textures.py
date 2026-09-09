# Purpose: No-network tests for GLB texture extraction (stdlib glTF parser).
# Run: py -3 -m unittest tests.test_glb_textures

from __future__ import print_function

import base64
import json
import os
import struct
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import fal_glb_textures as glb_tex


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00IEND\xaeB`\x82"
)
_JPEG_BYTES = b"\xff\xd8\xff\xd9ALBEDO"
_GLB_MAGIC = 0x46546C67


def pack_glb(gltf, bin_blob):
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * json_pad
    bin_pad = (4 - (len(bin_blob) % 4)) % 4
    bin_padded = bin_blob + (b"\x00" * bin_pad)
    json_chunk = struct.pack("<I", len(json_bytes)) + b"JSON" + json_bytes
    bin_chunk = struct.pack("<I", len(bin_padded)) + b"BIN\x00" + bin_padded
    body = json_chunk + bin_chunk
    header = struct.pack("<III", _GLB_MAGIC, 2, 12 + len(body))
    return header + body


def write_glb(path, gltf, bin_blob):
    with open(path, "wb") as handle:
        handle.write(pack_glb(gltf, bin_blob))


def _pbr_gltf(bin_len, views):
    return {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": bin_len}],
        "bufferViews": views,
        "images": [
            {"mimeType": "image/jpeg", "bufferView": 0, "name": "albedo"},
            {"mimeType": "image/png", "bufferView": 1, "name": "nrm"},
        ],
        "textures": [{"source": 0}, {"source": 1}],
        "materials": [
            {
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicRoughnessTexture": {"index": 1},
                },
                "normalTexture": {"index": 1},
            }
        ],
    }


class TestGlbTextures(unittest.TestCase):
    def test_extracts_material_roles(self):
        jpeg = _JPEG_BYTES
        png = _PNG_BYTES
        blob = jpeg + png
        views = [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(jpeg)},
            {"buffer": 0, "byteOffset": len(jpeg), "byteLength": len(png)},
        ]
        with tempfile.TemporaryDirectory() as td:
            glb_path = os.path.join(td, "model.glb")
            write_glb(glb_path, _pbr_gltf(len(blob), views), blob)
            extracted = glb_tex.extract_glb_textures(glb_path, td)
            roles = [item["role"] for item in extracted]
            self.assertEqual(roles, ["baseColor", "metallicRoughness"])
            base = extracted[0]
            self.assertTrue(base["path"].endswith("baseColor.jpg"))
            with open(base["path"], "rb") as handle:
                self.assertEqual(handle.read(), jpeg)
            self.assertTrue(os.path.isfile(os.path.join(td, "metallicRoughness.png")))

    def test_leftover_image_uses_name_role(self):
        png = _PNG_BYTES
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(png)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(png)}],
            "images": [{"mimeType": "image/png", "bufferView": 0, "name": "texture_metallic"}],
            "textures": [],
            "materials": [],
        }
        with tempfile.TemporaryDirectory() as td:
            glb_path = os.path.join(td, "model.glb")
            write_glb(glb_path, gltf, png)
            extracted = glb_tex.extract_glb_textures(glb_path, td)
            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0]["role"], "metallic")
            self.assertTrue(extracted[0]["path"].endswith("metallic.png"))

    def test_data_uri_image(self):
        payload = base64.b64encode(_PNG_BYTES).decode("ascii")
        gltf = {
            "asset": {"version": "2.0"},
            "images": [
                {
                    "uri": "data:image/png;base64,%s" % payload,
                    "name": "albedo",
                }
            ],
            "textures": [{"source": 0}],
            "materials": [
                {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            glb_path = os.path.join(td, "model.glb")
            write_glb(glb_path, gltf, b"")
            extracted = glb_tex.extract_glb_textures(glb_path, td)
            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0]["role"], "baseColor")
            with open(extracted[0]["path"], "rb") as handle:
                self.assertEqual(handle.read(), _PNG_BYTES)

    def test_invalid_glb_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "model.glb")
            with open(path, "wb") as handle:
                handle.write(b"not a glb")
            extracted = glb_tex.extract_glb_textures(glb_path=path, out_dir=td)
            self.assertEqual(extracted, [])

    def test_unique_path_when_file_exists(self):
        png = _PNG_BYTES
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(png)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(png)}],
            "images": [{"mimeType": "image/png", "bufferView": 0}],
            "textures": [{"source": 0}],
            "materials": [
                {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            existing = os.path.join(td, "baseColor.png")
            with open(existing, "wb") as handle:
                handle.write(b"old")
            glb_path = os.path.join(td, "model.glb")
            write_glb(glb_path, gltf, png)
            extracted = glb_tex.extract_glb_textures(glb_path, td)
            self.assertEqual(len(extracted), 1)
            self.assertTrue(extracted[0]["path"].endswith("baseColor_2.png"))


if __name__ == "__main__":
    unittest.main()
