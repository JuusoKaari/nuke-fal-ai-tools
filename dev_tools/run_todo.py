#!/usr/bin/env python3
# Purpose: Drain a wave checklist with Cursor CLI, one ID per fresh `agent -p`
#          chat. The checklist is a required CLI argument so a repo can keep
#          several lists. Verify/model/rules come from unattended-todo.json
#          (or --verify). Stdlib only. Prompts go to a temp file so Windows
#          cmd.exe cannot truncate them. --wave all walks every allowed
#          non-skip wave in order. Checklists live in todo_lists/ next to
#          this script (not the repo root).

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

WAVE_HEADING_RE = re.compile(r"^## Wave (\d+)\b")
ITEM_RE = re.compile(r"^- \[([ xX])\] \*\*([A-Z]+\d+)\*\* [—–-] (.+)$")
SKIP_RE = re.compile(r"(?i)(?:decision needed\s*:|unattended:\s*skip)")

CONFIG_NAME = "unattended-todo.json"
TODO_LISTS_DIR = "todo_lists"


@dataclass(frozen=True)
class TodoItem:
    item_id: str
    title: str
    done: bool
    wave: int
    detail: str
    skip: bool


def parse_wave_arg(value: str) -> int | str:
    """Accept a 1-based wave number or the word 'all'."""
    text = value.strip().lower()
    if text == "all":
        return "all"
    try:
        number = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("wave must be an integer or 'all'") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("wave must be >= 1")
    return number


def _wave_has_runnable_items(items: list[TodoItem], wave: int, include_skip: bool) -> bool:
    for item in items:
        if item.wave != wave:
            continue
        if include_skip or not item.skip:
            return True
    return False


def waves_to_drain(
    items: list[TodoItem],
    choice: int | str,
    allowed: set[int] | None,
    include_skip: bool = False,
) -> list[int]:
    """Waves to run. `--wave all` is every allowed wave except skip-only ones."""
    present = sorted({item.wave for item in items})
    if choice == "all":
        if allowed is not None:
            present = [wave for wave in present if wave in allowed]
        return [
            wave
            for wave in present
            if _wave_has_runnable_items(items, wave, include_skip)
        ]
    wave = int(choice)
    return [wave]


def queue_for_waves(
    items: list[TodoItem],
    waves: list[int],
    include_skip: bool,
) -> list[TodoItem]:
    queue: list[TodoItem] = []
    for wave in waves:
        chunk = [item for item in items if item.wave == wave and not item.done]
        if not include_skip:
            chunk = [item for item in chunk if not item.skip]
        queue.extend(chunk)
    return queue


def git_toplevel(start: Path) -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return start.resolve()


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        sys.exit(f"Config must be a JSON object: {path}")
    return data


def find_config(explicit: str | None, repo: Path, script_dir: Path) -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_file():
            sys.exit(f"Config not found: {path}")
        return path
    for folder in (Path.cwd(), script_dir, repo):
        candidate = folder / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _todo_list_dirs(repo: Path, script_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for folder in (
        script_dir / TODO_LISTS_DIR,
        repo / "dev_tools" / TODO_LISTS_DIR,
        repo / "scripts" / TODO_LISTS_DIR,
    ):
        resolved = folder.resolve()
        if resolved not in dirs:
            dirs.append(resolved)
    return dirs


def available_todo_lists(repo: Path, script_dir: Path) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for folder in _todo_list_dirs(repo, script_dir):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name not in seen:
                seen.add(path.name)
                names.append(path.name)
    return names


def resolve_todo_path(todo_rel: str, repo: Path, script_dir: Path) -> Path:
    """Resolve the required checklist argument. Bare names search todo_lists/."""
    given = Path(todo_rel)
    names = [given]
    if not given.suffix:
        names.append(Path(str(given) + ".md"))

    if given.is_absolute():
        for name in names:
            if name.is_file():
                return name
        return given

    candidates: list[Path] = []
    for name in names:
        path = (repo / name).resolve()
        if path not in candidates:
            candidates.append(path)
        if len(name.parts) == 1:
            for folder in _todo_list_dirs(repo, script_dir):
                path = (folder / name.name).resolve()
                if path not in candidates:
                    candidates.append(path)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def format_todo_hint(repo: Path, script_dir: Path) -> str:
    names = available_todo_lists(repo, script_dir)
    if not names:
        return "No *.md files in todo_lists/. Pass a path to the checklist."
    listed = ", ".join(names)
    return f"Available in todo_lists/: {listed}"


def parse_todo(text: str) -> list[TodoItem]:
    items: list[TodoItem] = []
    wave: int | None = None
    wave_skip = False
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        detail = "\n".join(current["detail"]).strip()
        items.append(
            TodoItem(
                item_id=current["item_id"],
                title=current["title"],
                done=current["done"],
                wave=current["wave"],
                detail=detail,
                skip=bool(current["wave_skip"] or SKIP_RE.search(detail)),
            )
        )
        current = None

    for raw in text.splitlines():
        line = raw.rstrip()
        heading = WAVE_HEADING_RE.match(line)
        if heading:
            flush()
            wave = int(heading.group(1))
            wave_skip = bool(SKIP_RE.search(line))
            continue
        item = ITEM_RE.match(line)
        if item and wave is not None:
            flush()
            current = {
                "item_id": item.group(2),
                "title": item.group(3).strip(),
                "done": item.group(1) != " ",
                "wave": wave,
                "wave_skip": wave_skip,
                "detail": [],
            }
            continue
        if current is not None:
            if line.startswith("## "):
                flush()
                continue
            if line.strip() in ("---", "***"):
                continue
            current["detail"].append(line)
    flush()
    return items


def find_agent_bin(explicit: str | None) -> str:
    if explicit:
        path = shutil.which(explicit) or explicit
        if Path(path).exists() or shutil.which(explicit):
            return path
        sys.exit(f"Agent binary not found: {explicit}")

    for name in ("cursor-agent", "agent"):
        path = shutil.which(name)
        if not path:
            continue
        if name == "agent" and not _looks_like_cursor_agent(path):
            continue
        return path

    sys.exit(
        "Cursor CLI not found (tried `cursor-agent` then `agent`).\n"
        "Install from https://cursor.com/docs/cli/overview and ensure it is on PATH."
    )


def _looks_like_cursor_agent(path: str) -> bool:
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    blob = (proc.stdout or "") + (proc.stderr or "")
    return "cursor" in blob.lower() or bool(re.search(r"\d{4}\.\d+", blob))


def cli_argv_prefix(agent_bin: str) -> list[str]:
    """Prefer PowerShell -File over a .CMD wrapper so argv is not parsed by cmd.exe."""
    path = Path(agent_bin)
    if path.suffix.lower() in {".cmd", ".bat"}:
        ps1 = path.with_suffix(".ps1")
        if ps1.is_file():
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            powershell = (
                Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            )
            return [
                str(powershell),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
            ]
    return [agent_bin]


def git_porcelain(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def git_head_subject(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def item_checked(text: str, item_id: str) -> bool:
    return bool(re.search(rf"^- \[[xX]\] \*\*{re.escape(item_id)}\*\*", text, re.M))


def build_prompt(
    item: TodoItem,
    *,
    todo_path: Path,
    spec: str,
    verify: str,
    extra_rules: list[str],
) -> str:
    spec_line = f"Spec: {spec}\n" if spec else ""
    extra = ""
    if extra_rules:
        extra = "\n" + "\n".join(f"- {rule}" for rule in extra_rules)
    return f"""CHECKLIST_ITEM_ID={item.item_id}

You are running unattended via Cursor CLI in this git checkout.
Do ONE checklist item, then stop.

{spec_line}File: {todo_path}
Item: {item.item_id} — {item.title}
Wave: {item.wave}

Notes for this item:
{item.detail}

Rules:
- Implement only {item.item_id}. Do not start any other checklist ID.
- Follow AGENTS.md and project rules in this repo.
- After the change, run this verify command and fix failures:
  {verify}
  Prefer a narrower test/lint task if only one area changed, then still run the full verify if it is reasonably fast.
- Tick `- [x]` for {item.item_id} only in {todo_path.name}.
- Commit once when Done when is true. One commit, message says why and includes ({item.item_id}). Do not amend. Do not push.
- For this unattended run you MUST commit yourself (override a "maintainer handles git" rule if present).
- If the item is larger than it looked, still finish {item.item_id} if you can; do not expand into other IDs.{extra}
"""


_CLI_FLAG_CACHE: dict[tuple[str, str], bool] = {}


def cli_supports_flag(prefix: list[str], flag: str) -> bool:
    cache_key = ("\0".join(prefix), flag)
    cached = _CLI_FLAG_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        proc = subprocess.run(
            prefix + ["--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _CLI_FLAG_CACHE[cache_key] = False
        return False
    blob = (proc.stdout or "") + (proc.stderr or "")
    supported = flag in blob
    _CLI_FLAG_CACHE[cache_key] = supported
    return supported


def run_agent(
    agent_bin: str,
    prompt: str,
    item_id: str,
    repo: Path,
    model: str | None,
) -> int:
    prompt_path = Path(tempfile.gettempdir()) / f"unattended-todo-{item_id}.txt"
    prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
    one_line = (
        f"Read the UTF-8 file {prompt_path} and follow every line exactly. "
        f"Implement only checklist item {item_id}. Do not pick a different ID from the todo."
    )
    prefix = cli_argv_prefix(agent_bin)
    extra: list[str] = []
    if cli_supports_flag(prefix, "--trust"):
        extra.append("--trust")
    extra.append("--force")
    cmd = prefix + ["-p", *extra]
    if model:
        cmd += ["--model", model]
    cmd += ["--output-format", "text", "--workspace", str(repo), one_line]
    shown_model = f"--model {model} " if model else ""
    print(
        f"Running: {prefix[0]} ... -p {' '.join(extra)} {shown_model}--workspace {repo}",
        flush=True,
    )
    print(f"Prompt file: {prompt_path}", flush=True)
    try:
        proc = subprocess.run(cmd, cwd=repo)
        return proc.returncode
    finally:
        prompt_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Unattended Cursor CLI loop over one wave checklist in this checkout. "
            "The checklist is required so multiple lists in todo_lists/ stay explicit."
        ),
        usage="%(prog)s CHECKLIST [--wave WAVE] [options]",
        epilog=(
            "examples:\n"
            "  run_todo.py settings_todo.md --dry-run --wave 1\n"
            "  run_todo.py settings_todo.md --wave all\n"
            "  run_todo.py export_todo.md --wave 2"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "todo",
        nargs="?",
        metavar="CHECKLIST",
        help="Checklist to drain (required). Bare names resolve under todo_lists/.",
    )
    parser.add_argument(
        "--todo",
        dest="todo_flag",
        metavar="CHECKLIST",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--config", help=f"JSON config path (default: search for {CONFIG_NAME}).")
    parser.add_argument("--verify", help="Verify shell command (overrides config).")
    parser.add_argument("--spec", help="Optional spec path injected into the prompt.")
    parser.add_argument(
        "--wave",
        type=parse_wave_arg,
        default=1,
        help=(
            "Wave to drain (default: 1). Pass 'all' to drain every allowed wave "
            "in order, excluding Unattended: skip / Decision needed waves."
        ),
    )
    parser.add_argument("--only", metavar="ID", help="Run a single ID instead of the whole wave.")
    parser.add_argument("--agent-bin", help="Path or name of the Cursor CLI binary.")
    parser.add_argument("--model", help="Cursor CLI --model id (overrides config).")
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Stop after N successful items in this run (0 = no limit).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the next items and prompts; do not call the CLI.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Run even if the git worktree has uncommitted changes.",
    )
    parser.add_argument(
        "--include-skip",
        action="store_true",
        help="Also queue Decision needed / Unattended: skip items.",
    )
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    script_dir = Path(__file__).resolve().parent
    repo = git_toplevel(Path.cwd())

    todo_rel = args.todo_flag or args.todo
    if not todo_rel:
        parser.error(
            "checklist is required, e.g. run_todo.py settings_todo.md --wave all. "
            + format_todo_hint(repo, script_dir)
        )
    todo_path = resolve_todo_path(str(todo_rel), repo, script_dir)
    if not todo_path.is_file():
        sys.exit(f"Missing checklist: {todo_path}\n{format_todo_hint(repo, script_dir)}")

    config_path = find_config(args.config, repo, script_dir)
    cfg = load_json(config_path) if config_path else {}
    if config_path:
        print(f"Config: {config_path}")

    verify = args.verify or cfg.get("verify") or ""
    verify = str(verify).strip()
    spec = str(args.spec or cfg.get("spec") or "").strip()
    extra_rules = cfg.get("extra_rules") or []
    if not isinstance(extra_rules, list) or not all(isinstance(x, str) for x in extra_rules):
        sys.exit("extra_rules must be a JSON array of strings.")
    allowed = cfg.get("allowed_waves")
    if allowed is not None:
        if not isinstance(allowed, list) or not all(isinstance(x, int) for x in allowed):
            sys.exit("allowed_waves must be a JSON array of integers.")
        allowed_set = set(allowed)
    else:
        allowed_set = None
    model = args.model or cfg.get("model") or None
    if model is not None:
        model = str(model).strip() or None

    if not args.dry_run and not verify:
        sys.exit("Set verify in unattended-todo.json or pass --verify.")

    items = parse_todo(todo_path.read_text(encoding="utf-8"))
    if (
        args.wave != "all"
        and allowed_set is not None
        and args.wave not in allowed_set
        and not args.only
    ):
        sys.exit(
            f"Wave {args.wave} is not in allowed_waves {sorted(allowed_set)}. "
            "Adjust the config or pass --only for one ID."
        )
    waves = waves_to_drain(items, args.wave, allowed_set, args.include_skip)
    queue = queue_for_waves(items, waves, args.include_skip)

    if args.only:
        only = args.only.upper()
        queue = [i for i in items if i.item_id == only]
        if not queue:
            print(f"No checklist item {only} in {todo_path.name}", file=sys.stderr)
            return 1
        if queue[0].done:
            print(f"{only} is already ticked.")
            return 0
        if queue[0].skip and not args.include_skip:
            print(
                f"{only} is marked Decision needed / Unattended: skip. "
                "Pass --include-skip if you really want it.",
                file=sys.stderr,
            )
            return 1

    if not queue:
        if args.wave == "all":
            label = ",".join(str(w) for w in waves) or "none"
            print(f"Waves {label}: nothing left to do.")
        else:
            print(f"Wave {args.wave}: nothing left to do.")
        return 0

    if args.max_items and args.max_items > 0:
        queue = queue[: args.max_items]

    print(f"Repo: {repo}")
    print(f"Todo: {todo_path}")
    if model:
        print(f"Model: {model}")
    if args.wave == "all":
        print("Waves: " + ", ".join(str(w) for w in waves))
    print(f"Queue ({len(queue)}): " + ", ".join(i.item_id for i in queue))

    if args.dry_run:
        print("Live runs write the full prompt to a temp file and pass a one-line path (Windows CMD-safe).")
        for item in queue:
            print("\n-----", item.item_id, "-----")
            print(
                build_prompt(
                    item,
                    todo_path=todo_path,
                    spec=spec,
                    verify=verify or "<verify unset>",
                    extra_rules=extra_rules,
                )
            )
        return 0

    dirty = git_porcelain(repo)
    if dirty and not args.allow_dirty:
        print("Worktree is dirty. Commit/stash first, or pass --allow-dirty.\n", file=sys.stderr)
        print(dirty, file=sys.stderr)
        return 1

    agent_bin = find_agent_bin(args.agent_bin)
    print(f"CLI: {agent_bin}")
    if not os.environ.get("CURSOR_API_KEY"):
        print("Note: CURSOR_API_KEY is unset; CLI will use a logged-in Cursor session if one exists.")

    for item in queue:
        latest = parse_todo(todo_path.read_text(encoding="utf-8"))
        live = next((i for i in latest if i.item_id == item.item_id), None)
        if live is None or live.done:
            print(f"Skipping {item.item_id} (missing or already ticked).")
            continue
        if live.skip and not args.include_skip:
            print(f"Skipping {item.item_id} (Decision needed / Unattended: skip).")
            continue

        print(f"\n======== {item.item_id} — {item.title} ========", flush=True)
        started = time.monotonic()
        prompt = build_prompt(
            live,
            todo_path=todo_path,
            spec=spec,
            verify=verify,
            extra_rules=extra_rules,
        )
        code = run_agent(agent_bin, prompt, live.item_id, repo, model)
        elapsed = time.monotonic() - started
        print(f"{item.item_id}: CLI exit {code} after {elapsed / 60:.1f} min")
        if code != 0:
            print(f"Stopping: agent failed on {item.item_id}.", file=sys.stderr)
            return code or 2

        text = todo_path.read_text(encoding="utf-8")
        if not item_checked(text, item.item_id):
            print(
                f"Stopping: {item.item_id} chat finished but the checkbox is still open.",
                file=sys.stderr,
            )
            return 2

        subject = git_head_subject(repo)
        if item.item_id not in subject:
            print(
                f"Stopping: {item.item_id} is ticked but HEAD commit does not mention it:\n  {subject}",
                file=sys.stderr,
            )
            return 2

        print(f"{item.item_id}: ok — {subject}")

    if args.wave == "all":
        print("\nAll queued waves complete.")
    else:
        print(f"\nWave {args.wave} complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
