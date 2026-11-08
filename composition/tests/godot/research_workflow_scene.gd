extends SceneTree
## Headless acceptance check for the research-to-simulation scene.
##
## The scene is loaded for real, the real Python workflow is executed through the
## real `CompositionRunner`, and every assertion below is read from the document
## that run wrote -- not from a fixture. If the boundary or the workflow breaks,
## this script fails rather than printing a plausible screen.
##
## Run with:
##   godot --headless --path . --script composition/tests/godot/research_workflow_scene.gd

const PROBLEM := "res://composition/composition/workflow/fixtures/pecan/problem.json"

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
	change_scene_to_file("res://scenes/research_workflow.tscn")


func _process(_delta: float) -> bool:
	if _ran:
		return true
	var root := current_scene
	if root == null:
		return false
	_frames += 1
	if _frames < 3:
		return false
	_ran = true
	_scene = root
	_run_checks()
	_finish()
	return true


func _run_checks() -> void:
	_check(_scene != null, "the research workflow scene loaded")
	if _scene == null:
		return
	var run_button = _scene.get("_run")
	_check(run_button != null, "the scene owns a Run workflow button")
	if run_button != null:
		_check(str(run_button.name) == "RunWorkflowButton", "the button is named RunWorkflowButton")
		_check(not bool(run_button.disabled), "the button is available before the first run")
	var status = _scene.get("_status")
	_check(status != null, "the scene owns a status label")
	if status != null:
		_check(str(status.text).contains("No workflow has run"),
			"the scene states that nothing has run yet instead of showing empty results")

	_scene.set_problem_input(PROBLEM)
	_check(_scene.problem_input() == PROBLEM, "the shipped pecan problem document can be selected")
	_scene.run_selected_problem()

	var payload: Dictionary = _scene.payload()
	_check(not payload.is_empty(), "the runner returned a result document")
	if payload.is_empty():
		return
	_check(int(payload.get("_exit_code", -1)) == 0, "the runner exited 0")
	_check(str(payload.get("status", "")) == "success", "the workflow status is success")
	_check(int(payload.get("error_count", 1)) == 0, "the run recorded no error diagnostic")

	_artifact_checks(payload)
	_science_checks(payload)
	_screen_checks()


func _artifact_checks(payload: Dictionary) -> void:
	var artifacts: Dictionary = payload.get("artifacts", {})
	for name in ["problem_spec", "literature_manifest", "research_encoded", "model_spec",
			"composition_graph", "simulation_result"]:
		_check(artifacts.has(name), "the run wrote an artifact path for " + name)
		if artifacts.has(name):
			_check(FileAccess.file_exists(str(artifacts[name])),
				"the artifact file exists: " + name)
	var result_path := str(payload.get("_result_path", ""))
	_check(result_path != "" and FileAccess.file_exists(result_path),
		"the result document the screen reads exists on disk")


func _science_checks(payload: Dictionary) -> void:
	var encoded: Dictionary = payload.get("encoded", {})
	var verification: Dictionary = encoded.get("verification", {})
	_check(int(verification.get("claim_count", 0)) == 25, "25 verified claims were encoded")
	_check(int(verification.get("quotes_verified", -1)) == 25, "every quote was re-found in its source")
	_check(int(verification.get("numeric_values_verified", -1)) == 66,
		"every numeric parameter was found in its own quote")
	_check(str(verification.get("source_role_check", "")) == "enforced",
		"the run enforced the source-role ceiling")

	var model: Dictionary = payload.get("model", {})
	var readiness: Dictionary = model.get("readiness", {})
	_check(int(readiness.get("direct_target_claim_count", -1)) == 6,
		"six claims are direct target-organism evidence")
	_check(int(readiness.get("analogue_claim_count", -1)) == 17,
		"seventeen claims are analogous-species evidence")
	_check(int(readiness.get("unresolved_parameter_count", -1)) == 18,
		"eighteen parameters remain unresolved")
	_check(bool(readiness.get("quantitative_yield_available_for_target", true)) == false,
		"no target yield is claimed")
	_check(bool(readiness.get("protocol_complete_for_target", true)) == false,
		"the target protocol is not claimed complete")

	var direct_steps := 0
	for step in model.get("steps", []):
		var status := str(step.get("evidence_status", ""))
		if status.begins_with("direct_target"):
			direct_steps += 1
			_check(step.get("source_ids", []) == ["pecan_miRNome"],
				"a direct step cites only the pecan source")
			_check(bool(step.get("hypothesis", true)) == false,
				"a direct step is not marked a hypothesis")
		elif status.begins_with("analogous"):
			_check(bool(step.get("hypothesis", false)) == true,
				"an analogue step is marked a hypothesis")
	_check(direct_steps == 6, "six direct protocol steps were built")

	var outputs := {}
	for result in payload.get("results", []):
		for output in result.get("outputs", []):
			var ref: Dictionary = output.get("ref", {})
			var value: Dictionary = output.get("value", {})
			outputs[str(ref.get("port_id", ""))] = value.get("value")
	_check(float(outputs.get("claim_count", -1)) == 25.0, "the model published claim_count")
	_check(float(outputs.get("direct_target_claim_count", -1)) == 6.0,
		"the model published direct_target_claim_count")
	_check(float(outputs.get("analogue_claim_count", -1)) == 17.0,
		"the model published analogue_claim_count")
	_check(float(outputs.get("quantitative_yield_available_for_target", 1)) == 0.0,
		"the model published no yield availability")
	for forbidden in ["predicted_yield", "degradation_rate", "yield_ug", "rin"]:
		_check(not outputs.has(forbidden), "the model published no %s port" % forbidden)


func _screen_checks() -> void:
	var problem_body = _scene.get("_problem_body")
	var result_body = _scene.get("_result_body")
	_check(problem_body != null and problem_body.get_child_count() > 0,
		"the problem specification is displayed")
	_check(result_body != null and result_body.get_child_count() > 0,
		"the workflow result is displayed")
	var texts := PackedStringArray()
	_collect_text(_scene, texts)
	var joined := "\n".join(texts)
	_check(joined.contains("Carya illinoinensis"), "the target organism is displayed")
	_check(joined.contains("direct_target_evidence"), "direct evidence is displayed and labelled")
	_check(joined.contains("analogous_species_hypothesis"), "analogous evidence is displayed and labelled")
	_check(joined.contains("hypothesis, not a measurement on the target"),
		"analogue steps are labelled as hypotheses on screen")
	_check(joined.contains("claim_count"), "the published outputs are displayed")
	_check(_payload_has_micro(_scene.payload()),
		"real paper text with a non-ASCII unit survived the Python → Godot bridge")
	_check(joined.contains("workflow_result.json"), "an artifact location is displayed")
	_check(joined.contains("do not state"), "unresolved quantities are displayed, not hidden")


## The pecan protocol text contains `µL`. If the bridge mis-decoded the UTF-8
## document, this string would arrive as mojibake instead -- which is exactly the
## bug this check exists for.
func _payload_has_micro(payload: Dictionary) -> bool:
	var model: Dictionary = payload.get("model", {})
	for step in model.get("steps", []):
		if str(step.get("action", "")).contains("µL"):
			return true
	return false


func _collect_text(node: Node, out: PackedStringArray) -> void:
	for child in node.get_children():
		if child is Label:
			out.append((child as Label).text)
		_collect_text(child, out)


func _finish() -> void:
	print("\nRESEARCH WORKFLOW SCENE CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)

