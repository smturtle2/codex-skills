# View contract

## Request

The launcher reads one JSON object from a file or `-`. Relative files and
custom templates resolve from the project working directory. Allowed top-level
keys:

| Key | Meaning |
| --- | --- |
| `version` | Must be `1` (defaults to `1`). |
| `title` | Required nonempty title. |
| `subtitle` | Optional subtitle. |
| `body` | Required declarative node. |
| `actions` | Optional footer actions; defaults to primary Send/submit. |
| `message` | Optional response styling: `icon` (default `💬`), `source_label` (default `팝업 응답`), `title`, and `action_label` (default `동작`). |
| `width` | Optional preferred logical width, 300..2000 (default 600). |

Unknown keys and unsupported node properties fail validation.

## Nodes and actions

Types are `column`, `row`, `grid`, `group`, `tabs`, `pages`,
`text`, `file`, `input`, `choice`, and `button`. Containers use
`children`; grid `columns` is 1..12. Group labels render as cards. Tabs
and pages require child `id` and `label`; pages also accept
`back_label` and `next_label`.

`text` accepts `text`, or `ref` naming an input for live text binding.
`file` takes an existing absolute or project-relative `path`; images are previewed and
local files have an external-open link. `button` requires `label` and
`action`.

`input` requires unique `id` and `label`; `format` is `text`,
`number`, `date`, or `file` (default text). Supported properties include
`response_label`, `multiline`, `required`, `value`, `placeholder`, `min`, `max`,
`error`, `browse_label`, and `clear_label`. `choice` requires unique
`id`, `label`, and nonempty options with unique nonempty string `value`
and readable `label`; `response_label` may override the label in the response;
`multiple` selects a list. Options may have
`content` nodes. `layout` independently arranges options using `{"type":"column"}`,
`{"type":"row"}`, or `{"type":"grid","columns":2}`. Inputs and choices support `visible_when` and
`enabled_when`.

Conditions use `ref` with `equals`, `contains`, or `empty`, recursively
combined by `all`, `any`, and `not`; a bare `ref` checks truthiness. Actions are `submit`, `dismiss`,
`defer`, `set`, `toggle`, and `navigate`. Set targets inputs or choices;
toggle targets multiple choices only; navigate targets tabs/pages and uses an
explicit page id or `next`/`previous`. Footer actions require `label`
and `action`; `primary` selects the keyboard default. A `submit` action may
set `include_values` (default `true`). With `include_values: false`, the
button action is submitted without field values and required-field validation
is bypassed; use this for a submit-role decision such as Defer or Reject.

## Templates

Use `{"type":"use","template":"question","id":"pick","params":{...}}`.
Bundled templates are in `templates/`; a custom path is project-relative.
Templates are JSON objects with `params` and declarative `body`. Parameters
use `${name}`: an exact placeholder preserves the substituted type
(including arrays/objects), while an embedded placeholder stringifies it.
Missing parameters fail compilation; `question` requires `options`, and `steps` requires `pages`. Each use needs an instance `id`; IDs
and matching `ref`/`target`/`page` references are namespaced per instance.

## Markdown, response, and lifecycle

Markdown is a readable subset: headings, bold, emphasis, inline code,
unordered lists, simple pipe tables, fenced code blocks, and standalone
local images. It is not full CommonMark. Images preview; each file has a link to open externally. Markdown links support local files and HTTP(S)/mailto destinations.

Submitted Markdown starts with one bold line in the form
`**[ICON SOURCE_LABEL · TITLE]**`, using the `message` defaults and the
existing `message.title` override; with defaults this is
`**[💬 팝업 응답 · TITLE]**`. Each included answer uses a separate bold
label line followed by a Markdown hard break and the answer verbatim; group
headings are not emitted. `response_label` overrides an input or choice label
in that record. Choice values use option labels; files use local links. Empty
and inactive fields are excluded. A submitted action is always recorded with
the `message.action_label` label (default `동작`); navigation, dismiss, and
defer actions are silent. When `include_values` is false, only the submit
button action is recorded.

The run stores compiled spec, absolute asset paths, draft, response, message,
origin, and delivery state. Escape dismisses while retaining draft; submitted
state never reopens. Tab traversal follows authored order; Enter submits
single-line input, remains newline in multiline input, and Ctrl+Enter (or
Command+Enter where supported) activates the default action.

Origin capture uses `CODEX_THREAD_ID`, optional matching `CODEX_SESSION_ID`,
and the desktop app-tools pipe. Pipe identity, host, and thread are frozen and
verified against the stored task ID before sending. No active UI, recent task,
or `--last` lookup is used. Delivery is internal tool input through the app
bridge; the live roundtrip has been verified. Windows delivery is unsupported
and fails closed. `sending` and `unknown` delivery states are never retried.

## Complete request example

All visible labels belong to the request; localize them for the user. Run with
`show request.json`; no Python view is generated. This example combines a
reusable section with a separately bound live summary:

```json
{
  "version": 1,
  "title": "Document settings",
  "body": {
    "type": "column",
    "children": [
      {
        "type": "use",
        "id": "format",
        "template": "question",
        "params": {
          "label": "Output format",
          "options": [
            {"value": "pdf", "label": "PDF", "content": [{"type": "text", "text": "Ready to share"}]},
            {"value": "md", "label": "Markdown", "content": [{"type": "text", "text": "Editable source"}]}
          ],
          "free_text_label": "Additional details"
        }
      },
      {"type": "text", "text": "Your additional details:"},
      {"type": "text", "ref": "format.free_text"}
    ]
  },
  "actions": [{"label": "Send", "primary": true, "action": {"type": "submit"}}]
}
```

A custom template follows the same format as the bundled JSON files. An array
parameter can replace `children` or option `content`, allowing whole subtrees
as slots. Template file paths and asset paths resolve from the project, not
from the template directory. Layout and content never specify delivery targets.
Unknown capabilities fail compilation; extend the shared renderer when a new
primitive is needed, rather than generating request-specific executable code.
