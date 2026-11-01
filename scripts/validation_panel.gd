class_name ValidationPanel
extends PanelContainer
## The validation panel: every diagnostic the runner produced, grouped by
## severity, each with its code, its location and what to do about it.
##
## A diagnostic the model reported keeps the model's own severity. The panel does
## not reclassify anything -- it renders.
##
## Every structured field the runner published is kept: `code`, `severity`,
## `origin`, `where`, `model_id`, `model_version`, `detail`, `remediation`, and
## both `message` (origin-prefixed) and `raw_message` (not). A field the runner did
## not send is shown as absent, never guessed at, so a thin diagnostic stays
## visibly thin.

var _list: VBoxContainer = null
var _summary_label: Label = null
var _count_label: Label = null
var _on_diagnostic_selected: Callable = Callable()
## Longest `detail` rendering before it is elided. A traceback belongs in the
## runner's output, not in a panel row.
const MAX_DETAIL_CHARS := 1200


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

	if not payload.has("diagnostics"):
		# An absent diagnostics key is not an absence of diagnostics. The runner
		# publishes the key on every document it writes, so a document without it
		# did not come from a runner this panel understands, and saying "no
		# diagnostics" here would read as a clean run.
		_summary_label.text = "No diagnostics field in this document"
		_summary_label.modulate = Color(0.95, 0.72, 0.45)
		_count_label.text = ""
		var missing := Label.new()
		missing.text = (
			"The result document has no 'diagnostics' key. This is not a clean run: "
			+ "it means the document was not produced by this runner, or it did not "
			+ "survive the boundary intact."
		)
		missing.autowrap_mode = TextServer.AUTOWRAP_WORD
		missing.modulate = Color(0.95, 0.72, 0.45)
		_list.add_child(missing)
		return

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
		empty.text = (
			"No diagnostics. The runner reported none for this run -- which is not "
			+ "the same as a statement that the result is scientifically correct."
		)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD
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

	var model_id := str(d.get("model_id", ""))
	var model_version := str(d.get("model_version", ""))
	if model_id != "":
		# Which model, at which version. A finding about a model's own source is
		# not the same claim as a finding about the composition.
		var subject := Label.new()
		subject.text = model_id if model_version == "" else "%s@%s" % [model_id, model_version]
		subject.add_theme_font_size_override("font_size", 10)
		subject.modulate = Color(1, 1, 1, 0.55)
		title.add_child(subject)

	var message := Label.new()
	message.text = str(d.get("message", ""))
	message.autowrap_mode = TextServer.AUTOWRAP_WORD
	message.add_theme_font_size_override("font_size", 11)
	vb.add_child(message)

	# `message` carries the origin prefix the runner added; `raw_message` is the
	# text without it. Showing both keeps a reader from having to strip one to
	# match a message against a log.
	var raw := str(d.get("raw_message", ""))
	var prefixed := str(d.get("message", ""))
	if raw != "" and raw != prefixed:
		var raw_label := Label.new()
		raw_label.text = "unprefixed:  " + raw
		raw_label.autowrap_mode = TextServer.AUTOWRAP_WORD
		raw_label.add_theme_font_size_override("font_size", 10)
		raw_label.modulate = Color(1, 1, 1, 0.45)
		vb.add_child(raw_label)

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

	var detail: Variant = d.get("detail", {})
	if detail is Dictionary and not (detail as Dictionary).is_empty():
		var rendered: String = _render_detail(detail as Dictionary)
		if rendered != "":
			var detail_label := Label.new()
			detail_label.text = rendered
			detail_label.autowrap_mode = TextServer.AUTOWRAP_WORD
			detail_label.add_theme_font_size_override("font_size", 10)
			detail_label.modulate = Color(1, 1, 1, 0.45)
			vb.add_child(detail_label)

	if not _on_diagnostic_selected.is_null():
		row.mouse_filter = Control.MOUSE_FILTER_STOP
		row.gui_input.connect(func(event):
			if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
				_on_diagnostic_selected.call(d)
		)

	return row


## Render the `detail` mapping the runner attached, one `key: value` per line.
##
## Detail is evidence, so it is shown verbatim and elided only when it is too
## long to read. Nothing here interprets a key: `blocked_by` and `traceback` are
## displayed, not classified.
func _render_detail(detail: Dictionary) -> String:
	var lines := PackedStringArray()
	for key in detail.keys():
		var value: Variant = detail[key]
		if value is Dictionary or value is Array:
			var text := JSON.stringify(value)
			if text.length() > MAX_DETAIL_CHARS:
				text = "%s ... (%d characters)" % [
					text.substr(0, MAX_DETAIL_CHARS), text.length(),
				]
			lines.append("%s: %s" % [str(key), text])
		else:
			lines.append("%s: %s" % [str(key), _clip(str(value))])
	return "detail:\n" + "\n".join(lines)


func _clip(text: String) -> String:
	if text.length() <= MAX_DETAIL_CHARS:
		return text
	return "%s ... (%d characters)" % [
		text.substr(0, MAX_DETAIL_CHARS), text.length(),
	]


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
