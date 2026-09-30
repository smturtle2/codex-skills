# user-dialog

Compose popups freely with inputs plus Markdown documents and image or document file paths, then receive the response as a user message in the originating Codex task.

[All skills](../../README.md#skills) · [한국어](user-dialog.ko.md)

## Installation

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## Runtime requirements

The launcher uses uv to manage its Python dependencies. Markdown and standalone code surfaces additionally require the native WebKitGTK 6.0
runtime; on Debian/Ubuntu, install the `gir1.2-webkit-6.0` package alongside the GTK and libadwaita runtime packages.

Response delivery supports CLI tasks attached to an existing managed shared daemon
and local desktop tasks. CLI delivery discovers `socketPath` through
`codex app-server daemon version`, verifies the originating thread is loaded, and
joins it for native item notifications. Desktop delivery uses
`$CODEX_HOME/ipc/ipc.sock` to discover the exact owner and its canonical log path.
`CODEX_HOME` defaults to `~/.codex`. The connection is saved with the draft and
verified automatically; no manual endpoint selection, app launch changes, or
new server is needed. Remote and embedded CLI servers are unsupported.
Run `doctor --delivery` through the skill launcher to check native connection
discovery and receipt prerequisites without delivering a response.

State and response formatting are shared; each client owns its native connection,
delivery, receipt checks, and recovery. CLI popups remain detached and use Core's
`turn/start`. Desktop keeps the originating turn active while the popup accepts
input and uses only the owner's native steering path. The agent waits the same
running exec session or cell in bounded intervals and does not finalize while
the popup is writable. A detached renderer alone does not keep the turn active.
Cancellation closes the writable popup and retains its draft or saved answer;
there is no Desktop start fallback.

After submission, Desktop freezes the popup and releases the launcher on admission
acknowledgement or an uncertain attempted-write outcome, before canonical
confirmation. The renderer then confirms independently. Automatic closing requires
the saved UUID and exact text in CLI `item/completed` or a completed `UserMessage`
in the Desktop owner's log. Post-send errors and lost acknowledgements never
trigger another send; recovery checks the client's saved native records.
A writable Desktop popup cannot outlive its originating turn's normal completion.
A legacy log without native user-message UUIDs cannot confirm uncertain delivery.

Response titles, field labels, and the submitted button receive the CLI theme's accent color
automatically. Use the existing popup JSON; no emphasis ranges or extra styling options are needed.
Answers retain their exact text, including any Markdown the user typed. Other clients may show
plain text. New submissions save a text preview in `message.txt` and the complete message in `state.json`.

## Use

Ask naturally, for example: “Use $user-dialog to ask me which deployment target to choose, with buttons for staging and production.”

For authored content, use a `markdown` node with literal `text` or a `ref` to an input/choice value. Markdown files use the same renderer through `file`; both accept independent `display` options for title, border, source-copy, and code-copy controls.

Popup text and controls use bundled Pretendard, and code uses D2Coding. Standalone code and Markdown code blocks share syntax colors, spacing, and a header with the language on the left and wrap/copy controls on the right. Wrapping is on by default; turning it off uses horizontal scrolling, and copying preserves the exact source text. Markdown files retain their filename and document frame by default. Fonts load locally without changing the system theme or installing system fonts.

## Working files

When a dialog run needs persisted state, use the project-root-relative `.codex-skills/user-dialog/<run-id>/` workspace unless the user explicitly gives a location. Resume older existing locations in place, retain state needed for recovery, and remove only expendable intermediates created by this run.

Literal `ref` values update in place. Live replacements wait while document text is selected or dragged, automatic resizing waits during selection, and draft updates are coalesced for 300 ms before submit or close flushes them.

Number/date drafts retain incomplete and invalid edits across resume and compatible updates. Submission saves the draft, converts and validates active fields, then records the response before delivery. Invalid numbers, including nonfinite values, show a field error; text answers retain their exact content. Submitted numbers and dates use normalized values, and integer precision is preserved.
Put conditional controllers outside the content they control. Conditions cannot depend on their own fields or descendants, and field-dependency cycles are rejected so an invalid required controller remains editable and cannot be silently omitted.

Tabs/pages honor the requested `none`, `crossfade`, `slide`, or `fade-through` effect and duration. One presentation controller waits for documents and settled layout, runs the chosen effect, and restores focus. Zero duration disables animation while retaining readiness checks.

For the skill instructions, see [SKILL.md](../../skills/user-dialog/SKILL.md) and the [view contract](../../skills/user-dialog/references/view-contract.md).
