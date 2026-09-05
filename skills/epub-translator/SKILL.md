---
name: epub-translator
description: Translate EPUB books as new target-language editions with deterministic mechanics — reading-flow IR extraction, slim narrative chunking, agent-owned translation, and build-time reconstruction into a brand-new EPUB. Use for .epub translation, vertically-written Japanese EPUB processing, translation continuity across large books, target-edition layout adaptation, EPUB packaging, and image text replacement workflows.
---

# EPUB Translator

The helper never patches source XHTML. It extracts a **reading-flow IR**, packs **slim chunks**, and **deterministically builds** a brand-new target-language EPUB. Codex owns language, translation quality, and edition policy; `$image-creator` owns raster-image generation. `$image-creator` is for image pixels only — never prose translation.

The original EPUB is evidence, not an output contract. Source wrappers, paragraph shapes, fixed offsets, and ruby/furigana are flattened; only reading order, anchor order, link destinations, and image payloads are invariant. Target XHTML and CSS are generated, not patched.

## Operating Contract

- Translate into the user's requested language. If no language is named, use the current user's language.
- **Deterministic mechanics are helper-owned; language is Codex-owned.** The helper extracts, chunks, and builds; it never invents target prose. Codex owns source/target language inference, prose quality, terminology and voice decisions, and edition policy. Never delegate prose, glossary, or translation work to subagents or background workers, and never call external machine-translation engines or translation APIs for prose, metadata, or chunks.
- Helper commands expose EPUB mechanics only — don't put glossary hints or translation choices into plan files.
- Treat user glossaries, notes, or sample translations as optional context for Codex.
- Always produce a **new** EPUB at a path distinct from the source.
- Every editable image job must end as `skipped_no_text` or `edited`.
- For raster image text, use direct visual review by the main agent. Do not use OCR or automated bulk image-text extraction.

## Helper Boundary

The helper may: inspect an EPUB; ingest it into a run folder (extract the flow IR, write chunks, export raster sources, draft `edition.json`); report `status` plus the seam of the last finished chunk; record an image job result and keep its review copy; and generate a brand-new EPUB from flow IR plus translations plus `edition.json`, with completeness and internal-link validation plus a terminology-consistency report. It treats images as files plus job records and never transcribes pixels into prose.

## Workflow

Set `<skill-dir>` to the installed `epub-translator` skill directory.

1. **Inspect and ingest**
   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py inspect --epub <book.epub> --json
   uv run --script <skill-dir>/scripts/epub_translate.py ingest --epub <book.epub> --workdir <run-dir>
   ```
   `ingest` unpacks to `<run-dir>/unpacked/`, writes the normalized flow IR to `flow/book.flow.json` (tree nodes: ruby flattened, layout wrappers unwrapped, container structure owned by parents, element ids and title/aria-label preserved, report in `flow_stats`), writes slim translation chunks to `chunks/` (schema v3), exports editable raster images to `images/source/`, creates `image-jobs.json`, drafts `edition.json`, and writes `manifest.json`. Treat this as cost already paid: do not re-extract or rewrite the run except through the helper.

2. **Decide edition policy** (`<run-dir>/edition.json`)
   - Read `flow/book.flow.json` and early prose; then write `<run-dir>/edition.json`. Language inference is Codex-owned: Codex must set `target_language` / `language_tag` and, when needed, `page_progression_direction` (e.g., `"ltr"` for Korean) and related finite enums — no prose in this file. Treat missing or wrong values here as the code owning them being wrong and fix them in place. Set target page progression and related fixed policy from the target edition, not from the numeric run — use the content to fix the code that sets the defaults, do not fudge each EPUB.
   - `edition.json` contract (finite enum values only — no prose keys):
     ```json
     { "schema_version": 1, "target_language": "ko", "language_tag": "ko", "page_progression_direction": "ltr" }
     ```
   - No chunk text, translation, or image-brief prose inside `edition.json`. The helper validates the schema; Codex's edition choices own the text consequences that follow.

3. **Translate** `chunks/chunk-*.json` -> `translations/chunk-*.json`
   - Work through chunks **in numeric order, sequentially, as the main translator**. Before starting a chunk, read `status` (next chunk plus seam tail) plus `translation-notes.md` for continuity; the seam shown there is the only memory you're promised across a compression boundary — without it a translated chunk may be summarized away, so re-establish context explicitly.
   - Maintain `<run-dir>/translation-notes.md` as the lead translator's compact global state — the **rolling summary** plus the minimal glossary (`source → target`, one entry per name/term/catchphrase) are the primary defense against an inconsistent seam; without them quality is lost the moment the viewer compresses.
   - Skinny chunks are not an excuse for short thinking — a single `{id, source}` block can hide a long beat, an aside anchor, and a separator; read the flow context (block order, block types, anchors, nearby headings) before translating any chunk.
   - Peripheral text (image `alt`, OPF metadata, nav labels) is already isolated into its own chunk so that prose chunks stay purely narrative. Translate the peripheral chunk with terse UI-prose discipline, not literary rhythm.
   - **Text ownership and parallelism**: Content translation is the main translator's sequential craft. Do not delegate prose, metadata, or chunk translation to subagents or parallel workers; do not use MT output as draft, glossary source, or validator; context, voice, and terminology must live in one reader's working memory.

4. **Image jobs**
   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py record-image --workdir <run-dir> --image-id <id> --skip-no-text
   uv run --script <skill-dir>/scripts/epub_translate.py record-image --workdir <run-dir> --image-id <id> --replacement <edited-image>
   ```
   Resolve every job from `image-jobs.json` using the image-job contract below.

5. **Build and validate**
   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py build --workdir <run-dir> --output <translated.epub>
   uv run --script <skill-dir>/scripts/epub_translate.py validate --workdir <run-dir> --output <translated.epub>
   ```
   `build` fails when translations are missing, an internal link points to a missing anchor, `edition.json` holds an invalid value, or an editable image job is still `pending_review`. It also writes `build-report.json` with `untranslated_candidates` (translation === source, often proper nouns) and `divergences` (same source rendered into multiple distinct translations — flagged for Codex review, not failed). Wrong-translation quality is not auto-checkable; the main agent's editing is the quality gate.

## Natural Translation Contract

The target must read like publishable prose, not a literal conversion.

- Preserve plot, speaker intent, emotional temperature, and character relationships.
- Adapt sentence structure to the target language. Translationese is a defect.
- Match genre, scene mood, narration distance, pacing, and formality; keep each character's voice steady (age, register, bluntness, humor, habits).
- Translate dialogue as speech for that character; narration as prose for that atmosphere; localize idioms and beats that would sound foreign.
- Preserve the chosen names, terms, titles, honorific policy, and style consistently — the glossary in `translation-notes.md` owns that list.
- Never add plot, explanations, censorship, summaries, or translator footnotes; translate only what's there, in the voice that was chosen.
- Target typography, punctuation, spacing, and line rhythm follow target publishing convention.

Quality gate before writing each chunk: re-read the target text without the source — dialogue should sound like the character, narration should keep the scene's mood, and punctuation should match the chosen style. Update `translation-notes.md` only with reusable decisions; do not invent book-level facts.

## Chunk and Item Contract

Chunks are helper-written and translator-read; they are not Codex-owned evidence. Items inside chunks are the translation units.

- Input: `chunks/chunk-*.json` — `{ schema_version: 3, chunk_index, kind: "peripheral" | "prose", items: [{ id, source, block_id, block_type, href, inline? }] }`
  - `peripheral` holds image `alt`, element `title`/`aria-label`, and OPF metadata (terse UI prose). Ignore the chunk's `kind` for translation quality; use `source` only. Attributes on flattened transparent inline wrappers (span etc.) have no output node and are not carried into the target edition.
  - `prose` holds narrative text in spine order. A single `{id, source}` item may already be an entire sentence or a breath unit pulled from a ruby-wrapped `漢<rt>かん</rt>字` — do not re-split it.
  - `inline` (when present) records emphasis and links, e.g., `[{tag:"em"}]` or `[{tag:"a", href:"#note1"}]`. It is layout hinting for the builder, not translation content — keep emphasis on the right target words, put the linked target words on the link slot, do not invent links.
- Output: `translations/chunk-*.json` — `{ schema_version: 3, chunk_index, translations: [{ id, translation }] }`
  - One row per input item, preserving every `id` exactly.
  - `translation` is pure target-language text — newly written, one string per item, no notes, alternatives, or markup.
  - If the translator cannot finish a chunk in one turn, do not fabricate rows; record real progress and let `status` show the seam for the next turn.
- Do not create intermediate placement files or run-local conversion scripts between items and rows.
- **Chunk packing invariants** (helper guarantees; agent should rely on them): block-atomic (a block's slots never split), scene/heading-aware breaks at budget, peripheral isolated, source order preserved. The agent translating a chunk should not second-guess the packing.

## Image Job Contract

`ingest` exports editable raster images under `<run-dir>/images/source/` and creates `<run-dir>/image-jobs.json`. `record-image` keeps the review copy for every resolved job under `<run-dir>/images/replacements/` (edited keeps the generated replacement; `skipped_no_text` keeps a copy of the reviewed source).

Image review and image text translation are isolated one-image tasks. Before opening source images for review, verify that the current session can spawn, wait on, and close subagents. Image processing requires a dedicated per-image subagent path; do not silently fall back to main-thread image generation.

Image text reading boundary:

- The main agent must directly view each source image needed for triage.
- Do not run OCR, computer-vision text extraction, image-text transcription scripts, CLI tools, libraries, services, or model-assisted bulk extraction against raster images.
- Do not create contact sheets, visual grids, crops, or intermediate sheets for reading image text.
- Use existing prose, `translation-notes.md`, glossaries, and user context only as book context; they are not substitutes for direct image review.
- Put exact source-to-target overrides in an image brief only when the main agent can justify them from direct visual review or non-image book context.
- Image subagents do not own book-level translation judgment, image triage, or text extraction.

Subagent capability gate:

1. Confirm that agent management tools are callable for spawning, waiting on, and closing subagents.
2. Confirm that an image subagent can receive exactly one local source image and the `$image-creator` skill instructions.
3. Use available subagent execution capacity to avoid waiting on one image while other image-generation capacity is idle.
4. If the gate fails, stop image processing before image review and report the missing capability.

Per-image dispatch contract:

1. Process jobs from `<run-dir>/image-jobs.json`; do not make a contact sheet or bulk visual sheet for triage.
2. Inspect source images one at a time, only when an edited-image subagent can be dispatched immediately if the image needs editing.
3. Do not inspect ahead to build a backlog of image briefs.
4. If the image has no visible source-edition text that needs translation, record `skipped_no_text`; this copies the reviewed source into `<run-dir>/images/replacements/` so the run shows the image was checked.
5. If the image has visible source-edition text, write an image edit brief: target language; the job ID; source and replacement paths; a broad source text scope; explicit text overrides for clearly read, context-critical strings; a preservation policy; and an edit-oriented prompt for `$image-creator`; plus an `$image-creator` handoff summarizing the execution path: split the creative edit request from the save destination, rewrite as concise English generation prompt, pass the provided local source image path as the sole `referenced_image_paths` entry without a `view_image` preparation step, call `image_gen`, copy or save the built-in tool's generated source file to the replacement path with the `$image-creator` file save helper, keep the generated replacement exactly as returned without matching dimensions, aspect ratio, extension, or format, and report the `$image-creator` response fields.
6. Spawn one independent image subagent for that image immediately after its brief is ready; pass only that local source image path as the sole `referenced_image_paths` entry plus the brief.
7. Keep using available subagent capacity with later jobs, still one visually reviewed image at a time.
8. Wait on active subagents only to harvest completed jobs or free capacity.
9. For each completed subagent, record the replacement with `record-image`, then close that subagent immediately.
10. If a subagent fails to save a replacement, close it, keep that job unresolved, adjust the brief as needed, and dispatch a new subagent for the same image when capacity is available.

Operational rules:

- Do not use OCR, contact sheets, visual grids, or crop sheets.
- Maintain an active job ledger mapping job ID to source path, replacement review path, subagent ID, status, and brief.
- Translate visible communicative text of the source edition; preserve non-source-edition text unless book context makes it part of the message.
- Edit-oriented prompts treat the provided image as the image to modify.
- Keep generated replacement files as returned; do not normalize, resize, or recompress before recording.

Main-agent image brief contract, image subagent execution contract, subagent return contract, and image recording commands are unchanged from the previous revision — the brief, handoff wording, generation-mode assertion, and `record-image` flags are the same. Unsupported image media types are listed in `<run-dir>/image-jobs.json` as `unsupported` (their count is `unsupported_image_count` in `<run-dir>/manifest.json`); handle them only when the user explicitly requests manual handling.

## Completion Criteria

- All `translations/chunk-*.json` rows exist; `build` succeeds and `validate` succeeds.
- Text was translated **directly by the main translator in chunk order**, without text-worker subagents or parallel content translation.
- Every editable image job is resolved through the per-image contract.
- `build` writes a new EPUB path that is not the source EPUB.
- Final response reports the output EPUB, run folder, item counts, per-chunk progress, image job summary, unsupported image count, any `build-report.json` flags that needed manual review (`divergences`, `untranslated_candidates`), and the build/validation result.
- No rewrites of `translation-notes.md` beyond the curated rolling summary and glossary — the seam exists because the notes were kept minimal and stayed recoverable after compression.
