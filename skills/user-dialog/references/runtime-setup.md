# Runtime setup

The public entry point is `uv run --script <skill-dir>/scripts/user_dialog.py`. Its inline metadata requires Python 3.11+ and no third-party launcher dependencies. GTK runs in a discovered interpreter containing PyGObject, GTK 4.16+, and libadwaita 1.6+. These native libraries are not installed by uv.

## Discover or select

Run `doctor` through the entry point. It prints the selected interpreter and library versions or the failed probes. It checks dependencies, not display access or complete OS compatibility.

Use `--python <absolute-python-path>` with `doctor`, `show`, or `resume`, or set `USER_DIALOG_PYTHON`. An explicit selection is authoritative and does not silently fall back. Otherwise discovery checks the launching interpreter, PATH, and conventional system/Homebrew/MSYS2 locations.

On Windows, the child process receives the interpreter's directory in PATH and PYGI_DLL_PATH for native library loading. Existing values are preserved. No global environment or desktop settings are modified.

## Dependencies

Use the platform's native packages or an already configured Python environment. Verify versions with `doctor`; older distributions may not meet the minimums. Do not change system packages merely to diagnose a missing runtime.

| Platform | Required runtime packages |
| --- | --- |
| Debian / Ubuntu | `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1` |
| Fedora | `python3-gobject`, `gtk4`, `libadwaita` |
| Arch | `python-gobject`, `gtk4`, `libadwaita` |
| macOS / Homebrew | `pygobject3`, `gtk4`, `libadwaita`; select the matching Homebrew Python |
| Windows / MSYS2 UCRT64 | `mingw-w64-ucrt-x86_64-python`, `mingw-w64-ucrt-x86_64-python-gobject`, `mingw-w64-ucrt-x86_64-gtk4`, `mingw-w64-ucrt-x86_64-libadwaita` |

Installation references: [PyGObject](https://pygobject.gnome.org/getting_started.html), [Homebrew libadwaita](https://formulae.brew.sh/formula/libadwaita), [MSYS2 libadwaita](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-libadwaita). GTK has [Windows and macOS backends](https://docs.gtk.org/gtk4/overview.html); packaging and behavior still need to be checked on each target. The current implementation has been exercised locally on Linux, not on Windows or macOS.

If imports succeed but the window cannot open, inspect the actual renderer error and its process environment. Preserve the run and fix the delivery problem before resuming. Window focus and notification behavior remain under the desktop's control.
