# Purpose:
# - Nuke / Python 2.7 helpers to spawn ReadGeo2 (fallback ReadGeo) nodes and optional texture wiring.
# - Used by fal Hunyuan 3D image-to-3D runner after OBJ/texture files are downloaded.
#
# Nuke 11 notes:
# - UI label is "ReadGeo"; node Class() is typically ReadGeo2 (see Foundry ReadGeo reference).
# - Pipe a Read node's output directly into the ReadGeo img input for projection/texturing.

from __future__ import print_function

_READGEO_CLASSES = ("ReadGeo2", "ReadGeo")


def _set_knob_value(node, knob_name, value):
    k = node.knob(knob_name)
    if k is None:
        return
    try:
        k.setValue(value)
    except Exception:
        pass


def _input_index(node, input_name, fallback):
    try:
        return int(node.inputIndex(input_name))
    except Exception:
        return int(fallback)


def create_readgeo(nuke_module, file_path):
    """
    Create a ReadGeo2/ReadGeo node pointing at file_path (OBJ, FBX, ABC, etc.).
    Returns the node or raises Exception if no reader class exists.
    """
    path = (file_path or "").strip()
    if not path:
        raise Exception("empty file path for ReadGeo")

    last_err = None
    for class_name in _READGEO_CLASSES:
        maker = getattr(nuke_module.nodes, class_name, None)
        if maker is None:
            continue
        try:
            geo = maker()
            _set_knob_value(geo, "file", path)
            if path.lower().endswith(".obj"):
                _set_knob_value(geo, "update_mode", "all")
                _set_knob_value(geo, "read_texture_w_coord", True)
            _set_knob_value(geo, "display", "textured")
            _set_knob_value(geo, "render_mode", "textured")
            return geo
        except Exception as e:
            last_err = e

    if last_err is not None:
        raise Exception("failed to create ReadGeo: %s" % str(last_err))
    raise Exception("ReadGeo2/ReadGeo node class not available in this Nuke build")


def attach_texture_to_readgeo(geo_node, texture_node):
    """Wire texture Read directly to ReadGeo img input."""
    if geo_node is None or texture_node is None:
        return False
    try:
        img_idx = _input_index(geo_node, "img", 0)
        geo_node.setInput(img_idx, texture_node)
        return True
    except Exception:
        return False


def spawn_readgeo_obj(
    nuke_module,
    spawn_pos_module,
    obj_path_nk,
    base_x,
    base_y,
    name_prefix,
    timestamp,
    exclude_nodes=None,
    texture_node=None,
    label=None,
    y_offset=280,
):
    """
    Spawn ReadGeo2 for an OBJ path; optionally connect a texture Read to the img input.
    Returns the ReadGeo node, or None.
    """
    if not obj_path_nk:
        return None

    nuke_module.root().begin()
    try:
        fx, fy = spawn_pos_module.resolve_spawn_xy(
            nuke_module, int(base_x), int(base_y) + int(y_offset), exclude_nodes=exclude_nodes
        )
        geo = create_readgeo(nuke_module, obj_path_nk)
        try:
            geo.setName("%s_%s_geo" % (name_prefix, timestamp), unique=True)
        except Exception:
            pass
        if label:
            try:
                geo.knob("label").setValue("%s\n%s" % (label, obj_path_nk))
            except Exception:
                pass
        geo.setXpos(fx)
        geo.setYpos(fy)

        if texture_node is not None:
            attach_texture_to_readgeo(geo, texture_node)

        return geo
    finally:
        nuke_module.endGroup()
