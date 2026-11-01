class_name EvidenceInspector
extends PanelContainer
## What every visible scientific quantity is, and where it came from.
##
## ## The rule this panel exists to enforce
##
## A number on screen is only meaningful if the reader can tell what kind of number
## it is. "Biomass 18.3 g/L" and "initial biomass 0.05 g/L, assumed" look identical in
## a results table and are not remotely the same claim. So every row carries an
## epistemic status, and the status is derived, never typed in by hand:
##
##   reported   -- printed in the source paper
##   calculated -- computed by an executable model from other quantities
##   derived    -- computed by this project from a reported value by a stated step
##   assumed    -- required by the equations and not established by the source
##   caller_supplied -- supplied by whoever runs the simulation
##   unknown    -- the source does not establish it
##
## ## Inputs and outputs are shown separately, and always are
##
## An initial condition is not a result. This panel keeps the model's *inputs* and
## its *outputs* in distinct sections with distinct framing, because the failure mode
## this guards against is an assumed initial condition being read as a measurement.
##
## Nothing here duplicates the compatibility engine or the manifest: the manifest is
## read from `--describe-model`, and the validation claim is read from the result
## document. If a field is not in either, it says so rather than guessing.

const STATUS_COLOURS := {
	"reported": Color(0.56, 0.82, 0.60),
	"calculated": Color(0.52, 0.72, 0.96),
	"derived": Color(0.72, 0.80, 0.55),
	"assumed": Color(0.95, 0.76, 0.45),
	"caller_supplied": Color(0.95, 0.68, 0.45),
	"inferred": Color(0.90, 0.72, 0.78),
	"unknown": Color(0.80, 0.55, 0.55),
	"digitized": Color(0.72, 0.68, 0.95),
}

## Shown wherever the manifest or the result document has no field. Distinct from an
## empty string, which would mean the source said nothing on purpose.
const NOT_SHOWN := "not published by this source"
const NO_CLAIM := "no validation claim published"

var _scroll: ScrollContainer
var _body: VBoxContainer
var _manifest: Dictionary = {}
var _result: Dictionary = {}
var _inputs: Dictionary = {}
var _available := false


func setup() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var heading := Label.new()
	heading.text = "Evidence and assumptions"
	heading.add_theme_font_size_override("font_size", 13)
	vb.add_child(heading)

	_sub = Label.new()
	_sub.text = "No model described yet."
	_sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_sub.add_theme_font_size_override("font_size", 10)
	_sub.modulate = Color(1, 1, 1, 0.62)
	vb.add_child(_sub)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(_scroll)

	_body = VBoxContainer.new()
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_theme_constant_override("separation", 4)
	_scroll.add_child(_body)


var _sub: Label


func clear() -> void:
	_available = false
	_manifest = {}
	_result = {}
	_inputs = {}
	if _sub != null:
		_sub.text = "No model described yet."
	_clear_body()


## Show the evidence for one model, with the result of its most recent execution.
##
## `manifest` is the `--describe-model` payload; `result` is a result document or `{}`;
## `inputs` maps instance_id -> { port_id: literal dictionary } as the graph declared
## it, which is what distinguishes a caller-supplied value from a default.
func show_model(manifest: Dictionary, result: Dictionary, inputs: Dictionary) -> void:
	_manifest = manifest
	_result = result
	_inputs = inputs
	_available = true
	_clear_body()

	var model_id := str(manifest.get("model_id", "?"))
	var version := str(manifest.get("model_version", "?"))
	_sub.text = "%s %s -- %s" % [model_id, version, str(manifest.get("title", ""))]

	_section("Source")
	_note(null, "citation: " + str(manifest.get("source_ref", NOT_SHOWN)))
	_note(null, "summary:  " + str(manifest.get("summary", NOT_SHOWN)))

	_output_section()
	_input_section()
	_assumptions_section()
	_limits_section()
	_validation_section()


## Convenience accessors used by the acceptance harness and the scene.
func has_model() -> bool:
	return _available


func model_id() -> String:
	return str(_manifest.get("model_id", ""))


func sections() -> PackedStringArray:
	var names := PackedStringArray()
	for child in _body.get_children():
		if child is Label and child.text.begins_with("== "):
			names.append(str(child.text).trim_prefix("== ").trim_suffix(" =="))
	return names


# ------------------------------------------------------------------ sections


func _output_section() -> void:
	_section("Quantities calculated by the model")
	var ports := _manifest.get("ports", []) as Array
	var any := false
	for port in ports:
		if str(port.get("direction", "")) != "output":
			continue
		any = true
		_output_card(port)
	if not any:
		_note(null, "This model publishes no output ports.")


func _output_card(port: Dictionary) -> void:
	var port_id := str(port.get("port_id", "?"))
	var box := _card(Color(0.52, 0.72, 0.96))
	_head(box, "%s  [%s]" % [str(port.get("label", port_id)), str(port.get("unit", ""))],
		"calculated")

	var found := _find_output(port_id)
	if found.is_empty():
		_row(box, "status", "not produced by the last run", Color(1, 0.72, 0.45))
	else:
		_row(box, "final value", "%s %s" % [
			str(found.get("value", "?")), str(found.get("unit", ""))])
		_row(box, "provenance", str(found.get("provenance", NOT_SHOWN)))
		var method := str(found.get("method", ""))
		if method != "":
			_row(box, "how", method.substr(0, 220))
		var source := str(found.get("source_ref", ""))
		_row(box, "source ref", source if source != "" else NOT_SHOWN)

		# Provenance chain: where the number came from, one hop at a time.
		var chain := found.get("provenance_chain", []) as Array
		if not chain.is_empty():
			var box2 := _card(Color(0.66, 0.70, 0.80))
			_head(box2, "provenance chain (%d)" % chain.size(), "")
			for record in chain:
				var kind := str(record.get("kind", "?"))
				var where := str(record.get("where", "?"))
				var detail := str(record.get("detail", ""))
				_row(box2, kind, "%s%s" % [
					where, ("  --  " + detail.substr(0, 140)) if detail != "" else ""])
			box.add_child(box2)

	var meta := port.get("metadata", {}) as Dictionary
	_row(box, "equation", str(meta.get("source_equation", NOT_SHOWN)))
	_row(box, "symbol", str(meta.get("model_symbol", NOT_SHOWN)))
	_row(box, "what it is", str(port.get("description", NOT_SHOWN)))
	var temporal := str(port.get("temporal_basis", ""))
	if temporal != "" and temporal != "none":
		_row(box, "temporal basis", temporal)
	_body.add_child(box)


func _input_section() -> void:
	_section("Inputs this run supplied")
	var ports := _manifest.get("ports", []) as Array
	var any := false
	for port in ports:
		if str(port.get("direction", "")) != "input":
			continue
		any = true
		var port_id := str(port.get("port_id", "?"))
		var literal := _find_literal(port_id)
		_input_card(port, literal)
	if not any:
		_note(null, "This model declares no input ports.")


func _input_card(port: Dictionary, literal: Dictionary) -> void:
	var port_id := str(port.get("port_id", "?"))
	var status := _input_status(port, literal)
	var colour: Color = STATUS_COLOURS.get(status, Color(1, 1, 1, 0.7))
	var box := _card(colour)
	_head(box, "%s  [%s]" % [str(port.get("label", port_id)), str(port.get("unit", ""))],
		status)

	if literal.is_empty():
		_note(box, "not supplied; the model supplies its own default, if it has one")
	else:
		_row(box, "value", "%s %s" % [
			str(literal.get("value", "?")), str(literal.get("unit", ""))])
		_row(box, "provenance", str(literal.get("provenance", NOT_SHOWN)))
		var reason := str(literal.get("reason", ""))
		if reason != "":
			_note(box, reason)
		var source := str(literal.get("source_ref", ""))
		_row(box, "source ref", source if source != "" else NOT_SHOWN)
		var method := str(literal.get("method", ""))
		if method != "":
			_note(box, method)

	if bool(port.get("required", false)):
		_row(box, "required", "yes -- the model cannot run without it")
	var unavailable := str(port.get("unavailable_reason", ""))
	if unavailable != "":
		_row(box, "unavailable", unavailable, Color(0.95, 0.72, 0.45))
	_body.add_child(box)


## The epistemic status of one supplied input.
##
## Taken from the literal's own provenance field where the runner recorded one, and
## otherwise from the manifest. Never invented: an unrecognised provenance is
## reported as unknown rather than being rounded to something friendlier.
func _input_status(port: Dictionary, literal: Dictionary) -> String:
	if literal.is_empty():
		if str(port.get("unavailable_reason", "")) != "":
			return "unknown"
		return "assumed"
	var provenance := str(literal.get("provenance", "")).to_lower()
	match provenance:
		"reported":
			return "reported"
		"derived":
			return "derived"
		"calculated":
			return "calculated"
		"digitized":
			return "digitized"
		"inferred":
			return "inferred"
		"transferred":
			return "caller_supplied"
		"declared":
			return "caller_supplied"
	if provenance == "":
		return "assumed"
	return provenance


func _assumptions_section() -> void:
	_section("Assumptions and unresolved readings")
	var entries := _manifest.get("assumptions", []) as Array
	if entries.is_empty():
		_note(null, "This model declares no assumptions.")
		return
	for entry in entries:
		var status := str(entry.get("status", "unknown"))
		var colour: Color = STATUS_COLOURS.get(
			"unresolved" if status == "unresolved" else "assumed", Color(1, 1, 1, 0.7))
		var box := _card(colour)
		_head(box, str(entry.get("item_id", "?")), status.replace("_", " "))
		_note(box, str(entry.get("summary", NOT_SHOWN)))
		_body.add_child(box)


func _limits_section() -> void:
	_section("What this model does not do")
	var unsupported := _manifest.get("unsupported_capabilities", {}) as Dictionary
	if unsupported.is_empty():
		_note(null, "No unsupported capability is declared.")
		return
	for key in unsupported:
		var box := _card(Color(0.95, 0.72, 0.45))
		_head(box, key.replace("_", " "), "unsupported")
		_note(box, str(unsupported[key]))
		_body.add_child(box)


func _validation_section() -> void:
	_section("Scientific validation status")
	var claim := _validation_claim()
	if claim.is_empty():
		_note(null, NO_CLAIM)
		_note(null, "An absent claim is not a claim that the model is invalid. It means "
			+ "this model publishes no validation status through the composition "
			+ "boundary.")
		return

	_note(null, "implementation: " + str(claim.get("implementation_status", NOT_SHOWN)))
	_note(null, "reproduction:  " + str(claim.get("reproduction_status", NOT_SHOWN)))

	var is_validated := str(claim.get("reproduction_status", "")) == "validated"
	_note(null, "This value is the model's own statement. Running the simulation does not "
		+ "change it, and it is never improved because software tests pass.",
		Color(0.95, 0.82, 0.45) if not is_validated else Color(0.62, 0.88, 0.62))

	var supported := claim.get("what_is_validated", []) as Array
	if not supported.is_empty():
		_subhead(null, "supported by the model")
		for item in supported:
			_note(null, "  +  " + str(item), Color(0.62, 0.82, 0.62))
	var unsupported := claim.get("what_is_not_validated", []) as Array
	if not unsupported.is_empty():
		_subhead(null, "not supported by the model")
		for item in unsupported:
			_note(null, "  -  " + str(item), Color(0.95, 0.76, 0.45))


# -------------------------------------------------------------------- lookup


func _find_output(port_id: String) -> Dictionary:
	for result in _result.get("results", []) as Array:
		for output in result.get("outputs", []) as Array:
			var ref := output.get("ref", {}) as Dictionary
			if str(ref.get("port_id", "")) == port_id:
				return output.get("value", {}) as Dictionary
	return {}


func _find_literal(port_id: String) -> Dictionary:
	for key in _inputs:
		var short := str(key).split("/")[-1]
		if short == port_id:
			return _inputs[key]
	return {}


func _validation_claim() -> Dictionary:
	for result in _result.get("results", []) as Array:
		for output in result.get("outputs", []) as Array:
			var value := output.get("value", {}) as Dictionary
			var extra := value.get("extra", {}) as Dictionary
			var claim := extra.get("validation_claim", {}) as Dictionary
			if not claim.is_empty():
				return claim
	return {}


# ------------------------------------------------------------------- builders


func _section(title: String) -> void:
	var label := Label.new()
	label.text = "== %s ==" % title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	_body.add_child(label)


func _subhead(_unused: Variant, text: String) -> void:
	var label := Label.new()
	label.text = "   " + text
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = Color(0.74, 0.78, 0.88)
	_body.add_child(label)


func _card(colour: Color) -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(colour.r, colour.g, colour.b, 0.09)
	style.border_color = Color(colour.r, colour.g, colour.b, 0.42)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 7
	style.content_margin_right = 7
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	box.add_theme_stylebox_override("panel", style)
	return box


func _head(box: VBoxContainer, title: String, status: String) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = title
	name_label.add_theme_font_size_override("font_size", 11)
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name_label)
	if status != "":
		var badge := Label.new()
		badge.text = status
		badge.add_theme_font_size_override("font_size", 9)
		badge.modulate = STATUS_COLOURS.get(status, Color(1, 1, 1, 0.8))
		row.add_child(badge)
	box.add_child(row)


func _row(container: Variant, key: String, value: String,
		colour: Color = Color(1, 1, 1, 0.78)) -> void:
	var target: VBoxContainer = container as VBoxContainer
	if target == null:
		target = _body
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(112, 0)
	name_label.add_theme_font_size_override("font_size", 10)
	name_label.modulate = Color(1, 1, 1, 0.52)
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value_label.add_theme_font_size_override("font_size", 10)
	value_label.modulate = colour
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	target.add_child(row)


func _note(container: Variant, text: String,
		colour: Color = Color(1, 1, 1, 0.52)) -> void:
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
