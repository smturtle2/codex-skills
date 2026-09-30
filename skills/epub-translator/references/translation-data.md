# Translation Data

Read before authoring edition settings or translation JSON. Paths are relative to the persistent run folder.

## Extracted Inputs

`ingest` requires an empty workdir. It creates `unpacked/`, `flow/book.flow.json`, `chunks/`, `translations/`, `edition.json`, `manifest.json`, `resources.json`, `image-jobs.json`, and `translation-notes.md`. Image sources and their jobs are separate from text chunks.

New runs use flow schema **3** and chunk/translation schema **4**. The helper owns the flow, source chunks, marker descriptors, and resource ledger. Prose units retain whole paragraphs, headings, list items, or table cells with protected inline content; chunk packing follows reading order and keeps units intact. Peripheral text is isolated. Do not edit extracted inputs or repack units to fit a translation preference. New runs detect changes to the unpacked source; restore it or explicitly start a separate run.

## Edition Settings

Use only these keys:

```json
{
  "schema_version": 2,
  "target_language": "ko",
  "language_tag": "ko",
  "page_progression_direction": "ltr",
  "text_direction": "ltr"
}
```

Both language fields require explicit nonempty language tags such as `ko` or `en-GB`. `page_progression_direction` sets spine progression; `text_direction` sets target text direction. Each is `ltr` or `rtl`. Set all four values from the target edition; ingest's unset language fields do not make a build ready. The Korean example is not a language default. Do not add prose, translation choices, glossary entries, or image briefs.

An existing edition-v1 file remains readable without rewriting it; when it lacks `text_direction`, the helper uses its explicit page progression. Use version 2 for new settings.

## Chunks

Input `chunks/chunk-*.json`:

```json
{
  "schema_version": 4,
  "chunk_index": 1,
  "kind": "prose",
  "items": [
    {
      "id": "u000001",
      "source": "彼女は⟦m000001⟧静かに⟦/m000001⟧言った。⟦m000002/⟧次の一言。",
      "block_id": "b000004",
      "block_type": "paragraph",
      "href": "xhtml/chapter.xhtml",
      "markers": {
        "m000001": {"kind": "inline", "tag": "em", "attrs": {}, "attr_slots": []},
        "m000002": {"kind": "br"}
      }
    }
  ]
}
```

- Copy actual IDs and indices from each input; examples do not establish naming or numbering.
- `kind` is `prose` or `peripheral`. Peripheral items include OPF metadata and retained image/element attributes.
- Translate each whole item without splitting its ID. Ruby readings are removed while base text remains.
- `markers` is present only when needed. Its descriptors belong to the helper; translate only `source` into the response string.
- Retained `alt`, `title`, and `aria-label` slots appear as peripheral items. Layout classes and styles on flattened wrappers are removed; retained anchors and supported attribute slots remain attached to their owning content.

Output `translations/chunk-*.json`:

```json
{
  "schema_version": 4,
  "chunk_index": 1,
  "translations": [
    {"id": "u000001", "translation": "그녀는 ⟦m000001⟧조용히⟦/m000001⟧ 말했다.⟦m000002/⟧다음 한마디."}
  ]
}
```

Save under the same filename as the input, for example `translations/chunk-0001.json`. Copy its schema and chunk index exactly. Provide exactly one nonempty row per input ID, with target prose and required markers; omit notes, alternatives, and added HTML/Markdown. Preserve completed rows when resuming a partial chunk. Unknown, duplicate, misplaced, empty, or malformed rows block completion.

## Protected Markers

| Syntax | Meaning | Translation requirement |
| --- | --- | --- |
| `⟦m000001⟧…⟦/m000001⟧` | Paired inline element, such as emphasis or a link | Keep both tokens once, with matching, properly nested pairs around the corresponding target text. |
| `⟦m000002/⟧` | Atomic image, line break, anchor, opaque media, or literal delimiter | Keep the token once at its semantic position. |

Use the actual keys and descriptors from the item. Preserve every marker; do not rename, duplicate, omit, translate, or change paired/atomic forms. Markers can move with the corresponding content to fit target syntax while conserving valid nesting. The helper restores element attributes, link destinations, and image references.

Literal source `⟦` and `⟧` characters are represented by helper-owned atomic `literal` markers. Preserve those tokens too; do not expand them into raw delimiters or invent an escape scheme. Raw delimiters outside recognized markers fail validation. An item without markers still requires ordinary nonempty translated prose.

## Resume and Legacy Recovery

```bash
uv run --script "$SKILL_DIR/scripts/epub_translate.py" status --workdir <run-dir>
```

Use the original run directory. Never ingest over it or convert old files merely to match the new examples. Flow-v2/chunk-v3 runs keep their existing fragment IDs and schema-v3 translation rows. The helper reconstructs retained content from the unpacked source and verifies each old slot's exact DOM ownership, including repeated text and attributes. Ambiguous or changed ownership blocks the run rather than assigning an old translation to another occurrence.

When `legacy_recovery_required` is true, explicitly record the omitted source items:

```bash
uv run --script "$SKILL_DIR/scripts/epub_translate.py" recover --workdir <run-dir>
uv run --script "$SKILL_DIR/scripts/epub_translate.py" status --workdir <run-dir>
```

`recover` adds schema-v3 recovery chunks and `legacy-recovery.json` while preserving old chunks and translation rows. It is idempotent, resumes an interrupted recovery, and refuses to overwrite a mismatching existing chunk. Translate the added items using their actual schema, IDs, and indices. Recovery adds source material, never translations. A source-ownership error requires source review/restoration or an explicitly separate new run.

## Continuity and Reports

`status` reports progress, `next_chunk`, and the contiguous completed `seam_tail`. Use the seam with the rolling summary and glossary in `translation-notes.md`; also read the current source.

- `valid`: source chunks and existing translation rows pass state checks. Missing rows may still remain.
- `text_complete`: the text state is valid, all expected rows exist, and explicit legacy recovery is complete.
- `build_ready`: text, edition settings, source resources, and resolved image jobs pass build prerequisites.
- `errors` and `build_blockers`: reasons the corresponding state is invalid or not ready.

`ok` and a successful status exit code do not mean the book is complete. An unset edition or pending image job can leave text valid while `build_ready` is false.

## Publication and Validation

`build` rejects incomplete or invalid state, unresolved editable image jobs, changed recorded payloads, and broken internal package references. Review `build-report.json` for source-equal translations and differing translations of the same source; these are language-review candidates, not automatic proof of an error.

The helper rebuilds horizontal target XHTML/CSS and navigation, retains source spine order and auxiliary `linear` status, and preserves resource locations relative to the package. Internal archive paths are normalized from the archive root; emitted manifest and document URIs are percent-quoted, including literal spaces, `%`, `#`, and `?`. Do not manually change URI encoding or rename source resources. Replacement MIME comes from decoded image bytes, so a PNG payload can retain the source `.jpg` archive path.

Before replacing the output, the helper opens the completed temporary ZIP and checks its container/OPF, manifest, navigation, spine, XML references/fragments, image MIME, and selected resource hashes. A rejected build leaves the previous output intact. Publication uses atomic replacement at a path distinct from the source EPUB.

`validate --workdir <run-dir> --output <translated.epub>` independently checks the final ZIP, current validated inputs and selected resources, and the successful artifact hash in `build-report.json`. After changing translations, edition settings, or image selections, rebuild before validating. These checks cover the helper's package graph and payload contract; they do not establish prose quality, translate preserved opaque media, or replace a reading-system review.
