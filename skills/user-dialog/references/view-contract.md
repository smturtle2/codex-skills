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
It automatically marks the header, field labels, and button line with `text_elements` UTF-8 byte ranges.
The CLI displays these in its theme's accent color; clients without this styling still show readable plain text.
Request authors do not specify ranges or add formatting options. Generated labels have no Markdown delimiters
or escaping; Markdown typed by the user remains verbatim. This is client emphasis, not Markdown bold.
Each submission becomes one ordinary user message in the originating conversation, not a tool output.
The source text is fixed English; titles, field labels, and button text come from the popup, with optional `message.title` and `response_label` overrides. Typed text and line breaks remain verbatim.
Choices use option labels; attachments show the filename and absolute path on separate lines;
empty/inactive fields and display-only content are omitted.
Submission first saves the editable draft, converts it, validates active fields, formats the response, and persists the submitted record before delivery.
`state.json` keeps the editable draft, typed active answers, and complete text input object; `message.txt` holds the plain-text preview.
Button-only submission still saves the draft while skipping field validation and answers. Legacy numeric drafts reopen as editable text; already submitted messages remain unchanged during recovery.
Retries reuse that object. Runtime state uses version 3; other state versions are rejected.
Arrival confirmation uses message identity and text, so
presentation differences never cause a duplicate submission.

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
Normal delivery requires the originating task to be loaded in an existing local Codex app-server.
The runtime connects over WebSocket to `$CODEX_HOME/app-server-control/app-server-control.sock`
(`CODEX_HOME` defaults to `~/.codex`). `USER_DIALOG_SOCKET` selects a custom local Unix socket;
set it before `show` and keep the same setting for updates and recovery. It never starts another
server or resumes a thread on a different server. CLI, IDE, and app tasks can use this connection;
a standalone CLI without an accessible server socket cannot. Remote and Windows delivery are unsupported.
The server must support `thread/read`, `thread/loaded/list`, `thread/turns/list`, `thread/items/list`,
`turn/steer`, `turn/start`, and user-message IDs (`clientUserMessageId` / history `clientId`).
This protocol was verified with Codex 0.158.0. uv supplies the WebSocket dependency.

Submission uses `turn/steer` with the current `expectedTurnId` while a turn is active, and
`turn/start` with ordinary text input when idle. Only an explicit turn-change rejection permits
rerouting; a lost acknowledgement never triggers another send. Delivery and history confirmation
use the same server connection. Each submission saves a client message ID before sending and
confirms that exact `userMessage` and its original text. The ID correlates messages; it is not
assumed to make repeat sends idempotent.

| Command | Purpose |
| --- | --- |
| `elements` / `--help` | List element types / CLI options. |
| `validate <request.json\|->` | Check a request without opening a window. |
| `show <request.json\|-> --preview` | Open without delivery; submission saves `message.txt` and the styled input in state. |
| `show <request.json\|-> --preview --render-image <file.png>` | Export the renderer's own visible widget tree and close, without delivery. Useful for inspecting layout. |
| `show <request.json\|-> --run-dir <path>` | Choose the workspace. Without this option, create a unique run under `.codex-skills/user-dialog/` in the project working directory. |
| `doctor --delivery` | Check native libraries, the originating loaded task, and turn/history reads without sending. |
| `status <run-dir>` / `resume <run-dir>` | Inspect status / reopen the saved draft; submitted runs stay closed. |
| `update <run-dir> <request.json|->` | Queue one live update; optional `--revision N` checks the current revision and `--timeout` defaults to 10 seconds. |
| `deliver <run-dir>` | Retry a pre-send failure or explicit rejection from the original task. |
| `confirm <run-dir>` | Recheck a submitted response without sending it again. |

`show`, `resume`, and `doctor` accept `--python <path>`; `USER_DIALOG_PYTHON` also selects the renderer interpreter.
Keep the run and referenced assets available. On failure, inspect status and `renderer.log`.
Submission and delivery are separate: a saved answer may have unconfirmed delivery.
The runtime prevents retries of `sending`, `unknown`, or accepted deliveries; do not resend those answers manually.
Automatic closing waits for a matching new response item after the saved pre-send history position.
New responses match by client message ID and exact text, so identical answers from separate popups remain distinct.
An interrupted `sending` state is also confirmation-only.
While sending, the clicked submit button shows a fixed-size sending indicator, and document selection/copy remains available.
Automatic focus prefers inputs, then an action button; it does not select display text. Manual text selection remains available.
Automatic focus skips offscreen inputs so opening a long popup preserves its start. Content-height changes reschedule window sizing after text layout validation, but automatic resizing waits during document selection. Draft updates are coalesced for 300 ms and flushed before submit or close.
One presentation controller owns page and live-update transitions. It waits for mapped documents and settled layout, applies the chosen effect once, then restores retained focus or focuses the new page's controls.
Set `USER_DIALOG_DEBUG_LAYOUT=1` to record geometry and opacity changes in `layout.jsonl`; document metrics include loads, text updates, and message counts, without recording document contents or answers.
The window titlebar close control remains available; the runtime adds no separate Close or Check again buttons.
If confirmation fails, the same clicked submit button offers a confirmation-only retry that never resends the response.
