# New Animation Run

Read only when starting a new character run. `SKILL_DIR` is the animation skill directory; `project-root` is the session project root and `run-dir` is `.codex-skills/animation-creator/<run-id>/` relative to it, unless the user selects another workspace. Keep final delivery destinations separate from this working folder.

After auditing the motion plan:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/prepare_animation_run.py" \
  --character-name "<name>" --character-prompt "<character description>" \
  --action-id <action-id> --action "<description>" \
  --frame-actions "<beat 1>; <beat 2>; <beat N>" \
  --project-root <project-root> --run-dir <run-dir>
```

With a supplied image, add `--source-character <absolute-image-path>`; the helper preserves it as the canonical base. Otherwise generate and record job `base-character` using the main workflow before generating actions.

Omitting `--run-dir` creates a unique folder under `.codex-skills/animation-creator/`; retain the returned path for every later command. `--output-dir` is a legacy alias for the working folder, not the final delivery destination.

Pass `--fps <value>` when timing is requested and `--no-loop` for a non-looping action. Use the helper's defaults for unspecified settings. Output format is WebP; intermediate frames are PNG.

The preparation step writes the manifest, jobs, prompt files, and registration guides. After recording a generated base, use the refreshed prompts and guides rather than pre-base copies.
