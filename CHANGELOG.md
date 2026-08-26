# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- MiniMax H3 Max Image to Video (`fal_minimax_h3_max_image_to_video_v1.nk`) - post-trained H3 variant with stronger prompt adherence, 5-15s, native 480P/768P via `minimax/h3-max/image-to-video`. Creates the MiniMax submenu next to MiniMax H3 I2V.
- Seedream 5.0 Pro Edit (`fal_seedream_5_pro_edit_v1.nk`) - prompted still edit from a primary plate plus up to 9 extra refs (10 stills total) via `bytedance/seedream/v5/pro/edit`. Stays flat under Image until a second Seedream node ships.
- Image upscale (Topaz Precision) (`fal_topaz_upscale_image_precision_v1.nk`) - still upscale with model and scale knobs via `topaz/upscale/image/precision`. Joins Image Utility (not a Topaz family).
- MiniMax H3 Image to Video (`fal_minimax_h3_image_to_video_v1.nk`) - animates a still into video with optional end frame, 5-15s, default 2K via `minimax/h3/image-to-video`. Stays flat under Video until a second MiniMax node ships.
- FLUX 3 Keyframes to Video (`fal_flux_3_keyframes_to_video_v1.nk`) - 1-10 contiguous stills pinned to 24 fps positions, 5-20s, optional draft endpoint via `blackforestlabs/flux-3/keyframes-to-video`. Creates the FLUX 3 submenu next to First/Last.
- FLUX 3 First/Last Frame to Video (`fal_flux_3_first_last_frame_to_video_v1.nk`) - required start and end stills, 5-20s, optional draft endpoint via `blackforestlabs/flux-3/first-last-frame-to-video`. Stays flat under Video until FLUX 3 Keyframes ships.
- Video tools default to a Nuke-written **DWAB EXR sequence** Read after the fal MP4 download (half float, compression level 200). The MP4 stays on disk. Toggle back to MP4 Reads in **fal.ai -> Settings...**. Shared helper: `nuke_video_output_v1.py`.
- Seedance 2 Reference to Video (`fal_seedance_2_reference_to_video_v1.nk`) - character/set lock from up to 9 stills, 3 videos, and 3 audio files via `bytedance/seedance-2.0/reference-to-video`. Joins the existing Seedance submenu.
- Seedance 2.5 Image to Video (`fal_seedance_25_image_to_video_v1.nk`) - animates a still into video with optional end frame, 4-30s duration, and synchronized audio via `bytedance/seedance-2.5/image-to-video`. Creates the Seedance submenu next to Seedance 2 I2V.
- LTX 2.5 Image to Video Pro (`fal_ltx_25_image_to_video_pro_v1.nk`) - animates a still into video with optional end frame, camera motion, and synchronized audio via `lightricks/ltx-2.5/image-to-video/pro`
- Nano Banana 2 Generate: **Extract selected as Read** and **Clear generation history** buttons. Clear only forgets node history; files on disk are kept.

### Changed

- FAL knob placeholder now says to insert a fal key to override for this node. Settings and `FAL_KEY` remain the defaults; the old "secret key / env variable" wording is still ignored so existing scripts keep working.
- GPT Image 2 Edit: primary reference image is now input 0 (`ref_image_a`) so creating the node after a plate auto-connects correctly. Optional second image, prompt Text, and mask follow on inputs 1-3.
- Menu groups by model family under Image / Video / 3D / Text. Families with 2+ tools become a submenu (Qwen, LTX, Utility, OpenRouter). Single-node families stay flat (Nano Banana 2, Seedance 2, Kling, ...). Utility is last in Image and Video.

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
