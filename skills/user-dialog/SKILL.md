---
name: user-dialog
description: Compose popups with inputs, Markdown documents, and image or document file paths, then return the response as a user message in the originating conversation.
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
Use a unique ID for each new dialog and reuse its path for updates and recovery.
Input asset paths remain project-relative.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <request.json|-> --run-dir <run-dir>
```

While a dialog is open, update it with `update <run-dir> <request.json|-> [--revision N]`
using the same JSON format and stable element IDs. Paths resolve from the original
working directory; use `status <run-dir>` to inspect pending updates.

Read the [view contract](references/view-contract.md) for JSON syntax when needed,
or its [runtime section](references/view-contract.md#runtime) for validation, preview, and recovery.

The runtime preserves submitted answers and delivers them as one user message to
the originating task through its existing local app-server. It adds input to an
active turn or starts a turn when the task is idle. No agent polling or manual
reposting is needed. Continue independent work while awaiting input; retain the
run if delivery fails. Clean up expendable
files only after delivery is confirmed and the window has closed; preserve any
draft or state still needed for recovery. Save requested exports at their output destination.

Response titles, field labels, and the submitted button are emphasized automatically
using the client's theme where supported. Compose the usual request JSON; no
emphasis ranges or additional styling fields are needed. Answer text stays verbatim.

Drafts retain incomplete number/date edits for resume and compatible updates. Submission
validates active fields before recording typed numeric/date answers; invalid input stays
editable in the popup. Use the documented tabs/pages transition type and duration;
the runtime waits for document readiness, settles layout, and restores focus.
Place conditional controllers outside the content they control. Self/descendant
conditions and indirect field-dependency cycles are rejected; keep required
controllers accessible so invalid drafts can be corrected.
