---
name: user-dialog
description: Compose popups with inputs, Markdown documents, and image or document file paths, then deliver the response to the originating CLI or Desktop conversation.
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

Both clients return after the popup is ready. The popup runs independently of the
calling tool and originating turn; completion, interruption, or changing the
focused conversation does not close it. Continue work or finalize normally.
If startup yields a running exec session or cell, wait on that same ID in bounded
waits of at most 60 seconds until readiness is reported.

While a dialog is open, update it with `update <run-dir> <request.json|-> [--revision N]`
using the same JSON format and stable element IDs. Paths resolve from the original
working directory; use `status <run-dir>` to inspect pending updates.

Read the [view contract](references/view-contract.md) for JSON syntax when needed,
or its [runtime section](references/view-contract.md#runtime) for validation, preview, and recovery.

The runtime captures the original conversation and chooses its delivery backend
automatically. CLI discovers its existing managed shared daemon, using
`turn/steer` with `expectedTurnId` while active and `turn/start` while idle.
Desktop uses the inherited tools pipe and `codex_app.send_message_to_thread`;
the app selects its active steering or idle start path and displays the delegated
tool output as a user-style message from another task. These clients use their own
existing servers and binaries; no endpoint selection or app launch change is needed.
Remote and embedded CLI servers are unsupported.

Submission saves the exact answer and freezes the popup. Automatic closing waits
for that answer's actual native input item, not an acknowledgement or the agent's
final response. Distinct conversations can receive responses concurrently.
Desktop serializes this skill's submissions to one conversation until input is
confirmed, with durable coordination in the shared Codex home across projects.

Once input may have been admitted, errors or lost acknowledgements never trigger
another send. Confirmation uses the client's saved native records without replay.
Use `resume <run-dir>` to reopen an unconfirmed submitted popup with its saved
answer locked and continue confirmation; confirmed and preview submissions stay closed.
Retain unconfirmed runs; clean up expendable files after confirmation and window
closure, preserving drafts and recovery state. Save requested exports at their
output destination.

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
