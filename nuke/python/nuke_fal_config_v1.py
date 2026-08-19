# Purpose:
# - Read/write artist fal.ai settings from ~/.nuke-fal-ai/config.json.
# - Resolve optional default output folder for runner temp/output dirs.
# - Video output mode: DWAB EXR sequence (default) or keep the fal MP4 Read.
# - Python 2.7 compatible; importable without Nuke for unit tests.

from __future__ import print_function

import json
import os
import sys


_CONFIG_DIR_NAME = ".nuke-fal-ai"
_CONFIG_FILE_NAME = "config.json"

VIDEO_OUTPUT_EXR_SEQUENCE = "exr_sequence"
VIDEO_OUTPUT_MP4 = "mp4"
VIDEO_OUTPUT_DEFAULT = VIDEO_OUTPUT_EXR_SEQUENCE

_DEFAULTS = {
    "fal_key": "",
    "output_dir": "",
    "video_output": VIDEO_OUTPUT_DEFAULT,
}


def config_dir(home=None):
    if home is None:
        home = os.path.expanduser("~")
    return os.path.join(home, _CONFIG_DIR_NAME)


def config_path(home=None):
    return os.path.join(config_dir(home=home), _CONFIG_FILE_NAME)


def _coerce_str(value):
    if value is None:
        return ""
    if sys.version_info[0] < 3 and isinstance(value, unicode):  # noqa: F821
        return value.encode("utf-8", "replace")
    return str(value)


def normalize_video_output(value):
    """
    Return VIDEO_OUTPUT_EXR_SEQUENCE or VIDEO_OUTPUT_MP4.
    Unknown / empty values fall back to the default (EXR sequence).
    """
    s = _coerce_str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if s in ("mp4", "movie", "video"):
        return VIDEO_OUTPUT_MP4
    if s in ("exr_sequence", "exr", "sequence", "dwab", "dwab_exr"):
        return VIDEO_OUTPUT_EXR_SEQUENCE
    return VIDEO_OUTPUT_DEFAULT


def normalize_config(data):
    """Return a plain dict with known keys as strings."""
    out = dict(_DEFAULTS)
    if not isinstance(data, dict):
        return out
    if "fal_key" in data:
        out["fal_key"] = _coerce_str(data.get("fal_key")).strip()
    if "output_dir" in data:
        out["output_dir"] = _coerce_str(data.get("output_dir")).strip()
    if "video_output" in data:
        out["video_output"] = normalize_video_output(data.get("video_output"))
    return out


def load_config(home=None, path=None):
    """
    Load config.json. Missing file returns defaults.
    Invalid JSON returns defaults (does not raise).
    """
    cfg_path = path if path is not None else config_path(home=home)
    if not cfg_path or (not os.path.isfile(cfg_path)):
        return normalize_config({})
    try:
        with open(cfg_path, "r") as f:
            raw = f.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return normalize_config({})
    return normalize_config(data)


def save_config(data, home=None, path=None):
    """
    Write config.json (creates parent dir). Returns the path written.
    Merges provided keys onto the existing file so a partial save does not
    reset other settings. On Unix, best-effort chmod 0600 after write.
    """
    cfg_path = path if path is not None else config_path(home=home)
    parent = os.path.dirname(cfg_path)
    if parent and (not os.path.isdir(parent)):
        os.makedirs(parent)
    merged = load_config(home=home, path=cfg_path)
    if isinstance(data, dict):
        for key in _DEFAULTS:
            if key in data:
                merged[key] = data[key]
    payload = normalize_config(merged)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    with open(cfg_path, "w") as f:
        f.write(text)
    try:
        os.chmod(cfg_path, 0o600)
    except Exception:
        pass
    return cfg_path


def get_fal_key_from_config(home=None, path=None):
    cfg = load_config(home=home, path=path)
    return (cfg.get("fal_key") or "").strip()


def get_output_dir(home=None, path=None):
    """Return configured default output folder string (may be empty)."""
    cfg = load_config(home=home, path=path)
    return (cfg.get("output_dir") or "").strip()


def get_video_output(home=None, path=None):
    """Return VIDEO_OUTPUT_EXR_SEQUENCE or VIDEO_OUTPUT_MP4."""
    cfg = load_config(home=home, path=path)
    return normalize_video_output(cfg.get("video_output"))


def _can_use_dir(path):
    """True if path exists or can be created and is writable."""
    try:
        if path and (not os.path.isdir(path)):
            os.makedirs(path)
        test_path = os.path.join(path, ".__nuke_fal_ai_write_test")
        f = open(test_path, "wb")
        try:
            f.write(b"x")
        finally:
            try:
                f.close()
            except Exception:
                pass
        try:
            os.remove(test_path)
        except Exception:
            pass
        return True
    except Exception:
        return False


def normalize_output_dir_path(path):
    """
    Expand ~, strip, and return an absolute path with OS separators.
    Empty input returns "".
    """
    raw = _coerce_str(path).strip()
    if not raw:
        return ""
    try:
        expanded = os.path.expanduser(raw)
    except Exception:
        expanded = raw
    expanded = expanded.strip()
    if not expanded:
        return ""
    try:
        return os.path.abspath(expanded)
    except Exception:
        return expanded


def resolve_usable_output_base(configured=None, home=None, path=None):
    """
    Resolve Settings default output folder to a usable absolute parent dir.

    Precedence source is config `output_dir` unless `configured` is passed.
    Returns "" when empty, invalid, or not writable (does not raise).
    """
    if configured is None:
        configured = get_output_dir(home=home, path=path)
    base = normalize_output_dir_path(configured)
    if not base:
        return ""
    if _can_use_dir(base):
        return base
    return ""


def resolve_fal_key(knob_value=None, env=None, home=None, config_file=None):
    """
    Resolve FAL_KEY with cascade (highest first):
    1. Per-node FAL knob (script override)
    2. ~/.nuke-fal-ai/config.json (local machine Settings)
    3. Env FAL_KEY (studio-wide fallback)
    """
    if env is None:
        env = os.environ
    knob = _coerce_str(knob_value).strip() if knob_value is not None else ""
    if knob and ("insert your secret" not in knob.lower()):
        return knob
    cfg_key = get_fal_key_from_config(home=home, path=config_file)
    if cfg_key:
        return cfg_key
    return _coerce_str(env.get("FAL_KEY", "")).strip()
