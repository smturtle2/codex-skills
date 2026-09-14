---
name: user-dialog
description: Create a purpose-built popup interface to communicate with the user and return their response to the conversation.
---

# User Dialog

Compose a compact blue libadwaita dialog from a version 1 JSON request. The
renderer owns GTK, persistence, keyboard behavior, validation, and response
formatting; request-specific Python modules are not used.

Set `SKILL_DIR` to this skill's absolute directory. Request files and relative
custom template paths resolve from the project working directory.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <request.json|-> \
  [--run-dir <path>] [--python <absolute-python>]
```

`show` compiles the request, starts the renderer detached, and returns
operational status. A normal run captures the originating Codex task and
delivers the submitted result there as internal tool input through the desktop
app bridge. Add `--preview` to open without origin or delivery and save
`message.md`; preview is explicit and never a silent fallback.

Top-level keys are `version`, `title`, `subtitle`, `body`, `actions`,
`message`, and `width`; `title` is required and `version` is `1`.
Read [the view contract](references/view-contract.md) before composing when its schema is absent from context.
Use bundled templates as editable building blocks, or supply a custom JSON template;
compose content and behavior for the actual communication purpose. Localize visible
labels so each answer remains understandable on its own; use `response_label`
when a long prompt needs a shorter answer label. The runtime owns response
formatting, and typed text remains verbatim.
For interpreter or connection errors, read [runtime setup](references/runtime-setup.md).

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" validate <request.json|->
uv run --script "$SKILL_DIR/scripts/user_dialog.py" templates
uv run --script "$SKILL_DIR/scripts/user_dialog.py" status <run-dir>
uv run --script "$SKILL_DIR/scripts/user_dialog.py" resume <run-dir>
uv run --script "$SKILL_DIR/scripts/user_dialog.py" deliver <run-dir>
```

`validate` reports structural validity. `resume` reuses the compiled spec
and absolute asset paths, restores the draft, and never reopens submitted state.
`deliver` retries only safe pre-send failures; `sending`, `unknown`, and
accepted states cannot be retried. Keep the run and referenced assets available.

After a successful normal launch, continue independent work or finish the current turn when waiting on the user. The detached renderer delivers the answer to the pinned task. Do not keep polling for the answer or repost `message.md` yourself. Dismissal, deferral, and navigation send nothing. A delivery error is not a submitted message; preserve the run and report its actual status.
