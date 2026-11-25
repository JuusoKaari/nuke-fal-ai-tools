# Purpose:
# - Nuke / Python 2.7 helper to spawn a Camera2 from focal length and window translate.
# - Used by the MoGe-3 runner. The mesh is already in camera space, so the camera
#   stays at the origin and looks down -Z.

from __future__ import print_function

_CAMERA_CLASSES = ("Camera2", "Camera")


def _set_knob_value(node, knob_name, value):
    k = node.knob(knob_name)
    if k is None:
        return
    try:
        k.setValue(value)
    except Exception:
        pass


def _set_xy(node, knob_name, pair):
    k = node.knob(knob_name)
    if k is None or not pair or len(pair) < 2:
        return
    try:
        k.setValue(float(pair[0]), 0)
        k.setValue(float(pair[1]), 1)
    except Exception:
        pass


def create_camera(nuke_module, camera):
    """
    Create a Camera2 (fallback Camera) and apply the helper's camera dict.
    camera keys: focal, haperture, vaperture, win_translate, near, far.
    """
    if not isinstance(camera, dict):
        raise Exception("missing camera settings")
    last_err = None
    node = None
    for class_name in _CAMERA_CLASSES:
        maker = getattr(nuke_module.nodes, class_name, None)
        if maker is None:
            continue
        try:
            node = maker()
            break
        except Exception as e:
            last_err = e
    if node is None:
        if last_err is not None:
            raise Exception("failed to create Camera: %s" % str(last_err))
        raise Exception("Camera2/Camera node class not available in this Nuke build")

    _set_knob_value(node, "focal", float(camera.get("focal")))
    _set_knob_value(node, "haperture", float(camera.get("haperture")))
    _set_knob_value(node, "vaperture", float(camera.get("vaperture")))
    _set_knob_value(node, "near", float(camera.get("near")))
    _set_knob_value(node, "far", float(camera.get("far")))
    _set_xy(node, "win_translate", camera.get("win_translate"))
    _set_knob_value(node, "read_from_file", False)
    return node


def spawn_camera(
    nuke_module,
    spawn_pos_module,
    camera,
    base_x,
    base_y,
    name_prefix,
    timestamp,
    exclude_nodes=None,
    label=None,
):
    """Spawn Camera2 at base_x, base_y. Returns the node, or None when settings are missing."""
    if not isinstance(camera, dict) or camera.get("focal") is None:
        return None

    nuke_module.root().begin()
    try:
        fx, fy = spawn_pos_module.resolve_spawn_xy(
            nuke_module, int(base_x), int(base_y), exclude_nodes=exclude_nodes
        )
        node = create_camera(nuke_module, camera)
        try:
            node.setName("%s_%s_cam" % (name_prefix, timestamp), unique=True)
        except Exception:
            pass
        if label:
            try:
                node.knob("label").setValue(label)
            except Exception:
                pass
        node.setXpos(fx)
        node.setYpos(fy)
        return node
    finally:
        nuke_module.endGroup()
