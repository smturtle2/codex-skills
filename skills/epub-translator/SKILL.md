---
name: epub-translator
description: Translate EPUB books from any source language into the user's requested language as natural Codex-authored published book prose without external machine-translation runtimes, apply a post-translation target-structure pass from Codex-authored XHTML composition plans, adapt EPUB layout and reading structure for the target-language edition through explicit mechanical plans, package a new EPUB, and resolve visible original text in raster images through main-agent visual triage, main-authored image edit briefs, and required one-image-per-subagent $image-creator execution. Use for .epub translation, literary EPUB prose translation, text-slot chunk workflows, target-edition EPUB composition and layout adaptation, EPUB packaging/validation, and original image text replacement workflows.
---

# EPUB Translator

Translate an EPUB as a book, not as a set of isolated strings. Use the bundled helper only for deterministic EPUB mechanics. Codex owns prose translation, target-edition layout policy, and style judgment. `$image-creator` owns visual image editing.

## Operating Contract

- Translate into the user's requested language. If the user does not name a target language, use the current user's language.
- Codex must author content translations directly from the EPUB text, user context, and translation notes. Do not install, discover, download, run, or use external translation runtimes, machine-translation engines, translation libraries, model packs, CLI translators, APIs, services, or language-model packages for prose, content, metadata, or chunk translation.
- Do not use package managers, model indexes, package indexes, or dependency probes to look for translation capability. Missing local translation tooling is irrelevant to this workflow.
- Helper commands expose EPUB mechanics only. Language, terminology, glossary hints, and translation choices stay in Codex context.
- Treat user-provided glossaries, notes, sample translations, or adjacent files as optional context for Codex decisions.
- Always produce a new EPUB at a path distinct from the source EPUB.
- Treat original EPUB layout as source-edition structure. Preserve book semantics and archive integrity, while adapting reading direction, writing mode, CSS, XHTML structure, ruby/furigana handling, spacing, and punctuation layout for the target-language edition.
- Use chunk JSON as the text source of truth and `apply-text` as the write-back mechanism.
- Every editable image job must end as `skipped_no_text` or `edited`.
- For raster image text, use direct visual review by the main agent. Do not use OCR or automated image-text extraction.

## Helper Boundary

The helper script is an EPUB mechanics tool. It may:

- inspect EPUB structure;
- unpack the EPUB into a run folder;
- extract text units and safe write-back slots;
- export editable raster images as source files;
- apply completed slot translations;
- export translated XHTML structure blocks for Codex-owned target-structure planning;
- apply an explicit Codex-authored target-structure plan to translated XHTML;
- apply an explicit target-edition layout plan to OPF, CSS, or XHTML;
- record an image job result;
- embed a finished replacement image by copying the generated file bytes into the EPUB run;
- package and validate the translated EPUB run.

The helper script must not read, OCR, transcribe, classify, translate, or propose text from raster image pixels. It must treat images as files plus job records only.

Main-agent-owned work:

- translate all prose, content, metadata, and chunk text directly without external translation runtimes;
- infer source and target language policy;
- use optional glossary or terminology hints;
- directly read the translated prose and decide target-language paragraphing, visual paragraph separation, line break, dialogue/narration rhythm, and XHTML composition;
- decide target-edition layout policy;
- visually inspect one exported source image at a time for image job triage;
- decide whether an image job is `skipped_no_text` or requires an edited replacement;
- prepare image edit briefs with translation context, explicit text overrides, preservation policy, and prompt constraints.

Image-subagent-owned work:

- execute one provided image edit brief through `$image-creator`;
- receive exactly one source image as the edit input for that image job;
- save the generated replacement image to the requested path;
- report the saved replacement path and final prompt used.

If a workflow needs translation judgment, layout judgment, image triage, or prompt intent, the main agent owns it. If a workflow needs image generation, a dedicated per-image subagent executes the main-authored edit brief through `$image-creator`, then hands the completed replacement image back to the main agent for helper recording and closure.

## Workflow

Set `<skill-dir>` to the installed `epub-translator` skill directory.

1. Inspect and prepare:

   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py inspect --epub <book.epub> --json
   uv run --script <skill-dir>/scripts/epub_translate.py prepare --epub <book.epub> --workdir <run-dir>
   ```

2. Infer the translation and target-edition layout policy from metadata, user context, and early prose. Maintain `<run-dir>/translation-notes.md` as the lead translator's state file when useful.

3. Translate `chunks/chunk-*.json` in chunk order into matching `translations/chunk-*.json` files. The main translator must produce every text translation row directly and sequentially.

4. Apply text:

   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py apply-text --workdir <run-dir> --translations <run-dir>/translations
   ```

5. Export the translated XHTML structure, directly read the translated prose, perform Codex-authored cleanup and composition target-structure passes, and apply the resulting plans:

   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py export-target-structure --workdir <run-dir> --output <run-dir>/target-structure-source.json
   uv run --script <skill-dir>/scripts/epub_translate.py apply-target-structure --workdir <run-dir> --plan <run-dir>/target-structure-cleanup-plan.json
   uv run --script <skill-dir>/scripts/epub_translate.py export-target-structure --workdir <run-dir> --output <run-dir>/target-structure-after-cleanup.json
   uv run --script <skill-dir>/scripts/epub_translate.py apply-target-structure --workdir <run-dir> --plan <run-dir>/target-structure-composition-plan.json
   ```

6. If the original EPUB layout does not fit the target-language edition, write `<run-dir>/layout-plan.json` and apply it:

   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py apply-layout --workdir <run-dir> --plan <run-dir>/layout-plan.json
   ```

7. Resolve each editable image job from `<run-dir>/image-jobs.json` using the image job contract below.

8. Package and validate:

   ```bash
   uv run --script <skill-dir>/scripts/epub_translate.py package --workdir <run-dir> --output <translated.epub>
   uv run --script <skill-dir>/scripts/epub_translate.py validate --workdir <run-dir> --output <translated.epub>
   ```

## Natural Translation Contract

The target EPUB must read like publishable prose in the target language. It must not read like a literal conversion of source slots.

Required behavior:

- Preserve meaning, plot facts, speaker intent, emotional temperature, and character relationships.
- Adapt sentence structure to the target language. Source-language mechanics should not survive when they create translationese.
- Match the book's genre, scene mood, narration distance, pacing, and formality.
- Keep character voices consistent across the entire book: age, social position, bluntness, politeness, humor, sarcasm, regional flavor, and recurring speech habits.
- Translate dialogue as natural speech in the target language while preserving subtext and relationship dynamics.
- Translate narration as prose that fits the book's atmosphere, not as explanatory paraphrase.
- Localize idioms, jokes, rhetorical emphasis, and emotional beats when direct translation would sound unnatural.
- Preserve recurring names, terms, titles, honorific policy, and stylistic choices consistently.
- Avoid adding plot information, explanations, censorship, summaries, or translator notes.

Target-language publishing conventions control typography, punctuation, spacing, and line rhythm. Preserve a source-edition mark only when it still serves the translated text.

`translation-notes.md` should stay concise and track only reusable decisions:

- genre and atmosphere;
- narration policy;
- dialogue and character voice policy;
- terms, names, titles, organizations, catchphrases, and intentionally untranslated words;
- target-language punctuation and typography policy;
- target-edition layout and reading-direction policy;
- unresolved decisions and later consistency corrections.

## Target Structure Pass Contract

After `apply-text` succeeds, treat the translated EPUB as a target-language draft that still inherits source-edition XHTML structure. Perform a separate target-structure pass before layout normalization and image handling.

The target-structure pass is not a second translation pass. Use the already translated target text as the editing material. Revise wording only when the structure review exposes a translation defect that must be corrected for the target-language edition.

Codex owns all target-structure decisions:

- decide source-structure cleanup policy, paragraph grouping, paragraph splitting, visible paragraph separation, dialogue and narration rhythm, line-break use, scene-transition spacing, ruby/furigana removal or retention, and prose block composition according to the target language;
- use `target-structure-source.json` only as the current translated XHTML map;
- create explicit cleanup and composition plans as mechanical plans;
- keep book meaning, content order, and target-language prose intact while reshaping structure;
- personally read the translated prose in order before deciding paragraph boundaries. Do not derive composition from source child counts, maximum character counts, regular expressions, source paragraph restoration, or helper/script-generated readability heuristics.

The helper owns only mechanical application:

- apply exactly the Codex-authored target-structure plan;
- replace only the specified contiguous child-element ranges with the supplied XHTML fragments;
- verify that preserved references such as `id`, `href`, and `src` from replaced ranges still exist in the new fragment;
- reject invalid XHTML fragments or fragments containing `script` or `style`;
- record `target_structure_status: "applied"` after successful application.

The helper must not audit, classify, infer paragraphing, merge or split blocks by itself, judge translation quality, decide whether a structure is acceptable, prefer one structure, or force the source edition's structure.

Required subpasses:

1. Cleanup pass:
   - Codex must inspect every XHTML document, not only long prose documents;
   - remove or retain source-edition-only structures according to the target-language edition policy;
   - when removing wrappers such as ruby/furigana structures, preserve translated base text and move required references to the nearest semantically equivalent replacement element;
   - never satisfy reference preservation by moving anchors to an unrelated location when a local placement is available.
2. Composition pass:
   - read the translated prose document by document, in book order, before writing replacement XHTML;
   - reshape paragraphs, line breaks, scene spacing, dialogue turns, headings, lists, tables, blockquotes, and image-adjacent text for the target-language reading experience;
   - make paragraph units visible with actual XHTML structure at the intended paragraph boundaries;
   - when a visible blank paragraph break is required, put a real spacer block in the target-structure plan, such as `<p class="para-gap"><br /></p>`, and use CSS only to size or normalize that explicit block;
   - do not treat separate `<p>` elements, CSS margin changes, or line-height changes as sufficient when the target edition needs a visible paragraph break tag;
   - use the target language's published prose rhythm, not source XHTML child count, as the paragraphing authority;
   - split overlong blocks when they contain multiple breath units, scene beats, speaker turns, or rhetorical turns;
   - merge only when a source split divides one target-language sentence, phrase, or inseparable beat;
   - do not merge across speaker turns, headings, scene transitions, list/table boundaries, blockquotes, image references, navigation anchors, or meaningfully separate emphasis blocks;
   - write replacement XHTML only after deciding the intended reading rhythm from the prose itself.
3. Verification loop:
   - re-export target structure after each applied plan;
   - Codex must read the exported XHTML map and current XHTML for source-structure residue and target-language readability defects;
   - if the structure still conflicts with the target-language edition policy, write and apply another explicit plan;
   - finish only when remaining source-edition structures or unusual paragraphing choices are intentionally retained for a documented target-edition reason.

`target-structure-plan.json` contract:

```json
{
  "schema_version": 1,
  "documents": [
    {
      "href": "item/xhtml/p-001.xhtml",
      "replacements": [
        {
          "parent_path": "0/1",
          "start": 3,
          "end": 6,
          "xhtml": "<p>...</p><p>...</p>"
        }
      ]
    }
  ]
}
```

Rules:

- `parent_path` identifies the parent element path from `target-structure-source.json`.
- `start` is inclusive and `end` is exclusive over that parent's child elements.
- `xhtml` must be a valid XHTML fragment containing element children.
- Use an empty `documents` list for an explicit no-op target-structure pass.
- Do not use this plan for OPF, CSS, image replacement, or text translation.

## Target Edition Structure Contract

The translated EPUB is a target-language edition. Structure changes are required when the source edition's structure exists to serve the source language rather than the book's meaning.

Preserve:

- archive validity, OPF manifest references, spine item order, navigation targets, filenames, links, media references, metadata roles, accessibility slots, and meaningful inline semantics;
- the intended book flow and content order;
- existing non-replaced image references.

Change when needed:

- OPF `page-progression-direction`;
- CSS `writing-mode`, vendor writing-mode properties, `direction`, text orientation, vertical-layout spacing, and source-language typography rules;
- XHTML attributes or wrappers that force source-language reading direction or writing mode;
- ruby/furigana display when it no longer serves the target-language edition;
- punctuation, quote marks, line rhythm, and spacing according to target-language publishing conventions;
- paragraph margins, indentation, scene-break spacing, line height, and spacer-block styling that supports the explicit paragraph-break tags inserted by the target-structure plan.

Codex must decide the target-edition structure policy. The helper may only apply an explicit mechanical plan.

`layout-plan.json` is optional, but required whenever the source EPUB's layout would make the translation read in the wrong direction or writing mode. Its contract:

```json
{
  "schema_version": 1,
  "opf": {
    "page_progression_direction": "ltr"
  },
  "css": [
    {
      "href": "*",
      "replace_declarations": {
        "writing-mode": "horizontal-tb",
        "-epub-writing-mode": "horizontal-tb",
        "-webkit-writing-mode": "horizontal-tb",
        "direction": "ltr"
      },
      "remove_declarations": ["text-orientation"],
      "append": "html, body { writing-mode: horizontal-tb; direction: ltr; }"
    }
  ],
  "xhtml": [
    {
      "href": "item/xhtml/p-001.xhtml",
      "set_attributes": [
        {"path": ".", "attributes": {"dir": "ltr"}}
      ],
      "remove_attributes": [
        {"path": ".", "names": ["style"]}
      ]
    }
  ]
}
```

Rules:

- Use only explicit file paths or `href: "*"` for all CSS files.
- Use `page_progression_direction: "ltr"` or `"rtl"` to set the OPF spine value. Use `null` to remove it.
- Use CSS declaration replacement/removal only for mechanical layout normalization. Do not put translated prose in CSS.
- Use XHTML attribute changes only for layout attributes. Do not use layout plans to translate text.
- Omit sections that are not needed.

## Text Ownership and Parallelism

Content translation is sequential, main-owned translation.

- The main translator owns final prose quality, terminology, character voice, punctuation style, and continuity.
- The only translation engine for prose, content, metadata, and chunk rows is the main translator's own reading and writing in context.
- Work through chunks in numeric order.
- Before starting a chunk, use previous translated prose and `translation-notes.md` for continuity.
- After finishing a chunk, update `translation-notes.md` only for reusable decisions.
- Do not delegate prose, content, metadata, or chunk translation to parallel agents, text-worker subagents, or background workers.
- Context preservation is part of translation quality: character voice, terminology, relationship dynamics, foreshadowing, pacing, punctuation style, and unresolved decisions evolve across chunks and must stay in one lead translator's working context.
- Do not use speed, chunk independence, or later reconciliation as a reason to split content translation across agents.
- Do not use machine translation output as a draft, fallback, benchmark, glossary source, or validation oracle for content translation.
- A subagent must not draft, rewrite, fill, reconcile, or produce translation rows for content chunks.

## Unit and Slot Method

Use `units[]` as the translation thinking unit and `segments[]` as the mechanical write-back unit.

For each chunk:

- Read `units[]` first, in order. Each unit is a translation unit such as a heading, paragraph, list item, table cell, attribute text, or metadata group.
- Use `unit.source` for prose flow and `unit.parts[]` to see slot IDs, inline tags, links, image markers, line breaks, and emphasis boundaries.
- Translate the whole unit as book prose before filling segment rows. Do not translate slots as isolated fragments when the unit forms one sentence, phrase, paragraph, joke, or emotional beat.
- Decide the target sentence that best fits the book's tone first; only then distribute that sentence into segment rows.
- Use `segment_ids` to distribute the natural target unit back into the required slot rows.
- Keep inline semantics attached to the right words: emphasized source slots should receive the emphasized target words, link slots should receive the linked target words, and tail slots should carry surrounding grammar.
- Move words across slots inside the same unit when target-language grammar requires it.
- Use an empty string for a slot only when its meaning has moved into another slot in the same unit. Do not duplicate moved text.
- Preserve punctuation once. Move or replace punctuation according to target-language publishing convention.
- Translate `xhtml_attribute` slots as concise accessibility/UI text, not literary prose.
- Treat `opf_metadata` as book metadata. Use book-level context for title, creator, publisher, description, and subject consistency.

Quality gate before writing each chunk:

- Re-read the target unit text without looking at the source. If it sounds translated, rewrite it.
- Check that dialogue sounds spoken by that character, not by a generic translator.
- Check that narration keeps the scene's pacing and mood.
- Check that punctuation and typography follow target-language publishing conventions.
- Check that moved words remain inside the same unit unless the surrounding chunks make a cross-unit sentence unavoidable.
- Check that slot distribution preserves inline tags, links, image positions, and accessibility text.

## Chunk Schema

Input chunk files contain:

- `schema_version`: `2`
- `chunk_index`
- `units[]`: natural translation units with `id`, `source`, `segment_ids`, and `parts[]`
- `segments[]`: write-back slots

Each unit contains:

- `id`: unit ID.
- `source`: source prose preview with simple markers such as `[img]` or `[br]` where non-text inline structure appears.
- `segment_ids`: slot IDs belonging to the unit.
- `parts[]`: ordered unit parts. `type: "slot"` parts identify translatable slots. `type: "marker"` parts identify non-text EPUB structure that must not be written as translation text.

Use markers only to understand where structure remains in the EPUB. Do not write marker text such as `[img]` or `[br]` into translations unless the source book literally contains that text.

Each segment contains:

- `id`: stable ID to preserve exactly.
- `kind`: `xhtml_text`, `xhtml_tail`, `xhtml_attribute`, or `opf_metadata`.
- `href`: EPUB-relative source document path.
- `path`: XML element path used by the helper.
- `source`: source text for this slot. Ruby pronunciation text from `rt` and `rp` is excluded.
- `unit_id`: unit containing this slot, when applicable.
- `context_before` and `context_after`: nearby slot text for continuity.
- `child_index`: present only for `xhtml_tail`.
- `attribute`: present only for `xhtml_attribute`.

Output translation files must contain:

```json
{
  "schema_version": 2,
  "chunk_index": 1,
  "translations": [
    {"id": "t000001", "translation": "..."}
  ]
}
```

Rules:

- Include one translation row for every input segment in the chunk.
- Preserve every `id` exactly.
- Put only target-language text in `translation`.
- Do not include notes, explanations, alternatives, source text, or markup inside `translation`.
- Preserve leading and trailing whitespace when it appears in `source`.
- Keep names, terms, honorifics, punctuation policy, and style consistent across chunks using user context, previous chunks, and `translation-notes.md`.
- If a segment is punctuation, a divider, or a symbol that should remain unchanged in the target-language edition, still emit the row with that content as `translation`.

## Image Job Contract

`prepare` exports editable raster images under `<run-dir>/images/source/` and creates `<run-dir>/image-jobs.json`.

Image review and image text translation are isolated one-image tasks. Before opening source images for review, verify that the current session can spawn, wait on, and close subagents. Image processing requires a dedicated per-image subagent execution path; do not silently fall back to main-thread image generation.

Image text reading boundary:

- The main agent must directly view each source image needed for triage.
- Do not run OCR, computer-vision text extraction, image-text transcription scripts, CLI tools, libraries, services, or model-assisted bulk extraction against EPUB raster images.
- Do not create contact sheets, visual grids, crops, or intermediate sheets for reading image text.
- Use existing EPUB text chunks, translated prose, `translation-notes.md`, glossaries, and user context only as book context or consistency sources; they are not substitutes for direct image review.
- Put exact source-to-target overrides in an image brief only when the main agent can justify them from direct visual review or non-image book context. Otherwise use a broad source text scope and let the image generation model handle the scoped visible text in the provided image.
- Image subagents do not own book-level translation judgment, image triage, or text extraction. They load exactly one provided source image only as `$image-creator` edit input and execute the supplied brief.

Subagent capability gate:

1. Confirm that agent management tools are callable for spawning, waiting on, and closing subagents.
2. Confirm that an image subagent can receive exactly one local source image and the `$image-creator` skill instructions.
3. Use available subagent execution capacity to avoid waiting on one image while other image-generation capacity is idle.
4. If the gate fails, stop image processing before image review and report the missing capability.

Per-image dispatch contract:

1. Process image jobs from `<run-dir>/image-jobs.json`; do not make a contact sheet or bulk visual sheet for triage.
2. Inspect source images one at a time, only when an edited-image subagent can be dispatched immediately if the image needs editing.
3. Do not inspect ahead to build a backlog of image briefs.
4. If the image has no visible source-edition text that needs translation, record `skipped_no_text` and continue to the next image if dispatch capacity rules allow it.
5. If the image has visible source-edition text, write an image edit brief:
   - target language;
   - the image job ID;
   - the source image path;
   - the required replacement output path;
   - a source text scope;
   - explicit text overrides for clearly read, context-critical strings;
   - a preservation policy for non-source-edition text and all non-text visual content;
   - an edit-oriented prompt for `$image-creator`.
6. Spawn one independent image subagent for that image immediately after its brief is ready.
7. Pass only that source image as the local image input plus the main-authored image edit brief.
8. Keep using available subagent capacity with later image jobs, still one visually reviewed image at a time.
9. Wait on active image subagents only to harvest completed jobs or free capacity.
10. For each completed subagent, record the replacement with `record-image`, then close that subagent immediately.
11. If a subagent fails to save a replacement, close it, keep that image job unresolved, adjust only the execution brief as needed, and dispatch a new subagent for the same image when capacity is available.

Operational rules:

- Do not use OCR, automated image-text extraction, contact sheets, visual grids, or crop sheets.
- Maintain an active job ledger mapping image job ID to source path, replacement path, subagent ID, status, and brief.
- Translate visible communicative text that belongs to the source edition's source language. Preserve non-source-edition text unless the book context makes it part of the source-edition message.
- Use edit-oriented prompt language that treats the provided image as the image to modify.
- Keep generated replacement files as returned by the generation path. Do not normalize, resize, resample, recompress, or convert them before recording.

Main-agent image brief contract:

- Main owns image triage, translation context, and prompt intent.
- Main uses book context, `translation-notes.md`, prior translated prose, and visible image content to decide the edit scope.
- Main provides exact target-language text only for strings that are clear enough and important enough to constrain explicitly.
- Main gives unclear, small, numerous, or low-salience source-edition text to the image generation model through the source text scope.
- The source text scope must be broad enough for complete translation of source-edition communicative text in the provided image.
- Explicit text overrides are constraints for known strings.
- The edit prompt describes a constrained edit to the provided image, scopes visual change to source-edition communicative text regions, and preserves all non-target visual content.
- The edit prompt asks the model to translate scoped visible source-edition text into the target language and render it in the same semantic regions, with placement, scale, angle, and print style adapted to look native in the edited image.

Image subagent execution contract:

- The subagent's only image-job responsibility is generation execution.
- The subagent uses `$image-creator` with the supplied edit brief, source image, and output path.
- The subagent receives and loads exactly one source image for its generation call.
- The subagent must use the received source image as the edit input. Do not generate from a text-only prompt for an EPUB image replacement.
- The supplied edit brief controls translation choices, text coverage, preservation policy, and prompt intent.
- Any `view_image` call in the subagent belongs to `$image-creator`'s single-image local-image bridge immediately before the generation call.

Image subagent return contract:

```json
{
  "image_id": "img0001",
  "status": "edited",
  "source_text_scope": "all visible source-edition communicative text",
  "explicit_term_overrides": [
    {
      "source": "known source string",
      "target": "required target string"
    }
  ],
  "preservation_policy": "visible text outside source-edition communicative content remains unchanged",
  "replacement_path": "/absolute/path/to/replacement-image",
  "final_image_prompt": "the exact English prompt passed to $image-creator"
}
```

Rules:

- `status: "edited"` means `$image-creator` produced and saved a replacement image for the job.
- `explicit_term_overrides` must match the main-authored image edit brief.

If the image generation path fails to return a saved replacement, keep the same one-image job unresolved and retry with an adjusted edit-oriented prompt. The image job is resolved only after `record-image` records `edited` or `skipped_no_text`.

Image recording commands:

```bash
uv run --script <skill-dir>/scripts/epub_translate.py record-image --workdir <run-dir> --image-id <id> --skip-no-text
uv run --script <skill-dir>/scripts/epub_translate.py record-image --workdir <run-dir> --image-id <id> --replacement <edited-image>
```

`record-image --replacement` embeds a finished replacement into the EPUB run by byte-for-byte copy. The helper treats the replacement as an already-finished asset.

Unsupported image media types are reported in `<run-dir>/manifest.json` as `unsupported_images`; handle them only when the user explicitly requests manual handling.

## Completion Criteria

- All chunk translation files exist and `apply-text` succeeds.
- The post-translation target-structure pass is applied, even when the plan is an explicit no-op.
- Text was translated directly by the main translator in chunk order, without text-worker subagents or parallel content translation.
- Source-edition layout that conflicts with the target-language edition is changed through an explicit layout plan.
- Every editable image job is resolved through the per-image contract.
- `package` writes a new EPUB path that is not the source EPUB.
- `validate` succeeds.
- Final response reports the output EPUB, run folder, text segment count, unit count, editable image job summary, unsupported image count, and validation result.
