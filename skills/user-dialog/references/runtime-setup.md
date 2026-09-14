# Runtime setup

Run:

```bash
uv run --script <skill-dir>/scripts/user_dialog.py <command> ...
```

The launcher requires Python 3.11+ and no third-party launcher packages. The
renderer uses a separately discovered interpreter with PyGObject, GTK 4.16+,
and libadwaita 1.6+; uv does not install native libraries.

```bash
uv run --script "$SKILL_DIR/scripts/user_dialog.py" doctor [--python <path>]
```

Use `--python` on `show`, `resume`, or `doctor`, or set
`USER_DIALOG_PYTHON`. Explicit selection is authoritative. Otherwise the
launcher checks the launching interpreter, PATH, and platform locations.
Discovery checks imports and versions, not display access.

Typical native packages:

| Platform | Packages |
| --- | --- |
| Debian/Ubuntu | `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1` |
| Fedora | `python3-gobject`, `gtk4`, `libadwaita` |
| Arch | `python-gobject`, `gtk4`, `libadwaita` |
| Homebrew | `pygobject3`, `gtk4`, `libadwaita` plus matching Python |

Linux rendering and read-only origin capture have been exercised. macOS
AF_UNIX bridge discovery is a candidate, but actual send delivery is not
exercised. Windows delivery is unsupported. Preserve a run and inspect the
renderer error before resuming when imports succeed but the window fails.

Use `doctor --delivery` to verify GTK and the originating desktop connection without sending a message. Request JSON is version 1; persisted run state is version 2. Legacy Python-view runs are rejected rather than executed.
