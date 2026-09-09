# Agent notes

Contributor notes for this public plugin repo. Not part of the artist install ZIP.

## Typography

Do not use em dashes (`—`, U+2014) or en dashes (`–`, U+2013) in this repo.

Nuke runs Python 2 without a source encoding declaration. Non-ASCII characters in `.py` files cause `SyntaxError` at import time.

Use ASCII instead:

- Em dash: `--` or rephrase with a comma or period
- En dash: `-` (hyphen-minus) for ranges and compound terms
- Arrow: `->` instead of `→`

This applies to user-facing strings in Python, comments, and docs that ship with the plugin.

## Public vs private

Everything committed to this repository must be suitable for public release. Product and source changes belong here. Do not add private planning documents, unattended-agent machinery, local workflow files, secrets, temporary files, or development-only tooling. Private development orchestration lives in the sibling `nuke-fal-ai-tools_devtools` repo.

## Unattended todo

Checklists live in the sibling private repo `nuke-fal-ai-tools_devtools` (`todo_lists/`). Drain from the sibling, using a path relative to this repo root:

```text
python ../nuke-fal-ai-tools_devtools/run_todo.py v1.1.0_release_todo.md --wave all
```

Other lists in that folder are separate runs (example: `image_preview_todo.md`). `unattended-todo.json` `allowed_waves` is `[1, 2, 3, 4, 5, 6]`. Image preview Wave 6 (P13 human click) stays skip.

Unattended item chats **must commit** in this public repo (override a "maintainer handles git" rule for those runs only). Do not push.

Planning notes, the implementer TODO, and the agent tool wishlist live in that same sibling repo (`planning/`, `TODO.md`, `proposed-tools.md`).

## This slice

Spec: `docs/planning/v1.1.0-release-prep.md`. Prepare the `work` branch as a v1.1.0 release candidate. Do not merge to main, tag, or publish a GitHub Release. Keep CHANGELOG `[Unreleased]` until the real tag.
