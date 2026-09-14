"""Render compiled JSON nodes using one common state/action model."""

from pathlib import Path

from dialog_content import code_block, file_content, label, markdown, markdown_document
from dialog_spec import FieldError, initial_value, matches, validate_values, walk
from dialog_transition import FadeStack, fade_switcher, select_page


def continuous_text(children):
    """Coalesce adjacent static prose without changing independent node rules."""
    pending = []
    for node in children:
        prose = (node['type'] == 'text'
                 and not set(node) - {'type', 'text', 'children'}
                 and '```' not in node.get('text', ''))
        if prose:
            pending.append(node.get('text', ''))
            continue
        if pending:
            yield {'type': 'text', 'text': '\n\n'.join(pending)}
            pending.clear()
        yield node
    if pending:
        yield {'type': 'text', 'text': '\n\n'.join(pending)}


class View:
    def __init__(self, ui, spec):
        self.ui, self.spec = ui, spec
        self.values, self.writers, self.widgets, self.rules, self.stacks = {}, {}, {}, [], {}
        self.nodes = {node['id']: node for node in walk(spec['body']) if 'id' in node}
        self.restoring = False
        self.text_bindings = []
        self.option_panels = []
        self.choice_controls = []
        self.records = {}
        for node in walk(spec['body']):
            if node['type'] in {'input', 'choice'}:
                self.values[node['id']] = initial_value(node)
        for key, value in ui.state.get('draft', {}).items():
            if key in self.values:
                self.values[key] = value

    def set(self, key, value):
        if self is not self.ui.view:
            return self.ui.view.set(key, value)
        self.values[key] = value
        if key in self.writers:
            self.restoring = True
            try:
                self.writers[key](value)
            finally:
                self.restoring = False
        self.refresh()

    def changed(self, key, value):
        if self.restoring or self.ui.view.restoring:
            return
        if self is not self.ui.view:
            return self.ui.view.changed(key, value)
        if not self.restoring:
            self.values[key] = value
            self.refresh()

    def refresh(self):
        for widget, key in self.text_bindings:
            value = self.values.get(key)
            widget.set_text('' if value is None else str(value))
        for widget, node in self.rules:
            widget.set_visible(matches(node.get('visible_when'), self.values))
            widget.set_sensitive(matches(node.get('enabled_when'), self.values))
        for panel, key, value in self.option_panels:
            panel.set_visible(self.values.get(key) == value)
        for key, (stack, _) in self.stacks.items():
            children = self.nodes[key]['children']
            visible = [child for child in children if matches(child.get('visible_when'), self.values)]
            if visible and stack.get_visible_child_name() not in [child['id'] for child in visible]:
                select_page(stack, visible[0]['id'])
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
            self.ui.message(str(error), error=True)
            return str(error)
        return None

    def action(self, action, button_label=None, button=None):
        if self is not self.ui.view:
            return self.ui.view.action(action, button_label, button)
        kind = action['type']
        if self.ui.state['status'] == 'submitted' and kind not in {'dismiss', 'defer', 'navigate'}:
            if (kind == 'submit' and button is self.ui._submit_button and self.ui._retry_available):
                self.ui.start_delivery(confirm_only=True)
            return
        if kind == 'submit':
            self.ui.submit(action=button_label, include_values=action.get('include_values', True), button=button)
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
                select_page(stack, destination)
                self.ui.focus(stack.get_visible_child())

    def render(self, node, path=()):
        ui = self.ui
        Gtk = ui.Gtk
        kind = node['type']
        if kind == 'text':
            if 'ref' in node:
                widget = label(ui, '')
                self.text_bindings.append((widget, node['ref']))
            else:
                widget = markdown(ui, node.get('text', ''), Path(ui.state['base']))
        elif kind == 'markdown':
            widget = markdown_document(ui, node['text'], Path(ui.state['base']), node.get('label') or 'Markdown')
        elif kind == 'code':
            widget = code_block(ui, node['text'], node.get('language', ''), node.get('label'))
        elif kind == 'file':
            widget = file_content(ui, node['path'], node.get('label'))
        elif kind == 'separator':
            widget = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL if node.get('orientation') == 'vertical' else Gtk.Orientation.HORIZONTAL)
        elif kind == 'table':
            widget = Gtk.Grid(column_spacing=18, row_spacing=8)
            for row_index, row in enumerate([node['columns'], *node.get('rows', [])]):
                for column_index, text in enumerate(row):
                    cell = label(ui, text)
                    if row_index == 0:
                        cell.add_css_class('heading')
                    widget.attach(cell, column_index, row_index, 1, 1)
        elif kind in {'column', 'row', 'group', 'grid'}:
            if kind == 'grid':
                widget = Gtk.Grid(column_spacing=16, row_spacing=16)
            else:
                widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if kind == 'row' else Gtk.Orientation.VERTICAL, spacing=12)
            if node.get('label') and kind != 'grid':
                heading = label(ui, node['label'])
                heading.add_css_class('heading')
                widget.append(heading)
                widget.dialog_heading = heading
            children = node.get('children', [])
            if kind in {'column', 'group'}:
                children = continuous_text(children)
            for index, child in enumerate(children):
                built = self.render(child, path + (child.get('id', f'@{index}'),))
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
            transition = node.get('transition', {'type': 'fade-through', 'duration': 320})
            effects = {'none': Gtk.StackTransitionType.NONE,
                       'crossfade': Gtk.StackTransitionType.CROSSFADE,
                       'slide': Gtk.StackTransitionType.SLIDE_LEFT_RIGHT}
            sequential = transition.get('type') == 'fade-through'
            stack = (FadeStack(transition.get('duration', 320)) if sequential else
                     Gtk.Stack(transition_type=effects[transition.get('type', 'none')],
                               transition_duration=transition.get('duration', 120), vhomogeneous=False))
            stack.connect('notify::visible-child', lambda *_: ui.GLib.idle_add(ui.refit) if ui._built else None)
            if kind == 'tabs' and not sequential:
                switcher = Gtk.StackSwitcher(stack=stack)
                widget.append(switcher)
            for child in node['children']:
                stack.add_titled(self.render(child, path + (child['id'],)), child['id'], child['label'])
            if kind == 'tabs' and sequential:
                widget.append(fade_switcher(stack, node['children']))
            widget.append(stack)
            widget.dialog_stack = stack
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
            widget.connect('clicked', lambda button: self.action(node['action'], node['label'], button))
        elif kind == 'input':
            widget = self.input(node)
        elif kind == 'choice':
            widget = self.choice(node, path)
        else:
            raise ValueError(f'Unsupported node: {kind}')
        widget.set_hexpand(True)
        if 'id' in node:
            self.widgets[node['id']] = widget
        self.rules.append((widget, node))
        self.records[path] = (node, widget)
        return widget

    def input(self, node):
        ui, Gtk = self.ui, self.ui.Gtk
        key = node['id']
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = label(ui, node['label'] + (' *' if node.get('required') else ''))
        heading.add_css_class('heading')
        box.append(heading)
        form = node.get('format', 'text')
        if form == 'boolean':
            entry = Gtk.Switch(halign=Gtk.Align.START)
            entry.connect('notify::active', lambda widget, _: self.changed(key, widget.get_active()))
            self.writers[key] = lambda value: entry.set_active(bool(value))
            box.append(entry)
        elif form == 'file':
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

    def choice(self, node, path=()):
        ui, Gtk = self.ui, self.ui.Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        heading = label(ui, node['label'] + (' *' if node.get('required') else ''))
        heading.add_css_class('heading')
        box.append(heading)
        if node.get('presentation') == 'dropdown':
            options = node['options']
            control = Gtk.DropDown.new_from_strings([option['label'] for option in options])
            self.choice_controls.append(control)
            control.set_selected(Gtk.INVALID_LIST_POSITION)
            def changed(widget, _):
                index = widget.get_selected()
                self.changed(node['id'], options[index]['value'] if index < len(options) else None)
            control.connect('notify::selected', changed)
            def write(value):
                index = next((index for index, option in enumerate(options) if option['value'] == value), Gtk.INVALID_LIST_POSITION)
                control.set_selected(index)
            self.writers[node['id']] = write
            box.append(control)
            for option in options:
                panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                for index, child in enumerate(option.get('content', [])):
                    panel.append(self.render(child, path + ('option:' + option['value'], child.get('id', f'@{index}'))))
                box.append(panel)
                self.option_panels.append((panel, node['id'], option['value']))
            return box
        layout = node.get('layout', {'type': 'column'})
        option_area = Gtk.Grid(column_spacing=16, row_spacing=12) if layout['type'] == 'grid' else Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL if layout['type'] == 'row' else Gtk.Orientation.VERTICAL, spacing=12)
        box.append(option_area)
        buttons = []
        for option in node['options']:
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            button = Gtk.CheckButton(label=option['label'])
            self.choice_controls.append(button)
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
            for index, child in enumerate(option.get('content', [])):
                section.append(self.render(child, path + ('option:' + option['value'], child.get('id', f'@{index}'))))
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
        self.build_actions()
        self.ui.set_validator(self.validate)
        self.refresh()
        return content

    def build_actions(self):
        for item in self.spec['actions']:
            button = self.ui.action(item.get('id', item['label']), item['label'],
                                    primary=item.get('primary', False),
                                    callback=lambda button, item=item: self.action(item['action'], item['label'], button))
            self.rules.append((button, item))

    def freeze_inputs(self):
        for widget, node in self.rules:
            if node.get('type') == 'input' or node.get('action', {}).get('type') in {'submit', 'set', 'toggle'}:
                widget.set_sensitive(False)
        for widget in self.choice_controls:
            widget.set_sensitive(False)
