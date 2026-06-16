# Purpose: Nuke menu entries for all 20 fal.ai toolbox group nodes (Nodes toolbar + top menubar).

from __future__ import print_function

import os

import nuke

import _install_help

_ROOT = os.path.normpath(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
_GROUP_DIR = os.path.join(_ROOT, "nuke", "groups").replace("\\", "/")
_PLACEHOLDER = "__INSTALL_ROOT__"

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


def _tool_path(filename):
    return "%s/nuke/python/%s" % (_PLACEHOLDER, filename)


def _create_fal_node(group_file, helper_py, runner_py):
    group_path = os.path.join(_GROUP_DIR, group_file).replace("\\", "/")
    if not os.path.isfile(group_path):
        nuke.message("Missing group file:\n%s%s" % (group_path, _install_help.install_hint()))
        raise Exception("group not found: %s" % group_file)
    node = nuke.createNode(group_path, inpanel=False)
    helper_knob = node.knob("helper_path")
    runner_knob = node.knob("runner_path")
    if helper_knob is None or runner_knob is None:
        nuke.message(
            "Group node is missing helper_path or runner_path knobs:\n%s\n\n"
            "Re-create from Nodes -> fal.ai or check the group .nk file."
            % group_file
        )
        raise Exception("fal.ai group missing path knobs: %s" % group_file)
    helper_knob.setValue(_tool_path(helper_py))
    runner_knob.setValue(_tool_path(runner_py))
    return node


# (category, label, group_file, helper_py, runner_py) - sorted A-Z by label within each category
_CATEGORY_ORDER = {"image": 0, "video": 1, "3d": 2, "text": 3}
_TOOLS = sorted(
    [
        ("image", "BiRefNet v2 Still", "fal_birefnet_v2_still_v1.nk", "fal_birefnet_v2_still_helper.py", "fal_birefnet_v2_still_runner_v1.py"),
        ("image", "Depth Anything v2", "fal_depth_anything_v2.nk", "fal_depth_anything_v2_helper.py", "fal_depth_anything_v2_runner_v1.py"),
        ("image", "Finegrain Eraser", "fal_finegrain_eraser_v1.nk", "fal_finegrain_eraser_helper.py", "fal_finegrain_eraser_runner_v1.py"),
        ("image", "GPT Image 2 Edit", "fal_gpt_image_2_edit_v1.nk", "fal_gpt_image_2_edit_helper.py", "fal_gpt_image_2_edit_runner_v1.py"),
        ("image", "Hunyuan World", "fal_hunyuan_world_v1.nk", "fal_hunyuan_world_helper.py", "fal_hunyuan_world_runner_v1.py"),
        ("image", "Nano Banana 2 Generate", "fal_nano_banana_2_generate_v1.nk", "fal_nano_banana_2_generate_helper.py", "fal_nano_banana_2_generate_runner_v1.py"),
        ("image", "Qwen Image Inpaint", "fal_qwen_image_inpaint_v1.nk", "fal_qwen_image_inpaint_helper.py", "fal_qwen_image_inpaint_runner_v1.py"),
        ("image", "Qwen Image Layered", "fal_qwen_image_layered_v1.nk", "fal_qwen_image_layered_helper.py", "fal_qwen_image_layered_runner_v1.py"),
        ("image", "Qwen Image Max Edit", "fal_qwen_image_max_edit_v1.nk", "fal_qwen_image_max_edit_helper.py", "fal_qwen_image_max_edit_runner_v1.py"),
        ("3d", "Hunyuan 3D Image to 3D", "fal_hunyuan_3d_image_to_3d_v1.nk", "fal_hunyuan_3d_image_to_3d_helper.py", "fal_hunyuan_3d_image_to_3d_runner_v1.py"),
        ("video", "BiRefNet v2", "fal_birefnet_v2.nk", "fal_birefnet_v2_helper.py", "fal_birefnet_v2_runner_v2.py"),
        ("video", "ByteDance Video Upscale", "fal_bytedance_video_upscale_v1.nk", "fal_bytedance_video_upscale_helper.py", "fal_bytedance_video_upscale_runner_v1.py"),
        ("video", "DreamActor v2 Motion Control", "fal_dreamactor_v2_motion_control_v1.nk", "fal_dreamactor_v2_helper.py", "fal_dreamactor_v2_motion_control_runner_v1.py"),
        ("video", "Kling O3 V2V Edit", "fal_kling_o3_v2v_edit_v1.nk", "fal_kling_o3_v2v_edit_helper.py", "fal_kling_o3_v2v_edit_runner_v1.py"),
        ("video", "LTX 2.3 Image to Video", "fal_ltx_23_image_to_video_v1.nk", "fal_ltx_23_image_to_video_helper.py", "fal_ltx_23_image_to_video_runner_v1.py"),
        ("video", "Pika v2.2 Pikaframes", "fal_pika_v22_pikaframes_v1.nk", "fal_pika_v22_pikaframes_helper.py", "fal_pika_v22_pikaframes_runner_v1.py"),
        ("video", "Seedance 2 Image to Video", "fal_seedance_2_image_to_video_v1.nk", "fal_seedance_2_image_to_video_helper.py", "fal_seedance_2_image_to_video_runner_v1.py"),
        ("video", "Veo 3.1 Extend Video", "fal_veo3_1_extend_video_v1.nk", "fal_veo3_1_extend_video_helper.py", "fal_veo3_1_extend_video_runner_v1.py"),
        ("text", "Describe image", "fal_openrouter_describe_image_v1.nk", "fal_openrouter_describe_image_helper.py", "fal_openrouter_describe_image_runner_v1.py"),
        ("text", "Generate text", "fal_openrouter_generate_text_v1.nk", "fal_openrouter_generate_text_helper.py", "fal_openrouter_generate_text_runner_v1.py"),
    ],
    key=lambda t: (_CATEGORY_ORDER[t[0]], t[1].lower()),
)


def _make_creator(group_file, helper_py, runner_py):
    def _creator():
        return _create_fal_node(group_file, helper_py, runner_py)

    return _creator


def _execute_selected_nodes():
    import _nuke_runner_launcher

    _nuke_runner_launcher.execute_selected_nodes()


def _add_tool_commands(parent_menu, categorized=False, category_labels=None):
    category_menus = {}

    for category, label, group, helper, runner in _TOOLS:
        target = parent_menu
        if categorized:
            if category not in category_menus:
                menu_label = category_labels[category]
                category_menus[category] = parent_menu.addMenu(menu_label)
            target = category_menus[category]
        target.addCommand(label, _make_creator(group, helper, runner))


def _add_execute_selected(parent_menu):
    parent_menu.addSeparator()
    parent_menu.addCommand("Execute Selected Nodes", _execute_selected_nodes)


_nodes_fal_menu = nuke.menu("Nodes").addMenu("fal.ai")
_add_tool_commands(_nodes_fal_menu, categorized=True, category_labels=_NODES_CATEGORY_LABELS)
_add_execute_selected(_nodes_fal_menu)

_top_fal_menu = nuke.menu("Nuke").addMenu("fal.ai")
_add_tool_commands(_top_fal_menu, categorized=True, category_labels=_TOP_CATEGORY_LABELS)
_add_execute_selected(_top_fal_menu)
