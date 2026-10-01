from __future__ import annotations

from contextlib import redirect_stdout
import argparse
import copy
import io
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
import uuid

from websockets.sync.server import unix_serve

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
import dialog_connection
import dialog_cli
from dialog_connection import capture_origin, open_connection, require_owner
from dialog_delivery import deliver, confirm_delivery
from dialog_observer import ResponseReader
from dialog_response import format_response
from dialog_state import read_state, save_state
from dialog_updates import send_update
import user_dialog


class UserDialogDeliveryTests(unittest.TestCase):
    """Exercise native discovery, subscription, input and receipts over real WS."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.socket = self.root / 'native-daemon.sock'
        self.thread_id = str(uuid.uuid4())
        self.environment = patch.dict(os.environ, {
            'CODEX_HOME': str(self.root), 'USER_DIALOG_SOCKET': str(self.root / 'ignored.sock'),
            'CODEX_THREAD_ID': self.thread_id, 'CODEX_SESSION_ID': self.thread_id,
        })
        self.environment.start()
        os.environ.pop('CODEX_APP_TOOLS_PIPE_PATH', None)
        self.addCleanup(self.environment.stop)
        discovery = patch.object(dialog_cli.subprocess, 'run', side_effect=self.discover)
        self.locator = discovery.start()
        self.addCleanup(discovery.stop)
        self.mode = 'active'
        self.active_turn = 'turn-1'
        self.guard_errors = []
        self.loaded = True
        self.server_home = str(self.root)
        self.calls, self.sends, self.persisted = [], [], []
        self.log = self.root / 'sessions' / ('rollout-native-' + self.thread_id + '.jsonl')
        self.log.parent.mkdir()
        self.log.write_text(json.dumps({'type': 'session_meta', 'payload': {
            'id': self.thread_id, 'history_mode': 'paginated'}}) + '\n')
        self.run = self.root / 'run'
        self.run.mkdir()
        self.guard = threading.Lock()
        self.server = unix_serve(self.handle, str(self.socket))
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop_server)
        wait = ResponseReader.wait
        self.short_wait = patch.object(ResponseReader, 'wait',
            lambda reader, delivery, message, timeout=60: wait(reader, delivery, message, timeout=.08))
        self.short_wait.start()
        self.addCleanup(self.short_wait.stop)

    def discover(self, command, **kwargs):
        self.assertEqual(command, ['codex', 'app-server', 'daemon', 'version'])
        self.assertTrue(kwargs['check'])
        return subprocess.CompletedProcess(command, 0, json.dumps({
            'status': 'running', 'socketPath': str(self.socket),
            'cliVersion': 'frontend', 'appServerVersion': 'backend',
        }), '')

    def stop_server(self):
        self.server.shutdown()
        self.server_thread.join(timeout=3)

    def metadata(self):
        return {'id': self.thread_id, 'name': 'Test', 'path': str(self.log),
                'historyMode': 'paginated',
                'status': {'type': 'idle' if self.mode == 'idle' else 'active'}}

    def event(self, connection, item, thread_id=None):
        connection.send(json.dumps({'method': 'item/completed', 'params': {
            'threadId': thread_id or self.thread_id, 'turnId': 'turn-1', 'item': item}}))

    def record(self, item):
        content = copy.deepcopy(item['content'])
        for part in content:
            for element in part.get('text_elements', []):
                if 'byteRange' in element:
                    element['byte_range'] = element.pop('byteRange')
        record = {'type': 'event_msg', 'payload': {
            'type': 'item_completed', 'thread_id': self.thread_id, 'turn_id': 'turn-1',
            'item': {'type': 'UserMessage', 'id': item['id'], 'client_id': item['clientId'],
                     'content': content}}}
        with self.guard, self.log.open('a') as stream:
            stream.write(json.dumps(record) + '\n')

    def handle(self, connection):
        subscribed = False
        for raw in connection:
            request = json.loads(raw)
            if 'id' not in request:
                continue
            method, params = request['method'], request['params']
            self.calls.append((method, params))
            result, error = {}, None
            if method == 'initialize':
                self.assertEqual(params, {'clientInfo': {'name': 'user_dialog', 'version': '3'},
                                          'capabilities': {'experimentalApi': True}})
                result = {'codexHome': self.server_home}
            elif method == 'thread/read':
                result = {'thread': self.metadata()}
            elif method == 'thread/loaded/list':
                result = {'data': [self.thread_id] if self.loaded else [], 'nextCursor': None}
            elif method == 'thread/resume':
                self.assertEqual(params, {'threadId': self.thread_id, 'excludeTurns': True})
                self.assertTrue(self.loaded)
                subscribed = True
                result = {'thread': self.metadata()}
            elif method == 'thread/turns/list':
                self.assertEqual(params, {'threadId': self.thread_id, 'limit': 1,
                                          'sortDirection': 'desc'})
                result = {'data': [{'id': self.active_turn, 'status': 'inProgress'}]}
            elif method == 'thread/items/list':
                error = {'code': -32601, 'message': 'Current history store does not support paging'}
            elif method in {'turn/start', 'turn/steer'}:
                self.assertTrue(subscribed)
                self.sends.append((method, params))
                self.persisted.append(read_state(self.run)['delivery'])
                if self.guard_errors:
                    error, mode, active_turn = self.guard_errors.pop(0)
                    self.mode, self.active_turn = mode, active_turn
                    connection.send(json.dumps({'id': request['id'], 'error': error}))
                    continue
                item = {'id': str(uuid.uuid4()), 'type': 'userMessage',
                        'clientId': params['clientUserMessageId'], 'content': params['input']}
                # These cannot confirm the submitted response, even with identical text.
                self.event(connection, {**item, 'id': 'other-thread'}, str(uuid.uuid4()))
                self.event(connection, {**item, 'id': 'other-client', 'clientId': str(uuid.uuid4())})
                self.event(connection, {**item, 'id': 'tool-output', 'type': 'functionCallOutput'})
                self.event(connection, {**item, 'id': 'other-text', 'content': [
                    {'type': 'text', 'text': 'Different answer', 'text_elements': []}]})
                if self.mode not in {'unrecorded', 'lost-unrecorded', 'rpc-unrecorded'}:
                    self.record(item)
                    if self.mode not in {'lost', 'rpc-invalid', 'rpc-internal', 'canonical-delayed-ack'}:
                        # The real completed item arrives before its RPC acknowledgement.
                        self.event(connection, item)
                    if self.mode in {'delayed-ack', 'canonical-delayed-ack'}:
                        deadline = time.monotonic() + 2
                        while time.monotonic() < deadline:
                            observed = read_state(self.run)['delivery'].get('observation', {})
                            if observed.get('status') == 'observed':
                                break
                            time.sleep(.01)
                        self.assertEqual(observed.get('status'), 'observed')
                if self.mode in {'lost', 'lost-unrecorded'}:
                    connection.close()
                    return
                if self.mode.startswith('rpc-'):
                    error = {'code': -32602 if self.mode == 'rpc-invalid' else -32603,
                             'message': 'RPC error after possible input admission'}
                result = ({'turnId': self.active_turn} if method == 'turn/steer' else
                          {'turn': {'id': 'turn-1', 'status': 'inProgress', 'items': []}})
            else:
                error = {'code': -32601, 'message': 'Unsupported method'}
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

    def test_native_discovery_subscription_and_ordinary_active_or_idle_input(self):
        for mode in ['active', 'idle']:
            with self.subTest(mode=mode):
                self.mode, self.sends, self.persisted = mode, [], []
                state = self.state()
                self.assertEqual(state['origin']['socket'], str(self.socket))
                self.assertEqual(state['origin']['rollout_path'], str(self.log))
                deliver(self.run, state)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                self.assertEqual(len(self.sends), 1)
                method, params = self.sends[0]
                self.assertEqual(method, 'turn/steer' if mode == 'active' else 'turn/start')
                self.assertEqual(set(params), {'threadId', 'clientUserMessageId', 'input'} |
                                 ({'expectedTurnId'} if mode == 'active' else set()))
                if mode == 'active':
                    self.assertEqual(params['expectedTurnId'], self.active_turn)
                self.assertEqual(params['input'], [state['message']])
                self.assertTrue(params['input'][0]['text_elements'])
                self.assertEqual(self.persisted[0]['status'], 'sending')
                self.assertEqual(self.persisted[0]['client_message_id'], params['clientUserMessageId'])
                self.assertNotIn('toolOutput', params)
                deliver(self.run, state)
                confirm_delivery(self.run, state)
                self.assertEqual(len(self.sends), 1)
        self.assertFalse({'thread/items/list'} &
                         {method for method, _ in self.calls})

    def test_uncertain_sends_recover_offline_without_replay_and_parallel_stale_send_is_skipped(self):
        for mode in ['lost', 'rpc-invalid', 'rpc-internal']:
            with self.subTest(mode=mode):
                self.mode, self.sends = mode, []
                state = self.state()
                deliver(self.run, state)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                self.assertEqual(len(self.sends), 1)
                for status in ['unknown', 'sending', 'accepted']:
                    state['delivery']['status'] = status
                    save_state(self.run, state)
                    recovered = read_state(self.run)
                    deliver(self.run, recovered)
                    with patch.object(dialog_cli.subprocess, 'run', side_effect=AssertionError(
                            'Confirmation must not require a running daemon')):
                        confirm_delivery(self.run, recovered)
                    self.assertEqual(recovered['delivery']['observation']['status'], 'observed')
                    self.assertEqual(len(self.sends), 1)
        for mode in ['lost-unrecorded', 'rpc-unrecorded']:
            with self.subTest(mode=mode):
                self.mode, self.sends = mode, []
                state = self.state()
                deliver(self.run, state)
                self.assertEqual(state['delivery']['status'], 'unknown')
                self.assertEqual(state['delivery']['observation']['status'], 'unconfirmed')
                deliver(self.run, state)
                confirm_delivery(self.run, state)
                self.assertEqual(len(self.sends), 1)
                self.record({'id': str(uuid.uuid4()), 'type': 'userMessage',
                             'clientId': state['delivery']['client_message_id'],
                             'content': [state['message']]})
                with patch.object(dialog_cli.subprocess, 'run', side_effect=AssertionError('Offline only')):
                    confirm_delivery(self.run, state)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                self.assertEqual(len(self.sends), 1)
        self.mode, self.sends = 'active', []
        state = self.state()
        copies = [copy.deepcopy(state), copy.deepcopy(state)]
        errors = []
        def submit(snapshot):
            try:
                deliver(self.run, snapshot)
            except Exception as error:
                errors.append(error)
        workers = [threading.Thread(target=submit, args=(snapshot,)) for snapshot in copies]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(errors, [])
        self.assertEqual(len(self.sends), 1)
        self.assertEqual(read_state(self.run)['delivery']['observation']['status'], 'observed')
        # A mutable popup mirror cannot erase the journal's admitted receipt or
        # replace its bound log path, and recovery never reconnects to send.
        missing_path = read_state(self.run)
        missing_path['delivery'].update(status='unknown', observation={})
        missing_path['origin'].pop('rollout_path')
        save_state(self.run, missing_path)
        with patch('dialog_cli.connection', side_effect=AssertionError('No attachment')):
            confirm_delivery(self.run, missing_path)
        self.assertEqual(missing_path['delivery']['observation']['status'], 'observed')
        self.assertEqual(missing_path['origin']['rollout_path'], str(self.log))
        self.assertEqual(len(self.sends), 1)

    def test_canonical_item_is_persisted_before_delayed_acknowledgement(self):
        for mode in ['delayed-ack', 'canonical-delayed-ack']:
            with self.subTest(mode=mode):
                self.mode, self.sends = mode, []
                state = self.state()
                deliver(self.run, state)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                self.assertEqual(state['delivery']['observation']['kind'], dialog_cli.kind)
                self.assertEqual(len(self.sends), 1)

    def test_steer_guards_refresh_same_origin_and_uuid_but_unknown_never_retries(self):
        for error, next_mode, next_turn in [
            ({'code': -32600, 'message': 'no active turn to steer'}, 'idle', 'turn-1'),
            ({'code': -32600, 'message': 'expected active turn id `turn-1` but found `turn-2`'},
             'active', 'turn-2'),
        ]:
            with self.subTest(error=error):
                self.mode, self.active_turn, self.sends = 'active', 'turn-1', []
                self.guard_errors = [(error, next_mode, next_turn)]
                state = self.state()
                deliver(self.run, state)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                self.assertEqual([method for method, _ in self.sends],
                                 ['turn/steer', 'turn/start' if next_mode == 'idle' else 'turn/steer'])
                self.assertEqual(len({params['clientUserMessageId'] for _, params in self.sends}), 1)
                self.assertEqual({params['threadId'] for _, params in self.sends}, {self.thread_id})
                if next_mode == 'active':
                    self.assertEqual(self.sends[-1][1]['expectedTurnId'], 'turn-2')
        self.mode, self.active_turn, self.sends = 'active', 'turn-1', []
        guard = {'code': -32600, 'message': 'no active turn to steer'}
        self.guard_errors = [(guard, 'active', 'turn-1')] * 4
        state = self.state()
        deliver(self.run, state)
        self.assertEqual(state['delivery']['status'], 'failed')
        self.assertEqual(len(self.sends), 3)
        self.assertEqual(len(self.guard_errors), 1)

    def test_definite_guard_is_saved_before_interrupted_refresh_and_can_resume(self):
        self.guard_errors = [({'code': -32600, 'message': 'no active turn to steer'},
                              'idle', 'turn-1')]
        state = self.state()
        active_turn = dialog_cli.AppServer._active_turn
        reads = []
        def interrupted_refresh(server):
            reads.append(True)
            if len(reads) == 2:
                saved = read_state(self.run)['delivery']
                self.assertEqual((saved['status'], saved['phase']), ('pending', 'prepared'))
                raise KeyboardInterrupt('Sender stopped during metadata refresh')
            return active_turn(server)
        with patch.object(dialog_cli.AppServer, '_active_turn', interrupted_refresh):
            with self.assertRaisesRegex(KeyboardInterrupt, 'metadata refresh'):
                deliver(self.run, state)
        saved = read_state(self.run)
        self.assertEqual((saved['delivery']['status'], saved['delivery']['phase']),
                         ('pending', 'prepared'))
        self.assertEqual(len(self.sends), 1)
        original_id = self.sends[0][1]['clientUserMessageId']
        deliver(self.run, saved)
        self.assertEqual([method for method, _ in self.sends], ['turn/steer', 'turn/start'])
        self.assertEqual(self.sends[1][1]['clientUserMessageId'], original_id)
        self.assertEqual(saved['delivery']['observation']['status'], 'observed')

    def test_preflight_binding_rejects_unloaded_changed_home_or_endpoint_and_never_falls_back(self):
        state = self.state()
        count = len([method for method, _ in self.calls if method == 'thread/resume'])
        self.loaded = False
        deliver(self.run, state)
        self.assertEqual(state['delivery']['status'], 'failed')
        self.assertEqual(read_state(self.run)['draft'], {'notes': 'Retain me'})
        self.assertEqual(len([method for method, _ in self.calls if method == 'thread/resume']), count)
        self.loaded = True
        self.server_home = str(self.root / 'different-home')
        with self.assertRaisesRegex(ValueError, 'different Codex home'):
            with open_connection(state['origin']):
                pass
        self.server_home = str(self.root)
        different_path = copy.deepcopy(state['origin'])
        different_path['rollout_path'] = str(self.root / 'different.jsonl')
        with self.assertRaisesRegex(ValueError, 'conversation log changed'):
            with open_connection(different_path):
                pass
        with patch.object(dialog_cli.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, json.dumps({'status': 'running', 'socketPath': str(self.root / 'other.sock')}), '')):
            require_owner(state['origin'])  # Pure identity checks remain available offline.
            with self.assertRaisesRegex(ValueError, 'endpoint changed'):
                with open_connection(state['origin']):
                    pass
        before = self.locator.call_count
        with patch.dict(os.environ, {'CODEX_APP_TOOLS_PIPE_PATH': ''}), \
             patch('dialog_desktop.DesktopIpc', side_effect=ValueError('Desktop owner unavailable')):
            with self.assertRaisesRegex(ValueError, 'Missing inherited Desktop tools connection'):
                capture_origin()
        self.assertEqual(self.locator.call_count, before)
        self.assertEqual(self.sends, [])

    def test_wrong_role_identity_text_and_nonordinary_local_inputs_cannot_confirm_or_send(self):
        self.mode = 'unrecorded'
        state = self.state()
        deliver(self.run, state)
        self.assertEqual(state['delivery']['status'], 'accepted')
        self.assertEqual(state['delivery']['observation']['status'], 'unconfirmed')
        with open_connection(state['origin']) as server:
            for message, client_id in [({'type': 'toolOutput', 'text': 'Wrong role'}, str(uuid.uuid4())),
                                       (state['message'], 'invalid-identity'),
                                       ([state['message']], str(uuid.uuid4()))]:
                with self.assertRaises(ValueError):
                    server.submit_user_message(message, client_id)
        self.assertEqual(len(self.sends), 1)

        # Live CLI receipts do not depend on canonical logfile persistence.
        self.log.write_text(json.dumps({'type': 'session_meta', 'payload': {
            'id': self.thread_id, 'history_mode': 'legacy'}}) + '\n')
        self.mode = 'active'
        legacy = self.state()
        deliver(self.run, legacy)
        self.assertEqual(legacy['delivery']['observation']['status'], 'observed')
        confirmed = copy.deepcopy(legacy['delivery'])
        confirm_delivery(self.run, legacy)
        self.assertEqual(legacy['delivery'], confirmed)

    def test_drafts_resume_in_place_updates_require_origin_and_preserve_invalid_draft(self):
        state = self.state()
        state.update(status='dismissed', base=str(self.root), response={}, revision=0,
                     spec={'title': 'Draft', 'body': {'type': 'input', 'id': 'notes', 'label': 'Notes'}})
        save_state(self.run, state)
        def launch(command, **kwargs):
            current = read_state(self.run)
            current.update(status='open', renderer_ready=True)
            save_state(self.run, current)
            return Mock(poll=lambda: None)
        with patch.object(user_dialog, 'find_python', return_value={'python': sys.executable}), \
             patch.object(user_dialog, 'python_environment', return_value={}), \
             patch.object(user_dialog.subprocess, 'Popen', side_effect=launch), redirect_stdout(io.StringIO()):
            user_dialog.run_dialog(argparse.Namespace(command='resume', run_dir=str(self.run), python=None))
        resumed = read_state(self.run)
        self.assertEqual(resumed['draft'], state['draft'])
        self.assertEqual(resumed['base'], str(self.root))
        self.assertEqual(send_update(self.run, resumed['spec'], timeout=0)['status'], 'queued')
        for overrides in [{'CODEX_THREAD_ID': str(uuid.uuid4())},
                          {'CODEX_SESSION_ID': str(uuid.uuid4())},
                          {'CODEX_HOME': str(self.root / 'other-home')},
                          {'CODEX_APP_TOOLS_PIPE_PATH': 'different-host'}]:
            with self.subTest(overrides=overrides), patch.dict(os.environ, overrides):
                with self.assertRaises(ValueError):
                    require_owner(resumed['origin'])
                with self.assertRaises(ValueError):
                    send_update(self.run, {}, timeout=0)
        resumed.update(status='dismissed', draft={'n': '-'}, spec={'title': 'Count', 'body': {
            'type': 'group', 'enabled_when': {'not': {'ref': 'n', 'equals': 0}},
            'children': [{'type': 'input', 'id': 'n', 'label': 'Count',
                          'format': 'number', 'required': True, 'value': 1}]}})
        save_state(self.run, resumed)
        original = (self.run / 'state.json').read_bytes()
        with patch.object(user_dialog, 'find_python') as renderer:
            with self.assertRaisesRegex(ValueError, 'own field or descendant'):
                user_dialog.run_dialog(argparse.Namespace(command='resume', run_dir=str(self.run), python=None))
        renderer.assert_not_called()
        self.assertEqual((self.run / 'state.json').read_bytes(), original)
        self.assertEqual(self.sends, [])


if __name__ == '__main__':
    unittest.main()
