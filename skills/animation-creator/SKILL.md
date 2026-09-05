---
name: animation-creator
description: Create character animations from a source image or character description, preserving identity across actions and exporting animated WebP assets.
---

# Animation Creator

Use one canonical character per run and `$image-creator` for every generated base or action sheet. Do not synthesize character frames with local drawing, tiling, or warping scripts.

Set `SKILL_DIR` to this skill's absolute directory. Run helpers with `uv run --project "$SKILL_DIR"` from the session project. Default runs to `animation-runs/<run-id>/`; resolve requested relative destinations from the project root.

## Plan the Action

Establish the character source and requested action; ask for the action if missing. Use requested timing and loop settings, defaulting to a looping WebP with full-body poses. Record an explicit partial-body request as the output contract.

Build adjacent motion beats before choosing a frame count. Each beat after the starting pose should describe the visible change from its predecessor, preserving character scale, facing, body-center path, balance, contact, and weight transfer.

Audit for needed anticipation, contact or launch, passing poses, follow-through, settling, and loop bridge or clear end pose. Remove duplicate silhouettes and tiny redundant steps. The audited beat count becomes the frame count, up to 12. Avoid flip/mirror/rotation language unless the action actually needs that transformation.

## Prepare or Extend

For a new run, read [references/run-setup.md](references/run-setup.md). Preserve the source or generated base as `references/canonical-base.png` without background removal.

For a later action, reuse the run and canonical base unless the user requests a new character:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/prepare_animation_run.py" \
  --run-dir <run-dir> --add-action --action-id <action-id> \
  --action "<description>" --frame-actions "<beat 1>; <beat 2>; <beat N>"
```

Read [references/animation-output-contract.md](references/animation-output-contract.md) before generating an action sheet when that contract is not already in context. The current pipeline requires `rembg-matte` raw sheets and rembg-normalized alpha outputs.

## Generate and Record

Build the prompt for the base job or selected action:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/build_generation_prompt.py" \
  --run-dir <run-dir> --job-id <job-id>
```

Give stdout to `$image-creator` as the authoritative final prompt, unchanged. Do not rewrite it or maintain a separate `prompts/image-creator/` copy.

For each action, supply both `references/canonical-base.png` as identity input and `references/registration-guides/<action-id>.png` as the edit template. Save attempts under the run's `generated/attempts/` with non-overwriting names.

Inspect the returned raw action sheet against the output contract: fixed grid and slot order, complete poses, reserved matte, retained outer cell borders, removed inner guides, and continuous character identity and motion. Record only a selected image that passes this review:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/record_animation_result.py" \
  --run-dir <run-dir> --job-id <job-id> --source <saved-source-image>
```

Recording a base preserves it and refreshes action prompts/guides. Recording an action performs per-slot rembg processing and reassembles the alpha sheet. If processing fails, report the error; do not substitute a different background-removal pipeline.

## Finalize and Review

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/finalize_animation_run.py" \
  --run-dir <run-dir> --action-id <action-id>
```

Read [references/qa-rubric.md](references/qa-rubric.md) before acceptance. Review validation results, the contact sheet, and animation where a viewer is available; deterministic checks alone cannot establish identity or motion quality. Repair the failed action or processing step without recreating valid work.

Report the run and canonical-base paths, generated action IDs, final WebP links, contact-sheet and validation links, use of `$image-creator` for base/actions, and repairs, omissions, or visual-review limitations.
