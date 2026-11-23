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

Other lists in that folder are separate runs (example: `image_preview_todo.md`, `gpt25_seedance25_sam31_todo.md`). `unattended-todo.json` `allowed_waves` is `[1, 2, 3, 4, 5, 6]`. Image preview Wave 6 (P13 human click) stays skip.

Unattended item chats **must commit** in this public repo (override a "maintainer handles git" rule for those runs only). Do not push.

Planning notes, the implementer TODO, and the older tool wishlist live in that same sibling repo (`planning/`, `TODO.md`, `proposed-tools.md`).

## Node dashboard

fal node findings and the node inventory live in a Google Sheet, not in this repo. Spreadsheet id: `1akHa3cZGJ_BJT8goaAcNO-vCK7tG1Bmnuu5Zkjgyh-w`.

https://docs.google.com/spreadsheets/d/1akHa3cZGJ_BJT8goaAcNO-vCK7tG1Bmnuu5Zkjgyh-w/edit

Open it with the Google Sheets connection (`plugin-google-sheets-google-sheets`). If that connection needs auth, authenticate it, then call `get_spreadsheet`, then `read_range`. Tabs are `Findings`, `Node inventory`, and `About`. Name the tab on every read. Read a tab before you write it. The last write wins.

Grokbot discovers rows. Juuso decides. Cursor implements. Do not implement a Findings row unless `Human decision` is `Add`, `Fix`, `Replace`, or `Remove`. `Status` `Approved` alone is not enough. Leave `Skip`, `Later`, and a blank decision alone unless Juuso overrides that row in this chat. Follow the decision and `Juuso's notes`. Do not change `Human decision` or `Juuso's notes`. `proposed-tools.md` is an older wishlist. Do not treat its unchecked rows as the queue.

`Add` is a new node. `Fix` repairs an existing node. `Replace` swaps an outdated node or model. `Remove` retires a node.

Find columns by the header row each time, not by a remembered letter. After the code for an actionable row is in this repo, set that row's `Status` to `Done` and `Status changed` to today (`YYYY-MM-DD`). Update the matching Node inventory row (implementation status, dates, branch, file paths, endpoint, linked finding id). Do not add finding rows, reformat the sheet, or paste sheet contents into this repo.

Column map, status values, and the write shape: `../nuke-fal-ai-tools_devtools/planning/node-dashboard.md`. Read that file before the first write.

## This slice

Spec: `docs/planning/v1.1.0-release-prep.md`. Prepare the `work` branch as a v1.1.0 release candidate. Do not merge to main, tag, or publish a GitHub Release. Keep CHANGELOG `[Unreleased]` until the real tag.
