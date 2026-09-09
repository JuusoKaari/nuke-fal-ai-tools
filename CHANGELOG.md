# Changelog

All notable changes to this project are documented here.

## [Unreleased]

Upcoming v1.1.0. Recreate nodes from **Nodes -> fal.ai** after updating so baked graphs and new knobs pick up.

### Added

**Image**

- Bria Extract Object - prompt-guided object cutout as an RGBA PNG (optional mask) via `bria/extract-object`.
- SAM 3.1 Image - text-prompted segmentation mask (Apply mask for RGBA cutout) via `fal-ai/sam-3-1/image`. Text plus one still only; no boxes, points, or multi-mask. Empty fal results say no matching object. Default prompt is `person`.
- Seedream 5.0 Pro Edit - prompted still edit from a primary plate plus up to 9 extra refs (10 stills total) via `bytedance/seedream/v5/pro/edit`.
- Image upscale (Topaz Precision) - still upscale with model and scale knobs via `topaz/upscale/image/precision`. Lives in Image Utility.

**Video**

- FLUX 3 First/Last Frame to Video - required start and end stills, 5-20s, optional draft endpoint via `blackforestlabs/flux-3/first-last-frame-to-video`.
- FLUX 3 Keyframes to Video - 1-10 contiguous stills pinned to 24 fps positions, 5-20s, optional draft via `blackforestlabs/flux-3/keyframes-to-video`.
- MiniMax H3 Image to Video - still to video with optional end frame, 5-15s, default 2K via `minimax/h3/image-to-video`.
- MiniMax H3 Max Image to Video - post-trained H3 with stronger prompt adherence, 5-15s, native 480P/768P via `minimax/h3-max/image-to-video`.
- Seedance 2 Reference to Video - character/set lock from up to 9 stills, 3 videos, and 3 audio files via `bytedance/seedance-2.0/reference-to-video`.
- Seedance 2.5 Image to Video - still to video with optional end frame, 4-30s, and synchronized audio via `bytedance/seedance-2.5/image-to-video`.
- LTX 2.5 Image to Video Pro - still to video with optional end frame, camera motion, and synchronized audio via `lightricks/ltx-2.5/image-to-video/pro`.

**3D**

- Hunyuan 3D Part - splits a local FBX into part FBX files via `fal-ai/hunyuan-3d/v3.1/part`.

**Settings and output**

- **Open temp folder** and **Open output folder** on every fal Group Advanced tab, and next to Default output folder in **fal.ai -> Settings...**. They reveal the parent `nuke_fal_temp/` / `nuke_fal_output/` dirs Execute would use (Settings folder when usable, else next to the saved script).
- Video tools default to a Nuke-written **DWAB EXR sequence** Read after the fal MP4 download (half float, compression level 200). The MP4 stays on disk. Toggle back to MP4 Reads in **fal.ai -> Settings...**.
- Nano Banana 2 Generate: **Extract selected as Read** and **Clear generation history** buttons. Clear only forgets node history; files on disk stay.

### Changed

- **Nodes -> fal.ai** groups by model family under Image / Video / 3D / Text. Families with 2+ tools become a submenu (Qwen, FLUX 3, LTX, MiniMax, Seedance, Hunyuan 3D, OpenRouter, Utility). Single-node families stay flat. Utility is last in Image and Video.
- In-group preview now covers Image editors (GPT Image 2 Edit, Qwen Image Max Edit, Seedream 5.0 Pro Edit, Qwen Image Inpaint, Hunyuan World), Qwen Image Layered, and Image utilities (BiRefNet v2 Still, Depth Anything v2, Finegrain Eraser, Topaz Precision). Groups look through the connected plate on `Output1`.
- GPT Image 2 Edit: same ROI crop-and-merge as Nano Banana 2 Generate (`use_roi`, `roi_area` on `ref_image_a`). Optional mask is cropped to that box when ROI is on. Primary reference image is input 0 so creating the node after a plate auto-connects. Optional second image, prompt Text, and mask follow on inputs 1-3.
- Still image-to-video Groups look through the primary still on `Output1` (Seedance 2/2.5 I2V, LTX 2.3/2.5 Pro, MiniMax H3/H3 Max, FLUX 3 first/last and keyframes, Pikaframes, Seedance 2 reference-to-video). Execute still spawns a video Read.
- Helper failures show the fal.ai error text in the Nuke popup, not only Script Editor. Nested JSON detail/error blobs unwrap to the inner message. Transient 5xx/429 (and similar) fal errors retry with backoff.
- FAL knob placeholder now says to insert a fal key to override for this node. Settings and `FAL_KEY` remain the defaults; the old "secret key / env variable" wording is still ignored so existing scripts keep working.
- Finegrain Eraser: if the mask input has an alpha channel, that alpha is used as the erase matte (copied to RGB). fal.ai removed premium mode; new nodes offer express/standard, and existing premium knobs remap to standard.
- Video prerender (PNG sequence to mp4) snaps odd width/height down by 1px so libx264 can encode formats like 1280x557.
- Clear generation history and Extract selected as Read show a Nuke dialog for unexpected errors (with a restart-Nuke hint) instead of only printing to the Script Editor.

## [1.0.2] - 2026-06-16

### Added

**Still / image**

- In-group output preview for Nano Banana 2 Generate (`fal_nano_banana_2_generate_v1.nk`): baked preview graph in the group `.nk`, viewer modes (Guide, Source input, AI input, Generated, grids), `preview_index` browse, optional `spawn_reads_in_graph` (default off). Accumulated generated outputs across Execute runs with `generated_output_count` and **Clear generated outputs**. Shared helper: `nuke_group_output_preview_v1.py`.
- BiRefNet v2 Still (`fal_birefnet_v2_still_v1.nk`) - single-image background removal via `fal-ai/birefnet/v2`

**Text**

- Describe image (`fal_openrouter_describe_image_v1.nk`) - OpenRouter vision LLM image captioning/analysis via `openrouter/router/vision`
- Generate text (`fal_openrouter_generate_text_v1.nk`) - OpenRouter LLM text generation via `openrouter/router`

### Changed

- Nano Banana 2 Generate: default ROI area is `0,0` to `512,512` (was dev-scene coordinates).
- Release zip no longer includes the `tests/` folder.

### Included nodes (20)

Same categories as v1.0.1, plus BiRefNet v2 Still, Describe image, and Generate text. See tool list in [README.md](README.md).

## [1.0.1] - 2026-06-08

Initial public release - fal.ai toolbox for Foundry Nuke.

### Included nodes (17)

**Still / image**

- Hunyuan World (`fal_hunyuan_world_v1.nk`)
- Nano Banana 2 Generate (`fal_nano_banana_2_generate_v1.nk`)
- Qwen Image Max Edit (`fal_qwen_image_max_edit_v1.nk`)
- GPT Image 2 Edit (`fal_gpt_image_2_edit_v1.nk`)
- Qwen Image Inpaint (`fal_qwen_image_inpaint_v1.nk`)
- Finegrain Eraser (`fal_finegrain_eraser_v1.nk`)
- BiRefNet v2 (`fal_birefnet_v2.nk`)
- Depth Anything v2 (`fal_depth_anything_v2.nk`)
- Qwen Image Layered (`fal_qwen_image_layered_v1.nk`)

**3D**

- Hunyuan 3D Image to 3D (`fal_hunyuan_3d_image_to_3d_v1.nk`)

**Video**

- LTX 2.3 Image to Video (`fal_ltx_23_image_to_video_v1.nk`)
- Seedance 2 Image to Video (`fal_seedance_2_image_to_video_v1.nk`)
- Pika v2.2 Pikaframes (`fal_pika_v22_pikaframes_v1.nk`)
- Kling O3 V2V Edit (`fal_kling_o3_v2v_edit_v1.nk`)
- Veo 3.1 Extend Video (`fal_veo3_1_extend_video_v1.nk`)
- ByteDance Video Upscale (`fal_bytedance_video_upscale_v1.nk`)
- DreamActor v2 Motion Control (`fal_dreamactor_v2_motion_control_v1.nk`)

### Notes

- Paths use the `__INSTALL_ROOT__` placeholder, resolved from the repo root on `NUKE_PATH` (see `docs/INSTALL.md`).
- Group `.nk` filenames, internal node names, and menu labels follow fal.ai model names where practical.
- Py2 and Py3 Nuke supported via `_nuke_py_compat.py` and `_nuke_runner_launcher.py`.
- fal.ai API usage is billed to your own account; models and endpoints may change without notice.
- Released as-is under Mozilla Public License 2.0.
