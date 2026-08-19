# Purpose:
# - Build and migrate the in-group preview DAG for fal.ai Group nodes (runs inside Nuke / Python 2.7).
# - Nano Banana 2 ships a baked preview graph in its .nk; ensure_group_preview_graph() remains for
#   older nodes that lack a baked graph. Switch.which knobs use parent expressions, not Python updates.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - `import nuke` stays inside functions so unit tests can import without Nuke.

from __future__ import print_function

import nuke_prerender_v1 as prerender
from nuke_group_output_preview_config_v1 import (
    CLEAR_HISTORY_KNOB,
    EXTRACT_SELECTED_KNOB,
    MATCH_INPUT_RESOLUTION_KNOB,
    OUTPUT_COUNT_KNOB,
    OUTPUT_PATHS_REGISTRY_KNOB,
    ROI_AREA_KNOB,
    USE_ROI_KNOB,
    VIEWER_MODES,
    contactsheet_rows_cols,
    get_config_for_group,
)
from nuke_group_output_preview_nodes_v1 import (
    _gather_preview_connection_state,
    _get_or_create_node,
    _group_input_name_to_index,
    _has_baked_preview_graph,
    _safe_set_input,
    _safe_set_knob,
    _set_disable_expression,
    _set_switch_expression,
    _wire_switch_inputs,
)


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

    if group.knob(EXTRACT_SELECTED_KNOB) is None:
        k = nuke.PyScript_Knob(
            EXTRACT_SELECTED_KNOB,
            "Extract selected as Read",
            "import nuke_group_output_preview_v1 as _gop\n"
            "_gop.extract_selected_generation_ui()\n",
        )
        try:
            k.setFlag(nuke.STARTLINE)
        except Exception:
            pass
        try:
            k.setTooltip(
                "Create a Read node below this Group for the image at Preview index. "
                "Does not copy or move files."
            )
        except Exception:
            pass
        group.addKnob(k)

    if group.knob(CLEAR_HISTORY_KNOB) is None:
        k = nuke.PyScript_Knob(
            CLEAR_HISTORY_KNOB,
            "Clear generation history",
            "import nuke_group_output_preview_v1 as _gop\n"
            "_gop.clear_generated_outputs_ui()\n",
        )
        try:
            k.setTooltip(
                "Forget stored generations on this node. Files on disk are not deleted."
            )
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
