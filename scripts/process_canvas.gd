class_name ProcessCanvas
extends Control
## The process canvas: model nodes, typed connections, and drag-to-connect.
##
## Connections are drawn as bezier curves whose colour is the physical quantity
## being carried. A pending drag is drawn dashed. The canvas never decides
## whether a connection is legal -- it records the intent and asks the Python
## runner, which enforces quantity, unit, component and capability rules.

signal connection_started(from_instance: String, from_port: String, from_direction: String, from_global: Vector2)
signal connection_completed(from_instance: String, from_port: String, from_direction: String, from_global: Vector2, to_instance: String, to_port: String, to_direction: String, to_global: Vector2)
signal connection_dropped(global_position: Vector2)
signal instance_selected(instance_id: String)

var nodes: Dictionary = {}
var connections: Array[Dictionary] = []
var _pending: Dictionary = {}
var _pending_end := Vector2.ZERO
var _hover_target := {}
var _document: GraphDocument = null
var _registry: ModelRegistry = null
var _line_layer: Control = null

# Zoom/pan state
var _zoom := 1.0
var _zoom_target := 1.0
var _pan_offset := Vector2.ZERO
var _drag_pan_origin := Vector2.ZERO
var _is_panning := false
const MIN_ZOOM := 0.25
const MAX_ZOOM := 3.0
const ZOOM_SPEED := 1.2


func setup(document: GraphDocument, registry: ModelRegistry) -> void:
	_document = document
	_registry = registry
	_line_layer = Control.new()
	_line_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_line_layer)
	move_child(_line_layer, 0)
	clip_contents = true
	_zoom = 1.0
	_zoom_target = 1.0
	_pan_offset = Vector2.ZERO
	_apply_default_layout()


func clear_nodes() -> void:
	for id in nodes:
		nodes[id].queue_free()
	nodes.clear()
	_pending = {}
	_hover_target = {}
	_line_layer.queue_free()
	_line_layer = Control.new()
	_line_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_line_layer)
	move_child(_line_layer, 0)
	_zoom = 1.0
	_zoom_target = 1.0
	_pan_offset = Vector2.ZERO
	_apply_default_layout()


func _apply_default_layout() -> void:
	"""Apply a default layout to nodes without valid positions."""
	var has_any_position := false
	for inst in _document.instances:
		var pos: Dictionary = inst.get("position", {})
		if pos.has("x") and pos.has("y"):
			if pos["x"] != 0 or pos["y"] != 0:
				has_any_position = true
				break
	
	if has_any_position:
		var placed: Dictionary = {}
		for inst in _document.instances:
			var pos: Dictionary = inst.get("position", {})
			if not (pos.has("x") and pos.has("y")) or (pos["x"] == 0 and pos["y"] == 0):
				placed[inst["instance_id"]] = true
		
		var cols := 4
		var spacing_x := 320.0
		var spacing_y := 220.0
		var start_x := 80.0
		var start_y := 90.0
		var idx := 0
		for inst in _document.instances:
			if placed.has(inst["instance_id"]):
				var col := idx % cols
				var row := idx / cols
				var node: ModelNode = nodes.get(inst["instance_id"])
				if node:
					node.position = Vector2(start_x + col * spacing_x, start_y + row * spacing_y)
				inst["position"] = {"x": start_x + col * spacing_x, "y": start_y + row * spacing_y}
				idx += 1
	else:
		var cols := 4
		var spacing_x := 320.0
		var spacing_y := 220.0
		var start_x := 80.0
		var start_y := 90.0
		for i in range(_document.instances.size()):
			var inst := _document.instances[i]
			var col := i % cols
			var row := i / cols
			var node: ModelNode = nodes.get(inst["instance_id"])
			if node:
				node.position = Vector2(start_x + col * spacing_x, start_y + row * spacing_y)
			inst["position"] = {"x": start_x + col * spacing_x, "y": start_y + row * spacing_y}
	
	call_deferred("zoom_to_fit")


func zoom_to_fit() -> void:
	if nodes.is_empty():
		return
	var min_x := INF
	var max_x := -INF
	var min_y := INF
	var max_y := -INF
	for id in nodes:
		var node: ModelNode = nodes[id]
		var rect := Rect2(node.position, node.size)
		min_x = min(min_x, rect.position.x)
		max_x = max(max_x, rect.position.x + rect.size.x)
		min_y = min(min_y, rect.position.y)
		max_y = max(max_y, rect.position.y + rect.size.y)
	
	var content_w := max_x - min_x
	var content_h := max_y - min_y
	if content_w <= 0 or content_h <= 0:
		return
	
	var padding := 60.0
	var scale_x := (size.x - padding * 2) / content_w
	var scale_y := (size.y - padding * 2) / content_h
	var new_zoom: float = min(scale_x, scale_y)
	new_zoom = clampf(new_zoom, MIN_ZOOM, MAX_ZOOM)
	
	_zoom = new_zoom
	_zoom_target = new_zoom
	
	var center_x := (min_x + max_x) * 0.5
	var center_y := (min_y + max_y) * 0.5
	_pan_offset = Vector2(size.x * 0.5, size.y * 0.5) - Vector2(center_x, center_y) * _zoom
	queue_redraw()


func build_from_document() -> void:
	clear_nodes()
	for inst in _document.instances:
		add_node(inst)
	for conn in _document.connections:
		connections.append(conn)


func add_node(inst: Dictionary) -> void:
	if nodes.has(str(inst["instance_id"])):
		nodes[str(inst["instance_id"])].queue_free()
		nodes.erase(str(inst["instance_id"]))
	var node := ModelNode.new()
	node.setup(inst, _registry)
	node.port_pressed.connect(_on_port_pressed)
	node.port_released.connect(_on_port_released)
	node.node_moved.connect(_on_node_moved)
	node.node_selected.connect(_on_node_selected)
	node.position = Vector2(inst["position"]["x"], inst["position"]["y"])
	add_child(node)
	# move_child puts the node at the end of the child list (drawn last, on top).
	# The line_layer is at index 0 (drawn first/behind). No move_to_back() needed.
	move_child(node, get_child_count() - 1)
	nodes[str(inst["instance_id"])] = node
	queue_redraw()


func _on_node_moved(instance_id: String, position: Vector2) -> void:
	if _document == null:
		return
	var inst := _document.find_instance(instance_id)
	if not inst.is_empty():
		inst["position"] = {"x": position.x, "y": position.y}
	queue_redraw()


func _on_node_selected(instance_id: String) -> void:
	emit_signal("instance_selected", instance_id)


func _on_port_pressed(instance_id: String, port_id: String, direction: String, port_global: Vector2) -> void:
	_pending = {
		"instance_id": instance_id,
		"port_id": port_id,
		"direction": direction,
		"global": port_global,
	}
	_pending_end = port_global
	_hover_target = {}
	emit_signal("connection_started", instance_id, port_id, direction, port_global)
	queue_redraw()


func _on_port_released(instance_id: String, port_id: String, direction: String, port_global: Vector2) -> void:
	if _pending.is_empty():
		return
	var target := _hover_target
	_pending = {}
	_hover_target = {}
	if not target.is_empty():
		emit_signal(
			"connection_completed",
			str(_pending.get("instance_id", instance_id)),
			str(_pending.get("port_id", port_id)),
			str(_pending.get("direction", direction)),
			port_global,
			str(target["instance_id"]),
			str(target["port_id"]),
			str(target["direction"]),
			str(target["global"]),
		)
	else:
		emit_signal("connection_dropped", port_global)
	queue_redraw()


func set_hover_target(target: Dictionary) -> void:
	_hover_target = target


func _screen_to_logical(screen_pos: Vector2) -> Vector2:
	return (screen_pos - _pan_offset) / _zoom


func _gui_input(event: InputEvent) -> void:
	var logical_pos := _screen_to_logical(event.position) if event is InputEventMouse else Vector2.ZERO
	
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_MIDDLE or (event.button_index == MOUSE_BUTTON_LEFT and event.ctrl_pressed):
			if event.pressed:
				_is_panning = true
				_drag_pan_origin = event.position - _pan_offset
				accept_event()
			else:
				_is_panning = false
				accept_event()
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom_target = clampf(_zoom_target * ZOOM_SPEED, MIN_ZOOM, MAX_ZOOM)
			accept_event()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom_target = clampf(_zoom_target / ZOOM_SPEED, MIN_ZOOM, MAX_ZOOM)
			accept_event()
	elif event is InputEventMouseMotion:
		var logical_mouse := _screen_to_logical(event.position)
		if _is_panning:
			_pan_offset = event.position - _drag_pan_origin
			queue_redraw()
			accept_event()
		elif not _pending.is_empty():
			_pending_end = logical_mouse
			_hover_target = _port_at(logical_mouse)
			queue_redraw()
			accept_event()
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and not event.pressed:
		if not _pending.is_empty():
			_pending = {}
			_hover_target = {}
			queue_redraw()
			accept_event()


func _port_at(position: Vector2) -> Dictionary:
	var best: Dictionary = {}
	var best_dist := 18.0
	for id in nodes:
		var node: ModelNode = nodes[id]
		for p in node.ports:
			var gp := node.port_global_position(str(p["port_id"]))
			var d := gp.distance_to(position)
			if d < best_dist:
				best_dist = d
				best = {
					"instance_id": node.instance_id,
					"port_id": str(p["port_id"]),
					"direction": str(p["direction"]),
					"global": gp,
				}
	return best


func _notification(what: int) -> void:
	if what == NOTIFICATION_DRAW:
		# Apply zoom/pan transform using canvas transform
		draw_set_transform(_pan_offset, 0, Vector2(_zoom, _zoom))
		
		_draw_grid()
		for conn in connections:
			_draw_connection(conn, false)
		if not _pending.is_empty():
			_draw_pending()
		
		draw_set_transform(Vector2.ZERO, 0, Vector2(1.0, 1.0))


func _draw_grid() -> void:
	var step := 24.0
	var colour := Color(1, 1, 1, 0.045)
	for x in range(0, int(size.x) + 1, int(step)):
		draw_line(Vector2(x, 0), Vector2(x, size.y), colour, 1.0)
	for y in range(0, int(size.y) + 1, int(step)):
		draw_line(Vector2(0, y), Vector2(size.x, y), colour, 1.0)


func _draw_connection(conn: Dictionary, pending: bool) -> void:
	var src := _endpoint_global(conn["source"]["instance_id"], conn["source"]["port_id"])
	var dst := _endpoint_global(conn["target"]["instance_id"], conn["target"]["port_id"])
	if src == Vector2.ZERO or dst == Vector2.ZERO:
		return
	var quantity := _port_quantity(conn["source"]["instance_id"], conn["source"]["port_id"])
	var colour: Color = _registry.colour_for(quantity)
	var mid := (src + dst) * 0.5 + Vector2(0, -40)
	if pending:
		draw_dashed_line(src, _pending_end, colour, 1.5, 6.0, false)
		return
	_draw_bezier(src, mid, dst, colour)


func _draw_pending() -> void:
	var colour := Color(1, 1, 1, 0.45)
	if not _hover_target.is_empty():
		colour = _registry.colour_for(_port_quantity(str(_hover_target["instance_id"]), str(_hover_target["port_id"])))
	colour = Color(colour.r, colour.g, colour.b, 0.7)
	draw_dashed_line(_pending.get("global", Vector2.ZERO), _pending_end, colour, 1.5, 6.0, false)


func _draw_bezier(a: Vector2, c: Vector2, b: Vector2, colour: Color) -> void:
	var points := 16
	for i in range(points):
		var t0 := float(i) / points
		var t1 := float(i + 1) / points
		var p0 := _quad(a, c, b, t0)
		var p1 := _quad(a, c, b, t1)
		draw_line(p0, p1, colour, 2.0)


func _quad(a: Vector2, c: Vector2, b: Vector2, t: float) -> Vector2:
	var u := 1.0 - t
	return u * u * a + 2.0 * u * t * c + t * t * b


func _endpoint_global(instance_id: String, port_id: String) -> Vector2:
	if not nodes.has(instance_id):
		return Vector2.ZERO
	return nodes[instance_id].port_global_position(port_id)


func _port_quantity(instance_id: String, port_id: String) -> String:
	if not nodes.has(instance_id):
		return "mass"
	var node: ModelNode = nodes[instance_id]
	for p in node.ports:
		if str(p["port_id"]) == port_id:
			return str(p["quantity"])
	return "mass"


func connections_for(instance_id: String) -> Array[Dictionary]:
	return connections.filter(
		func(c): return str(c["source"]["instance_id"]) == instance_id or str(c["target"]["instance_id"]) == instance_id
	)
