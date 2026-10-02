# Run: py -3 -m unittest tests.test_hidden_input_connectors
# Connector Dots for Group inputs past the first 4. No Nuke required.

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_hidden_input_connectors_v1 as connectors


class _Knob(object):
    def __init__(self, name, label="", value=None):
        self._name = name
        self._label = label
        self._value = value
        self.flags = []
        self.tooltip = ""

    def name(self):
        return self._name

    def label(self):
        return self._label

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value

    def setFlag(self, flag):
        self.flags.append(flag)

    def setTooltip(self, text):
        self.tooltip = text


class _Node(object):
    def __init__(self, klass, name):
        self._class = klass
        self._name = name
        self._knobs = {"selected": _Knob("selected", "selected", False)}
        self._inputs = {}
        self._children = []
        self._x = 0
        self._y = 0

    def Class(self):
        return self._class

    def name(self):
        return self._name

    def knob(self, name):
        return self._knobs.get(name)

    def __getitem__(self, key):
        return self._knobs[key]

    def addKnob(self, knob):
        self._knobs[knob.name()] = knob

    def nodes(self):
        return list(self._children)

    def input(self, index):
        return self._inputs.get(int(index))

    def setInput(self, index, node):
        self._inputs[int(index)] = node

    def setXYpos(self, x, y):
        self._x = int(x)
        self._y = int(y)

    def xpos(self):
        return self._x

    def ypos(self):
        return self._y

    def begin(self):
        return None

    def end(self):
        return None


class _NodeFactory(object):
    def __init__(self, nuke_mod):
        self._nuke = nuke_mod

    def Dot(self):
        dot = _Node("Dot", "Dot%d" % (len(self._nuke.root_nodes) + 1))
        dot._knobs["label"] = _Knob("label", "label", "")
        self._nuke.root_nodes.append(dot)
        return dot


class _FakeNuke(object):
    def __init__(self):
        self.messages = []
        self.shown = []
        self.deleted = []
        self.script_load_callbacks = []
        self.root_nodes = []
        self.nodes = _NodeFactory(self)
        self.STARTLINE = "STARTLINE"
        self._this_node = None
        self._this_knob = None

    def allNodes(self, klass=None):
        nodes = list(self.root_nodes)
        if klass:
            nodes = [node for node in nodes if node.Class() == klass]
        return nodes

    def message(self, text):
        self.messages.append(text)

    def show(self, node):
        self.shown.append(node)

    def delete(self, node):
        self.deleted.append(node)
        if node in self.root_nodes:
            self.root_nodes.remove(node)

    def thisNode(self):
        return self._this_node

    def thisKnob(self):
        return self._this_knob

    def thisGroup(self):
        return None

    def endGroup(self):
        return None

    def addOnScriptLoad(self, callback):
        self.script_load_callbacks.append(callback)

    def Tab_Knob(self, name, label):
        return _Knob(name, label, "")

    def Text_Knob(self, name, label, text=""):
        return _Knob(name, label, text)

    def PyScript_Knob(self, name, label, script=""):
        return _Knob(name, label, script)


def _add_input(group, name, number=None, xpos=0):
    node = _Node("Input", name)
    node.setXYpos(xpos, -40)
    if number is not None:
        node.addKnob(_Knob("number", "number", number))
    group._children.append(node)
    return node


def _mark_fal(group):
    group.addKnob(_Knob("helper_path", "Helper path", "helper.py"))
    group.addKnob(_Knob("runner_path", "Runner path", "runner.py"))


def _seedance_like(fake, with_fal_knobs=True):
    """image_1..image_5 plus video_1. image_1 has no number knob (Nuke default)."""
    group = _Node("Group", "Seedance_2_Reference_To_Video_v1")
    group.setXYpos(200, 100)
    _add_input(group, "image_1", number=None, xpos=0)
    _add_input(group, "image_2", number=1, xpos=80)
    _add_input(group, "image_3", number=2, xpos=160)
    _add_input(group, "image_4", number=3, xpos=240)
    _add_input(group, "image_5", number=4, xpos=320)
    _add_input(group, "video_1", number=9, xpos=0)
    if with_fal_knobs:
        _mark_fal(group)
    fake.root_nodes.append(group)
    return group


def _four_input_group(fake):
    group = _Node("Group", "Small_v1")
    group.setXYpos(200, 100)
    for index, name in enumerate(("start_image", "end_image", "prompt_text", "mask")):
        _add_input(group, name, number=index, xpos=index * 80)
    _mark_fal(group)
    fake.root_nodes.append(group)
    return group


def _dots(fake):
    return [node for node in fake.root_nodes if node.Class() == "Dot"]


class TestArtistLabels(unittest.TestCase):
    def test_labels_come_from_input_names(self):
        self.assertEqual(
            connectors.artist_label_from_input_name("video_1"), "Video Input 1"
        )
        self.assertEqual(
            connectors.connector_button_label("video_1"), "Create Video Input 1"
        )
        self.assertEqual(connectors.connector_dot_label("video_1"), "VIDEO INPUT 1")
        self.assertEqual(
            connectors.artist_label_from_input_name("image_5"), "Image Input 5"
        )
        self.assertEqual(
            connectors.artist_label_from_input_name("keyframe_10"),
            "Keyframe Input 10",
        )
        self.assertEqual(
            connectors.artist_label_from_input_name("ref_image_4"),
            "Ref Image Input 4",
        )
        self.assertEqual(
            connectors.artist_label_from_input_name("prompt_text"), "Prompt Text"
        )
        self.assertEqual(
            connectors.artist_label_from_input_name("video_input_1"),
            "Video Input 1",
        )

    def test_module_source_is_ascii(self):
        path = os.path.join(_PYTHON_DIR, "nuke_hidden_input_connectors_v1.py")
        with open(path, "rb") as handle:
            handle.read().decode("ascii")


class TestHiddenInputButtons(unittest.TestCase):
    def test_four_or_fewer_inputs_add_no_actions(self):
        fake = _FakeNuke()
        group = _four_input_group(fake)
        names = connectors.ensure_hidden_input_connector_knobs(
            group, nuke_module=fake
        )
        self.assertEqual(names, [])
        self.assertIsNone(group.knob(connectors.CONNECT_TAB_KNOB))
        self.assertEqual(_dots(fake), [])

    def test_hidden_inputs_get_one_button_each(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        names = connectors.ensure_hidden_input_connector_knobs(
            group, nuke_module=fake
        )
        self.assertEqual(
            names,
            [
                connectors.connector_knob_name(4),
                connectors.connector_knob_name(9),
            ],
        )
        image_button = group.knob(connectors.connector_knob_name(4))
        video_button = group.knob(connectors.connector_knob_name(9))
        self.assertEqual(image_button.label(), "Create Image Input 5")
        self.assertEqual(video_button.label(), "Create Video Input 1")
        self.assertEqual(image_button.value(), connectors.BUTTON_SCRIPT)
        self.assertIn("STARTLINE", image_button.flags)
        self.assertIn("video_1", video_button.tooltip)

        again = connectors.ensure_hidden_input_connector_knobs(
            group, nuke_module=fake
        )
        self.assertEqual(again, names)
        self.assertIs(group.knob(connectors.connector_knob_name(4)), image_button)

    def test_unnumbered_first_input_is_index_zero(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        specs = connectors.list_group_inputs(group, nuke_module=fake)
        by_name = dict((spec["name"], spec["index"]) for spec in specs)
        self.assertEqual(by_name["image_1"], 0)
        self.assertEqual(by_name["image_5"], 4)
        self.assertEqual(by_name["video_1"], 9)
        hidden = connectors.hidden_input_specs(specs)
        self.assertEqual([spec["name"] for spec in hidden], ["image_5", "video_1"])


class TestCreateConnector(unittest.TestCase):
    def test_creates_labeled_dot_and_connects_hidden_input(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        result = connectors.create_or_reveal_input_connector(
            group, 9, nuke_module=fake
        )
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["label"], "VIDEO INPUT 1")
        dot = result["node"]
        self.assertEqual(dot.Class(), "Dot")
        self.assertEqual(dot.knob("label").value(), "VIDEO INPUT 1")
        self.assertIs(group.input(9), dot)
        self.assertNotIn(dot, group.nodes())
        self.assertIn(dot, fake.root_nodes)
        self.assertEqual(dot.xpos(), 200 + connectors.DOT_OFFSET_X)
        self.assertEqual(dot.ypos(), 100 + (5 * connectors.DOT_STAGGER_Y))
        self.assertTrue(dot.knob("selected").value())
        self.assertEqual(fake.messages, [])
        self.assertEqual(fake.shown, [])

    def test_staggers_multiple_connectors(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        first = connectors.create_or_reveal_input_connector(
            group, 4, nuke_module=fake
        )
        second = connectors.create_or_reveal_input_connector(
            group, 9, nuke_module=fake
        )
        self.assertEqual(first["label"], "IMAGE INPUT 5")
        self.assertNotEqual(first["node"].ypos(), second["node"].ypos())
        self.assertEqual(
            second["node"].ypos() - first["node"].ypos(),
            5 * connectors.DOT_STAGGER_Y,
        )
        self.assertEqual(len(_dots(fake)), 2)

    def test_second_click_selects_existing_dot(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        group.knob("selected").setValue(True)
        first = connectors.create_or_reveal_input_connector(
            group, 4, nuke_module=fake
        )
        first["node"].knob("label").setValue("renamed a bit")
        group.knob("selected").setValue(True)
        second = connectors.create_or_reveal_input_connector(
            group, 4, nuke_module=fake
        )
        self.assertEqual(second["action"], "revealed")
        self.assertIs(second["node"], first["node"])
        self.assertIs(group.input(4), first["node"])
        self.assertEqual(len(_dots(fake)), 1)
        self.assertEqual(first["node"].knob("label").value(), "renamed a bit")
        self.assertTrue(first["node"].knob("selected").value())
        self.assertFalse(group.knob("selected").value())
        self.assertEqual(fake.messages, [])
        self.assertEqual(fake.shown, [first["node"]])

    def test_does_not_clobber_existing_connection(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        read = _Node("Read", "Read1")
        fake.root_nodes.append(read)
        group.setInput(4, read)
        group.knob("selected").setValue(True)
        result = connectors.create_or_reveal_input_connector(
            group, 4, nuke_module=fake
        )
        self.assertEqual(result["action"], "left_existing")
        self.assertIs(result["node"], read)
        self.assertIs(group.input(4), read)
        self.assertEqual(_dots(fake), [])
        self.assertTrue(read.knob("selected").value())
        self.assertFalse(group.knob("selected").value())
        self.assertEqual(fake.shown, [read])
        self.assertEqual(len(fake.messages), 1)
        self.assertIn("Image Input 5", fake.messages[0])
        self.assertIn("Read1", fake.messages[0])
        self.assertIn("Left that connection in place", fake.messages[0])

    def test_visible_input_is_ignored(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        result = connectors.create_or_reveal_input_connector(
            group, 1, nuke_module=fake
        )
        self.assertEqual(result["action"], "ignored")
        self.assertEqual(_dots(fake), [])
        self.assertIsNone(group.input(1))

    def test_button_callback_uses_knob_name(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        connectors.ensure_hidden_input_connector_knobs(group, nuke_module=fake)
        fake._this_node = group
        fake._this_knob = group.knob(connectors.connector_knob_name(9))
        result = connectors.on_create_connector_button(nuke_module=fake)
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["label"], "VIDEO INPUT 1")
        self.assertIs(group.input(9), result["node"])

    def test_autoconnected_dot_input_is_cleared(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        original = fake.nodes.Dot

        def _dot():
            dot = original()
            dot.setInput(0, group)
            return dot

        fake.nodes.Dot = _dot
        result = connectors.create_or_reveal_input_connector(
            group, 4, nuke_module=fake
        )
        self.assertIsNone(result["node"].input(0))
        self.assertIs(group.input(4), result["node"])

    def test_occupied_tile_is_nudged(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        blocker = _Node("Dot", "Blocker")
        base_x, base_y = connectors.connector_dot_position(200, 100, 4)
        blocker.setXYpos(base_x, base_y)
        fake.root_nodes.append(blocker)
        result = connectors.create_or_reveal_input_connector(
            group, 4, nuke_module=fake
        )
        dot = result["node"]
        self.assertNotEqual((dot.xpos(), dot.ypos()), (base_x, base_y))
        self.assertIs(group.input(4), dot)


class TestScriptUpgrade(unittest.TestCase):
    def test_upgrade_skips_groups_that_are_not_fal_nodes(self):
        fake = _FakeNuke()
        plain = _seedance_like(fake, with_fal_knobs=False)
        plain._name = "UserGroup"
        fal = _four_input_group(fake)
        _add_input(fal, "extra_5", number=4, xpos=320)
        connectors.upgrade_open_script_groups(fake)
        self.assertIsNone(plain.knob(connectors.CONNECT_TAB_KNOB))
        self.assertIsNotNone(fal.knob(connectors.connector_knob_name(4)))
        self.assertEqual(
            fal.knob(connectors.connector_knob_name(4)).label(),
            "Create Extra Input 5",
        )

    def test_script_load_hook_runs_upgrade(self):
        fake = _FakeNuke()
        group = _seedance_like(fake)
        callback = connectors.install_script_load_hook(fake)
        self.assertEqual(fake.script_load_callbacks, [callback])
        self.assertIsNone(group.knob(connectors.CONNECT_TAB_KNOB))
        callback()
        self.assertEqual(
            group.knob(connectors.connector_knob_name(9)).label(),
            "Create Video Input 1",
        )

    def test_menu_wires_shared_helper(self):
        menu_path = os.path.join(_ROOT, "menu.py")
        with open(menu_path, "r") as handle:
            text = handle.read()
        self.assertIn("ensure_hidden_input_connector_knobs", text)
        self.assertIn("install_script_load_hook", text)
        self.assertNotIn("seedance", text.lower())


if __name__ == "__main__":
    unittest.main()
