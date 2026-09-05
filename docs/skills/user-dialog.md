# user-dialog

Compose a purpose-built popup interface, communicate with the user, and receive their response.

[All skills](../../README.md#skills) · [한국어](user-dialog.ko.md)

## Install

```text
Use $skill-installer to install skills/user-dialog from https://github.com/smturtle2/codex-skills.
```

Requires uv and a Python environment with GTK4, libadwaita, and PyGObject. The launcher finds that interpreter separately from uv's Python. See [runtime setup](../../skills/user-dialog/references/runtime-setup.md) for native dependencies and explicit interpreter selection. Linux execution has been checked; Windows and macOS remain unverified.

## Interface

The default appearance is compact, blue libadwaita. Codex authors the content and interaction without a fixed catalog of forms. Related requests share one window, and the common host preserves registered values and returns a structured response.

Keyboard focus starts in the content. Tab and Shift+Tab move between controls; Enter activates the default action in single-line input and remains a newline in multiline input. Ctrl+Enter activates the default action (also Command+Enter on macOS). Escape closes while retaining the draft. Views can adjust focus and default actions to match their interaction.

## Output

The run directory retains the view reference, bound draft values, and final response. The generated view and any supporting files remain outside the installed skill. Reopening restores registered values; submitted results can be read without reopening. Closing a window does not submit an answer.

[Agent instructions](../../skills/user-dialog/SKILL.md)
