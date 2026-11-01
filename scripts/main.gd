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
var _palette: ModelPalette = null
var _form: InstanceForm = null
var _inspector: ModelInspector = null
var _validation: ValidationPanel = null
var _results: ResultsPanel = null
var _diagnostics: DiagnosticsView = null
var _report: CompositionReportPanel = null
var _composition: CompositionPanel = null
var _status: Label = null
var _progress: ProgressBar = null
var _selected_instance := ""
var _python_path := ""
var _composition_dir := ""
var _last_payload: Dictionary = {}
var _last_result_path := ""
var _examples: Array[String] = []
## Set while a result document is on screen. Any change to the graph clears it,
## because a result that belongs to a graph the user has since edited is not a
## result of the graph that is now in front of them.
var _results_are_current := false
## True only between issuing a graph run and receiving its result. The runner's
## single `finished` signal also carries discovery and manifest reads, which must
## not be rendered as a run.
var _awaiting_run := false
## Set while the `--describe-connections` request is outstanding.
##
## The palette renders the engine's compatibility position for every library
## entry, so this window asks for it once, after model discovery. The request is
## made here rather than inside `ModelRegistry` because the workshop and replay
## scenes drive that same runner with their own request sequencing, and a third
## caller inside the registry would interleave with theirs.
var _awaiting_connections := false
## Set while the `--describe-papers` request is outstanding. The model library
## lists the whole ingested corpus beside the registered models, so that a paper
## with no model is visible rather than silently absent.
var _awaiting_papers := false


func _ready() -> void:
	_detect_environment()
	_build_ui()
	_load_examples()
	_registry.load()
	_request_compatibility.call_deferred()
	_request_corpus.call_deferred()


func _detect_environment() -> void:
	if OS.get_name() == "Web":
		_python_path = "python"
		_composition_dir = ""
		return
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
	# The form is created before the palette because the palette opens it. It is
	# an independent window, so it is added to the tree rather than to a panel.
	_form = InstanceForm.new()
	_form.setup(_registry)
	add_child(_form)
	_registry.setup(_runner)
	_registry.models_loaded.connect(_on_models_loaded)
	_registry.load_failed.connect(_on_load_failed)
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

	_palette = ModelPalette.new()
	_palette.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_palette.setup(_registry, _form)
	_palette.instance_requested.connect(_on_instance_requested)
	_palette.palette_message.connect(_set_status)
	left.add_child(_palette)

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

	_report = CompositionReportPanel.new()
	tabs.add_child(_report)
	_report.name = "Report"

	# Which of the seven papers may contribute to the insulin process. It owns a
	# private runner, so it cannot consume one of this window's introspection
	# answers in the middle of the discovery chain.
	_composition = CompositionPanel.new()
	tabs.add_child(_composition)
	_composition.name = "Composition"
	_composition.setup(_python_path, _composition_dir)
	_composition.request()

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

	# There is deliberately no "Add model" button: the palette is always visible
	# above the canvas, and a button that only scrolled to a list already on
	# screen would be a second way to do one thing.
	var new_button := Button.new()
	new_button.text = "New graph"
	new_button.pressed.connect(_on_new_pressed)
	bar.add_child(new_button)

	var replay_button := Button.new()
	replay_button.text = "Zieliński replay"
	replay_button.tooltip_text = (
		"Predefined experiment replay, not a simulation. It re-plays one published "
		+ "batch from Zielinski et al. (2019): the growth curve is digitized from "
		+ "their Figure 3 and the purification values are transcribed from their "
		+ "text. It runs its own fixed graph and is separate from the models you "
		+ "compose on the canvas.")
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
	_sync_palette_to_graph()
	_discard_results("a different graph was loaded")
	_inspector.clear()
	_status.text = "Loaded %s  (%d instance(s), %d connection(s))" % [path.get_file(), _document.instances.size(), _document.connections.size()]
	_show_selected()


## One-line feedback in the status bar, from the palette or the runner.
func _set_status(text: String) -> void:
	if _status != null:
		_status.text = text


func _on_instance_requested(model_id: String, model_version: String, label: String, role: String, parameters: Dictionary, literals: Dictionary) -> void:
	var index := _document.instances.size()
	var position := Vector2(80 + (index % 4) * 280, 90 + (index / 4) * 200)
	var inst := _document.add_instance(model_id, model_version, label, role, position, parameters)
	var instance_id := str(inst["instance_id"])
	# Literals are declared on the document, not on the instance, because that is
	# where the engine reads them from. They are the values the operator typed;
	# none of them is inferred from a default.
	for port_id in literals.keys():
		_document.set_literal(instance_id, str(port_id), (literals[port_id] as Dictionary).duplicate(true))
	_canvas.add_node(inst)
	_selected_instance = instance_id
	_invalidate_results("the graph changed")
	_sync_palette_to_graph()
	_show_selected()
	var supplied := "" if literals.is_empty() else " with %d declared input(s)" % literals.size()
	_status.text = "Added %s (%s@%s)%s. Connect its ports, then Run." % [
		instance_id, model_id, model_version, supplied]


## Clear every result panel, because the graph these results described is no
## longer the graph on screen. Without this a run stays on the Results tab after
## the user deletes the node that produced it, and it reads as current.
##
## The composition report is *marked* rather than cleared here. A report is an
## argument, not a number: a reader who was part-way through it when they added
## a connection should be able to finish reading the assessment they were given,
## with a banner saying it describes the graph as it stood before that edit.
## Clearing is reserved for `_discard_results`, where a different graph replaces
## this one and the old assessment has nothing left to be about.
func _invalidate_results(reason: String) -> void:
	_results_are_current = false
	_last_payload = {}
	if _validation != null:
		_validation.clear()
	if _results != null:
		_results.clear()
	if _diagnostics != null:
		_diagnostics.clear()
	if _report != null:
		_report.mark_stale(reason)
	if _status != null:
		_status.text = "No current results -- %s." % reason


## Invalidate, and additionally clear the report: a different graph is now on
## screen, so the previous assessment is about a document that no longer exists.
func _discard_results(reason: String) -> void:
	_invalidate_results(reason)
	if _report != null:
		_report.clear()


func _on_new_pressed() -> void:
	_document.reset()
	_selected_instance = ""
	_canvas.build_from_document()
	_sync_palette_to_graph()
	_discard_results("a new empty graph was started")
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
		# The runner was never invoked on this path, so there is no report from
		# it to render. Saying "the runner had nothing to report" would be a
		# different claim, and a wrong one.
		_report.show_graph_problems(_document.graph_id, shape_problems)
		return

	var graph_dir := DirAccess.open(GRAPH_DIR)
	if graph_dir == null:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(GRAPH_DIR))
	var result_dir := DirAccess.open(RESULT_DIR)
	if result_dir == null:
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
	_invalidate_results("a run is in progress")
	# Only a graph run may repaint the result panels. The same `finished` signal
	# also carries model discovery, and rendering that as a run would report a
	# failure the user never asked for.
	_awaiting_run = true

	if plan_only:
		_runner.plan_graph(graph_path, result_path)
	else:
		_runner.run_graph(graph_path, result_path)


## Ask the runner for the compatibility position the palette renders.
##
## Deferred, so it runs after the discovery chain `_registry.load()` starts has
## finished. `describe_connections()` is synchronous on desktop, and issuing it
## from inside a signal handler that the discovery payload is still unwinding
## would hand the answer to whichever request happened to be pending.
func _request_compatibility() -> void:
	if _awaiting_connections or _runner == null or _registry == null:
		return
	if _registry.model_ids().is_empty():
		# Discovery failed or found nothing. The palette already reports that,
		# and a compatibility matrix about no models would only be noise on top
		# of the failure it is supposed to explain.
		return
	_awaiting_connections = true
	_runner.describe_connections()


## Ask the runner for the ingested-paper corpus index.
##
## Deferred for the same reason as the compatibility request: it must not land in
## the middle of the discovery chain's own pending requests. Unlike the model
## list, this one is asked even when the registry is empty -- a corpus whose
## papers produced no registered model is exactly what a reader needs to see.
func _request_corpus() -> void:
	if _awaiting_papers or _runner == null or _registry == null:
		return
	_awaiting_papers = true
	_runner.describe_papers()


## Tell the palette which models the graph actually contains, so a row can say
## whether that model can join *this* simulation rather than some other one.
func _sync_palette_to_graph() -> void:
	if _palette == null:
		return
	var model_ids: Array = []
	for inst in _document.instances:
		model_ids.append(str(inst.get("model_id", "")))
	_palette.set_active_models(model_ids)


func _on_models_loaded(_models: Array) -> void:
	if _status == null:
		return
	var names := PackedStringArray()
	for model_id in _registry.model_ids():
		var reference := _registry.reference_for(model_id)
		names.append(reference if reference != "" else str(model_id))
	if _status.text.is_empty():
		_status.text = "models: %s" % ", ".join(names)
	else:
		_status.text = "%s  |  models: %s" % [_status.text, ", ".join(names)]


func _on_load_failed(message: String) -> void:
	# A discovery failure is a loading failure, not a scientific incompatibility,
	# and it is stated as such. The canvas falls back to whatever the graph
	# document already carries; no port is invented to cover the gap.
	push_warning("model discovery failed: %s" % message)
	if _status != null:
		_status.text = "Model discovery failed -- %s" % message.split("\n")[0]


func _on_runner_finished(payload: Dictionary) -> void:
	if _awaiting_connections:
		# The compatibility position. `ModelRegistry` maps it; the palette draws
		# it. This window only had to ask, because it is the one scene whose
		# model library had no standing to show.
		_awaiting_connections = false
		_registry.accept_connections(payload)
		return
	if _awaiting_papers:
		# The ingested-paper corpus index. The palette lists it beside the
		# registered models; nothing in it is placeable.
		_awaiting_papers = false
		_registry.accept_papers(payload)
		return
	if not _awaiting_run:
		# Discovery or manifest read. `ModelRegistry` has already consumed it.
		return
	_awaiting_run = false
	_last_payload = payload
	_progress.visible = false
	_render_result()
	# Every document the runner writes carries a composition report, including
	# one that refused before executing, so this renders for a failure too. The
	# shape-rejection path above sets its own, because that one never reached
	# the runner at all.
	_report.show_report(_last_payload)


func _render_result() -> void:
	# The result document is the authority on why a run ended. Only when there is
	# no usable document is the subprocess's own output the only evidence left,
	# so that is the only case where the invocation detail is added -- otherwise
	# the same failure is reported twice under two codes.
	var exit_code: int = _last_payload.get("_exit_code", CompositionRunner.EXIT_OK)
	if exit_code != 0 and not _payload_has_diagnostics(_last_payload):
		var output: String = _last_payload.get("_output", "")
		var msg := "The Python runner subprocess exited with code %d (%s)." % [
			exit_code, CompositionRunner.exit_meaning(exit_code),
		]
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
	_results_are_current = true
	_status.text = "%s  [%s]" % [
		CompositionRunner.status_summary(_last_payload), _document.graph_id,
	]
	if exit_code != 0:
		_status.text += "  -- exit %d: %s" % [
			exit_code, CompositionRunner.exit_meaning(exit_code),
		]

	if not _selected_instance.is_empty():
		_show_selected()
	# The provenance panel is driven by the results panel; offer the first result.
	var results: Array = _last_payload.get("results", [])
	if results.size() > 0:
		var outputs: Array = results[0].get("outputs", [])
		if outputs.size() > 0:
			_select_output(outputs[0])


## True when the payload carries at least one diagnostic that explains itself.
##
## An empty or absent `diagnostics` array is not an empty success here: the
## runner writes a diagnostic for every failure it reports, so a missing array on
## a non-zero exit means the document did not survive the boundary.
func _payload_has_diagnostics(payload: Dictionary) -> bool:
	return payload.has("diagnostics") and not payload["diagnostics"].is_empty()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		pass


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
	var ports_source := "none"
	if _canvas.nodes.has(_selected_instance):
		ports = _canvas.nodes[_selected_instance].ports
		ports_source = _canvas.nodes[_selected_instance].ports_source
	_inspector.show_instance(inst, ports, ports_source)


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
	_invalidate_results("a connection was added")
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
			_sync_palette_to_graph()
			_invalidate_results("an instance was removed")
			_status.text = "Removed instance"
