# New Animation Run

Read only when starting a new character run. `SKILL_DIR` is the absolute animation skill directory; `project-root` and `run-dir` refer to the session project and its output folder.

After auditing the motion plan:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/prepare_animation_run.py" \
  --character-name "<name>" --character-prompt "<character description>" \
  --action-id <action-id> --action "<description>" \
  --frame-actions "<beat 1>; <beat 2>; <beat N>" \
  --project-root <absolute-project-root> --output-dir <absolute-run-dir>
```

With a supplied image, add `--source-character <absolute-image-path>`; the helper preserves it as the canonical base. Otherwise generate and record job `base-character` using the main workflow before generating actions.

Pass `--fps <value>` when timing is requested and `--no-loop` for a non-looping action. Use the helper's defaults for unspecified settings. Output format is WebP; intermediate frames are PNG.

The preparation step writes the manifest, jobs, prompt files, and registration guides. After recording a generated base, use the refreshed prompts and guides rather than pre-base copies.
