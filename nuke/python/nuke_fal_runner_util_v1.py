# Purpose:
# - Shared Nuke-side (Python 2.7) helpers for fal group runners: python3 argv, FAL env,
#   helper path, subprocess run, and frame range knobs.
# - FAL_KEY cascade: node knob -> ~/.nuke-fal-ai/config.json -> process env.
# - Importable without Nuke for unit tests (pass nuke_module where needed).

from __future__ import print_function

import sys

import _install_help
import nuke_fal_config_v1 as fal_config
import nuke_prerender_v1 as prerender


def resolve_python3_cmd(group_node, platform=None):
    """
    Resolve the group python3_cmd knob into an argv prefix.
    Baked .nk default is `py -3`; on macOS/Linux that value is treated as `python3`.
    """
    if platform is None:
        platform = sys.platform
    is_windows = str(platform).startswith("win")

    python3_cmd = ""
    try:
        python3_cmd = (group_node.knob("python3_cmd").value() or "").strip()
    except Exception:
        python3_cmd = ""

    if not python3_cmd:
        python3_cmd = "py -3" if is_windows else "python3"
    if python3_cmd == "py -3" and (not is_windows):
        python3_cmd = "python3"

    parts = prerender.split_cmd(python3_cmd)
    if parts:
        return parts
    if is_windows:
        return ["py", "-3"]
    return ["python3"]


def helper_env_from_group(group_node, home=None, config_file=None):
    """
    Build helper subprocess env. Sets FAL_KEY from cascade (highest first):
    1. Per-node FAL knob (script override)
    2. fal_key from ~/.nuke-fal-ai/config.json (local machine)
    3. Existing FAL_KEY in the process environment (studio-wide fallback)
    Config wins over env when both are set.
    """
    env = prerender.helper_subprocess_env()
    fal_knob = ""
    try:
        fal_knob = (group_node.knob("FAL").value() or "").strip()
    except Exception:
        fal_knob = ""
    fal_key = fal_config.resolve_fal_key(
        knob_value=fal_knob, env=env, home=home, config_file=config_file
    )
    if fal_key:
        env["FAL_KEY"] = fal_key
    return env


def helper_path_from_group(nuke_module, group_node):
    raw = ""
    try:
        raw = (group_node.knob("helper_path").value() or "").strip()
    except Exception:
        raw = ""
    return _install_help.require_helper_path(nuke_module, raw)


def run_group_helper(nuke_module, group_node, extra_args, title, failure_formatter=None):
    argv = resolve_python3_cmd(group_node) + [helper_path_from_group(nuke_module, group_node)]
    if extra_args:
        argv = argv + list(extra_args)
    try:
        returncode, stdout_lines = prerender.run_helper_subprocess(
            argv,
            env=helper_env_from_group(group_node),
            title=title,
        )
    except prerender.FalProgressCancelled:
        nuke_module.message("%s request cancelled." % title)
        raise Exception("cancelled")
    if returncode != 0:
        if failure_formatter is not None:
            nuke_module.message(failure_formatter(returncode, stdout_lines))
        else:
            nuke_module.message(
                "%s helper failed (exit %d). Check the Script Editor output for details."
                % (title, returncode)
            )
        raise Exception("%s helper failed" % title)
    return (returncode, stdout_lines)


def frame_range_from_knobs(group_node, nuke_module):
    try:
        mode = (group_node.knob("frame_range").value() or "root").strip().lower()
    except Exception:
        mode = "root"

    if mode == "current":
        f = int(nuke_module.frame())
        return f, f

    if mode == "custom":
        try:
            start = int(float((group_node.knob("custom_start").value() or "1").strip()))
            end = int(float((group_node.knob("custom_end").value() or "1").strip()))
            if end < start:
                start, end = end, start
            return start, end
        except Exception:
            pass

    try:
        start = int(nuke_module.root().firstFrame())
        end = int(nuke_module.root().lastFrame())
    except Exception:
        start = 1
        end = 1
    if end < start:
        start, end = end, start
    return start, end
