# user-dialog

Compose popups freely with inputs plus Markdown documents and image or document file paths, then receive the response in the originating Codex conversation.

[All skills](../../README.md#skills) · [한국어](user-dialog.ko.md)

## Installation

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## Runtime requirements

The launcher uses uv to manage its Python dependencies. Markdown and standalone code surfaces additionally require the native WebKitGTK 6.0
runtime; on Debian/Ubuntu, install the `gir1.2-webkit-6.0` package alongside the GTK and libadwaita runtime packages.

Response delivery supports CLI tasks attached to an existing managed shared daemon
and local Desktop tasks. The calling environment selects the backend automatically.
CLI delivery discovers `socketPath` through
`codex app-server daemon version`, verifies the originating thread is loaded, and
joins it for native item notifications. Desktop delivery uses the app-provided
`CODEX_APP_TOOLS_PIPE_PATH` and `codex_app.send_message_to_thread`; native IPC
provides the bound owner's canonical log for input confirmation.
Each client uses its own existing server and binary. The originating conversation
and connection are saved with the draft and verified automatically; no manual
endpoint selection, app launch changes, or new server is needed.
Remote and embedded CLI servers are unsupported.
Run `doctor --delivery` through the skill launcher to check native connection
discovery and receipt prerequisites without delivering a response.

Both launchers return when the popup is ready. Popups run independently of the
calling tool and stay open after the source turn completes or the focused
conversation changes. Active CLI delivery uses `turn/steer` with `expectedTurnId`;
idle delivery uses `turn/start`. The Desktop bridge makes the equivalent choice
inside the app. CLI records an ordinary user message; Desktop records a delegated
tool output that the app displays as a user-style message from another task.

Submission saves the exact answer and freezes input. Automatic closing requires
the actual native input item: CLI matches its saved response UUID and text in
`item/completed`, while Desktop matches a new delegated tool-output item in the
original conversation's canonical log. An acknowledgement or model completion
does not close the popup. Different conversations can receive responses concurrently.
Desktop serializes this skill's submissions to the same conversation through
canonical confirmation. Durable coordination in the shared Codex home covers
popups launched from different projects and survives a sender process ending.

Post-send errors and lost acknowledgements never trigger another send. Recovery
checks the saved native records; `resume <run-dir>` can reopen an unconfirmed
submitted popup with its answer locked and continue confirmation. Desktop's
public bridge does not preserve the response UUID in the native item, so it uses
the saved pre-send boundary, source conversation, exact body, and native item ID.
This distinguishes this skill's coordinated submissions; an independent sender
using the same source and body can leave confirmation ambiguous.

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
