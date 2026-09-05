---
name: user-dialog
description: Create a purpose-built popup interface to communicate with the user and return their response to the conversation.
---

# User Dialog

Codex determines the content and interaction. The helper displays an agent-authored GTK/libadwaita view, preserves its bound values, and returns the response. Compose the interface for the actual communication purpose; do not constrain it to a catalog of forms.

Use the compact blue libadwaita shell. Group related requests in one window, preserving entered values across navigation. Fit the content without clipping text, controls, or card shadows; adapt the composition before introducing unnecessary scrolling. Keep implementation commentary out of the interface.

Make the interaction usable without a mouse. Use the host's focus and default-action bridge, and keep keyboard order consistent with the authored layout.

## Compose and Open

Set `SKILL_DIR` to this skill's absolute directory. Resolve view and run paths from the session project.

Read [references/view-contract.md](references/view-contract.md) before authoring the view when its API is absent from context. Write a Python module exposing `build(ui)` using the provided GTK objects and response bridge. Place request-specific files outside the installed skill directory.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <view.py> \
  --title "<user-facing title>" --run-dir <run-dir>
```

The default run location is `dialog-runs/<unique-id>/`. The helper prints its path to stderr and returns one JSON response on stdout when the window finishes. If runtime discovery fails, read [references/runtime-setup.md](references/runtime-setup.md) and resolve the reported dependency or interpreter issue.

## Receive and Continue

Retain and poll a yielded execution handle while awaiting the response. Do not open another copy of the same request or give a final waiting handoff while a response is still expected.

Interpret `submitted` together with its action ID and values. `dismissed` and `deferred` contain no submitted answer. Do not treat closure or an untouched field as consent. Popup responses do not replace tool-required approvals.

For a requested reopening or interrupted run:

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" status <run-dir>
uv run --script "$SKILL_DIR/scripts/user_dialog.py" resume <run-dir>
```

Resume restores bound values; an already submitted run returns its saved response without reopening. Keep the original view and supporting files available. Fix view errors in those files and resume instead of changing the shared helper for a particular request.

Report the actual response or delivery failure. Preserve the run when further interaction or recovery is needed.
