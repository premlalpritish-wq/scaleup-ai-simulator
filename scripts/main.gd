extends Control
## The main composition window.
##
## Layout: the process canvas on the left, the inspector / validation / results
## / diagnostics stack on the right, and a toolbar across the top.
##
## This script orchestrates. It does not compute. Every scientific decision is
## made by the Python runner, and every panel only renders what the runner or
## the model's own manifest reported.

const GRAPH_DIR := "user://graphs"
const RESULT_DIR := "user://results"
const EXAMPLE_DIR := "res://composition/examples"

var _document: GraphDocument = null
var _registry: ModelRegistry = null
var _runner: CompositionRunner = null
var _canvas: ProcessCanvas = null
var _inspector: ModelInspector = null
var _validation: ValidationPanel = null
var _results: ResultsPanel = null
var _diagnostics: DiagnosticsView = null
var _status: Label = null
var _progress: ProgressBar = null
var _selected_instance := ""
var _python_path := ""
var _composition_dir := ""
var _last_payload: Dictionary = {}
var _last_result_path := ""
var _examples: Array[String] = []


func _ready() -> void:
	_detect_environment()
	_build_ui()
	_load_examples()
	_registry.load()


func _detect_environment() -> void:
	# Find Python executable - assume python is in PATH for now
	_python_path = "python"

	# The composition package lives at <repo>/composition. Find it relative to
	# the executable so the project runs from any location.
	var exe_path := OS.get_executable_path()
	var base := exe_path.get_base_dir()
	var candidates := [
		base.path_join("../composition"),
		base.path_join("composition"),
	]
	for c in candidates:
		var dir := DirAccess.open(c)
		if dir != null and dir.file_exists("composition/runner.py"):
			_composition_dir = c
			break
	if _composition_dir == "":
		# Fall back: try relative to project root (res://)
		var project_root := ProjectSettings.globalize_path("res://")
		var dir := DirAccess.open(project_root.path_join("composition"))
		if dir != null and dir.file_exists("composition/runner.py"):
			_composition_dir = project_root.path_join("composition")
	if _composition_dir == "":
		push_error("Could not locate composition package. Set _composition_dir manually.")


func _build_ui() -> void:
	_document = GraphDocument.new()
	_registry = ModelRegistry.new()
	_runner = CompositionRunner.new(_python_path, _composition_dir)
	add_child(_registry)
	add_child(_runner)
	_registry.setup(_runner)
	_runner.finished.connect(_on_runner_finished)

	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 4)
	add_child(root)

	root.add_child(_toolbar())

	var body := HSplitContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.collapsed = false
	root.add_child(body)

	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(left)

	var canvas_frame := PanelContainer.new()
	canvas_frame.size_flags_vertical = Control.SIZE_EXPAND_FILL
	canvas_frame.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.add_child(canvas_frame)

	_canvas = ProcessCanvas.new()
	_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	canvas_frame.add_child(_canvas)
	_canvas.setup(_document, _registry)
	_canvas.connection_completed.connect(_on_connection_completed)
	_canvas.instance_selected.connect(_on_instance_selected)

	var canvas_hint := Label.new()
	canvas_hint.text = "drag from an output port to an input port to connect them"
	canvas_hint.add_theme_font_size_override("font_size", 10)
	canvas_hint.modulate = Color(1, 1, 1, 0.4)
	left.add_child(canvas_hint)

	var right := VBoxContainer.new()
	right.custom_minimum_size = Vector2(420, 0)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(right)

	var tabs := TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tabs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_child(tabs)

	_inspector = ModelInspector.new()
	_inspector.setup(_registry)
	tabs.add_child(_inspector)
	_inspector.name = "Inspector"

	_validation = ValidationPanel.new()
	tabs.add_child(_validation)
	_validation.name = "Validation"

	_results = ResultsPanel.new()
	_results.setup(_registry)
	tabs.add_child(_results)
	_results.name = "Results"

	_diagnostics = DiagnosticsView.new()
	tabs.add_child(_diagnostics)
	_diagnostics.name = "Provenance"

	_status = Label.new()
	_status.text = "Ready"
	_status.add_theme_font_size_override("font_size", 11)
	right.add_child(_status)

	_progress = ProgressBar.new()
	_progress.visible = false
	right.add_child(_progress)


func _toolbar() -> Control:
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 6)

	var run_button := Button.new()
	run_button.text = "Run"
	run_button.tooltip_text = "Validate and execute the graph with the Python runner"
	run_button.pressed.connect(_on_run_pressed)
	bar.add_child(run_button)

	var plan_button := Button.new()
	plan_button.text = "Validate only"
	plan_button.tooltip_text = "Order the graph and produce a plan without executing anything"
	plan_button.pressed.connect(_on_plan_pressed)
	bar.add_child(plan_button)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(spacer)

	var example_label := Label.new()
	example_label.text = "Load example:"
	example_label.add_theme_font_size_override("font_size", 11)
	example_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	bar.add_child(example_label)

	var example := OptionButton.new()
	example.name = "ExamplePicker"
	example.item_selected.connect(_on_example_selected)
	bar.add_child(example)

	var add_button := Button.new()
	add_button.text = "Add model"
	add_button.tooltip_text = "Place a model instance on the canvas"
	add_button.pressed.connect(_on_add_pressed)
	bar.add_child(add_button)

	var new_button := Button.new()
	new_button.text = "New graph"
	new_button.pressed.connect(_on_new_pressed)
	bar.add_child(new_button)

	var replay_button := Button.new()
	replay_button.text = "3D replay"
	replay_button.tooltip_text = "Open the 3D replay of the Zielinski process (a separate scene)"
	replay_button.pressed.connect(_on_replay_pressed)
	bar.add_child(replay_button)

	var save_button := Button.new()
	save_button.text = "Save graph"
	save_button.pressed.connect(_on_save_pressed)
	bar.add_child(save_button)

	var load_button := Button.new()
	load_button.text = "Open graph..."
	load_button.pressed.connect(_on_open_pressed)
	bar.add_child(load_button)

	return bar


func _load_examples() -> void:
	var picker: OptionButton = _find_node(self, "ExamplePicker") as OptionButton
	if picker == null:
		return
	picker.clear()
	picker.add_item("(choose an example)")
	var dir := DirAccess.open(EXAMPLE_DIR)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name.ends_with(".json"):
			_examples.append(name)
			picker.add_item(name.get_basename())
		name = dir.get_next()
	dir.list_dir_end()


func _find_node(from: Node, node_name: String) -> Node:
	if from.name == node_name:
		return from
	for child in from.get_children():
		var found := _find_node(child, node_name)
		if found != null:
			return found
	return null


func _on_example_selected(index: int) -> void:
	if index <= 0 or index > _examples.size():
		return
	var path := EXAMPLE_DIR.path_join(_examples[index - 1])
	_load_graph_file(path)


func _load_graph_file(path: String) -> void:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		_status.text = "Could not open %s" % path
		return
	var text := f.get_as_text()
	f.close()
	var err: Error = _document.from_json(text)
	if err != OK:
		_status.text = "The graph document at %s could not be parsed." % path
		return
	_selected_instance = ""
	_canvas.build_from_document()
	_validation.clear()
	_results.clear()
	_diagnostics.clear()
	_inspector.clear()
	_status.text = "Loaded %s  (%d instance(s), %d connection(s))" % [path.get_file(), _document.instances.size(), _document.connections.size()]
	_show_selected()


func _on_add_pressed() -> void:
	var dialog := ConfirmationDialog.new()
	dialog.title = "Add Model Instance"
	dialog.dialog_text = "Model palette not implemented in this version. Use the example graphs instead."
	dialog.ok_button_text = "OK"
	dialog.cancel_button_text = "Cancel"
	dialog.confirmed.connect(_on_add_confirmed)
	add_child(dialog)
	dialog.popup_centered()

func _on_add_confirmed() -> void:
	_status.text = "Model palette not implemented. Load an example graph instead."


func _on_instance_requested(model_id: String, model_version: String, label: String, role: String, parameters: Dictionary) -> void:
	var index := _document.instances.size()
	var position := Vector2(80 + (index % 4) * 280, 90 + (index / 4) * 200)
	var inst := _document.add_instance(model_id, model_version, label, role, position, parameters)
	_canvas.add_node(inst)
	_selected_instance = str(inst["instance_id"])
	_show_selected()
	_status.text = "Added %s. Connect its ports, then Run." % str(inst["instance_id"])


func _on_new_pressed() -> void:
	_document.reset()
	_selected_instance = ""
	_canvas.build_from_document()
	_validation.clear()
	_results.clear()
	_diagnostics.clear()
	_inspector.clear()
	_status.text = "New empty graph"


func _on_save_pressed() -> void:
	var dir := DirAccess.open(GRAPH_DIR)
	if dir == null:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(GRAPH_DIR))
	var path := GRAPH_DIR.path_join("%s.json" % _document.graph_id)
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		_status.text = "Could not write %s" % path
		return
	f.store_string(_document.to_json())
	f.close()
	_status.text = "Saved %s" % path


func _on_replay_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/replay3d.tscn")


func _on_open_pressed() -> void:
	var dialog := FileDialog.new()
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.access = FileDialog.ACCESS_USERDATA
	dialog.add_filter("*.json")
	dialog.current_dir = GRAPH_DIR
	dialog.file_selected.connect(_load_graph_file)
	add_child(dialog)
	dialog.popup_centered()


func _on_run_pressed() -> void:
	_run_runner(false)


func _on_plan_pressed() -> void:
	_run_runner(true)


func _run_runner(plan_only: bool) -> void:
	var shape_problems := _document.validate_shape()
	if not shape_problems.is_empty():
		_last_payload = {
			"status": "invalid",
			"error_count": shape_problems.size(),
			"warning_count": 0,
			"diagnostics": shape_problems.map(func(p): return {"code": "graph.shape", "severity": "error", "message": p, "where": ["graph"], "origin": "composition"}),
			"results": [],
			"plan": {"order": [], "steps": [], "diagnostics": [], "digest": ""},
			"provenance_index": {},
			"reproducibility": "",
		}
		_render_result()
		return

	var dir := DirAccess.open(RESULT_DIR)
	if dir == null:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(RESULT_DIR))
	var graph_path := GRAPH_DIR.path_join("%s.json" % _document.graph_id)
	var result_path := RESULT_DIR.path_join("%s.result.json" % _document.graph_id)
	var f := FileAccess.open(graph_path, FileAccess.WRITE)
	if f == null:
		_status.text = "Could not write the graph document."
		return
	f.store_string(_document.to_json())
	f.close()
	_last_result_path = result_path

	_status.text = "Running..." if not plan_only else "Validating..."
	_progress.visible = true
	_progress.value = 30
	_validation.clear()
	_results.clear()
	_diagnostics.clear()

	if plan_only:
		_runner.plan_graph(graph_path, result_path)
	else:
		_runner.run_graph(graph_path, result_path)


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		pass


func _on_runner_finished(payload: Dictionary) -> void:
	_last_payload = payload
	_progress.visible = false
	_render_result()


func _render_result() -> void:
	# If the subprocess failed to run at all, the result document will not
	# describe why, so surface the invocation and its captured output. This is
	# added before the panels are shown so they render it in the same pass.
	var exit_code: int = _last_payload.get("_exit_code", -1)
	var output: String = _last_payload.get("_output", "")
	if exit_code != 0 and exit_code != CompositionRunner.EXIT_INVALID:
		var msg := "The Python runner subprocess exited with code %d." % exit_code
		if not output.strip_edges().is_empty():
			msg += "\n\nSubprocess output (stdout and stderr, merged -- Godot's OS.execute cannot separate them):\n%s" % output.strip_edges()
		var diag: Dictionary = {
			"code": "runner.subprocess_failed",
			"severity": "error",
			"message": msg,
			"where": ["runner"],
			"origin": "runner",
			"remediation": "Check the Python environment, model package paths, and composition package installation. Run the graph manually with 'python -m composition.runner --graph <path> --result <out>' to see the full traceback."
		}
		var existing: Array = _last_payload.get("diagnostics", [])
		existing.append(diag)
		_last_payload["diagnostics"] = existing

	_validation.show_diagnostics(_last_payload)
	_results.show_results(_last_payload)
	_status.text = "%s  [%s]" % [CompositionRunner.status_summary(_last_payload), _document.graph_id]

	if not _selected_instance.is_empty():
		_show_selected()
	# The provenance panel is driven by the results panel; offer the first result.
	var results: Array = _last_payload.get("results", [])
	if results.size() > 0:
		var outputs: Array = results[0].get("outputs", [])
		if outputs.size() > 0:
			_select_output(outputs[0])


func _on_instance_selected(instance_id: String) -> void:
	_selected_instance = instance_id
	_show_selected()


func _show_selected() -> void:
	if _selected_instance.is_empty():
		return
	var inst := _document.find_instance(_selected_instance)
	if inst.is_empty():
		return
	for id in _canvas.nodes:
		_canvas.nodes[id].set_selected(id == _selected_instance)
	var ports: Array = []
	if _canvas.nodes.has(_selected_instance):
		ports = _canvas.nodes[_selected_instance].ports
	_inspector.show_instance(inst, ports)


func _on_connection_completed(from_instance: String, from_port: String, from_direction: String, from_global: Vector2, to_instance: String, to_port: String, to_direction: String, to_global: Vector2) -> void:
	# Connections run output -> input. If the user dragged the other way, swap.
	var src := {"instance_id": to_instance, "port_id": to_port, "direction": to_direction}
	var dst := {"instance_id": from_instance, "port_id": from_port, "direction": from_direction}
	if from_direction == "output" and to_direction == "input":
		src = {"instance_id": from_instance, "port_id": from_port, "direction": from_direction}
		dst = {"instance_id": to_instance, "port_id": to_port, "direction": to_direction}
	elif from_direction == to_direction:
		_status.text = "A connection must run from an output port to an input port."
		return
	if src["instance_id"] == dst["instance_id"]:
		_status.text = "v0.1 has no iterative solve, so a node cannot feed itself."
		return
	_document.add_connection(src, dst)
	_canvas.connections.append(_document.connections[_document.connections.size() - 1])
	_canvas.queue_redraw()
	_status.text = "Connected %s -> %s" % [src["port_id"], dst["port_id"]]


func _select_output(out: Dictionary) -> void:
	var ref: Dictionary = out.get("ref", {})
	var value: Dictionary = out.get("value", {})
	var chain: Array = value.get("provenance_chain", [])
	_diagnostics.show_value(ref, value, chain)


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_DELETE:
		if not _selected_instance.is_empty():
			_document.remove_instance(_selected_instance)
			_canvas.build_from_document()
			_selected_instance = ""
			_inspector.clear()
			_status.text = "Removed instance"
