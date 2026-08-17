# Purpose:
# - fal.ai Settings panel (API key, optional output dir, connection test).
# - Output dir is used by runners via make_run_dirs when writable.
# - Test connection validates the key via fal platform models list (not a
#   generative run). Uses nukescripts.PythonPanel; optional Qt resize.
# - Python 2.7 compatible.

from __future__ import print_function

import os
import subprocess

import nuke
import nukescripts

import nuke_fal_config_v1 as fal_config
import nuke_fal_runner_util_v1 as runner_util


_KEY_HELP = (
    "Paste a new fal.ai API key below to replace the saved one, or leave the "
    "field blank to keep the key already stored in ~/.nuke-fal-ai/config.json.\n"
    "Cascade: studio-wide FAL_KEY (fallback) -> this Settings file (this machine) "
    "-> per-node FAL knob (script override). The Settings key is not written "
    "into your .nk script."
)

_OUT_HELP = (
    "Optional default output folder. When set and writable, Execute writes "
    "nuke_fal_temp/ and nuke_fal_output/ under this folder. Leave empty to "
    "keep writing next to the saved Nuke script."
)

_BTN_HELP = (
    "Save -- write the fields above to the config file "
    "(blank API key keeps the existing saved key).\n"
    "Clear key -- remove only the saved API key from the config file.\n"
    "Test connection -- check system Python 3, fal-client, and that the "
    "API key is accepted by fal.ai (models list ping; no generative run)."
)

# Comfortable open size so multiline help text is readable without shrinking.
_SETTINGS_PANEL_WIDTH = 640
_SETTINGS_PANEL_HEIGHT = 480
_SETTINGS_PANEL_TITLE = "fal.ai Settings"


def _import_qt_widgets():
    """Return QtWidgets (or PySide1 QtGui) module, or None if unavailable."""
    try:
        from PySide6 import QtWidgets
        return QtWidgets
    except Exception:
        pass
    try:
        from PySide2 import QtWidgets
        return QtWidgets
    except Exception:
        pass
    try:
        from PySide import QtGui
        return QtGui
    except Exception:
        return None


def _find_settings_panel_widget(panel, QtWidgets):
    """Locate the floating dialog widget for a shown PythonPanel."""
    for attr in ("_widget", "widget", "_window", "window"):
        candidate = getattr(panel, attr, None)
        if candidate is not None:
            return candidate
    mangled = getattr(panel, "_PythonPanel__widget", None)
    if mangled is not None:
        return mangled
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        return None
    if app is None:
        return None
    try:
        for w in app.topLevelWidgets():
            try:
                if w.isVisible() and w.windowTitle() == _SETTINGS_PANEL_TITLE:
                    return w
            except Exception:
                continue
    except Exception:
        return None
    return None


def _resize_settings_panel(panel, width=None, height=None):
    """
    Best-effort enlarge after show(). PythonPanel has no size API; use Qt
    when available. Failures are ignored so Nuke 8+ still opens the panel.
    """
    if width is None:
        width = _SETTINGS_PANEL_WIDTH
    if height is None:
        height = _SETTINGS_PANEL_HEIGHT
    try:
        QtWidgets = _import_qt_widgets()
        if QtWidgets is None:
            return
        widget = _find_settings_panel_widget(panel, QtWidgets)
        if widget is None:
            return
        try:
            widget.setMinimumWidth(int(width))
            widget.setMinimumHeight(int(height))
        except Exception:
            pass
        try:
            widget.resize(int(width), int(height))
        except Exception:
            pass
    except Exception:
        pass


def _default_python3_argv():
    """Platform default python3 launcher when no group node is selected."""
    class _Empty(object):
        def knob(self, _name):
            return None

    return runner_util.resolve_python3_cmd(_Empty())


def _make_key_knob(name, label, value):
    """Prefer Password_Knob when available; else String_Knob."""
    try:
        knob = nuke.Password_Knob(name, label)
    except Exception:
        knob = nuke.String_Knob(name, label)
    try:
        knob.setValue(value or "")
    except Exception:
        pass
    return knob


def _add_divider(panel, name):
    """Horizontal rule between sections (empty-label Text_Knob)."""
    panel.addKnob(nuke.Text_Knob(name, ""))


def _mask_key(key):
    """Short masked preview for status text (never show the full secret)."""
    key = (key or "").strip()
    if not key:
        return "(none)"
    if len(key) <= 8:
        return "set (%d chars)" % len(key)
    return "set (...%s, %d chars)" % (key[-4:], len(key))


def _key_status_text(key):
    return "Saved API key: %s" % _mask_key(key)


def resolve_key_for_test(panel_key):
    """
    Key for connection test: panel field if non-empty, else config, else env.
    Does not use a per-node knob (settings has no group context).
    """
    panel_key = (panel_key or "").strip()
    if panel_key and ("insert your secret" not in panel_key.lower()):
        return panel_key, "settings panel"
    cfg_key = fal_config.get_fal_key_from_config()
    if cfg_key:
        return cfg_key, "config file"
    env_key = (os.environ.get("FAL_KEY") or "").strip()
    if env_key:
        return env_key, "environment FAL_KEY"
    return "", "none"


def _decode_proc_output(b):
    if b is None:
        return ""
    if isinstance(b, bytes):
        # On Py2, bytes is an alias of str; decode still works for UTF-8 payloads.
        try:
            return b.decode("utf-8", "replace")
        except Exception:
            return str(b)
    return str(b)


def run_connection_test(fal_key, python3_argv=None):
    """
    Lightweight check via system Python 3 subprocess:
    1. fal_client imports
    2. SyncClient constructs with the key
    3. Authenticated GET https://api.fal.ai/v1/models?limit=1
       (validates the key with fal.ai; not a generative / paid model run)
    Returns (ok: bool, message: str).
    """
    if not (fal_key or "").strip():
        return False, (
            "No fal.ai API key found.\n\n"
            "Set one in fal.ai -> Settings..., or set the FAL_KEY environment variable."
        )

    if python3_argv is None:
        python3_argv = _default_python3_argv()

    # Runs under system Python 3. Keep this string ASCII-only.
    snippet = (
        "import os, sys\n"
        "try:\n"
        "    import fal_client\n"
        "except Exception as e:\n"
        "    sys.stderr.write('IMPORT_FAIL:%s\\n' % e)\n"
        "    sys.exit(1)\n"
        "key = (os.environ.get('FAL_KEY') or '').strip()\n"
        "if not key:\n"
        "    sys.stderr.write('NO_KEY\\n')\n"
        "    sys.exit(2)\n"
        "try:\n"
        "    fal_client.SyncClient(key=key)\n"
        "except Exception as e:\n"
        "    sys.stderr.write('CLIENT_FAIL:%s\\n' % e)\n"
        "    sys.exit(3)\n"
        "try:\n"
        "    from urllib.request import Request, urlopen\n"
        "    from urllib.error import HTTPError, URLError\n"
        "except ImportError:\n"
        "    from urllib2 import Request, urlopen, HTTPError, URLError\n"
        "url = 'https://api.fal.ai/v1/models?limit=1'\n"
        "req = Request(\n"
        "    url,\n"
        "    headers={\n"
        "        'Authorization': 'Key %s' % key,\n"
        "        'User-Agent': 'nuke-fal-ai-tools-settings',\n"
        "        'Accept': 'application/json',\n"
        "    },\n"
        ")\n"
        "try:\n"
        "    resp = urlopen(req, timeout=30)\n"
        "    try:\n"
        "        status = int(getattr(resp, 'status', None) or resp.getcode())\n"
        "    except Exception:\n"
        "        status = 200\n"
        "    try:\n"
        "        resp.read(64)\n"
        "    except Exception:\n"
        "        pass\n"
        "    if status < 200 or status >= 300:\n"
        "        sys.stderr.write('AUTH_FAIL:%s:unexpected status\\n' % status)\n"
        "        sys.exit(4)\n"
        "    sys.stdout.write('OK\\n')\n"
        "    sys.exit(0)\n"
        "except HTTPError as e:\n"
        "    body = b''\n"
        "    try:\n"
        "        body = e.read(500)\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        body_txt = body.decode('utf-8', 'replace')\n"
        "    except Exception:\n"
        "        body_txt = str(body)\n"
        "    sys.stderr.write('AUTH_FAIL:%s:%s\\n' % (getattr(e, 'code', 0), body_txt))\n"
        "    sys.exit(4)\n"
        "except URLError as e:\n"
        "    sys.stderr.write('NET_FAIL:%s\\n' % e)\n"
        "    sys.exit(5)\n"
        "except Exception as e:\n"
        "    sys.stderr.write('NET_FAIL:%s\\n' % e)\n"
        "    sys.exit(5)\n"
    )

    env = os.environ.copy()
    env["FAL_KEY"] = fal_key.strip()
    if "PYTHONUTF8" not in env:
        env["PYTHONUTF8"] = "1"
    if "PYTHONIOENCODING" not in env:
        env["PYTHONIOENCODING"] = "utf-8:replace"

    argv = list(python3_argv) + ["-c", snippet]
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        out_b, err_b = proc.communicate()
    except Exception as e:
        return False, (
            "Failed to launch system Python 3 (%s).\n\n"
            "Command: %s\n\n"
            "Install Python 3 and fal-client, or set Advanced / Python 3 cmd on a group node.\n"
            "See docs/INSTALL.md."
            % (e, " ".join(python3_argv))
        )

    out = _decode_proc_output(out_b).strip()
    err = _decode_proc_output(err_b).strip()
    code = int(proc.returncode or 0)

    if code == 0 and out.startswith("OK"):
        return True, (
            "fal.ai connection check passed.\n\n"
            "- API key is present\n"
            "- System Python 3 can import fal_client\n"
            "- fal.ai accepted the API key "
            "(GET /v1/models?limit=1)\n\n"
            "(No generative / paid model run was made.)"
        )

    if code == 1 or err.startswith("IMPORT_FAIL:"):
        detail = err.split("IMPORT_FAIL:", 1)[-1].strip() if "IMPORT_FAIL:" in err else err
        return False, (
            "System Python 3 could not import fal_client.\n\n"
            "%s\n\n"
            "Install with:\n"
            "  py -3 -m pip install -r requirements-python3.txt\n"
            "(or python3 -m pip ... on macOS/Linux)\n\n"
            "See docs/INSTALL.md."
            % (detail or err or "import failed")
        )

    if code == 2 or "NO_KEY" in err:
        return False, "API key was not passed to the helper process."

    if code == 3 or err.startswith("CLIENT_FAIL:"):
        detail = err.split("CLIENT_FAIL:", 1)[-1].strip() if "CLIENT_FAIL:" in err else err
        return False, (
            "fal_client.SyncClient failed to initialize with this key.\n\n%s"
            % (detail or err or "client init failed")
        )

    if code == 4 or err.startswith("AUTH_FAIL:"):
        detail = err.split("AUTH_FAIL:", 1)[-1].strip() if "AUTH_FAIL:" in err else err
        http_code = ""
        body = detail
        if ":" in detail:
            http_code, body = detail.split(":", 1)
            http_code = http_code.strip()
            body = body.strip()
        lines = [
            "fal.ai rejected this API key (or the auth request failed).",
            "",
        ]
        if http_code:
            lines.append("HTTP status: %s" % http_code)
        if body:
            lines.append(body[:800])
        lines.extend(
            [
                "",
                "Check the key at https://fal.ai/dashboard/keys",
                "then Save again in fal.ai -> Settings...",
            ]
        )
        return False, "\n".join(lines)

    if code == 5 or err.startswith("NET_FAIL:"):
        detail = err.split("NET_FAIL:", 1)[-1].strip() if "NET_FAIL:" in err else err
        return False, (
            "Could not reach fal.ai to validate the API key.\n\n"
            "%s\n\n"
            "Check internet access / proxy / firewall, then try again."
            % (detail or err or "network error")
        )

    return False, (
        "Connection check failed (exit %d).\n\nstdout:\n%s\n\nstderr:\n%s"
        % (code, out or "(empty)", err or "(empty)")
    )


class FalSettingsPanel(nukescripts.PythonPanel):
    """Settings UI with Save / Clear key / Test connection buttons."""

    def __init__(self):
        # No persistent id: Nuke would otherwise restore stale empty Password_Knob
        # values across sessions and hide the key loaded from config.
        nukescripts.PythonPanel.__init__(self, _SETTINGS_PANEL_TITLE)

        cfg = fal_config.load_config()
        self._saved_key = (cfg.get("fal_key") or "").strip()
        current_out = cfg.get("output_dir") or ""

        self.addKnob(nuke.Text_Knob("key_help", "", _KEY_HELP))
        self._key_status = nuke.Text_Knob("key_status", "", _key_status_text(self._saved_key))
        self.addKnob(self._key_status)
        # Leave the field empty on open. Password_Knob often will not display a
        # restored secret; blank means "keep saved key" on Save.
        self._key = _make_key_knob("api_key", "New API key (optional)", "")
        self.addKnob(self._key)

        _add_divider(self, "div_after_key")

        self.addKnob(nuke.Text_Knob("out_help", "", _OUT_HELP))
        self._out = nuke.File_Knob("output_dir", "Default output folder")
        self.addKnob(self._out)
        try:
            self._out.setValue(current_out or "")
        except Exception:
            pass

        _add_divider(self, "div_after_out")

        self.addKnob(nuke.Text_Knob("btn_help", "", _BTN_HELP))

        _add_divider(self, "div_before_buttons")

        self._btn_save = nuke.PyScript_Knob("save_settings", "Save")
        self._btn_save.setFlag(nuke.STARTLINE)
        self.addKnob(self._btn_save)

        self._btn_clear = nuke.PyScript_Knob("clear_key", "Clear key")
        self.addKnob(self._btn_clear)

        self._btn_test = nuke.PyScript_Knob("test_connection", "Test connection")
        self.addKnob(self._btn_test)

    def _refresh_key_status(self, key=None):
        if key is None:
            key = self._saved_key
        try:
            self._key_status.setValue(_key_status_text(key))
        except Exception:
            pass

    def _read_fields(self):
        try:
            key = self._key.value() or ""
        except Exception:
            key = ""
        try:
            out = self._out.value() or ""
        except Exception:
            out = ""
        return str(key), str(out)

    def _on_save(self):
        panel_key, panel_out = self._read_fields()
        panel_key = (panel_key or "").strip()
        # Blank password field means keep the existing saved key.
        if panel_key and ("insert your secret" not in panel_key.lower()):
            key_to_save = panel_key
        else:
            key_to_save = self._saved_key
        fal_config.save_config({"fal_key": key_to_save, "output_dir": panel_out})
        self._saved_key = (key_to_save or "").strip()
        self._refresh_key_status(self._saved_key)
        try:
            self._key.setValue("")
        except Exception:
            pass
        saved = fal_config.config_path()
        has_key = bool(self._saved_key)
        has_out = bool((panel_out or "").strip())
        nuke.message(
            "Settings saved to:\n%s\n\nAPI key: %s\nDefault output folder: %s"
            % (
                saved,
                "set" if has_key else "empty",
                "set" if has_out else "empty (use script folder)",
            )
        )

    def _on_clear(self):
        _panel_key, panel_out = self._read_fields()
        fal_config.save_config({"fal_key": "", "output_dir": panel_out})
        self._saved_key = ""
        self._refresh_key_status("")
        try:
            self._key.setValue("")
        except Exception:
            pass
        nuke.message("API key cleared from ~/.nuke-fal-ai/config.json.")

    def _on_test(self):
        panel_key, _panel_out = self._read_fields()
        key, source = resolve_key_for_test(panel_key)
        _ok, msg = run_connection_test(key)
        nuke.message("Key source: %s\n\n%s" % (source, msg))

    def knobChanged(self, knob):
        if knob is self._btn_save:
            self._on_save()
        elif knob is self._btn_clear:
            self._on_clear()
        elif knob is self._btn_test:
            self._on_test()


def show_settings_panel():
    """Open fal.ai Settings panel. Returns True after the panel is shown."""
    panel = FalSettingsPanel()
    # Non-modal so Save / Clear / Test can run without closing first.
    try:
        panel.show()
    except Exception:
        # Older Nuke builds may only support modal show.
        panel.showModalDialog()
    _resize_settings_panel(panel)
    return True
