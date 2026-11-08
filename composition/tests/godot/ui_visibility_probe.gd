extends SceneTree
## Read-only diagnostic probe.  Launches the real main scene, reports what a
## user can actually see and select, and then drives the shipped UI controls
## (the example picker and the Run button) rather than calling the Python
## layer directly.
##
##     godot --headless --path . --script res://composition/tests/godot/ui_visibility_probe.gd
##
## It changes nothing outside `user://` and asserts nothing.  Exit code 0 means
## the probe ran; it is not a pass/fail test.

const WAIT_SECONDS := 5.0
const EXAMPLE := "ganjave_fed_batch"

var _elapsed := 0.0
var _phase := 0
var _picker: OptionButton = null
var _ran: Dictionary = {}


func _initialize() -> void:
	change_scene_to_file("res://scenes/composition.tscn")


func _process(delta: float) -> bool:
	_elapsed += delta
	if current_scene == null:
		return _elapsed > 30.0
	if _phase == 0:
		if _elapsed < WAIT_SECONDS:
			return false
		_report_startup(current_scene)
		_phase = 1
		_elapsed = 0.0
	elif _phase == 1:
		if _elapsed < 0.5:
			return false
		_select_example(EXAMPLE)
		_phase = 2
		_elapsed = 0.0
	elif _phase == 2:
		if _elapsed < 0.5:
			return false
		_report_after_load(current_scene)
		current_scene.call("_on_run_pressed")          # the real Run button handler
		var payload: Variant = current_scene.get("_last_payload")
		_ran = payload if payload is Dictionary else {}
		_report_after_run(current_scene)
		return true
	_elapsed += 60.0                                     # never stall
	return _elapsed > 120.0


# --------------------------------------------------------------------------- #


func _report_startup(scene: Node) -> void:
	print("=== 1. MAIN SCENE AT LAUNCH (res://scenes/composition.tscn) ===")
	print("--- widgets carrying user-visible text ---")
	_walk(scene, 0)
	print("")
	print("--- startup state ---")
	_print_canvas(scene)
	print("status line              : %s" % _status(scene))
	print("")
	print("--- the model palette ---")
	var palette: Variant = scene.get("_palette")
	if palette == null:
		print("  (no palette attached to the scene)")
	else:
		for entry in palette.model_entries():
			print("  %-28s available=%s dependence=%-8s name=%s"
				% [entry.get("reference", "?"), str(entry.get("available", false)),
				   str(entry.get("port_dependence", "?")),
				   str(entry.get("display_name", "?"))])
		print("  has_load_error: %s" % str(palette.has_load_error()))
		print("  load_error    : %s" % palette.load_error())
	print("")
	print("--- example picker contents ---")
	_picker = _find_option_button(scene)
	if _picker == null:
		print("  (no OptionButton found)")
	else:
		for i in _picker.item_count:
			print("  [%d] %s" % [i, _picker.get_item_text(i)])


func _select_example(title: String) -> void:
	if _picker == null:
		return
	for i in _picker.item_count:
		if _picker.get_item_text(i) == title:
			_picker.selected = i
			_picker.item_selected.emit(i)
			return


func _report_after_load(scene: Node) -> void:
	print("")
	print("=== 2. AFTER CHOOSING '%s' IN THE EXAMPLE PICKER ===" % EXAMPLE)
	_print_canvas(scene)
	print("status line              : %s" % _status(scene))


func _report_after_run(scene: Node) -> void:
	print("")
	print("=== 3. AFTER PRESSING THE REAL 'Run' BUTTON ===")
	print("status line              : %s" % _status(scene))
	print("result payload status    : %s" % str(_ran.get("status", "(none)")))
	print("error_count / warnings   : %s / %s"
		% [str(_ran.get("error_count", "?")), str(_ran.get("warning_count", "?"))])
	for result in _ran.get("results", []):
		var outs: Array = result.get("outputs", [])
		var chained := 0
		for o in outs:
			if not (o.get("provenance_chain", []) as Array).is_empty():
				chained += 1
		print("  instance %s (model %s): status=%s  outputs=%d  with provenance chain=%d"
			% [result.get("instance_id", "?"), result.get("model_id", "?"),
			   result.get("status", "?"), outs.size(), chained])
		var shown := 0
		for o in outs:
			if shown >= 4:
				break
			var value: Dictionary = o.get("value", {})
			print("    %s = %s %s (%s)"
				% [o.get("ref", {}).get("port_id", "?"), str(value.get("value", "")),
				   str(value.get("unit", "")), str(value.get("provenance", ""))])
			shown += 1
	print("diagnostics surfaced     : %d" % (_ran.get("diagnostics", []) as Array).size())
	print("results panel tabs       : %s" % _result_tab_names(scene))


# --------------------------------------------------------------------------- #


func _print_canvas(scene: Node) -> void:
	var doc: Variant = scene.get("_document")
	if doc == null:
		print("graph document           : (null)")
		return
	print("graph_id                 : %s" % str(doc.graph_id))
	print("instances on the canvas  : %d" % doc.instances.size())
	print("connections on the canvas: %d" % doc.connections.size())
	for inst in doc.instances:
		print("  node: %s  model=%s@%s  label=%s"
			% [inst.get("instance_id", "?"), inst.get("model_id", "?"),
			   inst.get("model_version", "?"), inst.get("label", "")])
	var canvas: Variant = scene.get("_canvas")
	if canvas != null:
		print("canvas nodes drawn       : %d" % (canvas.nodes as Dictionary).size())


func _result_tab_names(scene: Node) -> String:
	var names := PackedStringArray()
	for tab in _find_named(scene, "Results"):
		for child in tab.get_children():
			names.append(String(child.name))
			for grandchild in child.get_children():
				names.append("  -> %s (%d rows)" % [String(grandchild.name), grandchild.get_child_count()])
	return str(names) if names.size() > 0 else "(no populated Results tab)"


func _find_named(n: Node, wanted: String) -> Array:
	var out: Array = []
	if String(n.name) == wanted:
		out.append(n)
	for c in n.get_children():
		out.append_array(_find_named(c, wanted))
	return out


func _status(scene: Node) -> String:
	var found := _status_of(scene)
	return found if found != "" else "(no status text)"


func _status_of(n: Node) -> String:
	if n is Label:
		var text := String(n.text)
		if text.find("models:") >= 0 or text.find("[") >= 0 or text.begins_with("Loaded ") \
				or text.begins_with("Removed ") or text.begins_with("Model palette"):
			return text
	for c in n.get_children():
		var found := _status_of(c)
		if found != "":
			return found
	return ""


func _last_dialog_text(scene: Node) -> String:
	var found := _dialog_text(scene)
	return found if found != "" else "(no dialog node found in the tree)"


func _dialog_text(n: Node) -> String:
	if n is ConfirmationDialog:
		return String(n.dialog_text)
	for c in n.get_children():
		var found := _dialog_text(c)
		if found != "":
			return found
	return ""


func _walk(node: Node, depth: int) -> void:
	for child in node.get_children():
		var line := _describe(child)
		if line != "":
			print("  ".repeat(depth) + "- " + line)
		_walk(child, depth + 1)


func _describe(n: Node) -> String:
	if n is OptionButton:
		return "%s [OptionButton] selected=%s items=%s" % [
			n.name, str(n.selected), str(n.item_count)]
	if n is Button:
		var tip := ""
		if n.has_method("get_tooltip_text"):
			tip = String(n.tooltip_text)
		return "%s [Button] text=%s%s" % [
			n.name, JSON.stringify(String(n.text)),
			"" if tip == "" else "  tooltip=%s" % JSON.stringify(tip)]
	if n is TabContainer:
		var names := PackedStringArray()
		for c in n.get_children():
			names.append(String(c.name))
		return "%s [TabContainer] tabs=%s" % [n.name, str(names)]
	if n is ProgressBar:
		return "%s [ProgressBar] visible=%s" % [n.name, str(n.visible)]
	if n is Label:
		var text := String(n.text)
		if text.strip_edges() == "":
			return ""
		return "%s [Label] %s" % [n.name, JSON.stringify(text)]
	return ""


func _find_option_button(n: Node) -> OptionButton:
	if n is OptionButton:
		return n
	for c in n.get_children():
		var found := _find_option_button(c)
		if found != null:
			return found
	return null