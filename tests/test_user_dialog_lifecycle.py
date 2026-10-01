"""Headless process checks for detached popup readiness and frozen recovery."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
from dialog_lifecycle import wait_for_renderer
from dialog_state import read_state, save_state
import user_dialog


RENDERER = r'''
import os, sys, time, uuid
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from dialog_state import finish_state, read_state, run_lock, save_state
directory = Path(sys.argv[1])
assert '--await-origin' not in sys.argv
with run_lock(directory, '.window-lock'):
    state = read_state(directory)
    if state['status'] != 'submitted':
        state.update(status='open', draft={'notes': '  saved 한글 β\nanswer  '})
    state['renderer_ready'] = True
    save_state(directory, state)
    while True:
        release = directory / 'release'
        if release.exists():
            mode = release.read_text()
            state = read_state(directory)
            if state['status'] != 'submitted':
                state['message'] = {'type': 'text', 'text': state['draft']['notes']}
                finish_state(directory, state, 'submitted', state['draft'], 'Send')
            identity = state['delivery'].get('response_id') or str(uuid.uuid4())
            state['delivery'] = {'status': 'sending', 'phase': 'write_started',
                                 'response_id': identity, 'client_message_id': identity}
            save_state(directory, state)
            if mode == 'crash':
                os._exit(7)
            state['delivery'].update(status='accepted', phase='admitted',
                                     observation={'status': 'observed', 'item_id': 'canonical-item'})
            save_state(directory, state)
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
        self.origin = {'transport': 'app-server', 'home': str(self.root),
                       'thread_id': str(uuid.uuid4())}
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(user_dialog, 'capture_origin', return_value=self.origin))
        patches.enter_context(patch.object(user_dialog, 'require_owner'))
        patches.enter_context(patch.object(user_dialog, 'find_python', return_value={'python': sys.executable}))
        patches.enter_context(patch.object(user_dialog, 'python_environment', side_effect=lambda _: os.environ.copy()))
        patches.enter_context(patch.object(user_dialog.subprocess, 'Popen', side_effect=self.launch))
        patches.enter_context(patch.object(user_dialog, 'print', create=True))

    def stop_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)

    def launch(self, command, **kwargs):
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertTrue(kwargs['start_new_session'])
        process = self.popen([sys.executable, str(self.renderer), command[2], str(SCRIPTS),
                              *command[3:]], **kwargs)
        self.processes.append(process)
        return process

    def args(self, name):
        request = self.root / (name + '.json')
        request.write_text(json.dumps({'title': 'Lifecycle', 'body': {
            'type': 'input', 'id': 'notes', 'label': 'Notes'}}))
        return argparse.Namespace(command='show', request=str(request), run_dir=str(self.root / name),
                                  preview=False, render_image=None, python=None)

    def wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Lifecycle did not reach its expected state')

    def test_both_clients_return_at_readiness_and_popup_survives_launcher_interruption(self):
        for transport in ('app-server', 'desktop-ipc'):
            with self.subTest(transport=transport):
                self.origin['transport'] = transport
                args = self.args(transport)
                directory = Path(args.run_dir)
                with patch.object(user_dialog, 'capture_origin', return_value=self.origin):
                    self.assertEqual(user_dialog.run_dialog(args), 0)
                self.assertIsNone(self.processes[-1].poll())
                self.assertTrue(read_state(directory)['renderer_ready'])
                (directory / 'release').write_text('accepted')
                self.processes[-1].wait(timeout=3)
                self.assertEqual(read_state(directory)['delivery']['phase'], 'admitted')

        args = self.args('interrupted')
        directory = Path(args.run_dir)
        def interrupt(directory, process):
            wait_for_renderer(directory, process)
            raise KeyboardInterrupt
        with patch.object(user_dialog, 'capture_origin', return_value=self.origin), \
             patch.object(user_dialog, 'wait_for_renderer', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                user_dialog.run_dialog(args)
        self.assertIsNone(self.processes[-1].poll())
        self.assertEqual(read_state(directory)['status'], 'open')
        (directory / 'release').write_text('accepted')
        self.processes[-1].wait(timeout=3)
        self.assertEqual(read_state(directory)['response']['values']['notes'], '  saved 한글 β\nanswer  ')

    def test_submitted_window_can_reopen_without_erasing_answer_and_confirmed_run_stays_closed(self):
        args = self.args('recover')
        directory = Path(args.run_dir)
        with patch.object(user_dialog, 'capture_origin', return_value=self.origin):
            user_dialog.run_dialog(args)
        (directory / 'release').write_text('crash')
        self.processes[-1].wait(timeout=3)
        before = read_state(directory)
        self.assertEqual(before['delivery']['phase'], 'write_started')
        (directory / 'release').unlink()
        resume = argparse.Namespace(command='resume', run_dir=str(directory), python=None)
        self.assertEqual(user_dialog.run_dialog(resume), 0)
        reopened = read_state(directory)
        self.assertEqual(reopened['status'], 'submitted')
        for key in ('message', 'response', 'draft', 'origin'):
            self.assertEqual(reopened[key], before[key])
        self.assertIsNone(self.processes[-1].poll())
        (directory / 'release').write_text('accepted')
        self.processes[-1].wait(timeout=3)
        count = len(self.processes)
        self.assertEqual(user_dialog.run_dialog(resume), 0)
        self.assertEqual(len(self.processes), count)

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
                         delivery={'status': 'sending', 'client_message_id': str(uuid.uuid4())})
            save_state(directory, state)
        process.terminate.side_effect = final_write
        with patch('dialog_lifecycle.time.monotonic', side_effect=[0, 16]):
            saved = wait_for_renderer(directory, process)
        self.assertEqual(saved['status'], 'submitted')
        self.assertEqual(saved['response']['values'], {'notes': 'new 한글 β'})
        self.assertEqual(saved['delivery']['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
