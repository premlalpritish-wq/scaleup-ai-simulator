class_name DiagnosticsView
extends PanelContainer
## The diagnostics view: which model produced each result, and which
## assumptions and derived calculations it passed through.
##
## This is the panel that makes a displayed number answerable. Every value
## carries a chain of provenance records -- source, transfer, derivation,
## assumption -- and this panel renders it.

var _tree: Tree = null
var _detail: RichTextLabel = null


func _ready() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var heading := Label.new()
	heading.text = "Provenance"
	heading.add_theme_font_size_override("font_size", 13)
	vb.add_child(heading)

	var hint := Label.new()
	hint.text = "Select a value in the results panel to trace it back to the model that produced it."
	hint.add_theme_font_size_override("font_size", 10)
	hint.modulate = Color(1, 1, 1, 0.55)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD
	vb.add_child(hint)

	var split := HSplitContainer.new()
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(split)

	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	split.add_child(scroll)

	_tree = Tree.new()
	_tree.columns = 3
	_tree.column_titles_visible = true
	_tree.set_column_title(0, "hop")
	_tree.set_column_title(1, "kind")
	_tree.set_column_title(2, "producer")
	_tree.hide_root = true
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.item_selected.connect(_on_item_selected)
	scroll.add_child(_tree)

	_detail = RichTextLabel.new()
	_detail.bbcode_enabled = true
	_detail.fit_content = true
	_detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.scroll_following = true
	split.add_child(_detail)


func show_value(ref: Dictionary, value: Dictionary, chain: Array) -> void:
	_tree.clear()
	_detail.text = ""
	if chain.is_empty():
		var root := _tree.create_item()
		root.set_text(0, "-")
		root.set_text(1, "no provenance")
		root.set_text(2, "this value carries no provenance chain")
		_detail.text = "[b]%s[/b] has no provenance chain. It was not produced by a model run." % str(ref.get("port_id", ""))
		return

	var root := _tree.create_item()
	for i in range(chain.size()):
		var record: Dictionary = chain[i]
		var item := _tree.create_item(root)
		item.set_text(0, "%d" % (i + 1))
		item.set_text(1, str(record.get("kind", "")))
		item.set_text(2, "%s v%s" % [str(record.get("producer_model", "")), str(record.get("producer_version", ""))])
		item.set_tooltip_text(0, str(record.get("where", "")))
		item.set_tooltip_text(1, str(record.get("detail", "")))
		item.set_meta("record", record)

	_detail.text = _render_value(ref, value, chain)


func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item == null:
		return
	var record: Dictionary = item.get_meta("record", {})
	var text := "[b]%s[/b]  v%s\n" % [str(record.get("producer_model", "")), str(record.get("producer_version", ""))]
	text += "[b]kind:[/b]  %s\n" % str(record.get("kind", ""))
	text += "[b]where:[/b]  %s\n" % str(record.get("where", ""))
	if str(record.get("detail", "")) != "":
		text += "\n%s\n" % str(record["detail"])
	if str(record.get("method", "")) != "":
		text += "\n[color=#9ec1ff]method:[/color]  %s" % str(record["method"])
	if record.has("connection_id"):
		text += "\n[color=#9ec1ff]connection:[/color]  %s" % str(record["connection_id"])
		text += "\n[color=#9ec1ff]from:[/b]  %s  ->  %s" % [str(record.get("source_port", "")), str(record.get("target_port", ""))]
	if record.has("conversion"):
		var conv: Dictionary = record["conversion"]
		text += "\n[color=#9ec1ff]conversion:[/color]  %s %s -> %s %s  (factor %s)" % [
			str(conv.get("value", "")), str(conv.get("from_unit", "")),
			str(conv.get("to_unit", "")), str(conv.get("quantity", "")),
			str(conv.get("factor", "")),
		]
	if str(record.get("source_ref", "")) != "":
		text += "\n[color=#9ec1ff]source:[/color]  %s" % str(record["source_ref"])
	if record.has("inputs"):
		var inputs: Array = record.get("inputs", [])
		if not inputs.is_empty():
			text += "\n[color=#9ec1ff]inputs:[/color]  %s" % ", ".join(inputs)
	_detail.text = text


func _render_value(ref: Dictionary, value: Dictionary, chain: Array) -> String:
	var text := "[b]%s[/b]\n" % str(ref.get("port_id", ""))
	text += "state:  %s\n" % str(value.get("state", ""))
	text += "quantity:  %s\n" % str(value.get("quantity", ""))
	text += "display:  %s\n" % str(value.get("display", ""))
	text += "provenance:  %s\n" % str(value.get("provenance", ""))
	if str(value.get("reason", "")) != "":
		text += "reason:  %s\n" % str(value["reason"])
	text += "\n[color=#9ec1ff]chain (%d hop(s), oldest first):[/color]\n" % chain.size()
	for i in range(chain.size()):
		var record: Dictionary = chain[i]
		text += "  %d.  [b]%s[/b]  %s v%s\n" % [i + 1, str(record.get("kind", "")), str(record.get("producer_model", "")), str(record.get("producer_version", ""))]
		if str(record.get("detail", "")) != "":
			text += "      %s\n" % str(record["detail"])
	return text


func clear() -> void:
	if _tree == null:
		return
	_tree.clear()
	if _detail != null:
		_detail.text = ""
