extends SceneTree
## Headless acceptance checks for the pecan evidence-workflow scene.
##
## Loads the real scene, reads the real compiled artifacts, selects steps through
## the same code path a click uses, and asserts that what is displayed is the
## artifact's own text: verbatim quote, source DOI, evidence class, hypothesis
## flag and unknowns. Nothing is stubbed.
##
## Run with:
##   godot --headless --path . --script composition/tests/godot/pecan_workflow_scene.gd

const SCENE := "res://scenes/pecan_workflow.tscn"

var _checks := 0
var _failures: Array[String] = []
var _ran := false
var _frames := 0
var _scene: Control


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		print("FAIL: ", message)


func _initialize() -> void:
	change_scene_to_file(SCENE)


func _process(_delta: float) -> bool:
	if _ran:
		return true
	if current_scene == null:
		return false
	_frames += 1
	if _frames < 3:
		return false
	_ran = true
	_scene = current_scene
	_run_checks()
	_finish()
	return true

func _run_checks() -> void:
	_check(_scene != null, "the pecan workflow scene loaded")
	if _scene == null:
		return
	_check(str(_scene.case_id()) == "pecan", "the pecan case is selected by default")
	_check(_scene.step_count() == 18, "18 protocol steps are rendered as nodes")
	# 6 direct + 11 analogue + 1 method-review steps: 5 + 10 + 0 protocol-order edges.
	_check(_scene.edge_count() == 15, "protocol-order edges are drawn inside each evidence class")
	var graph_size: Vector2 = _scene.graph_size()
	_check(graph_size.x > 800.0 and graph_size.y > 400.0,
		"the step graph is laid out with room for all three evidence lanes")
	var header := _find_label(_scene, "no predictive RNA yield")
	_check(header != null, "the header states this is not a predictive RNA simulation")
	var selector = _find_node(_scene, "CaseSelector")
	_check(selector != null, "a case selector is present")
	var status := _find_node(_scene, "CaseStatus")
	_check(status != null and str(status.text).contains("18 steps"),
		"the status line reports the loaded case")

	# Direct pecan step.
	_scene.select_step("pecan_trizol_extraction")
	var direct: String = _scene.evidence_text()
	_check(direct.contains("direct evidence"), "a direct step is labelled direct evidence")
	_check(direct.contains("10.3390/foods13182934"), "the direct step shows the pecan DOI")
	_check(direct.contains("Carya illinoinensis"), "the direct step shows the pecan organism")
	_check(direct.contains("TRIzol"), "the direct step shows the verbatim passage")
	_check(not direct.contains("analogue hypothesis"), "a direct step is not labelled a hypothesis")
	_check(direct.contains("unknown"), "the direct step shows its unknown parameter")

	# Analogous hypothesis.
	_scene.select_step("analogue_spruce_ctab_extraction")
	var analogue: String = _scene.evidence_text()
	_check(analogue.contains("analogue hypothesis"), "an analogue step is labelled a hypothesis")
	_check(analogue.contains("NOT validated on pecan"), "the analogue step says it is not validated")
	_check(analogue.contains("10.3390/plants13030389"), "the analogue step shows the spruce DOI")
	_check(analogue.contains("Picea abies") or analogue.contains("spruce"),
		"the analogue step names its organism or source")

	# Method review.
	_scene.select_step("method_review_caveat")
	var method: String = _scene.evidence_text()
	_check(method.contains("method review"), "a method-review step is labelled as such")

	# Unknowns must be visible somewhere in the scene.
	var all_text := _collect(_scene)
	_check(all_text.contains("not stated by the acquired sources") or all_text.contains("unknown"),
		"unknown quantities are displayed")
	_check(not all_text.to_lower().contains("predicted yield"),
		"no predicted yield is displayed")
	_check(_scene.outputs_panel() != null, "the existing results panel shows the workflow outputs")

	# The workshop header still offers both research entries.
	var workshop_script = load("res://scripts/workshop.gd")
	_check(workshop_script != null, "workshop.gd still compiles")
	if workshop_script != null:
		var workshop: Control = workshop_script.new()
		var header_row = workshop._header()
		_check(_find_node(header_row, "PecanWorkflowButton") != null,
			"the workshop header offers the pecan evidence workflow")
		_check(_find_node(header_row, "ResearchWorkflowButton") != null,
			"the workshop header still offers the research workflow")
		workshop.free()


func _find_node(node: Node, name: String) -> Node:
	if node == null:
		return null
	if str(node.name) == name:
		return node
	for child in node.get_children():
		var found := _find_node(child, name)
		if found != null:
			return found
	return null


func _find_label(node: Node, needle: String) -> Label:
	if node is Label and str((node as Label).text).contains(needle):
		return node
	for child in node.get_children():
		var found := _find_label(child, needle)
		if found != null:
			return found
	return null


func _collect(node: Node) -> String:
	var parts := PackedStringArray()
	_gather(node, parts)
	return "\n".join(parts)


func _gather(node: Node, parts: PackedStringArray) -> void:
	if node is Label:
		parts.append(str((node as Label).text))
	for child in node.get_children():
		_gather(child, parts)


func _finish() -> void:
	print("\nPECAN WORKFLOW SCENE CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)
