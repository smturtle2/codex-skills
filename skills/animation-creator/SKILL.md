---
name: animation-creator
description: Create character animation runs from one canonical base character. Codex plans the requested motion from pose to pose until the action reads clearly. The accumulated frame action list determines the frame count and layout, then $image-creator generates the action sheet and local scripts finalize a validated WebP animation.
---

# Animation Creator

Create character animation assets from one canonical base character. Codex does not fix the frame count or layout up front. It starts from the first pose of the requested motion, adds the next pose one at a time, and after each pose checks whether another anticipation, contact, follow-through, overshoot, settle, or loop-bridge pose is needed for the motion to read. When the motion is complete, Codex finalizes the frame action list and uses that list length to decide the frame count and layout. It then passes the canonical base and registration guide to `$image-creator` to generate the action sheet, while local scripts use the manifest grid and registration guide metadata for deterministic post-processing: extraction, validation, WebP composition, contact sheets, previews, and run summaries.

This skill saves runs and final assets into the current session project by default.

## Core Model

Every run has one canonical base character and one or more action jobs.

- If the user provides a source character image, use that image as the base reference.
- If the user does not provide a source character image, ask for or infer a concise character prompt, then use `$image-creator` to create the base character image first.
- Ask for the animation action when it is missing. The action is required.
- When the user later asks for additional actions, reuse the existing canonical base. Do not redesign or regenerate the character unless the user explicitly asks for a new base.
- Before creating any layout guide, build the per-frame action plan sequentially. Do not draft the full list in one pass and do not start by choosing a frame count. Add one concrete beat at a time. Frame 1 may describe the starting pose; every later beat should primarily describe the visible change from the immediately previous beat, and the frame should be understood as the accumulated result of all previous changes plus that new change, while scale, facing identity, spacing, balance, body center path, height, contact points, and weight shift remain continuous.
- After the first pass, audit the frame action list before preparing the run. Mark any missing anticipation, contact, passing pose, follow-through, settle, or loop bridge. Remove redundant beats, frozen duplicates, or micro-steps that do not change the silhouette, balance, contact, or timing enough to help playback. Rewrite any state-label-only beat as a concrete delta from the previous frame, with a short phase label only when it helps identify the accumulated current frame, before using it in `--frame-actions`. Add only the missing beats needed for the action to read. The final frame count is the number of audited frame actions after additions and deletions.
- Do not use few-shot examples, canned action templates, or action-category frame counts. Plan from the requested action itself, then derive the frame count from the completed audited list.

Use the manifest grid and registration guide for deterministic extraction, require complete poses inside safe grid cells, and reject frames that show clipping, cell crossing, weak identity consistency, or disconnected frame-to-frame motion. The registration guide is an edit template: it shows slot spacing, safe margins, center dashed lines, scale, and the base character footprint. The generated action sheet should keep the canvas, black cell borders, blue safe-area rectangles, and neutral background outside the blue rectangles, remove gray dashed centerlines and faint guide characters, replace only each inner safe-area background with the selected chroma key, and draw the animated poses on top. Do not create or attach a separate layout guide for image generation; attach only the canonical base and the registration guide when available.

## Hard Rules

- Use `$image-creator` for base and action image generation. Do not call image APIs directly from this skill.
- The prompt text sent to `$image-creator` must be the exact stdout from `build_generation_prompt.py` for that job. Do not create a separate `prompts/image-creator/` copy, and do not manually rewrite, summarize, shorten, or reconstruct the prompt from memory.
- Save run folders and final outputs in the current session project by default, normally under `animation-runs/<character-or-run-id>/`.
- If the user gives a destination, resolve relative destinations from the session project root.
- Do not draw, tile, warp, synthesize, or invent visual character frames with local scripts as a substitute for `$image-creator`.
- Local scripts may only prepare manifests/prompts/guides, copy selected outputs, remove backgrounds, extract frames, compose animation files, validate geometry, and create QA media.
- Every action generation must attach the canonical base image as an input image. After the canonical base is recorded, also attach that action's registration guide. Do not attach the raw layout guide as an input image.
- Keep action prompts identity-locked and continuity-locked: same character, same proportions, same face, same markings, same palette, same outfit/props, same camera distance, same scale, same facing, smooth motion, and consistent registration-guide slot spacing unless the requested action logically moves them.
- Use complete full-body poses by default. If the user wants a cropped bust, hand, icon, or partial-body animation, record that as an explicit output contract.
- Treat ground planes, floor lines, cast shadows, contact shadows, oval floor shadows, landing marks, dust, detached effects, glow, motion streaks, repeated still images, clipped body parts, poses crossing into neighboring grid cells, extra labels, extra guide marks, center dashed lines in the generated result, and ghost characters as failures unless explicitly accepted by the user. The raw generated action sheet should keep black cell borders and blue safe-area rectangles, remove gray dashed centerlines and faint guide characters, and use chroma-key background only inside each inner safe area. Extracted final frames must not retain guide lines, borders, safe-area boxes, center dashed lines, or guide background.
- Remove exact chroma-key pixels everywhere, including holes inside the character silhouette. Remove exposed chroma-family components when they touch transparent/erased background so dark antialias edges and internal background rims are cleaned, while preserving embedded character colors such as mouths or blushes. Reject large remaining chroma-colored shadows, smears, halos, or landing marks during validation.
- Do not accept deterministic validation alone as final proof. Review the contact sheet or preview for identity drift and visible clipping.

## Workflow

1. Establish the animation run:
   - character source image or base character prompt
   - required action name and action description
   - nominal registration-guide cell size, playback timing, loop mode, background mode, and output format
   - per-frame action plan, written specifically for this action
   - output destination, if requested
   - project root, defaulting to the current working directory
2. As Codex, plan the frame actions with this sequential draft-and-audit loop:
   - Start with the first readable pose for the requested action, then add the next adjacent beat only after checking how it connects to the prior beat.
   - For every beat after frame 1, primarily describe the visible change from the previous beat instead of naming a standalone pose. Treat each frame as the accumulated result of all previous frame changes plus the new change for that slot. Keep the continuity constraints stable: scale, facing identity, body center path, height, balance, contact points, spacing, easing, and weight transfer.
   - Prefer concrete spatial deltas over ambiguous state labels. Use a short phase label only when it helps identify the accumulated current frame. Describe how the body center, torso, head, hands, feet, contact, or weight shift changed from the previous beat.
   - When a beat is likely to be misread as an isolated pose, such as rotation, body crossing, occlusion, airborne motion, or contact transition, anchor it to the same arc, path, or contact transition established by the previous beat.
   - Continue until the action has the needed anticipation, contact or launch, key pose, passing or in-between poses, follow-through or overshoot, settle, and loop bridge or clear end pose.
   - Audit the completed list for too few frames: missing key poses, abrupt jumps, unclear contact, no readable follow-through, or a bad first-to-last loop bridge.
   - Audit the completed list for too many frames: repeated stills, duplicate silhouettes, tiny non-animated micro-changes, timing stalls, or extra beats that do not improve readability.
   - Audit the language before preparing the run: frame 1 is the starting pose, and every later frame must read as a cumulative continuation of the previous slot, primarily described by the new delta. Rewrite vague state labels into concrete spatial changes, using optional short phase labels rather than adding examples or action templates.
   - Revise the list by adding missing beats and deleting redundant beats. Only after this audit is clean may the list become `--frame-actions`.
   - Do not use few-shot examples or canned templates for this planning. Keep the concrete audited frame actions ready for the run setup, then use the number of audited frame actions as the frame count.
3. Prepare a run folder and manifest:

   ```bash
   SKILL_DIR="skills/animation-creator"
   python "$SKILL_DIR/scripts/prepare_animation_run.py" \
     --character-name "<Name>" \
     --character-prompt "<base character description>" \
     --action-id "<action-id>" \
     --action "<action description>" \
     --frame-actions "<frame 1 action>; <frame 2 action>; <frame N action>" \
     --project-root /absolute/path/to/session/project \
     --output-dir /absolute/path/to/run
   ```

   Run this command only after the sequential planning audit is complete. The `--frame-actions` value is the concrete final list Codex prepared, reviewed, and revised in step 2; it is not a user-provided template, a few-shot example, or a first-draft list.

   If `--output-dir` is omitted, the run directory is created under `/absolute/path/to/session/project/animation-runs/`. If a source image exists, pass it with `--source-character /absolute/path/to/image.png`.

4. If no source character was provided, generate the base character with `$image-creator` using the generated base prompt, save it to the manifest's base output path, and record it as the canonical base. The base prompt is an authoritative animation-production spec: one compact, readable, centered, full-body character with stable proportions, limited unnecessary detail, no scene, and a scale suitable for the nominal animation layout cell and safe area. It uses a flat white `#FFFFFF` background so the character palette can be inspected before choosing an action-sheet chroma key. Recording the base automatically selects a safe chroma-key color from the canonical base image and refreshes action prompts.

   Print the exact `$image-creator` prompt before generating:

   ```bash
   python "$SKILL_DIR/scripts/build_generation_prompt.py" \
     --run-dir /absolute/path/to/run \
     --job-id base-character
   ```

   Send stdout exactly as the final `$image-creator` prompt. Do not type a new prompt that merely resembles it.

   ```bash
   python "$SKILL_DIR/scripts/record_animation_result.py" \
     --run-dir /absolute/path/to/run \
     --job-id base-character \
     --source /absolute/path/to/generated/base.png
   ```

5. For each action job, call `$image-creator` with:
   - the action prompt file
   - `references/canonical-base.*` as the character identity input
   - `references/registration-guides/<action-id>.png` as the placement registration input after the canonical base is recorded
   - a destination inside the run directory, normally `generated/<action-id>.png`

   Print the exact `$image-creator` prompt from the job's markdown prompt file and input-image list:

   ```bash
   python "$SKILL_DIR/scripts/build_generation_prompt.py" \
     --run-dir /absolute/path/to/run \
     --job-id <action-id>
   ```

   Load the listed input images through `$image-creator`'s input-image workflow, then send stdout exactly as the final `$image-creator` prompt. The prompt must come from `build_generation_prompt.py`; do not reconstruct it manually.

   Always record the selected generated image, even if it was saved at the expected job path. `record_animation_result.py` records the source prompt hash and exact built prompt hash with the generated output.

   ```bash
   python "$SKILL_DIR/scripts/record_animation_result.py" \
     --run-dir /absolute/path/to/run \
     --job-id <action-id> \
     --source /absolute/path/to/generated/action-grid.png
   ```

6. Extract frames:

   ```bash
   python "$SKILL_DIR/scripts/extract_frames.py" --run-dir /absolute/path/to/run --action-id <action-id>
   ```

7. Finalize post-processing with the deterministic post-processing pipeline:

   ```bash
   python "$SKILL_DIR/scripts/finalize_animation_run.py" --run-dir /absolute/path/to/run --action-id <action-id>
   ```

   This checks recorded generated-job files, extracts frames from the known manifest layout, writes `qa/<action-id>-review.json`, composes and validates `final/<action-id>-frames.webp`, creates a contact sheet from that WebP sheet, writes `final/<action-id>.webp`, and records `qa/run-summary.json` with visual review still marked pending until Codex inspects the contact sheet or preview.

8. Inspect validation JSON, contact sheet, and WebP preview. Repair only the failed action when possible.

## Adding Actions To An Existing Run

For additional actions, reuse the run directory:

```bash
python "$SKILL_DIR/scripts/prepare_animation_run.py" \
  --run-dir /absolute/path/to/run \
  --add-action \
  --action-id "<new-action-id>" \
  --action "<new action description>" \
  --frame-actions "<frame 1 action>; <frame 2 action>; <frame N action>"
```

Then generate only that new action through `$image-creator` and run `finalize_animation_run.py` for that action.

## Prompt References

Read only the reference needed for the current step:

- `references/animation-output-contract.md` for frame size, frame count, background, format, and run manifest expectations.
- `references/qa-rubric.md` before accepting an action as complete.

## Defaults

Use these when the user does not specify otherwise:

- nominal layout-guide cell size: `512x512`
- the 16-frame maximum uses a `4x4` guide at `2048x2048`
- layout-guide safe margin: `30px` horizontal and `24px` vertical inside each nominal cell
- final frame size: preserves the generated sheet's actual per-cell size after chroma removal, guide-canvas cleanup, and component extraction
- frame count: derived from the completed per-frame action plan
- default layout: derived from the finalized frame count
- unused grid slots: when the recommended grid has more cells than planned frames, extraction ignores those slots even if generation fills them
- maximum frame count: `16`
- output format: `webp`
- final WebP: created by `finalize_animation_run.py` through `render_preview.py --write-final --formats webp`
- background mode: `chroma-key`
- chroma key: auto-selected safe high-saturation color, defaulting to green when no source image is available
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
