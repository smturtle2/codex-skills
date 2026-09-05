from gi.repository import Gtk


def box(spacing=16):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


class Flow:
    def __init__(self, ui):
        self.ui = ui
        self.root = box()
        self.heading = Gtk.Label(xalign=0, wrap=True)
        self.heading.add_css_class("title-1")
        self.position = Gtk.Label(xalign=0)
        self.position.add_css_class("dim-label")
        self.root.append(self.position)
        self.root.append(self.heading)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.root.append(self.stack)
        self.pages = []
        self.index = 0
        self.back = ui.action("back", "이전", callback=lambda: self.go(self.index - 1))
        self.next = ui.action("next", "다음", primary=True, callback=self.advance)
        self.send = ui.action("send", "보내기", primary=True, default=False)
        self.send.set_visible(False)
        ui.set_validator(self.validate)

    def add(self, title, widget, check=None):
        page = box()
        page.set_margin_start(8)
        page.set_margin_end(8)
        page.set_margin_top(6)
        page.set_margin_bottom(12)
        page.append(widget)
        self.stack.add_named(page, str(len(self.pages)))
        self.pages.append((title, check))

    def go(self, index):
        self.index = max(0, min(len(self.pages) - 1, index))
        self.stack.set_visible_child_name(str(self.index))
        self.heading.set_text(self.pages[self.index][0])
        self.position.set_text(f"{self.index + 1} / {len(self.pages)}")
        self.back.set_sensitive(self.index > 0)
        last = self.index == len(self.pages) - 1
        self.next.set_visible(not last)
        self.send.set_visible(last)
        self.ui.set_default_action(self.send if last else self.next)
        self.ui.message("")

    def advance(self):
        check = self.pages[self.index][1]
        error = check() if check else None
        if error:
            self.ui.message(error[0])
            self.ui.focus(error[1])
        else:
            self.go(self.index + 1)

    def validate(self, values):
        for index, (_, check) in enumerate(self.pages):
            error = check() if check else None
            if error:
                self.go(index)
                self.ui.focus(error[1])
                return error[0]
        return None

    def ready(self):
        self.go(0)
        return self.root


def add_control(Adw, group, title, widget):
    item = Adw.ActionRow(title=title)
    widget.set_valign(Gtk.Align.CENTER)
    item.add_suffix(widget)
    group.add(item)
    return item
