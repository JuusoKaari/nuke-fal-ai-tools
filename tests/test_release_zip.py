# Run: py -3 -m unittest tests.test_release_zip
# Fail CI if the release ZIP omits install files or ships development paths.

from __future__ import print_function

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PACK_SCRIPTS = os.path.join(_ROOT, ".github", "scripts")
if _PACK_SCRIPTS not in sys.path:
    sys.path.insert(0, _PACK_SCRIPTS)

from pack_release import PackError, pack_release_zip


INSTALL_PREFIX = "nuke-fal-ai-tools/"

REQUIRED_ZIP_FILES = (
    "nuke-fal-ai-tools/init.py",
    "nuke-fal-ai-tools/menu.py",
    "nuke-fal-ai-tools/requirements-python3.txt",
    "nuke-fal-ai-tools/README.md",
    "nuke-fal-ai-tools/LICENSE",
    "nuke-fal-ai-tools/docs/INSTALL.md",
    "nuke-fal-ai-tools/docs/troubleshooting.md",
)

REQUIRED_ZIP_PREFIXES = (
    "nuke-fal-ai-tools/nuke/groups/",
    "nuke-fal-ai-tools/nuke/python/",
)

FORBIDDEN_SEGMENTS = frozenset(
    (
        "tests",
        "dev_tools",
        "planning",
        "unattended-todo.json",
        ".git",
        ".github",
        "__pycache__",
        "dist",
    )
)


def _posix(name):
    return name.replace("\\", "/")


def layout_problems(names):
    """Return human-readable layout failures for ZIP member names."""
    names = [_posix(name) for name in names]
    problems = []
    name_set = set(names)
    for required in REQUIRED_ZIP_FILES:
        if required not in name_set:
            problems.append("missing %s" % required)
    for prefix in REQUIRED_ZIP_PREFIXES:
        if not any(name.startswith(prefix) for name in names):
            problems.append("missing tree %s" % prefix)
    for name in names:
        for part in name.split("/"):
            if part in FORBIDDEN_SEGMENTS:
                problems.append("forbidden %s in %s" % (part, name))
                break
    return problems


class TestReleaseZipLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="nuke-fal-zip-")
        cls._archive = os.path.join(cls._tmpdir, "nuke-fal-ai-tools-dev.zip")
        pack_release_zip(_ROOT, archive_path=cls._archive, version="dev")
        with zipfile.ZipFile(cls._archive, "r") as zf:
            cls._names = zf.namelist()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_packed_archive_matches_install_layout(self):
        self.assertTrue(os.path.isfile(self._archive), self._archive)
        self.assertEqual(layout_problems(self._names), [])
        self.assertIn(INSTALL_PREFIX + "init.py", self._names)
        self.assertIn(INSTALL_PREFIX + "tools/print_install_line.py", self._names)

    def test_layout_check_fails_when_tests_shipped(self):
        names = list(self._names) + ["nuke-fal-ai-tools/tests/test_foo.py"]
        problems = layout_problems(names)
        self.assertTrue(
            any("tests" in item for item in problems),
            problems,
        )

    def test_layout_check_fails_when_init_omitted(self):
        names = [
            name
            for name in self._names
            if _posix(name) != "nuke-fal-ai-tools/init.py"
        ]
        problems = layout_problems(names)
        self.assertTrue(
            any("init.py" in item for item in problems),
            problems,
        )

    def test_pack_fails_when_required_install_files_missing(self):
        empty = tempfile.mkdtemp(prefix="nuke-fal-empty-")
        try:
            archive = os.path.join(empty, "out.zip")
            with self.assertRaises(PackError):
                pack_release_zip(empty, archive_path=archive, version="dev")
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_release_workflow_uses_same_packer(self):
        path = os.path.join(_ROOT, ".github", "workflows", "release.yml")
        with open(path, "r") as handle:
            text = handle.read()
        self.assertIn(".github/scripts/pack_release.py", text)
        self.assertIn("python -m unittest discover -s tests", text)
