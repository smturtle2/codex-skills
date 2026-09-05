# View contract

## Module

The launcher loads the supplied Python file and calls `build(ui)` once. Return a `Gtk.Widget` or call `ui.set_content(widget)`. The host creates one window, its header, compact spacing, blue accent, and an optional action bar. All visible content and labels belong to the authored view.

Use `ui.Gtk`, `ui.Adw`, `ui.GLib`, `ui.Gdk`, and `ui.Gio` for the runtime's libraries. Any GTK/libadwaita composition is available; there is no form-type schema. GTK Builder definitions and companion modules can live alongside the view. `ui.view_dir` and `ui.run_dir` are absolute `Path` objects; resolve assets explicitly instead of changing the process working directory.

The module and its callbacks run as local Python code with the current user's permissions. They are agent-authored code, not a sandbox for untrusted supplied scripts. Keep callbacks responsive; long blocking operations freeze GTK's event loop.

## Host API

| API | Contract |
| --- | --- |
| `ui.set_content(widget)` | Replace the content while retaining the host window; refit after construction. |
| `ui.bind(name, read, write=None)` | Register a unique value name and zero-argument getter. Optional setter receives the saved value on resume, after construction. |
| `ui.collect()` | Read bound values into a JSON-serializable dictionary. |
| `ui.action(id, label, primary=False, callback=None, default=None)` | Add an action-bar button and return it. Without a callback, activation submits bound values with that action ID. A callback takes no arguments. Primary buttons become the keyboard default unless `default=False`; `default=True` selects another button explicitly. |
| `ui.focus(widget=None)` | Set initial focus during construction or focus a control/page after navigation. `None` chooses the first control in the content. |
| `ui.set_default_action(button)` | Select the current keyboard action, or disable it with `None`. Accepts a `Gtk.Button` from the action bar or custom content. |
| `ui.keyboard(widget, activates_default=None, accepts_tab=None)` | Override a single-line entry's Enter behavior or a text view's Tab behavior when the content requires it. |
| `ui.set_validator(callback)` | Before submission, call it with the proposed values. Return `None` to accept or localized text to keep the window open and explain what needs attention. |
| `ui.message(text)` | Display localized validation feedback; empty text clears it. |
| `ui.submit(values=None, action="submit")` | Validate, save a response, close the window. `None` collects bindings; an explicit JSON value supplies the payload. |
| `ui.dismiss()` | Save the bound draft and close without an answer. Also used by the window close control. |
| `ui.defer()` | Save the bound draft and close with deferred status. |
| `ui.checkpoint()` | Save current bound values; also runs automatically every half second. |
| `ui.refit(width=None)` | Recalculate natural content size; optionally change the preferred logical width. |

`ui.window` is the host `Adw.ApplicationWindow`; `ui.request_id` identifies this request. Custom controls may connect GTK signals directly to the bridge. Avoid changing host internals. A view with no action-bar buttons can provide all interaction in its content.

Getters must return JSON-compatible values, including during partial entry. Preserve missing values rather than coercing them into selections. Convert native objects at the view boundary. Writers should restore values without submitting a response. Connect view-specific validation and button sensitivity to its own signals.

## Keyboard

Opening focuses the content before the window chrome. Native Tab/Shift+Tab traversal follows the authored widget layout. Multiline text views use Tab for traversal by default, while Enter remains a newline. Single-line entries activate the current default action with Enter through GTK's native input handling.

Ctrl+Enter activates the same default action, including its callback and validation; macOS also accepts Command+Enter. Hidden or disabled defaults are not activated. Escape dismisses and preserves the draft after native controls and input methods have had a chance to handle it. These shortcuts do not globally capture ordinary Enter, Space, or arrow keys.

GTK Stack navigation focuses the newly visible page. For other navigation containers or conditional UI, call `ui.focus()` on the intended destination and update `ui.set_default_action()` when its meaning changes. Call `ui.refit()` after inserting controls so the host can configure them. Set `default=False` for actions that should require deliberate button activation. A validator can focus the relevant input before returning its message.

Use `ui.keyboard()` for view-specific deviations. Native focus indicators, selection behavior and input-method handling remain intact. Custom compositions still need a logical widget order; the host does not guess an alternative traversal order from screen coordinates.

## Layout

The host measures content, accounts for the header and action bar, and keeps the window resizable. It does not add a scrolling viewport. If minimum content dimensions exceed the display, opening fails with the required dimensions so the agent can adapt the view.

For custom navigation, keep the values in existing widgets or bindings. Reserve inner margins for shadows inside containers that clip children during transitions. Use the full set of pages when calculating a stable window size and call `ui.refit()` after changing content requirements. Native control sizing and semantic style classes preserve the approved appearance across text sizes and display scaling.

## Response and storage

The launcher emits one final JSON object with `request_id`, `status`, `action`, `values`, and `run_dir`. An error also includes `error`. Status is `submitted`, `dismissed`, `deferred`, or `error`. Only `submitted` carries a submitted value; other outcomes have `values: null`.

`state.json` stores the absolute view path, title, draft, status, and final response. Reads through `status` are safe while the window is open. Atomic writes and process locks keep one renderer in control of a run. View output is sent to stderr so stdout remains a response channel.

The current Python view is reloaded on resume. Bound setters restore the saved draft; unbound widget state is not persisted. Submitted results are returned unchanged on subsequent resume calls. A dismissed, deferred, or failed run can reopen, keeping its request ID and draft. Use a new run for a new communication rather than overwriting a completed answer.

Process interruption is reported as an error if no final response was saved; it is never fabricated as a user action. Automatic draft checkpoints limit loss but are not a guarantee that the last keystroke survives abrupt process termination.
