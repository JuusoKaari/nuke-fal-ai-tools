# Purpose:
# - Runner script for the Nuke Group node `OpenRouter_Generate_Text_v1` (executes inside Nuke / Python 2.7).
# - Reads LLM settings from the Group knobs; optionally overrides prompt from Input 0 when a Text node
#   (`message` knob) is connected, including through Dot nodes. Calls the external Python 3 helper and
#   spawns a Text node with the response.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_prompt_input_v1 as prompt_input
import nuke_spawn_read_position_v1 as spawn_pos


def _parse_helper_summary(stdout_lines):
    for line in reversed(stdout_lines):
        line = (line or "").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("ok"):
                return obj
        except Exception:
            pass
    return None


def _format_usage_popup(usage):
    if not isinstance(usage, dict):
        return ""
    parts = []
    total = usage.get("total_tokens")
    prompt_t = usage.get("prompt_tokens")
    completion_t = usage.get("completion_tokens")
    cost = usage.get("cost")
    if total is not None:
        parts.append("Total tokens: %s" % total)
    if prompt_t is not None and completion_t is not None:
        parts.append("Prompt/completion: %s / %s" % (prompt_t, completion_t))
    if cost is not None:
        parts.append("Cost: %s" % cost)
    if not parts:
        return ""
    return "\n".join(parts)


def _truncate_preview(text, max_len=400):
    text = text or ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )

    prompt = prompt_input.get_prompt_from_input_or_group(nuke, g)
    if not prompt:
        nuke.message("Prompt is empty (and no input Text node message found).")
        raise Exception("missing prompt")

    model = (g.knob("model").value() or "google/gemini-2.5-flash").strip()
    system_prompt = (g.knob("system_prompt").value() or "").strip()
    temperature_s = (g.knob("temperature").value() or "1").strip()
    max_tokens_s = (g.knob("max_tokens").value() or "").strip()
    reasoning = bool(g.knob("reasoning").value())

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="openrouter_generate_text",
        group_node=g,
    )


    extra_args = [
        "--prompt",
        prompt,
        "--model",
        model,
        "--out-dir",
        out_dir,
        "--verbose",
    ]

    if system_prompt:
        extra_args += ["--system-prompt", system_prompt]

    try:
        extra_args += ["--temperature", str(float(temperature_s))]
    except Exception:
        extra_args += ["--temperature", "1"]

    if max_tokens_s:
        try:
            extra_args += ["--max-tokens", str(int(max_tokens_s))]
        except Exception:
            pass

    if reasoning:
        extra_args += ["--reasoning"]

    returncode, stdout_lines = runner_util.run_group_helper(
        nuke, g, extra_args, 'OpenRouter Generate Text'
    )

    summary = _parse_helper_summary(stdout_lines)
    output_text = ""
    output_file = os.path.join(out_dir, "output.txt")
    usage = None

    if summary:
        output_text = summary.get("output_text") or ""
        if summary.get("output_file"):
            output_file = summary.get("output_file")
        usage = summary.get("usage")

    if not output_text and os.path.isfile(output_file):
        try:
            with open(output_file, "r") as f:
                output_text = f.read()
        except Exception:
            output_text = ""

    if not output_text:
        nuke.message("Helper finished, but no output text was found in:\n%s" % out_dir)
        raise Exception("no output text")

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        t = nuke.nodes.Text(message=output_text)
        try:
            t.setName("%s_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            t.knob("label").setValue("Generate text\n%s" % prerender.norm_slashes(output_file))
        except Exception:
            pass
        t.setXpos(fx)
        t.setYpos(fy)
    finally:
        nuke.endGroup()

    if _nuke_runner_launcher.should_show_success_popup(g):
        msg_lines = ["Text output created:", prerender.norm_slashes(output_file), ""]
        msg_lines.append(_truncate_preview(output_text))
        usage_s = _format_usage_popup(usage)
        if usage_s:
            msg_lines.append("")
            msg_lines.append(usage_s)
        nuke.message("\n".join(msg_lines))


if __name__ == "__main__":
    main()
