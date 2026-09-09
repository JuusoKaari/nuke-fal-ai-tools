# Scan tracked files for secrets, personal home paths, and DevTools clutter (R7).
# Fail CI if git ls-files grows a private runner, a real-looking credential, or a
# machine-specific Users/... path. Do not print matched secret text.

from __future__ import print_function

import os
import re
import subprocess
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# Root-only private planning. docs/planning/ is the public release spec.
FORBIDDEN_TRACKED_PREFIXES = (
    "dev_tools/",
    "planning/",
    ".cursor/",
    "nuke_fal_output/",
    "dist/",
)

FORBIDDEN_TRACKED_NAMES = frozenset(
    (
        "unattended-todo.json",
        "TODO.md",
        "proposed-tools.md",
    )
)

SKIP_TEXT_SUFFIXES = (
    ".gif",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp4",
    ".pyc",
    ".pyo",
    ".pyd",
    ".zip",
)

# Docs/tests may use these usernames as install examples, not a real home.
_PLACEHOLDER_USERS = frozenset(("you", "<you>", "public", "default", "all users"))

_WIN_HOME = re.compile(
    r"C:[/\\]+Users[/\\]+([^\s/\\\"'`]+)",
    re.IGNORECASE,
)
_UNIX_HOME = re.compile(
    r"(?:/Users|/home)/([^\s/\"'`]+)",
)
_PEM = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")
_GH_PAT = re.compile(r"\bghp_[A-Za-z0-9]{20,}")
_GH_FINE = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")
_OPENROUTER = re.compile(r"\bsk-or-v1-[A-Za-z0-9]{10,}")
_AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_FAL_UUID_KEY = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r":[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_FAL_KNOB = re.compile(r'^[ \t]*FAL[ \t]+"([^"]*)"', re.MULTILINE)
_ALLOWED_FAL_KNOB = frozenset(
    (
        "",
        "insert fal key to override for this node",
    )
)


def _posix(path):
    return path.replace("\\", "/")


def is_forbidden_tracked_path(rel):
    """True if this git path belongs in DevTools or must not be committed."""
    rel = _posix(rel)
    base = os.path.basename(rel)
    if base in FORBIDDEN_TRACKED_NAMES and (
        rel == base or base == "unattended-todo.json"
    ):
        return True
    for prefix in FORBIDDEN_TRACKED_PREFIXES:
        name = prefix.rstrip("/")
        if rel == name or rel.startswith(prefix):
            return True
    if rel.endswith(".pyc") or rel.endswith(".pyo") or rel.endswith(".pyd"):
        return True
    if "/__pycache__/" in "/" + rel or rel.startswith("__pycache__/"):
        return True
    return False


def _user_is_placeholder(name):
    return name.strip().lower() in _PLACEHOLDER_USERS


def personal_home_hits(text):
    """Return kinds of personal home paths (no matched values)."""
    kinds = []
    for match in _WIN_HOME.finditer(text):
        if not _user_is_placeholder(match.group(1)):
            kinds.append("windows-home")
            break
    for match in _UNIX_HOME.finditer(text):
        if not _user_is_placeholder(match.group(1)):
            kinds.append("unix-home")
            break
    return kinds


def credential_hits(text):
    """Return kinds of credential-shaped tokens (no matched values)."""
    kinds = []
    if _PEM.search(text):
        kinds.append("pem-private-key")
    if _GH_PAT.search(text):
        kinds.append("github-pat")
    if _GH_FINE.search(text):
        kinds.append("github-fine-pat")
    if _OPENROUTER.search(text):
        kinds.append("openrouter-key")
    if _AWS.search(text):
        kinds.append("aws-access-key")
    if _FAL_UUID_KEY.search(text):
        kinds.append("fal-uuid-key")
    return kinds


def fal_knob_hits(text):
    """Return True if an .nk FAL knob is not the public placeholder."""
    for match in _FAL_KNOB.finditer(text):
        if match.group(1) not in _ALLOWED_FAL_KNOB:
            return True
    return False


def tracked_files():
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=_ROOT,
    )
    names = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        names.append(_posix(raw.decode("utf-8")))
    return names


def _read_text(rel):
    path = os.path.join(_ROOT, rel.replace("/", os.sep))
    with open(path, "rb") as handle:
        data = handle.read()
    return data.decode("utf-8")


class TestTrackedHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._files = tracked_files()

    def test_no_devtools_or_private_planning_paths(self):
        bad = [name for name in self._files if is_forbidden_tracked_path(name)]
        self.assertEqual(bad, [])

    def test_public_release_spec_is_still_tracked(self):
        self.assertIn("docs/planning/v1.1.0-release-prep.md", self._files)

    def test_tracked_text_has_no_personal_homes_or_credentials(self):
        problems = []
        for rel in self._files:
            lower = rel.lower()
            if any(lower.endswith(suf) for suf in SKIP_TEXT_SUFFIXES):
                continue
            try:
                text = _read_text(rel)
            except UnicodeDecodeError:
                continue
            for kind in personal_home_hits(text) + credential_hits(text):
                problems.append("%s (%s)" % (rel, kind))
            if lower.endswith(".nk") and fal_knob_hits(text):
                problems.append("%s (fal-knob)" % rel)
        self.assertEqual(problems, [])

    def test_forbidden_path_helper_catches_devtools(self):
        self.assertTrue(is_forbidden_tracked_path("dev_tools/run_todo.py"))
        self.assertTrue(is_forbidden_tracked_path("unattended-todo.json"))
        self.assertTrue(is_forbidden_tracked_path("TODO.md"))
        self.assertTrue(is_forbidden_tracked_path("planning/notes.md"))
        self.assertFalse(
            is_forbidden_tracked_path("docs/planning/v1.1.0-release-prep.md")
        )
        self.assertFalse(is_forbidden_tracked_path("nuke/python/fal_common.py"))

    def test_detectors_flag_constructed_samples_without_storing_secrets(self):
        win = "C:/Users/" + "alice" + "/.nuke"
        unix = "/Users/" + "alice" + "/.nuke"
        self.assertIn("windows-home", personal_home_hits(win))
        self.assertIn("unix-home", personal_home_hits(unix))
        self.assertEqual(
            personal_home_hits(r"C:\Users\<you>\.nuke"),
            [],
        )
        self.assertEqual(personal_home_hits("/Users/you/tools/nuke-fal-ai-tools"), [])
        pat = "ghp_" + ("a" * 36)
        self.assertIn("github-pat", credential_hits(pat))
        self.assertFalse(
            fal_knob_hits(' FAL "insert fal key to override for this node"\n')
        )
        self.assertTrue(fal_knob_hits(' FAL "' + ("abcd" * 8) + '"\n'))
