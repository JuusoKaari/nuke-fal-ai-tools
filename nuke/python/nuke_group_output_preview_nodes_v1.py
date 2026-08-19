# Purpose:
# - Low-level in-group node helpers for fal.ai output preview (find, create, inspect, wire).
# - Used by graph construction and runtime AI-input export. Call Nuke DAG helpers inside group.begin().
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - `import nuke` stays inside functions so unit tests can import without Nuke.

from __future__ import print_function

import nuke_prerender_v1 as prerender
from nuke_group_output_preview_config_v1 import PREVIEW_EXCLUDED_INTERNAL_INPUTS


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


def _node_has_input(node, index=0):
    if node is None:
        return False
    try:
        return node.input(int(index)) is not None
    except Exception:
        return False


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


def _set_disable_expression(node, expression):
    if node is None:
        return
    try:
        node.knob("disable").setExpression(expression)
    except Exception:
        pass
