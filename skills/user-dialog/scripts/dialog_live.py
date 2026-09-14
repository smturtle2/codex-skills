"""Own the open window's update lifecycle and acknowledge applied revisions."""

from dialog_reconcile import ViewUpdate, assets
from dialog_spec import compile_request
from dialog_state import save_state
from dialog_transition import FadeGroup, FadeTransition
from dialog_updates import read_pending, write_result


class LiveUpdates:
    def __init__(self, ui):
        self.ui = ui
        self.pending = None
        self.transition = None
        self.frame_handler = None
        self.applied = False
        self.closed = False
        ui.view.assets = assets(ui.state['spec'], ui.state['base'])
        # This timer reads only this run's mailbox; GTK owns all state mutations.
        self.source = ui.GLib.timeout_add(150, self.poll)

    def result(self, payload, status, error=None):
        ui = self.ui
        result = write_result(ui.run_dir, payload, status, ui.state.get('revision', 0), error)
        ui.state['update'] = result
        save_state(ui.run_dir, ui.state)
        return result

    def poll(self):
        ui = self.ui
        if self.closed:
            return False
        if self.transition is not None or self.frame_handler is not None:
            return True
        try:
            if self.pending is None:
                for payload in read_pending(ui.run_dir):
                    if (ui.state['status'] != 'open' or payload['request_id'] != ui.request_id
                            or payload['base_revision'] != ui.state.get('revision', 0)):
                        self.result(payload, 'rejected', 'Dialog identity, revision, or open state no longer matches')
                        continue
                    try:
                        spec = compile_request(payload['spec'], ui.state['base'])
                        plan = ViewUpdate(ui, spec, assets(spec, ui.state['base']))
                    except (ValueError, OSError, TypeError, KeyError) as error:
                        self.result(payload, 'rejected', str(error))
                        ui.prune_widgets()
                        continue
                    self.pending = (payload, plan)
                    break
            if self.pending is None:
                return True
            payload, plan = self.pending
            if plan.blocked():
                marker = {'command_id': payload['command_id'], 'status': 'deferred',
                          'reason': 'The changed area is focused or selected'}
                if ui.state.get('update') != marker:
                    ui.state['update'] = marker
                    save_state(ui.run_dir, ui.state)
                return True
            changed = [widget for _, widget in plan.new.records.values() if widget not in plan.retained]
            targets = list(dict.fromkeys([*plan.removed, *changed]))
            # Avoid multiplying opacity when changed widgets contain one another.
            targets = [w for w in targets if not any(w != other and w.is_ancestor(other) for other in targets)]
            self.transition = FadeTransition(FadeGroup(ui.window, targets), 320)
            self.transition.run(self.apply, self.finished)
        except (ValueError, OSError, TypeError, KeyError) as error:
            if self.pending:
                self.result(self.pending[0], 'rejected', str(error))
                self.pending = None
            else:
                marker = {'status': 'error', 'error': str(error)}
                if ui.state.get('update') != marker:
                    ui.state['update'] = marker
                    save_state(ui.run_dir, ui.state)
        return True

    def apply(self):
        payload, plan = self.pending
        if plan.blocked():
            self.transition.cancel()
            self.transition = None
            return
        try:
            plan.apply()
            self.ui.state['revision'] = payload['base_revision'] + 1
            self.ui.state['update'] = {'command_id': payload['command_id'], 'status': 'rendering'}
            save_state(self.ui.run_dir, self.ui.state)
            self.applied = True
        except (ValueError, OSError, TypeError, KeyError) as error:
            self.transition.cancel()
            self.transition = None
            self.result(payload, 'rejected', str(error))
            self.pending = None
            self.ui.prune_widgets()

    def finished(self):
        self.transition = None
        if self.pending is None:
            return
        # after-paint is later than layout/snapshot; a queued file is not an ack.
        clock = self.ui.window.get_frame_clock()
        if clock is None:
            return
        self.frame_handler = (clock, clock.connect('after-paint', self.painted))
        self.ui.window.queue_draw()

    def painted(self, *args):
        if self.frame_handler:
            clock, handler = self.frame_handler
            self.frame_handler = None
            clock.disconnect(handler)
        if self.pending:
            self.result(self.pending[0], 'applied')
            self.pending = None
        self.applied = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.ui.GLib.source_remove(self.source)
        if self.transition:
            self.transition.cancel()
            self.transition = None
        if self.frame_handler:
            clock, handler = self.frame_handler
            clock.disconnect(handler)
            self.frame_handler = None
        if self.pending:
            self.result(self.pending[0], 'interrupted' if self.applied else 'rejected',
                        'Dialog closed or response submitted before update display was confirmed')
            self.pending = None
        try:
            for payload in read_pending(self.ui.run_dir):
                self.result(payload, 'rejected', 'Dialog is no longer accepting updates')
        except (ValueError, OSError):
            pass
