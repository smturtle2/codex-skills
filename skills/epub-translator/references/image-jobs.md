# EPUB Image Jobs

Read only when `image-jobs.json` contains editable raster images. The main agent owns visual triage and translation choices; one independent image subagent executes each edit using `$image-creator`.

## Capability and Reading Boundaries

Before reviewing images, check that the session can dispatch image subagents, collect their results, and reclaim execution capacity through its supported lifecycle. Use automatic capacity release where the host provides it; do not require a tool literally named `close`. Ensure each worker can access its one source image and the `$image-creator` instructions.

If this path is unavailable, report the image-processing blocker and leave those jobs unresolved. Do not silently substitute main-thread image generation.

- Directly view one source image at a time. No OCR, automated image-text extraction, contact sheets, grids, or crop sheets.
- Review only when an edit worker could be dispatched immediately; do not build a backlog of image briefs.
- Use book context and glossary decisions to support visual review, not replace it. Add exact text overrides only when justified by direct reading or non-image book context.
- Translate visible communicative source-edition text; preserve other text unless the book context makes it part of that message.

## Dispatch and Record

1. Take the next unresolved editable job and inspect its local source under `images/source/`.
2. If no visible text needs translation, record `skipped_no_text`.
3. Otherwise prepare a brief with job ID, target language, source path, destination, text scope, justified source-to-target overrides, and visual preservation requirements.
4. Dispatch a fresh worker with context limited to that brief, exactly one local image input, and the instruction to read and use `$image-creator`. Keep generated replacements exactly as returned; do not request source dimension, aspect-ratio, extension, or format matching.
5. Continue with later jobs while capacity is available. Track job ID, source, destination, worker ID, brief, and status in an active job ledger.
6. Collect results to record finished jobs or free capacity. Release finished workers through the host's supported lifecycle.

Require the worker to return its job ID, saved replacement path, exact final prompt, actual input path, and whether built-in generation and saving succeeded. Verify that the input matches the assigned source and the returned replacement is the saved artifact.

Set `SKILL_DIR` to the absolute directory containing the EPUB skill's `SKILL.md`:

```bash
uv run --script "$SKILL_DIR/scripts/epub_translate.py" record-image --workdir <run-dir> --image-id <id> --skip-no-text
uv run --script "$SKILL_DIR/scripts/epub_translate.py" record-image --workdir <run-dir> --image-id <id> --replacement <saved-image>
```

Use exactly one recording mode per job. Recording keeps a review copy in `images/replacements/`, detects the actual PNG/JPEG/GIF/WebP payload format, and records its hash. Do not normalize, resize, or recompress the replacement first. Only a successful recording resolves the job. If the saved replacement changes, record the intended file again before building.

The published payload retains the source archive location so references inside preserved media stay valid. Its OPF MIME describes the actual bytes; its archive suffix may still be the original one, such as PNG bytes at `image/cover.jpg`. Do not rename or convert the image to make its suffix match.

## Failures and Unsupported Media

If a worker fails, retain the unresolved job and error, release its execution capacity, and fix an identified cause before dispatching a fresh worker. If no supported remedy is available, report the blocker rather than repeat the same failed call.

Non-editable image formats, including SVG, are listed as `unsupported` in the jobs file and counted by `unsupported_image_count` in the manifest. Existing SVG and other resources are preserved; opaque SVG, MathML, audio/video, and similar inline content are retained and counted under `unsupported_inline_media_count`. Their text is outside this raster-editing workflow, so report it without claiming it was translated. Missing or unreadable source resources block publication. Further manual editing of unsupported media requires an explicit user request.
