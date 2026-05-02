---
name: animation-creator
description: Create character-based animation assets from a source character image or text-created base character, then generate requested actions against that canonical base using $image-creator, grid layout guides, frame extraction, validation, contact sheets, final GIF/WebP files, and preview output. Use when a user wants animation frame grids, sprite/frame sequences, GIF/WebP/MP4 previews, or additional action animations that must preserve the same character identity.
---

# Animation Creator

Create clean character animation assets from a canonical base character. This skill owns animation planning, base-character setup, action prompts, layout guides, frame extraction, validation, contact sheets, and previews. It delegates all visual generation to `$image-creator`.

This skill saves runs and final assets into the current session project by default.

## Core Model

Every run has one canonical base character and one or more action jobs.

- If the user provides a source character image, use that image as the base reference.
- If the user does not provide a source character image, ask for or infer a concise character prompt, then use `$image-creator` to create the base character image first.
- Ask for the animation action when it is missing. The action is required.
- When the user later asks for additional actions, reuse the existing canonical base. Do not redesign or regenerate the character unless the user explicitly asks for a new base.

The key quality pattern is the same one that makes `hatch-pet` reliable: use a layout guide as an input image, require complete poses inside safe grid cells, process generated sheets with component-first extraction, and reject frames that show clipping, cell crossing, guide artifacts, or weak identity consistency.

## Hard Rules

- Use `$image-creator` for base and action image generation. Do not call image APIs directly from this skill.
- Save run folders and final outputs in the current session project by default, normally under `animation-runs/<character-or-run-id>/`.
- If the user gives a destination, resolve relative destinations from the session project root.
- Do not draw, tile, warp, synthesize, or invent visual character frames with local scripts as a substitute for `$image-creator`.
- Local scripts may only prepare manifests/prompts/guides, copy selected outputs, remove backgrounds, extract frames, compose animation files, validate geometry, and create QA media.
- Every action generation must attach the canonical base image and that action's grid layout guide as input images.
- Keep action prompts identity-locked: same character, same proportions, same face, same markings, same palette, same outfit/props unless the requested action logically moves them.
- Use complete full-body poses by default. If the user wants a cropped bust, hand, icon, or partial-body animation, record that as an explicit output contract.
- Treat ground planes, floor lines, cast shadows, contact shadows, oval floor shadows, landing marks, dust, detached effects, glow, motion streaks, guide lines, visible boxes, repeated still images, clipped body parts, and poses crossing into neighboring grid cells as failures unless explicitly accepted by the user.
- Remove exact chroma-key pixels everywhere, including holes inside the character silhouette. Remove exposed chroma-family components when they touch transparent/erased background so dark antialias edges and internal background rims are cleaned, while preserving embedded character colors such as mouths or blushes. Reject large remaining chroma-colored shadows, smears, halos, or landing marks during validation.
- Do not accept deterministic validation alone as final proof. Review the contact sheet or preview for identity drift and visible clipping.

## Workflow

1. Establish the animation run:
   - character source image or base character prompt
   - required action name and action description
   - frame count, fixed working frame size, FPS, loop mode, background mode, and output format
   - output destination, if requested
   - project root, defaulting to the current working directory
2. Prepare a run folder and manifest:

   ```bash
   SKILL_DIR="skills/animation-creator"
   python "$SKILL_DIR/scripts/prepare_animation_run.py" \
     --character-name "<Name>" \
     --character-prompt "<base character description>" \
     --action-id "<action-id>" \
     --action "<action description>" \
     --project-root /absolute/path/to/session/project \
     --output-dir /absolute/path/to/run
   ```

   If `--output-dir` is omitted, the run directory is created under `/absolute/path/to/session/project/animation-runs/`. If a source image exists, pass it with `--source-character /absolute/path/to/image.png`.

3. If no source character was provided, generate the base character with `$image-creator` using `prompts/base-character.md`, save it to the manifest's base output path, and record it as the canonical base.

   ```bash
   python "$SKILL_DIR/scripts/record_animation_result.py" \
     --run-dir /absolute/path/to/run \
     --job-id base-character \
     --source /absolute/path/to/generated/base.png
   ```

4. For each action job, call `$image-creator` with:
   - the action prompt file
   - `references/canonical-base.*` as the character identity input
   - `references/layout-guides/<action-id>.png` as the grid layout-only input
   - a destination inside the run directory, normally `generated/<action-id>.png`

   If the image was saved outside the expected job path, record it:

   ```bash
   python "$SKILL_DIR/scripts/record_animation_result.py" \
     --run-dir /absolute/path/to/run \
     --job-id <action-id> \
     --source /absolute/path/to/generated/action-grid.png
   ```
5. Extract frames:

   ```bash
   python "$SKILL_DIR/scripts/extract_frames.py" --run-dir /absolute/path/to/run --action-id <action-id>
   ```

6. Compose preview output and QA media:

   ```bash
   python "$SKILL_DIR/scripts/compose_animation.py" --run-dir /absolute/path/to/run --action-id <action-id>
   python "$SKILL_DIR/scripts/make_contact_sheet.py" --run-dir /absolute/path/to/run --action-id <action-id>
   python "$SKILL_DIR/scripts/render_preview.py" --run-dir /absolute/path/to/run --action-id <action-id> --write-final
   python "$SKILL_DIR/scripts/validate_animation.py" --run-dir /absolute/path/to/run --action-id <action-id> --require-components
   ```

7. Inspect validation JSON, contact sheet, and preview. Repair only the failed action when possible.

## Adding Actions To An Existing Run

For additional actions, reuse the run directory:

```bash
python "$SKILL_DIR/scripts/prepare_animation_run.py" \
  --run-dir /absolute/path/to/run \
  --add-action \
  --action-id "<new-action-id>" \
  --action "<new action description>"
```

Then generate only that new action through `$image-creator` and run extraction, composition, preview, and validation for that action.

## Prompt References

Read only the reference needed for the current step:

- `references/prompt-patterns.md` for base/action prompt shape and repair wording.
- `references/animation-output-contract.md` for frame size, frame count, background, format, and run manifest expectations.
- `references/qa-rubric.md` before accepting an action as complete.

## Defaults

Use these when the user does not specify otherwise:

- fixed working frame size: `512x512`
- safe margin: `28px` inside each `512x512` cell
- frame count: `6`
- default layout: `3x2` grid
- recommended single-sheet max: `12` frames
- experimental single-sheet max: `16` frames
- split into multiple action sheets above `16` frames
- FPS: `8`
- output format: `webp`
- final GIF: created by `render_preview.py --write-final`
- background mode: `chroma-key`
- chroma key: auto-selected safe high-saturation color, defaulting to green like `hatch-pet` when no source image is available
- loop mode: loop

## Response

When finished, report:

- run directory
- project-local output directory
- canonical base image path
- generated action IDs
- final animation file paths
- contact sheet and validation paths
- whether `$image-creator` was used for the base, actions, or both
- any repairs, skipped outputs, or visual review concerns
