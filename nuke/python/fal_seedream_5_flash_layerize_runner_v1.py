# Purpose:
# - Runner script for the Nuke Group node `Seedream_5_Flash_Layerize_v1` (executes inside Nuke / Python 2.7).
# - Accepts any upstream image input. A suitable Read uses its file at the current frame.
#   Anything else is pre-rendered to a temp still.
# - Calls `fal_seedream_5_flash_layerize_helper.py` to split the still into a full-frame base
#   plus cropped RGBA elements. Each crop has layer_meta.json with a bounding box in base pixels.
# - Root graph: one column per layer under the Group: Read, Reformat, Transform.
#   Reformat targets the connected plate (resize none, center off). Transform scales
#   and moves the crop. build_merge_stack defaults off. When on, a Merge2 chain
#   composites each layer over the base. spawn_reads_in_graph defaults on.
#   Each Execute replaces the layer set.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import json
import os
import struct
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_group_output_preview_v1 as preview
import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_spawn_read_position_v1 as spawn_pos


_IMAGE_SIZES = ("auto", "auto_1K", "auto_1.5K", "auto_2K")
_PROMPT_MODES = ("standard", "fast")
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".exr")


def _enum_knob_str(group_node, knob_name, choices, default):
    """Read an enumeration knob as a string. Nuke may return the label or an index."""
    try:
        k = group_node.knob(knob_name)
        v = k.value()
        if isinstance(v, int):
            if 0 <= v < len(choices):
                return choices[v]
            return default
        s = (str(v) or default).strip()
        return s if s in choices else default
    except Exception:
        return default


def _layer_output_path(layer_dir):
    """Pick the layer image. Skip layer.json, which is the run sidecar next to layer.png."""
    if os.path.isdir(layer_dir):
        for name in sorted(os.listdir(layer_dir)):
            lower = name.lower()
            if not lower.startswith("layer."):
                continue
            if not lower.endswith(_IMAGE_EXTS):
                continue
            path = os.path.join(layer_dir, name)
            if os.path.isfile(path):
                return path
    return os.path.join(layer_dir, "layer.png")


def _as_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _png_ihdr_size(path):
    """Return (width, height) from a PNG header, or None."""
    try:
        with open(path, "rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            handle.read(4)
            if handle.read(4) != b"IHDR":
                return None
            width, height = struct.unpack(">II", handle.read(8))
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def _image_size(path, meta):
    """Crop or base size. PNG header wins, then width/height stored in layer_meta.json."""
    measured = _png_ihdr_size(path)
    if measured:
        return measured
    if not isinstance(meta, dict):
        return None
    width = _as_int(meta.get("width"))
    height = _as_int(meta.get("height"))
    if width and height:
        return width, height
    return None


def absolute_box(meta):
    """Return (left, top, right, bottom) in base pixels, y down, or None for the base plate."""
    if not isinstance(meta, dict):
        return None
    box = meta.get("bounding_box")
    if not isinstance(box, dict):
        return None
    absolute = box.get("absolute")
    if not isinstance(absolute, (list, tuple)) or len(absolute) != 4:
        return None
    try:
        left, top, right, bottom = [int(v) for v in absolute]
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def layer_transform(in_w, in_h, base_w, base_h, crop_w, crop_h, box):
    """
    Place a layer after Reformat (resize none, center false).
    Crop pixels then sit on (0, 0) to (crop_w, crop_h), Nuke y up.
    box is (left, top, right, bottom) in base pixels, origin top-left, y down.
    None means the full-frame base layer.
    Returns (scale, translate_x, translate_y). Center is always (0, 0),
    so output = input * scale + translate.
    Scale is the one uniform Transform knob, taken from width.
    crop height can miss the box when the aspects differ.
    Returns None when a size is missing or not positive.
    """
    try:
        in_w = float(in_w)
        in_h = float(in_h)
        base_w = float(base_w)
        base_h = float(base_h)
    except (TypeError, ValueError):
        return None
    if in_w <= 0 or in_h <= 0 or base_w <= 0 or base_h <= 0:
        return None
    # Float division. Python 2.7 would truncate an int/int divide.
    sx = in_w / base_w
    sy = in_h / base_h
    if box is None:
        return (sx, 0.0, 0.0)
    try:
        left, top, right, bottom = [float(v) for v in box]
        crop_w = float(crop_w)
        crop_h = float(crop_h)
    except (TypeError, ValueError):
        return None
    if crop_w <= 0 or crop_h <= 0 or right <= left or bottom <= top:
        return None
    left_i = left * sx
    right_i = right * sx
    top_i = top * sy
    bottom_i = bottom * sy
    scale = (right_i - left_i) / crop_w
    # top_i is the mapped top. Translate uses the bottom because Nuke y is up.
    if top_i >= bottom_i:
        return None
    return (scale, left_i, in_h - bottom_i)


def _set_xy_knob(knob, x, y):
    if knob is None:
        return
    for index in (0, 1):
        try:
            knob.setExpression("", index)
        except Exception:
            pass
    knob.setValue(float(x), 0)
    knob.setValue(float(y), 1)


def _set_knob_value(node, knob_name, value):
    """Write a literal knob value. Clear any expression so Execute does not link it."""
    knob = node.knob(knob_name)
    if knob is None:
        raise RuntimeError("missing knob %s" % knob_name)
    try:
        knob.setExpression("")
    except Exception:
        pass
    knob.setValue(value)


def _configure_plate_reformat(node, in_w, in_h):
    """Reformat to the connected plate. Resize none, center off, origin bottom-left."""
    _set_knob_value(node, "type", "to box")
    _set_knob_value(node, "box_width", int(in_w))
    _set_knob_value(node, "box_height", int(in_h))
    _set_knob_value(node, "box_fixed", True)
    _set_knob_value(node, "resize", "none")
    _set_knob_value(node, "center", False)


def _configure_transform(node, scale, translate_x, translate_y):
    """Uniform scale and translate. Center stays (0, 0) or the placement is wrong."""
    center = node.knob("center")
    translate = node.knob("translate")
    scale_knob = node.knob("scale")
    if center is None or translate is None or scale_knob is None:
        raise RuntimeError("Transform missing center, translate, or scale")
    _set_xy_knob(center, 0, 0)
    _set_xy_knob(translate, translate_x, translate_y)
    try:
        scale_knob.setExpression("")
    except Exception:
        pass
    for index in (0, 1):
        try:
            scale_knob.setExpression("", index)
        except Exception:
            pass
    try:
        scale_knob.setValue(float(scale))
    except Exception:
        scale_knob.setValue(float(scale), 0)
        scale_knob.setValue(float(scale), 1)


def _input_plate_size(group_node):
    """Connected plate width and height at execute time, or None."""
    try:
        src = group_node.input(0)
        if not src:
            return None
        width = int(src.width())
        height = int(src.height())
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _place_node(nuke, node, x, y, placed):
    fx, fy = spawn_pos.resolve_spawn_xy(nuke, x, y, exclude_nodes=placed)
    node.setXpos(fx)
    node.setYpos(fy)
    placed.append(node)
    return node


def _name_node(node, name):
    try:
        node.setName(name, unique=True)
    except Exception:
        pass


def _label_node(node, text):
    try:
        node.knob("label").setValue(text)
    except Exception:
        pass


def _make_read(nuke, path_nk, title, name, x, y, placed):
    read = nuke.nodes.Read(file=path_nk)
    _name_node(read, name)
    _label_node(read, "%s\n%s" % (title, path_nk))
    return _place_node(nuke, read, x, y, placed)


def _knob_bool(group_node, knob_name, default):
    try:
        knob = group_node.knob(knob_name)
        if knob is None:
            return default
        return bool(knob.value())
    except Exception:
        return default


def _spawn_read_row(nuke, group, ts, layer_paths, xpos, ypos, placed):
    """Plain Reads in a row. Used when the plate or base size cannot be read."""
    for column, (layer_idx, path_nk, meta) in enumerate(layer_paths):
        _make_read(
            nuke,
            path_nk,
            _layer_title(layer_idx, meta),
            "%s_layer_%d_%s" % (group.name(), layer_idx, ts),
            xpos + (column * 200),
            ypos + 120,
            placed,
        )


def _find_base_layer(layer_paths):
    """First layer with no bounding box. That file is the fal base image."""
    for layer_idx, path_nk, meta in layer_paths:
        if absolute_box(meta) is None:
            return (layer_idx, path_nk, meta)
    return None


def _chain_placement(layer_idx, path_nk, meta, base_idx, in_w, in_h, base_w, base_h):
    if layer_idx == base_idx:
        return layer_transform(in_w, in_h, base_w, base_h, base_w, base_h, None)
    crop_size = _image_size(path_nk, meta)
    box = absolute_box(meta)
    if box is None or not crop_size:
        return None
    return layer_transform(
        in_w, in_h, base_w, base_h, crop_size[0], crop_size[1], box
    )


def _spawn_merge_chain(nuke, group, ts, layer_paths, transforms, base_idx, x, y, placed):
    """Merge2 over the base Transform, low z_index first. Not wrapped in a Group."""
    background = transforms[base_idx]
    ordered = []
    for layer_idx, _path, meta in layer_paths:
        if layer_idx == base_idx or layer_idx not in transforms:
            continue
        z_index = _as_int(meta.get("z_index")) if isinstance(meta, dict) else None
        if z_index is None:
            z_index = 0
        ordered.append((z_index, layer_idx, meta, transforms[layer_idx]))
    ordered.sort(key=lambda item: (item[0], item[1]))
    made = 0
    for step, (_z_index, layer_idx, meta, xf) in enumerate(ordered):
        try:
            merge = nuke.nodes.Merge2()
            merge.setInput(0, xf)
            merge.setInput(1, background)
            _set_knob_value(merge, "operation", "over")
            _set_knob_value(merge, "bbox", "B")
            _name_node(merge, "%s_over_%d_%s" % (group.name(), layer_idx, ts))
            _label_node(merge, _layer_title(layer_idx, meta))
            _place_node(nuke, merge, x, y + (step * 120), placed)
            background = merge
            made += 1
        except Exception:
            continue
    return made


def _spawn_layer_row(nuke, group, ts, layer_paths, xpos, ypos, build_merge):
    """
    One column per layer under the Group: Read, Reformat, Transform.
    Columns are 200px apart. When build_merge is on, also build the Merge2 chain.
    Returns how many merges were created.
    """
    placed = []
    plate = _input_plate_size(group)
    base = _find_base_layer(layer_paths)
    base_size = _image_size(base[1], base[2]) if base is not None else None
    if not plate or not base_size:
        _spawn_read_row(nuke, group, ts, layer_paths, xpos, ypos, placed)
        return 0

    in_w, in_h = plate
    base_w, base_h = base_size
    base_idx = base[0]
    transforms = {}
    for column, (layer_idx, path_nk, meta) in enumerate(layer_paths):
        x = xpos + (column * 200)
        title = _layer_title(layer_idx, meta)
        read = _make_read(
            nuke,
            path_nk,
            title,
            "%s_layer_%d_%s" % (group.name(), layer_idx, ts),
            x,
            ypos + 120,
            placed,
        )
        placement = _chain_placement(
            layer_idx, path_nk, meta, base_idx, in_w, in_h, base_w, base_h
        )
        if not placement:
            continue
        scale, translate_x, translate_y = placement
        try:
            reform = nuke.nodes.Reformat()
            reform.setInput(0, read)
            _configure_plate_reformat(reform, in_w, in_h)
            _name_node(reform, "%s_reformat_%d_%s" % (group.name(), layer_idx, ts))
            _label_node(reform, title)
            _place_node(nuke, reform, x, ypos + 240, placed)

            xf = nuke.nodes.Transform()
            xf.setInput(0, reform)
            _configure_transform(xf, scale, translate_x, translate_y)
            _name_node(xf, "%s_transform_%d_%s" % (group.name(), layer_idx, ts))
            _label_node(xf, title)
            _place_node(nuke, xf, x, ypos + 360, placed)
            transforms[layer_idx] = xf
        except Exception:
            continue

    if not build_merge or base_idx not in transforms:
        return 0
    return _spawn_merge_chain(
        nuke,
        group,
        ts,
        layer_paths,
        transforms,
        base_idx,
        xpos + (len(layer_paths) * 200),
        ypos + 360,
        placed,
    )


def _read_layer_meta(layer_dir):
    path = os.path.join(layer_dir, "layer_meta.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _layer_title(layer_idx, meta):
    name = meta.get("name") or ""
    try:
        name = name.strip()
    except Exception:
        name = ""
    z_index = meta.get("z_index")
    if z_index == 0 and not name:
        return "Base"
    if name:
        try:
            return "Layer %d: %s" % (layer_idx, name)
        except Exception:
            return "Layer %d" % layer_idx
    if z_index == 0:
        return "Base"
    return "Layer %d" % layer_idx


def main():
    import nuke  # imported inside for Nuke environment

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    frame = int(nuke.frame())
    src_node = g.input(0)
    if not src_node:
        nuke.message("Input 0 is not connected.")
        raise Exception("missing input 0")

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="seedream_5_flash_layerize",
        group_node=g,
    )

    try:
        image_path = prerender.prepare_still_input_path(
            nuke_module=nuke,
            src_node=src_node,
            frame=frame,
            run_dir=temp_dir,
            base_name="source",
        )
    except Exception as exc:
        nuke.message("Failed to prepare input image:\n%s" % str(exc))
        raise

    prompt = (g.knob("prompt").value() or "").strip()
    image_size = _enum_knob_str(g, "image_size", _IMAGE_SIZES, "auto")
    enhance_prompt_mode = _enum_knob_str(
        g, "enhance_prompt_mode", _PROMPT_MODES, "standard"
    )
    enable_safety_checker = bool(g.knob("enable_safety_checker").value())

    extra_args = [
        "--image",
        image_path,
        "--out-dir",
        out_dir,
        "--image-size",
        image_size,
        "--enhance-prompt-mode",
        enhance_prompt_mode,
        "--verbose",
    ]
    if prompt:
        extra_args += ["--prompt", prompt]
    if not enable_safety_checker:
        extra_args += ["--no-enable-safety-checker"]

    runner_util.run_group_helper(
        nuke, g, extra_args, "Seedream 5.0 Flash Layerize"
    )

    layer_indices = []
    for name in (os.listdir(out_dir) if os.path.isdir(out_dir) else []):
        if name.startswith("layer_"):
            try:
                layer_indices.append(int(name.split("_")[1]))
            except (ValueError, IndexError):
                pass
    layer_indices.sort()

    created = []
    layer_paths = []
    for layer_idx in layer_indices:
        layer_dir = os.path.join(out_dir, "layer_%d" % layer_idx)
        out_path = _layer_output_path(layer_dir)
        if not os.path.isfile(out_path):
            continue
        out_path_nk = prerender.norm_slashes(out_path)
        created.append(out_path_nk)
        layer_paths.append((layer_idx, out_path_nk, _read_layer_meta(layer_dir)))

    if not created:
        nuke.message("No layer output found. Check the helper script output.")
        raise Exception("no outputs")

    try:
        preview.wire_group_outputs(g, created)
    except Exception as exc:
        nuke.message("Failed to wire in-group preview outputs:\n%s" % str(exc))
        raise

    spawn_reads = _knob_bool(g, "spawn_reads_in_graph", True)
    # Ignored when spawn is off. Default off so Execute does not build a Merge chain.
    build_merge = _knob_bool(g, "build_merge_stack", False) if spawn_reads else False

    merges = 0
    if spawn_reads:
        xpos = int(g.xpos())
        ypos = int(g.ypos())
        nuke.root().begin()
        try:
            merges = _spawn_layer_row(
                nuke, g, ts, layer_paths, xpos, ypos, build_merge
            )
        finally:
            nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        if merges:
            summary = "%d layer(s), merge stack on." % len(created)
        else:
            summary = "%d layer(s)." % len(created)
        nuke.message(
            "Seedream 5.0 Flash Layerize: %s\n%s"
            % (summary, prerender.norm_slashes(out_dir))
        )


if __name__ == "__main__":
    main()
