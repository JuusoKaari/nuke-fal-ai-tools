# Purpose:
# - Shared Nuke (Python 2.7) helpers for reading prompt text from external inputs.
# - Supports a chain of Dot nodes between the consumer Group and an upstream Text node.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).

from __future__ import print_function

_PASSTHROUGH_CLASSES = frozenset(["Dot"])


def resolve_through_dot_chain(node):
    """
    Follow input(0) through Dot nodes and return the ultimate upstream node.
    Returns None when the chain ends at an unconnected Dot or on cycles.
    """
    seen = set()
    current = node
    while current is not None:
        try:
            node_id = current.name()
        except Exception:
            node_id = id(current)
        if node_id in seen:
            return current
        seen.add(node_id)

        try:
            cls = current.Class()
        except Exception:
            cls = ""
        if cls not in _PASSTHROUGH_CLASSES:
            return current

        try:
            current = current.input(0)
        except Exception:
            current = None

    return None


def get_text_message_from_node(node):
    """Return stripped Text node `message` value, or None if missing or empty."""
    if node is None:
        return None
    try:
        k = node.knob("message")
    except Exception:
        k = None
    if k is None:
        return None
    try:
        msg = (k.value() or "").strip()
    except Exception:
        msg = ""
    return msg or None


def get_prompt_from_input_or_group(
    nuke_module,
    group_node,
    prompt_knob="prompt",
    input_index=0,
    input_label="prompt_text",
):
    """
    Read prompt from `prompt_knob`, optionally overridden by an upstream Text node on `input_index`.
    Dot nodes between the Group and the Text node are ignored.
    """
    try:
        prompt = (group_node.knob(prompt_knob).value() or "").strip()
    except Exception:
        prompt = ""

    try:
        src = group_node.input(input_index)
    except Exception:
        src = None

    if src is None:
        return prompt

    resolved = resolve_through_dot_chain(src)
    if resolved is None:
        return prompt

    msg = get_text_message_from_node(resolved)
    if msg:
        return msg

    try:
        k = resolved.knob("message")
    except Exception:
        k = None
    if k is not None:
        return prompt

    try:
        cls = resolved.Class()
    except Exception:
        cls = "<unknown>"
    try:
        nuke_module.message(
            "Input %d (%s) is connected, but it's not a Text node (missing 'message' knob).\n\n"
            "Connected node class: %s\n\n"
            "Disconnect it or plug a Text node here (Dot nodes in between are OK). "
            "Execution cancelled." % (input_index, input_label, cls)
        )
    except Exception:
        pass
    raise Exception("prompt_input_not_text_node")
