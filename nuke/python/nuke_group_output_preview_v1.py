# Purpose:
# - Shared in-group output preview for fal.ai Group nodes (runs inside Nuke / Python 2.7).
# - Nano Banana 2 ships a baked preview graph in its .nk; this module wires outputs after Execute
#   and handles UI polish (preview_index disable in grid modes, generated output count).
# - Accumulated outputs are stored on a hidden registry knob; Read nodes and switches grow as needed.
# - Optional match_input_resolution reformats the selected generated preview to image_a size.
# - Optional ROI: image_a through ROI_rectangle for preview; crop on export; merge-back preview.
# - ensure_group_preview_graph() remains for migrating older nodes that lack a baked graph.
# - Preview config is keyed by stable fal_tool_id / runner_path, not the display name.
# - Switch.which knobs use parent expressions (e.g. parent.viewer_mode), not Python updates.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Pure helper functions at module top are importable by unit tests without Nuke.

from __future__ import print_function

import math
import os

import nuke_prerender_v1 as prerender

# ---------------------------------------------------------------------------
# Pure / testable helpers (no nuke import)
# ---------------------------------------------------------------------------

VIEWER_MODES = [
    "Input",
    "Generated",
    "Generated grid",
]

OUTPUT_PATHS_REGISTRY_KNOB = "generated_output_paths"
OUTPUT_COUNT_KNOB = "generated_output_count"
MATCH_INPUT_RESOLUTION_KNOB = "match_input_resolution"
USE_ROI_KNOB = "use_roi"
ROI_AREA_KNOB = "roi_area"
TOOL_ID_KNOB = "fal_tool_id"
RUNNER_PATH_KNOB = "runner_path"
PREVIEW_EXCLUDED_INTERNAL_INPUTS = frozenset(["prompt_text"])
DEFAULT_MAX_STORED_OUTPUTS = 128

# Maps runner script basename -> TOOL_PREVIEW_CONFIG key (stable across display renames).
RUNNER_BASENAME_TO_TOOL_ID = {
    "fal_nano_banana_2_generate_runner_v1.py": "Nano_Banana_2_Generate_v1",
}


class AiInputExportError(Exception):
    """Raised when in-group AI input prerender fails (dialog already shown)."""

TOOL_PREVIEW_CONFIG = {
    "Nano_Banana_2_Generate_v1": {
        "preview_inputs": ["image_a", "image_b"],
        "max_ai_inputs": 2,
        "max_outputs": 4,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": True,
        "supports_roi": True,
        "accumulate_outputs": True,
    },
}


def viewer_mode_to_switch_index(mode):
    """Map viewer_mode enum string to viewer_mode_switch input index (0-2)."""
    try:
        return VIEWER_MODES.index((mode or "").strip())
    except ValueError:
        return 0


def contactsheet_rows_cols(count):
    """Return stable (rows, cols) for a ContactSheet given item count."""
    count = max(1, int(count))
    if count == 1:
        return (1, 1)
    if count == 2:
        return (1, 2)
    cols = int(math.ceil(math.sqrt(count)))
    rows = int(math.ceil(float(count) / cols))
    return (rows, cols)


def preview_index_range_max(count):
    """Upper bound for preview_index slider so each output gets equal width."""
    count = max(1, int(count))
    return count + 0.999


def preview_index_labels(count, prefix="Output"):
    """Return string labels for preview_index enumeration."""
    count = max(0, int(count))
    return [str(i + 1) for i in range(count)]


def should_show_grid_mode(item_count):
    """Grid viewer modes are only useful when more than one item exists."""
    return int(item_count) > 1


def validate_roi_bbox(box):
    """Return (ok, error_message) for a roi_area bbox tuple (x, y, r, t)."""
    if box is None:
        return False, "roi_area knob is missing or unreadable."
    try:
        x, y, r, t = [float(v) for v in box]
    except Exception:
        return False, "roi_area values are invalid."
    if r <= x or t <= y:
        return (
            False,
            "roi_area is empty or invalid (right must be > left, top must be > bottom).",
        )
    return True, ""


def parse_output_paths_registry(raw):
    """Parse newline-separated output paths from the Group registry knob."""
    paths = []
    seen = set()
    for line in (raw or "").splitlines():
        p = prerender.norm_slashes((line or "").strip())
        if not p or p in seen:
            continue
        seen.add(p)
        paths.append(p)
    return paths


def serialize_output_paths_registry(paths):
    """Serialize output paths for storage on the Group node."""
    clean = []
    seen = set()
    for p in paths or []:
        p = prerender.norm_slashes((p or "").strip())
        if not p or p in seen:
            continue
        seen.add(p)
        clean.append(p)
    return "\n".join(clean)


def merge_output_paths(existing_paths, new_paths, max_stored=None):
    """Append new paths, optionally capping total stored count."""
    merged = list(existing_paths or [])
    seen = set(merged)
    for p in new_paths or []:
        p = prerender.norm_slashes((p or "").strip())
        if not p or p in seen:
            continue
        merged.append(p)
        seen.add(p)
    cap = int(max_stored) if max_stored is not None else DEFAULT_MAX_STORED_OUTPUTS
    if cap > 0 and len(merged) > cap:
        merged = merged[-cap:]
    return merged


def generated_read_node_name(index):
    """Stable in-group Read name for a 1-based generated output index."""
    index = int(index)
    if index < 100:
        return "generated_read_%02d" % index
    return "generated_read_%03d" % index


def filter_existing_output_paths(paths):
    """Keep only paths that still exist on disk."""
    result = []
    for p in paths or []:
        p = prerender.norm_slashes((p or "").strip())
        if p and os.path.isfile(p):
            result.append(p)
    return result


def normalize_runner_basename(runner_path):
    """Return the runner script filename from a knob path or placeholder."""
    path = prerender.norm_slashes((runner_path or "").strip())
    if not path:
        return ""
    return os.path.basename(path)


def resolve_tool_id_from_runner_path(runner_path):
    """Map runner_path knob value to a TOOL_PREVIEW_CONFIG key, or None."""
    return RUNNER_BASENAME_TO_TOOL_ID.get(normalize_runner_basename(runner_path))


def resolve_tool_id(tool_id_knob_value=None, runner_path=None, display_name=None):
    """
    Resolve the stable tool id for TOOL_PREVIEW_CONFIG lookup.
    Priority: fal_tool_id knob, runner_path basename, legacy display name.
    """
    tool_id = (tool_id_knob_value or "").strip()
    if tool_id:
        return tool_id

    tool_id = resolve_tool_id_from_runner_path(runner_path)
    if tool_id:
        return tool_id

    name = (display_name or "").strip()
    if name in TOOL_PREVIEW_CONFIG:
        return name
    base = name.rstrip("0123456789")
    if base in TOOL_PREVIEW_CONFIG:
        return base
    return None


def get_config_for_group(group):
    """Return TOOL_PREVIEW_CONFIG entry for a Group node, or None."""
    tool_id_knob_value = None
    runner_path = None
    display_name = None

    try:
        knob = group.knob(TOOL_ID_KNOB)
        if knob is not None:
            tool_id_knob_value = knob.value()
    except Exception:
        pass

    try:
        knob = group.knob(RUNNER_PATH_KNOB)
        if knob is not None:
            runner_path = knob.value()
    except Exception:
        pass

    try:
        display_name = group.name()
    except Exception:
        pass

    tool_id = resolve_tool_id(tool_id_knob_value, runner_path, display_name)
    if tool_id is None:
        return None
    return TOOL_PREVIEW_CONFIG.get(tool_id)


def _is_integer_like(value):
    try:
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
    except Exception:
        pass
    try:
        if isinstance(value, long):  # noqa: F821 - Python 2.7
            return True
    except NameError:
        pass
    return False


def _read_viewer_mode(group):
    """Read viewer_mode knob as a string label (handles enum index or label)."""
    try:
        v = group.knob("viewer_mode").value()
    except Exception:
        return "Input"
    if _is_integer_like(v):
        idx = int(v)
        if 0 <= idx < len(VIEWER_MODES):
            return VIEWER_MODES[idx]
        return "Input"
    s = (str(v) if v is not None else "").strip()
    if s in VIEWER_MODES:
        return s
    try:
        idx = int(s)
        if 0 <= idx < len(VIEWER_MODES):
            return VIEWER_MODES[idx]
    except Exception:
        pass
    return "Input"


def _read_preview_index(group):
    try:
        return max(1, int(group.knob("preview_index").value()))
    except Exception:
        return 1


def _set_viewer_mode(group, mode):
    """Set viewer_mode enum by label (falls back to index)."""
    try:
        group.knob("viewer_mode").setValue(mode)
        return
    except Exception:
        pass
    try:
        idx = VIEWER_MODES.index(mode)
        group.knob("viewer_mode").setValue(idx)
    except Exception:
        pass


def _gather_preview_connection_state(group, config):
    """
    Inspect Group external inputs. Must be called outside group.begin().
    Returns (name_to_idx, connected_input_names).
    """
    import nuke

    with prerender.group_scope(nuke, group):
        name_to_idx = _group_input_name_to_index(group)
        for slot, logical_name in enumerate(config.get("preview_inputs") or [], start=1):
            inside = _find_preview_input_node(logical_name, slot)
            if inside is None:
                continue
            try:
                name_to_idx[logical_name] = int(inside.knob("number").value())
            except Exception:
                name_to_idx.setdefault(logical_name, int(slot) - 1)

    connected = set()
    for input_name in config.get("preview_inputs") or []:
        ext_idx = name_to_idx.get(input_name)
        if ext_idx is None:
            continue
        if _group_external_input_connected(group, ext_idx):
            connected.add(input_name)
    return name_to_idx, connected


def _group_external_input_source(group, ext_idx):
    """Return upstream node on a Group input index (call outside group.begin())."""
    try:
        return group.input(int(ext_idx))
    except Exception:
        return None


def _group_external_input_connected(group, ext_idx):
    return _group_external_input_source(group, ext_idx) is not None


def _has_baked_preview_graph(group):
    """Return True when the Group already contains a baked preview graph."""
    import nuke

    with prerender.group_scope(nuke, group):
        return nuke.toNode("viewer_mode_switch") is not None


def setup_preview_for_node(group):
    """Build preview graph only when missing (migration for older nodes)."""
    config = get_config_for_group(group)
    if config is None:
        return False
    if _has_baked_preview_graph(group):
        return True
    ensure_group_preview_graph(group, config)
    return True


def on_group_create():
    """Legacy onCreate hook; baked graphs no longer need Python graph construction."""
    pass

def _safe_set_input(node, idx, src):
    if node is None:
        return
    try:
        node.setInput(int(idx), src)
    except Exception:
        pass


def _safe_knob_value(node, knob_name, default=None):
    try:
        k = node.knob(knob_name)
        if k is None:
            return default
        return k.value()
    except Exception:
        return default


def _safe_set_knob(node, knob_name, value):
    try:
        k = node.knob(knob_name)
        if k is not None:
            k.setValue(value)
    except Exception:
        pass


def _find_node_in_group_by_name(name):
    """
    Find a node by name in the current Group DAG context.
    Must be called while inside group.begin() on the target Group.
    """
    import nuke

    name = (name or "").strip()
    if not name:
        return None
    try:
        n = nuke.toNode(name)
        if n is not None:
            return n
    except Exception:
        pass
    for n in nuke.allNodes():
        try:
            if n.name() == name:
                return n
        except Exception:
            pass
    return None


def _find_preview_input_node(logical_name, slot):
    """
    Find an internal Input node for a configured preview input.
    Tolerates renamed nodes (e.g. image_a1) by falling back to Input.number.
    Must be called while inside group.begin() on the target Group.
    """
    import nuke

    inside = _find_node_in_group_by_name(logical_name)
    if inside is not None:
        return inside
    target_number = int(slot) - 1
    for n in nuke.allNodes("Input"):
        try:
            if n.name() in PREVIEW_EXCLUDED_INTERNAL_INPUTS:
                continue
            if int(n.knob("number").value()) == target_number:
                return n
        except Exception:
            pass
    return None


def _preview_inputs_have_external_connection(group, config, name_to_idx):
    """Return True when any configured preview input has an upstream pipe on this Group."""
    for input_name in config.get("preview_inputs") or []:
        ext_idx = name_to_idx.get(input_name)
        if ext_idx is None:
            continue
        if _group_external_input_connected(group, ext_idx):
            return True
    return False


def _node_inside_group(group, name, class_name=None):
    import nuke

    n = nuke.toNode(name)
    if n is not None:
        return n
    if class_name:
        try:
            return getattr(nuke.nodes, class_name)()
        except Exception:
            return None
    return None


def _get_or_create_node(group, name, class_name):
    import nuke

    n = nuke.toNode(name)
    if n is not None:
        return n
    try:
        n = nuke.createNode(class_name, inpanel=False)
        n.setName(name)
        return n
    except Exception:
        try:
            n = getattr(nuke.nodes, class_name)()
            n.setName(name)
            return n
        except Exception:
            return None


def _group_input_name_to_index(group):
    """Map Input node name -> external Group input index (uses Input.number when set)."""
    import nuke

    mapping = {}
    inputs = []
    for n in nuke.allNodes("Input"):
        try:
            inputs.append(n)
        except Exception:
            pass

    for n in inputs:
        if n.name() in PREVIEW_EXCLUDED_INTERNAL_INPUTS:
            continue
        try:
            num_k = n.knob("number")
            if num_k is not None:
                mapping[n.name()] = int(num_k.value())
        except Exception:
            pass

    unmapped = [
        n for n in inputs
        if n.name() not in mapping and n.name() not in PREVIEW_EXCLUDED_INTERNAL_INPUTS
    ]
    unmapped.sort(key=lambda n: int(n.xpos()))
    used = set(mapping.values())
    next_idx = 0
    for n in unmapped:
        while next_idx in used:
            next_idx += 1
        mapping[n.name()] = next_idx
        used.add(next_idx)
        next_idx += 1

    return mapping


def _connected_preview_sources(group, config, name_to_idx=None, connected_names=None):
    """
    Return list of (slot, input_name, input_node_inside_group, external_src).
    External connections are resolved outside group.begin(); internal nodes inside.
    """
    import nuke

    if name_to_idx is None or connected_names is None:
        name_to_idx, connected_names = _gather_preview_connection_state(group, config)
    preview_inputs = config.get("preview_inputs") or []
    result = []

    pending = []
    for slot, input_name in enumerate(preview_inputs, start=1):
        if input_name not in connected_names:
            continue
        ext_idx = name_to_idx.get(input_name)
        ext_src = _group_external_input_source(group, ext_idx)
        if ext_src is None:
            continue
        pending.append((slot, input_name, ext_src))

    if not pending:
        return result

    with prerender.group_scope(nuke, group):
        for slot, input_name, ext_src in pending:
            inside = _find_preview_input_node(input_name, slot)
            if inside is None:
                continue
            result.append((slot, input_name, inside, ext_src))
    return result


def _ensure_group_knobs(group, config):
    import nuke

    if group.knob("viewer_mode") is None:
        k = nuke.Enumeration_Knob("viewer_mode", "Viewer mode", VIEWER_MODES)
        try:
            k.setValue("Input")
        except Exception:
            pass
        group.addKnob(k)

    if group.knob("preview_index") is None:
        k = nuke.Int_Knob("preview_index", "Preview index")
        try:
            k.setValue(1)
        except Exception:
            pass
        group.addKnob(k)

    if group.knob("spawn_reads_in_graph") is None:
        k = nuke.Boolean_Knob("spawn_reads_in_graph", "Spawn reads in graph")
        try:
            k.setValue(False)
        except Exception:
            pass
        group.addKnob(k)

    if group.knob("has_generated_output") is None:
        k = nuke.Boolean_Knob("has_generated_output", "has generated output")
        try:
            k.setFlag(nuke.INVISIBLE)
        except Exception:
            pass
        try:
            k.setValue(False)
        except Exception:
            pass
        group.addKnob(k)

    if group.knob(OUTPUT_PATHS_REGISTRY_KNOB) is None:
        k = nuke.String_Knob(OUTPUT_PATHS_REGISTRY_KNOB, "generated output paths")
        try:
            k.setFlag(nuke.INVISIBLE)
        except Exception:
            pass
        group.addKnob(k)

    if group.knob(OUTPUT_COUNT_KNOB) is None:
        k = nuke.String_Knob(OUTPUT_COUNT_KNOB, "Generated outputs")
        try:
            k.setEnabled(False)
        except Exception:
            pass
        try:
            k.setValue("0")
        except Exception:
            pass
        group.addKnob(k)

    if group.knob(MATCH_INPUT_RESOLUTION_KNOB) is None:
        k = nuke.Boolean_Knob(MATCH_INPUT_RESOLUTION_KNOB, "Match input resolution")
        try:
            k.setValue(True)
        except Exception:
            pass
        group.addKnob(k)

    if config and config.get("supports_roi"):
        if group.knob(USE_ROI_KNOB) is None:
            k = nuke.Boolean_Knob(USE_ROI_KNOB, "Use ROI")
            try:
                k.setValue(False)
            except Exception:
                pass
            group.addKnob(k)
        if group.knob(ROI_AREA_KNOB) is None:
            k = nuke.BBox_Knob(ROI_AREA_KNOB, "Area")
            try:
                k.setValue(0, 0, 100, 100)
            except Exception:
                pass
            group.addKnob(k)


def _read_bool_knob(group, name, default=False):
    try:
        return bool(group.knob(name).value())
    except Exception:
        return default


def _generated_preview_tail_node(group, generated_switch, format_ref_name):
    """Return the node wired to viewer_mode_switch for single generated preview."""
    import nuke

    roi_switch = nuke.toNode("ROI_switch")
    if roi_switch is not None:
        _ensure_generated_output_reformat(group, generated_switch, format_ref_name)
        return roi_switch
    return _ensure_generated_output_reformat(
        group, generated_switch, format_ref_name
    )


def _build_fallback_branch(group):
    """Constant -> Reformat(root.format) -> preview_fallback NoOp."""
    import nuke

    const = _get_or_create_node(group, "preview_constant", "Constant")
    if const is not None:
        try:
            const["color"].setValue(0, 0, 0, 1)
        except Exception:
            pass

    reform = _get_or_create_node(group, "preview_reformat", "Reformat")
    if reform is not None:
        try:
            reform["type"].setValue("to box")
            reform["box"].setValue("root.format")
        except Exception:
            pass
        _safe_set_input(reform, 0, const)

    fallback = _get_or_create_node(group, "preview_fallback", "NoOp")
    _safe_set_input(fallback, 0, reform)
    return fallback


def _build_preview_source_switch(group, preview_source, fallback):
    """Switch between live input (1) and neutral fallback (0) for a preview source tap."""
    switch_name = preview_source.name() + "_sw"
    sw = _get_or_create_node(group, switch_name, "Switch")
    if sw is not None:
        _safe_set_input(sw, 0, fallback)
        _safe_set_input(sw, 1, preview_source)
        try:
            sw["which"].setValue(1)
        except Exception:
            pass
    return sw if sw is not None else preview_source


def _update_preview_source_switches_in_group(config, connected_names):
    """Set preview_source_NN_sw.which (call inside group.begin())."""
    import nuke

    preview_input_names = config.get("preview_inputs") or []
    max_ai = int(config.get("max_ai_inputs") or len(preview_input_names))

    for slot in range(1, max_ai + 1):
        sw_name = "preview_source_%02d_sw" % slot
        sw = nuke.toNode(sw_name)
        if sw is None:
            continue
        which = 0
        if slot - 1 < len(preview_input_names):
            input_name = preview_input_names[slot - 1]
            if input_name in connected_names:
                which = 1
        _safe_set_knob(sw, "which", which)


def _wire_contactsheet(group, name, source_nodes, count):
    import nuke

    sheet = _get_or_create_node(group, name, "ContactSheet")
    if sheet is None:
        return None
    rows, cols = contactsheet_rows_cols(count)
    _safe_set_knob(sheet, "rows", rows)
    _safe_set_knob(sheet, "columns", cols)
    for i in range(int(count)):
        _safe_set_input(sheet, i, source_nodes[i])
    for i in range(int(count), sheet.inputs()):
        _safe_set_input(sheet, i, None)
    return sheet


def _set_switch_expression(sw, expression):
    """Drive a Switch.which from a parent knob expression (Nuke-native, like dynamic_UI_example_group)."""
    if sw is None:
        return
    try:
        sw.knob("which").setExpression(expression)
    except Exception:
        pass


def _wire_switch_inputs(sw, sources):
    if sw is None:
        return
    for i, src in enumerate(sources):
        _safe_set_input(sw, i, src)
    for i in range(len(sources), sw.inputs()):
        _safe_set_input(sw, i, None)


def _generated_format_reference_name(group):
    """Return in-group node name used as image_a resolution reference."""
    return "preview_source_01"


def _apply_match_input_reformat_settings(reformat, format_ref_name):
    """Configure a Reformat to fit generated output to image_a dimensions."""
    if reformat is None:
        return
    _safe_set_knob(reformat, "type", "to box")
    _safe_set_knob(reformat, "box_fixed", True)
    _safe_set_knob(reformat, "resize", "fit")
    _safe_set_knob(reformat, "center", False)
    try:
        reformat["box_width"].setExpression("%s.width" % format_ref_name)
        reformat["box_height"].setExpression("%s.height" % format_ref_name)
    except Exception:
        _safe_set_knob(reformat, "box_width", "{%s.width}" % format_ref_name)
        _safe_set_knob(reformat, "box_height", "{%s.height}" % format_ref_name)


def _set_disable_expression(node, expression):
    if node is None:
        return
    try:
        node.knob("disable").setExpression(expression)
    except Exception:
        pass


def _link_roi_rectangle_area(group):
    """Drive ROI_rectangle.area from the Group roi_area BBox knob (per component)."""
    import nuke

    rect = nuke.toNode("ROI_rectangle")
    if rect is None:
        return
    area_knob = rect.knob("area")
    if area_knob is None:
        return
    for index, comp in enumerate(("x", "y", "r", "t")):
        expr = "parent.%s.%s" % (ROI_AREA_KNOB, comp)
        try:
            area_knob.setExpression(expr, index)
        except Exception:
            try:
                area_knob.setExpression(expr, comp)
            except Exception:
                pass


def _ensure_generated_output_reformat(group, generated_switch, format_ref_name):
    """Reformat after generated_switch; disabled when match_input_resolution is off."""
    reform = _get_or_create_node(group, "generated_output_reformat", "Reformat")
    _safe_set_input(reform, 0, generated_switch)
    _apply_match_input_reformat_settings(reform, format_ref_name)
    _set_disable_expression(
        reform,
        "1-parent.%s" % MATCH_INPUT_RESOLUTION_KNOB,
    )
    return reform


def _ensure_generated_resolution_wiring(group, read_nodes):
    """Wire generated_switch, contactsheet from reads, and single reformat branch."""
    import nuke

    format_ref_name = _generated_format_reference_name(group)
    generated_switch = nuke.toNode("generated_switch")
    if generated_switch is None:
        generated_switch = _get_or_create_node(group, "generated_switch", "Switch")
    _wire_switch_inputs(generated_switch, read_nodes)
    generated_single = _generated_preview_tail_node(
        group, generated_switch, format_ref_name
    )
    generated_contactsheet = _wire_contactsheet(
        group,
        "generated_contactsheet",
        read_nodes,
        len(read_nodes),
    )
    if generated_contactsheet is not None and len(read_nodes) <= 1:
        _safe_set_input(
            generated_contactsheet,
            0,
            read_nodes[0] if read_nodes else None,
        )
    viewer_mode_switch = nuke.toNode("viewer_mode_switch")
    if viewer_mode_switch is not None:
        ai_input_switch = nuke.toNode("ai_input_switch")
        branches = [
            ai_input_switch,
            generated_single if generated_single is not None else generated_switch,
            generated_contactsheet,
        ]
        for i, branch in enumerate(branches):
            _safe_set_input(viewer_mode_switch, i, branch)
    return generated_single


def _apply_preview_switch_expressions(group, config):
    """Link preview switches to Group knobs via expressions."""
    import nuke

    _set_switch_expression(nuke.toNode("viewer_mode_switch"), "parent.viewer_mode")
    _set_switch_expression(nuke.toNode("ai_input_switch"), "parent.preview_index - 1")
    _set_switch_expression(nuke.toNode("generated_switch"), "parent.preview_index - 1")
    _set_switch_expression(
        nuke.toNode("ROI_switch"),
        "parent.use_roi ? 1 : 0",
    )
    _set_disable_expression(
        nuke.toNode("generated_output_reformat"),
        "1-parent.%s" % MATCH_INPUT_RESOLUTION_KNOB,
    )
    _set_disable_expression(nuke.toNode("generated_reformat_to_ROI"), "!parent.use_roi")
    _set_disable_expression(
        nuke.toNode("generated_reposition_to_ROI"),
        "!parent.use_roi",
    )
    _set_disable_expression(nuke.toNode("merge_roi"), "!parent.use_roi")
    _set_disable_expression(nuke.toNode("ROI_rectangle"), "!parent.use_roi")
    _link_roi_rectangle_area(group)


def _update_viewer_mode_in_group(group, config, connected_names):
    """Refresh connection-dependent switches only (call inside group.begin())."""
    _update_preview_source_switches_in_group(config, connected_names)


def ensure_group_preview_graph(group, config):
    """
    Idempotent: create preview graph inside Group, add knobs, wire Output1.
    """
    import nuke

    if config is None:
        raise Exception("No preview config for group: %s" % group.name())

    name_to_idx, connected_names = _gather_preview_connection_state(group, config)

    with prerender.group_scope(nuke, group):
        _ensure_group_knobs(group, config)

        fallback = _build_fallback_branch(group)
        max_outputs = int(config.get("max_outputs") or 1)
        max_ai = int(config.get("max_ai_inputs") or len(config.get("preview_inputs") or []))

        preview_sources = []
        for slot in range(1, max_ai + 1):
            ps_name = "preview_source_%02d" % slot
            ps = _get_or_create_node(group, ps_name, "NoOp")
            preview_sources.append(ps)

        name_to_idx = _group_input_name_to_index(group)
        preview_input_names = config.get("preview_inputs") or []
        for slot, input_name in enumerate(preview_input_names[:max_ai], start=1):
            ps = preview_sources[slot - 1]
            inside_input = nuke.toNode(input_name)
            if inside_input is not None:
                _safe_set_input(ps, 0, inside_input)

        active_taps = []
        for slot, ps in enumerate(preview_sources, start=1):
            tap = _build_preview_source_switch(group, ps, fallback)
            active_taps.append(tap)

        ai_input_switch = _get_or_create_node(group, "ai_input_switch", "Switch")
        _wire_switch_inputs(ai_input_switch, active_taps)

        generated_reads = []
        for i in range(1, max_outputs + 1):
            rname = "generated_read_%02d" % i
            r = _get_or_create_node(group, rname, "Read")
            if r is not None:
                generated_reads.append(r)

        _ensure_generated_resolution_wiring(group, generated_reads)

        viewer_mode_switch = nuke.toNode("viewer_mode_switch")
        if viewer_mode_switch is None:
            viewer_mode_switch = _get_or_create_node(
                group, "viewer_mode_switch", "Switch"
            )

        output1 = nuke.toNode("Output1")
        _safe_set_input(output1, 0, viewer_mode_switch)

        viewer1 = nuke.toNode("Viewer1")
        if viewer1 is not None and viewer_mode_switch is not None:
            _safe_set_input(viewer1, 0, viewer_mode_switch)
            try:
                viewer1["input_number"].setValue(0)
            except Exception:
                pass

        _apply_preview_switch_expressions(group, config)
        _update_viewer_mode_in_group(group, config, connected_names)

    try:
        group.knob("tile_color").setFlag(0)
    except Exception:
        pass
    try:
        import nuke as _nuke_mod

        _nuke_mod.updateUI()
    except Exception:
        pass


def _read_roi_bbox(group):
    """Return (x, y, r, t) from the Group roi_area knob, or None."""
    try:
        k = group.knob(ROI_AREA_KNOB)
        if k is None:
            return None
        return (
            float(k.value(0)),
            float(k.value(1)),
            float(k.value(2)),
            float(k.value(3)),
        )
    except Exception:
        return None


def _node_has_input(node, index=0):
    if node is None:
        return False
    try:
        return node.input(int(index)) is not None
    except Exception:
        return False


def _fail_ai_input_export(message):
    """Show a Nuke dialog and abort AI input export."""
    try:
        import nuke

        nuke.message(message)
    except Exception:
        pass
    raise AiInputExportError(message)


def _validate_ai_export_node(export_node, input_name, slot):
    """Raise if the in-group export tap is missing or unwired."""
    node_name = "preview_source_%02d" % int(slot)
    if export_node is None:
        _fail_ai_input_export(
            "AI input export failed for %s.\n\n"
            "Missing in-group node '%s'.\n"
            "The preview graph inside the group may be broken; "
            "try re-inserting the node from the fal.ai menu."
            % (input_name, node_name)
        )
    if not _node_has_input(export_node):
        _fail_ai_input_export(
            "AI input export failed for %s.\n\n"
            "In-group node '%s' has no input.\n"
            "Wire %s to '%s' inside the group."
            % (input_name, node_name, input_name, node_name)
        )


def _ai_input_export_node(group, slot):
    """Return the in-group preview source node sent to fal for a 1-based slot."""
    return _find_node_in_group_by_name("preview_source_%02d" % int(slot))


def _render_ai_input_still(nuke, group, export_node, out_path, frame, slot, input_name):
    """Prerender one AI input; crops to roi_area on the fly when use_roi is enabled."""
    _validate_ai_export_node(export_node, input_name, slot)
    if int(slot) == 1 and _read_bool_knob(group, USE_ROI_KNOB):
        box = _read_roi_bbox(group)
        ok, err = validate_roi_bbox(box)
        if not ok:
            _fail_ai_input_export(
                "AI input export failed for %s.\n\n%s" % (input_name, err)
            )
        prerender.render_still_inside_group_with_crop(
            nuke, export_node, out_path, frame, box
        )
        return
    prerender.render_still_inside_group(nuke, group, export_node, out_path, frame)


def prepare_ai_inputs(group, config, frame, temp_dir):
    """
    Build PNG paths for fal upload under temp_dir (always prerendered for debugging).
    Renders from preview_source_NN inside the Group; image_a is cropped to roi_area
    on the fly when use_roi is enabled.
    Returns list of (1-based_index, path).
    """
    import nuke

    if config is None:
        return []

    prerender.ensure_dir(temp_dir)
    name_to_idx, connected_names = _gather_preview_connection_state(group, config)
    connected = _connected_preview_sources(
        group, config, name_to_idx, connected_names
    )
    if not connected:
        if _preview_inputs_have_external_connection(group, config, name_to_idx):
            _fail_ai_input_export(
                "AI input export failed for %s.\n\n"
                "Image input(s) are connected on this node, but in-group export "
                "nodes could not be resolved.\n"
                "Check that preview_source_01/02 are wired inside the group, "
                "or re-insert the node from the fal.ai menu.\n\n"
                "Temp folder:\n%s"
                % (group.name(), prerender.norm_slashes(temp_dir))
            )
        return []

    results = []
    expected = len(connected)
    with prerender.group_scope(nuke, group):
        for slot, input_name, inside_input, ext_src in connected:
            base_name = "ai_input_%d" % int(slot)
            out_path = os.path.join(temp_dir, "%s.png" % base_name)
            try:
                export_node = _ai_input_export_node(group, slot)
                if export_node is not None:
                    _render_ai_input_still(
                        nuke, group, export_node, out_path, frame, slot, input_name
                    )
                else:
                    if ext_src is None:
                        _fail_ai_input_export(
                            "AI input export failed for %s.\n\n"
                            "No upstream node is connected to the group input."
                            % input_name
                        )
                    prerender.render_still_from_node(
                        nuke, ext_src, out_path, frame
                    )
                prerender.require_rendered_file(
                    out_path,
                    "AI input export (%s)" % input_name,
                )
                results.append((slot, prerender.norm_slashes(out_path)))
            except AiInputExportError:
                raise
            except Exception as e:
                msg = "AI input export failed for %s.\n\n%s\n\nTemp folder:\n%s" % (
                    input_name,
                    str(e),
                    prerender.norm_slashes(temp_dir),
                )
                _fail_ai_input_export(msg)
        if len(results) != expected:
            _fail_ai_input_export(
                "AI input export incomplete.\n\n"
                "Expected %d image(s) in:\n%s\n"
                "but only exported %d."
                % (expected, prerender.norm_slashes(temp_dir), len(results))
            )

    return results


def _read_output_paths_registry(group):
    try:
        raw = group.knob(OUTPUT_PATHS_REGISTRY_KNOB).value()
    except Exception:
        raw = ""
    return parse_output_paths_registry(raw)


def _write_output_paths_registry(group, paths):
    serialized = serialize_output_paths_registry(paths)
    try:
        group.knob(OUTPUT_PATHS_REGISTRY_KNOB).setValue(serialized)
    except Exception:
        pass


def _max_stored_outputs_for_config(config):
    if config is None:
        return DEFAULT_MAX_STORED_OUTPUTS
    try:
        cap = int(config.get("max_stored_outputs") or DEFAULT_MAX_STORED_OUTPUTS)
    except Exception:
        cap = DEFAULT_MAX_STORED_OUTPUTS
    return max(1, cap)


def _update_generated_output_count_ui(group, count):
    count = max(0, int(count))
    try:
        group.knob(OUTPUT_COUNT_KNOB).setValue(str(count))
    except Exception:
        pass


def _update_preview_index_range(group, count):
    count = max(1, int(count))
    try:
        pk = group.knob("preview_index")
        if pk is not None:
            pk.setRange(1, preview_index_range_max(count))
    except Exception:
        pass


def _ensure_generated_read_nodes(group, count):
    """Ensure generated_read_01..NN exist inside the Group."""
    import nuke

    nodes = []
    for i in range(1, int(count) + 1):
        rname = generated_read_node_name(i)
        r = _get_or_create_node(group, rname, "Read")
        if r is not None:
            nodes.append(r)
    return nodes


def _sync_generated_preview_wiring(group, config, paths):
    """Wire generated reads/switch/contactsheet for the full stored path list."""
    import nuke

    paths = filter_existing_output_paths(paths)
    count = len(paths)

    with prerender.group_scope(nuke, group):
        read_nodes = _ensure_generated_read_nodes(group, max(count, 1))
        active_reads = []
        for i, r in enumerate(read_nodes, start=1):
            if i <= count:
                _safe_set_knob(r, "file", paths[i - 1])
                active_reads.append(r)
            else:
                _safe_set_knob(r, "file", "")

        generated_switch = nuke.toNode("generated_switch")
        if generated_switch is None:
            generated_switch = _get_or_create_node(group, "generated_switch", "Switch")

        _ensure_generated_resolution_wiring(group, active_reads)

    _update_generated_output_count_ui(group, count)
    _update_preview_index_range(group, max(count, 1))
    return paths, count


def clear_generated_outputs(group):
    """Clear accumulated generated outputs and reset preview wiring."""
    config = get_config_for_group(group)
    if config is None:
        return

    _write_output_paths_registry(group, [])
    _sync_generated_preview_wiring(group, config, [])

    try:
        group["has_generated_output"].setValue(False)
    except Exception:
        pass
    try:
        group["preview_index"].setValue(1)
    except Exception:
        pass
    _set_viewer_mode(group, "Input")


def clear_generated_outputs_ui():
    """Knob callback entry point for clear_generated_outputs."""
    import traceback

    import nuke

    try:
        clear_generated_outputs(nuke.thisNode())
    except Exception:
        traceback.print_exc()


def wire_group_outputs(group, paths, preview_index=None, append=None):
    """Update internal generated reads and switch viewer to Generated mode."""
    import nuke

    config = get_config_for_group(group)
    if config is None:
        return

    paths = [prerender.norm_slashes(p) for p in (paths or []) if p]
    if not paths:
        return

    if append is None:
        append = bool(config.get("accumulate_outputs"))

    with prerender.group_scope(nuke, group):
        viewer_missing = nuke.toNode("viewer_mode_switch") is None

    if viewer_missing:
        ensure_group_preview_graph(group, config)

    _ensure_group_knobs(group, config)

    existing = _read_output_paths_registry(group) if append else []
    merged = merge_output_paths(
        existing,
        paths,
        max_stored=_max_stored_outputs_for_config(config),
    )
    _write_output_paths_registry(group, merged)
    stored_paths, count = _sync_generated_preview_wiring(group, config, merged)

    if not stored_paths:
        return

    try:
        group["has_generated_output"].setValue(True)
    except Exception:
        pass
    _set_viewer_mode(group, "Generated")

    if preview_index is None:
        if append:
            preview_index = max(1, count - len(paths) + 1)
        else:
            preview_index = 1
    try:
        idx = max(1, min(int(preview_index), count))
        group["preview_index"].setValue(idx)
    except Exception:
        pass


def on_knob_changed_ui():
    """Entry point for Group knobChanged callback (UI polish only)."""
    import traceback

    import nuke

    try:
        g = nuke.thisNode()
        k = nuke.thisKnob()
        if k is None:
            return
        if k.name() not in (
            "viewer_mode",
            "preview_index",
            USE_ROI_KNOB,
        ):
            return

        if get_config_for_group(g) is None:
            return

        mode = _read_viewer_mode(g)
        is_grid = mode == "Generated grid"
        pk = g.knob("preview_index")
        if pk is not None:
            try:
                pk.setEnabled(not is_grid)
            except Exception:
                try:
                    pk.setVisible(not is_grid)
                except Exception:
                    pass

        use_roi = _read_bool_knob(g, USE_ROI_KNOB)
        area_k = g.knob(ROI_AREA_KNOB)
        if area_k is not None:
            try:
                area_k.setEnabled(use_roi)
            except Exception:
                pass
    except Exception:
        traceback.print_exc()


def on_knob_changed():
    """Backward-compatible alias."""
    on_knob_changed_ui()
