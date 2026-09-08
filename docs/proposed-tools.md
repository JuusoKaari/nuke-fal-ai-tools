# Proposed tools

Wishlist of fal.ai models to add to the Nuke toolset. Sourced from the live catalog (August 2026).

Implement **one unchecked tool per agent turn**. Check it off, commit, then stop. Clone the listed existing files instead of inventing a new node shape.

Current coverage (do not duplicate): Nano Banana 2 generate+edit, GPT Image 2 edit, Qwen Max edit / inpaint / layered, Finegrain eraser, BiRefNet still+video, Depth Anything v2, Topaz Precision still upscale, Seedream 5.0 Pro Edit, Bria Extract Object, SAM 3.1 Image, Hunyuan World, Seedance 2.0 I2V, Seedance 2.0 Reference, Seedance 2.5 I2V, FLUX 3 First/Last + Keyframes, LTX 2.3 + LTX 2.5 Pro I2V, MiniMax H3 + H3 Max I2V, Pika 2.2 Pikaframes, Kling O3 V2V edit, Veo 3.1 extend, ByteDance video upscale, DreamActor v2, Hunyuan 3D v3.1 Pro image-to-3D, Hunyuan 3D v3.1 Part.

## Menu families

Menus are **Image / Video / 3D / Text**, then **model family**. Catalog rows in `_fal_tools.py` are `(category, family, label, group, helper, runner)`.

- Family ids live in `_FAMILY_LABELS` (Nodes prefix `fal-*`, top menu title).
- A family becomes a submenu only when that category has **2+** tools with the same family. Singles stay flat under the category. Adding Seedance 2.5 next to Seedance 2 I2V creates the Seedance submenu automatically. Do not edit `menu.py` for a new tool.
- **Utility** is last in Image and Video: mattes, depth, upscale, interpolate, Finegrain. Not a generative family.
- Do not split a family by generate vs edit. Nano Banana generate+edit, FLUX 3 first/last + keyframes, and Seedance I2V + Reference all stay in one family.
- Still vs shot still splits Topaz and BiRefNet: Image Utility vs Video Utility, not a top-level Topaz family.

Existing tree:

```text
Image
  Bria Extract Object       family bria (flat)
  GPT Image 2 Edit          family gpt-image (flat)
  Hunyuan World             family hunyuan-world (flat)
  Nano Banana 2 Generate    family nano-banana (flat)
  Qwen                      Inpaint, Layered, Max Edit
  Seedream 5.0 Pro Edit     family seedream (flat)
  Utility                   BiRefNet still, Depth, Finegrain, Topaz Precision, SAM 3.1 Image
Video
  DreamActor v2             family dreamactor (flat)
  FLUX 3                    First/Last, Keyframes
  Kling O3 V2V Edit         family kling (flat)
  LTX                       2.3, 2.5 Pro
  MiniMax                   H3 I2V, H3 Max I2V
  Pika v2.2 Pikaframes      family pika (flat)
  Seedance                  2 I2V, 2 Reference, 2.5 I2V
  Veo 3.1 Extend            family veo (flat until first/last)
  Utility                   BiRefNet, ByteDance upscale
3D
  Hunyuan 3D                Image to 3D, Part
Text
  OpenRouter                Describe image, Generate text
```

Family ids already reserved for this queue: `seedance`, `flux`, `minimax`, `utility`, `seedream`, `bria`, `veo`, `nano-banana`. Add a `_FAMILY_LABELS` row only if you need a new id.

## Agent prompt

Paste this each turn (new chat or same chat):

```text
Implement the next unchecked tool in docs/proposed-tools.md. One tool only.

Follow "Per-tool recipe", the clone map, and Menu families in that file.

1. Inspect the endpoint with `genmedia schema <id> --json` (do not invent field names).
2. Clone the closest existing helper/runner/group from the clone map.
3. Wire it in `_fal_tools.py` with the family id from the queue item. Keep ASCII-only Python (Nuke Py2). See AGENTS.md.
4. Run `py -3 -m unittest tests.test_fal_tools_catalog`.
5. Check the item off in proposed-tools.md. Add a CHANGELOG bullet under Unreleased.
6. Git commit only this tool, then stop and tell me the commit hash.
```

## Per-tool recipe

Do these steps in order. Do not start the next tool in the same turn.

1. **Pick** the first `- [ ]` item in [Queue: add first](#queue-add-first), then [Queue: add next](#queue-add-next).
2. **Inspect** `genmedia schema <endpoint> --json` (and `--endpoint_id` if you need description). Map knobs only to real schema fields.
3. **Clone** the files in the clone map. Copy helper argparse + `fal_common.subscribe_with_retry`, runner prerender, and `.nk` knob/input layout. Rename group node, prefixes, output filenames, and knob names to match this tool. Video tools must keep `nuke_video_output_v1.spawn_video_output_read` after the mp4 download (do not hand-roll a movie Read).
4. **Add the trio**
   - `nuke/python/fal_<name>_helper.py`
   - `nuke/python/fal_<name>_runner_v1.py`
   - `nuke/groups/fal_<name>_v1.nk` with `helper_path` / `runner_path` knobs
5. **Catalog** one new row in `nuke/python/_fal_tools.py`: `(category, family, label, group_file, helper_py, runner_py)`. Use the family id from the queue item. If that id is missing from `_FAMILY_LABELS`, add it (Nodes `fal-<id>`, top-menu title). Do not edit `menu.py`. Nesting is automatic at 2+ tools in the same category+family.
6. **Docs**
   - Check off this file (`- [x]`).
   - Append one CHANGELOG bullet under `## [Unreleased]` / `### Added`. Do not rewrite the README tool count in a way that stacks poorly for later `git revert` (add the tool name to the table; leave a count bump for a follow-up if needed).
7. **Test** `py -3 -m unittest tests.test_fal_tools_catalog`. Fix catalog mismatches before committing. The family-nesting tests should still pass (singles flat, 2+ nested, Utility last).
8. **Commit this tool only.** No drive-by refactors. Include the new trio, the `_fal_tools.py` row, the CHANGELOG bullet, and this checkbox.

Commit message (subject = tool name):

```text
Add <Tool label> node
```

Examples: `Add Seedance 2.5 Image to Video node`, `Add Bria Expand node`.

9. **Stop.** Reply with the commit hash, files touched, menu family (and whether this created a new submenu), and anything that still needs a Nuke UI pass (inputs, knobs).

To drop a tool later: `git revert <hash>`. Unique helper/runner/group files revert cleanly. Catalog and CHANGELOG are one-line adds, so they usually revert even after later tools landed. Reverting the second Seedance node will flatten Seedance back to a single command.

## Clone map

Copy these files. Steal I/O and knob patterns from the clone, then change endpoint, schema fields, and labels.

| New tool | Family | Clone these files | Copy this behavior | Notes |
|----------|--------|-------------------|--------------------|-------|
| Seedance 2.5 Image to Video | `seedance` (video) | `fal_seedance_2_image_to_video_{helper.py,runner_v1.py}` + `fal_seedance_2_image_to_video_v1.nk` | Input 0 start still, optional input 1 end still, prompt, duration/resolution/audio knobs, spawn Read via `nuke_video_output_v1` | Closest upgrade. Extend duration choices to 4-30s (or whatever schema allows). Same Nuke shape. Creates the Seedance submenu. |
| Seedance 2.0 Reference to Video | `seedance` (video) | Helper/knobs/output from Seedance 2.0 I2V. Multi-image inputs from `fal_pika_v22_pikaframes_*`. Video inputs from `fal_bytedance_video_upscale_*` or `fal_dreamactor_v2_*` | Repeated still inputs + optional video (and audio if schema has it), one fal mp4 then `spawn_video_output_read` | Schema first: up to 9 images, 3 videos, 3 audio. Do not invent 9+3+3 pipes if the API uses arrays. Named inputs like GPT Image 2 Edit (`fal_gpt_image_2_edit_*`) if labels matter more than order. |
| FLUX 3 First/Last Frame to Video | `flux` (video) | Seedance 2.0 I2V trio | Two stills in, fal mp4 then `spawn_video_output_read` | Optional draft endpoint as a knob (`.../first-last-frame-to-video/draft`), not a second node. Keep first/last as its own node (do not merge with single-image FLUX 3 I2V). Flat until keyframes ships. |
| FLUX 3 Keyframes to Video | `flux` (video) | `fal_pika_v22_pikaframes_{helper.py,runner_v1.py}` + `fal_pika_v22_pikaframes_v1.nk` | Contiguous keyframe inputs 0-N, stop at first gap, fal mp4 then `spawn_video_output_read` | Confirm max keyframe count from schema. Optional draft knob. Creates the FLUX 3 submenu. Pika can stay until this ships. |
| MiniMax H3 Image to Video | `minimax` (video) | Seedance 2.0 I2V trio (or LTX 2.5 Pro: `fal_ltx_25_image_to_video_pro_*`) | Start still, optional end still, fal mp4 then `spawn_video_output_read` | Resolution defaults toward 2K if schema allows. Same start/end layout as Seedance. Nested under MiniMax with H3 Max. |
| MiniMax H3 Max Image to Video | `minimax` (video) | `fal_minimax_h3_image_to_video_*` | Same start/end layout as H3 | Endpoint `minimax/h3-max/image-to-video`. Native 480P/768P only. `prompt_expansion_mode` enum, not a boolean. Creates the MiniMax submenu. |
| Image upscale (Topaz Precision) | `utility` (image) | Still I/O from `fal_depth_anything_v2_*`. Enum knobs from `fal_bytedance_video_upscale_*` | One still in, one still out, scale/model enums, no prompt required | Endpoint: `topaz/upscale/image/precision`. Image Utility, not a Topaz family. Skip SeedVR2 unless Topaz schema is a poor Nuke fit. |
| Seedream 5.0 Pro Edit | `seedream` (image) | `fal_gpt_image_2_edit_*` (multi-ref + optional mask) and `fal_qwen_image_max_edit_*` (prompted still edit) | Primary plate on input 0, extra refs, optional mask, prompt, stills out | Cap extra refs at what the group can show cleanly (schema allows up to 10). Stays flat until a second Seedream node. |
| Seedance 2.5 Reference to Video | `seedance` (video) | **If Seedance 2.0 Reference already exists, clone that.** Else Seedance 2.0 I2V + Pikaframes + video-input from ByteDance upscale | Same multimodal-ref idea, longer take (up to 30s), more refs | Heavier UI. Schema first (up to 50 files). Do not clone 2.0 Reference until that commit exists. |
| Bria Extract Object | `bria` (image) | `fal_birefnet_v2_still_*` for RGBA cutout + optional mask. Prompt knob / `prompt_text` from `fal_seedream_5_pro_edit_*` | One still in, prompt, RGBA still out, optional mask download | Filter in-group preview. Flat until Expand or Relight ships. |
| Bria Expand | `bria` (image) | `fal_bria_extract_object_*` (or `fal_depth_anything_v2_*`) for still in/out. Canvas/amount knobs from schema | One still in, expanded still out | Outpaint beyond borders. Not a mask eraser (that is Finegrain / Utility). Creates the Bria submenu next to Extract Object. |
| Bria Fibo Relight | `bria` (image) | `fal_bria_extract_object_*` plus prompt/enum knobs from `fal_qwen_image_max_edit_*` | One still in, relit still out | Lighting match, not a full rewrite. Joins the Bria submenu. Keep knobs structured if schema is structured. |
| Veo 3.1 First-Last | `veo` (video) | Seedance 2.0 I2V for start/end stills. `fal_veo3_1_extend_video_*` for Veo helper/output constraints | Two stills in, Veo mp4 then `spawn_video_output_read` | Creates the Veo submenu next to extend. Copy Veo-specific output limits from the extend helper, not from Seedance. |
| Topaz video interpolate | `utility` (video) | `fal_bytedance_video_upscale_{helper.py,runner_v1.py}` + `fal_bytedance_video_upscale_v1.nk` | Video in, fal mp4 then `spawn_video_output_read`, fps/model enums | Slow-mo / 24->60. Video Utility, not a Topaz family. Complements ByteDance upscale, do not merge them. |
| Nano Banana Pro | `nano-banana` (image) | `fal_nano_banana_2_generate_{helper.py,runner_v1.py}` + `fal_nano_banana_2_generate_v1.nk` | Generate vs edit by whether refs are connected, in-group preview | Dual endpoints: `fal-ai/nano-banana-pro` and `.../edit`. Creates the Nano Banana submenu. Same node shape as NB2. |
| SAM 3.1 Image | `utility` (image) | Prompt / 2-input from `fal_bria_extract_object_*`. Filter preview from `fal_birefnet_v2_still_*` | One still in, optional prompt Text, one still out (mask or RGBA cutout) | Endpoint: `fal-ai/sam-3-1/image` (not `fal-ai/sam-3/image`). Image Utility. v1 is text + one mask only. |

Shared rules for every clone:

- ASCII only in `.py` files (Nuke Python 2). See `AGENTS.md`.
- Top-of-file purpose comments on new helper/runner files. Keep them accurate.
- `__INSTALL_ROOT__` in `.nk` paths, same as existing groups.
- Notify if a new file grows past 500 lines.
- Video tools: fal still returns an mp4. After the helper writes it, call `nuke_video_output_v1.spawn_video_output_read` so Settings can spawn a DWAB EXR sequence Read (default) or an MP4 Read. Do not copy a raw `nuke.nodes.Read(file=...mp4)` spawn. Image tools are unchanged.

## Queue: add first

Highest Nuke value. Implement in this order.

- [x] **Seedance 2.5 Image to Video** -- `bytedance/seedance-2.5/image-to-video` -- family `seedance` / video -- upgrade of Seedance 2.0 I2V; 4-30s; optional end frame
- [x] **Seedance 2.0 Reference to Video** -- `bytedance/seedance-2.0/reference-to-video` -- family `seedance` / video -- up to 9 images, 3 videos, 3 audio; character/set lock
- [x] **FLUX 3 First/Last Frame to Video** -- `blackforestlabs/flux-3/first-last-frame-to-video` -- family `flux` / video -- start+end stills; optional draft endpoint as a knob
- [x] **FLUX 3 Keyframes to Video** -- `blackforestlabs/flux-3/keyframes-to-video` -- family `flux` / video -- multi-keyframe; modern Pikaframes
- [x] **MiniMax H3 Image to Video** -- `minimax/h3/image-to-video` -- family `minimax` / video -- frontier I2V; native 2K; optional last frame
- [x] **MiniMax H3 Max Image to Video** -- `minimax/h3-max/image-to-video` -- family `minimax` / video -- post-trained H3; native 480P/768P; prompt expansion enum; optional last frame
- [x] **Image upscale (Topaz Precision)** -- `topaz/upscale/image/precision` -- family `utility` / image -- still upscale (video upscale already exists)
- [x] **Seedream 5.0 Pro Edit** -- `bytedance/seedream/v5/pro/edit` -- family `seedream` / image -- region-precise edit, layer separation, up to 10 refs

FLUX 3 single-image I2V (`blackforestlabs/flux-3/image-to-video`) is not a separate queue item. First/last and keyframes cover the Nuke-shaped FLUX 3 work.

## Queue: add next

Strong additions. Start these only after add-first is done (or after you explicitly skip remaining add-first items).

- [ ] **Seedance 2.5 Reference to Video** -- `bytedance/seedance-2.5/reference-to-video` -- family `seedance` / video -- up to 50 multimodal refs; clone 2.0 Reference if it already shipped
- [x] **Bria Extract Object** -- `bria/extract-object` -- family `bria` / image -- prompt-guided RGBA cutout; optional mask; stays flat until Expand or Relight
- [x] **SAM 3.1 Image** -- `fal-ai/sam-3-1/image` -- family `utility` / image -- text prompt + one mask (Apply mask for RGBA cutout). Not SAM 3 embed. No boxes, points, multi-mask, or video.
- [ ] **Bria Expand** -- `fal-ai/bria/expand` -- family `bria` / image -- canvas outpaint; inpaint/eraser already exist
- [ ] **Bria Fibo Relight** -- `bria/fibo-edit/relight` -- family `bria` / image -- lighting match without a full generative rewrite
- [ ] **Veo 3.1 First-Last** -- `fal-ai/veo3.1/first-last-frame-to-video` -- family `veo` / video -- Veo is extend-only today
- [ ] **Topaz video interpolate** -- `topaz/interpolate/video` -- family `utility` / video -- 24->60 / slow-mo
- [ ] **Nano Banana Pro** -- `fal-ai/nano-banana-pro` and `fal-ai/nano-banana-pro/edit` -- family `nano-banana` / image -- quality step up from NB2, same workflow

## Skip for now

- Standalone text-to-video (Seedance 2.5 T2V, Kling V3 T2V, FLUX 3 T2V). I2V covers plate-based work.
- Kling O3/V3 I2V. Overlaps Seedance / FLUX 3 / H3. Kling O3 V2V edit already ships.
- GPT Image 2 text-to-image. Edit is the useful GPT node; Nano Banana 2 already generates.
- FLUX.2 Klein / Z-Image Turbo. Fast drafts, little extra vs Nano Banana 2.
- Extra mattes (Bria RMBG, Pixelcut). BiRefNet v2 covers still + video.
- Lipsync / talking-head (OmniHuman, Kling Avatar, sync-3). Different product lane.
- More 3D (Meshy 6, SAM 3D). Hunyuan 3D is enough until its quality ceiling is hit.
- SAM 3 embed. Awkward as a Nuke node (embeddings, not a clean mask out).
- SAM 3 / SAM 3.1 video, box prompts, point prompts, and multi-mask. SAM 3.1 Image v1 is text prompt + one still (mask, or RGBA cutout when Apply mask is on).
- SeedVR2 still upscale. Use Topaz Precision first.

Pika 2.2 can stay until FLUX 3 keyframes ships, then it is the candidate to retire.
