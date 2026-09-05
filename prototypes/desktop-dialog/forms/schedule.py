from shared import Flow, box, add_control


def build(ui):
    Gtk, Adw = ui.Gtk, ui.Adw
    flow = Flow(ui)
    date_page = box()
    calendar = Gtk.Calendar()
    calendar.set_halign(Gtk.Align.CENTER)
    date_page.append(calendar)
    time = Adw.PreferencesGroup()
    clock = Gtk.Box(spacing=8)
    hour = Gtk.SpinButton.new_with_range(0, 23, 1)
    minute = Gtk.SpinButton.new_with_range(0, 59, 5)
    clock.append(hour)
    clock.append(Gtk.Label(label=":"))
    clock.append(minute)
    add_control(Adw, time, "시작 시간", clock)
    date_page.append(time)
    flow.add("언제가 편하신가요?", date_page)
    preferences = Adw.PreferencesGroup()
    location = Adw.ComboRow(title="진행 방식", model=Gtk.StringList.new(["온라인", "직접 만나기"]))
    location.set_selected(Gtk.INVALID_LIST_POSITION)
    preferences.add(location)
    address = Adw.EntryRow(title="만날 장소")
    address.set_visible(False)
    preferences.add(address)
    def place(*args):
        address.set_visible(location.get_selected() == 1)
        if ui._built:
            ui.refit()
            if address.get_visible():
                ui.focus(address)
    location.connect("notify::selected", place)
    duration = Gtk.SpinButton.new_with_range(15, 240, 15)
    add_control(Adw, preferences, "소요 시간 · 분", duration)
    memo = Adw.EntryRow(title="덧붙일 내용 · 선택")
    preferences.add(memo)
    def check():
        if location.get_selected() == Gtk.INVALID_LIST_POSITION:
            return "진행 방식을 선택해 주세요.", location
        if location.get_selected() == 1 and not address.get_text().strip():
            return "만날 장소를 입력해 주세요.", address
    flow.add("세부 내용을 알려 주세요", preferences, check)
    ui.bind("date", lambda: calendar.get_date().format("%Y-%m-%d"), lambda value: calendar.select_day(ui.GLib.DateTime.new_from_iso8601(value + "T12:00:00", ui.GLib.TimeZone.new_local())))
    ui.bind("hour", hour.get_value_as_int, hour.set_value)
    ui.bind("minute", minute.get_value_as_int, minute.set_value)
    ui.bind("mode", lambda: None if location.get_selected() == Gtk.INVALID_LIST_POSITION else location.get_selected(), lambda value: location.set_selected(Gtk.INVALID_LIST_POSITION if value is None else value))
    ui.bind("location", address.get_text, address.set_text)
    ui.bind("duration_minutes", duration.get_value_as_int, duration.set_value)
    ui.bind("memo", memo.get_text, memo.set_text)
    return flow.ready()
