<!--
  Maintainer note after v1.1.0 RC prep (R11).
  Tracked in git. Omitted from the artist install ZIP.
-->

# v1.1.0 release candidate

Status of the `work` branch after prep. Not an install guide. Not a tag.

## Verdict

`work` is ready for a human `work` -> `main` pull request.

Do not merge from this note. Do not tag `v1.1.0`. Do not push a release tag. Do not publish a GitHub Release. Keep CHANGELOG `[Unreleased]` until the real tag.

## Automated checks (2026-09-09)

- `py -3 -m unittest discover -s tests -v` : 212 tests, OK. No Nuke, no fal.ai, no network.
- Working tree has no `dist/` directory and no zip leftovers. `.gitignore` already covers `dist/` and `*.zip`. Local `__pycache__` / `*.pyc` stay untracked.
- CHANGELOG heading is still `[Unreleased]`. README already says upcoming v1.1.0 and lists 32 tools from `_TOOLS`.

## What prep changed

Relative to the start of this RC pass (`docs/planning/v1.1.0-release-prep.md`):

- Public clones see the public-vs-DevTools boundary in tracked `AGENTS.md`. Private runner files stay out of this repo.
- The GitHub Release ZIP is an install tree from an explicit allowlist (`.github/scripts/pack_release.py`). CI and local dry packs share that script. `tests/test_release_zip.py` fails if the archive omits `init.py` or ships `tests/`, planning, or maintainer docs.
- Tag releases run the same unittest discover as PR CI before zip/publish. A failing suite cannot reach `softprops/action-gh-release`.
- Artist docs say helpers need **system Python 3.9+**, separate from Nuke's embedded interpreter.
- `[Unreleased]` is the future v1.1.0 user notes (new image/video/3D tools, Settings, family menus, in-group preview / ROI, DWAB EXR, fal error text and retries). Heading was not renamed to `[1.1.0]`.
- Tracked-file hygiene and catalog consistency are gated in unittest (`tests/test_tracked_hygiene.py`, `tests/test_fal_tools_catalog.py`).
- A local candidate ZIP was packed, extracted, checked, and deleted (R9). Nothing from that pack remains in the tree.

Product work on `work` (tools, preview, Settings, DWAB, and so on) is already on the branch. Prep did not add features. It made the branch reviewable and packable.

## Remaining warnings

Nuke smoke in [RELEASE_CHECK.md](RELEASE_CHECK.md) is still human. Unit tests never launch Nuke. Walk that list in a real GUI on a packed extract before tagging. Every Execute is a billed fal.ai call.

Other leftovers for a person, not another agent pass:

- Open the `work` -> `main` PR, review, and merge. This file does not merge anything.
- After merge and smoke: retitle CHANGELOG `[Unreleased]` to `[1.1.0]`, tag `v1.1.0`, and let `.github/workflows/release.yml` publish. Failed tests or a bad ZIP must stop that job.
- Recreate fal Groups from **Nodes -> fal.ai** after artists update, so baked graphs pick up.

## Stop

Prep ends here.
