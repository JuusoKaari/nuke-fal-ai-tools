# Purpose:
# - Runtime for in-group output preview: AI input prerender, generation history, generated reads, extract/clear, UI polish.
# - Accumulated outputs live on a hidden registry knob; Read nodes and switches grow as needed.
# - Optional ROI: image_a is cropped to roi_area on export.
# - Button callbacks (clear/extract) show a Nuke dialog on unexpected errors instead of failing silently.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - `import nuke` stays inside functions so unit tests can import without Nuke.

from __future__ import print_function

import os

import nuke_prerender_v1 as prerender
from nuke_group_output_preview_config_v1 import (
    OUTPUT_COUNT_KNOB,
    OUTPUT_PATHS_REGISTRY_KNOB,
    ROI_AREA_KNOB,
    USE_ROI_KNOB,
    _EXTRACT_READ_OFFSET_Y,
    _max_stored_outputs_for_config,
    _read_bool_knob,
    _read_preview_index,
    _read_roi_bbox,
    _read_viewer_mode,
    _set_viewer_mode,
    AiInputExportError,
    filter_existing_output_paths,
    generated_read_node_name,
    get_config_for_group,
    merge_output_paths,
    parse_output_paths_registry,
    preview_index_range_max,
    selected_output_path,
    serialize_output_paths_registry,
    validate_roi_bbox,
)
from nuke_group_output_preview_graph_v1 import (
    _ensure_generated_resolution_wiring,
    _ensure_group_knobs,
    ensure_group_preview_graph,
)
from nuke_group_output_preview_nodes_v1 import (
    _connected_preview_sources,
    _find_node_in_group_by_name,
    _gather_preview_connection_state,
    _get_or_create_node,
    _node_has_input,
    _preview_inputs_have_external_connection,
    _safe_set_knob,
)
from nuke_ui_error_v1 import report_unexpected_ui_error


def _ai_input_export_node(group, slot):
    """Return the in-group preview source node sent to fal for a 1-based slot."""
    return _find_node_in_group_by_name("preview_source_%02d" % int(slot))


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


def clear_generated_outputs(group):
    """Forget stored generations on this node. Files on disk are not deleted."""
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
    import nuke

    try:
        clear_generated_outputs(nuke.thisNode())
    except Exception as exc:
        report_unexpected_ui_error("clear generation history", exc)


def _spawn_root_read_for_path(group, path, index):
    """Create a root-level Read below the Group for one generated file."""
    import nuke
    import nuke_spawn_read_position_v1 as spawn_pos

    path_nk = prerender.norm_slashes(path)
    xpos = int(group.xpos())
    ypos = int(group.ypos())
    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(
            nuke, xpos, ypos + _EXTRACT_READ_OFFSET_Y
        )
        r = nuke.nodes.Read(file=path_nk)
        try:
            r.setName("%s_out_%02d" % (group.name(), int(index)), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("%s\n%s" % (group.name(), path_nk))
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
        return r
    finally:
        nuke.endGroup()


def extract_selected_generation(group):
    """Spawn a root Read for the Preview index image. Files are not copied or moved."""
    import nuke

    config = get_config_for_group(group)
    if config is None:
        nuke.message("This node does not support in-group generation history.")
        return None

    idx = _read_preview_index(group)
    path = selected_output_path(_read_output_paths_registry(group), idx)
    if not path:
        nuke.message(
            "No generated output is selected.\n"
            "Run Execute first, then set Preview index."
        )
        return None
    if not os.path.isfile(path):
        nuke.message("Selected generation file is missing:\n%s" % path)
        return None

    return _spawn_root_read_for_path(group, path, idx)


def extract_selected_generation_ui():
    """Knob callback entry point for extract_selected_generation."""
    import nuke

    try:
        extract_selected_generation(nuke.thisNode())
    except Exception as exc:
        report_unexpected_ui_error("extract the selected generation", exc)


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
