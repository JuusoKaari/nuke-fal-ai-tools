# Purpose:
# - Single catalog of fal.ai toolbox tools for menu.py and tests.
# - Category (image/video/3d/text) plus optional family (Qwen, LTX, Utility, ...).
# - Families with 2+ tools in a category become a submenu; singles stay flat.
# - No Nuke import. Python 2.7 compatible.

from __future__ import print_function

_NODES_CATEGORY_LABELS = {
    "image": "fal-image",
    "video": "fal-video",
    "3d": "fal-3d",
    "text": "fal-text",
}

_TOP_CATEGORY_LABELS = {
    "image": "Image",
    "video": "Video",
    "3d": "3D",
    "text": "Text",
}

# family id -> (Nodes / Tab submenu label, top menubar submenu label)
_FAMILY_LABELS = {
    "bria": ("fal-bria", "Bria"),
    "dreamactor": ("fal-dreamactor", "DreamActor"),
    "flux": ("fal-flux", "FLUX 3"),
    "gpt-image": ("fal-gpt-image", "GPT Image"),
    "hunyuan-3d": ("fal-hunyuan-3d", "Hunyuan 3D"),
    "hunyuan-world": ("fal-hunyuan-world", "Hunyuan World"),
    "kling": ("fal-kling", "Kling"),
    "ltx": ("fal-ltx", "LTX"),
    "minimax": ("fal-minimax", "MiniMax"),
    "nano-banana": ("fal-nano-banana", "Nano Banana"),
    "openrouter": ("fal-openrouter", "OpenRouter"),
    "pika": ("fal-pika", "Pika"),
    "qwen": ("fal-qwen", "Qwen"),
    "seedance": ("fal-seedance", "Seedance"),
    "seedream": ("fal-seedream", "Seedream"),
    "utility": ("fal-utility", "Utility"),
    "veo": ("fal-veo", "Veo"),
}

# (category, family, label, group_file, helper_py, runner_py)
# family must be a key in _FAMILY_LABELS. Nested only when 2+ tools share
# the same (category, family). Utility is sorted last within a category.
_CATEGORY_ORDER = {"image": 0, "video": 1, "3d": 2, "text": 3}
_TOOLS = sorted(
    [
        ("image", "utility", "BiRefNet v2 Still", "fal_birefnet_v2_still_v1.nk", "fal_birefnet_v2_still_helper.py", "fal_birefnet_v2_still_runner_v1.py"),
        ("image", "utility", "Depth Anything v2", "fal_depth_anything_v2.nk", "fal_depth_anything_v2_helper.py", "fal_depth_anything_v2_runner_v1.py"),
        ("image", "utility", "Finegrain Eraser", "fal_finegrain_eraser_v1.nk", "fal_finegrain_eraser_helper.py", "fal_finegrain_eraser_runner_v1.py"),
        ("image", "utility", "Image upscale (Topaz Precision)", "fal_topaz_upscale_image_precision_v1.nk", "fal_topaz_upscale_image_precision_helper.py", "fal_topaz_upscale_image_precision_runner_v1.py"),
        ("image", "gpt-image", "GPT Image 2 Edit", "fal_gpt_image_2_edit_v1.nk", "fal_gpt_image_2_edit_helper.py", "fal_gpt_image_2_edit_runner_v1.py"),
        ("image", "hunyuan-world", "Hunyuan World", "fal_hunyuan_world_v1.nk", "fal_hunyuan_world_helper.py", "fal_hunyuan_world_runner_v1.py"),
        ("image", "nano-banana", "Nano Banana 2 Generate", "fal_nano_banana_2_generate_v1.nk", "fal_nano_banana_2_generate_helper.py", "fal_nano_banana_2_generate_runner_v1.py"),
        ("image", "qwen", "Qwen Image Inpaint", "fal_qwen_image_inpaint_v1.nk", "fal_qwen_image_inpaint_helper.py", "fal_qwen_image_inpaint_runner_v1.py"),
        ("image", "qwen", "Qwen Image Layered", "fal_qwen_image_layered_v1.nk", "fal_qwen_image_layered_helper.py", "fal_qwen_image_layered_runner_v1.py"),
        ("image", "qwen", "Qwen Image Max Edit", "fal_qwen_image_max_edit_v1.nk", "fal_qwen_image_max_edit_helper.py", "fal_qwen_image_max_edit_runner_v1.py"),
        ("image", "seedream", "Seedream 5.0 Pro Edit", "fal_seedream_5_pro_edit_v1.nk", "fal_seedream_5_pro_edit_helper.py", "fal_seedream_5_pro_edit_runner_v1.py"),
        ("3d", "hunyuan-3d", "Hunyuan 3D Image to 3D", "fal_hunyuan_3d_image_to_3d_v1.nk", "fal_hunyuan_3d_image_to_3d_helper.py", "fal_hunyuan_3d_image_to_3d_runner_v1.py"),
        ("video", "utility", "BiRefNet v2", "fal_birefnet_v2.nk", "fal_birefnet_v2_helper.py", "fal_birefnet_v2_runner_v2.py"),
        ("video", "utility", "ByteDance Video Upscale", "fal_bytedance_video_upscale_v1.nk", "fal_bytedance_video_upscale_helper.py", "fal_bytedance_video_upscale_runner_v1.py"),
        ("video", "dreamactor", "DreamActor v2 Motion Control", "fal_dreamactor_v2_motion_control_v1.nk", "fal_dreamactor_v2_helper.py", "fal_dreamactor_v2_motion_control_runner_v1.py"),
        ("video", "flux", "FLUX 3 First/Last Frame to Video", "fal_flux_3_first_last_frame_to_video_v1.nk", "fal_flux_3_first_last_frame_to_video_helper.py", "fal_flux_3_first_last_frame_to_video_runner_v1.py"),
        ("video", "flux", "FLUX 3 Keyframes to Video", "fal_flux_3_keyframes_to_video_v1.nk", "fal_flux_3_keyframes_to_video_helper.py", "fal_flux_3_keyframes_to_video_runner_v1.py"),
        ("video", "kling", "Kling O3 V2V Edit", "fal_kling_o3_v2v_edit_v1.nk", "fal_kling_o3_v2v_edit_helper.py", "fal_kling_o3_v2v_edit_runner_v1.py"),
        ("video", "ltx", "LTX 2.3 Image to Video", "fal_ltx_23_image_to_video_v1.nk", "fal_ltx_23_image_to_video_helper.py", "fal_ltx_23_image_to_video_runner_v1.py"),
        ("video", "ltx", "LTX 2.5 Image to Video Pro", "fal_ltx_25_image_to_video_pro_v1.nk", "fal_ltx_25_image_to_video_pro_helper.py", "fal_ltx_25_image_to_video_pro_runner_v1.py"),
        ("video", "minimax", "MiniMax H3 Image to Video", "fal_minimax_h3_image_to_video_v1.nk", "fal_minimax_h3_image_to_video_helper.py", "fal_minimax_h3_image_to_video_runner_v1.py"),
        ("video", "pika", "Pika v2.2 Pikaframes", "fal_pika_v22_pikaframes_v1.nk", "fal_pika_v22_pikaframes_helper.py", "fal_pika_v22_pikaframes_runner_v1.py"),
        ("video", "seedance", "Seedance 2 Image to Video", "fal_seedance_2_image_to_video_v1.nk", "fal_seedance_2_image_to_video_helper.py", "fal_seedance_2_image_to_video_runner_v1.py"),
        ("video", "seedance", "Seedance 2 Reference to Video", "fal_seedance_2_reference_to_video_v1.nk", "fal_seedance_2_reference_to_video_helper.py", "fal_seedance_2_reference_to_video_runner_v1.py"),
        ("video", "seedance", "Seedance 2.5 Image to Video", "fal_seedance_25_image_to_video_v1.nk", "fal_seedance_25_image_to_video_helper.py", "fal_seedance_25_image_to_video_runner_v1.py"),
        ("video", "veo", "Veo 3.1 Extend Video", "fal_veo3_1_extend_video_v1.nk", "fal_veo3_1_extend_video_helper.py", "fal_veo3_1_extend_video_runner_v1.py"),
        ("text", "openrouter", "Describe image", "fal_openrouter_describe_image_v1.nk", "fal_openrouter_describe_image_helper.py", "fal_openrouter_describe_image_runner_v1.py"),
        ("text", "openrouter", "Generate text", "fal_openrouter_generate_text_v1.nk", "fal_openrouter_generate_text_helper.py", "fal_openrouter_generate_text_runner_v1.py"),
    ],
    key=lambda t: (_CATEGORY_ORDER[t[0]], t[2].lower()),
)


def family_menu_label(family, for_nodes):
    """Return the submenu title for a family. Nodes toolbar uses the fal- prefix."""
    nodes_label, top_label = _FAMILY_LABELS[family]
    if for_nodes:
        return nodes_label
    return top_label


def _family_counts():
    counts = {}
    for category, family, _label, _group, _helper, _runner in _TOOLS:
        key = (category, family)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _entry_sort_key(sort_name, family):
    # Utility sits at the end of Image / Video. Other families A-Z by display name.
    tail = 1 if family == "utility" else 0
    return (tail, (sort_name or "").lower())


def iter_categorized_menu_entries():
    """Yield (category, entries) for nested menus.

    Each entry is either:
      ("item", label, group_file, helper_py, runner_py)
      ("submenu", family, [(label, group_file, helper_py, runner_py), ...])
    """
    counts = _family_counts()
    categories = sorted(_CATEGORY_ORDER.keys(), key=lambda c: _CATEGORY_ORDER[c])
    for category in categories:
        nested = {}
        flats = []
        for row in _TOOLS:
            cat, family, label, group, helper, runner = row
            if cat != category:
                continue
            if counts.get((cat, family), 0) >= 2:
                nested.setdefault(family, []).append((label, group, helper, runner))
            else:
                flats.append((family, label, group, helper, runner))

        entries = []
        for _family, label, group, helper, runner in flats:
            entries.append(
                (
                    _entry_sort_key(label, _family),
                    ("item", label, group, helper, runner),
                )
            )
        for family, tools in nested.items():
            tools_sorted = sorted(tools, key=lambda t: t[0].lower())
            display = _FAMILY_LABELS[family][1]
            entries.append(
                (
                    _entry_sort_key(display, family),
                    ("submenu", family, tools_sorted),
                )
            )
        entries.sort(key=lambda item: item[0])
        yield category, [item[1] for item in entries]
