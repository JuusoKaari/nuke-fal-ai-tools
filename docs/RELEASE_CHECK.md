<!--
  Maintainer Nuke smoke for a release candidate.
  Tracked in git. Omitted from the artist install ZIP.
-->

# Maintainer Nuke smoke

Walk this list in a real Nuke GUI before tagging. Unit tests do not cover it. Every Execute below is a billed fal.ai call. Pick one tool per row. Skip the rest of the catalog.

Artist setup stays in [INSTALL.md](INSTALL.md). This page is only the candidate clicks.

## Candidate copy

1. Pack with `python .github/scripts/pack_release.py`, or reuse a zip built the same way.
2. Extract into a clean folder outside this git checkout. The archive has one top folder, `nuke-fal-ai-tools/`, with `init.py` at that root.
3. Point Nuke at that extract only. Set `NUKE_PATH` to the extract for this session, or point `pluginAddPath` there. Do not also load the clone.
4. From the extract, install helpers into system Python 3.9+: `py -3 -m pip install -r requirements-python3.txt`. ffmpeg and ffprobe still need to be on `PATH` for video.
5. Launch Nuke from that setup. The Script Editor should have no traceback from `init.py` or `menu.py`.

## Menus and key

6. **Nodes -> fal.ai** is there, grouped under Image, Video, 3D, and Text. Tab-search `fal` finds tools.
7. Open **fal.ai -> Settings...**. Save a key if this machine has none, then **Test connection**. Resolution is the per-node **FAL** knob first, then Settings `~/.nuke-fal-ai/config.json`, then `FAL_KEY`.

## Executes

Save a scratch `.nk` before Execute so temp and output folders have a home.

8. Established image. Create **Nano Banana 2 Generate**, connect a still, Execute. The Group should show a generated still.
9. Newer image or segmentation. **Bria Extract Object** or **SAM 3.1 Image**, Execute once. A cutout or mask is the happy path. SAM saying it found no matching object is also a valid result.
10. Video. One image-to-video tool is enough. Leave **Video output** in Settings on **DWAB EXR sequence**. After Execute the spawned Read should point at a `name.####.exr` sequence next to the MP4. The MP4 stays on disk.

## Preview, ROI, errors

11. In-group preview. On Nano Banana 2 Generate or GPT Image 2 Edit, switch Viewer mode Input vs Generated around Execute. Before Execute, Output1 should look through the connected plate.
12. ROI. On Nano Banana 2 Generate or GPT Image 2 Edit, enable `use_roi`, set `roi_area` on the plate, Execute. The model should run on that crop and the result should paste back into the box.
13. Errors. Force one failure: empty required input, a bad key in the node's **FAL** knob, or a SAM prompt that matches nothing. The Nuke popup should show a readable helper or fal.ai message, not only a Script Editor traceback.

## After

Quit Nuke. Point `NUKE_PATH` or `pluginAddPath` back at the real install. Delete the extract. Leave zip files and `dist/` uncommitted.
