class_name InstanceForm
extends AcceptDialog
## Configure one model instance from that model's own declared contract.
##
## ## What drives this form
##
## The manifest the registry read, and nothing else. Required inputs are the
## ports the manifest marks `required`. Units come from the contract registry
## (`--describe-contract`), so a value may only be typed in a unit the quantity
## actually has. Quantities, provenance requirements, and the model's own
## sentence explaining each requirement are rendered as the model wrote them.
##
## ## What it will not do
##
## * It will not invent a value for a required input. A required field left
##   blank blocks the Add button and says so, quoting the model's reason.
## * It will not offer a unit the contract does not define for that quantity.
##   If the model published a port whose quantity this contract does not have,
##   the row is shown, marked, and left read-only -- because the port cannot be
##   connected anyway and the gap should stay visible.
## * It will not guess a control volume for an instance-parameterised model. The
##   user either starts from a blank declaration or imports one that the
##   project already ships, provenance and all.
##
## ## Where a value ends up
##
## A supplied value becomes a `literal_inputs` record on the graph document, in
## the shape `CompositionEngine._build_literals` reads. It is never folded into
## the model's parameters and never silently converted.

signal configured(model_id: String, model_version: String, label: String, role: String, parameters: Dictionary, literals: Dictionary)

## Where control-volume templates are read from. These are declarations the
## project already ships, with their own source references and assumptions.
const EXAMPLE_DIR := "res://composition/examples"

var _registry: ModelRegistry = null
var _model_id := ""
var _model_version := ""
var _display_name := ""

var _body: VBoxContainer = null
var _optional_section: VBoxContainer = null
var _optional_toggle: Button = null
var _optional_rows: Dictionary = {}
var _required_rows: Dictionary = {}
var _parameter_editor: StructuredEditor = null
var _template_picker: OptionButton = null
var _template_source: Label = null
var _label_field: LineEdit = null
var _role_field: LineEdit = null
var _problems: Label = null
var _problems_text := ""
var _rebuild_armed := false


func _init() -> void:
	title = "Add a model instance"
	ok_button_text = "Add to graph"
	# `AcceptDialog` has no `cancel_button_text` property and its cancel button
	# does not exist until the dialog is ready; its default caption is "Cancel",
	# which is what this wants.
	# Large enough for the 196-port Zielinski manifest without the window
	# growing past the screen, and small enough to stay on a laptop.
	min_size = Vector2i(760, 520)
	close_requested.connect(func() -> void: _reset())


func setup(registry: ModelRegistry) -> void:
	if _registry != null and _registry.manifest_loaded.is_connected(_on_registry_manifest_loaded):
		_registry.manifest_loaded.disconnect(_on_registry_manifest_loaded)
	_registry = registry
	if _registry != null and not _registry.manifest_loaded.is_connected(_on_registry_manifest_loaded):
		_registry.manifest_loaded.connect(_on_registry_manifest_loaded)


## Open the form for one registered model. Requests the manifest first if the
## registry has not read it, and rebuilds once it arrives.
func open_for(model_id: String) -> void:
	_model_id = model_id
	_rebuild_armed = true
	_model_version = _version_of(model_id)
	_display_name = _name_of(model_id)
	title = "Add %s" % reference_of(model_id)
	_build()
	if _registry != null and not _registry.has_manifest(model_id):
		_registry.request_manifest(model_id)
	popup_centered(Vector2i(880, 680))


func _on_registry_manifest_loaded(loaded_model_id: String, _manifest: Dictionary) -> void:
	if not _rebuild_armed or loaded_model_id != _model_id:
		return
	_build()


# --------------------------------------------------------------------------- #
# layout
# --------------------------------------------------------------------------- #


func _build() -> void:
	_clear()
	_model_version = _version_of(_model_id)
	_display_name = _name_of(_model_id)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)

	_body = VBoxContainer.new()
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_theme_constant_override("separation", 6)
	scroll.add_child(_body)

	_body.add_child(_identity_block())

	var manifest := _manifest()
	var dependence := _registry.port_dependence_for(_model_id) if _registry != null else ""

	if dependence == "instance":
		_body.add_child(_instance_declaration_block())
	else:
		_body.add_child(_input_block("Required inputs", _ports(true), _required_rows, true))
		_build_optional(_ports(false))

	_body.add_child(_parameter_block(manifest, dependence))

	_problems = Label.new()
	_problems.name = "Problems"
	_problems.add_theme_font_size_override("font_size", 10)
	_problems.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_problems.custom_minimum_size = Vector2(0, 34)
	_body.add_child(_problems)

	_revalidate()


func _clear() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_body = null
	_optional_section = null
	_optional_toggle = null
	_optional_rows = {}
	_required_rows = {}
	_parameter_editor = null
	_template_picker = null
	_template_source = null
	_label_field = null
	_role_field = null
	_problems = null


## What the model says about itself. Read-only, and rendered with the model's own
## words so a reader can tell a declaration from an editor's opinion.
func _identity_block() -> Control:
	var box := _section("This model")
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 1)
	box.add_child(grid)

	_row(grid, "name", _display_name)
	_row(grid, "identifier", reference_of(_model_id))
	var manifest := _manifest()
	var source_ref := str(manifest.get("source_ref", ""))
	if source_ref != "":
		_row(grid, "source", source_ref)
	var capabilities: Variant = manifest.get("capabilities", [])
	if capabilities is Array and not capabilities.is_empty():
		_row(grid, "declared capabilities", ", ".join(PackedStringArray(capabilities)))
	var unsupported: Variant = manifest.get("unsupported_capabilities", {})
	if unsupported is Dictionary and not unsupported.is_empty():
		_row(grid, "not supported", ", ".join(PackedStringArray(unsupported.keys())))

	var role_grid := GridContainer.new()
	role_grid.columns = 2
	role_grid.add_theme_constant_override("h_separation", 10)
	box.add_child(role_grid)
	_label_field = LineEdit.new()
	_label_field.text = _display_name
	_label_field.placeholder_text = "label shown on the canvas node"
	_label_field.text_changed.connect(func(_t: String) -> void: _revalidate())
	role_grid.add_child(_label("Label"))
	role_grid.add_child(_label_field)
	_role_field = LineEdit.new()
	_role_field.placeholder_text = "optional; shown under the label"
	role_grid.add_child(_label("Role"))
	role_grid.add_child(_role_field)
	return box


## Required inputs first, then the same port list again behind a toggle. Both
## read the same manifest array; neither has its own idea of what a model needs.
func _input_block(caption: String, ports: Array, store: Dictionary, required: bool) -> Control:
	var box := _section("%s (%d)" % [caption, ports.size()])
	if ports.is_empty():
		var none := _note("This model declares no required inputs. It will run on the "
			+ "terms it declares for itself; nothing is supplied for it here.")
		box.add_child(none)
		return box
	for port in ports:
		box.add_child(_input_row(port, store, required))
	return box


func _build_optional(ports: Array) -> void:
	var header := HBoxContainer.new()
	_optional_toggle = Button.new()
	_optional_toggle.toggle_mode = true
	_optional_toggle.button_pressed = false
	_optional_toggle.text = "▸  Optional inputs and declared values (%d)" % ports.size()
	_optional_toggle.add_theme_font_size_override("font_size", 12)
	_optional_toggle.pressed.connect(_on_optional_toggled)
	header.add_child(_optional_toggle)
	_body.add_child(header)

	_optional_section = VBoxContainer.new()
	_optional_section.add_theme_constant_override("separation", 6)
	_optional_section.visible = false
	_body.add_child(_optional_section)
	if ports.is_empty():
		_optional_section.add_child(_note("This model declares no other input ports."))
		return
	var inner := _section("")
	_optional_section.add_child(inner)
	for port in ports:
		inner.add_child(_input_row(port, _optional_rows, false))


func _on_optional_toggled() -> void:
	if _optional_section == null or _optional_toggle == null:
		return
	_optional_section.visible = _optional_toggle.button_pressed
	_optional_toggle.text = ("▾  Optional inputs and declared values" if _optional_section.visible
		else "▸  Optional inputs and declared values")


## One contract row. Quantity, unit and the model's own explanation come from
## the manifest; the unit list comes from the contract registry; the value comes
## from the user and only from the user.
func _input_row(port: Dictionary, store: Dictionary, required: bool) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)

	var quantity := str(port.get("quantity", ""))
	var canonical := _registry.canonical_quantity(quantity) if _registry != null \
		else ModelRegistry.UNKNOWN_QUANTITY
	var usable := canonical != ModelRegistry.UNKNOWN_QUANTITY
	var blocked := str(port.get("unavailable_reason", "")) != ""

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	var title := Label.new()
	title.text = str(port.get("label", port.get("port_id", "?")))
	title.add_theme_font_size_override("font_size", 12)
	head.add_child(title)
	if required:
		var badge := Label.new()
		badge.text = "required"
		badge.add_theme_font_size_override("font_size", 9)
		badge.modulate = Color(0.95, 0.72, 0.45)
		head.add_child(badge)
	var quantity_label := Label.new()
	quantity_label.text = quantity if usable else "%s (not in this contract)" % quantity
	quantity_label.add_theme_font_size_override("font_size", 9)
	quantity_label.modulate = Color(1, 1, 1, 0.55)
	quantity_label.tooltip_text = "quantity: %s" % quantity
	head.add_child(quantity_label)
	head.add_child(_hspacer())
	box.add_child(head)

	var port_label := Label.new()
	port_label.text = str(port.get("port_id", ""))
	port_label.add_theme_font_size_override("font_size", 9)
	port_label.modulate = Color(0.62, 0.70, 0.86)
	box.add_child(port_label)

	var description := str(port.get("description", ""))
	var requirement := str(port.get("provenance_requirement", ""))
	if description != "" or requirement != "":
		var detail := Label.new()
		var text := description
		if requirement != "":
			text += ("  " if text != "" else "") + "[%s provenance required]" % requirement
		detail.text = text
		detail.add_theme_font_size_override("font_size", 9)
		detail.modulate = Color(1, 1, 1, 0.5)
		detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		box.add_child(detail)

	if blocked:
		var refusal := Label.new()
		refusal.text = "Not connectable, and not editable here: %s" % str(port["unavailable_reason"])
		refusal.add_theme_font_size_override("font_size", 9)
		refusal.modulate = Color(0.95, 0.70, 0.58)
		refusal.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		box.add_child(refusal)
		store[str(port.get("port_id", ""))] = {"row": box, "port": port, "editable": false}
		return box

	var fields := HBoxContainer.new()
	fields.add_theme_constant_override("separation", 6)
	var value_field := LineEdit.new()
	value_field.custom_minimum_size = Vector2(240, 0)
	value_field.placeholder_text = "required -- no default exists" if required else "not supplied"
	# `LineEdit` gates input with `editable`; `disabled` is a BaseButton property
	# and does not exist here.
	value_field.editable = usable
	if not usable:
		value_field.tooltip_text = ("the contract defines no unit for quantity %s, "
			+ "so no value can be entered for this port" % quantity)
	value_field.text_changed.connect(func(_t: String) -> void: _revalidate())
	fields.add_child(value_field)

	var unit_picker := OptionButton.new()
	var declared := str(port.get("unit", ""))
	var units := _units_for(quantity, declared)
	for unit in units:
		unit_picker.add_item(unit)
	var selected := 0
	if declared != "":
		selected = max(units.find(declared), 0)
	unit_picker.select(selected)
	unit_picker.disabled = not usable or units.size() <= 1
	fields.add_child(unit_picker)
	fields.add_child(_hspacer())
	box.add_child(fields)

	store[str(port.get("port_id", ""))] = {
		"row": box,
		"port": port,
		"editable": true,
		"field": value_field,
		"unit": unit_picker,
		"required": required,
		"declared_unit": declared,
	}
	return box


## A model that publishes its ports per instance needs an instance declaration
## before it will publish a manifest at all. This states the model's own refusal,
## then offers a blank declaration or one the project already ships.
func _instance_declaration_block() -> Control:
	var box := _section("Instance declaration")
	box.add_child(_note(
		"This model declares its ports per instance, not per model. It refuses to "
		+ "publish a manifest until the graph instance carries a control volume, "
		+ "which is why it has no model-level port list here."))

	var templates := _templates()
	var picker_row := HBoxContainer.new()
	picker_row.add_theme_constant_override("separation", 8)
	picker_row.add_child(_label("Start from"))
	_template_picker = OptionButton.new()
	for template in templates:
		_template_picker.add_item(str(template["caption"]))
		_template_picker.set_item_metadata(_template_picker.item_count - 1, template)
	_template_picker.item_selected.connect(_on_template_selected)
	picker_row.add_child(_template_picker)
	picker_row.add_child(_hspacer())
	box.add_child(picker_row)

	_template_source = _note("")
	box.add_child(_template_source)
	box.add_child(_hspacer())

	_parameter_editor = StructuredEditor.new()
	_parameter_editor.name = "ParameterEditor"
	box.add_child(_parameter_editor)
	_on_template_selected(0)
	return box


## Model parameters for a fixed-port model: whatever declaration the user wants
## to add, starting from nothing.
func _parameter_block(manifest: Dictionary, dependence: String) -> Control:
	if dependence == "instance":
		return Control.new()
	var box := _section("Model parameters")
	box.add_child(_note(
		"Nothing is required here. The block below starts empty and is yours: add "
		+ "the execution settings the model documents and nothing else."))
	var capabilities: Variant = manifest.get("capabilities", [])
	if capabilities is Array and not capabilities.is_empty():
		box.add_child(_note("The model declares these capabilities: %s."
			% ", ".join(PackedStringArray(capabilities))))
	_parameter_editor = StructuredEditor.new()
	_parameter_editor.name = "ParameterEditor"
	box.add_child(_parameter_editor)
	return box


# --------------------------------------------------------------------------- #
# instance-parameterised templates
# --------------------------------------------------------------------------- #


## A blank declaration, plus every declaration of this model that the project
## already ships. Both are the project's own; neither is composed here.
func _templates() -> Array:
	var out: Array = [{
		"caption": "(blank declaration)",
		"parameters": _blank_declaration(),
		"note": "The field names are the ones the model itself names when it "
			+ "declines to publish a manifest. Every field starts empty.",
	}]
	var directory := DirAccess.open(EXAMPLE_DIR)
	if directory == null:
		return out
	var names := PackedStringArray()
	directory.list_dir_begin()
	var entry := directory.get_next()
	while entry != "":
		if entry.ends_with(".json"):
			names.append(entry)
		entry = directory.get_next()
	directory.list_dir_end()
	names.sort()
	for name in names:
		var found := _template_from_example(EXAMPLE_DIR.path_join(name))
		for template in found:
			out.append(template)
	return out


## Pull one instance's `parameters` out of a shipped example graph. The source
## reference and notes travel with it, so an imported declaration is never
## anonymous.
func _template_from_example(path: String) -> Array:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return []
	var text := file.get_as_text()
	file.close()
	var json := JSON.new()
	if json.parse(text) != OK:
		return []
	var data: Variant = json.get_data()
	if not (data is Dictionary):
		return []
	var out: Array = []
	for instance in (data as Dictionary).get("instances", []):
		if not (instance is Dictionary):
			continue
		if str(instance.get("model_id", "")) != _model_id:
			continue
		var label := str(instance.get("label", ""))
		out.append({
			"caption": "%s -- %s" % [path.get_file(), label],
			"parameters": _deep_copy(instance.get("parameters", {})),
			"note": "Imported from %s, instance %s (%s). Its own source_ref, "
				% [path.get_file(), str(instance.get("instance_id", "?")), label]
				+ "assumptions and reasons travel with it unchanged.",
		})
	return out


func _on_template_selected(index: int) -> void:
	if _template_picker == null or _parameter_editor == null:
		return
	if index < 0 or index >= _template_picker.item_count:
		return
	var template: Dictionary = _template_picker.get_item_metadata(index)
	_parameter_editor.load_value(template.get("parameters", {}))
	if _template_source != null:
		_template_source.text = str(template.get("note", ""))


## The empty control volume the model's own refusal message describes. Field
## names come from that message; every value is empty.
func _blank_declaration() -> Dictionary:
	var blank_amount := {
		"quantity_id": "", "value": "", "unit": "", "kind": "",
		"provenance": "reported", "source_ref": "",
	}
	return {
		"system_id": "",
		"label": "",
		"process_mode": "batch",
		"basis": "mass",
		"source_ref": "",
		"components": [],
		"streams": [],
	}


# --------------------------------------------------------------------------- #
# validation and confirmation
# --------------------------------------------------------------------------- #


## Recompute what is blocking and what is merely worth saying, then enable or
## disable the Add button. Called on every edit.
func _revalidate() -> void:
	var problems := PackedStringArray()
	var warnings := PackedStringArray()

	for port_id in _required_rows.keys():
		var record: Dictionary = _required_rows[port_id]
		if not bool(record.get("editable", false)):
			continue
		if _text_of(record).strip_edges() == "":
			var port: Dictionary = record.get("port", {})
			var reason := str(port.get("description", ""))
			problems.append("%s is required and has no value. %s"
				% [str(port.get("label", port_id)),
				   reason if reason != "" else "The model publishes no default for it."])

	if _parameter_editor != null and not _parameter_editor.is_valid():
		warnings.append("Some parameter fields will not parse: %s. They are kept "
			% ", ".join(_parameter_editor.error_paths())
			+ "as text; fix them before running.")

	if _registry != null and _registry.port_dependence_for(_model_id) == "instance":
		if _parameter_editor != null and _instance_declaration_incomplete():
			problems.append("This model declares no ports until its instance carries a "
				+ "control volume. Declare the streams and components it needs, or "
				+ "import a declaration.")

	if _problems == null:
		return
	var text := ""
	if not problems.is_empty():
		text += "Blocking:\n  ·  " + "\n  ·  ".join(problems) + "\n"
	if not warnings.is_empty():
		text += "Worth knowing:\n  ·  " + "\n  ·  ".join(warnings)
	if text == "":
		text = "Ready to add. %s" % reference_of(_model_id)
		text += "   Nothing will be supplied that you did not type."
	_problems_text = text
	_problems.text = text
	_problems.modulate = Color(0.95, 0.70, 0.58) if not problems.is_empty() \
		else Color(0.66, 0.86, 0.68)
	if get_ok_button() != null:
		get_ok_button().disabled = not problems.is_empty()


## Whether an instance-parameterised model is still missing the thing it refuses
## to publish a manifest without: a control volume with at least one stream and
## at least one component.
##
## That is the whole of it. Whether the balance is *solvable* is the engine's
## question, answered by the engine, with its own diagnostics; the form does not
## second-guess it here and refuse a declaration the engine would have accepted.
func _instance_declaration_incomplete() -> bool:
	if _parameter_editor == null:
		return true
	var value: Variant = _parameter_editor.get_value()
	if not (value is Dictionary):
		return true
	var system: Variant = (value as Dictionary).get("system")
	if not (system is Dictionary):
		return true
	var streams: Variant = (system as Dictionary).get("streams")
	if not (streams is Array) or (streams as Array).is_empty():
		return true
	var components: Variant = (system as Dictionary).get("components")
	return not (components is Array) or (components as Array).is_empty()


## What the OK button does. Public so an acceptance test presses the same path
## the user does rather than a copy of it.
func press_ok() -> void:
	_revalidate()
	if get_ok_button() != null and get_ok_button().disabled:
		return
	_emit_configured()


func _emit_configured() -> void:
	var literals := {}
	for store in [_required_rows, _optional_rows]:
		for port_id in store.keys():
			var record: Dictionary = store[port_id]
			if not bool(record.get("editable", false)):
				continue
			var text := _text_of(record)
			if text.strip_edges() == "":
				continue
			literals[port_id] = _literal_for(port_id, record, text)
	var parameters: Variant = {}
	if _parameter_editor != null:
		parameters = _parameter_editor.get_value()
	if not (parameters is Dictionary):
		parameters = {}
	emit_signal("configured", _model_id, _version_of(_model_id),
		_label_field.text if _label_field != null and _label_field.text.strip_edges() != "" else _display_name,
		_role_field.text if _role_field != null else "",
		parameters as Dictionary, literals)
	hide()


## One literal input record, in the shape `CompositionEngine._build_literals`
## reads. `quantity` and `unit` are the model's, the value is the user's, and the
## record says so rather than claiming a provenance it does not have.
func _literal_for(port_id: String, record: Dictionary, text: String) -> Dictionary:
	var port: Dictionary = record.get("port", {})
	var picker: OptionButton = record.get("unit", null)
	var unit := str(port.get("unit", ""))
	if picker != null and picker.selected >= 0:
		unit = picker.get_item_text(picker.selected)
	var value: Variant = text
	if text.is_valid_float():
		value = float(text)
	return {
		"state": "number",
		"quantity": str(port.get("quantity", "")),
		"value": value,
		"unit": unit,
		"source_ref": "declared on the graph instance in the Godot editor",
		"method": "operator input on the %s instance" % _model_id,
		"reason": str(port.get("description", "supplied by the operator")),
	}


## The form is open for one model. Public so a caller -- or an acceptance test
## -- can tell what the user is looking at.
func configuring() -> String:
	return _model_id


## The input ports the manifest marks `required`, in the model's own order.
func required_port_ids() -> PackedStringArray:
	var out := PackedStringArray()
	for port_id in _required_rows.keys():
		out.append(str(port_id))
	return out


## Set one input's value through the same widget the user types into. Returns
## false when the port is unknown, not editable, or hidden behind the collapsed
## optional section, so a caller cannot supply a value where the user could not.
func set_input_value(port_id: String, text: String) -> bool:
	var record: Dictionary = _required_rows.get(port_id, {})
	if not record.is_empty():
		return _write_input(record, text)
	if _optional_section == null or not _optional_section.visible:
		expand_optional_inputs()
	record = _optional_rows.get(port_id, {})
	if record.is_empty():
		return false
	return _write_input(record, text)


func _write_input(record: Dictionary, text: String) -> bool:
	if not bool(record.get("editable", false)):
		return false
	var field: LineEdit = record.get("field", null)
	if field == null:
		return false
	field.text = text
	field.text_changed.emit(text)
	_revalidate()
	return true


## Reveal the optional-input section, exactly as the toggle does.
func expand_optional_inputs() -> void:
	if _optional_toggle == null or _optional_section == null:
		return
	_optional_toggle.set_pressed_no_signal(true)
	_optional_section.visible = true
	_optional_toggle.text = "▾  Optional inputs and declared values"


## What is currently in one input, or "" if it has none.
func input_value(port_id: String) -> String:
	for store in [_required_rows, _optional_rows]:
		var record: Dictionary = store.get(port_id, {})
		if not record.is_empty():
			return _text_of(record)
	return ""


## Every input row, required first, as
## `{port_id, label, quantity, unit, required, editable, blocked}`.
func input_rows() -> Array:
	var out: Array = []
	for required_pass in [true, false]:
		for port_id in ([_required_rows, _optional_rows][0 if required_pass else 1]).keys():
			var record: Dictionary = ([_required_rows, _optional_rows][0 if required_pass else 1])[port_id]
			var port: Dictionary = record.get("port", {})
			out.append({
				"port_id": str(port_id),
				"label": str(port.get("label", "")),
				"quantity": str(port.get("quantity", "")),
				"unit": str(record.get("declared_unit", port.get("unit", ""))),
				"required": bool(record.get("required", required_pass)),
				"editable": bool(record.get("editable", false)),
				"blocked": str(port.get("unavailable_reason", "")) != "",
			})
	return out


## What currently blocks the Add button. Empty means the user may add.
func blocking_problems() -> PackedStringArray:
	var out := PackedStringArray()
	for text in _problems_text.split("\n"):
		if text.begins_with("  ·  "):
			out.append(text.substr(4))
	return out


## The captions of the starting points for an instance-parameterised model.
func template_captions() -> PackedStringArray:
	if _template_picker == null:
		return PackedStringArray()
	var out := PackedStringArray()
	for index in _template_picker.item_count:
		out.append(_template_picker.get_item_text(index))
	return out


## Choose one of those starting points.
func select_template(index: int) -> void:
	if _template_picker == null:
		return
	_template_picker.select(clampi(index, 0, maxi(_template_picker.item_count - 1, 0)))
	_on_template_selected(_template_picker.selected)


## The parameters the user has assembled, as the form would send them.
func declared_parameters() -> Variant:
	if _parameter_editor == null:
		return {}
	return _parameter_editor.get_value()


## The parameter editor itself, so a caller can set one path in the block rather
## than rebuilding the whole value. Refuses a path the editor does not own.
func parameter_editor() -> StructuredEditor:
	return _parameter_editor


## Set one value inside the model-parameters block. The same call the "add
## field" button and the key field make.
func set_parameter(path: Array, value: Variant) -> bool:
	if _parameter_editor == null:
		return false
	return _parameter_editor.set_at(path, value)


func _text_of(record: Dictionary) -> String:
	var field: LineEdit = record.get("field", null)
	return "" if field == null else field.text


func _reset() -> void:
	_rebuild_armed = false
	_clear()


# --------------------------------------------------------------------------- #
# registry reads
# --------------------------------------------------------------------------- #


func _manifest() -> Dictionary:
	if _registry == null:
		return {}
	return _registry.manifest_for(_model_id)


## The manifest's input ports, required ones first and then in the order the
## model published them. The model owns that order; it is not re-sorted here.
func _ports(required: bool) -> Array:
	var manifest := _manifest()
	var declared: Variant = manifest.get("ports", [])
	if not (declared is Array):
		return []
	var out: Array = []
	for port in declared as Array:
		if not (port is Dictionary):
			continue
		if str((port as Dictionary).get("direction", "")) != "input":
			continue
		if bool((port as Dictionary).get("required", false)) != required:
			continue
		out.append(port)
	if required:
		return out
	# A manifest with no required inputs still has plenty of optional ones; cap
	# nothing, but keep required-first ordering stable for the required pass.
	return out


## Units the contract actually defines for this quantity, with the model's own
## declared unit first if it is among them. A quantity the contract does not
## define yields no units, which is what makes the row read-only.
func _units_for(quantity: String, declared: String) -> PackedStringArray:
	var out := PackedStringArray()
	if _registry == null:
		if declared != "":
			out.append(declared)
		return out
	for unit in _registry.units_for(quantity):
		out.append(str(unit))
	if out.is_empty() and declared != "":
		out.append(declared)
	return out


func _name_of(model_id: String) -> String:
	if _registry != null:
		var title := str(_registry.manifest_for(model_id).get("title", ""))
		if title.strip_edges() != "":
			return title
	return model_id


func _version_of(model_id: String) -> String:
	if _registry == null:
		return ""
	var reference := _registry.reference_for(model_id)
	return reference.get_slice("@", 1) if reference.contains("@") else ""


func reference_of(model_id: String) -> String:
	if _registry == null:
		return model_id
	var reference := _registry.reference_for(model_id)
	return reference if reference != "" else model_id


# --------------------------------------------------------------------------- #
# small builders
# --------------------------------------------------------------------------- #


func _section(caption: String) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	if caption != "":
		var heading := Label.new()
		heading.text = caption
		heading.add_theme_font_size_override("font_size", 12)
		heading.modulate = Color(0.72, 0.80, 0.95)
		box.add_child(heading)
	return box


func _row(grid: GridContainer, key: String, value: String) -> void:
	grid.add_child(_label(key))
	var shown := Label.new()
	shown.text = value
	shown.add_theme_font_size_override("font_size", 10)
	shown.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	shown.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(shown)


func _label(text: String) -> Control:
	var label := Label.new()
	label.text = text
	label.custom_minimum_size = Vector2(150, 0)
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = Color(1, 1, 1, 0.65)
	return label


func _note(text: String) -> Control:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 9)
	label.modulate = Color(1, 1, 1, 0.5)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return label


func _hspacer() -> Control:
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return spacer


static func _deep_copy(value: Variant) -> Variant:
	if value is Dictionary:
		var out: Dictionary = {}
		for key in (value as Dictionary).keys():
			out[key] = _deep_copy((value as Dictionary)[key])
		return out
	if value is Array:
		var out: Array = []
		for item in value as Array:
			out.append(_deep_copy(item))
		return out
	return value