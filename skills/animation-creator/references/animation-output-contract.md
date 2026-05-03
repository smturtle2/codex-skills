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
    <action-id>.png
  frames/
    <action-id>/000.png
    <action-id>/001.png
    ...
    frames-manifest.json
  final/
    <action-id>.webp
    <action-id>-frames.webp
    <action-id>-validation.json
  qa/
    <action-id>-contact-sheet.png
    <action-id>-review.json
    previews/<action-id>.webp
    run-summary.json
```

The exact final files depend on the requested output format.

`finalize_animation_run.py` writes WebP outputs by default: a composed frame sheet at `final/<action-id>-frames.webp`, an animated WebP at `final/<action-id>.webp`, and a QA preview at `qa/previews/<action-id>.webp`. It writes frame-review diagnostics to `qa/<action-id>-review.json` before composing and sheet-validation diagnostics to `final/<action-id>-validation.json` after composing.

When `finalize_animation_run.py` runs without `--action-id`, it writes aggregate files for the selected run: `final/animation-frames.webp`, `final/validation.json`, `qa/review.json`, and `qa/contact-sheet.png`.

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
- final WebP animation: `final/<action-id>.webp`

Each action image should be a grid sheet with exactly one cell per planned frame action, read left-to-right, top-to-bottom. Each cell contains one complete pose matching that frame action, with consistent character registration, scale, facing, safe-box placement, and camera distance across adjacent frames. The prompt treats the registration guide as an edit template: keep the canvas, black cell borders, blue safe-area rectangles, and neutral background outside the blue rectangles; remove gray dashed centerlines and faint guide characters; fill only each blue safe-area interior with the selected chroma key; and draw character artwork on top. Extraction accepts generated sheets that preserve the manifest grid aspect ratio, removes visible guide border/background remnants, then uses the known grid to group frame content.

Extraction removes the chroma-key background from the full generated sheet, removes visible guide borders and center dashed lines, clears the guide canvas outside each inner safe area, then preserves the generated sheet's actual per-cell size. It prefers connected-component grouping into the expected frame slots. The default finalize path requires component extraction; known-layout slot slicing is a manual diagnostic fallback, not an acceptable default completion path. Validation checks whether the extracted frames are non-empty, avoid cell edges, were component-extracted, and remain visually continuous.

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

Planning should continue one beat at a time. Do not use few-shot examples or canned templates. After each planned frame, ask whether the action still needs any of these beats before it will read clearly:

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

The chroma key must not appear in the character, outfit, props, highlights, shadows, or effects. Prefer a high-saturation key color far from source image colors. Extraction removes exact chroma-key pixels everywhere, including holes inside a character silhouette. It also removes exposed chroma-family components that touch transparent/erased background, including dark antialias edges and darker/lighter remnants around internal holes or shadows, while preserving chroma-adjacent pixels embedded in the character body. Validation fails frames that still contain too many non-transparent pixels close to the chroma key.

Transparent output is preferred for WebP frame assets. MP4 previews may use a checkerboard or flat background because MP4 does not carry alpha.
