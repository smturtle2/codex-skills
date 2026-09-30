"""Headless process checks for popup admission, confirmation and cancellation."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
from dialog_lifecycle import wait_for_renderer
from dialog_state import read_state, save_state
import user_dialog


RENDERER = r'''
import os, sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from dialog_lifecycle import watch_origin
from dialog_state import finish_state, read_state, run_lock, save_state
directory = Path(sys.argv[1])
ended = threading.Event()
awaited = '--await-origin' in sys.argv[3:]
if awaited:
    watch_origin(sys.stdin.buffer, ended.set)
with run_lock(directory, '.window-lock'):
    state = read_state(directory)
    state.update(status='open', draft={'notes': '  saved 한글 β\nanswer  '})
    save_state(directory, state)
    while True:
        release = directory / 'release'
        if release.exists():
            mode = release.read_text()
            state = read_state(directory)
            state['message'] = {'type': 'text', 'text': state['draft']['notes']}
            finish_state(directory, state, 'submitted', state['draft'], 'Send')
            state['delivery'] = {'status': 'sending' if mode == 'crash' else mode,
                                 'client_message_id': 'saved-response-uuid',
                                 'observation': {'status': 'waiting'}}
            save_state(directory, state)
            if mode == 'crash':
                os._exit(7)
            if awaited:
                assert ended.wait(5), 'Launcher waited for confirmation before returning'
            state = read_state(directory)
            state['delivery']['observation'] = {'status': 'observed', 'item_id': 'canonical-item'}
            save_state(directory, state)
            break
        if ended.is_set():
            finish_state(directory, read_state(directory), 'deferred', None)
            break
        time.sleep(.01)
'''


class UserDialogLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dialog-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.renderer = self.root / 'renderer.py'
        self.renderer.write_text(RENDERER)
        self.processes = []
        self.addCleanup(self.stop_processes)
        self.popen = subprocess.Popen

    def stop_processes(self):
        for process in self.processes:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)

    def launch(self, command, **kwargs):
        process = self.popen([sys.executable, str(self.renderer), command[2], str(SCRIPTS), *command[3:]], **kwargs)
        self.processes.append(process)
        return process

    def args(self, name):
        request = self.root / (name + '.json')
        request.write_text(json.dumps({'title': 'Lifecycle', 'body': {
            'type': 'input', 'id': 'notes', 'label': 'Notes'}}))
        return argparse.Namespace(command='show', request=str(request), run_dir=str(self.root / name),
                                  preview=False, render_image=None, python=None)

    def patches(self, awaited):
        return (
            patch.object(user_dialog, 'capture_origin', return_value={'transport': 'test'}),
            patch.object(user_dialog, 'backend_for', return_value=argparse.Namespace(awaits_response=awaited)),
            patch.object(user_dialog, 'find_python', return_value={'python': sys.executable}),
            patch.object(user_dialog, 'python_environment', side_effect=lambda _: os.environ.copy()),
            patch.object(user_dialog.subprocess, 'Popen', side_effect=self.launch),
            patch.object(user_dialog, 'print', create=True),
        )

    def wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Lifecycle did not reach its expected state')

    def test_awaited_launcher_releases_at_wire_outcome_and_detached_launcher_at_readiness(self):
        for mode in ('accepted', 'unknown', 'detached'):
            with self.subTest(mode=mode):
                args = self.args(mode)
                directory = Path(args.run_dir)
                result, errors = [], []
                def run():
                    try:
                        result.append(user_dialog.run_dialog(args))
                    except BaseException as error:
                        errors.append(error)
                p = self.patches(mode != 'detached')
                with p[0], p[1], p[2], p[3], p[4], p[5] as output:
                    thread = threading.Thread(target=run)
                    thread.start()
                    self.wait(lambda: (directory / 'state.json').exists()
                              and read_state(directory)['status'] == 'open')
                    if mode == 'detached':
                        thread.join(timeout=3)
                        self.assertFalse(thread.is_alive())
                    else:
                        self.assertTrue(thread.is_alive())
                    (directory / 'release').write_text('accepted' if mode == 'detached' else mode)
                    thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(errors, [])
                    self.assertEqual(result, [0])
                    if mode != 'detached':
                        returned = json.loads(output.call_args.args[0])
                        self.assertEqual(returned['delivery'], mode)
                        self.assertEqual(returned['observation']['status'], 'waiting')
                    self.processes[-1].wait(timeout=3)
                    saved = read_state(directory)
                    self.assertEqual(saved['response']['values']['notes'], '  saved 한글 β\nanswer  ')
                    self.assertEqual(saved['delivery']['observation']['status'], 'observed')

    def test_origin_cancellation_and_renderer_death_preserve_draft_and_submitted_answer(self):
        for mode in ('cancel', 'crash'):
            with self.subTest(mode=mode):
                args = self.args(mode)
                directory = Path(args.run_dir)
                p = self.patches(True)
                with p[0], p[1], p[2], p[3], p[4], p[5]:
                    if mode == 'cancel':
                        def cancel(directory, process, **kwargs):
                            wait_for_renderer(directory, process)
                            raise KeyboardInterrupt
                        with patch.object(user_dialog, 'wait_for_renderer', side_effect=cancel):
                            with self.assertRaises(KeyboardInterrupt):
                                user_dialog.run_dialog(args)
                        self.processes[-1].wait(timeout=3)
                        saved = read_state(directory)
                        self.assertEqual(saved['status'], 'deferred')
                        self.assertEqual(saved['draft']['notes'], '  saved 한글 β\nanswer  ')
                        self.assertNotIn('message', saved)
                    else:
                        result = []
                        thread = threading.Thread(target=lambda: result.append(user_dialog.run_dialog(args)))
                        thread.start()
                        self.wait(lambda: (directory / 'state.json').exists()
                                  and read_state(directory)['status'] == 'open')
                        (directory / 'release').write_text('crash')
                        thread.join(timeout=3)
                        self.assertFalse(thread.is_alive())
                        saved = read_state(directory)
                        self.assertEqual(saved['status'], 'submitted')
                        self.assertEqual(saved['delivery']['status'], 'unknown')
                        self.assertEqual(saved['delivery']['observation']['status'], 'unconfirmed')
                        self.assertEqual(saved['response']['action'], 'Send')
                        self.assertEqual(saved['response']['values'], saved['draft'])

    def test_startup_timeout_preserves_submission_saved_while_renderer_terminates(self):
        directory = self.root / 'timeout'
        directory.mkdir()
        state = {'version': 3, 'request_id': 'timeout', 'status': 'pending',
                 'draft': {'notes': 'old'}, 'response': {}, 'delivery': {'status': 'pending'}}
        save_state(directory, state)
        process = Mock(returncode=7)
        process.poll.return_value = None
        def final_write():
            state.update(status='submitted', draft={'notes': 'new 한글 β'},
                         response={'status': 'submitted', 'action': 'Send', 'values': {'notes': 'new 한글 β'}},
                         message={'type': 'text', 'text': 'new 한글 β'},
                         delivery={'status': 'sending', 'client_message_id': 'saved-response-uuid'})
            save_state(directory, state)
        process.terminate.side_effect = final_write
        with patch('dialog_lifecycle.time.monotonic', side_effect=[0, 16]):
            saved = wait_for_renderer(directory, process, await_response=True)
        process.wait.assert_called_once_with(timeout=2)
        self.assertEqual(saved['status'], 'submitted')
        self.assertEqual(saved['response']['values'], {'notes': 'new 한글 β'})
        self.assertEqual(saved['delivery']['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
