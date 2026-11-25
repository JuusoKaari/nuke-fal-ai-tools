# Purpose:
# - Runner for the Nuke Group `MoGe_3_v1` (executes inside Nuke / Python 2.7).
# - One still in. Calls the Python 3 helper, then spawns ReadGeo2 for the OBJ
#   and a Camera2 from the returned FOV and intrinsics.
# - Does not spawn depth, normals, a point cloud, or a ScanlineRender setup.
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
import nuke_spawn_camera_v1 as spawn_cam


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


def _optional_float(text):
    raw = (text or "").strip()
    if not raw:
        return None
    return float(raw)


def _fmt(value):
    try:
        return "%.3f" % float(value)
    except Exception:
        return "?"


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

    try:
        resolution_level = int(g.knob("resolution_level").value())
        refinement_steps = int(g.knob("num_refinement_steps").value())
        edge_threshold = float(g.knob("edge_threshold").value())
        fov_x = _optional_float(g.knob("known_fov_x").value())
    except Exception:
        nuke.message("Resolution level, refinement steps, edge threshold, and FOV must be numbers.")
        raise Exception("invalid knobs")

    if resolution_level < 0 or resolution_level > 9:
        nuke.message("Resolution level must be between 0 and 9.")
        raise Exception("resolution_level out of range")
    if refinement_steps < 0 or refinement_steps > 20:
        nuke.message("Refinement steps must be between 0 and 20.")
        raise Exception("num_refinement_steps out of range")
    if edge_threshold < 0.0 or edge_threshold > 1.0:
        nuke.message("Edge threshold must be between 0 and 1.")
        raise Exception("edge_threshold out of range")
    if fov_x is not None and (fov_x <= 0.0 or fov_x >= 180.0):
        nuke.message("Known horizontal FOV must be empty, or between 0 and 180 degrees.")
        raise Exception("fov_x out of range")

    apply_mask = bool(g.knob("apply_mask").value())

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="moge_3",
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
        "--resolution-level",
        str(int(resolution_level)),
        "--num-refinement-steps",
        str(int(refinement_steps)),
        "--edge-threshold",
        str(float(edge_threshold)),
        "--verbose",
    ]
    if apply_mask:
        extra_args.append("--apply-mask")
    else:
        extra_args.append("--no-apply-mask")
    if fov_x is not None:
        extra_args.extend(["--fov-x", str(fov_x)])

    _returncode, stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, "MoGe-3"
    )

    summary = _parse_helper_summary(stdout_lines)
    if not summary:
        nuke.message("MoGe-3 finished, but the helper summary was missing.")
        raise Exception("no helper summary")

    obj_path = summary.get("obj") or ""
    if not obj_path or not os.path.isfile(obj_path):
        nuke.message("Helper finished, but no OBJ mesh was written in:\n%s" % out_dir)
        raise Exception("no obj output")

    obj_path_nk = prerender.norm_slashes(obj_path)
    xpos = int(g.xpos())
    ypos = int(g.ypos())
    placed = []

    readgeo_node = None
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
            texture_node=None,
            label="MoGe-3 OBJ",
            y_offset=140,
        )
        if readgeo_node is not None:
            placed.append(readgeo_node)
    except Exception as e:
        print("WARNING: failed to spawn ReadGeo2: %s" % str(e))

    camera = summary.get("camera") if isinstance(summary.get("camera"), dict) else None
    fov_x_out = summary.get("fov_x")
    fov_y_out = summary.get("fov_y")
    label = "MoGe-3\nfov %s x %s deg" % (_fmt(fov_x_out), _fmt(fov_y_out))
    camera_node = None
    try:
        camera_node = spawn_cam.spawn_camera(
            nuke,
            spawn_pos,
            camera,
            xpos + 120,
            ypos + 140,
            g.name(),
            ts,
            exclude_nodes=placed,
            label=label,
        )
    except Exception as e:
        print("WARNING: failed to spawn Camera2: %s" % str(e))

    msg_lines = ["MoGe-3 geometry ready.", "", "OBJ: %s" % obj_path_nk]
    glb_path = summary.get("glb")
    if glb_path:
        msg_lines.append("GLB: %s" % prerender.norm_slashes(glb_path))
    if readgeo_node is not None:
        try:
            msg_lines.append("ReadGeo: %s" % readgeo_node.fullName())
        except Exception:
            msg_lines.append("ReadGeo: spawned in node graph")
    if camera_node is not None and camera:
        try:
            msg_lines.append("Camera: %s" % camera_node.fullName())
        except Exception:
            msg_lines.append("Camera: spawned in node graph")
        msg_lines.append("Focal: %s mm" % _fmt(camera.get("focal")))
        win = camera.get("win_translate") or [0, 0]
        msg_lines.append("Window translate: %s %s" % (_fmt(win[0]), _fmt(win[1])))
        msg_lines.append("FOV: %s x %s deg" % (_fmt(fov_x_out), _fmt(fov_y_out)))
    else:
        msg_lines.append("Camera was not spawned.")
    msg_lines.append("")
    msg_lines.append("Wire ReadGeo and the Camera into your own Scene and ScanlineRender.")

    if _nuke_runner_launcher.should_show_success_popup(g):
        nuke.message("\n".join(msg_lines))


if __name__ == "__main__":
    main()
