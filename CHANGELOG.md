# Changelog

All notable changes to this project are documented here.

## [1.0.0] - 2026-06-08

Initial public release - fal.ai toolbox for Foundry Nuke.

### Included nodes (16)

**Still / image**

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
