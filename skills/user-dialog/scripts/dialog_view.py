"""Render compiled JSON nodes using one common state/action model."""

from copy import deepcopy
from pathlib import Path

from dialog_content import file_content, label, markdown
from dialog_spec import FieldError, matches, validate_values, walk


class View:
    def __init__(self, ui, spec):
        self.ui, self.spec = ui, spec
        self.values, self.writers, self.widgets, self.rules, self.stacks = {}, {}, {}, [], {}
        self.nodes = {node['id']: node for node in walk(spec['body']) if 'id' in node}
        self.restoring = False
        self.text_bindings = []
        for node in walk(spec['body']):
            if node['type'] in {'input', 'choice'}:
                self.values[node['id']] = deepcopy(node.get('value', [] if node.get('multiple') else None))
        for key, value in ui.state.get('draft', {}).items():
            if key in self.values:
                self.values[key] = value

    def set(self, key, value):
        self.values[key] = value
        if key in self.writers:
            self.restoring = True
            try:
                self.writers[key](value)
            finally:
                self.restoring = False
        self.refresh()

    def changed(self, key, value):
        if not self.restoring:
            self.values[key] = value
            self.refresh()

    def refresh(self):
        for widget, key in self.text_bindings:
            widget.set_text(str(self.values.get(key) or ""))
        for widget, node in self.rules:
            widget.set_visible(matches(node.get('visible_when'), self.values))
            widget.set_sensitive(matches(node.get('enabled_when'), self.values))
        for key, (stack, _) in self.stacks.items():
            children = self.nodes[key]['children']
            visible = [child for child in children if matches(child.get('visible_when'), self.values)]
            if visible and stack.get_visible_child_name() not in [child['id'] for child in visible]:
                stack.set_visible_child_name(visible[0]['id'])
        if self.ui._built:
            self.ui.checkpoint()

    def validate(self, values):
        try:
            validate_values(self.spec, values)
        except (ValueError, TypeError) as error:
            if isinstance(error, FieldError):
                widget = self.widgets.get(error.field)
                child = widget
                while child is not None and child.get_parent() is not None:
                    parent = child.get_parent()
                    if isinstance(parent, self.ui.Gtk.Stack):
                        parent.set_visible_child(child)
                    child = parent
                if widget:
                    self.ui.focus(widget)
            self.ui.message(str(error))
            return str(error)
        return None

    def action(self, action, button_label=None):
        kind = action['type']
        if kind == 'submit':
            self.ui.submit(action=button_label, include_values=action.get('include_values', True))
        elif kind == 'dismiss':
            self.ui.dismiss()
        elif kind == 'defer':
            self.ui.defer()
        elif kind in {'set', 'toggle'}:
            target = action['target']
            value = action.get('value')
            if isinstance(value, dict) and 'ref' in value:
                value = self.values.get(value['ref'])
            if kind == 'toggle':
                old = list(self.values.get(target) or [])
                value = [entry for entry in old if entry != value] if value in old else [*old, value]
            self.set(target, value)
        elif kind == 'navigate':
            stack, children = self.stacks[action['target']]
            children = [child for child in children if matches(child.get('visible_when'), self.values)]
            names = [child['id'] for child in children]
            destination = action.get('page')
            if destination in {'next', 'previous'}:
                index = names.index(stack.get_visible_child_name())
                index += 1 if destination == 'next' else -1
                if not 0 <= index < len(names):
                    return
                destination = names[index]
            if destination in names:
                stack.set_visible_child_name(destination)
                self.ui.focus(stack.get_visible_child())

    def render(self, node):
        ui = self.ui
        Gtk = ui.Gtk
        kind = node['type']
        if kind == 'text':
            if 'ref' in node:
                widget = label(ui, '')
                self.text_bindings.append((widget, node['ref']))
            else:
                widget = markdown(ui, node.get('text', ''), Path(ui.state['base']))
        elif kind == 'file':
            widget = file_content(ui, node['path'])
        elif kind in {'column', 'row', 'group', 'grid'}:
            if kind == 'grid':
                widget = Gtk.Grid(column_spacing=16, row_spacing=16)
            else:
                widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if kind == 'row' else Gtk.Orientation.VERTICAL, spacing=12)
            if node.get('label') and kind != 'grid':
                heading = label(ui, node['label'])
                heading.add_css_class('heading')
                widget.append(heading)
            for index, child in enumerate(node.get('children', [])):
                built = self.render(child)
                if kind == 'grid':
                    columns = node.get('columns', 2)
                    widget.attach(built, index % columns, index // columns, 1, 1)
                else:
                    widget.append(built)
            if kind == 'group':
                widget.add_css_class('card')
                widget.add_css_class('dialog-group')
                for side in ('top', 'bottom', 'start', 'end'):
                    getattr(widget, f'set_margin_{side}')(8)
        elif kind in {'tabs', 'pages'}:
            widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
            if kind == 'tabs':
                switcher = Gtk.StackSwitcher(stack=stack)
                widget.append(switcher)
            for child in node['children']:
                stack.add_titled(self.render(child), child['id'], child['label'])
            widget.append(stack)
            if 'id' in node:
                self.stacks[node['id']] = (stack, node['children'])
            if kind == 'pages':
                navigation = Gtk.Box(spacing=8)
                for name, caption in [('previous', node.get('back_label', 'Back')), ('next', node.get('next_label', 'Next'))]:
                    button = Gtk.Button(label=caption)
                    button.connect('clicked', lambda _, page=name: self.action({'type': 'navigate', 'target': node['id'], 'page': page}))
                    navigation.append(button)
                widget.append(navigation)
        elif kind == 'button':
            widget = Gtk.Button(label=node['label'])
            widget.connect('clicked', lambda _: self.action(node['action'], node['label']))
        elif kind == 'input':
            widget = self.input(node)
        elif kind == 'choice':
            widget = self.choice(node)
        else:
            raise ValueError(f'Unsupported node: {kind}')
        widget.set_hexpand(True)
        if 'id' in node:
            self.widgets[node['id']] = widget
        self.rules.append((widget, node))
        return widget

    def input(self, node):
        ui, Gtk = self.ui, self.ui.Gtk
        key = node['id']
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = label(ui, node['label'] + (' *' if node.get('required') else ''))
        heading.add_css_class('heading')
        box.append(heading)
        form = node.get('format', 'text')
        if form == 'file':
            selected = label(ui, '')
            box.append(selected)
            self.writers[key] = lambda value: selected.set_text(value or '')
            def open_picker(_):
                dialog = Gtk.FileDialog(title=node['label'])
                def finished(dialog, result):
                    try:
                        file = dialog.open_finish(result)
                        if file and file.get_path():
                            self.set(key, str(Path(file.get_path()).resolve()))
                    except ui.GLib.Error:
                        pass
                dialog.open(ui.window, None, finished)
            button = Gtk.Button(label=node.get('browse_label', 'Choose file'))
            button.connect('clicked', open_picker)
            box.append(button)
            clear = Gtk.Button(label=node.get('clear_label', 'Clear'))
            clear.connect('clicked', lambda _: self.set(key, None))
            box.append(clear)
        elif node.get('multiline'):
            entry = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
            buffer = entry.get_buffer()
            buffer.connect('changed', lambda buf: self.changed(key, buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)))
            self.writers[key] = lambda value: buffer.set_text(value or '')
            scroll = Gtk.ScrolledWindow(min_content_height=100)
            scroll.set_child(entry)
            scroll.add_css_class('view')
            scroll.add_css_class('dialog-editor')
            box.append(scroll)
        else:
            entry = Gtk.Entry(placeholder_text=node.get('placeholder', 'YYYY-MM-DD' if form == 'date' else ''))
            def changed(widget):
                value = widget.get_text()
                if form == 'number' and value:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                self.changed(key, value)
            entry.connect('changed', changed)
            self.writers[key] = lambda value: entry.set_text('' if value is None else str(value))
            box.append(entry)
        return box

    def choice(self, node):
        ui, Gtk = self.ui, self.ui.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        heading = label(ui, node['label'] + (' *' if node.get('required') else ''))
        heading.add_css_class('heading')
        box.append(heading)
        layout = node.get('layout', {'type': 'column'})
        option_area = Gtk.Grid(column_spacing=16, row_spacing=12) if layout['type'] == 'grid' else Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL if layout['type'] == 'row' else Gtk.Orientation.VERTICAL, spacing=12)
        box.append(option_area)
        buttons = []
        for option in node['options']:
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            button = Gtk.CheckButton(label=option['label'])
            if buttons and not node.get('multiple'):
                button.set_group(buttons[0][0])
            buttons.append((button, option['value']))
            def changed(widget, value=option['value']):
                if self.restoring:
                    return
                if node.get('multiple'):
                    self.changed(node['id'], [value for control, value in buttons if control.get_active()])
                elif widget.get_active():
                    self.changed(node['id'], value)
            button.connect('toggled', changed)
            section.append(button)
            for child in option.get('content', []):
                section.append(self.render(child))
            section.set_hexpand(True)
            if layout['type'] == 'grid':
                index = len(buttons) - 1
                columns = layout.get('columns', 2)
                option_area.attach(section, index % columns, index // columns, 1, 1)
            else:
                option_area.append(section)
        def write(value):
            selected = value if isinstance(value, list) else [value]
            for button, key in buttons:
                button.set_active(key in selected)
        self.writers[node['id']] = write
        return box

    def build(self):
        content = self.render(self.spec['body'])
        for key, writer in self.writers.items():
            self.restoring = True
            try:
                writer(self.values[key])
            finally:
                self.restoring = False
            self.ui.bind(key, lambda key=key: self.values[key])
        for item in self.spec['actions']:
            button = self.ui.action(item.get('id', item['label']), item['label'],
                                    primary=item.get('primary', False),
                                    callback=lambda item=item: self.action(item['action'], item['label']))
            self.rules.append((button, item))
        self.ui.set_validator(self.validate)
        self.refresh()
        return content
