# Purpose:
# - Global fal.ai progress dialog for Nuke runner scripts (Python 2.7).
# - Wraps helper subprocess execution with nuke.ProgressTask, streams stdout to the Script Editor,
#   and maps common helper log lines to progress/message updates.

from __future__ import print_function

import json
import re
import subprocess

_DOWNLOAD_RE = re.compile(r"Downloading\s+(\d+)\s*/\s*(\d+)", re.I)
_UPLOAD_RE = re.compile(r"Uploading", re.I)
_SUBMIT_RE = re.compile(r"Submitting request", re.I)
_RETRY_RE = re.compile(r"WARNING:\s*fal request failed", re.I)
_ERROR_RE = re.compile(r"^ERROR:", re.I)


class FalProgressCancelled(Exception):
    """Raised when the user cancels the fal.ai progress dialog."""


def decode_subprocess_line(line):
    if line is None:
        return ""
    if isinstance(line, bytes):
        try:
            return line.decode("utf-8", "replace")
        except Exception:
            try:
                return str(line)
            except Exception:
                return ""
    try:
        return str(line)
    except Exception:
        return ""


def is_progress_noise(text):
    text = (text or "").strip()
    if not text:
        return True
    if "\r" in text and ("%|" in text or "|" in text and "/" in text):
        return True
    if text.startswith("100%|"):
        return True
    # tqdm / spinner fragments
    if len(text) > 60:
        sample = text[:40]
        if sample.count("|") >= 2 and sample.count("%") >= 1:
            return True
    return False


def progress_update_from_line(text, state):
    """
    Update `state` (dict with progress/message keys) from one helper stdout line.
    Returns True when the dialog should refresh.
    """
    text = (text or "").strip()
    if is_progress_noise(text):
        return False

    if _ERROR_RE.match(text):
        state["message"] = text[:160]
        return True

    if _RETRY_RE.search(text):
        state["progress"] = max(int(state.get("progress", 0)), 30)
        state["message"] = "Retrying fal.ai request..."
        return True

    match = _DOWNLOAD_RE.search(text)
    if match:
        current = int(match.group(1))
        total = max(1, int(match.group(2)))
        state["progress"] = min(95, 75 + int(20 * current / total))
        state["message"] = text[:160]
        state["phase"] = "download"
        return True

    if _UPLOAD_RE.search(text):
        state["progress"] = max(int(state.get("progress", 0)), 15)
        state["message"] = text[:160]
        state["phase"] = "upload"
        return True

    if _SUBMIT_RE.search(text):
        state["progress"] = max(int(state.get("progress", 0)), 25)
        state["message"] = text[:160]
        state["phase"] = "waiting"
        return True

    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("ok"):
                state["progress"] = 100
                state["message"] = "Done"
                state["phase"] = "done"
                return True
        except Exception:
            pass

    if state.get("phase") == "waiting":
        if len(text) <= 200 and not text.startswith("WARNING:"):
            state["progress"] = max(int(state.get("progress", 25)), 40)
            state["message"] = text[:160]
            return True

    return False


def _terminate_process(process):
    if process is None:
        return
    try:
        process.terminate()
    except Exception:
        pass
    try:
        process.kill()
    except Exception:
        pass


def _refresh_progress_task(task, state, nuke_module):
    try:
        task.setProgress(int(state.get("progress", 0)))
    except Exception:
        pass
    try:
        task.setMessage(str(state.get("message", "Running fal.ai...")))
    except Exception:
        pass
    try:
        nuke_module.updateUI()
    except Exception:
        pass


def run_helper_subprocess(args, env=None, title="fal.ai", initial_message="Starting fal.ai request..."):
    """
    Run a Python 3 helper subprocess with a global Nuke progress dialog.

    Returns (returncode, stdout_lines).
    Raises FalProgressCancelled when the user cancels the dialog.
    """
    import nuke

    state = {
        "progress": 0,
        "message": initial_message,
        "phase": "start",
    }

    task = nuke.ProgressTask(title or "fal.ai")
    _refresh_progress_task(task, state, nuke)

    stdout_lines = []
    process = None
    returncode = 1

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            env=env,
        )

        while True:
            if task.isCancelled():
                _terminate_process(process)
                raise FalProgressCancelled()

            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                _refresh_progress_task(task, state, nuke)
                continue

            text = decode_subprocess_line(line).rstrip("\r\n")
            stdout_lines.append(text)
            try:
                print(text)
            except Exception:
                pass

            if progress_update_from_line(text, state):
                _refresh_progress_task(task, state, nuke)

        returncode = int(process.wait())
        if returncode == 0:
            state["progress"] = 100
            state["message"] = "Done"
            _refresh_progress_task(task, state, nuke)
        return returncode, stdout_lines
    finally:
        try:
            del task
        except Exception:
            pass
