extends SceneTree
## The research-to-simulation screen is reachable from the workshop header, and
## the screen itself opens with a usable problem document.
##
## The workshop scene is not instantiated as a whole here: its `_ready` performs
## model-registry introspection that is already covered by
## `workshop_graph_run.gd`, and pulling that in would make this check depend on a
## different feature. Instead the header is built by the real `workshop.gd`, and
## the research scene is a real instantiate of its `.tscn`.
##
## Run with:
##   godot --headless --path . --script composition/tests/godot/research_workflow_entry.gd

const WORKSHOP_SCRIPT := "res://scripts/workshop.gd"
const TARGET_SCENE := "res://scenes/research_workflow.tscn"

var _checks := 0
var _failures: Array[String] = []


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		print("FAIL: ", message)


func _initialize() -> void:
	var script := load(WORKSHOP_SCRIPT)
	_check(script != null, "scripts/workshop.gd compiles")
	if script == null:
		_finish()
		return
	var workshop: Control = script.new()
	_check(workshop != null, "the workshop script instantiates")
	if workshop == null:
		_finish()
		return
	var header = workshop._header()
	_check(header != null, "the workshop builds a header")
	var button: Button = null
	if header != null:
		button = _find(header, "ResearchWorkflowButton")
	_check(button != null, "the workshop header owns a ResearchWorkflowButton")
	if button != null:
		_check(str(button.text) == "Research workflow", "the button is labelled Research workflow")
		_check(str(button.tooltip_text).contains("problem document"),
			"the button says it starts from a problem document")
		_check(not bool(button.disabled), "the button is enabled")
		_check(button.pressed.get_connections().size() == 1,
			"the button is wired to exactly one handler")
	_check(workshop.has_method("_on_research_pressed"), "the navigation handler exists")

	# The target scene must load on its own and start in a usable state. It is
	# added to the tree on the first processed frame, because a `_ready` added
	# during `_initialize` does not run.
	change_scene_to_file(TARGET_SCENE)
	workshop.free()


func _process(_delta: float) -> bool:
	if current_scene == null:
		return false
	var scene = current_scene
	_check(scene != null, "scenes/research_workflow.tscn opens")
	_check(scene.scene_file_path == TARGET_SCENE, "the opened scene is the research workflow scene")
	_check(scene.get("_run") != null, "the scene owns a Run workflow button")
	_check(scene.get("_status") != null, "the scene owns a status label")
	var problem := ""
	var field = scene.get("_problem_path")
	if field != null:
		problem = str(field.text)
	_check(problem != "" and FileAccess.file_exists(problem),
		"the scene starts with an existing problem document selected")
	var runner = scene.get("_runner")
	_check(runner != null and runner.has_method("run_research_workflow"),
		"the scene reaches Python through CompositionRunner.run_research_workflow")
	_finish()
	return true


func _find(node: Node, wanted: String) -> Button:
	for child in node.get_children():
		if child is Button and str(child.name) == wanted:
			return child as Button
		var found := _find(child, wanted)
		if found != null:
			return found
	return null


func _finish() -> void:
	print("\nRESEARCH WORKFLOW ENTRY CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)
