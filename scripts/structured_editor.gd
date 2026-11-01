class_name StructuredEditor
extends VBoxContainer
## A generic, recursive editor for a JSON-shaped value.
##
## The graph document and the model manifests carry nested dictionaries and
## arrays. This renders one as an editable tree and hands back the edited value.
## It is deliberately shape-agnostic: it knows about dictionaries, arrays and
## leaves, and nothing about material balances, fed-batch runs or any other
## particular model.
##
## Three rules it holds to:
##
##   1. **Nothing is invented.** A leaf starts empty unless the value it edits
##      already carried something. "Add element" clones the *shape* of a
##      sibling and blanks every leaf, so a new stream has the right fields and
##      no numbers in it.
##   2. **A leaf that will not parse is an error, not a coercion.** Clearing a
##      numeric field and typing letters does not become 0.0; `is_valid()` goes
##      false and `edit_error` names the path that is wrong. A *blank* numeric
##      field is not a parse error -- it is "not supplied", and whoever embeds
##      this decides whether that blocks them.
##   3. **The working copy is the value.** `get_value()` returns the live
##      structure, so nothing has to be re-assembled from the widget tree.
##
## It is a value editor. It performs no validation a model would perform and
## decides no compatibility; the composition engine still owns both.

signal changed
signal edit_error(message: String)

## How deep to descend before summarising. Deep enough for every declaration the
## shipped models use, shallow enough that a mistake cannot lock the editor.
const MAX_DEPTH := 7

var _value: Variant = {}
## path-key -> whether that leaf is currently text its own type cannot accept.
var _errors: Dictionary = {}


func _init() -> void:
	add_theme_constant_override("separation", 2)


## Replace the edited value. `value` is deep-copied, so the caller's structure is
## never mutated behind its back.
func load_value(value: Variant) -> void:
	_value = _deep_copy(value)
	_errors.clear()
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_render(_value, self, [], 0)


## The edited value. Deep-copied on the way out so a caller cannot reach back
## into the editor's working state.
func get_value() -> Variant:
	return _deep_copy(_value)


## False while any leaf holds text its own declared type cannot accept.
func is_valid() -> bool:
	return _errors.is_empty()


## The paths that are currently wrong, as `a/b/c` strings.
func error_paths() -> PackedStringArray:
	var out := PackedStringArray()
	for key in _errors.keys():
		out.append(str(key))
	return out


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


func _render(value: Variant, parent: Control, path: Array, depth: int) -> void:
	if value is Dictionary:
		_render_mapping(value as Dictionary, parent, path, depth)
	elif value is Array:
		_render_sequence(value as Array, parent, path, depth)
	else:
		parent.add_child(_leaf_row(value, path))


func _render_mapping(value: Dictionary, parent: Control, path: Array, depth: int) -> void:
	if depth >= MAX_DEPTH:
		parent.add_child(_summary("%d entries (not expanded)" % value.size()))
		return
	parent.add_child(_summary("(empty)" if value.is_empty() else "%d entries" % value.size()))
	for key in value.keys():
		var child_path: Array = path.duplicate()
		child_path.append(key)
		var block := _block(child_path, parent, true)
		_render(value[key], block.get_child(1), child_path, depth + 1)
	var add := Button.new()
	add.text = "add field"
	add.add_theme_font_size_override("font_size", 10)
	add.pressed.connect(_on_add_field.bind(path.duplicate()))
	parent.add_child(add)


func _render_sequence(value: Array, parent: Control, path: Array, depth: int) -> void:
	if depth >= MAX_DEPTH:
		parent.add_child(_summary("%d entries (not expanded)" % value.size()))
		return
	parent.add_child(_summary("%d entr%s" % [value.size(), "y" if value.size() == 1 else "ies"]))
	var index := 0
	while index < value.size():
		var child_path: Array = path.duplicate()
		child_path.append(index)
		var block := _block(child_path, parent, false)
		_render(value[index], block.get_child(1), child_path, depth + 1)
		index += 1
	var add_button := Button.new()
	add_button.text = "add element"
	add_button.add_theme_font_size_override("font_size", 10)
	add_button.pressed.connect(_on_add_element.bind(path.duplicate()))
	parent.add_child(add_button)


## A header row naming this entry, with its remove button, above a body the
## value is rendered into. Returns the block; child 1 is the body.
func _block(path: Array, parent: Control, renameable: bool) -> Control:
	var block := VBoxContainer.new()
	block.add_theme_constant_override("separation", 1)

	var head := HBoxContainer.new()
	if renameable:
		var key_field := LineEdit.new()
		key_field.text = str(path[path.size() - 1])
		key_field.custom_minimum_size = Vector2(220, 0)
		key_field.add_theme_font_size_override("font_size", 11)
		key_field.tooltip_text = "The key this entry is stored under."
		key_field.text_changed.connect(func(text: String) -> void:
			_rename_key(path.duplicate(), text))
		head.add_child(key_field)
	else:
		var name_label := Label.new()
		name_label.text = "[%d]" % int(path[path.size() - 1])
		name_label.add_theme_font_size_override("font_size", 11)
		name_label.modulate = Color(0.72, 0.80, 0.95)
		head.add_child(name_label)
	head.add_child(_spacer())
	var remove := Button.new()
	remove.text = "remove"
	remove.tooltip_text = "Remove %s from this declaration." % str(path[path.size() - 1])
	remove.add_theme_font_size_override("font_size", 10)
	remove.pressed.connect(_on_remove_entry.bind(path.duplicate()))
	head.add_child(remove)
	block.add_child(head)

	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 2)
	block.add_child(body)
	parent.add_child(block)
	return block


func _leaf_row(value: Variant, path: Array) -> Control:
	var born := typeof(value)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	var name_label := Label.new()
	name_label.text = str(path[path.size() - 1]) if path.size() > 0 else "value"
	name_label.custom_minimum_size = Vector2(210, 0)
	name_label.add_theme_font_size_override("font_size", 11)
	row.add_child(name_label)

	if born == TYPE_BOOL:
		var box := CheckBox.new()
		box.button_pressed = bool(value)
		box.toggled.connect(func(on: bool) -> void: _write(path, on))
		row.add_child(box)
	else:
		var field := LineEdit.new()
		field.custom_minimum_size = Vector2(220, 0)
		field.add_theme_font_size_override("font_size", 11)
		field.text = "" if value == null else str(value)
		field.placeholder_text = "not supplied"
		field.text_changed.connect(func(text: String) -> void: _on_leaf_text(path, text, born))
		row.add_child(field)
	row.add_child(_spacer())
	return row


func _summary(text: String) -> Control:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 9)
	label.modulate = Color(1, 1, 1, 0.45)
	return label


func _spacer() -> Control:
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return spacer


# --------------------------------------------------------------------------- #
# editing
# --------------------------------------------------------------------------- #


func _on_leaf_text(path: Array, text: String, born: int) -> void:
	_write(path, _parse(text, born))
	var key := _path_key(path)
	# A blank field is "not supplied", which is the embedder's business. Text
	# that is neither blank nor a number, in a field born numeric, is a parse
	# error and is reported rather than coerced.
	if _wants_number(born) and text != "" and not text.is_valid_float():
		_errors[key] = true
	elif _errors.has(key):
		_errors.erase(key)
	if not _errors.is_empty():
		emit_signal("edit_error", "%d field(s) will not parse: %s"
			% [_errors.size(), ", ".join(error_paths())])
	emit_signal("changed")


static func _wants_number(born: int) -> bool:
	return born == TYPE_FLOAT or born == TYPE_INT


## Parse a leaf's text into the type it was born as. Text that will not parse is
## kept verbatim and marked invalid -- never turned into a number.
func _parse(text: String, born: int) -> Variant:
	if text == "":
		return ""
	if _wants_number(born) and text.is_valid_float():
		return float(text)
	if born == TYPE_NIL and text.is_valid_float():
		return float(text)
	return text


func _write(path: Array, value: Variant) -> void:
	if path.is_empty():
		return
	var cursor: Variant = _value
	var i := 0
	while i < path.size() - 1:
		if cursor is Dictionary:
			if not cursor.has(path[i]):
				return
			cursor = cursor[path[i]]
		elif cursor is Array:
			var index := int(path[i])
			if index < 0 or index >= (cursor as Array).size():
				return
			cursor = (cursor as Array)[index]
		else:
			return
		i += 1
	if cursor is Dictionary:
		(cursor as Dictionary)[path[i]] = value
	elif cursor is Array:
		var index := int(path[i])
		if index >= 0 and index < (cursor as Array).size():
			(cursor as Array)[index] = value
	emit_signal("changed")


func _on_remove_entry(path: Array) -> void:
	if path.is_empty():
		return
	var parent_path: Array = path.slice(0, path.size() - 1)
	var last: Variant = path[path.size() - 1]
	var cursor: Variant = _root_at(parent_path)
	if cursor is Dictionary:
		(cursor as Dictionary).erase(last)
	elif cursor is Array:
		var index := int(last)
		if index >= 0 and index < (cursor as Array).size():
			(cursor as Array).remove_at(index)
	load_value(_value)
	emit_signal("changed")


func _on_add_element(path: Array) -> void:
	var cursor: Variant = _root_at(path)
	if not (cursor is Array):
		return
	var array := cursor as Array
	var template: Variant = {} if array.is_empty() else _blanked(_deep_copy(array[array.size() - 1]))
	array.append(template)
	load_value(_value)
	emit_signal("changed")


## A new key, with an empty value. The user names it afterwards; this file never
## picks the name.
func _on_add_field(path: Array) -> void:
	var cursor: Variant = _root_at(path)
	if not (cursor is Dictionary):
		return
	var mapping := cursor as Dictionary
	var key := "field"
	var suffix := 1
	while mapping.has(key):
		suffix += 1
		key = "field%d" % suffix
	mapping[key] = ""
	load_value(_value)
	emit_signal("changed")


## Move an entry to a new key, in place and with its value intact.
func _rename_key(path: Array, new_key: String) -> void:
	if path.is_empty() or new_key == "":
		return
	var old_key: Variant = path[path.size() - 1]
	if str(old_key) == new_key:
		return
	var parent_path: Array = path.slice(0, path.size() - 1)
	var cursor: Variant = _root_at(parent_path)
	if not (cursor is Dictionary):
		return
	var mapping := cursor as Dictionary
	if not mapping.has(old_key) or mapping.has(new_key):
		return
	mapping[new_key] = mapping[old_key]
	mapping.erase(old_key)
	emit_signal("changed")


## Set one value by path, creating the dictionaries and arrays the path needs.
##
## This is the programmatic equivalent of typing a key name and a value: it
## invents no value and refuses to overwrite a sibling that already exists.
func set_at(path: Array, value: Variant, create_missing := true) -> bool:
	if path.is_empty():
		return false
	var parent: Variant = _value
	for i in path.size():
		var step: Variant = path[i]
		var last := i == path.size() - 1
		if parent is Dictionary:
			var mapping := parent as Dictionary
			if last:
				if not mapping.has(step) and not create_missing:
					return false
				if mapping.has(step) and mapping[step] is Dictionary and value is Dictionary:
					return false
				mapping[step] = value
				load_value(_value)
				return true
			if not mapping.has(step):
				if not create_missing:
					return false
				mapping[step] = {}
			parent = mapping[step]
		elif parent is Array:
			var array := parent as Array
			if last:
				var index := int(step)
				if index < 0 or index >= array.size():
					return false
				array[index] = value
				load_value(_value)
				return true
			var index2 := int(step)
			if index2 < 0 or index2 >= array.size():
				return false
			parent = array[index2]
		else:
			return false
	return false


func _root_at(path: Array) -> Variant:
	var cursor: Variant = _value
	for step in path:
		if cursor is Dictionary:
			if not cursor.has(step):
				return null
			cursor = cursor[step]
		elif cursor is Array:
			var index := int(step)
			if index < 0 or index >= (cursor as Array).size():
				return null
			cursor = (cursor as Array)[index]
		else:
			return null
	return cursor


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


## A copy of `value` with every leaf blanked. Adding a stream to a control
## volume must give the right fields and no numbers.
static func _blanked(value: Variant) -> Variant:
	if value is Dictionary:
		var out: Dictionary = {}
		for key in (value as Dictionary).keys():
			out[key] = _blanked((value as Dictionary)[key])
		return out
	if value is Array:
		var out: Array = []
		for item in value as Array:
			out.append(_blanked(item))
		return out
	if typeof(value) == TYPE_BOOL:
		return false
	return ""


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


static func _path_key(path: Array) -> String:
	var parts := PackedStringArray()
	for step in path:
		parts.append(str(step))
	return "/".join(parts)