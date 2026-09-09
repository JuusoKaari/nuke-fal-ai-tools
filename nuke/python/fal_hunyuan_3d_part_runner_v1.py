# Purpose:
# - Runner script for the Nuke Group node `Hunyuan_3D_Part_v1` (executes inside Nuke / Python 2.7).
# - Reads a local FBX path from the input_file knob, calls the Python 3 helper, then spawns
#   one ReadGeo2 per downloaded part FBX.
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


def _collect_part_paths(downloaded, out_dir):
    parts = []
    raw = None
    if isinstance(downloaded, dict):
        raw = downloaded.get("parts")
    if isinstance(raw, (list, tuple)):
        for item in raw:
            text = (item or "").strip()
            if text and os.path.isfile(text):
                parts.append(text)
    if parts:
        return parts
    try:
        names = os.listdir(out_dir)
    except Exception:
        names = []
    for name in sorted(names):
        if not str(name).lower().endswith(".fbx"):
            continue
        path = os.path.join(out_dir, name)
        if os.path.isfile(path):
            parts.append(path)
    return parts


def _spawn_part_readgeo(nuke_module, file_path_nk, base_x, base_y, name_prefix, timestamp, index, exclude_nodes):
    nuke_module.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(
            nuke_module,
            int(base_x) + (int(index) * 120),
            int(base_y) + 280,
            exclude_nodes=exclude_nodes,
        )
        geo = spawn_geo.create_readgeo(nuke_module, file_path_nk)
        try:
            geo.setName("%s_%s_part_%s" % (name_prefix, timestamp, index), unique=True)
        except Exception:
            pass
        try:
            geo.knob("label").setValue("Hunyuan 3D Part %s\n%s" % (index, file_path_nk))
        except Exception:
            pass
        geo.setXpos(fx)
        geo.setYpos(fy)
        return geo
    finally:
        nuke_module.endGroup()


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    input_file = ""
    try:
        input_file = (g.knob("input_file").value() or "").strip()
    except Exception:
        input_file = ""
    if not input_file:
        nuke.message("Set Input FBX to a local .fbx file.")
        raise Exception("missing input_file")
    if not os.path.isfile(input_file):
        nuke.message("Input FBX not found:\n%s" % input_file)
        raise Exception("input_file not found")
    if not input_file.lower().endswith(".fbx"):
        nuke.message("Input must be an FBX file.")
        raise Exception("input_file not fbx")

    _temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="hunyuan_3d_part",
        group_node=g,
    )

    extra_args = [
        "--input-file",
        input_file,
        "--out-dir",
        out_dir,
        "--verbose",
    ]

    returncode, stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, "Hunyuan 3D Part"
    )
    del returncode

    summary = _parse_helper_summary(stdout_lines)
    downloaded = {}
    if summary and isinstance(summary.get("downloaded"), dict):
        downloaded = summary.get("downloaded") or {}

    parts = _collect_part_paths(downloaded, out_dir)
    if not parts:
        nuke.message("Helper finished, but no part FBX files found in:\n%s" % out_dir)
        raise Exception("no part fbx output")

    xpos = int(g.xpos())
    ypos = int(g.ypos())
    placed = []
    spawned = []
    for index, part_path in enumerate(parts):
        path_nk = prerender.norm_slashes(part_path)
        try:
            geo = _spawn_part_readgeo(
                nuke,
                path_nk,
                xpos,
                ypos,
                g.name(),
                ts,
                index,
                exclude_nodes=placed,
            )
        except Exception as e:
            print("WARNING: failed to spawn ReadGeo2 for part %s: %s" % (index, str(e)))
            continue
        if geo is not None:
            placed.append(geo)
            spawned.append((index, path_nk, geo))

    msg_lines = ["3D parts generated:", ""]
    for index, path_nk, geo in spawned:
        try:
            geo_name = geo.fullName()
        except Exception:
            geo_name = "ReadGeo"
        msg_lines.append("Part %s: %s" % (index, path_nk))
        msg_lines.append("  ReadGeo: %s" % geo_name)
    if not spawned:
        for index, part_path in enumerate(parts):
            msg_lines.append("Part %s: %s" % (index, prerender.norm_slashes(part_path)))
    msg_lines.append("")
    msg_lines.append("View in Nuke 3D (Viewer set to 3D) or import the FBX files in another DCC.")

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("\n".join(msg_lines))


if __name__ == "__main__":
    main()
