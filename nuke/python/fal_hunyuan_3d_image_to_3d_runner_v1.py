# Purpose:
# - Runner script for the Nuke Group node `Hunyuan_3D_Image_to_3D_v1` (executes inside Nuke / Python 2.7).
# - Accepts a front-view still on input 0; pre-renders if needed, calls the Python 3 helper, then spawns
#   Read nodes for extracted PBR maps (and fal texture/preview) plus ReadGeo2 for the OBJ.
#   Albedo (baseColor) is piped to ReadGeo img; fal's single texture URL is often the normal map.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_spawn_read_position_v1 as spawn_pos
import nuke_spawn_readgeo_v1 as spawn_geo


def _parse_helper_summary(stdout_lines):
    for line in reversed(stdout_lines):
        line = (line or "").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("ok"):
                return obj
        except Exception:
            pass
    return None


def _extracted_texture_items(summary):
    if not isinstance(summary, dict):
        return []
    items = summary.get("extracted_textures") or []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not path:
            continue
        out.append(item)
    return out


def _albedo_path(extracted_items, fallback_path):
    for item in extracted_items:
        if item.get("role") == "baseColor" and item.get("path"):
            return item.get("path")
    return fallback_path


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 (source_image) is not connected.")
        raise Exception("missing input 0")

    face_count_s = (g.knob("face_count").value() or "100000").strip()
    generate_type = (g.knob("generate_type").value() or "Normal").strip()
    enable_pbr = bool(g.knob("enable_pbr").value())
    download_obj = bool(g.knob("download_obj").value())

    try:
        face_count = int(face_count_s)
    except Exception:
        nuke.message("Face count must be an integer (40000-1500000).")
        raise Exception("invalid face_count")

    if face_count < 40000 or face_count > 1500000:
        nuke.message("Face count must be between 40000 and 1500000.")
        raise Exception("face_count out of range")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="hunyuan_3d_image_to_3d",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke, src_node=src_node, frame=frame, run_dir=temp_dir, base_name="source"
        )
    except Exception as e:
        nuke.message("Failed to prepare input image:\n%s" % str(e))
        raise


    extra_args = [
        "--image",
        image_path,
        "--out-dir",
        out_dir,
        "--face-count",
        str(int(face_count)),
        "--generate-type",
        generate_type,
        "--verbose",
    ]

    if enable_pbr:
        extra_args += ["--enable-pbr"]
    if download_obj:
        extra_args += ["--download-obj"]
    else:
        extra_args += ["--no-download-obj"]

    returncode, stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'Hunyuan 3D'
    )

    summary = _parse_helper_summary(stdout_lines)
    downloaded = {}
    if summary and isinstance(summary.get("downloaded"), dict):
        downloaded = summary.get("downloaded") or {}

    glb_path = downloaded.get("glb") or os.path.join(out_dir, "model.glb")
    if not os.path.isfile(glb_path):
        nuke.message("Helper finished, but no GLB model found in:\n%s" % out_dir)
        raise Exception("no glb output")

    glb_path_nk = prerender.norm_slashes(glb_path)
    obj_path = downloaded.get("obj") or os.path.join(out_dir, "model.obj")
    obj_path_nk = prerender.norm_slashes(obj_path) if os.path.isfile(obj_path) else None
    mtl_path = downloaded.get("mtl")
    mtl_path_nk = prerender.norm_slashes(mtl_path) if mtl_path and os.path.isfile(mtl_path) else None
    texture_path = downloaded.get("texture")
    if not texture_path or not os.path.isfile(texture_path):
        for name in os.listdir(out_dir):
            low = name.lower()
            if low.endswith((".png", ".jpg", ".jpeg", ".webp")) and "texture" in low:
                texture_path = os.path.join(out_dir, name)
                break
    texture_path_nk = prerender.norm_slashes(texture_path) if texture_path and os.path.isfile(texture_path) else None
    preview_path = downloaded.get("preview") or os.path.join(out_dir, "preview.png")
    preview_path_nk = prerender.norm_slashes(preview_path) if os.path.isfile(preview_path) else None

    extracted_items = _extracted_texture_items(summary)
    albedo_path = _albedo_path(extracted_items, texture_path)
    albedo_path_nk = prerender.norm_slashes(albedo_path) if albedo_path and os.path.isfile(albedo_path) else None

    xpos = int(g.xpos())
    ypos = int(g.ypos())
    placed = []

    texture_read = None

    def _spawn_read(file_path_nk, label, name_suffix, x_offset):
        if not file_path_nk or not os.path.isfile(file_path_nk):
            return None
        nuke.root().begin()
        try:
            fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos + x_offset, ypos + 140, exclude_nodes=placed)
            r = nuke.nodes.Read(file=file_path_nk)
            try:
                r.setName("%s_%s_%s" % (g.name(), ts, name_suffix), unique=True)
            except Exception:
                pass
            try:
                r.knob("label").setValue("%s\n%s" % (label, file_path_nk))
            except Exception:
                pass
            r.setXpos(fx)
            r.setYpos(fy)
            placed.append(r)
            return r
        finally:
            nuke.endGroup()

    x_offset = 0
    albedo_read = None
    extracted_paths = {}
    for item in extracted_items:
        item_path = item.get("path")
        if not item_path or not os.path.isfile(item_path):
            continue
        item_path_nk = prerender.norm_slashes(item_path)
        role = item.get("role") or "texture"
        extracted_paths[os.path.normcase(os.path.abspath(item_path))] = True
        spawned = _spawn_read(
            item_path_nk, "Hunyuan 3D %s" % role, str(role), x_offset
        )
        if role == "baseColor" and spawned is not None:
            albedo_read = spawned
        x_offset += 120

    fal_texture_abs = ""
    if texture_path and os.path.isfile(texture_path):
        fal_texture_abs = os.path.normcase(os.path.abspath(texture_path))
    if not extracted_items:
        texture_read = _spawn_read(texture_path_nk, "Hunyuan 3D texture", "texture", x_offset)
        if texture_read is not None:
            x_offset += 120
    elif fal_texture_abs and fal_texture_abs not in extracted_paths:
        _spawn_read(texture_path_nk, "Hunyuan 3D fal texture", "fal_texture", x_offset)
        x_offset += 120

    if albedo_read is not None:
        texture_read = albedo_read
    elif texture_read is None and albedo_path_nk:
        texture_read = _spawn_read(albedo_path_nk, "Hunyuan 3D texture", "texture", x_offset)
        if texture_read is not None:
            x_offset += 120

    _spawn_read(preview_path_nk, "Hunyuan 3D preview", "preview", x_offset)

    readgeo_node = None
    if obj_path_nk and download_obj:
        try:
            readgeo_node = spawn_geo.spawn_readgeo_obj(
                nuke,
                spawn_pos,
                obj_path_nk,
                xpos,
                ypos,
                g.name(),
                ts,
                exclude_nodes=placed,
                texture_node=texture_read,
                label="Hunyuan 3D OBJ",
            )
            if readgeo_node is not None:
                placed.append(readgeo_node)
        except Exception as e:
            print("WARNING: failed to spawn ReadGeo2: %s" % str(e))

    msg_lines = ["3D model generated:", "", "GLB: %s" % glb_path_nk]
    if extracted_items:
        for item in extracted_items:
            item_path = item.get("path")
            if not item_path:
                continue
            msg_lines.append("%s: %s" % (item.get("role") or "texture", prerender.norm_slashes(item_path)))
    elif texture_path_nk:
        msg_lines.append("Texture: %s" % texture_path_nk)
    if mtl_path_nk:
        msg_lines.append("MTL: %s" % mtl_path_nk)
    if obj_path_nk:
        msg_lines.append("OBJ: %s" % obj_path_nk)
    if readgeo_node is not None:
        try:
            msg_lines.append("ReadGeo: %s" % readgeo_node.fullName())
        except Exception:
            msg_lines.append("ReadGeo: spawned in node graph")
    if preview_path_nk:
        msg_lines.append("Preview: %s" % preview_path_nk)
    msg_lines.append("")
    msg_lines.append("View in Nuke 3D (Viewer set to 3D) or import GLB in another DCC.")

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("\n".join(msg_lines))


if __name__ == "__main__":
    main()
