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
    base-character.png  # only when the base is generated
    attempts/<action-id>-NN.png  # rejected or candidate action-sheet attempts, when regeneration was needed
    <action-id>.png
  frames/
    <action-id>/000.png
    <action-id>/001.png
    ...
    frames-manifest.json
  final/
    <action-id>.webp
    <action-id>-frames.png
    <action-id>-validation.json
  qa/
    <action-id>-contact-sheet.png
    <action-id>-review.json
    run-summary.json
```

The exact final files depend on the requested output format.

`finalize_animation_run.py` writes the composed frame sheet as PNG at `final/<action-id>-frames.png` and writes WebP only for the final animated result at `final/<action-id>.webp`. It writes frame-review diagnostics to `qa/<action-id>-review.json` before composing and sheet-validation diagnostics to `final/<action-id>-validation.json` after composing.

When `finalize_animation_run.py` runs without `--action-id`, it writes aggregate files for the selected run: `final/animation-frames.png`, `final/validation.json`, `qa/review.json`, and `qa/contact-sheet.png`.

## Required Manifest Fields

`animation_manifest.json` should record:

- `character_id`
- `character_name`
- `description`
- `canonical_base`
- `frame_width` and `frame_height` as nominal registration-guide cell dimensions
- `fps` when a playback rate was requested or already exists in the run
- `loop`
- `background_mode`
- `chroma_key`
- `actions`
- `action_plans`

Each action state should record:

- `action`
- `frame_actions`
- `motion_beats`
- `frames`
- `frame_count`
- `layout`

`animation-jobs.json` should record each base/action job, source path, output path, source prompt file, input images, status, hashes, and timestamps. A complete job records both the source prompt hash and the exact built `$image-creator` prompt hash from `build_generation_prompt.py`. The workflow should not create a duplicate `prompts/image-creator/` prompt directory.

## Geometry

Defaults:

- nominal registration-guide cell size: `512x512`
- the 16-frame maximum uses a `4x4` registration guide at `2048x2048`
- registration-guide safe margin: `30px` horizontal and `24px` vertical
- frame count: finalized from the completed per-frame action plan
- intermediate frame format: `png`
- final animation format: `webp`
- final WebP animation: `final/<action-id>.webp`; intermediate sheets and QA images stay PNG

Each action image should be a grid sheet with exactly one cell per planned frame action, read left-to-right, top-to-bottom. Each cell contains one complete pose matching that frame action, with consistent character registration, scale, facing, safe-box placement, and camera distance across adjacent frames. The prompt treats the registration guide as an edit template: keep the canvas, black cell borders, blue safe-area rectangles, and neutral background outside the blue rectangles; remove gray dashed centerlines and faint guide characters; fill only each blue safe-area interior with the selected chroma key; and draw character artwork on top. Extraction accepts generated sheets that preserve the manifest grid aspect ratio, removes visible guide border/background remnants, then uses the known grid to group frame content.

When the recommended grid contains more cells than planned frames, only the planned frame count is part of the output contract. Extraction ignores unused slots even if generation fills them.

Before extraction, inspect the raw generated action sheet. If the sheet has the wrong grid, missing requested frames, wrong slot order, repeated stills where motion should change, broken identity, disconnected motion, visible labels, extra guide marks, malformed or missing safe-area rectangles, clipped poses, or non-chroma safe-area interiors, the selected action image is invalid and should be regenerated. Do not use deterministic post-processing as a way to accept a bad raw sheet. Save rejected action-sheet attempts under `generated/attempts/` when useful, but record only the selected accepted attempt as `generated/<action-id>.png`.

Extraction removes the chroma-key background from the full generated sheet, removes visible outer grid borders, detects the generated chroma-key inner safe-area fill in each used slot, clears everything outside that detected inner safe-area box, ignores unused slots, then preserves the generated sheet's actual per-cell size. Safe-area outline color is not the primary detection signal; line detection is only a diagnostic backup when the inner fill cannot be read. If a used slot's inner safe-area fill cannot be detected, extraction may use the manifest safe-area geometry only as a diagnostic last resort and records that fallback in the frame manifest; an accepted production result should not rely on manifest fallback for a visibly malformed raw sheet. It prefers connected-component grouping into the expected frame slots. The default finalize path requires component extraction; known-layout slot slicing is a manual diagnostic fallback, not an acceptable default completion path. Validation checks whether the extracted frames are non-empty, avoid cell edges, were component-extracted, and remain visually continuous.

Recommended layouts:

| Frames | Layout |
| ---: | --- |
| 1-4 | `2x2` or smaller as needed |
| 5-6 | `3x2` |
| 7-8 | `4x2` |
| 9 | `3x3` |
| 10-12 | `4x3` |
| 13-16 | `4x4` |

The maximum action length is `16` frames. Do not choose a frame count from an action category. First build and audit the frame actions until the motion is complete; then choose the recommended layout from that finalized count.

Planning should continue one beat at a time. Frame 1 may describe the starting pose; every later frame should be treated as the accumulated result of all previous changes plus the visible change from the immediately previous slot, rather than a standalone pose label. A short phase label may be used only when it helps identify the accumulated current frame. Avoid transform-like wording unless the requested animation explicitly requires that major visual transform; for ordinary rotation, tumbling, airborne motion, or transitional poses, prefer body-part positions and continuous motion paths. Do not use few-shot examples or canned templates. After each planned frame, ask whether the action still needs any of these beats before it will read clearly:

- anticipation or wind-up
- first contact or launch
- main key pose
- passing/in-between pose
- follow-through or overshoot
- recovery or settle
- loop bridge back to the first pose

Only stop when the answer is no. Then audit the full list for both directions: too few frames that create pose pops or missing timing beats, and too many frames that create duplicate silhouettes, frozen holds, micro-steps, or timing stalls. Add missing beats and delete redundant beats before deriving the final frame count. If the audited list is over 16 frames, first delete or merge repeated information and timing stalls; if the action still cannot fit, narrow the action or ask the user before preparing the run. If stopping would remove one of the required beats, keep planning instead of forcing a shorter sheet.

## Background

Default action background mode is `chroma-key`, because clean background removal before component extraction is central to reliable frame extraction. Generated base characters use a flat white `#FFFFFF` reference background first; after the base is recorded, the scripts inspect the canonical base colors and select a safe high-saturation chroma key for action sheets. The selected chroma key applies to each generated action-sheet inner safe area, not to the registration guide file itself. Registration guides remain neutral edit templates with cell borders, safe-area borders, center dashed lines, and a faint canonical-base footprint. Generated action sheets should remove the dashed centerlines and faint guide characters.

Prefer a high-saturation key color far from source image colors, but extraction must not depend on green-specific or fixed-channel rules. For each extracted frame, cleanup estimates the actual background from the frame edge, builds an adaptive background-similarity mask, removes only regions connected to the exterior background plus very small isolated holes that are extremely close to the estimated background, then applies soft alpha, edge color restoration, and background-direction despill. Character colors, outfit details, props, highlights, and markings that resemble the key color should be preserved when they are not connected to the exterior background. Validation fails frames that still contain large exterior-connected key-color remnants or visible halos.

Transparent output is preferred for the final animated WebP. MP4 previews may use a checkerboard or flat background because MP4 does not carry alpha.
