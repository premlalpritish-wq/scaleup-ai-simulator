class_name ModelNode
extends Control
## One model instance on the canvas: a header, its typed ports, and the drag
## handles that start and finish connections.
##
## Ports are rendered from the model's manifest, so a port the model does not
## declare cannot be created here. The port's colour encodes its physical
## quantity, which is the compatibility key of the whole system.

signal port_pressed(instance_id: String, port_id: String, direction: String, port_global: Vector2)
signal port_released(instance_id: String, port_id: String, direction: String, port_global: Vector2)
signal node_moved(instance_id: String, position: Vector2)
signal node_selected(instance_id: String)
signal node_delete_requested(instance_id: String)

const PORT_HEIGHT := 22.0
const HEADER_HEIGHT := 30.0
const MIN_WIDTH := 240.0
const MAX_WIDTH := 480.0
const FONT_SIZE_LABEL := 11
const FONT_SIZE_UNIT := 10

var instance_id := ""
var model_id := ""
var label := ""
var role := ""
var ports: Array[Dictionary] = []
var selected := false

var _port_rows: Array[HBoxContainer] = []
var _port_hit: Array[Control] = []
var _header: PanelContainer = null
var _title_label: Label = null
var _subtitle_label: Label = null
var _vbox: VBoxContainer = null
var _registry: ModelRegistry = null
var _drag_offset := Vector2.ZERO


func setup(inst: Dictionary, registry: ModelRegistry) -> void:
	instance_id = str(inst["instance_id"])
	model_id = str(inst["model_id"])
	label = str(inst.get("label", model_id))
	role = str(inst.get("role", ""))
	_registry = registry
	ports = _collect_ports(inst)
	_rebuild()


func _collect_ports(inst: Dictionary) -> Array[Dictionary]:
	"""Ports come from the manifest the Python runner published, falling back to
	whatever the document carries so a hand-edited graph still opens."""
	var out: Array[Dictionary] = []
	var params: Dictionary = inst.get("parameters", {})
	if params.has("ports"):
		for p in params["ports"]:
			out.append(p)
		return out
	# A Morris instance declares its control volume inline; derive the same port
	# surface the runner would, so the canvas matches what will actually run.
	if params.has("system"):
		var system: Dictionary = params["system"]
		for stream in system.get("streams", []):
			var sid := str(stream["stream_id"])
			var slabel := str(stream.get("label", sid))
			if stream.has("amount"):
				out.append(_port("in:%s:total" % sid, "input", str(stream["amount"].get("kind", "mass")), str(stream["amount"].get("unit", "kg")), "%s: total" % slabel, null, []))
			for cid in stream.get("mass_fractions", {}):
				var frac: Dictionary = stream["mass_fractions"][cid]
				out.append(_port("in:%s:w:%s" % [sid, cid], "input", "mass_fraction", str(frac.get("unit", "1")), "%s: w(%s)" % [slabel, cid], cid, [cid]))
			for cid in stream.get("component_amounts", {}):
				var comp: Dictionary = stream["component_amounts"][cid]
				out.append(_port("in:%s:%s" % [sid, cid], "input", str(comp.get("kind", "mass")), str(comp.get("unit", "kg")), "%s: %s" % [slabel, cid], cid, [cid]))
		for stream in system.get("streams", []):
			var sid2 := str(stream["stream_id"])
			var slabel2 := str(stream.get("label", sid2))
			var kind := "mass"
			if stream.has("amount"):
				kind = str(stream["amount"].get("kind", "mass"))
			for cid in stream.get("component_amounts", {}):
				out.append(_port("out:%s:%s" % [sid2, cid], "output", kind, "kg", "%s: %s" % [slabel2, cid], cid, [cid]))
			for cid in stream.get("mass_fractions", {}):
				out.append(_port("out:%s:w:%s" % [sid2, cid], "output", "mass_fraction", "1", "%s: w(%s)" % [slabel2, cid], cid, [cid]))
			out.append(_port("out:%s:total" % sid2, "output", kind, "kg", "%s: total" % slabel2, null, []))
		out.append(_port("out:residual:total", "output", "mass", "kg", "total mass residual", null, []))
		for comp in system.get("components", []):
			out.append(_port("out:residual:%s" % str(comp["component_id"]), "output", "mass", "kg", "%s residual" % str(comp.get("label", comp["component_id"])), str(comp["component_id"]), [str(comp["component_id"])]))
	return out


func _port(port_id: String, direction: String, quantity: String, unit: String, label: String, component, components) -> Dictionary:
	return {
		"port_id": port_id,
		"direction": direction,
		"quantity": quantity,
		"unit": unit,
		"label": label,
		"component": component,
		"components": components,
	}


func _rebuild() -> void:
	for child in get_children():
		child.queue_free()
	_port_rows.clear()
	_port_hit.clear()

	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(MIN_WIDTH, 0)
	add_child(panel)

	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 2)
	panel.add_child(vb)

	_header = PanelContainer.new()
	_header.custom_minimum_size = Vector2(0, HEADER_HEIGHT)
	vb.add_child(_header)

	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 6)
	_header.add_child(hb)

	_title_label = Label.new()
	_title_label.text = label
	_title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title_label.add_theme_font_size_override("font_size", 14)
	hb.add_child(_title_label)

	_subtitle_label = Label.new()
	_subtitle_label.text = role if role != "" else model_id
	_subtitle_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_subtitle_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_subtitle_label.add_theme_font_size_override("font_size", 10)
	_subtitle_label.modulate = Color(1, 1, 1, 0.6)
	vb.add_child(_subtitle_label)

	_vbox = VBoxContainer.new()
	_vbox.add_theme_constant_override("separation", 1)
	vb.add_child(_vbox)

	var max_label_width := 0.0
	var max_unit_width := 0.0
	var font_label := get_theme_font("font", "Label")
	var font_size_label := FONT_SIZE_LABEL
	var font_size_unit := FONT_SIZE_UNIT

	# Pre-calculate max widths
	for p in ports:
		var label_text := str(p["label"])
		var unit_text := str(p["unit"])
		var label_size := font_label.get_string_size(label_text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size_label)
		var unit_size := font_label.get_string_size(unit_text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size_unit)
		max_label_width = max(max_label_width, label_size.x)
		max_unit_width = max(max_unit_width, unit_size.x)

	# Calculate required width: handle(14) + spacer(4) + label + spacer(8) + unit + spacer(8) + out_handle(14) + margins(16)
	var required_width := 14.0 + 4.0 + max_label_width + 8.0 + max_unit_width + 8.0 + 14.0 + 16.0
	required_width = clampf(required_width, MIN_WIDTH, MAX_WIDTH)

	for p in ports:
		_add_port_row(p, required_width, max_label_width, max_unit_width)

	custom_minimum_size = Vector2(required_width, HEADER_HEIGHT + 26 + ports.size() * PORT_HEIGHT)
	size = custom_minimum_size


func _add_port_row(p: Dictionary, node_width: float, max_label_width: float, max_unit_width: float) -> void:
	var row := HBoxContainer.new()
	row.custom_minimum_size = Vector2(0, PORT_HEIGHT)
	_vbox.add_child(row)
	_port_rows.append(row)

	var direction := str(p["direction"])
	var is_input := direction == "input"

	var handle := Control.new()
	handle.custom_minimum_size = Vector2(14, 14)
	handle.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	handle.tooltip_text = "%s (%s %s)" % [str(p["label"]), str(p["quantity"]), str(p["unit"])]
	handle.gui_input.connect(_on_handle_input.bind(p, handle))
	row.add_child(handle)
	_port_hit.append(handle)

	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(4, 0)
	row.add_child(spacer)

	var name := Label.new()
	name.text = str(p["label"])
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name.custom_minimum_size = Vector2(max_label_width, 0)
	name.add_theme_font_size_override("font_size", FONT_SIZE_LABEL)
	name.clip_text = true
	row.add_child(name)

	var spacer2 := Control.new()
	spacer2.custom_minimum_size = Vector2(8, 0)
	row.add_child(spacer2)

	var unit := Label.new()
	unit.text = str(p["unit"])
	unit.custom_minimum_size = Vector2(max_unit_width, 0)
	unit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	unit.add_theme_font_size_override("font_size", FONT_SIZE_UNIT)
	unit.modulate = Color(1, 1, 1, 0.55)
	row.add_child(unit)

	if not is_input:
		var spacer3 := Control.new()
		spacer3.custom_minimum_size = Vector2(8, 0)
		row.add_child(spacer3)

		var out_handle := Control.new()
		out_handle.custom_minimum_size = Vector2(14, 14)
		out_handle.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		out_handle.gui_input.connect(_on_handle_input.bind(p, out_handle))
		row.add_child(out_handle)
		_port_hit.append(out_handle)

	_style_handle(handle, p, is_input)


func _style_handle(handle: Control, p: Dictionary, is_input: bool) -> void:
	var colour: Color = _registry.colour_for(str(p["quantity"]))
	handle.set_meta("colour", colour)
	handle.set_meta("is_input", is_input)


func _on_handle_input(event: InputEvent, p: Dictionary, handle: Control) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			var global_pos := handle.get_global_rect().position + handle.get_global_rect().size * 0.5
			emit_signal("port_pressed", instance_id, str(p["port_id"]), str(p["direction"]), global_pos)
		else:
			var global_pos := handle.get_global_rect().position + handle.get_global_rect().size * 0.5
			emit_signal("port_released", instance_id, str(p["port_id"]), str(p["direction"]), global_pos)
	elif event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_LEFT:
		pass


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		_drag_offset = event.position
		emit_signal("node_selected", instance_id)
		accept_event()
	elif event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_LEFT:
		var new_pos: Vector2 = position + (event.position - _drag_offset)
		position = new_pos
		emit_signal("node_moved", instance_id, new_pos)
		accept_event()


func _notification(what: int) -> void:
	if what == NOTIFICATION_DRAW:
		var colour := Color(0.16, 0.18, 0.22, 0.95)
		if selected:
			colour = Color(0.22, 0.28, 0.38, 0.98)
		draw_rect(Rect2(Vector2.ZERO, size), colour, true)
		draw_rect(Rect2(Vector2.ZERO, size), Color(1, 1, 1, selected and 0.5 or 0.18), false, 1.5)
		for handle in _port_hit:
			var hcolour: Color = handle.get_meta("colour", Color.WHITE)
			var rect := Rect2(handle.get_global_rect().position - global_position, Vector2(12, 12))
			draw_circle(rect.position + Vector2(6, 6), 6, hcolour)
			draw_circle(rect.position + Vector2(6, 6), 6, Color(1, 1, 1, 0.35), false, 1.0)


func port_global_position(port_id: String) -> Vector2:
	for i in range(ports.size()):
		if str(ports[i]["port_id"]) == port_id:
			var row: Control = _port_rows[i]
			for child in row.get_children():
				if child is Control and child.get_meta("colour", null) != null:
					return child.get_global_rect().position + child.get_global_rect().size * 0.5
	return global_position + Vector2(0, HEADER_HEIGHT)


func port_position_index(port_id: String) -> int:
	for i in range(ports.size()):
		if str(ports[i]["port_id"]) == port_id:
			return i
	return -1


func set_selected(value: bool) -> void:
	selected = value
	queue_redraw()


func refresh_ports(new_ports: Array[Dictionary]) -> void:
	ports = new_ports
	_rebuild()
