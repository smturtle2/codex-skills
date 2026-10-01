from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import threading
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
from dialog_connection import capture_origin, open_connection
from dialog_delivery import DeliveryAttempt, confirm_delivery, deliver
from dialog_journal import SubmissionJournal
from dialog_observer import ResponseReader, RolloutToolResponseReader
from dialog_response import format_response
from dialog_state import read_state, save_state
import dialog_connection
import dialog_desktop


def receive_frame(connection):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            part = connection.recv(size - len(data))
            if not part:
                raise EOFError
            data.extend(part)
        return data
    size, = struct.unpack('<I', exact(4))
    if not 0 < size < 4 * 1024 * 1024:
        raise ValueError('Invalid fixture frame')
    return json.loads(exact(size))


def send_frame(connection, packet, lock):
    encoded = json.dumps(packet, ensure_ascii=False).encode()
    wire = struct.pack('<I', len(encoded)) + encoded
    with lock:
        # Split the length header and Unicode-bearing payload on real sockets.
        for start, end in [(0, 1), (1, 3), (3, 8), (8, len(wire))]:
            connection.sendall(wire[start:end])


class FramedBroker:
    """A real socket broker routing a freshly initialized helper to an owner."""

    def __init__(self, path):
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        self.listener.listen()
        self.clients, self.routes, self.requests, self.errors = {}, {}, [], []
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.owner_id = None
        self.workers = []
        self.acceptor = threading.Thread(target=self.accept, daemon=True)
        self.acceptor.start()

    def accept(self):
        while not self.closed.is_set():
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            worker = threading.Thread(target=self.serve, args=(connection,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def send(self, client_id, packet):
        with self.lock:
            peer = self.clients.get(client_id)
        if peer:
            send_frame(peer[0], packet, peer[1])

    def serve(self, connection):
        client_id = None
        try:
            request = receive_frame(connection)
            if request['method'] != 'initialize' or request['version'] != 0:
                raise ValueError('Expected native initialization')
            client_id = str(uuid.uuid4())
            with self.lock:
                self.clients[client_id] = connection, threading.Lock()
                self.requests.append(request)
                if request['params']['clientType'] == 'test-owner':
                    self.owner_id = client_id
            self.send(client_id, {'type': 'response', 'requestId': request['requestId'],
                'method': 'initialize', 'resultType': 'success', 'result': {'clientId': client_id}})
            while True:
                packet = receive_frame(connection)
                with self.lock:
                    self.requests.append(copy.deepcopy(packet))
                if packet['type'] == 'request':
                    with self.lock:
                        self.routes[packet['requestId']] = client_id
                    if packet['method'] == 'thread-owner-discovery':
                        self.send(client_id, {'type': 'client-discovery-request',
                            'requestId': packet['requestId'], 'request': packet})
                    self.send(packet.get('targetClientId', self.owner_id), packet)
                elif packet['type'] == 'response':
                    with self.lock:
                        target = self.routes.pop(packet['requestId'], None)
                    self.send(target, packet)
                elif packet['type'] == 'broadcast':
                    targets = packet.get('targetClientIds')
                    if targets is None:
                        with self.lock:
                            targets = [target for target in self.clients if target != client_id]
                    for target in targets:
                        self.send(target, packet)
        except (EOFError, ConnectionError, OSError):
            pass
        except Exception as error:
            self.errors.append(error)
        finally:
            with self.lock:
                self.clients.pop(client_id, None)
            connection.close()

    def disconnect(self, client_id):
        with self.lock:
            peer = self.clients.get(client_id)
        if peer:
            try:
                peer[0].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            peer[0].close()

    def close(self):
        self.closed.set()
        try:
            self.listener.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.listener.close()
        with self.lock:
            clients = list(self.clients)
        for client_id in clients:
            self.disconnect(client_id)
        for worker in self.workers:
            worker.join(timeout=1)
        self.acceptor.join(timeout=1)


class DesktopOwner:
    """Own native metadata only; the tool gateway owns all input admission."""

    def __init__(self, broker, path, thread_id, rollout):
        self.broker, self.thread_id, self.rollout = broker, thread_id, rollout
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.connect(str(path))
        self.lock = threading.Lock()
        send_frame(self.connection, {'type': 'request', 'requestId': 'owner-init',
            'method': 'initialize', 'version': 0, 'params': {'clientType': 'test-owner'}}, self.lock)
        self.client_id = receive_frame(self.connection)['result']['clientId']
        self.owner_id, self.snapshot_id, self.snapshot_path = self.client_id, thread_id, str(rollout)
        self.calls, self.errors = [], []
        self.worker = threading.Thread(target=self.serve, daemon=True)
        self.worker.start()

    def send(self, packet):
        send_frame(self.connection, packet, self.lock)

    def snapshot(self, target):
        packet = {'type': 'broadcast', 'method': 'thread-stream-state-changed',
            'sourceClientId': self.client_id, 'targetClientIds': [target], 'params': {
                'hostId': 'local', 'conversationId': self.thread_id, 'change': {
                    'type': 'snapshot', 'conversationState': {
                        'id': self.snapshot_id, 'title': 'Desktop test', 'rolloutPath': self.snapshot_path,
                        'cwd': str(self.rollout.parent), 'turns': 'UI history is not a receipt'}}}}
        self.send({**packet, 'sourceClientId': str(uuid.uuid4())})
        self.send({**packet, 'targetClientIds': [str(uuid.uuid4())]})
        self.send(packet)

    def serve(self):
        try:
            while True:
                request = receive_frame(self.connection)
                self.calls.append(request)
                if request['method'] == 'thread-owner-discovery':
                    self.send({'type': 'response', 'requestId': request['requestId'],
                        'method': request['method'], 'handledByClientId': self.owner_id,
                        'resultType': 'success', 'result': {'supportsUntrustedAppInput': True}})
                elif request['method'] == 'thread-stream-following-changed':
                    self.snapshot(request['sourceClientId'])
                else:
                    raise ValueError('Input must not use native follower IPC: ' + request['method'])
        except (EOFError, ConnectionError, OSError):
            pass
        except Exception as error:
            self.errors.append(error)

    def close(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()
        self.worker.join(timeout=1)


class ToolsGateway:
    """Use a real framed pipe and persist the delegated canonical input."""

    def __init__(self, path, thread_id, rollout):
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        self.listener.listen()
        self.thread_id, self.rollout = thread_id, rollout
        self.active_turn = str(uuid.uuid4())
        self.mode = 'normal'
        self.calls, self.sends, self.persisted, self.errors = [], [], [], []
        self.run = None
        self.commit_gate = threading.Event()
        self.ack_ready = threading.Event()
        self.closed = threading.Event()
        self.peers, self.workers = [], []
        self.acceptor = threading.Thread(target=self.accept, daemon=True)
        self.acceptor.start()

    def accept(self):
        while not self.closed.is_set():
            try:
                peer, _ = self.listener.accept()
            except OSError:
                return
            self.peers.append(peer)
            worker = threading.Thread(target=self.serve, args=(peer,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def record(self, prompt, source=None, item_id=None, turn_id=None, namespace='codex_app'):
        root = ET.Element('codex_delegation')
        ET.SubElement(root, 'source_thread_id').text = source or self.thread_id
        ET.SubElement(root, 'input').text = prompt
        item_id = item_id or 'fco_' + str(uuid.uuid4())
        record = {'type': 'response_item', 'payload': {
            'type': 'function_call_output', 'id': item_id,
            'namespace': namespace, 'name': 'send_message_to_thread',
            'output': ET.tostring(root, encoding='unicode'),
            'internal_chat_message_metadata_passthrough': {'turn_id': turn_id or self.active_turn}}}
        wire = (json.dumps(record, ensure_ascii=False) + '\n').encode()
        with self.rollout.open('ab') as stream:
            stream.write(wire)
        return item_id, wire

    def serve(self, peer):
        try:
            request = receive_frame(peer)
            self.calls.append(request)
            if request['method'] == 'tools/list':
                result = {'tools': [{'name': 'send_message_to_thread', 'namespace': 'codex_app'}]}
            elif request['method'] == 'tools/call':
                self.sends.append(request)
                params = request['params']
                self.persisted.append(read_state(self.run)['delivery'])
                if self.active_turn is None:
                    self.active_turn = str(uuid.uuid4())
                if self.mode not in {'ack-before-commit', 'unrecorded'}:
                    self.item_id, _ = self.record(params['arguments']['prompt'])
                if self.mode == 'lost':
                    return
                if self.mode == 'error':
                    send_frame(peer, {'jsonrpc': '2.0', 'id': request['id'],
                        'error': {'code': -32000, 'message': 'Tool failed after possible admission'}}, threading.Lock())
                    return
                if self.mode == 'delayed-ack':
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        observed = read_state(self.run)['delivery'].get('observation', {})
                        if observed.get('status') == 'observed':
                            break
                        time.sleep(.01)
                    if observed.get('status') != 'observed':
                        raise AssertionError('Canonical admission was not saved before delayed ACK')
                    self.ack_ready.set()
                result = {'success': True, 'contentItems': [
                    {'type': 'inputText', 'text': json.dumps({'threadId': self.thread_id})}]}
            else:
                raise ValueError('Unexpected app-tools method')
            send_frame(peer, {'jsonrpc': '2.0', 'id': request['id'], 'result': result}, threading.Lock())
            if self.mode == 'ack-before-commit' and request['method'] == 'tools/call':
                self.ack_ready.set()
                if not self.commit_gate.wait(3):
                    raise AssertionError('Fixture commit gate timed out')
                self.item_id, _ = self.record(request['params']['arguments']['prompt'])
        except (EOFError, ConnectionError, OSError):
            pass
        except Exception as error:
            self.errors.append(error)
        finally:
            peer.close()

    def close(self):
        self.closed.set()
        self.commit_gate.set()
        try:
            self.listener.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.listener.close()
        for peer in self.peers:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for worker in self.workers:
            worker.join(timeout=3)
        self.acceptor.join(timeout=1)


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'Desktop IPC uses local Unix sockets')
class UserDialogDesktopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.socket = self.root / 'ipc/ipc.sock'
        self.socket.parent.mkdir()
        self.pipe = self.root / 'tools.sock'
        self.run = self.root / 'run'
        self.run.mkdir()
        self.thread_id, self.source_turn = str(uuid.uuid4()), str(uuid.uuid4())
        self.rollout = self.root / 'sessions' / (self.thread_id + '.jsonl')
        self.rollout.parent.mkdir()
        self.rollout.write_text(json.dumps({'type': 'session_meta',
            'payload': {'id': self.thread_id, 'history_mode': 'paginated'}}) + '\n' +
            json.dumps({'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': self.source_turn}}) + '\n')
        environment = patch.dict(os.environ, {'CODEX_HOME': str(self.root), 'CODEX_THREAD_ID': self.thread_id,
            'CODEX_SESSION_ID': self.thread_id, 'CODEX_APP_TOOLS_PIPE_PATH': str(self.pipe)})
        environment.start()
        os.environ.pop('CODEX_TURN_ID', None)
        self.addCleanup(environment.stop)
        self.broker = FramedBroker(self.socket)
        self.owner = DesktopOwner(self.broker, self.socket, self.thread_id, self.rollout)
        self.gateway = ToolsGateway(self.pipe, self.thread_id, self.rollout)
        self.gateway.run = self.run
        self.addCleanup(self.stop)
        wait = ResponseReader.wait
        short_wait = patch.object(ResponseReader, 'wait',
            lambda reader, delivery, message, timeout=60: wait(reader, delivery, message, timeout=.08))
        short_wait.start()
        self.addCleanup(short_wait.stop)

    def stop(self):
        self.gateway.close()
        self.owner.close()
        self.broker.close()
        self.assertEqual(self.owner.errors + self.broker.errors + self.gateway.errors, [])

    def state(self, *, markdown=True):
        message = format_response({'title': '검토', 'body': {'type': 'input', 'id': 'notes', 'label': '의견'}},
            {'notes': '  Original <answer> & **body**\r\n한글 🧑🏽‍💻\n'}, '확인', markdown=markdown)
        state = {'version': 3, 'request_id': str(uuid.uuid4()), 'status': 'submitted',
            'origin': capture_origin(), 'message': message, 'delivery': {'status': 'pending'},
            'draft': {'notes': 'Retain the editable answer'}}
        save_state(self.run, state)
        return state

    def test_native_metadata_and_public_bridge_preserve_origin_and_exact_body(self):
        state = self.state()
        message = copy.deepcopy(state['message'])
        self.assertEqual(state['origin']['source_turn_id'], self.source_turn)
        self.assertEqual(self.gateway.sends, [])
        deliver(self.run, state)
        request, = self.gateway.sends
        params = request['params']
        self.assertEqual((params['callerSource'], params['namespace'], params['tool']),
                         ('codex', 'codex_app', 'send_message_to_thread'))
        self.assertEqual((params['threadId'], params['hostId'], params['turnId']),
                         (self.thread_id, 'local', self.source_turn))
        self.assertEqual(params['arguments'], {'threadId': self.thread_id, 'hostId': 'local',
                                              'prompt': state['message']['text']})
        self.assertEqual(read_state(self.run)['message'], message)
        snapshot = SubmissionJournal(state['origin']).load(state['delivery']['response_id'])[1]
        self.assertEqual(snapshot['message'], message)
        self.assertEqual(params['callId'], state['delivery']['client_message_id'])
        uuid.UUID(request['id'])
        self.assertEqual(self.gateway.persisted[0]['status'], 'sending')
        self.assertIn('fence', self.gateway.persisted[0])
        self.assertEqual(state['delivery']['observation'], {'status': 'observed',
            'item_id': self.gateway.item_id, 'turn_id': self.gateway.active_turn,
            'kind': 'desktop_tool_output'})
        self.assertEqual({call['method'] for call in self.owner.calls},
                         {'thread-owner-discovery', 'thread-stream-following-changed'})
        self.assertTrue(all(packet['response'] == {'canHandle': False}
            for packet in self.broker.requests if packet['type'] == 'client-discovery-response'))
        deliver(self.run, state)
        confirm_delivery(self.run, state)
        self.assertEqual(len(self.gateway.sends), 1)

    def test_detached_origin_and_app_owned_idle_or_active_admission(self):
        state = self.state()
        with self.rollout.open("a") as stream:
            stream.write(json.dumps({"type": "event_msg", "payload": {
                "type": "task_complete", "turn_id": self.source_turn}}) + "\n")
        self.gateway.active_turn = None
        # A completed source turn and an idle target do not cancel the popup.
        deliver(self.run, state)
        self.assertEqual(state['delivery']['observation']['status'], 'observed')
        target_turn = self.gateway.active_turn
        first_item = state['delivery']['observation']['item_id']
        # The same exact text in a later popup is new input, not the first receipt.
        state = self.state()
        deliver(self.run, state)
        self.assertEqual(state['delivery']['observation']['turn_id'], target_turn)
        self.assertNotEqual(state['delivery']['observation']['item_id'], first_item)
        self.assertEqual(len(self.gateway.sends), 2)

    def test_canonical_admission_closes_before_delayed_or_lost_ack(self):
        for mode in ['delayed-ack', 'lost', 'error']:
            with self.subTest(mode=mode):
                self.gateway.mode = mode
                state = self.state()
                before = len(self.gateway.sends)
                deliver(self.run, state)
                self.assertEqual(state['delivery']['observation']['status'], 'observed')
                confirm_delivery(self.run, state)
                self.assertEqual(len(self.gateway.sends), before + 1)
                if mode == 'delayed-ack':
                    self.assertTrue(self.gateway.ack_ready.wait(1))

    def test_ack_is_not_receipt_and_offline_recovery_does_not_replay(self):
        self.gateway.mode = 'ack-before-commit'
        # Already submitted Desktop messages retain the earlier native format.
        state = self.state(markdown=False)
        message = copy.deepcopy(state['message'])
        deliver(self.run, state)
        self.assertTrue(self.gateway.ack_ready.wait(1))
        self.assertEqual(state['delivery']['status'], 'accepted')
        self.assertEqual(state['delivery']['observation']['status'], 'unconfirmed')
        self.gateway.commit_gate.set()
        deadline = time.monotonic() + 2
        while not hasattr(self.gateway, 'item_id') and time.monotonic() < deadline:
            time.sleep(.01)
        self.owner.close()
        self.gateway.close()
        with patch('dialog_desktop.connection', side_effect=AssertionError('No reconnect')), \
             patch('dialog_desktop.Bridge', side_effect=AssertionError('No tools call')):
            deliver(self.run, state)
            confirm_delivery(self.run, state)
        self.assertEqual(state['delivery']['observation']['status'], 'observed')
        self.assertEqual(state['message'], message)
        self.assertEqual(len(self.gateway.sends), 1)
        # A pre-bridge uncertain USER attempt keeps its original correlation
        # even after the app is unavailable; it must not become a tool send.
        legacy_run = self.root / 'legacy-run'
        legacy_run.mkdir()
        client_id = str(uuid.uuid4())
        legacy = {**copy.deepcopy(state), 'request_id': str(uuid.uuid4()),
                  'delivery': {'status': 'unknown', 'client_message_id': client_id}}
        save_state(legacy_run, legacy)
        with self.rollout.open('a') as stream:
            stream.write(json.dumps({'type': 'event_msg', 'payload': {
                'type': 'item_completed', 'thread_id': self.thread_id, 'turn_id': self.source_turn,
                'item': {'type': 'UserMessage', 'id': 'legacy-user-item', 'client_id': client_id,
                         'content': [legacy['message']]}}}) + '\n')
        with patch('dialog_desktop.Bridge', side_effect=AssertionError('No replay')):
            confirm_delivery(legacy_run, legacy)
        self.assertEqual(legacy['delivery']['observation']['item_id'], 'legacy-user-item')
        self.assertEqual(legacy['message'], message)
        self.assertEqual(len(self.gateway.sends), 1)

    def test_saved_boundary_excludes_existing_partial_and_unrelated_inputs(self):
        state = self.state()
        reader = RolloutToolResponseReader(state['origin'])
        existing, _ = self.gateway.record(state['message']['text'])
        fence = reader.capture_fence()
        delivery = {'client_message_id': str(uuid.uuid4()), 'fence': fence}
        self.assertIn(existing, fence['previous_item_ids'])
        self.gateway.record(state['message']['text'], source=str(uuid.uuid4()))
        self.gateway.record('Different body')
        self.gateway.record(state['message']['text'], namespace='another_tool')
        self.assertIsNone(reader.find_response(delivery, state['message']['text']))
        actual, _ = self.gateway.record(state['message']['text'])
        self.assertEqual(reader.find_response(delivery, state['message']['text'])['item_id'], actual)
        other = RolloutToolResponseReader(state['origin'])
        next_fence = other.capture_fence()
        # A canonical record with split UTF-8 cannot be parsed until complete.
        _, wire = self.gateway.record(state['message']['text'])
        with self.rollout.open('r+b') as stream:
            boundary = stream.seek(0, os.SEEK_END) - len(wire)
            stream.truncate(boundary)
            stream.seek(boundary)
            split = wire.index('🧑'.encode()) + 1
            stream.write(wire[:split])
        partial_reader = RolloutToolResponseReader(state['origin'])
        partial_fence = partial_reader.capture_fence()
        with self.rollout.open('ab') as stream:
            stream.write(wire[split:])
        partial_delivery = {'client_message_id': str(uuid.uuid4()), 'fence': partial_fence}
        self.assertIsNone(partial_reader.find_response(partial_delivery, state['message']['text']))
        self.assertIsNotNone(other.find_response({'client_message_id': str(uuid.uuid4()),
                                                'fence': next_fence}, state['message']['text']))
        self.gateway.record(state['message']['text'])
        with self.assertRaisesRegex(ValueError, 'Multiple'):
            reader.find_response(delivery, state['message']['text'])

    def test_saved_log_rotation_and_wrong_origin_fail_closed_before_send(self):
        state = self.state()
        reader = RolloutToolResponseReader(state['origin'])
        fence = reader.capture_fence()
        replacement = self.rollout.with_suffix('.replacement')
        replacement.write_bytes(self.rollout.read_bytes())
        replacement.replace(self.rollout)
        recovered = RolloutToolResponseReader(state['origin'])
        with self.assertRaisesRegex(ValueError, 'boundary'):
            recovered.find_response({'client_message_id': str(uuid.uuid4()), 'fence': fence},
                                    state['message']['text'])
        for attribute, value in [('owner_id', str(uuid.uuid4())), ('snapshot_id', str(uuid.uuid4())),
                                 ('snapshot_path', str(self.root / 'other.jsonl'))]:
            original = getattr(self.owner, attribute)
            setattr(self.owner, attribute, value)
            deliver(self.run, state)
            self.assertEqual(state['delivery']['status'], 'failed')
            setattr(self.owner, attribute, original)
        with patch.dict(os.environ, {'CODEX_THREAD_ID': str(uuid.uuid4())}):
            with self.assertRaises(ValueError):
                with open_connection(state['origin']):
                    pass
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            with open_connection(state['origin'], cancelled):
                pass
        with patch.dict(os.environ, {'CODEX_APP_TOOLS_PIPE_PATH': str(self.root / 'wrong.sock')}):
            with self.assertRaises(ValueError):
                dialog_desktop.Bridge(state['origin']).discover()
        self.assertEqual(self.gateway.sends, [])


if __name__ == '__main__':
    unittest.main()
