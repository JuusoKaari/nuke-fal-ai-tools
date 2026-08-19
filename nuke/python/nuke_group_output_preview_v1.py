# Purpose:
# - Compatibility wrapper for shared in-group output preview (runs inside Nuke / Python 2.7).
# - Keeps the public API stable while implementation is split into smaller modules:
#   - `nuke_group_output_preview_config_v1.py` (constants, tool config, pure helpers)
#   - `nuke_group_output_preview_nodes_v1.py` (find/create/inspect in-group nodes)
#   - `nuke_group_output_preview_graph_v1.py` (build/migrate preview DAG)
#   - `nuke_group_output_preview_runtime_v1.py` (AI input export, history, generated reads, extract/clear, UI)
# - Group knobs, runners, and unit tests continue to import this module.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Pure helper functions remain importable by unit tests without Nuke.

from __future__ import print_function

from nuke_group_output_preview_config_v1 import (
    VIEWER_MODES,
    OUTPUT_PATHS_REGISTRY_KNOB,
    OUTPUT_COUNT_KNOB,
    EXTRACT_SELECTED_KNOB,
    CLEAR_HISTORY_KNOB,
    MATCH_INPUT_RESOLUTION_KNOB,
    _EXTRACT_READ_OFFSET_Y,
    USE_ROI_KNOB,
    ROI_AREA_KNOB,
    TOOL_ID_KNOB,
    RUNNER_PATH_KNOB,
    PREVIEW_EXCLUDED_INTERNAL_INPUTS,
    DEFAULT_MAX_STORED_OUTPUTS,
    RUNNER_BASENAME_TO_TOOL_ID,
    TOOL_PREVIEW_CONFIG,
    AiInputExportError,
    viewer_mode_to_switch_index,
    contactsheet_rows_cols,
    preview_index_range_max,
    preview_index_labels,
    should_show_grid_mode,
    validate_roi_bbox,
    parse_output_paths_registry,
    serialize_output_paths_registry,
    merge_output_paths,
    generated_read_node_name,
    selected_output_path,
    filter_existing_output_paths,
    normalize_runner_basename,
    resolve_tool_id_from_runner_path,
    resolve_tool_id,
    get_config_for_group,
    _is_integer_like,
    _read_viewer_mode,
    _read_preview_index,
    _set_viewer_mode,
    _read_bool_knob,
    _read_roi_bbox,
    _max_stored_outputs_for_config,
)

from nuke_group_output_preview_nodes_v1 import (
    _group_external_input_source,
    _group_external_input_connected,
    _has_baked_preview_graph,
    _safe_set_input,
    _safe_knob_value,
    _safe_set_knob,
    _find_node_in_group_by_name,
    _find_preview_input_node,
    _preview_inputs_have_external_connection,
    _node_inside_group,
    _get_or_create_node,
    _group_input_name_to_index,
    _gather_preview_connection_state,
    _connected_preview_sources,
    _node_has_input,
    _set_switch_expression,
    _wire_switch_inputs,
    _set_disable_expression,
)

from nuke_group_output_preview_graph_v1 import (
    setup_preview_for_node,
    on_group_create,
    _ensure_group_knobs,
    _generated_preview_tail_node,
    _build_fallback_branch,
    _build_preview_source_switch,
    _update_preview_source_switches_in_group,
    _wire_contactsheet,
    _generated_format_reference_name,
    _apply_match_input_reformat_settings,
    _link_roi_rectangle_area,
    _ensure_generated_output_reformat,
    _ensure_generated_resolution_wiring,
    _apply_preview_switch_expressions,
    _update_viewer_mode_in_group,
    ensure_group_preview_graph,
)

from nuke_group_output_preview_runtime_v1 import (
    _update_generated_output_count_ui,
    _update_preview_index_range,
    _ensure_generated_read_nodes,
    _sync_generated_preview_wiring,
    _fail_ai_input_export,
    _validate_ai_export_node,
    _ai_input_export_node,
    _render_ai_input_still,
    prepare_ai_inputs,
    _read_output_paths_registry,
    _write_output_paths_registry,
    clear_generated_outputs,
    clear_generated_outputs_ui,
    _spawn_root_read_for_path,
    extract_selected_generation,
    extract_selected_generation_ui,
    wire_group_outputs,
    on_knob_changed_ui,
    on_knob_changed,
)
