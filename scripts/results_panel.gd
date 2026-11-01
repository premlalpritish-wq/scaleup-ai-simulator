class_name ResultsPanel
extends PanelContainer
## The results panel: what each instance produced, what it could not, and how
## far each balance closed.
##
## Values are shown with their state, never flattened into a number. An
## unresolved value reads as "unresolved", a range as "15-16 h", an unknown as
## "unknown" -- because the whole point of the panel is that "absent" is not
## "zero".

var _tabs: TabContainer = null
var _registry: ModelRegistry = null


func setup(registry: ModelRegistry) -> void:
	_registry = registry


func show_results(payload: Dictionary) -> void:
	if _tabs != null:
		_tabs.queue_free()
	_tabs = TabContainer.new()
	_tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tabs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(_tabs)

	var results: Array = payload.get("results", [])
	if results.is_empty():
		var label := Label.new()
		label.text = "Nothing was executed.\n\nSee the validation panel for why."
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		_tabs.add_child(label)
		return

	for result in results:
		_tabs.add_child(_instance_tab(result))


func _instance_tab(result: Dictionary) -> Control:
	var scroll := ScrollContainer.new()
	scroll.name = str(result.get("instance_id", "instance"))

	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(vb)

	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	vb.add_child(header)

	var title := Label.new()
	title.text = str(result.get("instance_id", ""))
	title.add_theme_font_size_override("font_size", 14)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)

	var status := Label.new()
	status.text = str(result.get("status", ""))
	match str(result.get("status", "")):
		"success":
			status.modulate = Color(0.62, 0.88, 0.62)
		"success_with_warnings":
			status.modulate = Color(0.95, 0.82, 0.45)
		_:
			status.modulate = Color(0.95, 0.58, 0.52)
	header.add_child(status)

	var model := Label.new()
	model.text = "%s  v%s" % [str(result.get("model_id", "")), str(result.get("model_version", ""))]
	model.add_theme_font_size_override("font_size", 10)
	model.modulate = Color(1, 1, 1, 0.55)
	vb.add_child(model)

	var summary: Dictionary = result.get("raw_summary", {})
	if not summary.is_empty():
		var mode := Label.new()
		mode.text = _summary_line(summary)
		mode.add_theme_font_size_override("font_size", 10)
		mode.modulate = Color(1, 1, 1, 0.6)
		mode.autowrap_mode = TextServer.AUTOWRAP_WORD
		vb.add_child(mode)

	var outputs: Array = result.get("outputs", [])
	if outputs.is_empty():
		var none := Label.new()
		none.text = "No values produced."
		none.modulate = Color(0.95, 0.58, 0.52)
		vb.add_child(none)
	else:
		var tree := _outputs_tree(outputs)
		vb.add_child(tree)

	var residuals: Array = result.get("residuals", [])
	if not residuals.is_empty():
		vb.add_child(_residuals(residuals))

	var unresolved: Array = result.get("unresolved", [])
	if not unresolved.is_empty():
		vb.add_child(_unresolved(unresolved))

	return scroll


func _summary_line(summary: Dictionary) -> String:
	var bits: Array[String] = []
	if summary.has("process_mode"):
		bits.append(str(summary["process_mode"]))
	if summary.has("solvability"):
		bits.append(str(summary["solvability"]))
	if summary.has("rank"):
		bits.append("rank %s of %s unknowns" % [str(summary.get("rank")), str(summary.get("n_unknowns"))])
	if summary.has("is_consistent"):
		bits.append("consistent" if bool(summary["is_consistent"]) else "inconsistent")
	if summary.has("balances_close"):
		bits.append("balances close" if bool(summary["balances_close"]) else "balances do not close")
	if summary.has("predicted_values"):
		bits.append("%s predictions" % str(summary.get("predicted_values")))
	if summary.has("unresolved_targets"):
		bits.append("%s unresolved target(s)" % str(summary.get("unresolved_targets")))
	return "  |  ".join(bits)


func _outputs_tree(outputs: Array) -> Tree:
	var tree := Tree.new()
	tree.columns = 5
	tree.column_titles_visible = true
	tree.set_column_title(0, "port")
	tree.set_column_title(1, "state")
	tree.set_column_title(2, "value")
	tree.set_column_title(3, "unit")
	# The provenance column keeps the runner's own vocabulary intact. A reported
	# observation and a derived value are different claims, and relabelling
	# either one here would blur exactly the distinction this column exists for.
	tree.set_column_title(4, "provenance")
	tree.hide_root = true
	tree.size_flags_vertical = Control.SIZE_EXPAND_FILL

	for out in outputs:
		var value: Dictionary = out.get("value", {})
		var item := tree.create_item()
		item.set_text(0, str(out.get("ref", {}).get("port_id", "")))
		item.set_text(1, str(value.get("state", "")))
		item.set_text(2, str(value.get("display", "")))
		item.set_text(3, str(value.get("unit", "")))
		item.set_text(4, str(value.get("provenance", "")))

		# An observed reading and a computed value are told apart by colour as
		# well as by text, because "the model produced a number" is not a claim
		# the number was measured.
		var provenance := str(value.get("provenance", ""))
		match provenance:
			"reported", "digitized":
				item.set_custom_color(4, Color(0.62, 0.88, 0.62))
			"derived", "solved", "transferred":
				item.set_custom_color(4, Color(0.62, 0.78, 0.95))
			"assumed":
				item.set_custom_color(4, Color(0.95, 0.82, 0.45))
			"unknown":
				item.set_custom_color(4, Color(0.95, 0.72, 0.45))
			_:
				item.set_custom_color(4, Color(1, 1, 1, 0.5))

		item.set_tooltip_text(4, _provenance_tooltip(value))
		match str(value.get("state", "")):
			"number", "zero":
				item.set_custom_color(1, Color(0.62, 0.88, 0.62))
				item.set_custom_color(2, Color(0.85, 0.95, 0.85))
				if str(value.get("state", "")) == "zero":
					item.set_tooltip_text(2, "A stated zero, not a computed zero. The distinction is deliberate.")
			"range":
				item.set_custom_color(1, Color(0.95, 0.82, 0.45))
				item.set_tooltip_text(2, "Reported as an interval. It is never collapsed to a point value.")
			"unresolved":
				item.set_custom_color(1, Color(0.95, 0.58, 0.52))
				item.set_tooltip_text(2, str(value.get("reason", "not determined")))
			"unknown":
				item.set_custom_color(1, Color(0.95, 0.72, 0.45))
				item.set_tooltip_text(2, str(value.get("reason", "not reported by the source")))
			"not_reported":
				item.set_custom_color(1, Color(0.72, 0.72, 0.72))
				item.set_tooltip_text(2, "The model does not report this quantity at all.")
			_:
				item.set_custom_color(1, Color(0.95, 0.58, 0.52))
		if str(value.get("determination", "")) != "":
			item.set_tooltip_text(2, "Determination: %s" % str(value["determination"]))
	return tree


## What the runner can say about where one value came from.
##
## Every field is printed only if the runner published it. The summary never
## upgrades a value's standing: a value whose provenance is `unknown` is not
## described as reported, and a value that ran successfully is not described as
## scientifically validated.
func _provenance_tooltip(value: Dictionary) -> String:
	var lines := PackedStringArray()
	lines.append("provenance: %s" % str(value.get("provenance", "(absent)")))
	lines.append("state: %s" % str(value.get("state", "(absent)")))
	if str(value.get("method", "")) != "":
		lines.append("method: %s" % str(value["method"]))
	if str(value.get("source_ref", "")) != "":
		lines.append("source: %s" % str(value["source_ref"]))
	if str(value.get("determination", "")) != "":
		lines.append("determination: %s" % str(value["determination"]))
	if str(value.get("reason", "")) != "":
		lines.append("reason: %s" % str(value["reason"]))
	var conversion: Variant = value.get("conversion", null)
	if conversion != null and not str(conversion).is_empty():
		lines.append("conversion: %s" % JSON.stringify(conversion))
	var chain: Array = value.get("provenance_chain", [])
	if chain.is_empty():
		lines.append("")
		lines.append("no provenance chain was published for this value")
	return "\n".join(lines)


func _residuals(residuals: Array) -> VBoxContainer:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 2)

	var heading := Label.new()
	heading.text = "balance residuals (sec. 4.6.2)"
	heading.add_theme_font_size_override("font_size", 11)
	heading.modulate = Color(0.72, 0.80, 0.95)
	vb.add_child(heading)

	for r in residuals:
		var row := Label.new()
		var within := bool(r.get("within_tolerance", false))
		row.text = "%s:  %s %s   (tolerance %s)   %s" % [
			str(r.get("label", "")),
			_str_num(r.get("value", 0.0)),
			str(r.get("unit", "")),
			_str_num(r.get("tolerance", 0.0)),
			"closes" if within else "DOES NOT CLOSE",
		]
		row.add_theme_font_size_override("font_size", 11)
		row.modulate = Color(0.62, 0.88, 0.62) if within else Color(0.95, 0.58, 0.52)
		if str(r.get("determination", "")) == "representative":
			row.tooltip_text = "This residual is computed from a representative member of a free family. See the diagnostics panel."
		vb.add_child(row)
	return vb


func _unresolved(unresolved: Array) -> VBoxContainer:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 2)

	var heading := Label.new()
	heading.text = "not determined"
	heading.add_theme_font_size_override("font_size", 11)
	heading.modulate = Color(0.95, 0.58, 0.52)
	vb.add_child(heading)

	for u in unresolved:
		var row := Label.new()
		row.text = "%s -- %s" % [str(u.get("variable_id", u.get("target", ""))), str(u.get("reason", ""))]
		row.autowrap_mode = TextServer.AUTOWRAP_WORD
		row.add_theme_font_size_override("font_size", 10)
		vb.add_child(row)
	return vb


## GDScript's `%` operator has no `%g` conversion, so six significant digits
## are computed here. Very large or very small values fall back to scientific
## notation, because `%.6f` would render 1e-8 as "0.000000".
func _str_num(value) -> String:
	if value == null:
		return "-"
	var f := float(value)
	if not is_finite(f):
		return "inf" if f > 0.0 else "-inf"
	if f == 0.0:
		return "0"
	var a := absf(f)
	if a >= 1000000.0 or a < 0.0001:
		var exponent := 0
		var normalised := a
		while normalised >= 10.0:
			normalised /= 10.0
			exponent += 1
		while normalised < 1.0:
			normalised *= 10.0
			exponent -= 1
		return "%s%.5fe%s%d" % ["-" if f < 0.0 else "", normalised, "+" if exponent >= 0 else "-", absi(exponent)]
	return "%.6f" % f


func clear() -> void:
	if _tabs == null:
		return
	_tabs.queue_free()
	_tabs = null
