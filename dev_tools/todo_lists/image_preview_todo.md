<!--
  dev_tools/todo_lists/image_preview_todo.md
  Purpose: Checkable build list for in-group preview on Image nodes besides Nano Banana 2.
  IDs: P1-P13. Spec: ../../docs/planning/image-ingroup-preview.md
  Keep this file under todo_lists/; do not place it at the repo root.
-->

# Image in-group preview TODO

Living checklist for [docs/planning/image-ingroup-preview.md](../../docs/planning/image-ingroup-preview.md). Check an item only when the behavior described in **Done when** is true.

Work top to bottom. Later IDs may assume earlier ones exist.

Unattended Cursor CLI: `python dev_tools/run_todo.py image_preview_todo.md` (default Wave 1). Use `--wave N` for a later wave, or `--wave all` to drain every non-skip wave in order. Add `--dry-run` to preview, `--allow-dirty` if the tree is unclean.

`unattended-todo.json` `allowed_waves` is `[1, 2, 3, 4, 5, 6]`. Wave 6 human click (P13) stays skip.

Do not call fal.ai. Do not launch Nuke. Do not copy ROI nodes onto any tool except Nano Banana 2. Do not touch Video, 3D, or Text groups.

---

## Wave 1 - config without baking other nodes

- [x] **P1** - Preview config kinds and optional ROI/history
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/python/nuke_group_output_preview_graph_v1.py`, `tests/test_group_output_preview_logic.py`
  - Do: Keep Nano Banana 2's existing config and tests green. Add optional `preview_kind` (`editor` / `layers` / `filter`; default `editor` so NB2 stays valid). `supports_roi` defaults false when omitted. Filter kind does not add ROI knobs, `preview_index`, extract, clear, or generated-path registry. Layers kind does not add ROI. Allow a per-tool `viewer_modes` list so filter can be Input + Generated only; do not change the global editor list that NB2 uses. If `nuke_group_output_preview_graph_v1.py` would go past 500 lines, split instead of growing it. Do not edit any `.nk` except if a comment in the Python files needs an ASCII-only tweak. Do not add production `TOOL_PREVIEW_CONFIG` rows for GPT/Qwen/etc yet.
  - Done when: unit tests show NB2 still has ROI + accumulate; a fake filter config skips history/ROI knobs; a fake editor config without `supports_roi` does not request ROI knobs; unknown tools still resolve to None.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

---

## Wave 2 - first editor

- [x] **P2** - GPT Image 2 Edit in-group preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_gpt_image_2_edit_v1.nk`, `nuke/python/fal_gpt_image_2_edit_runner_v1.py`, `tests/test_group_output_preview_logic.py`
  - Do: Add `GPT_Image_2_Edit_v1` as `preview_kind` editor, `preview_inputs` `ref_image_a` and `ref_image_b`, `max_outputs` 4, `supports_roi` false, `spawn_reads_in_graph` default false, accumulate true. Map `fal_gpt_image_2_edit_runner_v1.py` in `RUNNER_BASENAME_TO_TOOL_ID`. Bake look-through + generated reads + `viewer_mode_switch` from the Nano Banana 2 `.nk` as text; strip every ROI node; keep Inputs `ref_image_a`, `ref_image_b`, `prompt_text`, `mask`; delete the Text placeholder on `Output1`. Hidden `fal_tool_id` and `knobChanged` like NB2. Runner keeps `_collect_reference_images` and mask export. After helper success, `wire_group_outputs`, then spawn root Reads only if `spawn_reads_in_graph` is on.
  - Done when: the GPT `.nk` text contains `viewer_mode_switch`, `generated_read_01`, `fal_tool_id GPT_Image_2_Edit_v1`, and does not contain `ROI_rectangle` or `use_roi`. Tests resolve the GPT runner basename to that config with `supports_roi` false.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

---

## Wave 3 - remaining variant editors

- [x] **P3** - Qwen Image Max Edit in-group preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_qwen_image_max_edit_v1.nk`, `nuke/python/fal_qwen_image_max_edit_runner_v1.py`, tests
  - Do: Same editor pattern as P2. Look-through `source_image`. `max_outputs` 6 (knob is 1-6). No ROI. Keep Input name `source_image`. Runner keeps current still export; add `wire_group_outputs`; spawn Reads only when the knob is on (default off).
  - Done when: Qwen Max `.nk` has baked preview without ROI; config maps `fal_qwen_image_max_edit_runner_v1.py` to `Qwen_Image_Max_Edit_v1` with `max_outputs` 6 and `supports_roi` false.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

- [x] **P4** - Seedream 5.0 Pro Edit in-group preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_seedream_5_pro_edit_v1.nk`, `nuke/python/fal_seedream_5_pro_edit_runner_v1.py`, tests
  - Do: Editor pattern. `preview_inputs` is `image_1` only (look-through the primary plate). `max_outputs` 6. No ROI. Do not add an AI-input grid of ten stills. Runner still collects `image_1`..`image_10` as it does today. `wire_group_outputs` after download. Spawn Reads default off.
  - Done when: Seedream `.nk` looks through `image_1`, has `viewer_mode_switch` and no ROI nodes, and still has Inputs `image_1`..`image_10` plus `prompt_text`. Config `preview_inputs` is exactly `["image_1"]`.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

---

## Wave 4 - inpaint, panorama, layers

- [x] **P5** - Qwen Image Inpaint in-group preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_qwen_image_inpaint_v1.nk`, `nuke/python/fal_qwen_image_inpaint_runner_v1.py`, tests
  - Do: Editor pattern. Look-through `source_image` only. Keep `mask` as input 1. Do not add ROI. `max_outputs` 4. Runner keeps mask export. `wire_group_outputs`; spawn Reads default off.
  - Done when: inpaint `.nk` has `viewer_mode_switch` and Inputs `source_image` plus `mask`, and has no `ROI_rectangle` / `use_roi`.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

- [x] **P6** - Hunyuan World in-group preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_hunyuan_world_v1.nk`, `nuke/python/fal_hunyuan_world_runner_v1.py`, tests
  - Do: Editor pattern with `max_outputs` 1 and `supports_generated_grid` false (Input + Generated only). Look-through `source_image`. No ROI. History/extract/clear still ok for re-runs. Spawn Reads default off. Do not merge the panorama back over the source plate.
  - Done when: Hunyuan World `.nk` has look-through + `generated_read_01`, no Generated grid enum, no ROI, no merge-back nodes.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

- [x] **P7** - Qwen Image Layered in-group preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_qwen_image_layered_v1.nk`, `nuke/python/fal_qwen_image_layered_runner_v1.py`, tests
  - Do: `preview_kind` layers. Look-through `source_image`. `max_outputs` 10. Generated grid for the layer stack. `spawn_reads_in_graph` default **true**. `accumulate_outputs` false (each Execute replaces the layer set). No ROI. Runner still writes one Read per layer when spawn is on; also `wire_group_outputs` so the Group shows the stack.
  - Done when: layered `.nk` has `spawn_reads_in_graph` true, `generated_read_01` through `generated_read_10` (or equivalent baked count), no ROI; config `preview_kind` is `layers`.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

---

## Wave 5 - Image utilities (filter preview)

- [x] **P8** - BiRefNet v2 Still filter preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_birefnet_v2_still_v1.nk`, `nuke/python/fal_birefnet_v2_still_runner_v1.py`, tests
  - Do: `preview_kind` filter. Look-through `source_image`. After Execute the Group output is the matte/result. Viewer modes Input + Generated only. No history knobs, no ROI, spawn Reads default off. Runner `wire_group_outputs` with the single output path.
  - Done when: BiRefNet still `.nk` has `viewer_mode` with Input and Generated only, `generated_read_01`, no `preview_index` / extract / clear / ROI; config `preview_kind` is `filter`.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

- [x] **P9** - Depth Anything v2 filter preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_depth_anything_v2.nk`, `nuke/python/fal_depth_anything_v2_runner_v1.py`, tests
  - Do: Same filter pattern as P8. Keep the existing Depth knobs and `source_image` Input. No ROI.
  - Done when: Depth `.nk` matches the filter bake (look-through + generated, no history/ROI) and the runner wires in-group output.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

- [x] **P10** - Finegrain Eraser filter preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_finegrain_eraser_v1.nk`, `nuke/python/fal_finegrain_eraser_runner_v1.py`, tests
  - Do: Same filter pattern. Look-through `source_image`, not `mask`. Keep the mask Input. No ROI rectangle.
  - Done when: Finegrain `.nk` looks through `source_image`, still has `mask`, has no ROI, and the runner wires the processed still onto the Group.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

- [ ] **P11** - Topaz Precision filter preview
  - Where: `nuke/python/nuke_group_output_preview_config_v1.py`, `nuke/groups/fal_topaz_upscale_image_precision_v1.nk`, `nuke/python/fal_topaz_upscale_image_precision_runner_v1.py`, tests
  - Do: Same filter pattern as P8 on the Topaz still upscale node. Look-through `source_image`. After Execute the Group shows the upscaled frame. Spawn Reads default off.
  - Done when: Topaz `.nk` is filter-preview baked without ROI/history, and the runner calls `wire_group_outputs`.
  - Tests: `py -3 -m unittest tests.test_group_output_preview_logic`.

---

## Wave 6 - docs and human click (P13 skip)

- [ ] **P12** - Document which Image nodes look through
  - Where: `docs/troubleshooting.md`, `CHANGELOG.md` (Unreleased)
  - Do: Replace the "Nano Banana 2 pilot" troubleshooting section so it lists editor vs layers vs filter, and that ROI is Nano Banana 2 only. Recreate-from-menu note stays. CHANGELOG Unreleased: in-group preview now covers the Image editors, Qwen Layered, and Image utilities as specified. Do not rewrite README tool table unless a one-line mention of look-through is needed. ASCII punctuation only.
  - Done when: troubleshooting no longer says preview is a Nano Banana-only pilot, and CHANGELOG Unreleased names the other Image nodes.
  - Tests: none beyond repo verify.

- [ ] **P13** - Human click in Nuke (Unattended: skip)
  - Where: Nuke 11.3 or 17 session on Windows, Nodes -> fal.ai
  - Unattended: skip
  - Do: Recreate GPT Image 2 Edit, Qwen Layered, and BiRefNet v2 Still from the menu. Confirm each looks through the plate before Execute. After a billed Execute (your key), GPT shows Generated on the Group with spawn-reads off; Layered still spawns layer Reads by default; BiRefNet output is on the Group. Confirm Qwen Inpaint has no ROI knobs. Tick this box yourself.
  - Done when: you have seen look-through on those three nodes and one billed GPT or BiRefNet result on the Group output.
  - Tests: none (human only).
