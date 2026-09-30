"""Opt-in preview checks that open windows and move focus on the shared desktop.

Set USER_DIALOG_NATIVE_TESTS=1 only when the desktop is available for testing,
and run with the launcher's selected native interpreter and package environment.
Normal discovery skips these checks even when GTK is installed.
"""

from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    if os.environ.get('USER_DIALOG_NATIVE_TESTS') != '1':
        raise ImportError('Native preview tests require explicit opt-in')
    import dialog_runtime
    from dialog_document_view import DocumentView
    from dialog_layout import documents_ready
    from dialog_presentation import select_page
    from dialog_reconcile import descendants
    from dialog_spec import compile_request
    from dialog_state import read_state, save_state
    from dialog_updates import send_update
    Gtk, Adw, GLib, Gio = dialog_runtime.Gtk, dialog_runtime.Adw, dialog_runtime.GLib, dialog_runtime.Gio
    NATIVE = ((Gtk.get_major_version(), Gtk.get_minor_version()) >= (4, 16)
              and (Adw.get_major_version(), Adw.get_minor_version()) >= (1, 6))
except (ImportError, ValueError):
    NATIVE = False


@unittest.skipUnless(NATIVE, 'Requires USER_DIALOG_NATIVE_TESTS=1, native libraries and a free desktop')
class UserDialogNativeTests(unittest.TestCase):
    def setUp(self):
        Gtk.init()
        Adw.init()
        if dialog_runtime.Gdk.Display.get_default() is None:
            self.skipTest('Requires a display')
        self.temp = tempfile.TemporaryDirectory(prefix='user-dialog-native-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dialogs = []
        self.addCleanup(self.close_dialogs)

    def close_dialogs(self):
        for ui in self.dialogs:
            if not ui._finished:
                ui.dismiss()
        self.drain(0.05)

    @staticmethod
    def drain(seconds=0.05):
        deadline = time.monotonic() + seconds
        context = GLib.MainContext.default()
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.002)

    def wait(self, predicate, observe=None, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain(0.005)
            if observe:
                observe()
            if predicate():
                return
        self.fail('Native preview did not reach its expected state')

    def open(self, request, draft=None):
        directory = self.root / uuid.uuid4().hex
        directory.mkdir()
        spec = compile_request(request, self.root)
        state = {'version': 3, 'request_id': uuid.uuid4().hex, 'status': 'pending',
                 'spec': spec, 'base': str(self.root), 'origin': None, 'title': spec['title'],
                 'subtitle': '', 'draft': draft or {}, 'response': {}, 'revision': 0,
                 'delivery': {'status': 'preview'}}
        save_state(directory, state)
        app = Adw.Application(application_id='local.codex.UserDialogTests.a' + uuid.uuid4().hex,
                              flags=Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        ui = dialog_runtime.Dialog(app, directory, state)
        self.dialogs.append(ui)
        ui.open()
        self.wait(lambda: not ui.presentation.busy and documents_ready(ui.content))
        self.drain()
        return ui

    def entry(self, ui, key):
        return next(widget for widget in descendants(ui.view.widgets[key]) if isinstance(widget, Gtk.Entry))

    def test_edit_invalid_drafts_reveal_errors_and_submit_without_delivery(self):
        request = {'title': 'Preview form', 'body': {'type': 'column', 'children': [
            {'type': 'input', 'id': 'number', 'label': 'Number', 'format': 'number', 'required': True},
            {'type': 'input', 'id': 'date', 'label': 'Date', 'format': 'date'},
            {'type': 'input', 'id': 'notes', 'label': 'Notes'},
        ]}}
        ui = self.open(request, {'number': 7})
        number, date = self.entry(ui, 'number'), self.entry(ui, 'date')
        self.assertEqual(number.get_text(), '7')
        for text in ['-', 'nan', 'inf', '1e309']:
            number.set_text(text)
            ui.submit()
            self.wait(lambda: not ui.presentation.busy)
            saved = read_state(ui.run_dir)
            self.assertEqual(saved['status'], 'open')
            self.assertEqual(saved['draft']['number'], text)
            self.assertIn('invalid number', ui.status_label.get_text())
            self.assertNotIn('message', saved)
        number.set_text('9007199254740993')
        date.set_text('2026-09-')
        # Error reveal queues behind an in-progress change instead of being lost.
        ui.presentation.change(lambda: None, transition={'type': 'fade-through', 'duration': 80})
        ui.submit()
        self.wait(lambda: not ui.presentation.busy)
        self.drain()
        self.assertIn('YYYY-MM-DD', ui.status_label.get_text())
        self.assertTrue(date.has_focus() or ui.window.get_focus().is_ancestor(date))
        date.set_text('2026-09-30')
        notes = self.entry(ui, 'notes')
        notes.set_text('  **verbatim**  ')
        ui.submit(action='Send')
        saved = read_state(ui.run_dir)
        self.assertEqual(saved['status'], 'submitted')
        self.assertEqual(saved['response']['values']['number'], 9007199254740993)
        self.assertEqual(saved['draft']['number'], '9007199254740993')
        self.assertEqual(saved['response']['values']['notes'], '  **verbatim**  ')
        self.assertEqual(saved['delivery']['status'], 'preview')
        self.assertTrue(ui._finished)
        bypass = self.open(request)
        self.entry(bypass, 'number').set_text('nan')
        bypass.submit(action='Continue', include_values=False)
        saved = read_state(bypass.run_dir)
        self.assertEqual(saved['response']['values'], {})
        self.assertEqual(saved['draft']['number'], 'nan')
        self.assertNotIn('Number', saved['message']['text'])

    def test_transitions_and_live_document_update_have_one_owner(self):
        settings = Gtk.Settings.get_default()
        old_animations = settings.get_property('gtk-enable-animations')
        settings.set_property('gtk-enable-animations', True)
        self.addCleanup(settings.set_property, 'gtk-enable-animations', old_animations)
        for kind, duration in [('none', 180), ('crossfade', 180), ('slide', 180),
                               ('fade-through', 180), ('slide', 0)]:
            with self.subTest(kind=kind, duration=duration):
                request = {'title': 'Transitions', 'body': {'type': 'pages', 'id': 'pages',
                    'transition': {'type': kind, 'duration': duration}, 'children': [
                        {'type': 'column', 'id': 'first', 'label': 'First', 'children': [
                            {'type': 'input', 'id': 'first-input', 'label': 'First input'}]},
                        {'type': 'column', 'id': 'second', 'label': 'Second', 'children': [
                            {'type': 'markdown', 'id': 'document', 'text': '# Ready\n\nA settled document.'},
                            {'type': 'input', 'id': 'second-input', 'label': 'Second input'}]},
                    ]}}
                ui = self.open(request)
                stack = ui.view.stacks['pages'][0]
                self.assertEqual(stack.get_transition_type(), Gtk.StackTransitionType.NONE)
                phases, effects, native_started, native_finished = set(), [], [], []
                def observe():
                    p = ui.presentation
                    phases.add(p.phase)
                    if p.phase == 'native' and p.cover.get_transition_running():
                        effects.append((p.cover.get_transition_type(), p.cover.get_transition_duration()))
                        if not native_started:
                            native_started.append(time.monotonic())
                    elif native_started and not native_finished:
                        native_finished.append(time.monotonic())
                    if p.phase == 'out':
                        self.assertEqual(ui.scroller.get_opacity(), 0)
                ui.view.action({'type': 'navigate', 'target': 'pages', 'page': 'next'})
                self.wait(lambda: not ui.presentation.busy, observe)
                self.drain()
                self.assertEqual(stack.get_visible_child_name(), 'second')
                self.assertTrue(documents_ready(ui.content))
                second = self.entry(ui, 'second-input')
                self.assertTrue(second.has_focus() or ui.window.get_focus().is_ancestor(second))
                if kind in {'slide', 'crossfade'} and duration:
                    expected = Gtk.StackTransitionType.SLIDE_LEFT if kind == 'slide' else Gtk.StackTransitionType.CROSSFADE
                    self.assertIn((expected, duration), effects)
                    self.assertGreater(native_finished[0] - native_started[0], duration / 1000 * 0.7)
                elif kind == 'fade-through':
                    self.assertTrue({'out', 'in'} <= phases)
                else:
                    self.assertTrue(phases.isdisjoint({'native', 'out', 'in'}))
                if kind == 'none':
                    document = next(d for d in ui.documents if d.get_mapped())
                    document.dialog_has_selection = True
                    import copy
                    replacement = copy.deepcopy(request)
                    replacement['title'] = 'Updated'
                    replacement['body']['children'][1]['children'][0]['text'] = '# Updated\n\nA replaced document.'
                    second.set_text('Keep my focus and draft')
                    command = send_update(ui.run_dir, replacement, timeout=0)
                    self.drain(0.2)
                    self.assertEqual(ui.state['revision'], 0)
                    document.dialog_has_selection = False
                    result = ui.run_dir / 'updates' / (command['command_id'] + '.result.json')
                    self.wait(lambda: result.exists())
                    self.assertEqual(read_state(ui.run_dir)['update']['status'], 'applied', read_state(ui.run_dir)['update'])
                    self.assertIs(self.entry(ui, 'second-input'), second)
                    self.assertEqual(second.get_text(), 'Keep my focus and draft')
                    self.assertTrue(second.has_focus() or ui.window.get_focus().is_ancestor(second))
                ui.dismiss()


if __name__ == '__main__':
    unittest.main()
