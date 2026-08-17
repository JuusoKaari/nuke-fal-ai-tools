# Purpose: Nuke menu entries for all fal.ai toolbox group nodes (Nodes toolbar + top menubar).

from __future__ import print_function

import os

import nuke

import _install_help
from _fal_tools import (
    _NODES_CATEGORY_LABELS,
    _TOOLS,
    _TOP_CATEGORY_LABELS,
)

_ROOT = os.path.normpath(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
_GROUP_DIR = os.path.join(_ROOT, "nuke", "groups").replace("\\", "/")
_PLACEHOLDER = "__INSTALL_ROOT__"


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


def _make_creator(group_file, helper_py, runner_py):
    def _creator():
        return _create_fal_node(group_file, helper_py, runner_py)

    return _creator


def _execute_selected_nodes():
    import _nuke_runner_launcher

    _nuke_runner_launcher.execute_selected_nodes()


def _show_settings():
    import nuke_fal_settings_v1

    nuke_fal_settings_v1.show_settings_panel()


def _add_tool_commands(parent_menu, categorized=False, category_labels=None, label_prefix=""):
    category_menus = {}
    prefix = label_prefix or ""

    for category, label, group, helper, runner in _TOOLS:
        target = parent_menu
        if categorized:
            if category not in category_menus:
                menu_label = category_labels[category]
                category_menus[category] = parent_menu.addMenu(menu_label)
            target = category_menus[category]
        cmd_label = "%s%s" % (prefix, label) if prefix else label
        target.addCommand(cmd_label, _make_creator(group, helper, runner))


def _add_execute_selected(parent_menu):
    parent_menu.addSeparator()
    parent_menu.addCommand("Execute Selected Nodes", _execute_selected_nodes)


def _add_settings_command(parent_menu, at_top=False):
    if at_top:
        parent_menu.addCommand("Settings...", _show_settings)
        parent_menu.addSeparator()
        return
    parent_menu.addSeparator()
    parent_menu.addCommand("Settings...", _show_settings)


_nodes_fal_menu = nuke.menu("Nodes").addMenu("fal.ai")
_add_settings_command(_nodes_fal_menu, at_top=True)
_add_tool_commands(
    _nodes_fal_menu,
    categorized=True,
    category_labels=_NODES_CATEGORY_LABELS,
    label_prefix="fal ",
)
_add_execute_selected(_nodes_fal_menu)

_top_fal_menu = nuke.menu("Nuke").addMenu("fal.ai")
_add_settings_command(_top_fal_menu, at_top=True)
_add_tool_commands(_top_fal_menu, categorized=True, category_labels=_TOP_CATEGORY_LABELS)
_add_execute_selected(_top_fal_menu)
