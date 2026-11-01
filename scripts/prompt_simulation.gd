extends Control
## Prompt → interpret → validate → execute → visualise, using the existing
## Zielinski replay model and the existing composition runner.
##
## This screen adds no simulation engine. It sends the prompt to
## `composition.prompt` through the runner, shows the structured interpretation,
## and then asks the runner to execute the configured replay graph. The 3D
## vessel, growth chart and cascade chart are the existing replay components.

const PANEL_TITLE := "Prompt to insulin simulation"
const RESULT_PATH := "user://prompt_simulation_result.json"
const INSTANCE_ID := "zielinski_replay"
const INK := Color(0.84, 0.89, 0.97)
const MUTED := Color(1, 1, 1, 0.58)
const WARN := Color(0.95, 0.78, 0.45)
const BAD := Color(0.95, 0.62, 0.55)
const GOOD := Color(0.56, 0.82, 0.60)

var _runner: CompositionRunner
var _prompt: TextEdit
var _generate: Button
var _interpret_only: Button
var _execute: Button
var _status: Label
var _sim_status: Label
var _interpretation_body: VBoxContainer
var _result_body: VBoxContainer
var _output_tree: Tree
var _view: ReplayVesselView
var _growth: GrowthChart
var _cascade: CascadeChart
var _readout: Label
var _request := ""
var _interpretation: Dictionary = {}
var _result: Dictionary = {}
var _data: ReplayData


func _ready() -> void:
	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 4)
	add_child(root)
	root.add_child(_header())
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 8)
	root.add_child(body)
	body.add_child(_left_column())
	body.add_child(_right_column())

	_runner = CompositionRunner.new("python", _detect_composition_dir())
	_runner.name = "PromptRunner"
	add_child(_runner)
	_runner.finished.connect(_on_runner_finished)
	# The workspace starts idle, so both actions are available. An empty prompt is
	# answered by `_on_generate_pressed` / `_on_interpret_pressed` with a request
	# for input; it must never leave the interface permanently unusable.
	_set_buttons(true)


func _detect_composition_dir() -> String:
	var root := ProjectSettings.globalize_path("res://")
	for candidate in [root.path_join("composition"), root]:
		var dir := DirAccess.open(candidate)
		if dir != null and dir.file_exists("composition/runner.py"):
			return candidate
	return ""


func _header() -> Control:
	var box := PanelContainer.new()
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	box.add_child(row)
	var title := Label.new()
	title.text = PANEL_TITLE
	title.add_theme_font_size_override("font_size", 16)
	row.add_child(title)
	var subtitle := Label.new()
	subtitle.text = "Zielinski et al. (2019) — evidence replay, configured from a prompt"
	subtitle.add_theme_font_size_override("font_size", 11)
	subtitle.modulate = MUTED
	row.add_child(subtitle)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	var back := Button.new()
	back.text = "Back to workshop"
	back.pressed.connect(func() -> void: get_tree().change_scene_to_file.call_deferred("res://scenes/workshop.tscn"))
	row.add_child(back)
	return box


func _left_column() -> Control:
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(560, 0)
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 4)
	var title := Label.new()
	title.text = "Replay view"
	title.add_theme_font_size_override("font_size", 12)
	title.modulate = INK
	column.add_child(title)
	var note := Label.new()
	note.text = "Bulk OD600 encoding, not a spatial field. The vessel geometry and published values are the existing replay components."
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_font_size_override("font_size", 10)
	note.modulate = MUTED
	column.add_child(note)
	_view = ReplayVesselView.new()
	_view.custom_minimum_size = Vector2(540, 360)
	_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(_view)
	_readout = Label.new()
	_readout.text = "No simulation executed yet."
	_readout.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_readout.add_theme_font_size_override("font_size", 10)
	_readout.modulate = MUTED
	column.add_child(_readout)
	_growth = GrowthChart.new()
	_growth.custom_minimum_size = Vector2(540, 220)
	_growth.scrubbed.connect(_on_scrub)
	column.add_child(_growth)
	_cascade = CascadeChart.new()
	_cascade.custom_minimum_size = Vector2(540, 120)
	column.add_child(_cascade)
	return column


func _right_column() -> Control:
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.custom_minimum_size = Vector2(560, 0)
	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 6)
	scroll.add_child(body)

	_section(body, "A. Prompt input")
	var examples := OptionButton.new()
	examples.name = "PromptExamples"
	examples.add_item("Choose an example prompt...")
	examples.set_item_metadata(0, "")
	for item in [
		["Full run — growth and activity", "Simulate the Zielinski insulin production process for 19 hours and show OD600, wet biomass, inclusion bodies and insulin activity."],
		["Configured volume and cascade", "Run the E. coli 20 / pIBAINS fermentation with a 5 L starting medium volume at 37 C and show the growth curve and AU purification cascade."],
		["Parameter change and rerun", "Increase the starting medium volume to 8 L and show wet biomass and insulin activity."],
		["Clarification example — duration", "Simulate 48 hours of the insulin process."],
		["Unsupported example — CHO", "Simulate CHO cell insulin production for 48 hours."],
	]:
		examples.add_item(str(item[0]))
		examples.set_item_metadata(examples.item_count - 1, str(item[1]))
	examples.item_selected.connect(_on_example_selected.bind(examples))
	body.add_child(examples)

	_prompt = TextEdit.new()
	_prompt.name = "PromptText"
	_prompt.placeholder_text = (
		"Describe the Zielinski insulin process you want to run, the duration, "
		+ "the variables to show, and any supported parameter changes."
	)
	_prompt.custom_minimum_size = Vector2(0, 118)
	_prompt.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	body.add_child(_prompt)

	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 8)
	body.add_child(buttons)
	_generate = Button.new()
	_generate.name = "GenerateSimulationButton"
	_generate.text = "Generate simulation"
	_generate.tooltip_text = "Interpret the prompt, validate the configuration and execute it through the existing runner."
	_generate.pressed.connect(_on_generate_pressed)
	buttons.add_child(_generate)
	_interpret_only = Button.new()
	_interpret_only.name = "InterpretOnlyButton"
	_interpret_only.text = "Interpret only"
	_interpret_only.pressed.connect(_on_interpret_pressed)
	buttons.add_child(_interpret_only)
	_status = Label.new()
	_status.name = "PromptStatus"
	_status.text = "Enter a prompt and choose Generate simulation."
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_font_size_override("font_size", 10)
	_status.modulate = MUTED
	body.add_child(_status)

	_section(body, "B. Interpretation")
	_interpretation_body = VBoxContainer.new()
	_interpretation_body.add_theme_constant_override("separation", 2)
	body.add_child(_interpretation_body)

	_section(body, "C. Simulation")
	_sim_status = Label.new()
	_sim_status.name = "SimulationStatus"
	_sim_status.text = "No validated configuration yet."
	_sim_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_sim_status.add_theme_font_size_override("font_size", 10)
	_sim_status.modulate = MUTED
	body.add_child(_sim_status)
	_execute = Button.new()
	_execute.name = "RunValidatedButton"
	_execute.text = "Run validated configuration"
	_execute.disabled = true
	_execute.pressed.connect(_on_execute_pressed)
	body.add_child(_execute)

	_section(body, "D. Results")
	_result_body = VBoxContainer.new()
	_result_body.add_theme_constant_override("separation", 2)
	body.add_child(_result_body)
	_output_tree = Tree.new()
	_output_tree.name = "RequestedOutputs"
	_output_tree.columns = 4
	_output_tree.set_column_title(0, "requested output")
	_output_tree.set_column_title(1, "value")
	_output_tree.set_column_title(2, "unit")
	_output_tree.set_column_title(3, "provenance / source")
	_output_tree.set_column_expand(0, true)
	_output_tree.set_column_expand(1, false)
	_output_tree.set_column_expand(2, false)
	_output_tree.set_column_expand(3, true)
	_output_tree.custom_minimum_size = Vector2(0, 210)
	body.add_child(_output_tree)
	return scroll


func _section(parent: VBoxContainer, title: String) -> void:
	var label := Label.new()
	label.text = title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	parent.add_child(label)


# --------------------------------------------------------------------- actions

func _set_buttons(enabled: bool) -> void:
	_generate.disabled = not enabled
	_interpret_only.disabled = not enabled
	_execute.disabled = not (enabled and bool(_interpretation.get("ok", false)))


func _on_example_selected(index: int, examples: OptionButton) -> void:
	var text := str(examples.get_item_metadata(index))
	if text != "":
		_prompt.text = text
		_status.text = "Example loaded. Choose Generate simulation or Interpret only."


func _on_generate_pressed() -> void:
	if _prompt.text.strip_edges() == "":
		_clear_result_surface()
		_status.text = "Enter a prompt first. An empty prompt is not a request."
		return
	_start_interpret("interpret_and_run")


func _on_interpret_pressed() -> void:
	if _prompt.text.strip_edges() == "":
		_clear_result_surface()
		_status.text = "Enter a prompt first. An empty prompt is not a request."
		return
	_start_interpret("interpret")


func _start_interpret(kind: String) -> void:
	_request = kind
	_status.text = "Reading the prompt against the Zielinski manifest..."
	_generate.disabled = true
	_interpret_only.disabled = true
	_execute.disabled = true
	# A new interpretation invalidates the previous result; leaving it visible
	# would make an old run look like the answer to the new prompt.
	_clear_result_surface()
	_runner.interpret_prompt(_prompt.text)


func _clear_result_surface() -> void:
	_result = {}
	_data = null
	_clear(_result_body)
	if _output_tree != null:
		_output_tree.clear()
	if _growth != null:
		_growth.set_data(null)
	if _cascade != null:
		_cascade.set_data(null)
	if _view != null:
		_view.set_turbidity(0.0)
	if _readout != null:
		_readout.text = "No current simulation. A validated configuration must be executed."


func _on_execute_pressed() -> void:
	if not bool(_interpretation.get("ok", false)):
		_sim_status.text = "There is no validated configuration to execute."
		return
	_start_run()


func _start_run() -> void:
	_request = "run"
	_sim_status.text = "Executing the validated configuration through the existing runner..."
	_set_buttons(false)
	var result_dir := ProjectSettings.globalize_path(RESULT_PATH).get_base_dir()
	DirAccess.make_dir_recursive_absolute(result_dir)
	_runner.run_prompt(_prompt.text, RESULT_PATH)


func _on_runner_finished(payload: Dictionary) -> void:
	if payload.is_empty():
		_status.text = "The prompt runner returned no readable document. No analysis was substituted."
		_request = ""
		_set_buttons(true)
		return
	if _request == "interpret" or _request == "interpret_and_run":
		_interpretation = payload
		_show_interpretation()
		if _request == "interpret_and_run" and bool(payload.get("ok", false)):
			_request = ""
			_start_run()
			return
		_request = ""
		_set_buttons(true)
		return
	if _request == "run":
		_request = ""
		_result = payload
		var interpretation: Variant = payload.get("prompt_interpretation")
		if interpretation is Dictionary and not interpretation.is_empty():
			_interpretation = interpretation
			_show_interpretation()
		var status := str(payload.get("status", ""))
		if status in ["invalid", "failed", "rejected"]:
			_sim_status.text = (
				"Execution did not produce a simulation. "
				+ str(payload.get("notes", payload.get("error", "See the interpretation and diagnostics.")))
			)
			_set_buttons(true)
			return
		_render_results(payload)
		_set_buttons(true)
		return
	_set_buttons(true)


func _show_interpretation() -> void:
	_clear(_interpretation_body)
	if _interpretation.is_empty():
		_paragraph(_interpretation_body, "No interpretation has been produced.", MUTED)
		return
	var status := str(_interpretation.get("status", "unknown"))
	_status.text = "Interpretation status: %s." % status
	_status.modulate = GOOD if bool(_interpretation.get("ok", false)) else WARN
	var process: Dictionary = _interpretation.get("target_process", {})
	_field(_interpretation_body, "Detected process", str(process.get("reason", "")))
	if bool(process.get("supported", false)):
		_status.text += " " + str(process.get("supported_process", ""))
	var model: Dictionary = _interpretation.get("selected_model", {})
	_field(_interpretation_body, "Selected model", "%s@%s — %s" % [
		str(model.get("model_id", "?")),
		str(model.get("model_version", "?")),
		str(model.get("title", "")),
	])
	var duration: Dictionary = _interpretation.get("duration", {})
	_field(_interpretation_body, "Duration", "%s h requested; the published trajectory ends at %s h." % [
		str(duration.get("requested_hours", "?")),
		str(duration.get("published_max_hours", "?")),
	])
	var variable_lines: Array = []
	for output in _interpretation.get("requested_outputs", []):
		variable_lines.append("%s%s" % [
			str(output.get("label", output.get("key", ""))),
			"" if bool(output.get("available", false)) else " (not available)",
		])
	_field(_interpretation_body, "Requested variables", _bullet(variable_lines))
	_field(_interpretation_body, "Requested parameter changes", _bullet(_parameter_lines()))
	var missing: Array = _interpretation.get("missing_information", [])
	if not missing.is_empty():
		_field(_interpretation_body, "Missing information / clarification", _missing_lines(missing), WARN)
	_field(_interpretation_body, "Assumptions", _bullet(_interpretation.get("assumptions", [])))
	_field(_interpretation_body, "Warnings", _bullet(_interpretation.get("warnings", [])), WARN)
	var validation: Dictionary = _interpretation.get("validation", {})
	if not bool(validation.get("ok", true)):
		_field(_interpretation_body, "Validation errors", _validation_lines(validation), BAD)
	if bool(_interpretation.get("ok", false)):
		_sim_status.text = "Validated configuration is ready. Press Run validated configuration or Generate simulation."
		_sim_status.modulate = GOOD
	else:
		_sim_status.text = "Execution is blocked until the clarification is answered. No default was substituted."
		_sim_status.modulate = WARN
	_set_buttons(true)


func _render_results(payload: Dictionary) -> void:
	_clear(_result_body)
	_output_tree.clear()
	_data = ReplayData.new()
	_data.load_payload(payload, INSTANCE_ID)
	_view.set_fill_fraction(_data.fill_fraction())
	_growth.set_data(_data)
	_cascade.set_data(_data)
	if _data.has_trajectory():
		_on_scrub(_data.hours[0])
	else:
		_view.set_turbidity(0.0)
		_readout.text = "The result publishes no growth trajectory."
	_sim_status.text = "Executed through the existing runner: %s." % str(payload.get("status", "unknown"))
	_sim_status.modulate = GOOD
	_field(_result_body, "Execution status", str(payload.get("status", "")))
	_field(_result_body, "Baseline comparison", _effect_text(payload.get("prompt_effect", {})))
	_field(_result_body, "Configured parameters", _bullet(_parameter_lines()))
	_field(_result_body, "Source attribution", str(_interpretation.get("selected_model", {}).get("source_ref", "")))
	_field(_result_body, "Warnings", _bullet(_interpretation.get("warnings", [])), WARN)
	_field(_result_body, "Model diagnostics", _diagnostics_text(payload), WARN)
	_field(_result_body, "Assumptions", _bullet(_interpretation.get("assumptions", [])))
	_field(_result_body, "Runner notes", str(payload.get("notes", "")), MUTED)
	_render_outputs(payload)


func _render_outputs(payload: Dictionary) -> void:
	var by_port := _output_map(payload)
	var root := _output_tree.create_item()
	for output in _interpretation.get("requested_outputs", []):
		if not output is Dictionary:
			continue
		if str(output.get("kind", "")) == "trajectory":
			_add_tree_row(root, [
				str(output.get("label", "OD600 trajectory")),
				"%d points, %.1f–%.1f h" % [
					_data.hours.size(),
					_data.hours[0] if _data.hours.size() > 0 else 0.0,
					_data.hours[_data.hours.size() - 1] if _data.hours.size() > 0 else 0.0,
				],
				"OD600",
				"digitized Fig. 3; existing replay",
			])
			for port in output.get("ports", []):
				if "#od600_h" in str(port.get("port_id", "")):
					continue
				_add_output_row(root, port, by_port)
			continue
		for port in output.get("ports", []):
			_add_output_row(root, port, by_port)


func _add_output_row(root: TreeItem, port: Dictionary, by_port: Dictionary) -> void:
	var port_id := str(port.get("port_id", ""))
	var value: Dictionary = by_port.get(port_id, {})
	var displayed := _display_value(value)
	var source := str(port.get("provenance", ""))
	var citation := str(port.get("citation", ""))
	if citation != "":
		source += " | " + citation
	if displayed.begins_with("not available") and str(port.get("reason", "")) != "":
		displayed += " — " + str(port.get("reason", ""))
	_add_tree_row(root, [
		str(port.get("label", port_id)),
		displayed,
		str(port.get("unit", "")),
		source,
	])


func _add_tree_row(root: TreeItem, cells: Array) -> void:
	var item := _output_tree.create_item(root)
	for i in range(mini(cells.size(), 4)):
		item.set_text(i, str(cells[i]))


func _on_scrub(hour: float) -> void:
	if _data == null:
		return
	_growth.set_cursor(hour, true)
	var od := _data.od_at_hour(hour)
	var max_od := _data.max_od()
	var ratio := 0.0
	if not is_nan(max_od) and max_od > 0.0 and not is_nan(od):
		ratio = clampf(od / max_od, 0.0, 1.0)
	_view.set_turbidity(ratio)
	_readout.text = "Replay hour %.1f — OD600 %s. Bulk OD encoding only; no spatial field is computed." % [
		hour,
		"not available" if is_nan(od) else "%.2f" % od,
	]


# ------------------------------------------------------------------- helpers

func _parameter_lines() -> Array:
	var out: Array = []
	for change in _interpretation.get("requested_parameters", []):
		out.append("%s = %s %s (%s)" % [
			str(change.get("label", change.get("port_id", ""))),
			str(change.get("value", "?")),
			str(change.get("unit", "")),
			str(change.get("port_id", "")),
		])
	return out


func _missing_lines(missing: Array) -> String:
	var parts: Array = []
	for item in missing:
		if not item is Dictionary:
			continue
		var line := "%s: %s" % [str(item.get("code", "missing")), str(item.get("message", ""))]
		var options: Array = item.get("options", [])
		if not options.is_empty():
			line += " Options: " + "; ".join(PackedStringArray(options))
		parts.append(line)
	return "\n".join(PackedStringArray(parts))


func _validation_lines(validation: Dictionary) -> String:
	var parts: Array = []
	for error in validation.get("errors", []):
		if error is Dictionary:
			parts.append("%s: %s" % [str(error.get("code", "error")), str(error.get("message", ""))])
	return "\n".join(PackedStringArray(parts))


func _effect_text(effect: Variant) -> String:
	if not effect is Dictionary or effect.is_empty():
		return "No baseline comparison was produced."
	var e: Dictionary = effect
	return "%s Compared %s output ports; %s differed. Baseline %s; configured %s." % [
		str(e.get("note", "")),
		str(e.get("compared_ports", "?")),
		str(e.get("differing_ports", []).size()),
		str(e.get("baseline_status", "?")),
		str(e.get("configured_status", "?")),
	]


func _output_map(payload: Dictionary) -> Dictionary:
	var out := {}
	for result in payload.get("results", []):
		if str(result.get("instance_id", "")) != INSTANCE_ID:
			continue
		for output in result.get("outputs", []):
			var ref: Dictionary = output.get("ref", {})
			out[str(ref.get("port_id", ""))] = output.get("value", {})
	return out


func _diagnostics_text(payload: Dictionary) -> String:
	var parts: Array = []
	for diagnostic in payload.get("diagnostics", []):
		if diagnostic is Dictionary:
			parts.append("%s: %s" % [
				str(diagnostic.get("severity", "info")),
				str(diagnostic.get("message", diagnostic.get("code", ""))),
			])
		if parts.size() >= 8:
			break
	return "\n".join(PackedStringArray(parts))


func _display_value(value: Dictionary) -> String:
	if value.is_empty():
		return "not available"
	if not bool(value.get("is_resolved", false)):
		var reason := str(value.get("reason", ""))
		return "not available" + (" — " + reason if reason != "" else "")
	var raw: Variant = value.get("value")
	if raw == null:
		var reason := str(value.get("reason", ""))
		return "not available" + (" — " + reason if reason != "" else "")
	if raw is Array:
		return "range %s" % str(raw)
	return str(raw)


func _field(parent: VBoxContainer, key: String, value: String,
		colour: Color = INK) -> void:
	if value.strip_edges() == "":
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(150, 0)
	name_label.add_theme_font_size_override("font_size", 9)
	name_label.modulate = MUTED
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value_label.add_theme_font_size_override("font_size", 10)
	value_label.modulate = colour
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	parent.add_child(row)


func _paragraph(parent: VBoxContainer, text: String, colour: Color = INK) -> void:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	parent.add_child(label)


func _bullet(values: Variant) -> String:
	var parts := PackedStringArray()
	if values is Array:
		for value in values:
			parts.append("- " + str(value))
	return "\n".join(parts)


func _clear(parent: Node) -> void:
	if parent == null:
		return
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()


# --------------------------------------------------------------- harness API

func interpretation() -> Dictionary:
	return _interpretation


func result_payload() -> Dictionary:
	return _result


func prompt_text() -> String:
	return _prompt.text if _prompt != null else ""
