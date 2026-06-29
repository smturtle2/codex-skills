---
name: animation-creator
description: Create character animation runs from one preserved canonical base character. Codex plans the requested motion beat by beat, generates matte-background action sheets with $image-creator, removes action-sheet backgrounds with rembg, extracts validated frames, and produces project-local WebP animations.
---

# Animation Creator

Create character animation assets from one canonical base character. Plan the requested motion one adjacent pose beat at a time, audit the beats, then generate a base character if needed and generate action sheets with `$image-creator`. Preserve the canonical base as the identity reference. Generated action sheets use a flat removable matte background because rembg removes that more reliably than fake transparency before frame extraction.

This skill saves runs and final assets into the current session project by default.

## Core Model

Every run has one canonical base character and one or more action jobs.

- Use `$image-creator` for base and action image generation. Do not call image APIs directly.
- Ask for the animation action when it is missing.
- If the user provides a source character image, preserve it as `references/canonical-base.png` without rembg background removal.
- If no source image exists, generate the base character first, then record it through `record_animation_result.py` without rembg background removal.
- Reuse the existing canonical base for later actions unless the user explicitly asks for a new base.
- Before preparing a run, build the per-frame action plan sequentially. Do not choose a frame count first.
- Frame 1 may describe the starting pose. Every later frame should primarily describe the visible change from the previous frame, while scale, facing identity, body center path, balance, contact points, and weight transfer remain continuous.
- Audit the completed frame action list for missing anticipation, contact, passing pose, follow-through, settle, or loop bridge. Delete duplicate silhouettes and tiny micro-steps. The final frame count is the audited beat count.
- Avoid transform-like wording such as `flipped`, `mirrored`, `reversed`, `opposite direction`, or `rotate 180 degrees` unless the requested action truly needs that major transform.

## Hard Rules

- The prompt text sent to `$image-creator` must be the exact stdout from `build_generation_prompt.py` for that job.
- Do not create a separate `prompts/image-creator/` copy, and do not manually rewrite, summarize, shorten, or reconstruct the prompt.
- Save run folders and final outputs in the current session project by default, normally under `animation-runs/<character-or-run-id>/`.
- If the user gives a destination, resolve relative destinations from the session project root.
- Do not draw, tile, warp, synthesize, or invent visual character frames with local scripts as a substitute for `$image-creator`.
- Do not use old key-color cleanup or legacy background modes. The only supported generated-background contract is `rembg-matte`.
- Raw generated action images must use a single flat solid vivid sky-blue removable matte background `#00B7FF`.
- The matte color `#00B7FF` is reserved for background only; do not use it on character pixels, props, markings, motion effects, outlines, highlights, or shadows.
- Final recorded action sheets and extracted frames must be true alpha PNGs created by rembg. Cut the raw action sheet into planned frame slots using the actual generated image size, strip the preserved outer black cell borders from each slot crop, run rembg on each stripped slot image, remove matte-color residue from the rembg slot output, then reassemble the alpha-normalized sheet. If rembg cannot run, stop and report the failure.
- Run skill scripts with `uv run --project skills/animation-creator ...` so uv prepares the project-local `rembg[gpu,cli]` environment. Use GPU-backed rembg automatically when ONNX Runtime exposes `CUDAExecutionProvider` or `ROCMExecutionProvider`; if the GPU provider is unavailable or fails during execution, retry with CPU fallback and record the selected backend plus any fallback reason in manifest/job metadata.
- Do not ask `$image-creator` for scene backgrounds, floors, horizons, rooms, skies, landscapes, gradients, textured backgrounds, fake checkerboard transparency, cast shadows, contact shadows, glows, dust, or landing marks.
- Treat missing outer black cell borders in the raw action sheet, visible inner safe boxes, centerlines, guide marks, labels, captions, frame numbers, ghost characters, clipped body parts, repeated stills, wrong slot order, broken identity, or disconnected motion as failures. Final recorded sheets and extracted frames must not retain borders or guide lines.
- Every action generation must attach the canonical base image. After the canonical base is recorded, also attach that action's registration guide as an edit template.
- The generated raw action sheet should preserve the registration guide's 4:3 layout, outer boundaries, and outer black cell borders; replace guide characters with animated poses in used slots; leave unused slots empty; and remove only inner safe rectangles, centerlines, labels, ghost characters, and guide marks.
- Use complete full-body poses by default. If the user wants a cropped bust, hand, icon, or partial-body animation, record that as an explicit output contract.
- Do not accept deterministic validation alone as final proof. Review the contact sheet or final animation for identity drift and visible clipping.

## Workflow

1. Establish the run:
   - character source image or base character prompt
   - required action name and action description
   - playback timing, loop mode, output format, and destination if requested
   - per-frame action plan written specifically for this action
   - project root, defaulting to the current working directory

2. Plan frame actions sequentially:
   - Add one concrete adjacent beat at a time.
   - Prefer concrete spatial deltas over standalone pose labels.
   - Continue until the action has needed anticipation, contact or launch, key pose, passing/in-between poses, follow-through or overshoot, settle, and loop bridge or clear end pose.
   - Audit for too few frames, too many frames, repeated stills, missing transitions, and vague wording.
   - Only after the audit is clean may the list become `--frame-actions`.

3. Prepare a run folder and manifest:

   ```bash
   SKILL_DIR="skills/animation-creator"
   uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/prepare_animation_run.py" \
     --character-name "<Name>" \
     --character-prompt "<base character description>" \
     --action-id "<action-id>" \
     --action "<action description>" \
     --frame-actions "<frame 1 action>; <frame 2 action>; <frame N action>" \
     --project-root /absolute/path/to/session/project \
     --output-dir /absolute/path/to/run
   ```

   If a source image exists, pass it with `--source-character /absolute/path/to/image.png`. Source images are preserved as the canonical base.

4. If no source character was provided, generate the base character with `$image-creator`:

   ```bash
   uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/build_generation_prompt.py" \
     --run-dir /absolute/path/to/run \
     --job-id base-character
   ```

   Send stdout exactly as the final `$image-creator` prompt. Save the generated raw image, then record it:

   ```bash
   uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/record_animation_result.py" \
     --run-dir /absolute/path/to/run \
     --job-id base-character \
     --source /absolute/path/to/generated/base.png
   ```

   Recording stores the raw image under `generated/raw/base-character.png`, writes the preserved canonical image to `references/canonical-base.png`, and refreshes action prompts and registration guides.

5. For each action job, call `$image-creator` with:
   - the action prompt built by `build_generation_prompt.py`
   - `references/canonical-base.png` as the character identity input
   - `references/registration-guides/<action-id>.png` as an edit template whose canvas size should be preserved
   - an attempt destination inside the run directory, normally `generated/attempts/<action-id>-NN.png`

   Review the raw generated action sheet before recording it:
   - canvas aspect and 4x3 layout match the registration guide
   - requested slots contain exactly one full-body pose each, left-to-right then top-to-bottom
   - outer black cell borders are present in the raw sheet
   - the sheet background is one flat vivid sky-blue matte `#00B7FF`
   - no visible inner safe boxes, centerlines, labels, captions, frame numbers, ghost characters, guide marks, or scene background are present
   - character identity, scale, facing identity, and camera distance remain stable
   - adjacent frames read as one continuous motion

   Record only the selected raw image that passed review. Recording cuts the sheet into planned slots, runs rembg on each slot, removes matte-color residue, and reassembles the transparent action sheet:

   ```bash
   uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/record_animation_result.py" \
     --run-dir /absolute/path/to/run \
     --job-id <action-id> \
     --source /absolute/path/to/generated/action-grid.png
   ```

6. Finalize post-processing:

   ```bash
   uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/finalize_animation_run.py" --run-dir /absolute/path/to/run --action-id <action-id>
   ```

   This checks recorded generated-job files, extracts frames from the rembg-normalized alpha sheet, writes validation JSON, composes the PNG frame sheet, creates a contact sheet, writes the final animated WebP, and records `qa/run-summary.json`.

7. Inspect validation JSON, contact sheet, and final WebP animation. Repair only the failed action when possible.

## Adding Actions To An Existing Run

For additional actions, reuse the run directory:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/prepare_animation_run.py" \
  --run-dir /absolute/path/to/run \
  --add-action \
  --action-id "<new-action-id>" \
  --action "<new action description>" \
  --frame-actions "<frame 1 action>; <frame 2 action>; <frame N action>"
```

Then generate only that new action through `$image-creator`, record it through `record_animation_result.py`, and run `finalize_animation_run.py` for that action.

## Prompt References

Read only the reference needed for the current step:

- `references/animation-output-contract.md` for frame size, frame count, matte background, rembg removal, format, and manifest expectations.
- `references/qa-rubric.md` before accepting an action as complete.

## Defaults

- nominal registration-guide cell size: `362x362`
- generated registration guides use a fixed `4x3` layout at `1448x1086`
- safe margin: `30px` horizontal and `24px` vertical inside each nominal cell
- frame count: derived from the completed per-frame action plan
- default layout: derived from the finalized frame count
- maximum frame count: `12`
- output format: `webp`
- final WebP path: `final/<action-id>.webp`
- background mode: `rembg-matte`
- removal matte: `#00B7FF` vivid sky-blue background-only matte
- background removal engine: required `rembg`
- background removal model: `birefnet-general-lite`
- background removal uv extra: `rembg[gpu,cli]`
- background removal backend: `cuda` or `rocm` when available through ONNX Runtime, otherwise `cpu`
- background removal fallback: retry with `CPUExecutionProvider` when a GPU provider is detected but rembg execution fails
- loop mode: loop

## Response

When finished, report:

- run directory
- project-local output directory
- canonical base image path
- generated action IDs
- final WebP animation file paths
- contact sheet and validation paths
- whether `$image-creator` was used for the base, actions, or both
- any repairs, skipped outputs, or visual review concerns
