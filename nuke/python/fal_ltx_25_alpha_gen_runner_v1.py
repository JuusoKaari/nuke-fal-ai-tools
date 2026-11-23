# Purpose:
# - Runner for the Nuke Group node `LTX_25_Alpha_Gen_v1` (executes inside Nuke / Python 2.7).
# - Accepts upstream video on input 0. A single mp4/mov Read is sent as-is when it
#   fits the 200MB upload cap, and recompressed when it does not.
# - Calls `fal_ltx_25_alpha_gen_helper.py` (Python 3), then spawns one Read.
#   Alpha only (default) is the grayscale matte. RGBA is the ProRes 4444 cutout
#   with straight alpha.
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3).

from __future__ import print_function

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import _nuke_runner_launcher

import nuke_prerender_v1 as prerender
import nuke_fal_runner_util_v1 as runner_util
import nuke_video_output_v1 as video_out

_OUTPUT_MODE_CHOICES = ("Alpha only", "RGBA")
_OUTPUT_MODE_CLI = {"Alpha only": "alpha", "RGBA": "rgba"}


def _enum_knob_str(g, knob_name, choices, default):
    try:
        k = g.knob(knob_name)
        v = k.value()
        if isinstance(v, int):
            if 0 <= v < len(choices):
                return choices[v]
            return default
        s = (str(v) or default).strip()
        return s if s in choices else default
    except Exception:
        return default


def main():
    import nuke

    g = _nuke_runner_launcher.get_execute_group_node(
        nuke, caller_globals=globals()
    )
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        nuke.message("Input 0 (source_video) is not connected.")
        raise Exception("missing input 0")

    output_mode = _enum_knob_str(g, "output_mode", _OUTPUT_MODE_CHOICES, "Alpha only")
    output_mode_cli = _OUTPUT_MODE_CLI[output_mode]

    enable_safety_checker = True
    try:
        enable_safety_checker = bool(g.knob("enable_safety_checker").value())
    except Exception:
        enable_safety_checker = True

    default_first, default_last = runner_util.frame_range_from_knobs(g, nuke)

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="ltx_25_alpha_gen",
        group_node=g,
    )

    try:
        video_path = prerender.prepare_video_input_path(
            nuke_module=nuke,
            src_node=src_video_node,
            frame=frame,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="source_video",
            max_bytes=prerender.LTX_25_ALPHA_GEN_MAX_BYTES,
        )
    except Exception as e:
        nuke.message("Failed to prepare source video:\n%s" % str(e))
        raise

    if output_mode_cli == "rgba":
        out_ext = "mov"
        out_label = "LTX 2.5 Alpha Gen RGBA"
        spawn_channels = "rgba"
    else:
        out_ext = "mp4"
        out_label = "LTX 2.5 Alpha Gen alpha"
        spawn_channels = "rgb"
    out_path = os.path.join(out_dir, "ltx_25_alpha_gen_%s_%s.%s" % (output_mode_cli, ts, out_ext))

    extra_args = [
        "--video",
        video_path,
        "--output-mode",
        output_mode_cli,
        "--out",
        out_path,
        "--verbose",
    ]
    if enable_safety_checker:
        extra_args.append("--enable-safety-checker")
    else:
        extra_args.append("--no-enable-safety-checker")

    runner_util.run_group_helper(
        nuke, g, extra_args, "LTX 2.5 Alpha Gen"
    )

    display_path = video_out.spawn_video_output_read(
        nuke,
        g,
        out_path,
        out_label,
        "%s_%s_%s" % (g.name(), output_mode_cli, ts),
        y_offset=140,
        channels=spawn_channels,
    )

    if _nuke_runner_launcher.should_show_success_popup(g):
        if output_mode_cli == "rgba":
            nuke.message(
                "LTX 2.5 Alpha Gen RGBA created (straight alpha):\n%s" % display_path
            )
        else:
            nuke.message("LTX 2.5 Alpha Gen alpha created:\n%s" % display_path)


if __name__ == "__main__":
    main()
