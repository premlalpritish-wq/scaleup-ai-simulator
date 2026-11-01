class_name ModelInspector
extends PanelContainer
## The model inspector: identity, declared parameters, declared ports and their
## provenance for the selected node.
##
## Everything shown here is read, never computed. Two sources are used and they
## are kept apart on purpose:
##
##   * the **graph instance** carries what *this instance* was configured with --
##     its own control volume, execution mode and declared assumptions;
##   * the **model manifest**, fetched by `ModelRegistry`, carries what the
##     *model* declares about itself -- its identity, capabilities, parameter
##     sections and ports.
##
## The two are labelled as such. A node whose parameters are not recognised is
## rendered generically from whatever the manifest published, rather than being
## hidden behind a block name this file happens to know.

var _instance: Dictionary = {}
var _tree: Tree = null
var _registry: ModelRegistry = null
var _ports: Array[Dictionary] = []
var _ports_source := "none"
## How deep the generic manifest renderer will walk. Beyond this a value is
## summarised by its size rather than expanded.
const MAX_DEPTH := 4
## Longest scalar rendered in full before it is elided.
const MAX_VALUE_CHARS := 220


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


func show_instance(inst: Dictionary, ports: Array[Dictionary], ports_source: String = "none") -> void:
	_instance = inst
	_ports = ports
	_ports_source = ports_source
	_populate(ports)


func clear() -> void:
	_instance = {}
	_ports = []
	_ports_source = "none"
	if _tree == null:
		return
	_tree.clear()


func _populate(ports: Array[Dictionary]) -> void:
	_tree.clear()
	if _instance.is_empty():
		var empty := _tree.create_item()
		empty.set_text(0, "No node selected")
		return

	var root := _tree.create_item()
	root.set_text(0, str(_instance.get("label", _instance.get("instance_id", "node"))))
	root.set_text(1, str(_instance.get("role", "")))

	_add_section("identity")
	_add_row("model_id", str(_instance.get("model_id", "")))
	_add_row("model_version", str(_instance.get("model_version", "")))
	_add_row("instance_id", str(_instance.get("instance_id", "")))

	var model_id := str(_instance.get("model_id", ""))
	var reference := _registry.reference_for(model_id) if _registry != null else ""
	if reference != "":
		_add_row("resolved_reference", reference)
	var dependence := _registry.port_dependence_for(model_id) if _registry != null else ""
	if dependence == "instance":
		_add_row("port_dependence", "declared per instance, not per model")
	elif dependence == "fixed":
		_add_row("port_dependence", "fixed at model level")

	_populate_manifest(model_id)
	_populate_instance_parameters()
	_populate_ports(ports)


# --------------------------------------------------------------------------- #
# what the model declares about itself
# --------------------------------------------------------------------------- #

func _populate_manifest(model_id: String) -> void:
	if _registry == null or _registry.manifest_for(model_id).is_empty():
		return
	var manifest := _registry.manifest_for(model_id)

	if str(manifest.get("source_ref", "")) != "":
		_add_row("source_ref", str(manifest["source_ref"]))
	if str(manifest.get("title", "")) != "":
		_add_row("title", str(manifest["title"]))

	var capabilities: Array = manifest.get("capabilities", [])
	if not capabilities.is_empty():
		_add_row("capabilities", ", ".join(PackedStringArray(capabilities)))

	var unsupported: Dictionary = manifest.get("unsupported_capabilities", {})
	if not unsupported.is_empty():
		_add_row("not_supported", ", ".join(PackedStringArray(unsupported.keys())))

	var reaction_terms: Array = manifest.get("reaction_terms", [])
	_add_row("reaction_terms",
		", ".join(PackedStringArray(reaction_terms)) if not reaction_terms.is_empty()
		else "(none declared)")
	if bool(manifest.get("non_reacting_only", false)):
		_add_row("non_reacting_only", "true -- a control volume may not be drawn "
			+ "around a boundary this model does not represent as non-reacting")

	var sections: Dictionary = manifest.get("parameter_sections", {})
	if sections.is_empty():
		return
	# Sections the instance block below already renders from the graph document
	# are not repeated here; the same facts in two places are two chances to
	# read them differently.
	var rendered_elsewhere := ["assumptions", "declared missing models"]
	for name in sections.keys():
		if str(name) in rendered_elsewhere:
			continue
		_add_section("declared by the model -- %s" % str(name))
		_render_value(sections[name], MAX_DEPTH, 1)


# --------------------------------------------------------------------------- #
# what this graph instance was configured with
# --------------------------------------------------------------------------- #

func _populate_instance_parameters() -> void:
	var params: Dictionary = _instance.get("parameters", {})

	if params.has("system"):
		var system: Dictionary = params["system"]
		_add_section("control volume (this instance)")
		_add_row("system_id", str(system.get("system_id", "")))
		_add_row("process_mode", str(system.get("process_mode", "")))
		_add_row("basis", str(system.get("basis", "")))
		if system.has("components"):
			var comps := []
			for c in system["components"]:
				comps.append("%s (%s)" % [str(c.get("component_id")), str(c.get("label", ""))])
			_add_row("components", ", ".join(comps))

	if params.has("execution"):
		_add_section("execution (this instance)")
		var execution: Dictionary = params["execution"]
		_add_row("mode", str(execution.get("mode", "")))

	if params.has("assumptions"):
		_add_section("assumptions (this instance)")
		for a in params["assumptions"]:
			_add_assumption(a)

	if params.has("missing_information"):
		_add_section("declared missing information (this instance)")
		for m in params["missing_information"]:
			var child := _tree.create_item(_tree.get_root())
			child.set_text(0, str(m.get("parameter_id", "")))
			child.set_text(1, str(m.get("reason", "")))

	# Any block this file does not recognise is still shown, generically, rather
	# than dropped. An unrecognised block is a gap in this inspector, not a
	# reason to hide what the graph actually carries.
	var known := ["ports", "system", "execution", "assumptions", "missing_information"]
	var extra: Array[String] = []
	for key in params.keys():
		if not str(key) in known:
			extra.append(str(key))
	if extra.is_empty():
		return
	extra.sort()
	for key in extra:
		_add_section("other parameters -- %s" % key)
		_render_value(params[key], MAX_DEPTH, 1)


# --------------------------------------------------------------------------- #
# ports
# --------------------------------------------------------------------------- #

func _populate_ports(ports: Array[Dictionary]) -> void:
	_add_section("ports (%d)" % ports.size())
	match _ports_source:
		"manifest":
			_add_row("port source", "declared by the model in its manifest")
		"instance":
			_add_row("port source", "configured on this graph instance")
		"instance_parameterised":
			_add_row("port source", "declared per instance; read from this instance")
		_:
			_add_row("port source", "none -- this model has not published a port set")

	if ports.is_empty():
		var none := _tree.create_item(_tree.get_root())
		none.set_text(0, "(no ports)")
		none.set_text(1, "")
		none.set_selectable(0, false)
		return

	for p in ports:
		var child := _tree.create_item(_tree.get_root())
		var quantity := str(p.get("quantity", ""))
		child.set_text(0, "%s  %s" % [str(p.get("port_id", "")), str(p.get("unit", ""))])
		child.set_text(1, "%s (%s)" % [quantity, str(p.get("direction", ""))])

		var tooltip := _port_tooltip(p)
		if tooltip != "":
			child.set_tooltip_text(1, tooltip)

		var provenance := _port_provenance(p)
		if str(p.get("unavailable_reason", "")) != "":
			child.set_custom_color(1, Color(0.95, 0.62, 0.45))
		elif provenance == "unknown":
			child.set_custom_color(1, Color(0.95, 0.72, 0.45))
		elif provenance == "reported" or provenance == "digitized":
			child.set_custom_color(1, Color(0.62, 0.88, 0.62))
		elif provenance == "derived" or provenance == "solved":
			child.set_custom_color(1, Color(0.62, 0.78, 0.95))


## A port published by a manifest carries its provenance inside `metadata`; a
## port configured on the graph document may carry it at the top level. Both are
## read; neither is inferred from the port id.
func _port_provenance(p: Dictionary) -> String:
	if p.has("provenance"):
		return str(p["provenance"])
	var metadata: Variant = p.get("metadata", {})
	if metadata is Dictionary and (metadata as Dictionary).has("provenance"):
		return str((metadata as Dictionary)["provenance"])
	return ""


func _port_tooltip(p: Dictionary) -> String:
	var lines := PackedStringArray()
	for key in ["label", "temporal_basis", "required", "solvable",
			"provenance_requirement", "attribution_required", "component"]:
		if p.has(key) and str(p[key]) != "" and str(p[key]) != "false":
			lines.append("%s: %s" % [key, str(p[key])])
	if str(p.get("unavailable_reason", "")) != "":
		lines.append("not connectable: %s" % str(p["unavailable_reason"]))
	if not lines.is_empty():
		lines.append("")
	return "\n".join(lines)


# --------------------------------------------------------------------------- #
# generic renderer
#
# Used for manifest parameter sections and for graph parameter blocks this file
# does not recognise. It renders structure; it never interprets it, and it never
# decides that two differently-named entries mean the same thing.
# --------------------------------------------------------------------------- #

func _render_value(value: Variant, depth: int, level: int) -> void:
	if depth <= 0:
		_add_row("...", "(nested further than %d levels; not expanded)" % MAX_DEPTH)
		return

	if value is Dictionary:
		var d: Dictionary = value
		if d.is_empty():
			_add_row("(empty)", "")
			return
		for key in d.keys():
			_render_entry(str(key), d[key], depth, level)
		return

	if value is Array:
		var a: Array = value
		if a.is_empty():
			_add_row("(empty)", "")
			return
		for i in range(a.size()):
			_render_entry("[%d]" % i, a[i], depth, level)
		return

	_add_row("value", _scalar(value))


func _render_entry(key: String, value: Variant, depth: int, level: int) -> void:
	if value is Dictionary or value is Array:
		var item := _tree.create_item(_tree.get_root())
		item.set_text(0, key)
		item.set_text(1, "%s  %s" % [type_string(typeof(value)), _size_of(value)])
		item.set_custom_color(0, Color(0.72, 0.80, 0.95))
		item.set_selectable(0, false)
		_render_value(value, depth - 1, level + 1)
		return
	_add_row(key, _scalar(value))


func _scalar(value: Variant) -> String:
	var text := str(value)
	if text.length() <= MAX_VALUE_CHARS:
		return text
	return "%s ... (%d characters)" % [text.substr(0, MAX_VALUE_CHARS), text.length()]


func _size_of(value: Variant) -> String:
	if value is Dictionary:
		return "%d entries" % (value as Dictionary).size()
	if value is Array:
		return "%d entries" % (value as Array).size()
	return ""


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


func _add_assumption(a: Dictionary) -> void:
	var child := _tree.create_item(_tree.get_root())
	child.set_text(0, str(a.get("assumption_id", "")))
	child.set_text(1, _scalar(a.get("statement", "")))
	if str(a.get("rationale", "")) != "":
		child.set_tooltip_text(1, str(a["rationale"]))