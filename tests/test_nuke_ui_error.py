# Run: py -3 -m unittest tests.test_nuke_ui_error
# Pure-logic tests for unexpected Nuke UI error dialogs (no Nuke required).

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import nuke_ui_error_v1 as ui_error


class _FakeNuke(object):
    def __init__(self):
        self.messages = []

    def message(self, text):
        self.messages.append(text)


class TestUnexpectedUiErrorMessage(unittest.TestCase):
    def test_includes_exception_and_restart_hint(self):
        exc = AttributeError(
            "module 'nuke_prerender_v1' has no attribute 'group_scope'"
        )
        text = ui_error.unexpected_ui_error_message(
            "clear generation history", exc
        )
        self.assertIn("Could not clear generation history.", text)
        self.assertIn("AttributeError", text)
        self.assertIn("group_scope", text)
        self.assertIn("restart Nuke", text)
        self.assertIn("Script Editor", text)
        self.assertNotIn("\u2014", text)
        self.assertNotIn("\u2013", text)

    def test_empty_action_and_none_exc(self):
        text = ui_error.unexpected_ui_error_message("", None)
        self.assertIn("Could not complete this action.", text)
        self.assertIn("Error", text)
        self.assertIn("restart Nuke", text)


class TestReportUnexpectedUiError(unittest.TestCase):
    def test_shows_dialog_and_does_not_raise(self):
        fake = _FakeNuke()
        try:
            raise AttributeError(
                "module 'nuke_prerender_v1' has no attribute 'group_scope'"
            )
        except Exception as exc:
            ui_error.report_unexpected_ui_error(
                "clear generation history",
                exc,
                nuke_module=fake,
                print_traceback=False,
            )
        self.assertEqual(len(fake.messages), 1)
        self.assertIn("group_scope", fake.messages[0])
        self.assertIn("restart Nuke", fake.messages[0])

    def test_message_failure_is_swallowed(self):
        class _BrokenNuke(object):
            def message(self, text):
                raise RuntimeError("dialog failed")

        try:
            raise ValueError("boom")
        except Exception as exc:
            ui_error.report_unexpected_ui_error(
                "extract the selected generation",
                exc,
                nuke_module=_BrokenNuke(),
                print_traceback=False,
            )


if __name__ == "__main__":
    unittest.main()
