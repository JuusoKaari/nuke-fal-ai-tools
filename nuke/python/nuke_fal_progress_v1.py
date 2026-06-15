# Purpose:
# - Global fal.ai progress dialog for Nuke runner scripts (Python 2.7).
# - Wraps helper subprocess execution with nuke.ProgressTask, streams stdout to the Script Editor,
#   and maps common helper log lines to progress/message updates.

from __future__ import print_function

import json
import re
import subprocess
import threading

try:
    import Queue as _queue_mod
except ImportError:
    import queue as _queue_mod

_POLL_TIMEOUT_SEC = 0.1

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
    Update `state` (dict with message/phase keys) from one helper stdout line.
    Returns True when the dialog should refresh.
    """
    text = (text or "").strip()
    if is_progress_noise(text):
        return False

    if _ERROR_RE.match(text):
        state["message"] = text[:160]
        return True

    if _RETRY_RE.search(text):
        state["message"] = "Retrying fal.ai request..."
        return True

    match = _DOWNLOAD_RE.search(text)
    if match:
        state["message"] = text[:160]
        state["phase"] = "download"
        return True

    if _UPLOAD_RE.search(text):
        state["message"] = text[:160]
        state["phase"] = "upload"
        return True

    if _SUBMIT_RE.search(text):
        state["message"] = text[:160]
        state["phase"] = "waiting"
        return True

    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("ok"):
                state["message"] = "Done"
                state["phase"] = "done"
                return True
        except Exception:
            pass

    if state.get("phase") == "waiting":
        if len(text) <= 200 and not text.startswith("WARNING:"):
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
    # Only setMessage: setProgress drives Nuke's time-remaining estimate, which
    # is misleading for long unpredictable fal.ai queue waits.
    try:
        task.setMessage(str(state.get("message", "Running fal.ai...")))
    except Exception:
        pass
    try:
        nuke_module.updateUI()
    except Exception:
        pass


def _start_stdout_reader(process, line_queue):
    def _reader():
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line_queue.put(line)
        finally:
            line_queue.put(None)

    thread = threading.Thread(target=_reader)
    thread.daemon = True
    thread.start()
    return thread


def run_helper_subprocess(args, env=None, title="fal.ai", initial_message="Running fal.ai request..."):
    """
    Run a Python 3 helper subprocess with a global Nuke progress dialog.

    Returns (returncode, stdout_lines).
    Raises FalProgressCancelled when the user cancels the dialog.
    """
    import nuke

    state = {
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

        line_queue = _queue_mod.Queue()
        reader_thread = _start_stdout_reader(process, line_queue)

        while True:
            if task.isCancelled():
                _terminate_process(process)
                raise FalProgressCancelled()

            try:
                line = line_queue.get(timeout=_POLL_TIMEOUT_SEC)
            except _queue_mod.Empty:
                if process.poll() is not None and line_queue.empty():
                    break
                if state.get("phase") == "start":
                    state["phase"] = "running"
                    state["message"] = initial_message
                _refresh_progress_task(task, state, nuke)
                continue

            if line is None:
                break

            text = decode_subprocess_line(line).rstrip("\r\n")
            stdout_lines.append(text)
            try:
                print(text)
            except Exception:
                pass

            if progress_update_from_line(text, state):
                _refresh_progress_task(task, state, nuke)

        try:
            reader_thread.join(timeout=1.0)
        except Exception:
            pass

        returncode = int(process.wait())
        if returncode == 0:
            state["message"] = "Done"
            _refresh_progress_task(task, state, nuke)
        return returncode, stdout_lines
    finally:
        try:
            del task
        except Exception:
            pass
