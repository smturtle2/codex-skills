# epub-translator

Translate an EPUB into a new edition with consistent terminology and continuity across chapters.

[All skills](../../README.md#skills) · [한국어](epub-translator.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/epub-translator from https://github.com/smturtle2/codex-skills.
```

Also install `image-creator` when text inside raster images needs translation.

## Example

```text
Use $epub-translator to translate book.epub into Korean, preserving names consistently throughout the book.
```

## Working files

Keep persistent translation state in the project-root-relative `.codex-skills/epub-translator/<run-id>/` workspace when no location is requested. An explicit work location wins, and an existing older location should be resumed in place. Retain resumable data, clean up only expendable intermediates from this run, and write the final EPUB to the requested destination.

`ingest` refuses a nonempty workspace. Resume through `status`; its `valid`, `text_complete`, and `build_ready` fields distinguish usable saved rows, finished text, and readiness to publish. `errors` and `build_blockers` identify work still needed. A successful status command alone does not mean completion.

## Translation and resume

New runs use flow schema 3 and chunk/translation schema 4. Prose items retain whole paragraphs or reading units; protected paired and atomic markers carry emphasis, links, images, and other retained content. The agent translates surrounding text while preserving marker syntax and nesting. Edition schema 2 explicitly records `target_language`, `language_tag`, `page_progression_direction`, and `text_direction`.

Older flow-v2/chunk-v3 runs preserve existing IDs and completed rows. The helper verifies their ownership against the original document positions. When source material was omitted, explicit `recover` adds the missing source items without replacing old translations; repeated recovery is safe. Translate the added items before building.

[Data formats and recovery](../../skills/epub-translator/references/translation-data.md) · [Image jobs](../../skills/epub-translator/references/image-jobs.md)

## Output

A translated `.epub`, resumable working files, and `build-report.json`. The rebuild produces horizontal target text and new navigation, preserves reading order and auxiliary spine entries, and uses normalized archive paths with quoted resource URIs. Edited raster images retain their returned bytes and actual MIME; their archive suffix may remain the source suffix.

SVG, math, audio/video, and other media outside the raster-image editing workflow are preserved and reported; their internal text is not translated by the helper. The helper verifies the completed ZIP's package graph and selected payloads before atomically replacing the output. `validate` checks both the final artifact and the current run state; rebuild after changing translations, edition settings, or images. Mechanical validation does not establish translation quality.

[Read the agent instructions](../../skills/epub-translator/SKILL.md)
