---
name: user-dialog
description: Create a purpose-built popup interface to communicate with the user and return their response to the conversation.
---

# User Dialog

Compose basic UI elements freely in JSON for the communication purpose, using
file paths for documents and images. Run the provided script; do not create
request-specific executable scripts. Set `SKILL_DIR` to this skill's absolute directory.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <request.json|->
```

While a dialog is open, update it with `update <run-dir> <request.json|-> [--revision N]`
using the same JSON format and stable element IDs. Paths resolve from the original
working directory; use `status <run-dir>` to inspect pending updates.

Read the [view contract](references/view-contract.md) for JSON syntax when needed,
or its [runtime section](references/view-contract.md#runtime) for validation, preview, and recovery.

The runtime formats responses and delivers them as internal tool input to the
originating task. No polling or manual reposting is needed. Continue independent
work while awaiting input; retain the run if delivery fails.
