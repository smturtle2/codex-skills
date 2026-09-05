from shared import Flow, box, add_control


def build(ui):
    Gtk, Adw = ui.Gtk, ui.Adw
    flow = Flow(ui)
    choices = Gtk.Box(spacing=14, homogeneous=True)
    selected = {"value": None}
    checks = {}
    first = None
    for key, title, filename in [("calm", "잔잔한 흐름", "calm.svg"), ("bold", "선명한 대비", "bold.svg")]:
        card = box(12)
        card.add_css_class("card")
        for side in ("top", "bottom", "start", "end"):
            getattr(card, f"set_margin_{side}")(3)
        picture = Gtk.Picture.new_for_filename(str(ui.view_dir / "assets" / filename))
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(160, 110)
        card.append(picture)
        check = Gtk.CheckButton(label=title)
        check.set_margin_start(12)
        check.set_margin_end(12)
        check.set_margin_bottom(14)
        if first:
            check.set_group(first)
        first = check
        check.connect("toggled", lambda control, value=key: selected.update(value=value) if control.get_active() else None)
        checks[key] = check
        card.append(check)
        choices.append(card)
    flow.add("어느 분위기가 좋으세요?", choices, lambda: None if selected["value"] else ("마음에 드는 이미지를 선택해 주세요.", checks["calm"]))
    extras = box(16)
    preview = Gtk.Picture()
    preview.set_content_fit(Gtk.ContentFit.CONTAIN)
    preview.set_size_request(-1, 110)
    preview.set_visible(False)
    filename = Gtk.Label(label="선택한 파일 없음", xalign=0, wrap=True)
    path = {"value": None}
    def restore(value):
        path["value"] = value
        filename.set_text(ui.Gio.File.new_for_path(value).get_basename() if value else "선택한 파일 없음")
        preview.set_filename(value)
        preview.set_visible(bool(value))
        if ui._built:
            ui.refit()
    def picked(dialog, result):
        try:
            restore(dialog.open_finish(result).get_path())
        except ui.GLib.Error as error:
            if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                ui.message(str(error))
    def select(*args):
        dialog = Gtk.FileDialog(title="참고 이미지 선택")
        filter = Gtk.FileFilter()
        filter.set_name("이미지")
        filter.add_pixbuf_formats()
        filter.add_pattern("*.svg")
        filters = ui.Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter)
        dialog.set_filters(filters)
        dialog.open(ui.window, None, picked)
    line = Gtk.Box(spacing=10)
    choose = Gtk.Button(label="참고 이미지 선택")
    choose.connect("clicked", select)
    remove = Gtk.Button(label="제거")
    remove.connect("clicked", lambda *_: restore(None))
    line.append(choose)
    line.append(remove)
    extras.append(line)
    extras.append(filename)
    extras.append(preview)
    group = Adw.PreferencesGroup(title="함께 반영할 요소")
    flags = {}
    for key, title in [("colors", "색상"), ("layout", "배치"), ("texture", "질감")]:
        check = Gtk.CheckButton()
        add_control(Adw, group, title, check)
        flags[key] = check
        ui.bind(key, check.get_active, check.set_active)
    extras.append(group)
    flow.add("참고할 자료도 함께 골라 주세요", extras)
    ui.bind("direction", lambda: selected["value"], lambda value: checks[value].set_active(True) if value in checks else None)
    ui.bind("reference", lambda: path["value"], restore)
    return flow.ready()
