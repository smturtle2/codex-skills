# View contract

## Request

Pass a JSON object as a file or stdin (`-`). Run from the project root and keep request files in the dialog's workspace, normally `.codex-skills/user-dialog/<run-id>/`. Asset paths are absolute or relative to the project working directory, not the request file's folder.

| Key | Contract |
| --- | --- |
| `version` | `1` (default). |
| `title`, `subtitle` | Required nonempty title; optional subtitle. |
| `body` | One node, usually a layout containing other nodes. |
| `actions` | Footer buttons; default is Send/submit. |
| `width` | Preferred width, 300..2000; default 600. |
| `message` | Optional `title` override and `icon` (default `💬`). |

## Elements

Node `type` selects the element. IDs must be unique across the request. Labels are literal user-facing UI strings.
Layouts accept any nodes in `children`, including nested layouts; other elements do not accept `children`.

| Type | Properties |
| --- | --- |
| `column`, `row`, `group` | `children`, optional `label`; group renders a card. |
| `grid` | `children`, `columns` 1..12 (default 2). |
| `tabs`, `pages` | `children`, each with `id` and `label`; pages requires its own `id`, with optional `back_label`, `next_label`. Give tabs an `id` when targeting navigation. The visible child determines the stack's natural height. |
| `markdown` | `text` or `ref` (an input/choice current value shown literally); optional `label` and `display`. Renders the full Markdown body. |
| `code` | Required string `text`; optional string `language` and `label`. Renders a standalone code surface and copies the exact text. |
| `file` | Existing file `path`, optional `label` and `display`; previews images and text/Markdown, with an external-open link. Other formats provide a link. Markdown files render the same Markdown body. |
| `input` | Required `id`, `label`; `format`: `text` (default), `number`, `date`, `file`, `boolean`. |
| `choice` | Required `id`, `label`, `options`; selection and content rules below. |
| `button` | Required `label`, `action`. |
| `separator` | `orientation`: `horizontal` (default) or `vertical`. |
| `table` | Nonempty string list `columns`; optional `rows` of string lists matching column count. |

Inputs support `value`, `required`, `response_label` (record label override), and `error`.
Tabs/pages accept `transition: {"type": "none" | "crossfade" | "slide" | "fade-through", "duration": 120}`;
duration is 0..1000 ms. The default is fade-through at 320 ms; explicit transition types are allowed, and an explicit fade-through without a duration is also 320 ms.
Fade-through fades out before switching content, then fades in; the two pages never overlap.
Crossfade blends the previous and next settled views; slide moves between them in the navigation direction.
`none`, a zero duration, or disabled system animations changes content without animation, after document readiness and layout settlement.
Text inputs support `multiline` and `placeholder`; number inputs accept `min`/`max`; dates use `YYYY-MM-DD`.
File inputs accept `browse_label`/`clear_label`. Boolean inputs render a switch, default to `false`,
and accept `true_label`/`false_label` for recorded values (defaults `On`/`Off`); they cannot be multiline.

Editable number/date drafts preserve the entered text, including incomplete or invalid values, across checkpoints, close/resume, and compatible live updates.
One conversion model handles authored defaults, actions, conditions, validation, and submitted answers. Numbers must be finite and within their bounds;
integer inputs retain their precision, and dates must be valid `YYYY-MM-DD` values. Invalid values show a field error at submission instead of closing the window.
Text answers, including whitespace and Markdown, stay verbatim; submitted numbers and dates use their normalized values. No typed-value cache is persisted beside the draft.

Choices support `value`, `required`, `response_label`, `error`, and `multiple` (default false).
Each option has a unique nonempty string `value`, a `label`, and optional `content` containing any nodes.
`presentation` is `list` (default) or `dropdown` (single selection only).
Lists show every option's content; dropdowns show the selected option's content below the control.
Only selected options contribute nested input values to the response.
List `layout` is `{"type":"column"}` (default), `{"type":"row"}`, or `{"type":"grid","columns":2}` (1..12 columns).

Markdown bodies use CommonMark through markdown-it-py with tables, strikethrough, task lists, and footnotes. A `markdown`
node accepts either literal `text` or `ref`; a ref displays the current input/choice value literally. Relative image paths
resolve from the project base.

Standalone `code` nodes preserve and copy their exact `text`, with an optional `language` hint.
They share the Markdown code renderer, including syntax highlighting, spacing, and the language/wrap/copy header. Wrapping is on by default for every code block; turning it off uses horizontal scrolling, and copy preserves the exact source text. They use a gray,
code-toned background and share the bundled D2Coding font with fenced code in documents. Document surfaces use a
separate white/light-theme surface (or the theme-appropriate dark surface); fenced code inside documents remains
visually distinct from surrounding document text. Theme changes update both code presentations.

Markdown bodies render in the popup's main scroll area; there is no separate inner document scroller. They support relative
assets, image dimensions and alignment, anchors, Pygments code highlighting, and GitHub Markdown CSS styling. Dollar-
delimited math is rendered with the bundled KaTeX assets when present. Mermaid fenced diagrams are rendered when present.
The document renderer uses WebKitGTK 6.0. Markdown parsing scopes remain separate when adjacent bodies share one surface.

`display` is an object of booleans and independently controls `title`, `border`, `copy_source`, and `copy_code`. All four default to `false` for
`markdown`, producing a bare full Markdown body. For `.md` and `.markdown` `file` nodes, all four default to `true` to
preserve the convenient filename/source-copy document view. Explicit properties override these defaults independently.
`label` only supplies the title text; it does not make the title visible. Titles use one line with ellipsis when needed,
with a tooltip exposing the full title/path. When shown, the title is `label` for authored Markdown and the `label` or
filename for Markdown files. Source-copy copies the exact original Markdown, and code-block controls copy the exact code source without
fences; each clicked copy control briefly shows a check icon in place of a toast.
Markdown file image paths resolve from the Markdown file's directory. File path convenience is unchanged, including image
preview and external-open links for other file types.
Adjacent unkeyed static bare Markdown bodies in a `column` or `group` coalesce into one continuous selectable surface,
without merging their Markdown parsing scopes. Bodies with IDs, bindings, conditions, or display chrome retain their own
surface, as do separate controls and layouts.
All content remains selectable while a response is sending.

Popup controls and Markdown prose use bundled Pretendard; standalone and Markdown code use D2Coding.
Fonts load locally for the popup without system installation. Theme colors remain independent of typography.

## Conditions and actions

Nodes and footer buttons accept `visible_when` and `enabled_when`. A condition uses `ref` to an input/choice,
optionally with one of `equals`, `contains`, or `empty`. Combine conditions with `all`/`any` lists or `not`.
A bare `ref` checks truthiness. Example: `{"ref":"details_enabled","equals":true}`.
Conditions use normalized values. An invalid referenced field remains unresolved through `not`, `all`, and `any`; negation cannot turn an invalid number or date into an enabled condition.
`set` references use the same converted source value; an invalid source leaves the target unchanged and shows its error.
Keep visibility/enabled controllers outside the field or container they control. A condition cannot reference its own field or a descendant field,
including fields inside choice-option content. Nested `all`/`any`/`not` follow this rule, and indirect field-dependency cycles are rejected.
Selected option content also depends on its choice controller. These checks keep a required invalid controller editable and subject to validation.
Resume checks the same dependency policy on older unsubmitted requests, preserving their saved draft if correction is needed; submitted-message recovery is unchanged.

Footer buttons require `label` and `action`; `primary: true` selects the keyboard default.

| Action `type` | Properties and effect |
| --- | --- |
| `submit` | Records the button and active answers. `include_values: false` sends only the button and skips field validation. |
| `dismiss`, `defer` | Close without delivering a response; preserve the draft. |
| `set` | Input/choice `target` and `value`, either literal or `{"ref":"another_input"}`. |
| `toggle` | Multiple-choice `target` and option `value` to toggle. |
| `navigate` | Tabs/pages `target`; `page` is a child ID, `next`, or `previous`. |

## Live updates

`update <run-dir> <request.json|-> [--revision N] [--timeout SECONDS]` applies JSON compiled against the original `show` base. It owns the exact originating thread, request ID, and revision; stable element IDs reuse unchanged widgets, compatible changed fields preserve values, and a focused or selected replaced subtree waits until focus leaves or selection clears. Literal `ref` display values update in place; live replacements wait while document text is selected or dragged. Removing or changing the type of an answered field, or removing a chosen option, is rejected. Assets at the same paths are reread for an update; they are not watched automatically. Updates are accepted while the dialog is open and stop at submission. A timeout returns `queued`; do not resubmit it. `status` reports `revision` and `update`, and each command writes `updates/<command_id>.result.json`. `applied` is acknowledged after paint; closing the window before confirmation reports `interrupted`.

## Response

The runtime produces a `[💬 Popup response · TITLE]` header, labeled answers, and a `→ BUTTON_LABEL` final line.
CLI responses mark the header, field labels, and button line with `text_elements` UTF-8 byte ranges
for the theme's accent color. Desktop responses wrap those segments in Markdown `**` bold,
escaping their literal punctuation and preserving surrounding whitespace as entities outside the delimiters
so label padding cannot become an indented code block.
Request authors do not specify ranges or add formatting options. Answer text, including any
Markdown typed by the user, remains verbatim. Preview responses retain the CLI text format.
CLI records one ordinary user message; Desktop records a delegated tool output
that the app displays as a user-style message in the originating conversation.
The source text is fixed English; titles, field labels, and button text come from the popup, with optional `message.title` and `response_label` overrides. Typed text and line breaks remain verbatim.
Choices use option labels; attachments show the filename and absolute path on separate lines;
empty/inactive fields and display-only content are omitted.
Submission first saves the editable draft, converts it, validates active fields, formats the response, and persists the submitted record before delivery.
`state.json` keeps the editable draft, typed active answers, and complete text input object; `message.txt` holds the exact outgoing text, including Desktop Markdown.
Button-only submission still saves the draft while skipping field validation and answers. Legacy numeric drafts reopen as editable text; already submitted messages remain unchanged during recovery.
Any allowed retry reuses the saved submission. Receipt matching belongs to the
selected adapter, as described below; presentation differences do not permit
another submission.

## Example

```json
{
  "title": "Document settings",
  "body": {"type": "column", "children": [
    {"type": "choice", "id": "format", "label": "Output format", "presentation": "dropdown",
     "options": [
       {"value": "pdf", "label": "PDF", "content": [{"type": "markdown", "text": "Ready to share"}]},
       {"value": "md", "label": "Markdown", "content": [{"type": "markdown", "text": "Editable source"}]}
     ]},
    {"type": "input", "id": "notes", "label": "Additional details", "multiline": true}
  ]},
  "actions": [{"label": "Send", "primary": true, "action": {"type": "submit"}}]
}
```

## Runtime

Commands use `uv run --script "$SKILL_DIR/scripts/user_dialog.py" …`.
The launcher needs Python 3.11+; uv supplies the Python dependencies. The native renderer needs PyGObject,
GTK 4.16+, and libadwaita 1.6+. Markdown bodies and standalone code additionally need WebKitGTK 6.0. On Debian/Ubuntu these are
`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, and `gir1.2-webkit-6.0`; uv does not install native libraries.
Document styles and math/diagram engines are bundled locally, with versions and licenses under `assets/document/vendor`.
Hidden document tabs load on first display; ordinary documents do not load the math or diagram engines.
Delivery supports CLI tasks attached to an existing managed shared daemon and
local Desktop tasks. The calling environment selects the backend automatically.
The runtime saves an immutable origin `(backend, codex_home, host_id, thread_id)`,
a popup ID, and a separate response UUID before sending. Later commands verify
the original binding; the focused conversation never chooses the destination.

- CLI: `codex app-server daemon version` supplies the running daemon's `socketPath`.
  The runtime connects to that existing Unix WebSocket, initializes its own client,
  and verifies the exact thread is loaded there. Before submission it joins that
  loaded thread with `thread/resume {threadId, excludeTurns: true}` to receive
  native item notifications. This joins the existing session without input or
  configuration overrides; it does not resume an unavailable task elsewhere.
- Desktop: the app-provided `CODEX_APP_TOOLS_PIPE_PATH` supplies the existing tools
  bridge. Submission calls `codex_app.send_message_to_thread` for the saved thread
  and host; the app coordinates its active steering or idle start path. The runtime
  separately uses native IPC at `$CODEX_HOME/ipc/ipc.sock` to obtain the exact
  original owner's canonical `rolloutPath`. `CODEX_HOME` defaults to `~/.codex`.
  Desktop writes a delegated `function_call_output`, which the app displays as a
  user-style message with the "Sent by … from another task" source label.

CLI writes an ordinary user message. Before input, it reads the active turn and
uses `turn/steer {threadId, expectedTurnId, clientUserMessageId, input}` while
active, or `turn/start {threadId, clientUserMessageId, input}` while idle.
Only a definitive active-turn mismatch or no-active-turn rejection permits
re-reading the turn and choosing again. A timeout or disconnect after a possible
write never selects another send path.

State and response formatting are shared; connection discovery, submission,
native receipt checks, and recovery belong to each client's adapter. Each client
uses its own existing server and binary. No manual endpoint, app launch change,
or new server is needed. Remote, embedded CLI, and Windows delivery are unsupported.

Both `show` and `resume` return when the popup is ready. The detached renderer
survives normal completion or interruption of the source turn and changing the
focused conversation. If startup yields a running exec session or cell, wait on
that same ID in intervals of at most 60 seconds until readiness. The agent can
then continue work or finalize; the user can submit while the task is active or idle.

Submission persists the exact answer before writing and freezes input. Actual
input admission is separate from the bridge or server acknowledgement. The
renderer closes automatically only after it has confirmed the native input item;
it does not wait for the model's final response.

- CLI matches native `item/completed` with `item.type: userMessage`, the saved
  `clientId`, and exact text. It also accepts a matching item that arrives before
  the RPC acknowledgement. Recovery uses records bound to the same conversation.
- Desktop saves a pre-send boundary in the exact owner-provided canonical log,
  then matches one new `function_call_output` with namespace `codex_app`, name
  `send_message_to_thread`, the original source thread, and exact decoded body.
  It stores the real item and turn IDs. Pending UI placeholders do not confirm
  delivery. If a replaced or truncated log cannot recover the saved boundary,
  confirmation remains uncertain rather than matching an old identical message.

The shared journal is `$CODEX_HOME/user-dialog/delivery.sqlite3`. Submitted
content and Desktop per-origin outstanding ownership are committed atomically;
the run's `state.json` mirrors them for inspection. One Desktop submission per
origin remains outstanding through canonical confirmation. Other popups for that
origin preserve their answers and wait; different conversations send concurrently.
This coordination spans projects and survives a sender process ending. An
unconfirmed earlier submission is resolved before a later one is sent.

The public Desktop bridge does not preserve the response UUID in its native item.
The saved boundary, source, exact body, and per-origin serialization distinguish
this skill's submissions. An independent sender using the same source and body
can still make confirmation ambiguous. CLI's UUID correlates a response; it does
not make repeated sends idempotent.

Delivery keeps a separate `phase`: `prepared`, `write_started`, `awaiting_receipt`,
`uncertain`, `admitted`, `waiting_origin`, or `rejected`. Once a write may have
happened, recovery is confirmation-only. Lost acknowledgements and verification
timeouts do not replay input. Confirmation continues in bounded cycles with
backoff; a confirmed `admitted` result cannot be reversed by a later RPC error.
Only a pre-write failure or explicit rejection that proves no input was admitted
allows an explicit retry. Recovery never invents a new origin.

| Command | Purpose |
| --- | --- |
| `elements` / `--help` | List element types / CLI options. |
| `validate <request.json\|->` | Check a request without opening a window. |
| `show <request.json\|-> --preview` | Open without delivery; submission saves `message.txt` and the styled input in state. |
| `show <request.json\|-> --preview --render-image <file.png>` | Export the renderer's own visible widget tree and close, without delivery. Useful for inspecting layout. |
| `show <request.json\|-> --run-dir <path>` | Choose the workspace. Default: `.codex-skills/user-dialog/<run-id>/`. Both clients return after popup readiness. |
| `doctor --delivery` | Check native libraries, native connection discovery, and receipt prerequisites without delivering a response. |
| `status <run-dir>` / `resume <run-dir>` | Inspect status / reopen a draft or an unconfirmed submitted popup. Submitted input stays locked while confirmation resumes; confirmed and preview submissions stay closed. |
| `update <run-dir> <request.json\|->` | Queue one live update; optional `--revision N` checks the current revision and `--timeout` defaults to 10 seconds. |
| `deliver <run-dir>` | Attempt delivery from the original task only before a possible write or after a definitive non-admission failure. |
| `confirm <run-dir>` | Recheck the saved native input records without sending another response. |

`show`, `resume`, and `doctor` accept `--python <path>`; `USER_DIALOG_PYTHON` also selects the renderer interpreter.
Keep the run and referenced assets available. On failure, inspect status and `renderer.log`.
Submission and delivery are separate: a saved answer may have unconfirmed delivery.
The runtime prevents replay after any possible write; do not resend unconfirmed answers manually.
Automatic closing waits for the adapter's matching native input receipt.
Identical answers in different conversations are checked only in their original
conversation. CLI distinguishes responses by UUID; Desktop distinguishes this
skill's same-conversation responses with its saved boundary and durable serialization.
An interrupted write is also confirmation-only.
While sending, the clicked submit button shows a fixed-size sending indicator, and document selection/copy remains available.
Automatic focus prefers inputs, then an action button; it does not select display text. Manual text selection remains available.
Automatic focus skips offscreen inputs so opening a long popup preserves its start. Content-height changes reschedule window sizing after text layout validation, but automatic resizing waits during document selection. Draft updates are coalesced for 300 ms and flushed before submit or close.
One presentation controller owns page and live-update transitions. It waits for mapped documents and settled layout, applies the chosen effect once, then restores retained focus or focuses the new page's controls.
Set `USER_DIALOG_DEBUG_LAYOUT=1` to record geometry and opacity changes in `layout.jsonl`; document metrics include loads, text updates, and message counts, without recording document contents or answers.
The window titlebar close control remains available; the runtime adds no separate Close or Check again buttons.
If confirmation fails, the same clicked submit button offers a confirmation-only retry that never resends the response.
