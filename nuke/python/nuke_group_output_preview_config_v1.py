# Purpose:
# - Shared constants, tool preview config, and pure helpers for in-group output preview.
# - Preview kinds (editor / layers / filter) control ROI knobs, history knobs, and viewer modes.
# - No Nuke import: unit tests can load this module (and the wrapper) without Nuke.
# - Tool lookup is keyed by stable fal_tool_id / runner_path, not the display name.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).

from __future__ import print_function

import math
import os

import nuke_prerender_v1 as prerender

VIEWER_MODES = [
    "Input",
    "Generated",
    "Generated grid",
]

PREVIEW_KIND_EDITOR = "editor"
PREVIEW_KIND_LAYERS = "layers"
PREVIEW_KIND_FILTER = "filter"
PREVIEW_KINDS = (PREVIEW_KIND_EDITOR, PREVIEW_KIND_LAYERS, PREVIEW_KIND_FILTER)
FILTER_VIEWER_MODES = [
    "Input",
    "Generated",
]

OUTPUT_PATHS_REGISTRY_KNOB = "generated_output_paths"
OUTPUT_COUNT_KNOB = "generated_output_count"
EXTRACT_SELECTED_KNOB = "extract_selected_generation"
CLEAR_HISTORY_KNOB = "clear_generated_outputs"
MATCH_INPUT_RESOLUTION_KNOB = "match_input_resolution"
_EXTRACT_READ_OFFSET_Y = 140
USE_ROI_KNOB = "use_roi"
ROI_AREA_KNOB = "roi_area"
TOOL_ID_KNOB = "fal_tool_id"
RUNNER_PATH_KNOB = "runner_path"
PREVIEW_EXCLUDED_INTERNAL_INPUTS = frozenset(["prompt_text"])
DEFAULT_MAX_STORED_OUTPUTS = 128

# Maps runner script basename -> TOOL_PREVIEW_CONFIG key (stable across display renames).
RUNNER_BASENAME_TO_TOOL_ID = {
    "fal_nano_banana_2_generate_runner_v1.py": "Nano_Banana_2_Generate_v1",
    "fal_gpt_image_2_edit_runner_v1.py": "GPT_Image_2_Edit_v1",
    "fal_qwen_image_max_edit_runner_v1.py": "Qwen_Image_Max_Edit_v1",
    "fal_seedream_5_pro_edit_runner_v1.py": "Seedream_5_Pro_Edit_v1",
    "fal_qwen_image_inpaint_runner_v1.py": "Qwen_Image_Edit_Inpaint_v1",
    "fal_hunyuan_world_runner_v1.py": "Hunyuan_World_v1",
    "fal_qwen_image_layered_runner_v1.py": "Qwen_Image_Layered_v1",
    "fal_birefnet_v2_still_runner_v1.py": "BiRefNet_v2_Still_v1",
    "fal_depth_anything_v2_runner_v1.py": "Depth_Anything_v2",
    "fal_finegrain_eraser_runner_v1.py": "Finegrain_Eraser_v1",
    "fal_topaz_upscale_image_precision_runner_v1.py": "Topaz_Upscale_Image_Precision_v1",
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
    "GPT_Image_2_Edit_v1": {
        "preview_kind": PREVIEW_KIND_EDITOR,
        "preview_inputs": ["ref_image_a", "ref_image_b"],
        "max_ai_inputs": 2,
        "max_outputs": 4,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": True,
        "supports_roi": True,
        "accumulate_outputs": True,
    },
    "Qwen_Image_Max_Edit_v1": {
        "preview_kind": PREVIEW_KIND_EDITOR,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 6,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": True,
        "supports_roi": False,
        "accumulate_outputs": True,
    },
    "Seedream_5_Pro_Edit_v1": {
        "preview_kind": PREVIEW_KIND_EDITOR,
        "preview_inputs": ["image_1"],
        "max_ai_inputs": 1,
        "max_outputs": 6,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": True,
        "supports_roi": False,
        "accumulate_outputs": True,
    },
    "Qwen_Image_Edit_Inpaint_v1": {
        "preview_kind": PREVIEW_KIND_EDITOR,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 4,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": True,
        "supports_roi": False,
        "accumulate_outputs": True,
    },
    "Hunyuan_World_v1": {
        "preview_kind": PREVIEW_KIND_EDITOR,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 1,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": False,
        "supports_roi": False,
        "accumulate_outputs": True,
        "viewer_modes": ["Input", "Generated"],
    },
    "Qwen_Image_Layered_v1": {
        "preview_kind": PREVIEW_KIND_LAYERS,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 10,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": True,
        "supports_roi": False,
        "accumulate_outputs": False,
    },
    "BiRefNet_v2_Still_v1": {
        "preview_kind": PREVIEW_KIND_FILTER,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 1,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": False,
        "supports_roi": False,
        "accumulate_outputs": False,
        "viewer_modes": ["Input", "Generated"],
    },
    "Depth_Anything_v2": {
        "preview_kind": PREVIEW_KIND_FILTER,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 1,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": False,
        "supports_roi": False,
        "accumulate_outputs": False,
        "viewer_modes": ["Input", "Generated"],
    },
    "Finegrain_Eraser_v1": {
        "preview_kind": PREVIEW_KIND_FILTER,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 1,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": False,
        "supports_roi": False,
        "accumulate_outputs": False,
        "viewer_modes": ["Input", "Generated"],
    },
    "Topaz_Upscale_Image_Precision_v1": {
        "preview_kind": PREVIEW_KIND_FILTER,
        "preview_inputs": ["source_image"],
        "max_ai_inputs": 1,
        "max_outputs": 1,
        "max_stored_outputs": DEFAULT_MAX_STORED_OUTPUTS,
        "supports_ai_input_grid": False,
        "supports_generated_grid": False,
        "supports_roi": False,
        "accumulate_outputs": False,
        "viewer_modes": ["Input", "Generated"],
    },
}


def preview_kind_for_config(config):
    """Return preview_kind; omitted or unknown values default to editor."""
    if not config:
        return PREVIEW_KIND_EDITOR
    kind = (config.get("preview_kind") or PREVIEW_KIND_EDITOR)
    try:
        kind = str(kind).strip().lower()
    except Exception:
        return PREVIEW_KIND_EDITOR
    if kind not in PREVIEW_KINDS:
        return PREVIEW_KIND_EDITOR
    return kind


def config_supports_roi(config):
    """ROI is opt-in. Omitted supports_roi is false."""
    if not config:
        return False
    return bool(config.get("supports_roi"))


def wants_roi_knobs(config):
    """ROI knobs only for editor tools that set supports_roi. Filter and layers never get ROI."""
    if preview_kind_for_config(config) in (PREVIEW_KIND_FILTER, PREVIEW_KIND_LAYERS):
        return False
    return config_supports_roi(config)


def wants_history_knobs(config):
    """Filter preview skips preview_index, extract, clear, and the generated-path registry."""
    return preview_kind_for_config(config) != PREVIEW_KIND_FILTER


def viewer_modes_for_config(config):
    """Per-tool viewer_modes, else Input+Generated when grid is off, else the global editor list."""
    if config is not None:
        custom = config.get("viewer_modes")
        if custom:
            return list(custom)
        if preview_kind_for_config(config) == PREVIEW_KIND_FILTER:
            return list(FILTER_VIEWER_MODES)
        if config.get("supports_generated_grid") is False:
            return list(FILTER_VIEWER_MODES)
    return list(VIEWER_MODES)


def spawn_reads_in_graph_default(config):
    """Layers spawn root Reads by default; editors and filters do not."""
    return preview_kind_for_config(config) == PREVIEW_KIND_LAYERS


def requested_preview_knob_names(config):
    """Knob names _ensure_group_knobs would add for this config."""
    names = [
        "viewer_mode",
        "spawn_reads_in_graph",
        "has_generated_output",
        MATCH_INPUT_RESOLUTION_KNOB,
        OUTPUT_COUNT_KNOB,
    ]
    if wants_history_knobs(config):
        names.extend(
            [
                "preview_index",
                OUTPUT_PATHS_REGISTRY_KNOB,
                EXTRACT_SELECTED_KNOB,
                CLEAR_HISTORY_KNOB,
            ]
        )
    if wants_roi_knobs(config):
        names.extend([USE_ROI_KNOB, ROI_AREA_KNOB])
    return names


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


def selected_output_path(paths, preview_index):
    """Return the path at 1-based preview_index, or None if missing / out of range."""
    items = list(paths or [])
    if not items:
        return None
    try:
        idx = int(preview_index)
    except Exception:
        return None
    if idx < 1 or idx > len(items):
        return None
    path = prerender.norm_slashes((items[idx - 1] or "").strip())
    if not path:
        return None
    return path


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


def _read_bool_knob(group, name, default=False):
    try:
        return bool(group.knob(name).value())
    except Exception:
        return default


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


def _max_stored_outputs_for_config(config):
    if config is None:
        return DEFAULT_MAX_STORED_OUTPUTS
    try:
        cap = int(config.get("max_stored_outputs") or DEFAULT_MAX_STORED_OUTPUTS)
    except Exception:
        cap = DEFAULT_MAX_STORED_OUTPUTS
    return max(1, cap)
