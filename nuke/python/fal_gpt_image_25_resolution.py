# Purpose:
# - Turn a GPT Image 2.5 Resolution tier plus a source aspect into width and height.
# - Match input is not sized here. The helper sends image_size "auto" for that.
# - 1K, 2K, and 4K target long edges of 1024, 2048, and 3840. 3840 is this
#   model's 4K cap, so 16:9 lands on 3840x2160 rather than a 4096-wide frame.
# - 0.5K is omitted. A 512 long edge cannot meet the 655360 pixel minimum,
#   so that label would not describe the image fal returns.
# - Results are multiples of 16, edges stay <= 3840, aspect stays <= 3:1,
#   and total pixels stay inside 655360..8294400.

import math
import os
import struct

# Internal token. The Nuke knob label is "Match input".
MATCH_INPUT = "match_input"
TIER_LONG_EDGE = {
    "1K": 1024,
    "2K": 2048,
    "4K": 3840,
}
RESOLUTION_CHOICES = (MATCH_INPUT, "1K", "2K", "4K")

DIVISOR = 16
MAX_EDGE = 3840
MAX_PIXELS = 8294400  # 3840 * 2160
MIN_PIXELS = 655360
MAX_ASPECT = 3

# Text-to-image presets, used only when no still is connected.
PRESET_ASPECTS = {
    "landscape_4_3": (4, 3),
    "square": (1, 1),
    "landscape_16_9": (16, 9),
    "portrait_16_9": (9, 16),
}

_MATCH_ALIASES = {
    "match_input": MATCH_INPUT,
    "match input": MATCH_INPUT,
    "auto": MATCH_INPUT,
}

# How far around the snapped size to look for a legal multiple of 16.
_SNAP_STEPS = 32


def normalize_resolution(value):
    """Return match_input, 1K, 2K, 4K, or None when the value is not a tier."""
    text = (value or "").strip()
    key = text.lower()
    if key in _MATCH_ALIASES:
        return MATCH_INPUT
    if text in TIER_LONG_EDGE:
        return text
    return None


def fit_output_size(src_w, src_h, tier):
    """
    Return (width, height) for a tier and a source aspect.
    The long edge starts at the tier target, then limits pull it in.
    """
    tier_name = normalize_resolution(tier)
    if tier_name not in TIER_LONG_EDGE:
        raise ValueError("resolution tier must be 1K, 2K, or 4K.")
    src_w = int(src_w)
    src_h = int(src_h)
    if src_w < 1 or src_h < 1:
        raise ValueError("source width and height must be positive.")

    long_edge = float(TIER_LONG_EDGE[tier_name])
    if src_w >= src_h:
        width = long_edge
        height = long_edge * float(src_h) / float(src_w)
    else:
        height = long_edge
        width = long_edge * float(src_w) / float(src_h)

    # Keep the long edge and raise the short side when the plate is past 3:1.
    if width >= height:
        if width > height * float(MAX_ASPECT):
            height = width / float(MAX_ASPECT)
    elif height > width * float(MAX_ASPECT):
        width = height / float(MAX_ASPECT)

    width, height = _apply_pixel_and_edge_limits(width, height)
    snapped_w, snapped_h = _snap_legal(width, height)
    if snapped_w is None:
        raise ValueError(
            "no GPT Image 2.5 size within limits for %s x %s at %s"
            % (src_w, src_h, tier_name)
        )
    return int(snapped_w), int(snapped_h)


def resolve_image_size(resolution, is_edit, preset, src_width=None, src_height=None):
    """
    Return the fal image_size value.
    Match input on edit is "auto". Explicit tiers are {"width", "height"}.
    Text-to-image with no still uses the Image size preset's aspect.
    Preset "auto" with no still stays "auto", because there is no aspect to scale.
    """
    tier = normalize_resolution(resolution)
    if tier is None:
        raise ValueError("resolution must be Match input, 1K, 2K, or 4K.")
    if tier == MATCH_INPUT:
        if is_edit:
            return "auto"
        preset_name = (preset or "").strip() or "landscape_4_3"
        return preset_name

    if src_width and src_height:
        width, height = fit_output_size(src_width, src_height, tier)
        return {"width": int(width), "height": int(height)}

    if is_edit:
        raise ValueError("explicit resolution needs the first image width and height.")

    aspect = PRESET_ASPECTS.get((preset or "").strip())
    if aspect is None:
        return "auto"
    width, height = fit_output_size(aspect[0], aspect[1], tier)
    return {"width": int(width), "height": int(height)}


def read_image_size(path):
    """Return (width, height) from a PNG or JPEG header, or None."""
    size = _png_ihdr_size(path)
    if size is not None:
        return size
    return _jpeg_size(path)


def _apply_pixel_and_edge_limits(width, height):
    long_edge = max(width, height)
    if long_edge > float(MAX_EDGE):
        scale = float(MAX_EDGE) / long_edge
        width *= scale
        height *= scale
    pixels = width * height
    if pixels > float(MAX_PIXELS):
        scale = math.sqrt(float(MAX_PIXELS) / pixels)
        width *= scale
        height *= scale
    pixels = width * height
    if 0 < pixels < float(MIN_PIXELS):
        scale = math.sqrt(float(MIN_PIXELS) / pixels)
        width *= scale
        height *= scale
        long_edge = max(width, height)
        if long_edge > float(MAX_EDGE):
            scale = float(MAX_EDGE) / long_edge
            width *= scale
            height *= scale
    return width, height


def _nearest_multiple(value, multiple):
    snapped = int(math.floor(float(value) / float(multiple) + 0.5)) * multiple
    if snapped < multiple:
        return multiple
    return snapped


def _is_legal(width, height):
    if width < DIVISOR or height < DIVISOR:
        return False
    if width % DIVISOR or height % DIVISOR:
        return False
    if width > MAX_EDGE or height > MAX_EDGE:
        return False
    pixels = width * height
    if pixels < MIN_PIXELS or pixels > MAX_PIXELS:
        return False
    long_edge = width if width >= height else height
    short_edge = height if width >= height else width
    if long_edge > short_edge * MAX_ASPECT:
        return False
    return True


def _snap_legal(ideal_w, ideal_h):
    """Pick the legal multiple of 16 closest to the continuous ideal size."""
    base_w = _nearest_multiple(ideal_w, DIVISOR)
    base_h = _nearest_multiple(ideal_h, DIVISOR)
    best = None
    for step_w in range(-_SNAP_STEPS, _SNAP_STEPS + 1):
        for step_h in range(-_SNAP_STEPS, _SNAP_STEPS + 1):
            width = base_w + step_w * DIVISOR
            height = base_h + step_h * DIVISOR
            if not _is_legal(width, height):
                continue
            dist = (width - ideal_w) ** 2 + (height - ideal_h) ** 2
            rank = (dist, width * height, width, height)
            if best is None or rank < best:
                best = rank
    if best is None:
        return None, None
    return best[2], best[3]


def _png_ihdr_size(path):
    try:
        with open(path, "rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            handle.read(4)
            if handle.read(4) != b"IHDR":
                return None
            width, height = struct.unpack(">II", handle.read(8))
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def _jpeg_size(path):
    try:
        with open(path, "rb") as handle:
            if handle.read(2) != b"\xff\xd8":
                return None
            while True:
                marker = _next_jpeg_marker(handle)
                if marker is None:
                    return None
                if marker in (
                    0xC0, 0xC1, 0xC2, 0xC3,
                    0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB,
                    0xCD, 0xCE, 0xCF,
                ):
                    if len(handle.read(2)) != 2:
                        return None
                    rest = handle.read(5)
                    if len(rest) != 5:
                        return None
                    _precision, height, width = struct.unpack(">BHH", rest)
                    if width <= 0 or height <= 0:
                        return None
                    return int(width), int(height)
                if marker in (0xD9, 0xDA):
                    return None
                if marker == 0xD8 or 0xD0 <= marker <= 0xD7:
                    continue
                length_bytes = handle.read(2)
                if len(length_bytes) != 2:
                    return None
                length = struct.unpack(">H", length_bytes)[0]
                if length < 2:
                    return None
                handle.seek(length - 2, os.SEEK_CUR)
    except Exception:
        return None


def _next_jpeg_marker(handle):
    byte = handle.read(1)
    while byte and byte != b"\xff":
        byte = handle.read(1)
    if not byte:
        return None
    while byte == b"\xff":
        byte = handle.read(1)
        if not byte:
            return None
    return byte[0]
