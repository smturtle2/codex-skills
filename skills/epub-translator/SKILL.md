---
name: epub-translator
description: Translate EPUB books into natural prose in a new target-language edition, preserving reading order, links, and translation continuity, with image-text editing when needed.
---

# EPUB Translator

Codex owns language, voice, terminology, and edition choices. The bundled helper extracts reading-flow IR and chunks, stores image job results, and builds a new EPUB; it never writes translations.

## Translation Contract

- Use the requested target language, defaulting to the user's language.
- Translate prose, metadata, and glossary content directly as the main agent in numeric chunk order. Do not delegate text translation or use external machine translation for drafts, terminology, or validation.
- Preserve plot, speaker intent, emotional tone, and relationships. Adapt syntax, idioms, punctuation, and dialogue to natural target-language prose while maintaining character voice.
- Do not add plot, explanations, censorship, summaries, or translator footnotes.
- Preserve reading order, anchors, link destinations, and source image payloads except for explicitly edited image jobs. Source layout wrappers and ruby/furigana are flattened; the helper constructs target XHTML and CSS.
- Write the new EPUB to a path distinct from the source.

Set `SKILL_DIR` to this skill's absolute directory and choose a persistent run folder. Read [references/translation-data.md](references/translation-data.md) before writing edition settings or translation JSON; consult it again only when its contract is missing from context.

## Start or Resume

For a new book:

```bash
uv run --script "$SKILL_DIR/scripts/epub_translate.py" inspect --epub <book.epub> --json
uv run --script "$SKILL_DIR/scripts/epub_translate.py" ingest --epub <book.epub> --workdir <run-dir>
```

For an existing run, reuse its extracted flow and chunks rather than ingesting again:

```bash
uv run --script "$SKILL_DIR/scripts/epub_translate.py" status --workdir <run-dir>
```

Use `status` and `translation-notes.md` to recover progress. Fix actual run-data errors at their owning files; routine edition choices do not require rewriting the helper.

## Work Through the Book

1. Read early prose and relevant flow context, then set `edition.json` for the target language and reading direction. Keep prose and glossary notes out of this configuration.
2. Before each chunk, read `status`, its seam tail, and `translation-notes.md`. Read nearby flow context when block boundaries, headings, or links affect interpretation.
3. Write one translation per input item, preserving every ID. Do not re-split items, rewrite source chunks, or create intermediate conversion scripts.
4. Re-read the target prose for natural dialogue, consistent voice, scene mood, and typography before accepting the chunk.
5. Keep `translation-notes.md` compact: a rolling narrative summary and reusable name, term, honorific, and style decisions. Preserve unresolved context without inventing book-level facts.
6. Inspect `image-jobs.json`. When it contains editable raster jobs, read [references/image-jobs.md](references/image-jobs.md) and resolve each through main-agent visual triage and a dedicated image subagent when editing is needed. Do not use OCR or bulk image-text extraction.
7. Build and validate only after all text and editable image jobs are complete.

Peripheral metadata and image attributes should read as concise labels or descriptions; narrative chunks should retain literary voice. Judge the actual content instead of treating chunk size as a quality target.

## Build and Finish

```bash
uv run --script "$SKILL_DIR/scripts/epub_translate.py" build --workdir <run-dir> --output <translated.epub>
uv run --script "$SKILL_DIR/scripts/epub_translate.py" validate --workdir <run-dir> --output <translated.epub>
```

Review `build-report.json`, including `untranslated_candidates` and `divergences`. Proper names and context-sensitive translations may be valid; resolve findings through source review. Mechanical validation does not prove translation quality.

If interrupted, retain real completed rows and notes, then resume from `status`; never fabricate missing translations. A blocked image job remains unresolved even if text work can continue.

Report the output EPUB and run folder, item and chunk progress, image-job results and unsupported count, reviewed report findings, and build/validation results. Claim completion only when every translation exists, every editable image job is resolved, and both commands succeed.
