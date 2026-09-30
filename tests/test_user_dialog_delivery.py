from __future__ import annotations

from contextlib import redirect_stdout
import argparse
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

from websockets.sync.server import unix_serve

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
from dialog_connection import capture_origin, require_owner
from dialog_delivery import deliver, confirm_delivery
from dialog_response import format_response
from dialog_state import read_state, save_state
from dialog_updates import send_update
import user_dialog


class UserDialogDeliveryTests(unittest.TestCase):
    """Exercise the actual Unix/WebSocket client against a deterministic server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.socket = self.root / 'server.sock'
        self.thread_id = str(uuid.uuid4())
        self.environment = patch.dict(os.environ, {
            'CODEX_HOME': str(self.root), 'USER_DIALOG_SOCKET': str(self.socket),
            'CODEX_THREAD_ID': self.thread_id, 'CODEX_SESSION_ID': self.thread_id,
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.mode = 'active'
        self.loaded = True
        self.calls = []
        self.sends = []
        self.history = [{'turnId': 'turn-1', 'item': {'id': 'boundary', 'type': 'agentMessage', 'text': 'Ready'}}]
        self.persisted = []
        self.run = self.root / 'run'
        self.run.mkdir()
        self.server = unix_serve(self.handle, str(self.socket))
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server_thread.join(timeout=3)

    def handle(self, connection):
        for raw in connection:
            request = json.loads(raw)
            if 'id' not in request:
                continue
            method, params = request['method'], request['params']
            self.calls.append(method)
            result, error = {}, None
            if method == 'thread/read':
                result = {'thread': {'id': self.thread_id, 'name': 'Test'}}
            elif method == 'thread/loaded/list':
                result = {'data': [self.thread_id] if self.loaded else [], 'nextCursor': None}
            elif method == 'thread/turns/list':
                result = {'data': [{'id': 'turn-1', 'status': 'completed' if self.mode == 'idle' else 'inProgress'}]}
            elif method == 'thread/items/list':
                start = int(params.get('cursor', 0))
                end = start + params['limit']
                result = {'data': self.history[start:end],
                          'nextCursor': str(end) if end < len(self.history) else None}
            elif method in {'turn/steer', 'turn/start'}:
                self.sends.append((method, params))
                self.persisted.append(read_state(self.run)['delivery'])
                if self.mode == 'race':
                    self.mode = 'idle'
                    error = {'code': -32600, 'message': 'No active turn to steer'}
                elif self.mode == 'reject':
                    error = {'code': -32602, 'message': 'Invalid input'}
                else:
                    item = {'id': str(uuid.uuid4()), 'type': 'userMessage',
                            'clientId': params['clientUserMessageId'], 'content': params['input']}
                    if self.mode == 'unstyled':
                        item['content'] = [{'type': 'text', 'text': params['input'][0]['text']}]
                    self.history.insert(0, {'turnId': 'turn-1', 'item': item})
                    # Include an identical answer with a different ID and enough
                    # newer items to require paging during confirmation.
                    self.history.insert(0, {'turnId': 'turn-1', 'item': {
                        **item, 'id': 'other-message', 'clientId': str(uuid.uuid4())}})
                    for n in range(101):
                        self.history.insert(0, {'turnId': 'turn-1', 'item': {
                            'id': str(uuid.uuid4()), 'type': 'agentMessage', 'text': 'Progress'}})
                    if self.mode == 'lost':
                        connection.close()
                        return
                    result = {'turnId': 'turn-1'} if method == 'turn/steer' else {'turn': {'id': 'turn-1'}}
                    if self.mode == 'internal-error':
                        error = {'code': -32603, 'message': 'Internal error after write'}
            elif method != 'initialize':
                error = {'code': -32601, 'message': 'Unknown method'}
            connection.send(json.dumps({'method': 'test/notification', 'params': {}}))
            connection.send(json.dumps({'id': request['id'], 'error': error} if error else
                                       {'id': request['id'], 'result': result}))

    def state(self):
        origin = capture_origin()
        message = format_response({'title': '응답', 'body': {'type': 'input', 'id': 'notes', 'label': '의견'}},
                                  {'notes': 'Original answer\n한글 그대로\n'}, '확인')
        state = {'version': 3, 'request_id': str(uuid.uuid4()), 'status': 'submitted',
                 'origin': origin, 'message': message,
                 'delivery': {'status': 'pending'}, 'draft': {'notes': 'Retain me'}}
        save_state(self.run, state)
        return read_state(self.run)

    def test_active_idle_and_turn_completion_during_submission(self):
        for mode, expected in [('active', ['turn/steer']), ('idle', ['turn/start']),
                               ('race', ['turn/steer', 'turn/start']), ('unstyled', ['turn/steer'])]:
            with self.subTest(mode=mode):
                self.mode, self.sends, self.persisted = mode, [], []
                state = self.state()
                deliver(self.run, state)
                self.assertEqual([method for method, _ in self.sends], expected)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                for (_, params), saved in zip(self.sends, self.persisted):
                    self.assertEqual(saved['status'], 'sending')
                    self.assertEqual(saved['client_message_id'], params['clientUserMessageId'])
                    self.assertEqual(params['input'], [read_state(self.run)['message']])
                    self.assertTrue(params['input'][0]['text_elements'])
                    self.assertNotIn('toolOutput', params)
                if mode == 'race':
                    self.assertEqual(self.sends[0][1]['clientUserMessageId'], self.sends[1][1]['clientUserMessageId'])
                count = len(self.sends)
                deliver(self.run, state)
                confirm_delivery(self.run, state)
                self.assertEqual(len(self.sends), count)

    def test_lost_ack_and_interrupted_sending_confirm_without_replay(self):
        for mode in ['lost', 'internal-error']:
            with self.subTest(mode=mode):
                self.mode, self.sends = mode, []
                state = self.state()
                deliver(self.run, state)
                self.assertEqual(state['delivery']['status'], 'unknown')
                self.assertEqual(len(self.sends), 1)
                for status in ['unknown', 'sending', 'accepted']:
                    state['delivery']['status'] = status
                    save_state(self.run, state)
                    recovered = read_state(self.run)
                    deliver(self.run, recovered)
                    confirm_delivery(self.run, recovered)
                    self.assertEqual(recovered['delivery']['observation']['status'], 'observed')
                    self.assertEqual(len(self.sends), 1)

    def test_rejected_submission_can_retry_and_connection_failure_preserves_answer(self):
        self.mode = 'reject'
        state = self.state()
        deliver(self.run, state)
        self.assertEqual(state['delivery']['status'], 'failed')
        message_id = state['delivery']['client_message_id']
        self.mode = 'active'
        deliver(self.run, state)
        self.assertEqual(state['delivery']['client_message_id'], message_id)
        self.assertEqual(state['delivery']['observation']['status'], 'observed')
        state = self.state()
        self.loaded = False
        deliver(self.run, state)
        self.assertEqual(state['delivery']['status'], 'failed')
        self.assertEqual(read_state(self.run)['draft'], {'notes': 'Retain me'})
        self.assertEqual(len(self.sends), 2)
        self.assertNotIn('thread/resume', self.calls)

    def test_drafts_resume_in_place_and_accept_updates(self):
        state = self.state()
        state.update(status='dismissed', base=str(self.root), response={}, revision=0,
                     spec={'title': 'Draft', 'body': {'type': 'input', 'id': 'notes', 'label': 'Notes'}})
        save_state(self.run, state)
        def launch(command, **kwargs):
            current = read_state(self.run)
            current['status'] = 'open'
            save_state(self.run, current)
            return Mock(poll=lambda: None)
        with patch.object(user_dialog, 'find_python', return_value={'python': sys.executable}), \
             patch.object(user_dialog, 'python_environment', return_value={}), \
             patch.object(user_dialog.subprocess, 'Popen', side_effect=launch), redirect_stdout(io.StringIO()):
            user_dialog.run_dialog(argparse.Namespace(command='resume', run_dir=str(self.run), python=None))
        resumed = read_state(self.run)
        self.assertEqual(resumed['origin']['transport'], 'app-server')
        self.assertEqual(resumed['draft'], state['draft'])
        self.assertEqual(resumed['base'], str(self.root))
        update = send_update(self.run, resumed['spec'], timeout=0)
        self.assertEqual(update['status'], 'queued')
        self.assertEqual(self.sends, [])

    def test_owner_and_endpoint_checks_apply_to_updates_and_recovery(self):
        state = self.state()
        state.update(status='open', base=str(self.root), revision=0)
        save_state(self.run, state)
        for overrides in [{'CODEX_THREAD_ID': str(uuid.uuid4())},
                          {'USER_DIALOG_SOCKET': str(self.root / 'other.sock')}]:
            with self.subTest(overrides=overrides), patch.dict(os.environ, overrides):
                with self.assertRaises(ValueError):
                    require_owner(state['origin'])
                with self.assertRaises(ValueError):
                    send_update(self.run, {}, timeout=0)
                submitted = copy.deepcopy(state)
                submitted['status'] = 'submitted'
                deliver(self.run, submitted)
                self.assertEqual(submitted['delivery']['status'], 'failed')
        self.assertEqual(self.sends, [])

    def test_unsafe_legacy_conditions_preserve_the_draft_without_opening_a_window(self):
        state = self.state()
        state.update(status='dismissed', base=str(self.root), response={}, revision=0,
                     draft={'n': '-'}, spec={'title': 'Count', 'body': {
                         'type': 'group', 'enabled_when': {'not': {'ref': 'n', 'equals': 0}},
                         'children': [{'type': 'input', 'id': 'n', 'label': 'Count',
                                       'format': 'number', 'required': True, 'value': 1}]}})
        save_state(self.run, state)
        original = (self.run / 'state.json').read_bytes()
        with patch.object(user_dialog, 'find_python') as renderer:
            with self.assertRaisesRegex(ValueError, 'own field or descendant'):
                user_dialog.run_dialog(argparse.Namespace(command='resume', run_dir=str(self.run), python=None))
        renderer.assert_not_called()
        self.assertEqual((self.run / 'state.json').read_bytes(), original)
        self.assertEqual(self.sends, [])


if __name__ == '__main__':
    unittest.main()
