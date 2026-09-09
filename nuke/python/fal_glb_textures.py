# Purpose:
# - Extract embedded texture images from a GLB (binary glTF) into PNG/JPEG/WebP files.
# - Used by Hunyuan 3D helpers: fal only returns one model_urls.texture file, while PBR
#   maps (albedo, metallic-roughness, normal) live inside the GLB.
# - Stdlib only (no pygltflib / Pillow).

from __future__ import annotations

import base64
import json
import os
import struct
import sys

_GLB_MAGIC = 0x46546C67  # "glTF"
_JSON_CHUNK = 0x4E4F534A  # "JSON"
_BIN_CHUNK = 0x004E4942  # "BIN\0"

_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}

# Longer tokens first so metallicroughness wins over metallic.
_NAME_ROLES = (
    ("metallicroughness", "metallicRoughness"),
    ("metal_rough", "metallicRoughness"),
    ("basecolor", "baseColor"),
    ("base_color", "baseColor"),
    ("albedo", "baseColor"),
    ("diffuse", "baseColor"),
    ("metallic", "metallic"),
    ("roughness", "roughness"),
    ("normal", "normal"),
    ("occlusion", "occlusion"),
    ("emissive", "emissive"),
)

_GENERIC_NAME = ("texture", "image", "img")


def _safe_stem(raw: str) -> str:
    text = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in str(raw or ""))
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("._")


def _role_from_name(name: str) -> str | None:
    low = str(name or "").lower().replace("-", "_").replace(" ", "_")
    if not low:
        return None
    for token, role in _NAME_ROLES:
        if token in low:
            return role
    if low == "ao" or low.endswith("_ao"):
        return "occlusion"
    return None


def _ext_for_mime(mime: str, blob: bytes) -> str:
    ext = _MIME_EXT.get((mime or "").lower().split(";")[0].strip())
    if ext:
        return ext
    if blob.startswith(b"\x89PNG"):
        return ".png"
    if blob.startswith(b"\xff\xd8"):
        return ".jpg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def _unique_path(out_dir: str, stem: str, ext: str) -> str:
    path = os.path.join(out_dir, stem + ext)
    n = 2
    while os.path.isfile(path):
        path = os.path.join(out_dir, "%s_%d%s" % (stem, n, ext))
        n += 1
    return path


def parse_glb(path: str) -> tuple[dict, bytes]:
    """Return (gltf_json, bin_chunk_bytes). Raises ValueError on a bad file."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 12:
        raise ValueError("GLB too small")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise ValueError("not a GLB file")
    if version != 2:
        raise ValueError("unsupported GLB version %s" % version)
    if length > len(data):
        length = len(data)

    json_doc = None
    bin_blob = b""
    offset = 12
    while offset + 8 <= length:
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == _JSON_CHUNK:
            json_doc = json.loads(chunk.decode("utf-8"))
        elif chunk_type == _BIN_CHUNK:
            bin_blob = chunk
    if not isinstance(json_doc, dict):
        raise ValueError("GLB missing JSON chunk")
    return json_doc, bin_blob


def _texture_image_index(gltf: dict, tex_info) -> int | None:
    if not isinstance(tex_info, dict):
        return None
    idx = tex_info.get("index")
    textures = gltf.get("textures") or []
    if not isinstance(idx, int) or idx < 0 or idx >= len(textures):
        return None
    tex = textures[idx]
    if not isinstance(tex, dict):
        return None
    src = tex.get("source")
    if not isinstance(src, int) or src < 0:
        return None
    return src


def _roles_by_image(gltf: dict) -> dict[int, list[str]]:
    roles: dict[int, list[str]] = {}
    materials = gltf.get("materials") or []
    if not isinstance(materials, list):
        return roles

    def _add(role: str, tex_info) -> None:
        src = _texture_image_index(gltf, tex_info)
        if src is None:
            return
        existing = roles.setdefault(src, [])
        if role not in existing:
            existing.append(role)

    for mat in materials:
        if not isinstance(mat, dict):
            continue
        pbr = mat.get("pbrMetallicRoughness") or {}
        if not isinstance(pbr, dict):
            pbr = {}
        _add("baseColor", pbr.get("baseColorTexture"))
        _add("metallicRoughness", pbr.get("metallicRoughnessTexture"))
        _add("normal", mat.get("normalTexture"))
        _add("occlusion", mat.get("occlusionTexture"))
        _add("emissive", mat.get("emissiveTexture"))
    return roles


def _buffer_view_bytes(view: dict, bin_blob: bytes) -> bytes | None:
    if not isinstance(view, dict):
        return None
    offset = int(view.get("byteOffset") or 0)
    length = int(view.get("byteLength") or 0)
    if offset < 0 or length < 0:
        return None
    end = offset + length
    if end > len(bin_blob):
        return None
    return bin_blob[offset:end]


def _image_bytes(image: dict, buffer_views: list, bin_blob: bytes) -> tuple[bytes, str] | tuple[None, None]:
    if not isinstance(image, dict):
        return None, None
    mime = str(image.get("mimeType") or "")
    if "bufferView" in image:
        idx = image.get("bufferView")
        if not isinstance(idx, int) or idx < 0 or idx >= len(buffer_views):
            return None, None
        blob = _buffer_view_bytes(buffer_views[idx], bin_blob)
        if blob is None:
            return None, None
        return blob, mime
    uri = image.get("uri")
    if not isinstance(uri, str) or not uri.startswith("data:"):
        return None, None
    header, sep, payload = uri.partition(",")
    if not sep:
        return None, None
    try:
        blob = base64.b64decode(payload)
    except Exception:
        return None, None
    if not mime and ";" in header:
        mime = header.split(":", 1)[-1].split(";", 1)[0]
    elif not mime and header.startswith("data:"):
        mime = header[5:].split(";", 1)[0]
    return blob, mime


def _stem_for_image(index: int, image: dict, roles: list[str]) -> tuple[str, str]:
    """Return (filename_stem, role_label)."""
    if roles:
        return roles[0], roles[0]
    name = str(image.get("name") or "")
    guessed = _role_from_name(name)
    if guessed:
        return guessed, guessed
    safe = _safe_stem(name)
    low = safe.lower()
    if safe and low not in _GENERIC_NAME and not low.startswith("texture_") and not low.startswith("image_"):
        return safe, "extra"
    return "extra_%d" % index, "extra"


def extract_glb_textures(glb_path: str, out_dir: str, verbose: bool = False) -> list[dict]:
    """
    Write embedded GLB images into out_dir.

    Each item is {"role": "baseColor"|"metallicRoughness"|"normal"|..., "path": abs_path}.
    Returns [] if the file has no images or cannot be parsed.
    """
    try:
        gltf, bin_blob = parse_glb(glb_path)
    except Exception as e:
        print("WARNING: GLB texture extract skipped: %s" % e, file=sys.stderr)
        return []

    images = gltf.get("images") or []
    if not isinstance(images, list) or not images:
        if verbose:
            print("GLB has no embedded images")
        return []

    buffer_views = gltf.get("bufferViews") or []
    if not isinstance(buffer_views, list):
        buffer_views = []

    roles_by_image = _roles_by_image(gltf)
    os.makedirs(out_dir, exist_ok=True)

    extracted: list[dict] = []
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            continue
        blob, mime = _image_bytes(image, buffer_views, bin_blob)
        if not blob:
            continue
        stem, role = _stem_for_image(index, image, roles_by_image.get(index) or [])
        ext = _ext_for_mime(mime, blob)
        out_path = _unique_path(out_dir, stem, ext)
        with open(out_path, "wb") as handle:
            handle.write(blob)
        extracted.append({"role": role, "path": os.path.abspath(out_path)})
        if verbose:
            print("Extracted GLB texture [%s] -> %s" % (role, out_path))

    if verbose:
        print("Extracted %d texture(s) from GLB" % len(extracted))
    return extracted
