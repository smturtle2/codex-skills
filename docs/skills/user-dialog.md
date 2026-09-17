# user-dialog

Compose popups freely with inputs plus Markdown documents and image or document file paths, then receive the response in the originating Codex task.

[All skills](../../README.md#skills) · [한국어](user-dialog.ko.md)

## Installation

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## Runtime requirements

The launcher uses uv to manage its Python dependencies. Markdown and standalone code surfaces additionally require the native WebKitGTK 6.0
runtime; on Debian/Ubuntu, install the `gir1.2-webkit-6.0` package alongside the GTK and libadwaita runtime packages.

## Use

Ask naturally, for example: “Use $user-dialog to ask me which deployment target to choose, with buttons for staging and production.”

For authored content, use a `markdown` node with literal `text` or a `ref` to an input/choice value. Markdown files use the same renderer through `file`; both accept independent `display` options for title, border, source-copy, and code-copy controls.

Popup text and controls use bundled Pretendard, and code uses D2Coding. Standalone code and Markdown code blocks share syntax colors, spacing, and a header with the language on the left and wrap/copy controls on the right. Wrapping is on by default; turning it off uses horizontal scrolling, and copying preserves the exact source text. Markdown files retain their filename and document frame by default. Fonts load locally without changing the system theme or installing system fonts.

## Working files

When a dialog run needs persisted state, use the project-root-relative `.codex-skills/user-dialog/<run-id>/` workspace unless the user explicitly gives a location. Resume older existing locations in place, retain state needed for recovery, and remove only expendable intermediates created by this run.

Literal `ref` values update in place. Live replacements wait while document text is selected or dragged, automatic resizing waits during selection, and draft updates are coalesced for 300 ms before submit or close flushes them.

For the skill instructions, see [SKILL.md](../../skills/user-dialog/SKILL.md) and the [view contract](../../skills/user-dialog/references/view-contract.md).
