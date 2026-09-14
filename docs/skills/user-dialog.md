# user-dialog

Create a popup from a declarative JSON request and receive the response in the
originating Codex task.

[All skills](../../README.md#skills) · [한국어](user-dialog.ko.md)

## Installation

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

## Use

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" show <request.json|-> \
  [--run-dir <path>] [--python <absolute-python>]
```

Requests use version 1 and the keys `version`, `title`, `subtitle`,
`body`, `actions`, `message`, and `width`. The body is declarative and
does not load request-specific Python. See the [view contract](../../skills/user-dialog/references/view-contract.md).

`show` starts the detached renderer and reports operational status. Normal
submission delivers Markdown as internal tool input to the originating task
through the app bridge. `--preview` explicitly omits origin and delivery and
saves `message.md`; it is never an automatic fallback. Use `validate`,
`templates`, `status`, `resume`, and `deliver` for compilation, presets, and
run recovery.

The launcher needs uv/Python 3.11+. The renderer needs PyGObject, GTK 4.16+,
and libadwaita 1.6+. Linux rendering, origin capture, and the live app-bridge
delivery roundtrip are exercised. Windows delivery is unsupported. See
[runtime setup](../../skills/user-dialog/references/runtime-setup.md).
