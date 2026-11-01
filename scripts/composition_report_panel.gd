class_name CompositionReportPanel
extends PanelContainer
## The evidence-backed composition report, rendered from what the runner wrote.
##
## ## What it shows, and why it is a separate tab
##
## The **Validation** tab answers "what did the runner object to?". This one
## answers four different questions that are routinely collapsed into one:
##
##   * did the connection hold mechanically? (quantity, unit, direction, component)
##   * does it mean anything between *these two models*?
##   * did it run?
##   * is any of it scientifically validated?
##
## A graph can be mechanically fine, semantically refused, unrun, and entirely
## unvalidated at once, and this panel keeps those four apart. It renders the
## runner's `composition_report` field verbatim -- it holds no rule of its own,
## has no list of model ids, and reaches no verdict the runner did not publish.
##
## ## Staleness
##
## A report describes one attempt at one graph. When the graph changes, the
## report describes a graph that is no longer on screen, so `mark_stale()` says
## so in place rather than leaving a previous successful assessment looking
## current. The same rule that invalidates results invalidates this.

## Longest `detail` rendering before it is elided, so a traceback belongs in the
## diagnostics view and not in a report row.
const MAX_EVIDENCE_CHARS := 600

var _header: Label = null
var _subheader: Label = null
var _body: VBoxContainer = null
var _stale := false
var _shown := false


func _init() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	_header = Label.new()
	_header.text = "Not run"
	_header.add_theme_font_size_override("font_size", 13)
	vb.add_child(_header)

	_subheader = Label.new()
	_subheader.add_theme_font_size_override("font_size", 10)
	_subheader.autowrap_mode = TextServer.AUTOWRAP_WORD
	_subheader.modulate = Color(1, 1, 1, 0.6)
	vb.add_child(_subheader)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(scroll)

	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 4)
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_body)


## Render the report the runner published on `payload`.
##
## A document with no `composition_report` key is not a document without
## anything to report: the runner publishes the field on every document it
## writes, so its absence means the document did not survive the boundary. That
## is said here rather than rendered as an empty report.
func show_report(payload: Dictionary) -> void:
	_clear()
	_stale = false
	_shown = true

	if not payload.has("composition_report"):
		_header.text = "No composition report in this document"
		_header.modulate = Color(0.95, 0.72, 0.45)
		_subheader.text = (
			"The runner publishes a report on every document it writes. This one "
			+ "has none, so it did not come from this runner or did not survive "
			+ "the boundary intact. This is not a clean run."
		)
		return

	var report: Dictionary = payload["composition_report"]
	var schema := str(report.get("schema", "?"))
	if schema != _expected_schema():
		_header.text = "Composition report schema %s" % schema
		_header.modulate = Color(0.95, 0.72, 0.45)
		_subheader.text = (
			"This panel renders report schema %s and does not recognise %s. The "
			% [_expected_schema(), schema]
			+ "fields it does not know are left unread rather than guessed at."
		)
		return

	_render(report)


func _expected_schema() -> String:
	return "composition-report/1"


## A graph the editor refused before the runner was ever invoked.
##
## `GraphDocument.validate_shape()` runs in GDScript and short-circuits the
## Run button, so there is no result document and therefore no report from the
## runner. Showing "no report" there would be wrong in a specific way: it would
## read as "the runner had nothing to say" when in fact the runner was never
## asked. So the panel says which of the two happened.
func show_graph_problems(graph_id: String, problems: Array) -> void:
	_clear()
	_stale = false
	_shown = true
	_header.text = "Composition report — %s" % graph_id
	_header.modulate = Color(0.95, 0.58, 0.52)
	_subheader.text = (
		"The editor rejected this graph's shape before the runner was invoked. "
		+ "No connection was assessed, and nothing below is a judgement about "
		+ "the models it names."
	)
	var box := _card(Color(0.95, 0.58, 0.52))
	box.add_child(_heading("Why the runner was not called (%d)" % problems.size()))
	for problem in problems:
		box.add_child(_bullet(str(problem)))
	box.add_child(_note(
		"Fix these and run again; the runner will then produce the real report."
	))
	_body.add_child(box)


## The report describes a graph that is no longer the one on screen.
func mark_stale(reason: String) -> void:
	if not _shown:
		return
	_stale = true
	var banner := Label.new()
	banner.text = "STALE — this report describes a graph that has since changed (%s)." % reason
	banner.autowrap_mode = TextServer.AUTOWRAP_WORD
	banner.add_theme_font_size_override("font_size", 11)
	banner.modulate = Color(0.95, 0.82, 0.45)
	_body.add_child(banner)
	_body.move_child(banner, 0)
	_header.modulate = Color(0.95, 0.82, 0.45)


func is_stale() -> bool:
	return _stale


func clear() -> void:
	_clear()
	_stale = false
	_shown = false
	_header.text = "Not run"
	_header.modulate = Color(1, 1, 1, 1)
	_subheader.text = "Run a graph to produce a composition report."


func _clear() -> void:
	if _body == null:
		return
	for child in _body.get_children():
		_body.remove_child(child)
		child.queue_free()


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


func _render(report: Dictionary) -> void:
	var graph: Dictionary = report.get("graph", {})
	var execution: Dictionary = report.get("execution", {})
	var science: Dictionary = report.get("science", {})

	_header.text = "Composition report — %s" % str(graph.get("graph_id", "?"))
	_header.modulate = Color(0.78, 0.86, 0.96)
	_subheader.text = str(
		(report.get("reading_guide", {}) as Dictionary).get("note", "")
	)

	_body.add_child(_execution_block(execution))
	_body.add_child(_heading("Connections (%d)" % (report.get("connections", []) as Array).size()))
	var connections: Array = report.get("connections", [])
	if connections.is_empty():
		_body.add_child(_note(
			"This graph declares no connections. Nothing had to be assessed, which "
			+ "is not a statement that the graph is correct."
		))
	for connection in connections:
		_body.add_child(_connection_card(connection))
	_body.add_child(_science_block(science))


## A. Execution summary, kept visibly separate from B and C.
func _execution_block(execution: Dictionary) -> Control:
	var box := _card(Color(0.66, 0.78, 0.94))
	var produced := bool(execution.get("results_produced", false))
	box.add_child(_line("execution",
		("ran, %d result(s)" % int(execution.get("result_count", 0)))
		if produced else "no model produced a result",
		Color(0.62, 0.88, 0.62) if produced else Color(0.95, 0.72, 0.45)))
	box.add_child(_line("status", str(execution.get("status", "?"))))
	box.add_child(_line("attempted",
		"no — plan-only run" if bool(execution.get("plan_only", false))
		else ("yes" if bool(execution.get("attempted", false)) else "no")))
	box.add_child(_line("diagnostics", "%s error(s), %s warning(s)" % [
		str(execution.get("error_count", 0)), str(execution.get("warning_count", 0))]))
	box.add_child(_line("run id", str(execution.get("run_id", "?"))))
	box.add_child(_line("graph digest", str(execution.get("reproducibility", "?"))))
	if bool(execution.get("results_invalidated", false)):
		box.add_child(_line("previous results", "invalidated", Color(0.95, 0.82, 0.45)))
	var note := str(execution.get("note", ""))
	if note != "" and note != "not_documented":
		box.add_child(_note(note))
	return box


## B. One card per connection. The disposition is the headline; everything else
## is evidence for it.
func _connection_card(connection: Dictionary) -> Control:
	var disposition := str(connection.get("disposition", "?"))
	var colour := _disposition_colour(disposition)
	var box := _card(colour)

	var source: Dictionary = connection.get("source", {})
	var destination: Dictionary = connection.get("destination", {})

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	var badge := Label.new()
	badge.text = disposition.replace("_", " ").to_upper()
	badge.add_theme_font_size_override("font_size", 10)
	badge.modulate = colour
	head.add_child(badge)
	var cid := Label.new()
	cid.text = str(connection.get("connection_id", "?"))
	cid.add_theme_font_size_override("font_size", 11)
	cid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(cid)
	box.add_child(head)

	box.add_child(_note("%s  →  %s" % [_endpoint(source), _endpoint(destination)]))

	var dimensional: Dictionary = connection.get("dimensional", {})
	var semantic: Dictionary = connection.get("semantic", {})
	box.add_child(_line("mechanical",
		"dimensional: %s   ·   semantic: %s" % [
			str(dimensional.get("result", "?")),
			str(semantic.get("result", "?"))],
		colour))

	var explanation := str(connection.get("disposition_explanation", ""))
	if explanation != "":
		box.add_child(_note(explanation))

	var diagnostic: Dictionary = connection.get("diagnostic", {})
	var code := str(diagnostic.get("code", "not_documented"))
	if code != "not_documented":
		box.add_child(_line("diagnostic", "%s [%s]" % [
			code, str(diagnostic.get("severity", "?"))]))
		box.add_child(_note(str(diagnostic.get("message", ""))))

	var stance := str(semantic.get("stance", ""))
	if stance != "not_documented":
		var basis := str(semantic.get("evidence_basis", "?"))
		box.add_child(_line("rule", "%s  ·  evidence basis: %s" % [
			str(semantic.get("rule", "?")), basis]))
		box.add_child(_note(str(semantic.get("reason", ""))))

	for heading in ["assumptions", "evidence", "unresolved"]:
		var entries: Array = connection.get(heading, [])
		if entries.is_empty():
			continue
		box.add_child(_subheading("%s (%d)" % [heading.capitalize(), entries.size()]))
		for entry in entries:
			box.add_child(_bullet(str(entry)))

	var remediation := str(connection.get("remediation", ""))
	if remediation != "" and remediation != "not_documented":
		box.add_child(_line("remediation", remediation, Color(0.72, 0.92, 0.78)))

	var other: Array = connection.get("other_diagnostics", [])
	if not other.is_empty():
		box.add_child(_note("%d further diagnostic(s) name this connection; see "
			% other.size() + "the Validation tab."))
	return box


func _endpoint(port: Dictionary) -> String:
	return "%s/%s  (%s, %s)" % [
		str(port.get("instance_id", "?")), str(port.get("port_id", "?")),
		str(port.get("quantity", "?")), str(port.get("unit", "?"))]


## C. Scientific limitations. Never inherits from the parts.
func _science_block(science: Dictionary) -> Control:
	var box := _card(Color(0.95, 0.82, 0.45))
	box.add_child(_heading("Scientific status"))
	var models: Array = science.get("models", [])
	for entry in models:
		var model_id := str(entry.get("model_id", "?"))
		var line := "%s" % model_id
		var reproduction := str(entry.get("reproduction_status", "not_documented"))
		var implementation := str(entry.get("implementation_status", "not_documented"))
		line += "  —  reproduction: %s, implementation: %s" % [reproduction, implementation]
		box.add_child(_line(str(entry.get("instance_id", model_id)), line))
		var basis := str(entry.get("basis", ""))
		if basis != "":
			box.add_child(_note(basis))
		var limitations: Dictionary = entry.get("limitations", {})
		var unsupported: Array = limitations.get("declared_unsupported_capabilities", [])
		if not unsupported.is_empty():
			box.add_child(_note("declares it does not support: "
				+ ", ".join(PackedStringArray(unsupported))))
		var missing: Array = limitations.get("declared_missing_information", [])
		if not missing.is_empty():
			box.add_child(_note("%d declared missing-information item(s) on its "
				% missing.size() + "own manifest"))

	var combined: Dictionary = science.get("combined_graph", {})
	var validated := bool(combined.get("independently_validated", false))
	box.add_child(_line("combined graph",
		("independently validated" if validated else "not established"),
		Color(0.62, 0.88, 0.62) if validated else Color(0.95, 0.82, 0.45)))
	box.add_child(_note(str(combined.get("basis", ""))))
	box.add_child(_note(str(combined.get("execution_is_not_validation", ""))))
	return box


# --------------------------------------------------------------------------- #
# small builders, matching the conventions the other panels use
# --------------------------------------------------------------------------- #


func _disposition_colour(disposition: String) -> Color:
	match disposition:
		"permitted":
			return Color(0.62, 0.88, 0.62)
		"permitted_conditionally":
			return Color(0.80, 0.86, 0.55)
		"mechanically_invalid":
			return Color(0.95, 0.58, 0.52)
		"scientifically_refused":
			return Color(0.95, 0.72, 0.45)
		"unresolved":
			return Color(0.72, 0.68, 0.95)
	return Color(1, 1, 1, 0.6)


func _card(colour: Color) -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(colour.r, colour.g, colour.b, 0.10)
	style.border_color = Color(colour.r, colour.g, colour.b, 0.45)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 8
	style.content_margin_right = 8
	style.content_margin_top = 6
	style.content_margin_bottom = 6
	box.add_theme_stylebox_override("panel", style)
	return box


func _heading(text: String) -> Control:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 12)
	label.modulate = Color(0.72, 0.80, 0.95)
	return label


func _subheading(text: String) -> Control:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = Color(0.66, 0.74, 0.92)
	return label


func _line(key: String, value: String, colour := Color(1, 1, 1)) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(130, 0)
	name_label.add_theme_font_size_override("font_size", 10)
	name_label.modulate = Color(1, 1, 1, 0.6)
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	value_label.add_theme_font_size_override("font_size", 10)
	value_label.modulate = colour
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	return row


func _bullet(text: String) -> Control:
	var label := Label.new()
	label.text = "  •  " + text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = Color(1, 1, 1, 0.62)
	return label


func _note(text: String) -> Control:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = Color(1, 1, 1, 0.5)
	return label