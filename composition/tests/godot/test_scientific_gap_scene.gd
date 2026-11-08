extends SceneTree
## Checks that the feature is reachable from the Zielinski replay scene.

var _checks := 0
var _failures: Array[String] = []
var _ran := false
var _frames := 0


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		print("FAIL: ", message)


func _initialize() -> void:
	change_scene_to_file("res://scenes/replay3d.tscn")


func _process(_delta: float) -> bool:
	if _ran:
		return true
	var root := current_scene
	if root == null:
		return false
	_frames += 1
	# The replay starts its model asynchronously. The gap panel is built in
	# _ready and is independent of that run, so wait for the scene to settle
	# rather than waiting for a particular execution result.
	if _frames < 3:
		return false
	_ran = true
	root.set("_playing", false)

	var panel = root.get("_gaps")
	_check(panel != null, "the replay scene owns a ScientificGapPanel")
	if panel == null:
		_finish()
		return true
	_check(str(panel.name) == "ScientificGapPanel", "the section is named ScientificGapPanel")
	_check(panel.is_inside_tree(), "the gap panel is in the replay scene tree")
	panel.request()
	var payload: Dictionary = panel.payload()
	_check(payload.has("gaps"), "the replay scene can run the gap analysis")
	_check(panel.gap_count() == 12, "the live feature shows all 12 gaps")
	_check(panel.summary_value("target").contains("Zielinski"), "the analysis names the Zielinski target")
	_check(panel.summary_value("partially_addressed") == "2", "the summary shows the partial literature contributions")
	_finish()
	return true


func _finish() -> void:
	print("\nSCIENTIFIC GAP SCENE CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)
