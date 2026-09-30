from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
from dialog_connection import capture_origin, open_connection
from dialog_delivery import DeliveryAttempt, confirm_delivery, deliver
from dialog_observer import ResponseReader, RolloutResponseReader
from dialog_response import format_response
from dialog_state import read_state, save_state
import dialog_connection


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
    START = 'thread-follower-start-turn'
    STEER = 'thread-follower-steer-turn'

    def __init__(self, broker, path, thread_id, run, rollout):
        self.broker, self.thread_id, self.run, self.rollout = broker, thread_id, run, rollout
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.connect(str(path))
        self.lock = threading.Lock()
        send_frame(self.connection, {'type': 'request', 'requestId': 'owner-init',
            'method': 'initialize', 'version': 0, 'params': {'clientType': 'test-owner'}}, self.lock)
        self.client_id = receive_frame(self.connection)['result']['clientId']
        self.owner_id, self.snapshot_id, self.snapshot_path = self.client_id, thread_id, str(rollout)
        self.targeted_snapshot = True
        self.mode = 'normal'
        self.commit_gate = None
        self.active_turn = 'native-turn'
        self.turns = [{'turn_id': self.active_turn, 'status': 'inProgress', 'messages': []}]
        self.sends, self.calls, self.persisted, self.errors = [], [], [], []
        self.worker = threading.Thread(target=self.serve, daemon=True)
        self.worker.start()

    def send(self, packet):
        send_frame(self.connection, packet, self.lock)

    def reply(self, request, result=None, error=None):
        packet = {'type': 'response', 'requestId': request['requestId'],
            'resultType': 'error' if error else 'success'}
        if error:
            # Native IPC serializes only error.message, omitting owner/method.
            packet['error'] = error
        else:
            packet.update(method=request['method'], handledByClientId=self.owner_id, result=result)
        self.send(packet)

    def snapshot(self, target):
        packet = {'type': 'broadcast', 'method': 'thread-stream-state-changed',
            'sourceClientId': self.client_id, 'targetClientIds': [target], 'params': {
                'hostId': 'local', 'conversationId': self.thread_id, 'change': {
                    'type': 'snapshot', 'conversationState': {
                        'id': self.snapshot_id, 'title': 'Desktop test', 'rolloutPath': self.snapshot_path,
                        'cwd': str(self.rollout.parent),
                        # Deliberately unusable UI history: metadata capture must ignore it.
                        'turns': 'not a receipt', 'turnHistory': {'unreadable': True}}}}}
        self.send({**packet, 'sourceClientId': str(uuid.uuid4())})
        self.send({**packet, 'targetClientIds': [str(uuid.uuid4())]})
        if not self.targeted_snapshot:
            packet.pop('targetClientIds')
        self.send(packet)

    def persist(self, item):
        event = {'type': 'event_msg', 'payload': {'type': 'item_completed',
            'thread_id': self.thread_id, 'turn_id': self.active_turn, 'item': item}}
        encoded = (json.dumps(event, ensure_ascii=False) + '\n').encode()
        if self.mode in {'lost', 'error-after-write', 'unknown-mentions-inactive',
                         'wrong-thread-inactive', 'timeout-after-write'}:
            split = len(encoded) // 2
            encoded, self.pending_record = encoded[:split], encoded[split:]
        with self.rollout.open('ab') as stream:
            stream.write(encoded)

    def finish_turn(self):
        for turn in self.turns:
            if turn['turn_id'] == self.active_turn:
                turn['status'] = 'completed'
        self.active_turn = None

    def admit(self, request):
        """Model the native owner's optimistic turn/message reconciliation."""
        steering = request['method'] == self.STEER
        native = request['params'] if steering else request['params']['turnStart']['request']
        client_id, inputs = native['clientUserMessageId'], native['input']
        pending = {'client_id': client_id, 'text': inputs[0]['text'], 'canonical': False}
        if steering:
            if self.mode == 'finish-before-steer':
                self.finish_turn()
            if self.active_turn is None:
                self.reply(request, error=f'Cannot steer conversation {self.thread_id} '
                           'because its active turn already ended')
                if self.mode == 'competing-start-after-rejection':
                    self.active_turn = str(uuid.uuid4())
                    self.turns.append({'turn_id': self.active_turn, 'status': 'inProgress',
                        'messages': [{'client_id': str(uuid.uuid4()), 'text': 'Native human input',
                                      'canonical': True}]})
                return
            target = next(turn for turn in self.turns if turn['turn_id'] == self.active_turn)
            target['messages'].append(pending)
        else:
            # startTurn creates its placeholder even when Core will steer.
            placeholder = {'turn_id': None, 'status': 'inProgress', 'messages': [pending]}
            self.turns.append(placeholder)
            if self.active_turn is None:
                self.active_turn = str(uuid.uuid4())
                placeholder['turn_id'] = self.active_turn
            target = next(turn for turn in self.turns if turn['turn_id'] == self.active_turn)
        self.item_id = str(uuid.uuid4())
        item = {'type': 'UserMessage', 'id': self.item_id,
            'client_id': client_id, 'content': inputs}
        if self.mode == 'optimistic':
            item = {'type': 'steeringUserMessage', 'id': self.item_id,
                'status': 'accepted', 'serverUserMessageId': self.item_id,
                'serverClientUserMessageId': client_id, 'input': inputs}
        elif self.mode == 'tool-output':
            item = {'type': 'FunctionCallOutput', 'id': self.item_id,
                'client_id': client_id, 'output': inputs[0]['text']}
        elif self.mode == 'wrong-client':
            item['client_id'] = str(uuid.uuid4())
        elif self.mode == 'wrong-text':
            item['content'] = [{'type': 'text', 'text': 'Different response'}]
        def commit():
            self.persist(item)
            if item['type'] == 'UserMessage':
                existing = next((message for message in target['messages']
                                 if message['client_id'] == item['client_id']), None)
                if existing is None:
                    target['messages'].append({'client_id': item['client_id'],
                        'text': item['content'][0]['text'], 'canonical': True})
                else:
                    existing['canonical'] = True
        if self.mode != 'ack-before-commit':
            commit()
        if self.mode == 'lost':
            self.broker.disconnect(request['sourceClientId'])
        elif self.mode == 'error-after-write':
            self.reply(request, error='Owner error after admission')
        elif self.mode == 'unknown-mentions-inactive':
            self.reply(request, error='Outcome unknown: Cannot steer conversation '
                       f'{self.thread_id} because its active turn already ended')
        elif self.mode == 'wrong-thread-inactive':
            self.reply(request, error=f'Cannot steer conversation {uuid.uuid4()} '
                       'because its active turn already ended')
        elif self.mode == 'timeout-after-write':
            pass
        else:
            receipt = {'turnId': self.active_turn} if steering else {'turn': {'id': self.active_turn}}
            self.reply(request, {'result': receipt})
            if self.mode == 'ack-before-commit':
                if not self.commit_gate.wait(3):
                    raise TimeoutError('The originating tool did not release after ACK')
                commit()

    def serve(self):
        try:
            while True:
                request = receive_frame(self.connection)
                self.calls.append(request)
                method = request['method']
                if method == 'thread-owner-discovery':
                    self.reply(request, {'supportsUntrustedAppInput': True})
                elif method == 'thread-stream-following-changed':
                    self.snapshot(request['sourceClientId'])
                elif method in {self.STEER, self.START}:
                    self.sends.append(request)
                    self.persisted.append(read_state(self.run)['delivery'])
                    self.admit(request)
                else:
                    raise ValueError('Unexpected desktop method: ' + method)
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


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'Desktop IPC uses local Unix sockets')
class UserDialogDesktopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.socket = self.root / 'ipc/ipc.sock'
        self.socket.parent.mkdir()
        self.run = self.root / 'run'
        self.run.mkdir()
        self.thread_id = str(uuid.uuid4())
        self.rollout = self.root / 'sessions' / (self.thread_id + '.jsonl')
        self.rollout.parent.mkdir()
        self.rollout.write_text(json.dumps({'type': 'session_meta',
            'payload': {'id': self.thread_id, 'history_mode': 'paginated'}}) + '\n')
        environment = patch.dict(os.environ, {'CODEX_HOME': str(self.root), 'CODEX_THREAD_ID': self.thread_id,
            'CODEX_SESSION_ID': self.thread_id, 'CODEX_APP_TOOLS_PIPE_PATH': 'desktop-present'})
        environment.start()
        os.environ.pop('USER_DIALOG_SOCKET', None)
        self.addCleanup(environment.stop)
        self.broker = FramedBroker(self.socket)
        self.owner = DesktopOwner(self.broker, self.socket, self.thread_id, self.run, self.rollout)
        self.addCleanup(self.stop)

    def stop(self):
        self.owner.close()
        self.broker.close()
        self.assertEqual(self.owner.errors + self.broker.errors, [])

    def state(self):
        message = format_response({'title': '검토', 'body': {'type': 'input', 'id': 'notes', 'label': '의견'}},
            {'notes': '  Original **answer**\n한글 🧑🏽‍💻\n'}, '확인')
        state = {'version': 3, 'request_id': str(uuid.uuid4()), 'status': 'submitted',
            'origin': capture_origin(), 'message': message, 'delivery': {'status': 'pending'},
            'draft': {'notes': 'Retain the editable answer'}}
        save_state(self.run, state)
        return state

    def test_native_submission_preserves_text_spans_and_only_captures_metadata(self):
        self.owner.targeted_snapshot = False
        state = self.state()
        origin = state['origin']
        self.assertEqual((origin['owner_client_id'], origin['rollout_path'], origin['title']),
                         (self.owner.client_id, str(self.rollout), 'Desktop test'))
        self.assertEqual(self.owner.sends, [])
        deliver(self.run, state)
        request, = self.owner.sends
        self.assertEqual((request['method'], request['version'], request['targetClientId']),
                         (self.owner.STEER, 1, self.owner.client_id))
        steer = request['params']
        client_id = state['delivery']['client_message_id']
        self.assertEqual((steer['conversationId'], steer['clientUserMessageId'], steer['input']),
                         (self.thread_id, client_id, [state['message']]))
        self.assertTrue(state['message']['text_elements'])
        restored = steer['restoreMessage']
        self.assertEqual((restored['id'], restored['text'], restored['cwd']),
                         (client_id, state['message']['text'], str(self.rollout.parent)))
        self.assertEqual(restored['context'], {'prompt': state['message']['text'],
                         'workspaceRoots': [str(self.rollout.parent)], 'commentAttachments': []})
        self.assertIsInstance(restored['createdAt'], int)
        self.assertEqual(steer['attachments'], [])
        self.assertEqual(self.owner.persisted[0]['status'], 'sending')
        self.assertEqual(state['delivery']['observation']['item_id'], self.owner.item_id)
        self.assertEqual(state['delivery']['observation']['turn_id'], 'native-turn')
        allowed = {'thread-owner-discovery', 'thread-stream-following-changed', self.owner.STEER}
        self.assertTrue(all(packet['method'] in allowed for packet in self.owner.calls))
        follows = [packet for packet in self.owner.calls if packet['type'] == 'broadcast']
        self.assertEqual(len(follows), 2)  # One capture context and one submission context.
        helpers = [packet for packet in self.broker.requests if packet.get('method') == 'initialize'
                   and packet['params']['clientType'] == 'user-dialog']
        self.assertTrue(all(packet['sourceClientId'] == 'initializing-client' for packet in helpers))
        discovery_answers = [packet for packet in self.broker.requests
                             if packet['type'] == 'client-discovery-response']
        self.assertTrue(discovery_answers)
        self.assertTrue(all(packet['response'] == {'canHandle': False} for packet in discovery_answers))
        deliver(self.run, state)
        confirm_delivery(self.run, state)
        self.assertEqual(len(self.owner.sends), 1)

    def test_active_idle_and_ended_turns_do_not_leave_duplicate_or_thinking_placeholder(self):
        original_wait = ResponseReader.wait
        def bounded_wait(reader, delivery, message, timeout=60):
            return original_wait(reader, delivery, message, timeout=0.01)
        with patch.object(ResponseReader, 'wait', bounded_wait):
            for phase in ['active', 'idle', 'finish-before-steer', 'competing-start-after-rejection']:
                with self.subTest(phase=phase):
                    self.owner.mode = 'normal' if phase in {'active', 'idle'} else phase
                    if phase in {'idle', 'competing-start-after-rejection'}:
                        self.owner.finish_turn()
                    elif self.owner.active_turn is None:
                        self.owner.active_turn = str(uuid.uuid4())
                        self.owner.turns.append({'turn_id': self.owner.active_turn,
                            'status': 'inProgress', 'messages': []})
                    state = self.state()
                    before = len(self.owner.sends)
                    deliver(self.run, state)
                    self.assertEqual([packet['method'] for packet in self.owner.sends[before:]],
                                     [self.owner.STEER])
                    client_id = state['delivery']['client_message_id']
                    visible = [message for turn in self.owner.turns for message in turn['messages']
                               if message['client_id'] == client_id]
                    if phase == 'active':
                        self.assertEqual(state['delivery']['observation']['status'], 'observed')
                        self.assertEqual(len(visible), 1)
                        self.assertTrue(visible[0]['canonical'])
                    else:
                        self.assertEqual(state['delivery']['status'], 'unknown')
                        self.assertEqual(state['delivery']['observation']['status'], 'unconfirmed')
                        self.assertEqual(visible, [])
                        self.assertEqual(read_state(self.run)['draft'], state['draft'])
                        deliver(self.run, state)
                        confirm_delivery(self.run, state)
                        self.assertEqual(len(self.owner.sends), before + 1)
                    self.assertFalse(any(turn['turn_id'] is None for turn in self.owner.turns))
                    self.owner.finish_turn()
                    self.assertFalse(any(turn['status'] == 'inProgress' for turn in self.owner.turns))

    def test_origin_lifetime_guards_attach_and_wire_without_erasing_the_draft(self):
        original_sending = DeliveryAttempt.sending
        for phase in ['before-attach', 'before-wire']:
            with self.subTest(phase=phase):
                state = self.state()
                origin_cancel = threading.Event()
                if phase == 'before-attach':
                    origin_cancel.set()
                def origin_ends_before_wire(attempt):
                    original_sending(attempt)
                    origin_cancel.set()
                with patch.object(DeliveryAttempt, 'sending', origin_ends_before_wire):
                    deliver(self.run, state, origin_cancel=origin_cancel)
                self.assertEqual(state['delivery']['status'], 'failed')
                self.assertEqual(self.owner.sends, [])
                self.assertEqual(read_state(self.run)['draft'], state['draft'])
                # An observer cancellation reset cannot reopen the origin guard.
                deliver(self.run, state, threading.Event(), origin_cancel=origin_cancel)
                self.assertEqual(self.owner.sends, [])

    def test_ack_releases_origin_lifetime_before_canonical_observation(self):
        self.owner.mode = 'ack-before-commit'
        self.owner.commit_gate = threading.Event()
        state = self.state()
        origin_cancel = threading.Event()
        original_accepted = DeliveryAttempt.accepted
        def release_origin_after_ack(attempt, receipt):
            original_accepted(attempt, receipt)
            saved = read_state(self.run)['delivery']
            self.assertEqual(saved['status'], 'accepted')
            self.assertNotIn('observation', saved)
            self.assertNotIn(saved['client_message_id'], self.rollout.read_text())
            origin_cancel.set()
            self.owner.commit_gate.set()
        with patch.object(DeliveryAttempt, 'accepted', release_origin_after_ack):
            deliver(self.run, state, origin_cancel=origin_cancel)
        self.assertTrue(origin_cancel.is_set())
        self.assertEqual(state['delivery']['observation']['status'], 'observed')
        self.assertEqual(len(self.owner.sends), 1)
        self.assertEqual(self.owner.sends[0]['method'], self.owner.STEER)
        deliver(self.run, state, origin_cancel=origin_cancel)
        confirm_delivery(self.run, state)
        self.assertEqual(len(self.owner.sends), 1)

    def test_lost_or_negative_acknowledgement_never_replays_and_receipt_needs_no_owner(self):
        original_wait = ResponseReader.wait
        def bounded_wait(reader, delivery, message, timeout=60):
            return original_wait(reader, delivery, message, timeout=0.01)
        with patch.object(ResponseReader, 'wait', bounded_wait):
            for mode in ['lost', 'error-after-write', 'unknown-mentions-inactive',
                         'wrong-thread-inactive', 'timeout-after-write']:
                with self.subTest(mode=mode):
                    self.owner.mode = mode
                    state = self.state()
                    count = len(self.owner.sends)
                    with patch('dialog_desktop.REQUEST_TIMEOUT', 0.2):
                        deliver(self.run, state)
                    self.assertEqual(state['delivery']['status'], 'unknown')
                    self.assertEqual(len(self.owner.sends), count + 1)
                    self.assertEqual(self.owner.sends[-1]['method'], self.owner.STEER)
                    with self.rollout.open('ab') as stream:
                        stream.write(self.owner.pending_record)
                    # Recovery must use the pinned canonical log even if no owner can reconnect.
                    with patch('dialog_desktop.connection', side_effect=AssertionError('No reconnect')):
                        for status in ['sending', 'unknown', 'accepted']:
                            state['delivery']['status'] = status
                            save_state(self.run, state)
                            restored = read_state(self.run)
                            deliver(self.run, restored)
                            confirm_delivery(self.run, restored)
                            self.assertEqual(restored['delivery']['observation']['status'], 'observed')
                            self.assertEqual(len(self.owner.sends), count + 1)

    def test_noncanonical_or_nonmatching_receipts_do_not_confirm_or_resend(self):
        original_wait = ResponseReader.wait
        def bounded_wait(reader, delivery, message, timeout=60):
            return original_wait(reader, delivery, message, timeout=0.01)
        with patch.object(ResponseReader, 'wait', bounded_wait):
            for mode in ['optimistic', 'tool-output', 'wrong-client', 'wrong-text']:
                with self.subTest(mode=mode):
                    self.owner.mode = mode
                    state = self.state()
                    deliver(self.run, state)
                    self.assertEqual(state['delivery']['status'], 'accepted')
                    self.assertEqual(state['delivery']['observation']['status'], 'unconfirmed')
                    count = len(self.owner.sends)
                    deliver(self.run, state)
                    confirm_delivery(self.run, state)
                    self.assertEqual(len(self.owner.sends), count)

    def test_canonical_log_partial_unicode_and_file_replacement(self):
        state = self.state()
        delivery = {'client_message_id': str(uuid.uuid4())}
        reader = RolloutResponseReader(state['origin'])
        reader.validate()
        item = {'type': 'UserMessage', 'id': 'native-item', 'client_id': delivery['client_message_id'],
                'content': [state['message']]}
        event = {'type': 'event_msg', 'payload': {'type': 'item_completed',
                 'thread_id': self.thread_id, 'turn_id': 'native-turn', 'item': item}}
        wire = (json.dumps(event, ensure_ascii=False) + '\n').encode()
        split = wire.index('🧑'.encode()) + 1
        with self.rollout.open('ab') as stream:
            stream.write(wire[:split])
        self.assertIsNone(reader.find_response(delivery, state['message']['text']))
        with self.rollout.open('ab') as stream:
            stream.write(wire[split:])
        self.assertEqual(reader.find_response(delivery, state['message']['text']),
                         {'item_id': 'native-item', 'turn_id': 'native-turn'})
        replacement = self.rollout.with_suffix('.replacement')
        replacement.write_bytes(self.rollout.read_bytes())
        replacement.replace(self.rollout)
        with self.assertRaisesRegex(ValueError, 'changed'):
            reader.find_response(delivery, state['message']['text'])
        # Binding starts at validation, before any completed event is consumed.
        reader = RolloutResponseReader(state['origin'])
        reader.validate()
        replacement.write_bytes(self.rollout.read_bytes())
        replacement.replace(self.rollout)
        with self.assertRaisesRegex(ValueError, 'changed'):
            reader.find_response(delivery, state['message']['text'])
        self.assertEqual(self.owner.sends, [])

    def test_owner_path_origin_and_cancel_fail_before_submission(self):
        state = self.state()
        for field, changed in [('owner_id', str(uuid.uuid4())), ('snapshot_id', str(uuid.uuid4())),
                               ('snapshot_path', str(self.root / 'different.jsonl'))]:
            with self.subTest(field=field):
                original = getattr(self.owner, field)
                setattr(self.owner, field, changed)
                deliver(self.run, state)
                self.assertEqual(state['delivery']['status'], 'failed')
                self.assertEqual(self.owner.sends, [])
                self.assertEqual(read_state(self.run)['draft'], state['draft'])
                setattr(self.owner, field, original)
        with patch.dict(os.environ, {'CODEX_THREAD_ID': str(uuid.uuid4())}):
            with self.assertRaises(ValueError):
                with open_connection(state['origin']):
                    pass
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            with open_connection(state['origin'], cancelled):
                pass
        with open_connection(state['origin']) as server:
            for message, client_id in [({'type': 'toolOutput', 'text': 'text'}, str(uuid.uuid4())),
                                       (state['message'], 'not-a-uuid')]:
                with self.assertRaises(ValueError):
                    server.submit_user_message(message, client_id)
        with patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'unavailable')}), \
             patch('dialog_cli.AppServer') as alternate:
            with self.assertRaises(ValueError):
                capture_origin()
            alternate.assert_not_called()
        self.assertEqual(self.owner.sends, [])


if __name__ == '__main__':
    unittest.main()
