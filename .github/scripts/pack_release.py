# Purpose: Build the artist install ZIP from an explicit path allowlist (CI and local dry pack).

"""Pack nuke-fal-ai-tools as an install tree, not a development checkout.

Run without a git tag:

    python .github/scripts/pack_release.py

Default output is dist/nuke-fal-ai-tools-dev.zip. Tests import this module and
call pack_release_zip() / collect_install_members(), then extract and compile.
"""

from __future__ import print_function

import argparse
import os
import sys
import zipfile


INSTALL_ROOT_NAME = "nuke-fal-ai-tools"
DEFAULT_VERSION = "dev"

# Files that must exist at the repo root of the ZIP.
REQUIRED_FILES = (
    "init.py",
    "menu.py",
    "requirements-python3.txt",
    "README.md",
    "LICENSE",
    "docs/INSTALL.md",
    "docs/troubleshooting.md",
    "tools/print_install_line.py",
)

# Shipped only when present (README references it).
OPTIONAL_FILES = (
    "docs/demo.gif",
)

# Copy the whole tree so new runtime files under nuke/ are not omitted.
TREE_DIRS = (
    "nuke",
)

SKIP_DIR_NAMES = (
    "__pycache__",
    ".git",
    ".github",
    ".cursor",
)

BYTECODE_SUFFIXES = (".pyc", ".pyo", ".pyd")

_JUNK_NAMES = (
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
)


class PackError(Exception):
    """Install tree is missing a required path."""


def _repo_root_from_script():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(scripts_dir, "..", ".."))


def _posix_rel(path):
    return path.replace("\\", "/")


def _is_bytecode_name(name):
    lower = name.lower()
    return lower.endswith(BYTECODE_SUFFIXES)


def _is_junk_name(name):
    return name.lower() in _JUNK_NAMES


def _join_root(repo_root, rel):
    parts = rel.replace("\\", "/").split("/")
    return os.path.join(repo_root, *parts)


def _zip_name(rel):
    return "%s/%s" % (INSTALL_ROOT_NAME, _posix_rel(rel))


def collect_install_members(repo_root):
    """Return (abs_src, zip_name) pairs for the install ZIP, sorted by zip_name."""
    repo_root = os.path.abspath(repo_root)
    members = []
    seen = set()

    for rel in REQUIRED_FILES:
        src = _join_root(repo_root, rel)
        if not os.path.isfile(src):
            raise PackError("required install file missing: %s" % rel)
        zip_name = _zip_name(rel)
        members.append((src, zip_name))
        seen.add(zip_name)

    for rel in OPTIONAL_FILES:
        src = _join_root(repo_root, rel)
        if os.path.isfile(src):
            zip_name = _zip_name(rel)
            members.append((src, zip_name))
            seen.add(zip_name)

    for tree in TREE_DIRS:
        abs_tree = _join_root(repo_root, tree)
        if not os.path.isdir(abs_tree):
            raise PackError("required install directory missing: %s/" % tree)
        for dirpath, dirnames, filenames in os.walk(abs_tree):
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if name not in SKIP_DIR_NAMES and not name.startswith(".")
            ]
            for name in sorted(filenames):
                if _is_bytecode_name(name) or _is_junk_name(name):
                    continue
                src = os.path.join(dirpath, name)
                rel = _posix_rel(os.path.relpath(src, repo_root))
                zip_name = _zip_name(rel)
                if zip_name in seen:
                    continue
                members.append((src, zip_name))
                seen.add(zip_name)

    members.sort(key=lambda item: item[1])
    return members


def default_archive_path(repo_root, version=DEFAULT_VERSION):
    name = "nuke-fal-ai-tools-%s.zip" % version
    return os.path.join(os.path.abspath(repo_root), "dist", name)


def pack_release_zip(repo_root, archive_path=None, version=DEFAULT_VERSION):
    """Write the install ZIP. Returns the archive path."""
    repo_root = os.path.abspath(repo_root)
    if not archive_path:
        archive_path = default_archive_path(repo_root, version)
    archive_path = os.path.abspath(archive_path)

    groups = _join_root(repo_root, "nuke/groups")
    python_dir = _join_root(repo_root, "nuke/python")
    if not os.path.isdir(groups):
        raise PackError("required install directory missing: nuke/groups/")
    if not os.path.isdir(python_dir):
        raise PackError("required install directory missing: nuke/python/")

    members = collect_install_members(repo_root)
    parent = os.path.dirname(archive_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.isfile(archive_path):
        os.remove(archive_path)

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, zip_name in members:
            zf.write(src, zip_name)
    return archive_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pack the nuke-fal-ai-tools install ZIP from an allowlist."
    )
    parser.add_argument(
        "--root",
        default=_repo_root_from_script(),
        help="Repository root (default: two levels above this script).",
    )
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help="Archive suffix (default: %s). Release CI passes the git tag." % DEFAULT_VERSION,
    )
    parser.add_argument(
        "--output",
        default="",
        help="Zip path. Default: <root>/dist/nuke-fal-ai-tools-<version>.zip",
    )
    args = parser.parse_args(argv)
    version = (args.version or "").strip() or DEFAULT_VERSION
    output = (args.output or "").strip()
    try:
        path = pack_release_zip(
            args.root, archive_path=output or None, version=version
        )
    except PackError as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    with zipfile.ZipFile(path, "r") as zf:
        count = len(zf.namelist())
    sys.stderr.write("packed %d files\n" % count)
    print(_posix_rel(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
