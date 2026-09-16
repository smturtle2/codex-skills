---
name: user-dialog
description: Compose popups with inputs, Markdown documents, and image or document file paths, then return the user's response to the conversation.
---

# User Dialog

Compose basic UI elements freely in JSON for the communication purpose, using
inputs and file paths for documents and images. Run the provided script; do not
create request-specific executable scripts. Set `SKILL_DIR` to this skill's
absolute directory.

Use `markdown` for body content, from brief explanations to full documents,
and `file` for existing documents or images. Markdown is unframed by default;
title, border, source-copy, and code-copy controls are independent display options.
See the [view contract](references/view-contract.md) for supported syntax and options.

Run from the session project root. Keep request JSON, state, and logs in
`.codex-skills/user-dialog/<run-id>/` unless the user chooses another workspace.
Use a unique ID for each new dialog and reuse its path for updates and recovery,
including dialogs saved at older locations. Input asset paths remain project-relative.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <request.json|-> --run-dir <run-dir>
```

While a dialog is open, update it with `update <run-dir> <request.json|-> [--revision N]`
using the same JSON format and stable element IDs. Paths resolve from the original
working directory; use `status <run-dir>` to inspect pending updates.

Read the [view contract](references/view-contract.md) for JSON syntax when needed,
or its [runtime section](references/view-contract.md#runtime) for validation, preview, and recovery.

The runtime formats responses and delivers them as internal tool input to the
originating task. No polling or manual reposting is needed. Continue independent
work while awaiting input; retain the run if delivery fails. Clean up expendable
files only after delivery is confirmed and the window has closed; preserve any
draft or state still needed for recovery. Save requested exports at their output destination.
