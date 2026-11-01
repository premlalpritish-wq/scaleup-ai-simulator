class_name CompatibilityPanel
extends PanelContainer
## Which models are in the simulation, which are not, and why.
##
## ## No rules here
##
## This panel renders `--describe-connections`. It holds no model list, no quantity
## pair, and no rule of its own: the compatibility engine in
## `composition/composition/cross_model.py` is the authority, and every position,
## reason and unresolved question shown here is read from it. A rule changed there
## reaches this panel without anything here being edited.
##
## ## Why the default simulation uses one model
##
## The engine permits two ordered pairs and both are same-model. The scene states
## that rather than hiding it: a user who wonders why Morris or Zielinski is not in
## the flask gets an answer with a citation.

var _scroll: ScrollContainer
var _body: VBoxContainer
var _summary: Label
var _entries: Array = []


func setup() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var heading := Label.new()
	heading.text = "Models in the project"
	heading.add_theme_font_size_override("font_size", 13)
	vb.add_child(heading)

	_summary = Label.new()
	_summary.text = "The compatibility engine has not been consulted yet."
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.add_theme_font_size_override("font_size", 10)
	_summary.modulate = Color(1, 1, 1, 0.62)
	vb.add_child(_summary)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(_scroll)

	_body = VBoxContainer.new()
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_theme_constant_override("separation", 4)
	_scroll.add_child(_body)


func clear() -> void:
	_entries.clear()
	if _summary != null:
		_summary.text = "The compatibility engine has not been consulted yet."
	_clear_body()


## Show the boundary matrix, highlighting the pairs that touch `active_model`.
func show_connections(connections: Dictionary, active_model: String) -> void:
	_clear_body()
	_entries.clear()

	var claim_scope := str(connections.get("claim_scope", ""))
	_summary.text = claim_scope if claim_scope != "" else \
		"Positions read from the compatibility engine."

	var boundaries := connections.get("boundaries", []) as Array
	if boundaries.is_empty():
		_note(null, "The compatibility engine returned no boundaries.", Color(1, 0.6, 0.6))
		return

	var permitted := 0
	for boundary in boundaries:
		if bool(boundary.get("permitted", false)):
			permitted += 1

	_summary.text = ("%d of %d ordered model pairs may be connected. %s" % [
		permitted, boundaries.size(), claim_scope]).substr(0, 320)

	for boundary in boundaries:
		var source := str(boundary.get("source_model", "?"))
		var target := str(boundary.get("target_model", "?"))
		var touches := source == active_model or target == active_model
		_entries.append({
			"source": source,
			"target": target,
			"permitted": bool(boundary.get("permitted", false)),
			"touches_active": touches,
		})
		_card(boundary, touches)

	var unclassified: Array = connections.get("quantity_pairs_examined", [])
	if not unclassified.is_empty():
		_section("quantity pairs examined by the policy")
		for pair in unclassified:
			_note(null, "  " + str(pair), Color(1, 1, 1, 0.6))


# -------------------------------------------------------- harness accessors


func boundaries() -> Array:
	return _entries


func permitted_pairs() -> PackedStringArray:
	var names := PackedStringArray()
	for entry in _entries:
		if bool(entry.get("permitted", false)):
			names.append("%s -> %s" % [str(entry.get("source", "")),
				str(entry.get("target", ""))])
	return names


func refused_pairs_touching(model_id: String) -> PackedStringArray:
	var names := PackedStringArray()
	for entry in _entries:
		if bool(entry.get("permitted", false)):
			continue
		if not bool(entry.get("touches_active", false)):
			continue
		names.append("%s -> %s" % [str(entry.get("source", "")),
			str(entry.get("target", ""))])
	return names


func has_forbidden_shortcut() -> bool:
	"""The scene must not present a model pair the engine refuses as available."""
	for entry in _entries:
		if bool(entry.get("touches_active", false)) and bool(entry.get("permitted", false)):
			return true
	return false


# ------------------------------------------------------------------ rendering


func _section(title: String) -> void:
	var label := Label.new()
	label.text = "== %s ==" % title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	_body.add_child(label)


func _card(boundary: Dictionary, touches: bool) -> void:
	var permitted := bool(boundary.get("permitted", false))
	var base := Color(0.56, 0.82, 0.60) if permitted else Color(0.95, 0.72, 0.45)
	if touches:
		base = base.lerp(Color(0.72, 0.80, 1.0), 0.45)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(base.r, base.g, base.b, 0.10 if permitted else 0.07)
	style.border_color = Color(base.r, base.g, base.b, 0.45)
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
	title.text = "%s  ->  %s" % [str(boundary.get("source_model", "?")),
		str(boundary.get("target_model", "?"))]
	title.add_theme_font_size_override("font_size", 11)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	var badge := Label.new()
	badge.text = "permitted" if permitted else "refused"
	badge.add_theme_font_size_override("font_size", 9)
	badge.modulate = base
	head.add_child(badge)
	if touches:
		var marker := Label.new()
		marker.text = "  (this simulation)"
		marker.add_theme_font_size_override("font_size", 9)
		marker.modulate = Color(0.72, 0.80, 1.0, 0.85)
		head.add_child(marker)
	box.add_child(head)

	_note(box, "stance: " + str(boundary.get("stance", "?")))
	_note(box, str(boundary.get("reason", "")))

	var evidence := boundary.get("evidence", []) as Array
	if not evidence.is_empty():
		_field(box, "evidence", str(evidence[0]).substr(0, 260))

	var unresolved := boundary.get("unresolved", []) as Array
	if not unresolved.is_empty():
		_field(box, "unresolved", str(unresolved[0]).substr(0, 260),
			Color(0.95, 0.82, 0.60))

	_body.add_child(box)


func _field(box: VBoxContainer, key: String, value: String,
		colour: Color = Color(1, 1, 1, 0.62)) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(76, 0)
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
