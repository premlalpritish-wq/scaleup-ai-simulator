extends SceneTree
## End-to-end Godot → Python prompt workflow checks.

var _checks := 0
var _failures: Array[String] = []
var _frames := 0
var _ran := false


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		print("FAIL: ", message)


func _initialize() -> void:
	change_scene_to_file("res://scenes/prompt_simulation.tscn")


func _process(_delta: float) -> bool:
	if _ran:
		return true
	if current_scene == null:
		return false
	_frames += 1
	if _frames < 3:
		return false
	_ran = true
	var scene := current_scene
	_check(scene != null, "the prompt scene loads")
	if scene == null:
		_finish()
		return true

	var prompt_edit: TextEdit = scene.get("_prompt")
	_check(prompt_edit != null, "the prompt text box exists")
	_check(scene.get("_generate") != null, "the Generate Simulation button exists")
	_check(scene.get("_execute") != null, "the Run validated configuration button exists")
	_check(scene.get("_view") != null, "the existing 3D replay view is embedded")
	_check(scene.get("_growth") != null, "the existing growth chart is embedded")

	# 0. The workspace is idle on load: both prompt actions must be clickable,
	# and only the validated-configuration action starts disabled.
	var generate_button: Button = scene.get("_generate")
	var interpret_button: Button = scene.get("_interpret_only")
	var execute_button: Button = scene.get("_execute")
	_check(not generate_button.disabled, "Generate simulation is enabled on an idle workspace")
	_check(not interpret_button.disabled, "Interpret only is enabled on an idle workspace")
	_check(execute_button.disabled, "Run validated configuration starts disabled")

	# 1. Supported natural-language run.
	prompt_edit.text = (
		"Simulate the Zielinski insulin production process for 19 hours and show "
		+ "OD600, wet biomass, inclusion bodies and insulin activity."
	)
	scene.call("_on_generate_pressed")
	var interpretation: Dictionary = scene.get("_interpretation")
	var result: Dictionary = scene.get("_result")
	_check(bool(interpretation.get("ok", false)), "the supported prompt is interpreted")
	_check(str(interpretation.get("selected_model", {}).get("model_id", "")) == "zielinski2019.rhi_process", "the interpreter selects Zielinski")
	var output_keys: Array = []
	for output in interpretation.get("requested_outputs", []):
		output_keys.append(str(output.get("key", "")))
	_check("od600" in output_keys, "OD600 maps to a requested output")
	_check("wet_biomass" in output_keys, "wet biomass maps to a requested output")
	_check("inclusion_bodies" in output_keys, "inclusion bodies map to a requested output")
	_check("activity" in output_keys, "activity maps to a requested output")
	_check(result.has("results"), "the runner returns a result document")
	_check(result.has("prompt_effect"), "the result reports the baseline comparison")
	_check(str(result.get("status", "")) != "invalid", "the supported prompt executes")
	var data: ReplayData = scene.get("_data")
	_check(data != null and data.hours.size() == 19, "the existing replay trajectory is loaded")
	_check(scene.get("_output_tree").get_root() != null, "requested outputs are displayed")
	var effect: Dictionary = result.get("prompt_effect", {})
	_check(bool(effect.get("identical", false)), "the default prompt leaves the original replay numerically unchanged")

	# 2. Supported parameter change through natural language.
	prompt_edit.text = "Increase the starting medium volume to 8 L and show wet biomass and insulin activity."
	scene.call("_on_generate_pressed")
	interpretation = scene.get("_interpretation")
	result = scene.get("_result")
	var parameters: Array = interpretation.get("requested_parameters", [])
	_check(parameters.size() == 1, "one supported parameter change is interpreted")
	if parameters.size() == 1:
		_check(str(parameters[0].get("port_id", "")) == "node:N01#starting_medium_volume", "the parameter maps to the real port")
		_check(is_equal_approx(float(parameters[0].get("value", 0.0)), 8.0), "the parameter value is parsed")
	_check(result.has("prompt_interpretation"), "the executed result carries its interpretation")
	effect = result.get("prompt_effect", {})
	_check(int(effect.get("parameter_change_count", 0)) == 1, "the effect report sees the parameter change")
	_check(bool(effect.get("published_outputs_changed", false)), "the parameter change updates the configured simulation outputs")
	_check("node:N02#wet_biomass_g_per_L" in effect.get("requested_differences", []), "the changed wet-biomass output is named")

	# 3. Missing duration triggers clarification, not execution.
	prompt_edit.text = "Simulate 48 hours of the insulin process."
	scene.call("_on_generate_pressed")
	interpretation = scene.get("_interpretation")
	_check(str(interpretation.get("status", "")) == "needs_clarification", "48 h is rejected as outside the published trajectory")
	_check(str(interpretation.get("clarification", [{}])[0].get("code", "")) == "duration_not_available", "the clarification names the duration gap")
	_check((scene.get("_result") as Dictionary).is_empty(), "a clarification clears the old result and executes nothing")

	# 4. Unsupported process is rejected.
	prompt_edit.text = "Simulate CHO cell insulin production for 48 hours."
	scene.call("_on_generate_pressed")
	interpretation = scene.get("_interpretation")
	_check(str(interpretation.get("status", "")) == "rejected", "CHO insulin production is rejected")
	_check(str(interpretation.get("clarification", [{}])[0].get("code", "")) == "process_not_supported", "the rejection names the unsupported process")
	_check(not generate_button.disabled, "Generate simulation recovers after a rejection")
	_check(not interpret_button.disabled, "Interpret only recovers after a rejection")

	# 5. Interpret only interprets but executes nothing.
	prompt_edit.text = (
		"Simulate the Zielinski insulin production process for 19 hours and show "
		+ "OD600, wet biomass, inclusion bodies and insulin activity."
	)
	scene.call("_on_interpret_pressed")
	interpretation = scene.get("_interpretation")
	_check(bool(interpretation.get("ok", false)), "Interpret only produces a validated interpretation")
	_check((scene.get("_result") as Dictionary).is_empty(), "Interpret only executes no simulation")
	_check(scene.get("_data") == null, "Interpret only leaves the replay surface empty")
	_check(not generate_button.disabled, "Generate simulation recovers after interpretation")
	_check(not interpret_button.disabled, "Interpret only recovers after interpretation")

	# 6. An empty prompt is answered with a clarification and leaves the actions usable.
	prompt_edit.text = ""
	scene.call("_on_interpret_pressed")
	var status_label: Label = scene.get("_status")
	_check(status_label != null and status_label.text.contains("Enter a prompt"),
		"an empty prompt asks for input instead of failing silently")
	_check(not generate_button.disabled, "Generate simulation stays enabled after an empty prompt")
	_check(not interpret_button.disabled, "Interpret only stays enabled after an empty prompt")
	_finish()
	return true


func _finish() -> void:
	print("\nPROMPT SIMULATION CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)
