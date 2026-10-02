# Purpose:
# - Buttons for Group inputs Nuke does not draw as pipes (input index 4 and later).
# - A button creates a labeled Dot in the parent graph and connects it to that Group input.
# - A second click selects the node already wired there. Existing wires are not replaced.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - `import nuke` stays inside the button callback so unit tests can import without Nuke.
# - Hidden means external Group input index >= 4 (the 5th input onward), from Input nodes
#   inside the Group. setInput uses that external index, not an internal Input node.

from __future__ import print_function

import traceback

import nuke_spawn_read_position_v1 as spawn_pos


# Nuke draws four input pipes on a node (indices 0-3).
HIDDEN_INPUT_MIN_INDEX = 4

# Place connector Dots to the left of the Group, one row lower per hidden input.
DOT_OFFSET_X = -160
DOT_STAGGER_Y = 40

CONNECT_TAB_KNOB = "connect_inputs_tab"
CONNECT_NOTE_KNOB = "connect_inputs_note"
KNOB_PREFIX = "create_hidden_input_"

CONNECT_NOTE_TEXT = (
    "Nuke draws pipes for the first 4 inputs only. "
    "Each button below adds a labeled Dot next to this node and connects that input. "
    "An existing connection is left as it is."
)

BUTTON_SCRIPT = (
    "import nuke_hidden_input_connectors_v1 as _hic\n"
    "_hic.on_create_connector_button()\n"
)


def artist_label_from_input_name(raw_name):
    """Turn an Input node name into an artist label. video_1 -> Video Input 1."""
    text = str(raw_name or "").strip()
    if not text:
        return "Input"
    parts = [part for part in text.replace("-", " ").replace("_", " ").split(" ") if part]
    if not parts:
        return "Input"
    words = []
    for part in parts:
        if part.isdigit():
            words.append(part)
        else:
            words.append(part[:1].upper() + part[1:].lower())
    if len(words) >= 2 and words[-1].isdigit():
        has_input = False
        for word in words[:-1]:
            if word.lower() == "input":
                has_input = True
                break
        if not has_input:
            words.insert(len(words) - 1, "Input")
    return " ".join(words)


def connector_button_label(input_name):
    return "Create " + artist_label_from_input_name(input_name)


def connector_dot_label(input_name):
    return artist_label_from_input_name(input_name).upper()


def connector_knob_name(index):
    return "%s%d" % (KNOB_PREFIX, int(index))


def index_from_connector_knob_name(name):
    text = str(name or "")
    if not text.startswith(KNOB_PREFIX):
        return None
    tail = text[len(KNOB_PREFIX):]
    if not tail.isdigit():
        return None
    return int(tail)


def connector_dot_position(group_x, group_y, input_index, hidden_start=None):
    """Return (x, y) for a connector Dot before occupancy nudging."""
    if hidden_start is None:
        hidden_start = HIDDEN_INPUT_MIN_INDEX
    slot = int(input_index) - int(hidden_start)
    if slot < 0:
        slot = 0
    return int(group_x) + DOT_OFFSET_X, int(group_y) + (slot * DOT_STAGGER_Y)


def already_connected_message(input_label, upstream_name):
    upstream = upstream_name or "another node"
    label = input_label or "This input"
    return (
        "%s is already connected to %s.\n\n"
        "Left that connection in place. "
        "Disconnect it first if you want a new connector Dot."
        % (label, upstream)
    )


def _node_class(node):
    try:
        return str(node.Class())
    except Exception:
        return ""


def _node_name(node):
    try:
        name = node.name()
    except Exception:
        name = ""
    name = str(name or "").strip()
    return name or "node"


def _is_dot(node):
    return _node_class(node) == "Dot"


def _knob(node, name):
    if node is None:
        return None
    try:
        knob = node.knob(name)
    except Exception:
        knob = None
    if knob is not None:
        return knob
    try:
        return node[name]
    except Exception:
        return None


def _set_knob_value(node, name, value):
    knob = _knob(node, name)
    if knob is None:
        return False
    try:
        knob.setValue(value)
        return True
    except Exception:
        return False


def _read_label(node):
    knob = _knob(node, "label")
    if knob is None:
        return ""
    try:
        return str(knob.value() or "")
    except Exception:
        return ""


def _input_number_or_none(node):
    knob = _knob(node, "number")
    if knob is None:
        return None
    try:
        return int(knob.value())
    except Exception:
        return None


def _node_xy(node):
    try:
        return int(node.xpos()), int(node.ypos())
    except Exception:
        return 0, 0


def _set_xy(node, x, y):
    try:
        node.setXYpos(int(x), int(y))
        return
    except Exception:
        pass
    _set_knob_value(node, "xpos", int(x))
    _set_knob_value(node, "ypos", int(y))


def input_specs_from_nodes(nodes):
    """
    Build [{index, name, label}, ...] from Input nodes.
    Uses the Input `number` knob. Inputs without one take the next free index,
    left to right, matching how Nuke orders Group pipes.
    """
    numbered = []
    unnumbered = []
    for node in nodes or []:
        name = _node_name(node)
        index = _input_number_or_none(node)
        xpos, _ypos = _node_xy(node)
        if index is None:
            unnumbered.append((xpos, name, node))
        else:
            numbered.append((int(index), name))

    mapping = {}
    for index, name in numbered:
        if name not in mapping:
            mapping[name] = int(index)

    used = set(mapping.values())
    unnumbered.sort(key=lambda item: (item[0], item[1]))
    next_idx = 0
    for _xpos, name, _node in unnumbered:
        if name in mapping:
            continue
        while next_idx in used:
            next_idx += 1
        mapping[name] = next_idx
        used.add(next_idx)
        next_idx += 1

    specs = []
    for name, index in mapping.items():
        specs.append(
            {
                "index": int(index),
                "name": name,
                "label": artist_label_from_input_name(name),
            }
        )
    specs.sort(key=lambda item: (item["index"], item["name"]))

    deduped = []
    seen = set()
    for spec in specs:
        index = int(spec["index"])
        if index in seen:
            continue
        seen.add(index)
        deduped.append(spec)
    return deduped


def hidden_input_specs(specs, hidden_start=None):
    if hidden_start is None:
        hidden_start = HIDDEN_INPUT_MIN_INDEX
    hidden = []
    for spec in specs or []:
        if int(spec["index"]) >= int(hidden_start):
            hidden.append(spec)
    return hidden


def _child_nodes(group):
    getter = getattr(group, "nodes", None)
    if not callable(getter):
        return None
    return list(getter())


def _inputs_via_begin(group, nuke_module):
    if nuke_module is None or group is None:
        return None
    begin = getattr(group, "begin", None)
    end = getattr(group, "end", None)
    if not callable(begin) or not callable(end):
        return None
    try:
        begin()
    except Exception:
        return None
    try:
        try:
            return list(nuke_module.allNodes("Input"))
        except TypeError:
            return [
                node
                for node in nuke_module.allNodes()
                if _node_class(node) == "Input"
            ]
    finally:
        try:
            end()
        except Exception:
            pass


def list_group_inputs(group, nuke_module=None):
    """Return input specs for a Group, from its internal Input nodes."""
    children = _child_nodes(group)
    if children is None:
        children = _inputs_via_begin(group, nuke_module)
    if not children:
        return []
    return input_specs_from_nodes(
        [node for node in children if _node_class(node) == "Input"]
    )


def _spec_for_index(specs, index):
    for spec in specs or []:
        if int(spec["index"]) == int(index):
            return spec
    return None


def is_fal_group(group):
    """True for fal toolbox Groups (helper_path and runner_path knobs)."""
    if group is None:
        return False
    try:
        helper = group.knob("helper_path")
        runner = group.knob("runner_path")
    except Exception:
        return False
    return helper is not None and runner is not None


def iter_fal_groups(nuke_module):
    """Yield fal Groups in the current script, including Groups nested inside Groups."""
    if nuke_module is None:
        return
    try:
        top = list(nuke_module.allNodes("Group"))
    except TypeError:
        top = [
            node
            for node in nuke_module.allNodes()
            if _node_class(node) == "Group"
        ]
    except Exception:
        return

    stack = list(top)
    seen = set()
    while stack:
        node = stack.pop()
        marker = id(node)
        if marker in seen:
            continue
        seen.add(marker)
        if is_fal_group(node):
            yield node
        try:
            children = node.nodes()
        except Exception:
            children = []
        for child in children:
            if _node_class(child) == "Group":
                stack.append(child)


def _set_flag(knob, nuke_module, flag_name):
    flag = getattr(nuke_module, flag_name, None)
    if flag is None or knob is None:
        return
    setter = getattr(knob, "setFlag", None)
    if not callable(setter):
        return
    try:
        setter(flag)
    except Exception:
        pass


def _set_tooltip(knob, text):
    setter = getattr(knob, "setTooltip", None)
    if not callable(setter):
        return
    try:
        setter(text)
    except Exception:
        pass


def _py_script_knob(nuke_module, name, label, script):
    factory = nuke_module.PyScript_Knob
    try:
        return factory(name, label, script)
    except TypeError:
        knob = factory(name, label)
        setter = getattr(knob, "setValue", None)
        if callable(setter):
            try:
                setter(script)
            except Exception:
                pass
        return knob


def _disconnect_inputs(node):
    """Drop wires on a brand-new Dot. createNode can auto-connect and cycle the Group."""
    try:
        count = int(node.inputs())
    except Exception:
        count = 1
    if count < 1:
        count = 1
    for idx in range(count):
        try:
            if node.input(idx) is None:
                continue
            node.setInput(idx, None)
        except Exception:
            break


def ensure_hidden_input_connector_knobs(group, nuke_module=None, input_pairs=None):
    """
    Add a Connect inputs tab with one button per hidden input.
    Groups with 4 or fewer inputs are left unchanged.
    Returns the button knob names (empty when there is nothing to add).
    `input_pairs` is an optional list of (index, name) or spec dicts, for tests.
    """
    if nuke_module is None:
        import nuke

        nuke_module = nuke
    if group is None:
        return []

    if input_pairs is None:
        specs = list_group_inputs(group, nuke_module=nuke_module)
    else:
        specs = _coerce_input_pairs(input_pairs)
    hidden = hidden_input_specs(specs)
    if not hidden:
        return []

    if group.knob(CONNECT_TAB_KNOB) is None:
        group.addKnob(nuke_module.Tab_Knob(CONNECT_TAB_KNOB, "Connect inputs"))
    if group.knob(CONNECT_NOTE_KNOB) is None:
        group.addKnob(
            nuke_module.Text_Knob(CONNECT_NOTE_KNOB, "", CONNECT_NOTE_TEXT)
        )

    names = []
    for spec in hidden:
        knob_name = connector_knob_name(spec["index"])
        names.append(knob_name)
        if group.knob(knob_name) is not None:
            continue
        button_label = connector_button_label(spec["name"])
        knob = _py_script_knob(nuke_module, knob_name, button_label, BUTTON_SCRIPT)
        _set_flag(knob, nuke_module, "STARTLINE")
        _set_tooltip(
            knob,
            "Add a Dot labeled %s next to this node and connect it to %s. "
            "Does not replace a wire that is already there."
            % (connector_dot_label(spec["name"]), spec["name"]),
        )
        group.addKnob(knob)
    return names


def _coerce_input_pairs(input_pairs):
    specs = []
    for item in input_pairs or []:
        if isinstance(item, dict):
            name = item.get("name") or ""
            index = int(item.get("index"))
        else:
            index = int(item[0])
            name = item[1]
        specs.append(
            {
                "index": index,
                "name": name,
                "label": artist_label_from_input_name(name),
            }
        )
    specs.sort(key=lambda spec: (spec["index"], spec["name"]))
    return specs


def _connected(group, index):
    try:
        return group.input(int(index))
    except Exception:
        return None


def _show_message(nuke_module, text):
    if nuke_module is None:
        return
    messenger = getattr(nuke_module, "message", None)
    if not callable(messenger):
        return
    try:
        messenger(text)
    except Exception:
        pass


def _delete_node(nuke_module, node):
    if nuke_module is None or node is None:
        return
    deleter = getattr(nuke_module, "delete", None)
    if not callable(deleter):
        return
    try:
        deleter(node)
    except Exception:
        pass


def _set_selected(node, selected):
    if _set_knob_value(node, "selected", True if selected else False):
        return
    setter = getattr(node, "setSelected", None)
    if callable(setter):
        try:
            setter(True if selected else False)
        except Exception:
            pass


def _context_nodes(nuke_module):
    if nuke_module is None:
        return []
    try:
        return list(nuke_module.allNodes())
    except Exception:
        return []


def _select_node(nuke_module, node):
    if node is None:
        return
    for other in _context_nodes(nuke_module):
        if other is node:
            continue
        _set_selected(other, False)
    _set_selected(node, True)


def _reveal_node(nuke_module, node, open_panel):
    _select_node(nuke_module, node)
    if not open_panel or nuke_module is None:
        return
    show = getattr(nuke_module, "show", None)
    if not callable(show):
        return
    try:
        show(node)
    except Exception:
        pass


def focus_parent_graph(nuke_module, group):
    """
    Pop DAG contexts until `group` is in the current graph.
    Connector Dots must be siblings of the Group, not nodes inside it.
    Stops if endGroup() does not change thisGroup(), so a stuck context
    cannot unwind the whole stack.
    """
    if nuke_module is None or group is None:
        return False
    for _step in range(64):
        found = False
        try:
            nodes = list(nuke_module.allNodes())
        except Exception:
            return False
        for node in nodes:
            if node is group:
                found = True
                break
        if found:
            return True
        end_group = getattr(nuke_module, "endGroup", None)
        if not callable(end_group):
            return False
        try:
            before = nuke_module.thisGroup()
        except Exception:
            before = None
        try:
            end_group()
        except Exception:
            return False
        try:
            after = nuke_module.thisGroup()
        except Exception:
            after = None
        if after is before:
            return False
    return False


def _create_dot_node(nuke_module):
    nodes_ns = getattr(nuke_module, "nodes", None)
    if nodes_ns is not None:
        factory = getattr(nodes_ns, "Dot", None)
        if callable(factory):
            return factory()
    create = getattr(nuke_module, "createNode", None)
    if callable(create):
        try:
            return create("Dot", inpanel=False)
        except TypeError:
            return create("Dot")
    raise Exception("Could not create a Dot node.")


def _result(action, index, node=None, label="", message=""):
    return {
        "action": action,
        "index": int(index),
        "node": node,
        "label": label or "",
        "message": message or "",
    }


def _leave_existing(nuke_module, group_index, upstream, artist):
    _reveal_node(nuke_module, upstream, open_panel=True)
    if _is_dot(upstream):
        return _result(
            "revealed",
            group_index,
            node=upstream,
            label=_read_label(upstream),
        )
    message = already_connected_message(artist, _node_name(upstream))
    _show_message(nuke_module, message)
    return _result(
        "left_existing",
        group_index,
        node=upstream,
        message=message,
    )


def create_or_reveal_input_connector(group, index, nuke_module, input_name=None):
    """
    Connect a labeled Dot to Group input `index`, or select what is already there.
    Never calls setInput when that input is already connected.
    """
    index = int(index)
    if nuke_module is None:
        import nuke

        nuke_module = nuke
    if index < HIDDEN_INPUT_MIN_INDEX:
        return _result("ignored", index)

    specs = list_group_inputs(group, nuke_module=nuke_module)
    spec = _spec_for_index(specs, index)
    if spec is None and not input_name:
        return _result("ignored", index)

    name = input_name or (spec["name"] if spec is not None else "")
    if not name:
        name = "input_%d" % (index + 1)
    artist = artist_label_from_input_name(name)
    dot_label = connector_dot_label(name)

    focus_parent_graph(nuke_module, group)

    upstream = _connected(group, index)
    if upstream is not None:
        return _leave_existing(nuke_module, index, upstream, artist)

    group_x, group_y = _node_xy(group)
    base_x, base_y = connector_dot_position(group_x, group_y, index)
    x, y = spawn_pos.resolve_spawn_xy(nuke_module, base_x, base_y)

    upstream = _connected(group, index)
    if upstream is not None:
        return _leave_existing(nuke_module, index, upstream, artist)

    dot = _create_dot_node(nuke_module)
    _disconnect_inputs(dot)
    _set_knob_value(dot, "label", dot_label)
    _set_xy(dot, x, y)

    upstream = _connected(group, index)
    if upstream is not None:
        _delete_node(nuke_module, dot)
        return _leave_existing(nuke_module, index, upstream, artist)

    try:
        group.setInput(index, dot)
    except Exception:
        _delete_node(nuke_module, dot)
        raise

    wired = _connected(group, index)
    if wired is not dot:
        _delete_node(nuke_module, dot)
        if wired is not None:
            return _leave_existing(nuke_module, index, wired, artist)
        raise Exception("Could not connect a Dot to %s." % artist)

    _reveal_node(nuke_module, dot, open_panel=False)
    return _result("created", index, node=dot, label=dot_label)


def on_create_connector_button(nuke_module=None):
    """PyScript_Knob callback. The knob name carries the Group input index."""
    if nuke_module is None:
        import nuke

        nuke_module = nuke
    try:
        group = nuke_module.thisNode()
        knob = nuke_module.thisKnob()
        knob_name = ""
        try:
            knob_name = knob.name()
        except Exception:
            knob_name = ""
        index = index_from_connector_knob_name(knob_name)
        if group is None or index is None:
            return _result("ignored", -1)
        return create_or_reveal_input_connector(
            group, index, nuke_module=nuke_module
        )
    except Exception as exc:
        import nuke_ui_error_v1 as ui_error

        ui_error.report_unexpected_ui_error(
            "create the input connector",
            exc,
            nuke_module=nuke_module,
        )
        return _result("failed", -1)


def upgrade_open_script_groups(nuke_module):
    """Add missing connector buttons to fal Groups already in the open script."""
    if nuke_module is None:
        return
    for group in iter_fal_groups(nuke_module):
        try:
            ensure_hidden_input_connector_knobs(group, nuke_module=nuke_module)
        except Exception:
            traceback.print_exc()


def install_script_load_hook(nuke_module):
    """Register a script-load callback. Returns the callback, or None."""
    if nuke_module is None:
        return None

    def _on_script_load():
        upgrade_open_script_groups(nuke_module)

    adder = getattr(nuke_module, "addOnScriptLoad", None)
    if not callable(adder):
        return None
    adder(_on_script_load)
    return _on_script_load
