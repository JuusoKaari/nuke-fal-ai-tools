# Purpose: No-network tests for GLB to OBJ conversion used by MoGe-3.
# Run: py -3 -m unittest tests.test_glb_to_obj

from __future__ import print_function

import os
import struct
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import fal_glb_to_obj as glb_obj
import test_glb_textures as glb_test


def _triangle_glb(translation=None):
    positions = struct.pack("<9f", 0.0, 0.0, -1.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0)
    uvs = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    indices = struct.pack("<3I", 0, 1, 2)
    png = glb_test._PNG_BYTES
    blob = positions + uvs + indices + png
    views = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
        {"buffer": 0, "byteOffset": len(positions), "byteLength": len(uvs)},
        {"buffer": 0, "byteOffset": len(positions) + len(uvs), "byteLength": len(indices)},
        {"buffer": 0, "byteOffset": len(positions) + len(uvs) + len(indices), "byteLength": len(png)},
    ]
    node = {"mesh": 0}
    if translation is not None:
        node["translation"] = list(translation)
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"},
            {"bufferView": 2, "componentType": 5125, "count": 3, "type": "SCALAR"},
        ],
        "images": [{"mimeType": "image/png", "bufferView": 3, "name": "albedo"}],
        "textures": [{"source": 0}],
        "materials": [
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ]
            }
        ],
        "nodes": [node],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    return glb_test.pack_glb(gltf, blob)


class TestGlbToObj(unittest.TestCase):
    def test_textured_triangle_flips_gltf_v(self):
        with tempfile.TemporaryDirectory() as td:
            glb_path = os.path.join(td, "model.glb")
            with open(glb_path, "wb") as handle:
                handle.write(_triangle_glb())
            result = glb_obj.glb_to_obj(glb_path, td)
            self.assertTrue(result["obj"].endswith("model.obj"))
            self.assertEqual(result["triangles"], 1)
            self.assertTrue(os.path.isfile(result["texture"]))
            with open(result["obj"], "r") as handle:
                text = handle.read()
            self.assertIn("v 0 0 -1\n", text)
            self.assertIn("v 1 0 -1\n", text)
            self.assertIn("vt 0 1\n", text)
            self.assertIn("vt 1 1\n", text)
            self.assertIn("vt 0 0\n", text)
            self.assertIn("f 1/1 2/2 3/3\n", text)
            with open(result["mtl"], "r") as handle:
                mtl = handle.read()
            self.assertIn("map_Kd baseColor.png", mtl)

    def test_node_translation_moves_vertices(self):
        with tempfile.TemporaryDirectory() as td:
            glb_path = os.path.join(td, "model.glb")
            with open(glb_path, "wb") as handle:
                handle.write(_triangle_glb(translation=(2.0, 0.0, 0.0)))
            result = glb_obj.glb_to_obj(glb_path, td)
            with open(result["obj"], "r") as handle:
                text = handle.read()
            self.assertIn("v 2 0 -1\n", text)
            self.assertNotIn("v 0 0 -1\n", text)


if __name__ == "__main__":
    unittest.main()
