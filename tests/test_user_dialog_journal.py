from __future__ import annotations

import copy
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/user-dialog/scripts'
sys.path.insert(0, str(SCRIPTS))
import dialog_delivery
from dialog_delivery import DeliveryAttempt, confirm_delivery, deliver, restore_submission
from dialog_journal import SubmissionJournal, admitted
from dialog_state import read_state, save_state


def configure_owner(origin):
    os.environ.update(CODEX_HOME=origin['home'], CODEX_THREAD_ID=origin['thread_id'],
                      CODEX_SESSION_ID=origin['thread_id'])
    if origin['transport'] == 'desktop-ipc':
        os.environ['CODEX_APP_TOOLS_PIPE_PATH'] = 'inherited-test-bridge'
    else:
        os.environ.pop('CODEX_APP_TOOLS_PIPE_PATH', None)


class AdmissionBackend:
    """Simulate only native I/O; journal, process locks and recovery are real."""

    def __init__(self, root, gate=None):
        self.root, self.gate = Path(root), gate

    def event(self, event, attempt):
        record = {'event': event, 'response_id': attempt.client_id,
                  'thread_id': attempt.origin['thread_id'], 'message': attempt.message,
                  'cwd': os.getcwd()}
        with (self.root / 'events.jsonl').open('a+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            if event == 'sent':
                stream.seek(0)
                prior = [json.loads(line) for line in stream]
                journal = SubmissionJournal(attempt.origin)
                record['prior_admitted'] = {
                    entry['response_id']: admitted(journal.load(entry['response_id'])[1])
                    for entry in prior if entry['event'] == 'sent'
                    and entry['thread_id'] == attempt.origin['thread_id']}
                stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(record) + '\n')
            stream.flush()

    def receipt(self, attempt):
        path = self.root / (attempt.client_id + '.receipt')
        if not path.exists():
            return None
        receipt = json.loads(path.read_text())
        if (receipt['thread_id'] != attempt.origin['thread_id']
                or receipt['message'] != attempt.message):
            raise ValueError('Receipt belongs to another submission')
        return {'item_id': 'item-' + attempt.client_id, 'turn_id': 'native-turn', 'kind': 'test-tool'}

    def deliver(self, attempt):
        attempt.prepare('test-tool', fence={'response_id': attempt.client_id})
        attempt.sending()
        self.event('sent', attempt)
        if self.gate:
            while not (self.root / self.gate).exists():
                if attempt.cancel.wait(.01):
                    return
        (self.root / (attempt.client_id + '.receipt')).write_text(json.dumps({
            'thread_id': attempt.origin['thread_id'], 'message': attempt.message}))
        attempt.observed(self.receipt(attempt))
        self.event('observed', attempt)

    def confirm(self, attempt):
        match = self.receipt(attempt)
        if match:
            attempt.observed(match)
            self.event('recovered', attempt)
        else:
            attempt.unconfirmed('Canonical admission has not appeared')


def process_delivery(run, root, cancel, gate=None):
    """Each renderer has its own cwd and genuine origin environment."""
    state = read_state(run)
    configure_owner(state['origin'])
    os.chdir(Path(run).parent)
    with patch.object(dialog_delivery, 'backend_for', return_value=AdmissionBackend(root, gate)):
        deliver(run, state, cancel)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Requires fork and Unix file locks')
class UserDialogJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = multiprocessing.get_context('fork')
        self.workers = []
        self.environment = patch.dict(os.environ, {})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.stop_workers)
        self.origin = {'transport': 'desktop-ipc', 'home': str(self.root / 'codex-home'),
                       'host_id': 'local', 'thread_id': str(uuid.uuid4())}

    def stop_workers(self):
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=3)

    def popup(self, name, origin=None):
        run = self.root / name / 'run'
        run.mkdir(parents=True)
        state = {'version': 3, 'request_id': str(uuid.uuid4()), 'status': 'submitted',
                 'origin': copy.deepcopy(origin or self.origin),
                 'message': {'type': 'text', 'text': 'Identical answer\n한글', 'text_elements': []},
                 'delivery': {'status': 'pending', 'response_id': str(uuid.uuid4())}}
        save_state(run, state)
        return run, state

    def start(self, run, gate=None):
        cancel = self.context.Event()
        worker = self.context.Process(target=process_delivery, args=(run, self.root, cancel, gate))
        worker.start()
        self.workers.append(worker)
        return worker, cancel

    def events(self):
        path = self.root / 'events.jsonl'
        if not path.exists():
            return []
        with path.open() as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            return [json.loads(line) for line in stream]

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Condition did not complete before timeout')

    def finish(self, worker):
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive(), 'Delivery process remained blocked')
        self.assertEqual(worker.exitcode, 0)

    def test_same_origin_across_projects_serializes_through_admission_and_distinct_origins_overlap(self):
        first, a = self.popup('project-a')
        second, b = self.popup('project-b')
        worker_a, _ = self.start(first, 'admit-a')
        self.wait_for(lambda: len(self.events()) == 1)
        worker_b, _ = self.start(second)
        self.wait_for(lambda: read_state(second)['delivery'].get('phase') == 'waiting_origin')
        self.assertEqual([entry['event'] for entry in self.events()], ['sent'])
        (self.root / 'admit-a').touch()
        self.finish(worker_a)
        self.finish(worker_b)
        events = self.events()
        sends = [entry for entry in events if entry['event'] == 'sent']
        self.assertEqual([entry['response_id'] for entry in sends],
                         [a['delivery']['response_id'], b['delivery']['response_id']])
        self.assertEqual(sends[1]['prior_admitted'], {a['delivery']['response_id']: True})
        self.assertEqual({entry['response_id'] for entry in events if entry['event'] == 'observed'},
                         {a['delivery']['response_id'], b['delivery']['response_id']})
        self.assertNotEqual(sends[0]['cwd'], sends[1]['cwd'])
        self.assertTrue(admitted(read_state(first)))
        self.assertTrue(admitted(read_state(second)))

        other = {**self.origin, 'thread_id': str(uuid.uuid4())}
        third, c = self.popup('project-c')
        fourth, d = self.popup('project-d', other)
        worker_c, _ = self.start(third, 'admit-c')
        worker_d, _ = self.start(fourth, 'admit-d')
        self.wait_for(lambda: len([entry for entry in self.events() if entry['event'] == 'sent']) == 4)
        self.assertFalse(admitted(read_state(third)))
        self.assertFalse(admitted(read_state(fourth)))
        for name in ['admit-c', 'admit-d']:
            (self.root / name).touch()
        self.finish(worker_c)
        self.finish(worker_d)
        for run, state in [(third, c), (fourth, d)]:
            saved = read_state(run)
            self.assertTrue(admitted(saved))
            self.assertEqual(saved['delivery']['observation']['item_id'],
                             'item-' + state['delivery']['response_id'])

    def test_sender_death_keeps_slot_and_successor_recovers_before_sending_without_replay(self):
        first, a = self.popup('crashed-project')
        second, b = self.popup('successor-project')
        worker_a, _ = self.start(first, 'never-admit')
        self.wait_for(lambda: len(self.events()) == 1)
        worker_a.terminate()
        worker_a.join(timeout=3)
        self.assertEqual(read_state(first)['delivery']['phase'], 'write_started')
        worker_b, cancel = self.start(second)
        self.wait_for(lambda: read_state(second)['delivery'].get('phase') == 'waiting_origin')
        self.wait_for(lambda: read_state(first)['delivery'].get('observation', {}).get('status') ==
                      'unconfirmed')
        self.assertEqual(len(self.events()), 1)
        journal = SubmissionJournal(self.origin)
        old_run, old = journal.claim(second, read_state(second))
        self.assertEqual(old_run, first)
        self.assertEqual(old['delivery']['response_id'], a['delivery']['response_id'])
        configure_owner(self.origin)
        with patch.object(dialog_delivery, 'backend_for', return_value=AdmissionBackend(self.root)):
            confirm_delivery(first, read_state(first))
        self.assertEqual(len(self.events()), 1, 'Uncertain confirmation must not replay input')

        (self.root / (a['delivery']['response_id'] + '.receipt')).write_text(json.dumps({
            'thread_id': a['origin']['thread_id'], 'message': a['message']}))
        self.finish(worker_b)
        self.assertFalse(cancel.is_set())
        self.assertEqual([(entry['event'], entry['response_id']) for entry in self.events()], [
            ('sent', a['delivery']['response_id']), ('recovered', a['delivery']['response_id']),
            ('sent', b['delivery']['response_id']), ('observed', b['delivery']['response_id'])])
        self.assertTrue(admitted(read_state(first)))
        self.assertTrue(admitted(read_state(second)))

    def test_admission_is_monotonic_over_late_errors_and_stale_popup_mirrors(self):
        run, state = self.popup('monotonic')
        configure_owner(self.origin)
        journal = SubmissionJournal(self.origin)
        self.assertIsNone(journal.claim(run, state))
        stale = copy.deepcopy(state)
        attempt = DeliveryAttempt(run, state, threading.Event(), journal)
        receipt = {'item_id': 'canonical', 'turn_id': 'turn', 'kind': 'test-tool'}
        attempt.observed(receipt)
        for error in ['accepted', 'unknown', 'rejected', 'unconfirmed']:
            with self.subTest(error=error):
                snapshot = copy.deepcopy(stale)
                stale_attempt = DeliveryAttempt(run, snapshot, threading.Event(), journal)
                getattr(stale_attempt, error)('Late response')
                self.assertTrue(admitted(snapshot))
                self.assertEqual(snapshot['delivery']['observation'], {'status': 'observed', **receipt})
        save_state(run, stale)
        with patch.object(dialog_delivery, 'backend_for', side_effect=AssertionError('No reconnect')):
            recovered = read_state(run)
            confirm_delivery(run, recovered)
        self.assertTrue(admitted(recovered))
        # Recovering an admitted mirror should also persist it for a fresh GUI.
        self.assertTrue(admitted(read_state(run)))

    def test_saved_submission_cannot_migrate_body_popup_destination_or_run_directory(self):
        run, state = self.popup('immutable')
        journal = SubmissionJournal(self.origin)
        journal.claim(run, state)
        alternate, _ = self.popup('alternate')
        mutations = {
            'body': lambda value: value['message'].update(text='Changed answer'),
            'popup': lambda value: value.update(request_id=str(uuid.uuid4())),
            'destination': lambda value: value['origin'].update(thread_id=str(uuid.uuid4())),
            'home': lambda value: value['origin'].update(home=str(self.root / 'other-home')),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(state)
                mutation(changed)
                with self.assertRaises(ValueError):
                    restore_submission(run, changed, journal)
        with self.assertRaises(ValueError):
            restore_submission(alternate, copy.deepcopy(state), journal)
        self.assertEqual(journal.load(state['delivery']['response_id'])[1]['message'], state['message'])


if __name__ == '__main__':
    unittest.main()
