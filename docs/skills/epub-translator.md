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

## Output

A translated `.epub`, working translation files, and a validation summary. Reading order, links, and image placement guide the rebuild.

[Read the agent instructions](../../skills/epub-translator/SKILL.md)
