class_name ValidationPanel
extends PanelContainer
## The validation panel: every diagnostic the runner produced, grouped by
## severity, each with its code, its location and what to do about it.
##
## A diagnostic the model reported keeps the model's own severity. The panel does
## not reclassify anything -- it renders.

var _list: VBoxContainer = null
var _summary_label: Label = null
var _count_label: Label = null
var _on_diagnostic_selected: Callable = Callable()


func setup() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	vb.add_child(header)

	_summary_label = Label.new()
	_summary_label.text = "Not run"
	_summary_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_summary_label.add_theme_font_size_override("font_size", 13)
	header.add_child(_summary_label)

	_count_label = Label.new()
	_count_label.text = ""
	_count_label.add_theme_font_size_override("font_size", 11)
	header.add_child(_count_label)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(scroll)

	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 3)
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_list)


func bind_selection(callback: Callable) -> void:
	_on_diagnostic_selected = callback


func show_diagnostics(payload: Dictionary) -> void:
	if _list == null:
		return
	for child in _list.get_children():
		child.queue_free()

	var diagnostics: Array = payload.get("diagnostics", [])
	var errors := 0
	var warnings := 0
	var infos := 0
	for d in diagnostics:
		match str(d.get("severity", "info")):
			"error":
				errors += 1
			"warning":
				warnings += 1
			_:
				infos += 1

	_summary_label.text = CompositionRunner.status_summary(payload)
	match CompositionRunner.status_severity(payload):
		"ok":
			_summary_label.modulate = Color(0.62, 0.88, 0.62)
		"warning":
			_summary_label.modulate = Color(0.95, 0.82, 0.45)
		_:
			_summary_label.modulate = Color(0.95, 0.58, 0.52)
	_count_label.text = "%d errors, %d warnings, %d notes" % [errors, warnings, infos]

	if diagnostics.is_empty():
		var empty := Label.new()
		empty.text = "No diagnostics. The graph validated and executed without a remark."
		empty.modulate = Color(0.62, 0.88, 0.62)
		_list.add_child(empty)
		return

	for d in diagnostics:
		_list.add_child(_diagnostic_row(d))


func _diagnostic_row(d: Dictionary) -> Control:
	var row := PanelContainer.new()
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 2)
	row.add_child(vb)

	var colour := Color(0.62, 0.88, 0.62)
	match str(d.get("severity", "info")):
		"error":
			colour = Color(0.95, 0.58, 0.52)
		"warning":
			colour = Color(0.95, 0.82, 0.45)
		_:
			colour = Color(0.62, 0.78, 0.95)
	row.add_theme_stylebox_override("panel", _panel_style(colour))

	var title := HBoxContainer.new()
	title.add_theme_constant_override("separation", 6)
	vb.add_child(title)

	var badge := Label.new()
	badge.text = str(d.get("severity", "info")).to_upper()
	badge.add_theme_font_size_override("font_size", 10)
	badge.modulate = colour
	title.add_child(badge)

	var code := Label.new()
	code.text = str(d.get("code", ""))
	code.add_theme_font_size_override("font_size", 11)
	code.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_child(code)

	var origin := str(d.get("origin", "composition"))
	if origin != "composition":
		var origin_label := Label.new()
		origin_label.text = "[%s]" % origin
		origin_label.add_theme_font_size_override("font_size", 10)
		origin_label.modulate = colour
		title.add_child(origin_label)

	var message := Label.new()
	message.text = str(d.get("message", ""))
	message.autowrap_mode = TextServer.AUTOWRAP_WORD
	message.add_theme_font_size_override("font_size", 11)
	vb.add_child(message)

	var where: Array = d.get("where", [])
	if not where.is_empty():
		var location := Label.new()
		location.text = "at " + " / ".join(where)
		location.add_theme_font_size_override("font_size", 10)
		location.modulate = Color(1, 1, 1, 0.55)
		vb.add_child(location)

	var remediation := str(d.get("remediation", ""))
	if remediation != "":
		var fix := Label.new()
		fix.text = "do:  " + remediation
		fix.autowrap_mode = TextServer.AUTOWRAP_WORD
		fix.add_theme_font_size_override("font_size", 10)
		fix.modulate = Color(0.72, 0.92, 0.78)
		vb.add_child(fix)

	if not _on_diagnostic_selected.is_null():
		row.mouse_filter = Control.MOUSE_FILTER_STOP
		row.gui_input.connect(func(event):
			if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
				_on_diagnostic_selected.call(d)
		)

	return row


func _panel_style(colour: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(colour.r, colour.g, colour.b, 0.12)
	sb.border_color = Color(colour.r, colour.g, colour.b, 0.55)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(4)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	return sb


func clear() -> void:
	if _list == null:
		return
	for child in _list.get_children():
		child.queue_free()
	_summary_label.text = "Not run"
	_count_label.text = ""
