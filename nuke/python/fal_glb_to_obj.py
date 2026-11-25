# Purpose:
# - Convert a binary glTF (GLB) mesh into an OBJ Nuke ReadGeo can load.
# - Pulls the base-color image out beside the OBJ and writes an MTL for it.
# - Stdlib only. Used by the MoGe-3 helper; the GLB itself is not a Nuke mesh.

from __future__ import annotations

import os
import struct

from fal_glb_textures import extract_glb_textures, parse_glb

# glTF accessor componentType -> (struct code, byte size).
_COMPONENTS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
_TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
# Signed normalized integers use these positive peaks (glTF spec).
_NORM_PEAK = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
_TRIANGLES = 4


def _identity():
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def _mul(a, b):
    """Column-major 4x4 product a * b."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            total = 0.0
            for k in range(4):
                total += a[k * 4 + row] * b[col * 4 + k]
            out[col * 4 + row] = total
    return out


def _mat_from_node(node):
    """glTF node transform as a column-major 4x4. Missing fields are identity."""
    if not isinstance(node, dict):
        return _identity()
    matrix = node.get("matrix")
    if isinstance(matrix, list) and len(matrix) == 16:
        return [float(v) for v in matrix]
    translation = node.get("translation") or [0.0, 0.0, 0.0]
    rotation = node.get("rotation") or [0.0, 0.0, 0.0, 1.0]
    scale = node.get("scale") or [1.0, 1.0, 1.0]
    x, y, z, w = (float(rotation[0]), float(rotation[1]), float(rotation[2]), float(rotation[3]))
    sx, sy, sz = (float(scale[0]), float(scale[1]), float(scale[2]))
    tx, ty, tz = (float(translation[0]), float(translation[1]), float(translation[2]))
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    # Row-major rotation, stored below as column-major.
    r00 = 1.0 - 2.0 * (yy + zz)
    r01 = 2.0 * (xy - wz)
    r02 = 2.0 * (xz + wy)
    r10 = 2.0 * (xy + wz)
    r11 = 1.0 - 2.0 * (xx + zz)
    r12 = 2.0 * (yz - wx)
    r20 = 2.0 * (xz - wy)
    r21 = 2.0 * (yz + wx)
    r22 = 1.0 - 2.0 * (xx + yy)
    rot_scale = [
        r00 * sx, r10 * sx, r20 * sx, 0.0,
        r01 * sy, r11 * sy, r21 * sy, 0.0,
        r02 * sz, r12 * sz, r22 * sz, 0.0,
        tx, ty, tz, 1.0,
    ]
    return rot_scale


def _transform_point(matrix, point):
    x, y, z = point
    ox = matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12]
    oy = matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13]
    oz = matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14]
    return (ox, oy, oz)


def read_accessor(gltf, bin_blob, accessor_index):
    """Return accessor items. SCALAR is a float/int; VEC* is a tuple."""
    accessors = gltf.get("accessors") or []
    if not isinstance(accessor_index, int) or accessor_index < 0 or accessor_index >= len(accessors):
        raise ValueError("GLB accessor index out of range")
    acc = accessors[accessor_index]
    if not isinstance(acc, dict):
        raise ValueError("GLB accessor is not an object")
    if acc.get("sparse"):
        raise ValueError("sparse GLB accessors are not supported")
    view_index = acc.get("bufferView")
    views = gltf.get("bufferViews") or []
    if not isinstance(view_index, int) or view_index < 0 or view_index >= len(views):
        raise ValueError("GLB accessor has no bufferView")
    view = views[view_index]
    if not isinstance(view, dict):
        raise ValueError("GLB bufferView is not an object")
    comp_type = int(acc.get("componentType"))
    if comp_type not in _COMPONENTS:
        raise ValueError("unsupported GLB componentType %s" % comp_type)
    type_name = str(acc.get("type") or "")
    if type_name not in _TYPE_COUNT:
        raise ValueError("unsupported GLB accessor type %s" % type_name)
    fmt, comp_size = _COMPONENTS[comp_type]
    ncomp = _TYPE_COUNT[type_name]
    count = int(acc.get("count") or 0)
    if count < 0:
        raise ValueError("GLB accessor count is negative")
    tight = comp_size * ncomp
    stride = int(view.get("byteStride") or tight)
    if stride < tight:
        raise ValueError("GLB bufferView stride is shorter than one element")
    start = int(view.get("byteOffset") or 0) + int(acc.get("byteOffset") or 0)
    if count:
        end = start + (count - 1) * stride + tight
        if start < 0 or end > len(bin_blob):
            raise ValueError("GLB accessor exceeds the binary chunk")
    normalize = bool(acc.get("normalized")) and comp_type in _NORM_PEAK
    peak = _NORM_PEAK.get(comp_type, 1.0)
    out = []
    for i in range(count):
        offset = start + i * stride
        values = []
        for c in range(ncomp):
            value = struct.unpack_from("<" + fmt, bin_blob, offset + c * comp_size)[0]
            if normalize:
                value = float(value) / peak
            values.append(value)
        if ncomp == 1:
            out.append(values[0])
        else:
            out.append(tuple(values))
    return out


def _scene_mesh_nodes(gltf):
    """Yield (mesh_index, world_matrix) for the default scene."""
    nodes = gltf.get("nodes") or []
    if not isinstance(nodes, list):
        nodes = []
    scenes = gltf.get("scenes") or []
    roots = []
    if isinstance(scenes, list) and scenes:
        scene_index = gltf.get("scene") or 0
        if not isinstance(scene_index, int) or scene_index < 0 or scene_index >= len(scenes):
            scene_index = 0
        scene = scenes[scene_index]
        if isinstance(scene, dict):
            roots = scene.get("nodes") or []
    if not roots and nodes:
        roots = list(range(len(nodes)))

    found = []

    def _walk(index, parent):
        if not isinstance(index, int) or index < 0 or index >= len(nodes):
            return
        node = nodes[index]
        if not isinstance(node, dict):
            return
        world = _mul(parent, _mat_from_node(node))
        mesh_index = node.get("mesh")
        if isinstance(mesh_index, int):
            found.append((mesh_index, world))
        for child in node.get("children") or []:
            _walk(child, world)

    for root in roots:
        _walk(root, _identity())
    if not found and gltf.get("meshes"):
        found.append((0, _identity()))
    return found


def _triangles_from_primitive(gltf, bin_blob, primitive):
    """Return (positions, uvs or None, index triples). Positions are untransformed."""
    attrs = primitive.get("attributes") or {}
    if not isinstance(attrs, dict) or not isinstance(attrs.get("POSITION"), int):
        raise ValueError("GLB primitive has no POSITION")
    mode = primitive.get("mode", _TRIANGLES)
    if mode != _TRIANGLES:
        raise ValueError("only triangle GLB meshes are supported (mode %s)" % mode)
    positions = read_accessor(gltf, bin_blob, attrs["POSITION"])
    uvs = None
    if isinstance(attrs.get("TEXCOORD_0"), int):
        raw_uvs = read_accessor(gltf, bin_blob, attrs["TEXCOORD_0"])
        if len(raw_uvs) == len(positions):
            # glTF UV origin is the top-left. OBJ / Nuke origin is the bottom-left.
            # trimesh writes that flip on export, so flip it back here.
            uvs = [(float(uv[0]), 1.0 - float(uv[1])) for uv in raw_uvs]
    if isinstance(primitive.get("indices"), int):
        raw = read_accessor(gltf, bin_blob, primitive["indices"])
        indices = [int(v) for v in raw]
    else:
        indices = list(range(len(positions)))
    if len(indices) < 3 or len(indices) % 3 != 0:
        raise ValueError("GLB triangle index count is not a multiple of 3")
    faces = []
    count = len(positions)
    for i in range(0, len(indices), 3):
        tri = (indices[i], indices[i + 1], indices[i + 2])
        for idx in tri:
            if idx < 0 or idx >= count:
                raise ValueError("GLB triangle index out of range")
        faces.append(tri)
    return positions, uvs, faces


def _base_color_name(extracted):
    for item in extracted:
        if item.get("role") == "baseColor" and item.get("path"):
            return os.path.basename(item["path"]), item["path"]
    for item in extracted:
        path = item.get("path")
        if path:
            return os.path.basename(path), path
    return None, None


def _write_obj(obj_path, positions, uvs, faces, mtl_name):
    with open(obj_path, "w", encoding="ascii", newline="\n") as handle:
        handle.write("# Converted from GLB for Nuke ReadGeo\n")
        if mtl_name:
            handle.write("mtllib %s\n" % mtl_name)
            handle.write("usemtl moge\n")
        chunk = []
        for x, y, z in positions:
            chunk.append("v %.6g %.6g %.6g\n" % (x, y, z))
            if len(chunk) >= 20000:
                handle.write("".join(chunk))
                chunk = []
        if uvs:
            for u, v in uvs:
                chunk.append("vt %.6g %.6g\n" % (u, v))
                if len(chunk) >= 20000:
                    handle.write("".join(chunk))
                    chunk = []
        for a, b, c in faces:
            if uvs:
                chunk.append(
                    "f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1)
                )
            else:
                chunk.append("f %d %d %d\n" % (a + 1, b + 1, c + 1))
            if len(chunk) >= 20000:
                handle.write("".join(chunk))
                chunk = []
        if chunk:
            handle.write("".join(chunk))


def glb_to_obj(glb_path, out_dir):
    """
    Write model.obj (and model.mtl when a texture is embedded) into out_dir.

    Returns {"obj", "mtl", "texture", "triangles"}. mtl and texture are None
    when the mesh has no image. Raises ValueError when the GLB has no triangles.
    """
    gltf, bin_blob = parse_glb(glb_path)
    meshes = gltf.get("meshes") or []
    positions = []
    uvs = []
    faces = []
    any_uv = False
    missing_uv = False
    for mesh_index, world in _scene_mesh_nodes(gltf):
        if mesh_index < 0 or mesh_index >= len(meshes):
            continue
        mesh = meshes[mesh_index]
        if not isinstance(mesh, dict):
            continue
        for primitive in mesh.get("primitives") or []:
            if not isinstance(primitive, dict):
                continue
            prim_pos, prim_uv, prim_faces = _triangles_from_primitive(gltf, bin_blob, primitive)
            base = len(positions)
            for point in prim_pos:
                positions.append(_transform_point(world, (float(point[0]), float(point[1]), float(point[2]))))
            if prim_uv is None:
                missing_uv = True
                uvs.extend((0.0, 0.0) for _ in prim_pos)
            else:
                any_uv = True
                uvs.extend(prim_uv)
            for a, b, c in prim_faces:
                faces.append((a + base, b + base, c + base))
    if not faces:
        raise ValueError("GLB contains no triangles")

    os.makedirs(out_dir, exist_ok=True)
    extracted = extract_glb_textures(glb_path, out_dir)
    tex_name, tex_path = _base_color_name(extracted)
    use_uv = any_uv and not missing_uv
    mtl_path = None
    obj_path = os.path.join(out_dir, "model.obj")
    mtl_name = None
    if use_uv and tex_name:
        mtl_name = "model.mtl"
        mtl_path = os.path.join(out_dir, mtl_name)
        with open(mtl_path, "w", encoding="ascii", newline="\n") as handle:
            handle.write("newmtl moge\n")
            handle.write("Kd 1 1 1\n")
            handle.write("map_Kd %s\n" % tex_name)
    _write_obj(obj_path, positions, uvs if use_uv else None, faces, mtl_name)
    return {
        "obj": os.path.abspath(obj_path),
        "mtl": os.path.abspath(mtl_path) if mtl_path else None,
        "texture": os.path.abspath(tex_path) if (use_uv and tex_path) else None,
        "triangles": len(faces),
    }
