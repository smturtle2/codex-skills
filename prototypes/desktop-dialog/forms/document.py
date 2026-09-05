from shared import Flow, box, add_control


def build(ui):
    Gtk, Adw = ui.Gtk, ui.Adw
    flow = Flow(ui)
    basic = Adw.PreferencesGroup()
    title = Adw.EntryRow(title="문서 제목")
    audience = Adw.ComboRow(title="읽는 사람", model=Gtk.StringList.new(["나", "팀원", "외부 독자"]))
    audience.set_selected(Gtk.INVALID_LIST_POSITION)
    basic.add(title)
    basic.add(audience)
    def check():
        if not title.get_text().strip():
            return "문서 제목을 입력해 주세요.", title
        if audience.get_selected() == Gtk.INVALID_LIST_POSITION:
            return "읽는 사람을 선택해 주세요.", audience
    flow.add("어떤 문서를 만들까요?", basic, check)
    options = box(18)
    group = Adw.PreferencesGroup(title="분량과 구성")
    pages = Gtk.SpinButton.new_with_range(1, 30, 1)
    add_control(Adw, group, "목표 페이지 수", pages)
    summary = Gtk.Switch()
    add_control(Adw, group, "앞부분에 요약 넣기", summary)
    custom = Gtk.Switch()
    add_control(Adw, group, "별도 요청 추가", custom)
    request = Adw.EntryRow(title="추가로 원하는 내용")
    request.set_visible(False)
    group.add(request)
    def toggle(*args):
        request.set_visible(custom.get_active())
        if ui._built:
            ui.refit()
            if custom.get_active():
                ui.focus(request)
    custom.connect("notify::active", toggle)
    options.append(group)
    options.append(Gtk.Label(label="말투 · 편안하게 ↔ 격식 있게", xalign=0))
    tone = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 10)
    tone.set_value(50)
    tone.set_draw_value(True)
    options.append(tone)
    flow.add("세부 내용을 조절해 주세요", options)
    ui.bind("title", title.get_text, title.set_text)
    ui.bind("audience", lambda: None if audience.get_selected() == Gtk.INVALID_LIST_POSITION else audience.get_selected(), lambda value: audience.set_selected(Gtk.INVALID_LIST_POSITION if value is None else value))
    ui.bind("pages", pages.get_value_as_int, pages.set_value)
    ui.bind("include_summary", summary.get_active, summary.set_active)
    ui.bind("custom_request", custom.get_active, custom.set_active)
    ui.bind("request", request.get_text, request.set_text)
    ui.bind("tone", lambda: int(tone.get_value()), tone.set_value)
    return flow.ready()
