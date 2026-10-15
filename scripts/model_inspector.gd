class_name ModelInspector
extends PanelContainer
## The model inspector: parameters, units, assumptions and provenance for the
## selected node.
##
## Everything shown here comes from the model's own manifest or from the graph
## document. Nothing is computed.

var _instance: Dictionary = {}
var _tree: Tree = null
var _registry: ModelRegistry = null


func setup(registry: ModelRegistry) -> void:
	_registry = registry


func _ready() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(scroll)

	_tree = Tree.new()
	_tree.columns = 2
	_tree.column_titles_visible = true
	_tree.set_column_title(0, "property")
	_tree.set_column_title(1, "value")
	_tree.set_column_expand(0, false)
	_tree.set_column_expand(1, true)
	_tree.hide_root = true
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(_tree)


func show_instance(inst: Dictionary, ports: Array[Dictionary]) -> void:
	_instance = inst
	_populate(ports)


func clear() -> void:
	_instance = {}
	if _tree == null:
		return
	_tree.clear()


func _populate(ports: Array[Dictionary]) -> void:
	_tree.clear()
	if _instance.is_empty():
		var root := _tree.create_item()
		root.set_text(0, "No node selected")
		return

	var root := _tree.create_item()
	root.set_text(0, str(_instance.get("label", _instance.get("instance_id", "node"))))
	root.set_text(1, str(_instance.get("role", "")))

	_add_section("identity")
	_add_row("model_id", str(_instance.get("model_id", "")))
	_add_row("model_version", str(_instance.get("model_version", "")))
	_add_row("instance_id", str(_instance.get("instance_id", "")))

	var params: Dictionary = _instance.get("parameters", {})

	if params.has("system"):
		var system: Dictionary = params["system"]
		_add_section("control volume")
		_add_row("system_id", str(system.get("system_id", "")))
		_add_row("process_mode", str(system.get("process_mode", "")))
		_add_row("basis", str(system.get("basis", "")))
		if system.has("components"):
			var comps := []
			for c in system["components"]:
				comps.append("%s (%s)" % [str(c.get("component_id")), str(c.get("label", ""))])
			_add_row("components", ", ".join(comps))
		if system.has("assumptions"):
			_add_section("declared assumptions")
			for a in system["assumptions"]:
				var child := _tree.create_item(root)
				child.set_text(0, str(a.get("assumption_id", "")))
				child.set_text(1, str(a.get("statement", "")))
				child.set_tooltip_text(0, str(a.get("rationale", "")))

	if params.has("execution"):
		_add_section("execution")
		_add_row("mode", str(params["execution"].get("mode", "evidence_replay")))

	if params.has("assumptions"):
		_add_section("assumptions")
		for a in params["assumptions"]:
			var child := _tree.create_item(root)
			child.set_text(0, str(a.get("assumption_id", "")))
			child.set_text(1, str(a.get("statement", "")))
			child.set_tooltip_text(0, str(a.get("rationale", "")))

	if params.has("missing_information"):
		_add_section("declared missing information")
		for m in params["missing_information"]:
			var child := _tree.create_item(root)
			child.set_text(0, str(m.get("parameter_id", "")))
			child.set_text(1, str(m.get("reason", "")))

	_add_section("ports (%d)" % ports.size())
	for p in ports:
		var child := _tree.create_item(root)
		var quantity := str(p.get("quantity", ""))
		child.set_text(0, "%s  %s" % [str(p.get("port_id", "")), str(p.get("unit", ""))])
		child.set_text(1, "%s (%s)" % [quantity, str(p.get("direction", ""))])
		if str(p.get("unavailable_reason", "")) != "":
			child.set_custom_color(1, Color(0.95, 0.62, 0.45))
			child.set_tooltip_text(1, str(p["unavailable_reason"]))
		elif str(p.get("provenance", "")) == "unknown":
			child.set_custom_color(1, Color(0.95, 0.72, 0.45))
		elif str(p.get("provenance", "")) == "reported":
			child.set_custom_color(1, Color(0.62, 0.88, 0.62))
		elif str(p.get("provenance", "")) == "derived":
			child.set_custom_color(1, Color(0.62, 0.78, 0.95))


func _add_section(name: String) -> void:
	var item := _tree.create_item(_tree.get_root())
	item.set_text(0, name)
	item.set_custom_color(0, Color(0.72, 0.80, 0.95))
	item.set_selectable(0, false)


func _add_row(key: String, value: String) -> void:
	var item := _tree.create_item(_tree.get_root())
	item.set_text(0, key)
	item.set_text(1, value)
	item.set_selectable(0, false)
	if key == "process_mode":
		item.set_tooltip_text(1, "Which operating mode the control volume declares. It decides which conservation equations the model may generate, and it is checked against the stream directions.")
