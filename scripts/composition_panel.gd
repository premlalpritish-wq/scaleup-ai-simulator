class_name CompositionPanel
extends PanelContainer
## Which models may contribute to the insulin simulation, and why not.
##
## ## No rules here
##
## Every classification, blocker, evidence line and connection shown here is read
## from `composition/composition/compatibility.py` through
## `--describe-compatibility`. This panel holds no model list and no rule: a
## classification changed there reaches this panel with nothing here being edited.
##
## ## What it is allowed to claim
##
## The panel shows two different things and never blurs them:
##
##   * the *assessment* -- what each model is relative to the Zielinski process;
##   * the *comparison* -- whether adding an independent instance changed any
##     baseline value. That one is an execution result, fetched on demand from
##     `--compare-composition`, and it is a statement about the pipeline, not
##     about the science.
##
## ## Why it owns a runner
##
## The workshop window multiplexes one runner across several introspection
## requests by flipping a flag before each call. A panel that piggybacked on that
## runner could consume another request's answer if two arrived together. This
## panel therefore owns a private `CompositionRunner`, so its requests cannot
## interleave with the scene's.

signal compatibility_loaded(payload: Dictionary)
signal comparison_loaded(payload: Dictionary)

const PANEL_TITLE := "Models assessed against this simulation"

var _runner: CompositionRunner = null
var _scroll: ScrollContainer
var _body: VBoxContainer
var _summary: Label
var _compare_button: Button
var _compare_status: Label
var _payload: Dictionary = {}
var _comparison: Dictionary = {}
var _rows: Dictionary = {}
var _connection_rows: Array = []


func setup(python_path: String = "", composition_dir: String = "") -> void:
	_runner = CompositionRunner.new(python_path, composition_dir)
	_runner.name = "CompositionPanelRunner"
	add_child(_runner)
	_runner.finished.connect(_on_runner_finished)

	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var heading := Label.new()
	heading.text = PANEL_TITLE
	heading.add_theme_font_size_override("font_size", 13)
	vb.add_child(heading)

	_summary = Label.new()
	_summary.name = "CompositionSummary"
	_summary.text = "The compatibility assessment has not been loaded yet."
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.add_theme_font_size_override("font_size", 10)
	_summary.modulate = Color(1, 1, 1, 0.62)
	vb.add_child(_summary)

	_compare_button = Button.new()
	_compare_button.name = "RunComparisonButton"
	_compare_button.text = "Run baseline vs composed comparison"
	_compare_button.tooltip_text = (
		"Executes the baseline replay and the multi-model graph, then compares the "
		+ "insulin instance's values across the two runs. Nothing is connected "
		+ "between the models.")
	_compare_button.pressed.connect(_on_compare_pressed)
	vb.add_child(_compare_button)

	_compare_status = Label.new()
	_compare_status.name = "ComparisonStatus"
	_compare_status.text = ""
	_compare_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_compare_status.add_theme_font_size_override("font_size", 10)
	_compare_status.modulate = Color(1, 1, 1, 0.6)
	vb.add_child(_compare_status)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(_scroll)

	_body = VBoxContainer.new()
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_theme_constant_override("separation", 4)
	_scroll.add_child(_body)


## Fetch the assessment. Safe to call more than once; the answer replaces the view.
func request() -> void:
	if _runner == null:
		return
	_summary.text = "Reading the compatibility assessment..."
	_runner.describe_compatibility()


## Accept an assessment payload directly, for a scene that already fetched it.
func set_compatibility(payload: Dictionary) -> void:
	_payload = payload
	_clear_body()
	_rows.clear()
	_connection_rows.clear()
	if payload.is_empty():
		_summary.text = "The compatibility assessment could not be read."
		_note(null, "No assessment payload was returned.", Color(0.95, 0.6, 0.6))
		return
	_render_summary()
	_render_connections()
	_render_assessments()
	compatibility_loaded.emit(payload)


func set_comparison(payload: Dictionary) -> void:
	_comparison = payload
	_render_comparison()
	comparison_loaded.emit(payload)


func _on_runner_finished(payload: Dictionary) -> void:
	# One runner, two questions. The comparison payload carries `comparison`;
	# the assessment carries `assessments`. Distinguishing on the payload rather
	# than on a request flag means an unexpected shape is reported, not rendered
	# as the wrong thing.
	if payload.has("comparison"):
		_compare_button.disabled = false
		set_comparison(payload)
		return
	if payload.has("assessments"):
		set_compatibility(payload)
		return
	_summary.text = "The runner answered with a document this panel does not recognise."
	_note(null, str(payload.get("error", payload)), Color(0.95, 0.6, 0.6))


func _on_compare_pressed() -> void:
	if _runner == null:
		return
	_compare_button.disabled = true
	_compare_status.text = "Executing the baseline and the composed graph..."
	_runner.compare_composition()


func _render_summary() -> void:
	var target: Dictionary = _payload.get("target", {})
	var summary: Dictionary = _payload.get("summary", {})
	var counts: Dictionary = summary.get("counts", {})
	_summary.text = (
		"%d model(s) assessed against %s@%s. %d contributes; %d are evidence-only. "
		+ "Dynamic connections touching the target: %d."
	) % [
		int(summary.get("assessed", 0)),
		str(target.get("model_id", "?")),
		str(target.get("model_version", "?")),
		int((summary.get("contributors", []) as Array).size()),
		int((summary.get("evidence_only", []) as Array).size()),
		int((summary.get("connections_touching_target", []) as Array).size()),
	]
	var order := [
		"dynamically_composable", "evidence_compatible",
		"contextually_relevant_not_composable", "incompatible",
		"insufficient_information",
	]
	var parts := PackedStringArray()
	for key in order:
		var n := int(counts.get(key, 0))
		if n > 0:
			parts.append("%d %s" % [n, str(key).replace("_", " ")])
	if not parts.is_empty():
		_summary.text += "  [" + "  ·  ".join(parts) + "]"
	var scope := str(_payload.get("claim_scope", ""))
	if scope != "":
		_note(null, scope, Color(1, 1, 1, 0.55))


func _render_connections() -> void:
	var connections: Dictionary = _payload.get("connections", {})
	var permitted: Array = connections.get("permitted", [])
	var touching: Array = connections.get("touching_target", [])
	_section("validated dynamic connections")
	if permitted.is_empty():
		_note(null, "The engine permits no dynamic connection in this project.")
	else:
		for connection in permitted:
			var touches := bool(connection.get("touches_target", false))
			var row := HBoxContainer.new()
			row.add_theme_constant_override("separation", 6)
			var label := Label.new()
			label.text = "%s -> %s" % [
				str(connection.get("source_model", "?")),
				str(connection.get("target_model", "?")),
			]
			label.add_theme_font_size_override("font_size", 10)
			label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(label)
			var badge := Label.new()
			badge.text = "touches target" if touches else "same model"
			badge.add_theme_font_size_override("font_size", 9)
			badge.modulate = Color(0.95, 0.72, 0.45) if touches else Color(0.62, 0.72, 0.82)
			row.add_child(badge)
			_body.add_child(row)
			_connection_rows.append({
				"source": str(connection.get("source_model", "")),
				"target": str(connection.get("target_model", "")),
				"touches_target": touches,
			})
	_note(
		null,
		"No connection touches the insulin process: %d touching the target." % touching.size(),
		Color(0.72, 0.86, 0.72) if touching.is_empty() else Color(0.95, 0.72, 0.45),
	)
	var note := str(connections.get("note", ""))
	if note != "":
		_note(null, note, Color(1, 1, 1, 0.45))


func _render_assessments() -> void:
	_section("every model, and why it can or cannot contribute")
	for assessment in _payload.get("assessments", []):
		_card(assessment)



## One assessment card. The baseline is marked as such and never given a blocker.
func _card(assessment: Dictionary) -> void:
	var key := str(assessment.get("key", "?"))
	var contributes := bool(assessment.get("contributes", false))
	var number := int(assessment.get("classification_number", 5))
	var colour := _classification_colour(number)

	var box := VBoxContainer.new()
	box.name = "Model_" + key
	box.add_theme_constant_override("separation", 1)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(colour.r, colour.g, colour.b, 0.10 if contributes else 0.06)
	style.border_color = Color(colour.r, colour.g, colour.b, 0.45)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 7
	style.content_margin_right = 7
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	box.add_theme_stylebox_override("panel", style)

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	var title := Label.new()
	title.text = "%d. %s" % [number, str(assessment.get("display_name", key))]
	title.add_theme_font_size_override("font_size", 11)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	head.add_child(title)
	var role := Label.new()
	role.text = "contributor" if contributes else "evidence only"
	role.add_theme_font_size_override("font_size", 9)
	role.modulate = color_ok() if contributes else Color(1, 1, 1, 0.5)
	head.add_child(role)
	box.add_child(head)

	_field(box, "class", str(assessment.get("classification_label", "")), colour)
	# Which paper this component is. Attribution is not decoration: it is how a
	# reader knows whose numbers a row belongs to.
	_field(box, "paper", str(assessment.get("paper", "")))
	var package := str(assessment.get("package", ""))
	var model_id := str(assessment.get("model_id", ""))
	var address := package
	if model_id != "":
		address += "  (" + model_id + ")"
	_field(box, "model", address)

	var summary := str(assessment.get("summary", ""))
	if summary != "":
		_note(box, summary)

	var blockers: Array = assessment.get("blockers", [])
	if not blockers.is_empty():
		_field(box, "why not", "")
		for blocker in blockers:
			_note(box, "  - " + str(blocker), Color(0.95, 0.80, 0.62))
	var evidence_check := str(assessment.get("evidence_check", ""))
	if evidence_check != "":
		_field(box, "evidence", evidence_check, Color(1, 1, 1, 0.55))

	_add_inspection(box, assessment.get("inspection", {}))
	_add_collapsible(box, "raw assessment record", _pretty(assessment))
	_body.add_child(box)
	_rows[key] = box


func _add_inspection(box: VBoxContainer, inspection: Dictionary) -> void:
	if inspection.is_empty():
		return
	var toggle := Button.new()
	toggle.text = "what was inspected"
	toggle.add_theme_font_size_override("font_size", 9)
	toggle.toggle_mode = true
	toggle.button_pressed = false
	var body := VBoxContainer.new()
	body.visible = false
	body.add_theme_constant_override("separation", 1)
	toggle.toggled.connect(func(on: bool) -> void: body.visible = on)
	box.add_child(toggle)
	box.add_child(body)
	for axis in [
		"organism", "context", "inputs", "outputs", "units", "equations",
		"parameters", "time_scale", "assumptions",
	]:
		var value := str(inspection.get(axis, ""))
		if value != "":
			_field(body, axis, value, Color(1, 1, 1, 0.55))


func _add_collapsible(box: VBoxContainer, label: String, text: String) -> void:
	if text == "":
		return
	var toggle := Button.new()
	toggle.text = label
	toggle.add_theme_font_size_override("font_size", 9)
	toggle.toggle_mode = true
	toggle.button_pressed = false
	var body := RichTextLabel.new()
	body.bbcode_enabled = false
	body.fit_content = true
	body.visible = false
	body.custom_minimum_size = Vector2(0, 0)
	body.add_theme_font_size_override("normal_font_size", 9)
	toggle.toggled.connect(func(on: bool) -> void: body.visible = on)
	box.add_child(toggle)
	box.add_child(body)
	body.text = text



## The baseline-vs-composed comparison. Rendered from execution results only.
func _render_comparison() -> void:
	# The comparison section is rebuilt in place each time, so pressing the button
	# twice adds nothing and never shows a stale verdict next to a fresh one.
	for child in _body.get_children():
		if str(child.name).begins_with("Comparison"):
			_body.remove_child(child)
			child.queue_free()

	var comparison: Dictionary = _comparison.get("comparison", {})
	var identical := bool(comparison.get("identical", false))
	var holder := VBoxContainer.new()
	holder.name = "ComparisonSection"
	holder.add_theme_constant_override("separation", 2)
	var style := StyleBoxFlat.new()
	var tint := color_ok() if identical else Color(0.95, 0.62, 0.45)
	style.bg_color = Color(tint.r, tint.g, tint.b, 0.10)
	style.border_color = Color(tint.r, tint.g, tint.b, 0.5)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 7
	style.content_margin_right = 7
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	holder.add_theme_stylebox_override("panel", style)

	var title := Label.new()
	title.text = "baseline vs composed"
	title.add_theme_font_size_override("font_size", 11)
	title.modulate = Color(0.70, 0.79, 0.95)
	holder.add_child(title)

	var baseline: Dictionary = _comparison.get("baseline", {})
	var composed: Dictionary = _comparison.get("composed", {})
	_field(holder, "baseline", "%s -- %s (exit %d)" % [
		str(baseline.get("graph_id", "?")),
		str(baseline.get("status", "?")),
		int(baseline.get("exit_code", -1)),
	])
	_field(holder, "composed", "%s -- %s (exit %d)" % [
		str(composed.get("graph_id", "?")),
		str(composed.get("status", "?")),
		int(composed.get("exit_code", -1)),
	])
	_field(
		holder,
		"values",
		"%d baseline ports, %d composed ports, %d differing" % [
			int(comparison.get("baseline_ports", 0)),
			int(comparison.get("composed_ports", 0)),
			(comparison.get("differing_ports", []) as Array).size(),
		],
		tint,
	)
	var verdict := Label.new()
	verdict.name = "ComparisonVerdict"
	verdict.text = (
		"IDENTICAL -- adding the independent instance changed no baseline value."
		if identical else
		"DIFFERENT -- the baseline changed. This must be investigated."
	)
	verdict.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	verdict.add_theme_font_size_override("font_size", 10)
	verdict.modulate = tint
	holder.add_child(verdict)

	var excluded: Array = comparison.get("fields_excluded_as_attribution", [])
	if not excluded.is_empty():
		_field(
			holder,
			"excluded",
			"compared on %s; %s differ by construction because they name the instance" % [
				", ".join(PackedStringArray(comparison.get("fields_compared", []))),
				", ".join(PackedStringArray(excluded)),
			],
			Color(1, 1, 1, 0.5),
		)

	# Per-instance attribution of the composed run.
	var instances: Array = (_comparison.get("composition", {}) as Dictionary).get(
		"instances", [])
	for instance in instances:
		var contributes := bool(instance.get("contributes", false))
		_field(
			holder,
			str(instance.get("instance_id", "?")),
			"%s -- %s, %d output(s)" % [
				str(instance.get("paper", "(unattributed)")),
				"contributor" if contributes else "co-executed, not contributing",
				int(instance.get("output_count", 0)),
			],
			Color(0.72, 0.86, 0.72) if contributes else Color(1, 1, 1, 0.6),
		)
	var note := str(_comparison.get("note", ""))
	if note != "":
		_note(holder, note, Color(1, 1, 1, 0.45))
	_body.add_child(holder)

	_compare_status.text = (
		"The comparison ran. The baseline is unchanged."
		if identical else
		"The comparison ran, and the baseline differs -- see the differing ports."
	)
	_compare_button.disabled = false


# -------------------------------------------------------- harness accessors


## The assessment entries the panel rendered, in payload order.
func assessment_rows() -> Array:
	return _payload.get("assessments", [])


## The card node for one model key, or null.
func row_for(key: String) -> Node:
	return _rows.get(key, null)


## ``[number, label]`` for one model, or ``[]`` when it was not assessed.
func classification_for(key: String) -> Array:
	for assessment in assessment_rows():
		if str(assessment.get("key", "")) == key:
			return [
				int(assessment.get("classification_number", 0)),
				str(assessment.get("classification_label", "")),
			]
	return []


func contributors() -> PackedStringArray:
	var out := PackedStringArray()
	for assessment in assessment_rows():
		if bool(assessment.get("contributes", false)):
			out.append(str(assessment.get("key", "")))
	return out


func evidence_only_keys() -> PackedStringArray:
	var out := PackedStringArray()
	for assessment in assessment_rows():
		if not bool(assessment.get("contributes", true)):
			out.append(str(assessment.get("key", "")))
	return out


func connections() -> Array:
	return _connection_rows


func summary_text() -> String:
	return _summary.text if _summary != null else ""


func comparison() -> Dictionary:
	return _comparison


func payload() -> Dictionary:
	return _payload



# ------------------------------------------------------------- small builders


func _section(title: String) -> void:
	var label := Label.new()
	label.text = "== %s ==" % title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	_body.add_child(label)


func _field(box: VBoxContainer, key: String, value: String,
		colour: Color = Color(1, 1, 1, 0.62)) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(84, 0)
	name_label.add_theme_font_size_override("font_size", 10)
	name_label.modulate = Color(1, 1, 1, 0.5)
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value_label.add_theme_font_size_override("font_size", 10)
	value_label.modulate = colour
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	box.add_child(row)


func _note(container: Variant, text: String,
		colour: Color = Color(1, 1, 1, 0.55)) -> void:
	var target: VBoxContainer = container as VBoxContainer
	if target == null:
		target = _body
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	target.add_child(label)


func _clear_body() -> void:
	if _body == null:
		return
	for child in _body.get_children():
		_body.remove_child(child)
		child.queue_free()


## The brief's numbering, as a colour. A model that contributes is green; a model
## that cannot be connected moves through amber to grey as the claim weakens.
static func _classification_colour(number: int) -> Color:
	match number:
		1:
			return Color(0.56, 0.82, 0.60)
		2:
			return Color(0.60, 0.80, 0.86)
		3:
			return Color(0.95, 0.82, 0.45)
		4:
			return Color(0.95, 0.62, 0.45)
	return Color(0.72, 0.74, 0.80)


static func color_ok() -> Color:
	return Color(0.56, 0.82, 0.60)


static func _pretty(value: Variant) -> String:
	return JSON.stringify(value, "  ", false, true) if value != null else ""

