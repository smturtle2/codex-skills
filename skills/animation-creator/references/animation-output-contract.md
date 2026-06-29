# Animation Output Contract

## Run Layout

All paths are project-local by default. A normal run lives under:

```text
<session-project>/animation-runs/<run-id>/
  animation_manifest.json
  animation-jobs.json
  prompts/
    base-character.md
    actions/<action-id>.md
  references/
    canonical-base.png
    registration-guides/<action-id>.png
  generated/
    raw/
      base-character.png
      <action-id>.png
    attempts/<action-id>-NN.png
    base-character.png
    <action-id>.png
  frames/<action-id>/000.png
  final/<action-id>.webp
  final/<action-id>-frames.png
  final/<action-id>-validation.json
  qa/<action-id>-contact-sheet.png
  qa/<action-id>-review.json
  qa/run-summary.json
```

`generated/raw/` stores raw `$image-creator` outputs. `references/canonical-base.png` preserves the source or generated base image as the identity reference. Recorded action sheets directly under `generated/` must be rembg-normalized true alpha PNGs.

## Required Manifest Fields

`animation_manifest.json` records:

- `character_id`
- `character_name`
- `description`
- `canonical_base`
- `frame_width` and `frame_height`
- `loop`
- `background_mode: "rembg-matte"`
- `removal_background.hex: "#00B7FF"`
- `removal_background.policy: "flat-matte-for-rembg"`
- `background_removal.required: true`
- `background_removal.engine: "rembg"`
- `background_removal.backend: "cuda"`, `"rocm"`, or `"cpu"`
- `background_removal.available_providers`
- `background_removal.selected_providers`
- `background_removal.gpu_fallback` when a GPU provider was attempted but CPU retry completed the job
- `background_removal.model: "birefnet-general-lite"`
- `background_removal.alpha_matting`
- `actions`
- `action_plans`

Each action state records:

- `action`
- `frame_actions`
- `motion_beats`
- `frames`
- `frame_count`
- `layout`

`animation-jobs.json` records each base/action job, raw source path, recorded output path, prompt file, input images, job status, hashes, and timestamps. Action jobs also record `background_removal` metadata after recording.

## Geometry

Defaults:

- nominal cell size: `362x362`
- maximum action length: `12` frames
- generated registration guide layout: fixed `4x3` at `1448x1086`
- safe margin: `30px` horizontal and `24px` vertical
- intermediate frame format: `png`
- final animation format: `webp`
- default background removal model: `birefnet-general-lite`
- uv background removal dependency: `rembg[gpu,cli]`

Each action image is a fixed `4x3` grid sheet, read left-to-right then top-to-bottom. Each used cell contains one complete pose matching that frame action, with consistent character registration, scale, facing, safe placement, and camera distance across adjacent frames. Unused cells stay empty except for the same matte interior and preserved outer black cell borders.

The registration guide is an edit template. Generated raw action sheets should preserve the guide's `4x3` layout, outer boundaries, and outer black cell borders; replace guide characters with animated poses in used slots; leave unused slots empty; and remove inner safe rectangles, centerlines, guide characters, captions, and slot labels.

When the recommended grid contains unused cells, only the planned frame count is part of the output contract. Extraction ignores unused slots.

Recommended layout:

| Frames | Layout |
| ---: | --- |
| 1-12 | `4x3` |

## Background Removal

Generated raw action images must use a single flat solid vivid sky-blue removable matte background `#00B7FF`. This color is reserved for background only; character pixels, props, markings, outlines, highlights, shadows, and motion effects must not use it. Do not use scene backgrounds, floor planes, shadows, gradients, textured backgrounds, or fake checkerboard transparency.

Recording an action result must cut the raw sheet into planned frame slots from the actual generated image size, strip the preserved outer black cell borders from each slot crop, run rembg on each stripped slot, remove matte-color residue from each rembg slot output, reassemble the alpha-normalized sheet, and only then mark the job complete:

- raw input path: `generated/raw/<job-id>.png`
- per-slot rembg work path: `generated/rembg-work/<job-id>/<frame-index>.png`
- alpha-normalized output path: job `output_path`
- action job metadata: `background_removal.matte_residue_cleanup`
- action job metadata: `background_removal.source_sheet_size`
- action job metadata: `background_removal.border_strip`

Recording a base-character result preserves the source image as the canonical identity reference at `references/canonical-base.png`. Do not run rembg on the canonical base.

Run scripts with `uv run --project skills/animation-creator ...` so uv prepares the project-local rembg runtime. The declared runtime uses `rembg[gpu,cli]`; ONNX Runtime should select `CUDAExecutionProvider` or `ROCMExecutionProvider` when available. If a detected GPU provider fails during rembg execution, retry the same slot once with `CPUExecutionProvider` and record `background_removal.gpu_fallback`. If the rembg CLI is unavailable or cannot run on either provider, the job fails. There is no key-color alternate path.

Extraction accepts only slot-rembg-normalized alpha action sheets. It validates sheet aspect ratio, clears unused slots, groups foreground components into frame slots, and writes transparent PNG frames. The default completion path requires component extraction.

Transparent output is required for final WebP animations. MP4 previews may use a checkerboard or flat background because MP4 does not carry alpha.
