# View contract

## Request

Pass a JSON object as a file or stdin (`-`). Asset paths are absolute or relative to the project working directory.

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
| `tabs`, `pages` | `children`, each with `id` and `label`; pages requires its own `id`, with optional `back_label`, `next_label`. Give tabs an `id` when targeting navigation. |
| `text` | Markdown `text`, or `ref` naming an input/choice for live value display. |
| `file` | Existing file `path`; previews images and text/Markdown, with an external-open link. Other formats provide a link. |
| `input` | Required `id`, `label`; `format`: `text` (default), `number`, `date`, `file`, `boolean`. |
| `choice` | Required `id`, `label`, `options`; selection and content rules below. |
| `button` | Required `label`, `action`. |
| `separator` | `orientation`: `horizontal` (default) or `vertical`. |
| `table` | Nonempty string list `columns`; optional `rows` of string lists matching column count. |

Inputs support `value`, `required`, `response_label` (record label override), and `error`.
Text inputs support `multiline` and `placeholder`; number inputs accept `min`/`max`; dates use `YYYY-MM-DD`.
File inputs accept `browse_label`/`clear_label`. Boolean inputs render a switch, default to `false`,
and accept `true_label`/`false_label` for recorded values (defaults `On`/`Off`); they cannot be multiline.

Choices support `value`, `required`, `response_label`, `error`, and `multiple` (default false).
Each option has a unique nonempty string `value`, a `label`, and optional `content` containing any nodes.
`presentation` is `list` (default) or `dropdown` (single selection only).
Lists show every option's content; dropdowns show the selected option's content below the control.
Only selected options contribute nested input values to the response.
List `layout` is `{"type":"column"}` (default), `{"type":"row"}`, or `{"type":"grid","columns":2}` (1..12 columns).

Text/Markdown supports headings, bold, emphasis, code, lists, simple tables, links, and standalone local images;
it is not full CommonMark. Markdown image paths resolve from the document's directory.

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
Normal delivery requires the originating Codex desktop connection; Windows delivery is unsupported.

| Command | Purpose |
| --- | --- |
| `elements` / `--help` | List element types / CLI options. |
| `validate <request.json\|->` | Check a request without opening a window. |
| `show <request.json\|-> --preview` | Open without delivery; submission saves `message.md`. |
| `show <request.json\|-> --run-dir <path>` | Choose where the run is saved. |
| `doctor --delivery` | Check native libraries and task connection without sending. |
| `status <run-dir>` / `resume <run-dir>` | Inspect status / reopen the saved draft; submitted runs stay closed. |
| `deliver <run-dir>` | Retry a confirmed pre-send failure from the original task. |

`show`, `resume`, and `doctor` accept `--python <path>`; `USER_DIALOG_PYTHON` also selects the renderer interpreter.
Keep the run and referenced assets available. On failure, inspect status and `renderer.log`.
Submission and delivery are separate: a saved answer may have unconfirmed delivery.
The runtime prevents retries of `sending`, `unknown`, or accepted deliveries; do not resend those answers manually.
