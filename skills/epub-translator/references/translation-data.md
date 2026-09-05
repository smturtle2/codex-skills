# Translation Data

Read before authoring edition settings or translation JSON. Paths are relative to the persistent run folder.

## Extracted Inputs

`ingest` creates `unpacked/`, `flow/book.flow.json`, `chunks/`, `translations/`, `edition.json`, and `manifest.json`. Image sources and their jobs are separate from text chunks.

The helper owns the flow IR and chunk packing. Blocks remain atomic, chunks follow source order with scene/heading-aware boundaries, and peripheral text is isolated. Do not edit packing to fit a translation preference.

## Edition Settings

Use only these keys:

```json
{
  "schema_version": 1,
  "target_language": "ko",
  "language_tag": "ko",
  "page_progression_direction": "ltr"
}
```

Both language fields are BCP-47 tags; direction is `ltr` or `rtl`. Choose values from the target edition. The Korean example is not a language default. Do not add prose, translation choices, glossary entries, or image briefs to this file.

## Chunks

Input `chunks/chunk-*.json`:

```json
{
  "schema_version": 3,
  "chunk_index": 0,
  "kind": "prose",
  "items": [
    {"id": "example-id", "source": "Source text", "block_id": "example-block", "block_type": "p", "href": "chapter.xhtml"}
  ]
}
```

- Copy actual IDs and indices from each input; examples do not establish naming or numbering.
- `kind` is `prose` or `peripheral`. Peripheral items include OPF metadata and retained image/element attributes.
- An item may span a complete sentence or reading unit flattened from ruby markup. Translate the whole item without splitting its ID.
- Optional `inline` metadata identifies emphasis or links. Preserve their semantic placement through the corresponding item; do not translate metadata or invent links.
- Attributes on flattened transparent wrappers have no target node and are not carried into the new edition.

Output `translations/chunk-*.json`:

```json
{
  "schema_version": 3,
  "chunk_index": 0,
  "translations": [{"id": "example-id", "translation": "Target text"}]
}
```

Provide exactly one row per input ID, with pure target-language text and no notes, alternatives, or markup. Preserve existing completed rows when resuming a partial chunk.

## Continuity and Reports

`status --workdir <run-dir>` reports progress, `next_chunk`, and `seam_tail`. Use the seam with the rolling summary and glossary in `translation-notes.md`; it does not replace reading the current source.

`build` rejects missing translations, invalid edition settings, pending editable image jobs, or broken internal links. Its report flags source-equal translations and differing translations of the same source for human-language review. Fix the affected rows or settings and rebuild; do not re-extract a valid run.
