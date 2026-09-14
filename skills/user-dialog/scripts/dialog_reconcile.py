"""Plan view changes without touching the live tree; preserve reusable widgets."""

import hashlib
from pathlib import Path
import re

from dialog_view import View, continuous_text


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


def assets(spec, base):
    """Fingerprint local assets, including images referenced inside Markdown."""
    from dialog_spec import walk
    result = {}
    for node in walk(spec['body']):
        paths = []
        text, directory = node.get('text', ''), Path(base)
        if node['type'] == 'file':
            path = Path(node['path'])
            paths.append(path)
            if path.suffix.lower() in {'.md', '.markdown'}:
                text, directory = path.read_text(encoding='utf-8'), path.parent
        if node['type'] in {'text', 'markdown', 'file'}:
            for name in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text):
                if '://' not in name:
                    paths.append((directory / name).resolve())
        for path in paths:
            if path.is_file():
                with path.open('rb') as source:
                    result[str(path)] = hashlib.file_digest(source, 'sha256').hexdigest()
            else:
                result[str(path)] = None
    return result


def preserve_answers(old, new, values):
    """Reject updates that cannot retain existing answers without coercion."""
    for key, value in values.items():
        if value in (None, '', []):
            continue
        before, after = old.nodes[key], new.nodes.get(key)
        if after is None or after['type'] != before['type']:
            raise ValueError(f'Update would remove an answer: {key}')
        for prop, default in [('format', 'text'), ('multiple', False), ('multiline', False)]:
            if before.get(prop, default) != after.get(prop, default):
                raise ValueError(f'Update would change an answered field type: {key}')
        if after['type'] == 'choice':
            selected = value if after.get('multiple') else [value]
            options = {option['value'] for option in after['options']}
            if any(item not in options for item in selected):
                raise ValueError(f'Update would remove a selected option: {key}')


class ViewUpdate:
    def __init__(self, ui, spec, fingerprints):
        self.ui, self.old = ui, ui.view
        self.new = View(ui, spec)
        self.new.values.update({k: v for k, v in self.old.values.items() if k in self.new.values})
        preserve_answers(self.old, self.new, self.old.values)
        self.operations, self.removed, self.retained = [], [], set()
        self.asset_change = fingerprints != getattr(self.old, 'assets', {})
        self.new.assets = fingerprints
        self.new.restoring = True
        try:
            self.root = self.plan(spec['body'], ())
        finally:
            self.new.restoring = False
        self.footer_changed = self.old.spec['actions'] != spec['actions']
        if self.footer_changed:
            self.removed.append(ui.actions)
        # Merge metadata for retained widgets. Old callbacks route through ui.view.
        for name in ('writers', 'widgets', 'stacks'):
            source, target = getattr(self.old, name), getattr(self.new, name)
            for key, value in source.items():
                owner = self.old.widgets.get(key)
                if owner in self.retained:
                    target[key] = value
        for name in ('rules', 'text_bindings', 'option_panels'):
            getattr(self.new, name).extend(item for item in getattr(self.old, name)
                                          if item[0] in self.retained)
        self.new.choice_controls.extend(w for w in self.old.choice_controls if w in self.retained)
        if not self.footer_changed:
            self.new.rules.extend(item for item in self.old.rules if item[0].get_parent() == ui.actions)

    def retain(self, path, node, widget, subtree=False):
        if subtree:
            self.retained.update(descendants(widget))
            for key, record in self.old.records.items():
                if key[:len(path)] == path:
                    self.new.records[key] = record
        else:
            self.retained.add(widget)
        self.new.records[path] = (node, widget)
        return widget

    def plan(self, node, path):
        record = self.old.records.get(path)
        if record:
            before, widget = record
            same = before == node
            if node['type'] in {'input', 'choice'}:
                same = {k: v for k, v in before.items() if k != 'value'} == {
                    k: v for k, v in node.items() if k != 'value'}
            dependencies = assets({'body': node}, self.ui.state['base']) if same and self.asset_change else {}
            changed_assets = any(self.old.assets.get(key) != value for key, value in dependencies.items())
            if same and not changed_assets:
                return self.retain(path, node, widget, True)
            layout = node['type'] in {'column', 'row', 'group', 'grid', 'tabs', 'pages'}
            if node['type'] in {'tabs', 'pages'} and before['type'] == node['type']:
                layout = [(c['id'], c['label']) for c in before['children']] == [(c['id'], c['label']) for c in node['children']]
            shell = lambda n: {k: v for k, v in n.items() if k != 'children'}
            if layout and shell(before) == shell(node):
                children = list(continuous_text(node['children'])) if node['type'] in {'column', 'group'} else node['children']
                planned = [(child, self.plan(child, path + (child.get('id', f'@{i}'),)))
                           for i, child in enumerate(children)]
                parent = getattr(widget, 'dialog_stack', widget)
                heading = getattr(widget, 'dialog_heading', None)
                desired = [w for _, w in planned]
                existing = list(self._children(parent))
                discarded = [w for w in existing if w is not heading and w not in desired]
                self.removed.extend(discarded)
                def arrange():
                    Gtk = self.ui.Gtk
                    for child in discarded:
                        parent.remove(child)
                    previous = heading
                    for index, (child, built) in enumerate(planned):
                        if isinstance(parent, Gtk.Stack):
                            if built.get_parent() is None:
                                parent.add_titled(built, child['id'], child['label'])
                        elif isinstance(parent, Gtk.Grid):
                            columns = node.get('columns', 2)
                            if built.get_parent() is None:
                                parent.attach(built, index % columns, index // columns, 1, 1)
                            else:
                                cell = parent.get_layout_manager().get_layout_child(built)
                                cell.set_property('column', index % columns)
                                cell.set_property('row', index // columns)
                        else:
                            if built.get_parent() is None:
                                parent.append(built)
                            parent.reorder_child_after(built, previous)
                            previous = built
                self.operations.append(arrange)
                return self.retain(path, node, widget)
            self.removed.append(widget)
        return self.new.render(node, path)

    @staticmethod
    def _children(widget):
        child = widget.get_first_child()
        while child:
            yield child
            child = child.get_next_sibling()

    def blocked(self):
        focus = self.ui.window.get_focus()
        for root in self.removed:
            for widget in descendants(root):
                if widget == focus:
                    return True
                if isinstance(widget, self.ui.Gtk.TextView) and widget.get_buffer().get_has_selection():
                    return True
                if isinstance(widget, self.ui.Gtk.Label) and widget.get_selection_bounds()[0]:
                    return True
        return False

    def apply(self):
        ui, new = self.ui, self.new
        preserve_answers(self.old, new, self.old.values)
        new.values.update({k: v for k, v in self.old.values.items() if k in new.values})
        offsets = [(adj, adj.get_value()) for adj in (ui.scroller.get_hadjustment(), ui.scroller.get_vadjustment())]
        pages = {key: stack.get_visible_child_name() for key, (stack, _) in self.old.stacks.items()}
        ui._updating = True
        new.restoring = True
        try:
            for operation in self.operations:
                operation()
            if self.root.get_parent() is None:
                ui.content.remove(ui.content.get_first_child())
                ui.content.append(self.root)
            ui.view = new
            ui._bindings.clear()
            for key, writer in new.writers.items():
                if new.widgets[key] not in self.retained:
                    writer(new.values[key])
                ui.bind(key, lambda key=key: new.values[key])
            if self.footer_changed:
                ui.set_default_action(None)
                for button in list(self._children(ui.actions)):
                    ui.actions.remove(button)
                new.build_actions()
            for key, name in pages.items():
                if key in new.stacks and new.stacks[key][0].get_child_by_name(name):
                    new.stacks[key][0].set_visible_child_name(name)
            new.stacks = {key: (stack, new.nodes[key]['children']) for key, (stack, _) in new.stacks.items()}
            ui.set_validator(new.validate)
            ui.state.update(spec=new.spec, title=new.spec['title'], subtitle=new.spec.get('subtitle', ''), draft=dict(new.values))
            ui.window.set_title(ui.state['title'])
            ui.window_title.set_title(ui.state['title'])
            ui.window_title.set_subtitle(ui.state['subtitle'])
            ui._preferred_width = new.spec.get('width', 600)
            new.refresh()
            ui.refit()
            ui.prune_widgets()
            def restore_scroll():
                for adjustment, value in offsets:
                    adjustment.set_value(value)
                return False
            ui.GLib.idle_add(restore_scroll)
        finally:
            new.restoring = False
            ui._updating = False
        # Reused controls may retain their original View through signal callbacks.
        # Their methods delegate to ui.view, so release stale trees and data here.
        for name in ('values', 'writers', 'widgets', 'rules', 'stacks', 'nodes',
                     'records', 'text_bindings', 'option_panels', 'choice_controls'):
            getattr(self.old, name).clear()
        self.old.spec = None
