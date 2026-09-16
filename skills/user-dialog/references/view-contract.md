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

Node `type` selects the element. IDs must be unique across the request. Labels are user-facing strings.
Layouts accept any nodes in `children`, including nested layouts; other elements do not accept `children`.

| Type | Properties |
| --- | --- |
| `column`, `row`, `group` | `children`, optional `label`; group renders a card. |
| `grid` | `children`, `columns` 1..12 (default 2). |
| `tabs`, `pages` | `children`, each with `id` and `label`; pages requires its own `id`, with optional `back_label`, `next_label`. Give tabs an `id` when targeting navigation. The visible child determines the stack's natural height. |
| `text` | Formatted Markdown `text`, or `ref` naming an input/choice for live value display. |
| `markdown` | Required string `text`; optional `label`. Renders a document card. |
| `code` | Required string `text`; optional string `language` and `label`. Renders a standalone code surface and copies the exact text. |
| `file` | Existing file `path`, optional `label`; previews images and text/Markdown, with an external-open link. Other formats provide a link. Markdown files render a document card. |
| `input` | Required `id`, `label`; `format`: `text` (default), `number`, `date`, `file`, `boolean`. |
| `choice` | Required `id`, `label`, `options`; selection and content rules below. |
| `button` | Required `label`, `action`. |
| `separator` | `orientation`: `horizontal` (default) or `vertical`. |
| `table` | Nonempty string list `columns`; optional `rows` of string lists matching column count. |

Inputs support `value`, `required`, `response_label` (record label override), and `error`.
Tabs/pages accept `transition: {"type": "none" | "crossfade" | "slide" | "fade-through", "duration": 120}`;
duration is 0..1000 ms. The default is fade-through at 320 ms; explicit transition types are allowed, and an explicit fade-through without a duration is also 320 ms.
Fade-through fades out before switching content, then fades in; the two pages never overlap.
Text inputs support `multiline` and `placeholder`; number inputs accept `min`/`max`; dates use `YYYY-MM-DD`.
File inputs accept `browse_label`/`clear_label`. Boolean inputs render a switch, default to `false`,
and accept `true_label`/`false_label` for recorded values (defaults `On`/`Off`); they cannot be multiline.

Choices support `value`, `required`, `response_label`, `error`, and `multiple` (default false).
Each option has a unique nonempty string `value`, a `label`, and optional `content` containing any nodes.
`presentation` is `list` (default) or `dropdown` (single selection only).
Lists show every option's content; dropdowns show the selected option's content below the control.
Only selected options contribute nested input values to the response.
List `layout` is `{"type":"column"}` (default), `{"type":"row"}`, or `{"type":"grid","columns":2}` (1..12 columns).

Text and Markdown nodes support headings, bold, emphasis, code, lists, simple tables, links, and standalone local images;
they are not full CommonMark. Image paths in `text` and `markdown` nodes resolve from the project base. Repeated blank
separators collapse, and the trailing blank separator is removed; code-block whitespace remains exact. Inline backtick
code content remains literal.
Text remains selectable continuously while sending and stays formatted as an explanation, without document chrome,
source-copy controls, or code-block copy buttons.
Adjacent static `text` nodes in a `column` or `group` share a selection area across paragraphs.
Nodes with IDs, bindings, conditions, or fenced code retain their own area, as do separate controls and layouts.

Standalone `code` nodes preserve and copy their exact `text`, with an optional `language` hint. They use a gray,
code-toned background and share the system monospace font with fenced code in documents. Document surfaces use a
separate white/light-theme surface (or the theme-appropriate dark surface); fenced code inside documents remains
visually distinct from surrounding document text. Theme changes update both code presentations.

Markdown nodes render a document card in the popup's main scroll area; there is no separate inner document scroller.
Titles use one line with ellipsis when needed; a tooltip exposes the full title/path.
Its title is `label` when provided, otherwise `Markdown`. The title opens the source `.md` file when applicable;
the UI does not add a duplicated file link below it. The title's source-copy control copies the exact original Markdown,
and code-block buttons copy code without fences; each clicked copy control briefly shows a check icon in place of a toast.
Files ending in `.md` or `.markdown` render the same document card, titled by `label` when provided or by the filename.
Markdown file image paths resolve from the Markdown file's directory. File path convenience is unchanged.
All content remains selectable while a response is sending.

## Conditions and actions

Nodes and footer buttons accept `visible_when` and `enabled_when`. A condition uses `ref` to an input/choice,
optionally with one of `equals`, `contains`, or `empty`. Combine conditions with `all`/`any` lists or `not`.
A bare `ref` checks truthiness. Example: `{"ref":"details_enabled","equals":true}`.

Footer buttons require `label` and `action`; `primary: true` selects the keyboard default.

| Action `type` | Properties and effect |
| --- | --- |
| `submit` | Records the button and active answers. `include_values: false` sends only the button and skips field validation. |
| `dismiss`, `defer` | Close without delivering a response; preserve the draft. |
| `set` | Input/choice `target` and `value`, either literal or `{"ref":"another_input"}`. |
| `toggle` | Multiple-choice `target` and option `value` to toggle. |
| `navigate` | Tabs/pages `target`; `page` is a child ID, `next`, or `previous`. |

## Live updates

`update <run-dir> <request.json|-> [--revision N] [--timeout SECONDS]` applies JSON compiled against the original `show` base. It owns the exact originating thread, request ID, and revision; stable element IDs reuse unchanged widgets, compatible changed fields preserve values, and a focused or selected replaced subtree waits until focus leaves or selection clears. Removing or changing the type of an answered field, or removing a chosen option, is rejected. Assets at the same paths are reread for an update; they are not watched automatically. Updates are accepted while the dialog is open and stop at submission. A timeout returns `queued`; do not resubmit it. `status` reports `revision` and `update`, and each command writes `updates/<command_id>.result.json`. `applied` is acknowledged after paint; closing the window before confirmation reports `interrupted`.

## Response

The runtime produces a bold `[💬 Popup response · TITLE]` header, labeled answers, and a bold `→ BUTTON_LABEL` final line.
The source text is fixed English; titles, field labels, and button text come from the popup, with optional `message.title` and `response_label` overrides. Typed text and line breaks remain verbatim.
Choices use option labels; attachments use file links; empty/inactive fields and display-only content are omitted.

## Example

```json
{
  "title": "Document settings",
  "body": {"type": "column", "children": [
    {"type": "choice", "id": "format", "label": "Output format", "presentation": "dropdown",
     "options": [
       {"value": "pdf", "label": "PDF", "content": [{"type": "text", "text": "Ready to share"}]},
       {"value": "md", "label": "Markdown", "content": [{"type": "text", "text": "Editable source"}]}
     ]},
    {"type": "input", "id": "notes", "label": "Additional details", "multiline": true}
  ]},
  "actions": [{"label": "Send", "primary": true, "action": {"type": "submit"}}]
}
```

## Runtime

Commands use `uv run --script "$SKILL_DIR/scripts/user_dialog.py" …`.
The launcher needs Python 3.11+; the native renderer needs PyGObject, GTK 4.16+, and libadwaita 1.6+.
On Debian/Ubuntu these are `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`; uv does not install native libraries.
Normal delivery requires the originating local Codex desktop connection and a Codex CLI supporting
`thread/items/list`. `USER_DIALOG_CODEX` selects the CLI (default: `codex` on PATH).
The runtime starts a temporary read-only app-server to confirm the response, then stops it.
Remote-task and Windows delivery are unsupported.

| Command | Purpose |
| --- | --- |
| `elements` / `--help` | List element types / CLI options. |
| `validate <request.json\|->` | Check a request without opening a window. |
| `show <request.json\|-> --preview` | Open without delivery; submission saves `message.md`. |
| `show <request.json\|-> --preview --render-image <file.png>` | Export the renderer's own visible widget tree and close, without delivery. Useful for inspecting layout. |
| `show <request.json\|-> --run-dir <path>` | Choose the workspace. Without this option, create a unique run under `.codex-skills/user-dialog/` in the project working directory. |
| `doctor --delivery` | Check native libraries and task connection without sending. |
| `status <run-dir>` / `resume <run-dir>` | Inspect status / reopen the saved draft; submitted runs stay closed. |
| `update <run-dir> <request.json|->` | Queue one live update; optional `--revision N` checks the current revision and `--timeout` defaults to 10 seconds. |
| `deliver <run-dir>` | Retry a confirmed pre-send failure from the original task. |
| `confirm <run-dir>` | Recheck a submitted response without sending it again. |

`show`, `resume`, and `doctor` accept `--python <path>`; `USER_DIALOG_PYTHON` also selects the renderer interpreter.
Keep the run and referenced assets available. On failure, inspect status and `renderer.log`.
Submission and delivery are separate: a saved answer may have unconfirmed delivery.
The runtime prevents retries of `sending`, `unknown`, or accepted deliveries; do not resend those answers manually.
Automatic closing waits for a matching new response item after the saved pre-send history position.
While sending, the clicked submit button shows a fixed-size sending indicator, and document selection/copy remains available.
Automatic focus prefers inputs, then an action button; it does not select display text. Manual text selection remains available.
Automatic focus skips offscreen inputs so opening a long popup preserves its start. Content-height changes reschedule window sizing after text layout validation.
Set `USER_DIALOG_DEBUG_LAYOUT=1` to record geometry and opacity changes in `layout.jsonl`, without recording content or answers.
The window titlebar close control remains available; the runtime adds no separate Close or Check again buttons.
If confirmation fails, the same clicked submit button offers a confirmation-only retry that never resends the response.
Older runs without a saved history position cannot use automatic confirmation.
