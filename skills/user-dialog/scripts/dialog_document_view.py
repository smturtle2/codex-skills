"""WebKit document surface embedded in the popup's single reading flow."""

import json
import html
import math
import uuid
from urllib.parse import urlsplit

import gi

try:
    gi.require_version('WebKit', '6.0')
except ValueError as error:
    raise ValueError('Markdown documents require WebKitGTK 6.0 (gir1.2-webkit-6.0)') from error
from gi.repository import Gdk, GLib, Gtk, WebKit

from dialog_document import Document, compile_document, compile_segments, html_page


class DocumentWebView(WebKit.WebView):
    def do_measure(self, orientation, for_size):
        # WebKit can retain its previous viewport as a minimum height. The
        # document's measured content, not that viewport, owns the host size.
        if orientation == Gtk.Orientation.VERTICAL:
            height = max(1, self.get_property('height-request'))
            return height, height, -1, -1
        return 0, 0, -1, -1


class DocumentView(Gtk.Box):
    def __init__(self, ui, source, base, display=None, segments=None, document=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ui = ui
        self._closed = False
        self.source = source
        self.display = display or {}
        self._reload_source = 0
        self._literal = False
        self.document = document if document is not None else (compile_segments(segments, base) if segments else compile_document(source, base))
        self._next_document = None
        self._document_token = ''
        self.metrics = {'loads': 0, 'text_updates': 0, 'messages': {}}
        self.base = base.resolve()
        self._started = False
        self._loaded = False
        self.dialog_has_selection = False
        self.dialog_dragging = False
        self._viewport_source = 0
        self._last_viewport = None
        self._height = 80
        self._measured_width = 0
        manager = WebKit.UserContentManager()
        self.manager = manager
        manager.register_script_message_handler('document', None)
        self._message_handler = manager.connect('script-message-received::document', self.message)
        self.web = DocumentWebView(user_content_manager=manager)
        self.web.set_hexpand(True)
        self.web.set_vexpand(False)
        self.web.set_size_request(0, self._height)
        settings = self.web.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_html5_database(False)
        settings.set_enable_html5_local_storage(False)
        settings.set_allow_file_access_from_file_urls(True)
        color = Gdk.RGBA()
        color.parse('transparent')
        self.web.set_background_color(color)
        self._web_handlers = [self.web.connect('decide-policy', self.navigation),
                              self.web.connect('load-failed', self.load_failed)]
        self.append(self.web)
        self.set_hexpand(True)
        self.set_vexpand(False)
        self._map_handler = self.connect('map', self.start)
        self._scroll = ui.scroller.get_vadjustment()
        self._scroll_handler = self._scroll.connect('value-changed', self.schedule_viewport)
        ui.documents.add(self)
        ui.style.bind(self)

    def close_document(self):
        if self._closed:
            return
        self._closed = True
        if self._reload_source:
            GLib.source_remove(self._reload_source)
            self._reload_source = 0
        self._scroll.disconnect(self._scroll_handler)
        if self._viewport_source:
            self.ui.window.remove_tick_callback(self._viewport_source)
            self._viewport_source = 0
        self.ui.documents.discard(self)
        self.disconnect(self._map_handler)
        self.manager.disconnect(self._message_handler)
        self.manager.unregister_script_message_handler('document', None)
        for handler in self._web_handlers:
            self.web.disconnect(handler)
        self.web.stop_loading()
        self.remove(self.web)
        self.web.run_dispose()

    def start(self, *args):
        if not self._started:
            self._started = True
            self.reload()

    def background(self):
        found, color = self.ui.window.get_style_context().lookup_color('window_bg_color')
        return color.to_string() if found else ('#222226' if self.ui.style.manager.get_dark() else '#fafafb')

    def reload(self):
        self._reload_source = 0
        self._loaded = False
        if self._started and not self._closed:
            if self._next_document is not None:
                self.document, self._next_document = self._next_document, None
            self._document_token = uuid.uuid4().hex
            self.metrics['loads'] += 1
            self.web.load_html(html_page(self.document, self.ui.style.manager.get_dark(),
                                        self.display, self.background(), self._document_token), self.base.as_uri() + '/')
        return GLib.SOURCE_REMOVE

    def set_text(self, source, literal=False):
        if source == self.source and literal == self._literal:
            return
        self.source, self._literal = source, literal
        self._next_document = (Document('<p style="white-space:pre-wrap">' + html.escape(source) + '</p>', [], set(), False, False)
                         if literal else compile_document(source, self.base))
        if self._reload_source:
            GLib.source_remove(self._reload_source)
            self._reload_source = 0
        if self._started and self._loaded:
            self._reload_source = GLib.idle_add(self.flush_text if literal else self.reload)

    def flush_text(self):
        self._reload_source = 0
        if self._next_document is not None:
            self.document, self._next_document = self._next_document, None
        self.metrics['text_updates'] += 1
        self.evaluate('window.documentText(' + json.dumps(self.source) + ')')
        return GLib.SOURCE_REMOVE

    def schedule_viewport(self, *args):
        if not self._viewport_source and self.dialog_dragging and self.get_mapped():
            self._viewport_source = self.ui.window.add_tick_callback(self.send_viewport)

    def send_viewport(self, *args):
        self._viewport_source = 0
        found, bounds = self.web.compute_bounds(self.ui.scroller)
        if found and self.get_mapped() and self._loaded:
            origin = bounds.get_y()
            top = -origin
            bottom = self.ui.scroller.get_height() - origin
            viewport = (top, bottom, origin)
            if viewport != self._last_viewport:
                self._last_viewport = viewport
                self.evaluate(f'window.documentViewport({top}, {bottom}, {origin})')
        return GLib.SOURCE_REMOVE

    @property
    def dialog_ready(self):
        return (self._loaded and abs(self._measured_width - self.web.get_width()) <= 1
                and abs(self._height - self.web.get_height()) <= 1)

    def evaluate(self, script):
        if self.ui._finished or self._closed or not self._started:
            return
        self.web.evaluate_javascript(script, -1, None, None, None, None, None)

    def document_theme(self, dark):
        self.evaluate('window.documentTheme && window.documentTheme(' + json.dumps(dark) + ', ' +
                      json.dumps(self.ui.style.font.get_family()) + ', ' + json.dumps(self.background()) + ')')

    def message(self, manager, value):
        if self.ui._finished or self._closed:
            return
        try:
            message = json.loads(value.to_string())
            if message.get('document') != self._document_token:
                return
            kind = message.get('type')
            counts = self.metrics['messages']
            counts[kind] = counts.get(kind, 0) + 1
            if kind == 'size':
                width, height = float(message['width']), float(message['height'])
                if not math.isfinite(height) or width < 32 or height < 0:
                    return
                self._measured_width = width
                height = max(1, math.ceil(height))
                if self._height != height:
                    self._height = height
                    self.web.set_size_request(0, height)
                    self.ui.layout.request()
            elif kind == 'ready':
                self._loaded = True
                self.document_theme(self.ui.style.manager.get_dark())
                self.ui.layout.request()
                if self._literal:
                    self.flush_text()
                self.send_viewport()
            elif kind == 'selection':
                self.dialog_has_selection = bool(message['selected'])
                if not self.dialog_has_selection:
                    self.ui.layout.request()
            elif kind == 'drag':
                self.dialog_dragging = bool(message['active'])
                if self.dialog_dragging:
                    self._last_viewport = None
                    self.send_viewport()
                else:
                    self.ui.layout.request()
            elif kind == 'copy':
                index = message.get('index')
                if type(index) is int and 0 <= index < len(self.document.codes):
                    self.ui.Gdk.Display.get_default().get_clipboard().set(self.document.codes[index])
                    self.evaluate(f'window.documentCopied({index})')
            elif kind == 'link':
                uri = message.get('uri', '')
                if urlsplit(uri).scheme in {'http', 'https', 'mailto', 'file'}:
                    self.ui.Gio.AppInfo.launch_default_for_uri(uri, None)
            elif kind in {'scroll', 'anchor'}:
                adjustment = self.ui.scroller.get_vadjustment()
                if kind == 'scroll':
                    position = adjustment.get_value() + float(message['delta'])
                else:
                    found, bounds = self.compute_bounds(self.ui.content)
                    if not found:
                        return
                    position = bounds.get_y() + float(message['top'])
                if math.isfinite(position):
                    adjustment.set_value(position)
            elif kind == 'extension-error':
                print('Document extension: ' + str(message.get('message')), flush=True)
        except (ValueError, TypeError, KeyError) as error:
            print(f'Document bridge: {error}', flush=True)

    def navigation(self, view, decision, kind):
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            action = decision.get_navigation_action()
            if action.get_navigation_type() == WebKit.NavigationType.LINK_CLICKED:
                uri = action.get_request().get_uri()
                decision.ignore()
                if urlsplit(uri).scheme in {'http', 'https', 'mailto', 'file'}:
                    self.ui.Gio.AppInfo.launch_default_for_uri(uri, None)
                return True
        if kind == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
            decision.ignore()
            return True
        return False

    def load_failed(self, view, event, uri, error):
        self._loaded = True
        self._measured_width = self.web.get_width()
        print(f'Document load failed: {error.message}', flush=True)
        return False
