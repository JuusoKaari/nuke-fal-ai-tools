# Purpose:
# - Python 3 helper for Nuke (Python 2.7) to extend a video via fal.ai Veo 3.1.
# - Uploads a local reference video to fal storage, calls:
#   `fal-ai/veo3.1/extend-video`, downloads the resulting MP4, and prints logs/JSON.
#
# Model: https://fal.ai/models/fal-ai/veo3.1/extend-video
#
# Requirements:
#   pip install fal-client
#
# Auth:
# - Provide `--fal-key` or set environment variable `FAL_KEY`.

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from fal_common import (
    compute_retry_sleep_seconds,
    download,
    ensure_dir,
    format_fal_error_summary,
    print_queue_logs,
    should_retry_fal_error,
)

_ENDPOINT_ID = "fal-ai/veo3.1/extend-video"
# OpenAPI for this endpoint only allows these fixed output settings.
_API_DURATION = "7s"
_API_RESOLUTION = "720p"
_MAX_INPUT_SECONDS = 8.0
_ALLOWED_DIMENSIONS = {
    (1280, 720),
    (1920, 1080),
    (720, 1280),
    (1080, 1920),
}


def _norm_ext(p: str) -> str:
    return os.path.splitext(p)[1].lower().lstrip(".")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Extend a reference video using Veo 3.1 via fal.ai and download result."
    )
    parser.add_argument("--fal-key", default=None, help="fal.ai API key (otherwise uses FAL_KEY env var).")
    parser.add_argument("--video", required=True, help="Path to local reference video (.mp4/.mov).")
    parser.add_argument("--prompt", required=True, help="Text prompt describing how the video should be extended.")
    parser.add_argument("--out", required=True, help="Path to output MP4 file to write.")
    parser.add_argument(
        "--aspect-ratio",
        default="auto",
        choices=["auto", "16:9", "9:16"],
        help="Aspect ratio of the generated extension. Default: auto.",
    )
    parser.add_argument(
        "--max-input-seconds",
        type=float,
        default=_MAX_INPUT_SECONDS,
        help="Warn if input video exceeds this length (API max 8s). Default: 8.",
    )
    parser.add_argument(
        "--generate-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to generate audio for the extension. Default: true.",
    )
    parser.add_argument("--negative-prompt", default="", help="Optional negative prompt.")
    parser.add_argument(
        "--safety-tolerance",
        default="4",
        choices=["1", "2", "3", "4", "5", "6"],
        help="Content moderation tolerance (1 strict, 6 permissive). Default: 4.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed.")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient fal backend errors (5xx/429/downstream_service_error). Default: 3.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base backoff seconds for retries (exponential with jitter). Default: 2.0.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more logs.")
    args = parser.parse_args(argv)

    fal_key = args.fal_key or os.environ.get("FAL_KEY")
    if not fal_key:
        print("ERROR: missing FAL key. Provide --fal-key or set FAL_KEY env var.", file=sys.stderr)
        return 2

    video_path = os.path.abspath(args.video)
    out_path = os.path.abspath(args.out)
    ensure_dir(os.path.dirname(out_path))

    if not os.path.isfile(video_path):
        print("ERROR: video file not found: %s" % video_path, file=sys.stderr)
        return 2

    video_ext = _norm_ext(video_path)
    if video_ext not in {"mp4", "mov"}:
        print(
            "ERROR: video must be .mp4 or .mov for this model. Got: %s" % video_path,
            file=sys.stderr,
        )
        return 2

    prompt = (args.prompt or "").strip()
    if not prompt:
        print("ERROR: prompt is empty.", file=sys.stderr)
        return 2

    try:
        import fal_client
    except Exception as e:
        print("ERROR: failed to import fal_client. Did you `pip install fal-client`? (%s)" % (e,), file=sys.stderr)
        return 3
    try:
        from fal_client.client import FalClientHTTPError  # type: ignore
    except Exception:
        FalClientHTTPError = Exception  # type: ignore

    client = fal_client.SyncClient(key=fal_key)
    user_agent = "nuke-fal-veo3-1-extend-video-helper"

    try:
        import subprocess as _sp

        probe_args = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            video_path,
        ]
        p_probe = _sp.run(probe_args, capture_output=True, text=True)
        if p_probe.returncode == 0 and p_probe.stdout:
            probe_data = json.loads(p_probe.stdout)
            st = (probe_data.get("streams") or [{}])[0]
            w = int(st.get("width") or 0)
            h = int(st.get("height") or 0)
            dur_s = None
            try:
                if st.get("duration") is not None:
                    dur_s = float(st.get("duration"))
                elif (probe_data.get("format") or {}).get("duration") is not None:
                    dur_s = float((probe_data.get("format") or {}).get("duration"))
            except Exception:
                dur_s = None
            if dur_s is not None and dur_s > float(args.max_input_seconds) + 0.05:
                print(
                    "ERROR: input video is %.2fs but fal-ai/veo3.1/extend-video accepts at most %.0fs. "
                    "Re-run from the Nuke node (runner trims to the last %.0fs automatically)."
                    % (dur_s, args.max_input_seconds, args.max_input_seconds),
                    file=sys.stderr,
                )
                return 2
            if (w, h) not in _ALLOWED_DIMENSIONS:
                print(
                    "ERROR: input video resolution is %dx%d. API requires 720p or 1080p in 16:9 or 9:16 "
                    "(1280x720, 1920x1080, 720x1280, or 1080x1920)."
                    % (w, h),
                    file=sys.stderr,
                )
                return 2
            if args.verbose:
                print("Input probe OK: %dx%d, %.2fs" % (w, h, dur_s or 0.0))
    except FileNotFoundError:
        if args.verbose:
            print("WARNING: ffprobe not found; skipping local input validation.")
    except Exception as e:
        if args.verbose:
            print("WARNING: ffprobe validation skipped (%s)" % e)

    if args.verbose:
        print("Uploading video: %s" % video_path)
    video_url = client.upload_file(video_path)

    if args.verbose:
        print("Uploaded video_url=%s" % video_url)

    def on_queue_update(update) -> None:
        print_queue_logs(update)

    arguments: dict = {
        "prompt": prompt,
        "video_url": video_url,
        "aspect_ratio": args.aspect_ratio,
        "duration": _API_DURATION,
        "resolution": _API_RESOLUTION,
        "generate_audio": bool(args.generate_audio),
        "safety_tolerance": args.safety_tolerance,
    }
    negative_prompt = (args.negative_prompt or "").strip()
    if negative_prompt:
        arguments["negative_prompt"] = negative_prompt
    if args.seed is not None:
        arguments["seed"] = int(args.seed)

    result = None
    last_exc: BaseException | None = None
    max_attempts = max(1, int(args.max_retries) + 1)
    for attempt in range(1, max_attempts + 1):
        try:
            if args.verbose:
                print(
                    "Submitting request: %s (attempt %d/%d)\narguments=%s"
                    % (_ENDPOINT_ID, attempt, max_attempts, json.dumps(arguments, indent=2))
                )
            result = client.subscribe(
                _ENDPOINT_ID,
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update,
            )
            last_exc = None
            break
        except FalClientHTTPError as e:
            last_exc = e
            if (attempt >= max_attempts) or (not should_retry_fal_error(e)):
                break
            sleep_s = compute_retry_sleep_seconds(attempt, float(args.retry_base_seconds))
            print(
                "WARNING: fal request failed (attempt %d/%d). Retrying in %.1fs.\n%s"
                % (attempt, max_attempts, sleep_s, format_fal_error_summary(e)),
                file=sys.stderr,
            )
            time.sleep(sleep_s)
        except Exception as e:
            last_exc = e
            break

    if result is None:
        print(
            "ERROR: Veo 3.1 extend-video request failed.\n%s"
            % (format_fal_error_summary(last_exc) if last_exc else "Unknown error"),
            file=sys.stderr,
        )
        return 5

    try:
        video_out_url = result["video"]["url"]
    except Exception:
        print("ERROR: unexpected response shape:\n%s" % json.dumps(result, indent=2), file=sys.stderr)
        return 4

    if args.verbose:
        print("Downloading output video -> %s" % out_path)
    download(str(video_out_url), out_path, user_agent=user_agent)

    print(
        json.dumps(
            {
                "ok": True,
                "endpoint": _ENDPOINT_ID,
                "out_path": out_path,
                "video_url": video_out_url,
                "duration": _API_DURATION,
                "resolution": _API_RESOLUTION,
                "aspect_ratio": args.aspect_ratio,
                "generate_audio": bool(args.generate_audio),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
