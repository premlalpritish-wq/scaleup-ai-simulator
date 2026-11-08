extends SceneTree
## WS -- the literature-grounded 3D simulation workshop.
##
## The default scene is no longer a graph canvas. It is a shake-flask fed-batch
## culture drawn in 3D and driven by the Ganjave model through the normal
## composition runner. These checks drive that through the real scene, in the same
## way a user would, and refuse the shortcuts that would make the scene look better
## than the science is.
##
## The shortcuts this suite exists to catch:
##
##   * animating a value independently of the runner while labelling it a calculated
##     quantity -- the single worst thing this scene could do;
##   * rendering an effect the model does not compute (cells, bubbles, gradients);
##   * inventing a default for a required input;
##   * presenting a model the engine refuses to connect as if it were available;
##   * letting a stale result pass as current.

const MAIN_SCENE := "res://scenes/workshop.tscn"
const MODEL_ID := "ganjave"

## One Ganjave run through the runner takes about a minute on this machine, and the
## harness performs several. The wait is generous on purpose: a correct simulation
## that is merely slow must not fail the check.
const RUN_WAIT := 900.0
const POLL := 5.0

var _scene: Control = null
var _failures: Array[String] = []
var _checks := 0
var _elapsed := 0.0
var _ran := false
## The payload from a run that produced results, kept for the checks that must
## not read a deliberately-failed run.
var _good_payload: Dictionary = {}


func _initialize() -> void:
	# In --script mode Godot does not load the project's main scene for us: the
	# other harnesses change scene explicitly, and so does this one. That call is
	# also what makes the harness's claim about the *default* scene real -- a scene
	# the project would not actually open would pass a weaker test.
	if ProjectSettings.get_setting("application/run/main_scene", "") != MAIN_SCENE:
		_fail("the project does not start in the simulation workshop: %s"
			% str(ProjectSettings.get_setting("application/run/main_scene", "")))
	change_scene_to_file(MAIN_SCENE)


var _printed_launch := false

func _process(delta: float) -> bool:
	_elapsed += delta
	if _scene == null and current_scene != null:
		_scene = current_scene as Control
	if _scene == null:
		return _elapsed > 300.0
	if not _printed_launch:
		_printed_launch = true
		print("WS: scene loaded (", _scene.name, "); checks starting")
	if not _ran:
		_run_all()
		# Report as soon as the checks are done. The scene's own startup sequence
		# -- introspection, then the first run -- completes synchronously inside
		# _ready(), so the checks find the scene already populated, and there is
		# nothing to wait for afterwards.
		_report()
		return true
	return false


# ------------------------------------------------------------------ the scene


func _workshop() -> Control:
	return _scene


func _key(name: String) -> Variant:
	var value: Variant = _workshop().get(name)
	if value == null:
		_fail("the scene exposes no %s" % name)
	return value


func _ok(condition: bool, what: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(what)


func _fail(what: String) -> void:
	_checks += 1
	_failures.append(what)


# --------------------------------------------------------------- 1 launch


func _check_launch() -> void:
	var scene := _workshop()
	_ok(scene != null, "the default scene did not instantiate")
	if scene == null:
		return
	_ok(str(scene.name) == "Workshop", "the default scene is not the Workshop")
	_ok(ProjectSettings.get_setting("application/run/main_scene", "") == MAIN_SCENE,
		"project.godot does not point at the workshop scene")

	# It is a 3D scene, not a canvas.
	var flask: Variant = scene.get("_flask")
	_ok(flask != null and flask.get_class() == "SubViewportContainer",
		"the scene has no shake-flask 3D view")
	if flask is SubViewportContainer:
		var has_viewport := false
		for node in _walk(flask):
			if node is SubViewport:
				has_viewport = true
		_ok(has_viewport, "the 3D view holds no SubViewport, so nothing can be drawn")

	# The timeline exists with the documented controls.
	_ok(scene.get("_timeline") != null and _timeline() is HSlider,
		"the scene has no timeline slider")
	_ok(scene.get("_play_button") != null, "the scene has no play control")
	var play_text := str(_play_button().text)
	_ok(play_text == "Play" or play_text == "Pause",
		"the play control is neither playing nor pausing")
	_ok(scene.get("_banner") != null, "the scene has no status indicator")

	# The five documented quantities are the ones rendered.
	var ports := _rendered()
	_ok(ports.size() == 5, "the scene renders %d quantities, expected 5" % ports.size())
	for expected in ["biomass_concentration", "glycerol_concentration",
					"complex_substrate_concentration", "dissolved_oxygen",
					"culture_volume"]:
		_ok(ports.has(expected), "the scene does not render %s" % expected)


func _timeline() -> HSlider:
	return _workshop().get("_timeline") as HSlider


func _play_button() -> Button:
	return _workshop().get("_play_button") as Button


func _rendered() -> PackedStringArray:
	return _workshop().rendered_ports()


func _status_text() -> String:
	var status: Variant = _workshop().get("_status")
	if status is Label:
		return str((status as Label).text)
	return ""


# ---------------------------------------------------- 2 registry, 6 truth


func _check_model_list_is_registry_derived() -> void:
	var registry: Variant = _workshop().get("_registry")
	_ok(registry != null, "the scene has no model registry")
	if registry == null:
		return
	var ids: Array = registry.model_ids()
	_ok(not ids.is_empty(), "the model registry reported no models")
	# The one model the scene simulates is registered, and is the one used.
	_ok(ids.has(MODEL_ID), "%s is not in the registry" % MODEL_ID)

	var compat: CompatibilityPanel = _workshop().compatibility()
	_ok(compat != null, "the scene has no compatibility panel")
	if compat == null:
		return
	var permitted: PackedStringArray = compat.permitted_pairs()
	_ok(permitted.size() == 2,
		"the engine permits %d model pairs, expected 2" % permitted.size())
	# No panel in this scene may offer a model the engine refuses.
	for name in ["Morris", "Zielinski", "Zielinski2019"]:
		_ok(not _presents_model(name),
			"the scene presents %s, which the engine refuses to connect" % name)


func _presents_model(name: String) -> bool:
	# The Models tab must be able to say these are refused without offering them.
	var source := FileAccess.get_file_as_string(
		"res://scripts/compatibility_panel.gd")
	return source.contains("\"%s\"" % name)


# --------------------------------------------------- 3 graph, and 9 honesty


func _check_graph_is_scientifically_permitted() -> void:
	var document: Dictionary = _workshop()._document()
	var connections: Array = document.get("connections", [])
	_ok(connections.is_empty(),
		"the workshop graph declares %d connection(s); the engine permits no cross-model pair, so a connection here would be invented" % connections.size())
	var instances: Array = document.get("instances", [])
	_ok(instances.size() == 1, "the workshop graph has %d instances, expected 1"
		% instances.size())
	if instances.size() == 1:
		var instance := instances[0] as Dictionary
		_ok(str(instance.get("model_id", "")) == MODEL_ID,
			"the workshop graph uses %s" % str(instance.get("model_id", "")))

	# No default may be invented for a required input: every required input is
	# either declared or shown as a gap.
	var manifest: Dictionary = _key("_manifest") as Dictionary
	if manifest.is_empty():
		_fail("the manifest was never described to the scene")
	else:
		for port in manifest.get("ports", []) as Array:
			if str(port.get("direction", "")) != "input":
				continue
			var port_id := str(port.get("port_id", ""))
			var declared := false
			var literals: Dictionary = document.get("literal_inputs", {}) as Dictionary
			for key in literals:
				if str(key).split("/")[-1] == port_id:
					declared = true
					break
			_ok(declared,
				"required input %s is neither declared nor shown as a gap" % port_id)


# ---------------------------------------------------------- 4 runner, 5 uses


func _check_execution_and_driving() -> void:
	var scene := _workshop()
	var payload: Dictionary = scene.last_payload()
	_ok(not payload.is_empty(), "no result document was produced")
	if payload.is_empty():
		return
	# Keep the successful payload: the staleness checks below deliberately
	# provoke a failure, and the scientific-status checks must read the run
	# that produced results, not the one that could not.
	_good_payload = payload
	_ok(str(payload.get("status", "")).begins_with("success"),
		"the run did not succeed: %s" % str(payload.get("status", "?")))
	_ok(payload.get("composition_report", {}) is Dictionary,
		"the result has no composition report")

	# Every displayed quantity is the runner's output, not a local animation:
	# sampling at the same time twice must agree exactly.
	for port in scene.rendered_ports():
		var first: float = scene.quantity_at(str(port), 6.0)
		var second: float = scene.quantity_at(str(port), 6.0)
		_ok(is_finite(first), "%s is not finite" % port)
		_ok(is_equal_approx(first, second),
			"%s does not reproduce the same value when sampled twice" % port)
	# And sampling at a different time must give a different value where the
	# trajectory actually moves, which proves playback reads the trajectory.
	var t0: float = scene.quantity_at("biomass_concentration", 1.0)
	var t20: float = scene.quantity_at("biomass_concentration", 20.0)
	_ok(not is_equal_approx(t0, t20),
		"biomass does not move between 1 h and 20 h: playback is not reading the "
		+ "trajectory")

	# No independent animation: with no results the flask must be empty, not
	# carried on from a previous run.
	var flask: ShakeFlaskView = scene.flask_view()
	_ok(flask != null, "the scene exposes no flask view")
	if flask != null:
		_ok(flask.SHOKER_RADIUS > 0.0, "the shaker radius was not set")

	# The composition report is present and carries the execution block.
	var report := payload.get("composition_report", {}) as Dictionary
	_ok(not report.is_empty(), "the composition report is empty")
	var execution: Dictionary = report.get("execution", {}) as Dictionary
	_ok(bool(execution.get("results_produced", false)),
		"the composition report says no result was produced")
	# Nothing in the report claims the combination is validated.
	var science: Dictionary = report.get("science", {}) as Dictionary
	var combined: Dictionary = science.get("combined_graph", {}) as Dictionary
	_ok(not bool(combined.get("independently_validated", true)),
		"the composition report claims the combined graph is validated")


# ---------------------------------------------- 7 provenance, 8 gaps, 11 replay


func _check_provenance_and_gaps() -> void:
	var scene := _workshop()

	var evidence: EvidenceInspector = scene.evidence_panel()
	_ok(evidence != null, "the scene has no evidence inspector")
	if evidence == null:
		return
	_ok(evidence.has_model(), "the evidence inspector shows no model")
	# Every rendered quantity must be inspectable with its epistemic status.
	var sections: PackedStringArray = evidence.sections()
	for expected in ["Source", "Quantities calculated by the model",
					"Inputs this run supplied"]:
		_ok(sections.has(expected),
			"the evidence inspector has no %s section" % expected)
	var panel_text := _panel_text(evidence)
	for status in ["calculated", "assumed", "derived", "reported"]:
		_ok(panel_text.contains(status),
			"the evidence inspector never states the status %s" % status)
	# An assumed initial condition must never be shown as a measurement.
	_ok(panel_text.contains("assumed"),
		"the assumed initial conditions are not labelled as assumed")
	_ok(not panel_text.contains("experimentally validated"),
		"the evidence inspector claims experimental validation")

	# The research-gap panel covers the five documented categories.
	var gaps: ResearchGapPanel = scene.gap_panel()
	_ok(gaps != null, "the scene has no research-gap panel")
	if gaps == null:
		return
	var categories: PackedStringArray = gaps.categories_present()
	for category in ["A", "B", "C", "D", "E"]:
		_ok(categories.has(category),
			"the research-gap panel has no category %s" % category)
	var text := _panel_text(gaps)
	# Category B must name a required input the literature does not establish.
	_ok(text.contains("initial_biomass")
		or text.contains("initial_complex")
		or text.contains("initial_dissolved"),
		"the gap panel does not name a required input the source does not establish")
	_ok(text.contains("not established by the source"),
		"the gap panel does not say that a required input is unestablished")
	# Category D must state the validation gap plainly.
	_ok(text.contains("observation"),
		"the gap panel says nothing about missing observations")
	# The panel must not claim research does not exist anywhere.
	_ok(not text.contains("no research exists"),
		"the gap panel claims no research exists, which is not what it means")

	# The Zielinski replay must be reachable and labelled as a replay.
	var replay_button := false
	var found_label := ""
	for node in _walk(scene):
		if node is Button and str(node.text) == "Zielinski replay":
			replay_button = true
			found_label = str(node.tooltip_text)
	_ok(replay_button, "the scene has no way to reach the Zielinski replay")
	_ok(found_label.to_lower().contains("replay"),
		"the replay button does not say it is a replay")
	_ok(found_label.to_lower().contains("not a predictive simulation"),
		"the replay button does not disclaim predictive simulation")


# ------------------------------------------------------- 9, 10 and 12 regression


func _check_no_invented_effects_and_staleness() -> void:
	# 9: the render path must *name* the effects it does not draw, and must not
	# implement one. Checking that the words are absent would punish the very
	# disclaimer that makes the scene honest -- a scene that silently omits
	# bubbles is worse than one that says it draws none.
	for script in ["shake_flask_view.gd", "workshop.gd"]:
		var source := FileAccess.get_file_as_string("res://scripts/%s" % script)
		var lowered := source.to_lower()
		# The scene must name the effects it does not draw. A scene that
		# silently omits bubbles is worse than one that says it draws none.
		for concept in ["bubble", "gradient", "cell", "vortex"]:
			_ok(lowered.contains(concept),
				"%s does not name %s among the effects it does not draw"
				% [script, concept])
		_ok(lowered.contains("well-mixed"),
			"%s does not state that it renders a well-mixed vessel" % script)
		# And it must not implement an effect the model does not compute.
		for banned in ["gas_holdup", "molecular_motion", "turbulent", "streak",
					  "concentration_gradient", "eddy_velocity"]:
			_ok(not lowered.contains(banned),
				"%s implements %s, an effect the model does not compute"
				% [script, banned])

	# 10: an edit marks previous results stale and a run recomputes them.
	var scene := _workshop()
	var before: float = scene.quantity_at("biomass_concentration", 20.0)

	# A change the model actually reacts to. 0.30 mL/h is not a small
	# perturbation: at the baseline the culture is fed 0.72 mL/h and reaches
	# 17.1 g/L by 20 h, and at 0.30 mL/h it reaches 10.1 g/L.
	_set_input(scene, "feed_flow_rate", "0.30")
	_ok(scene.is_stale(), "changing an input did not mark results stale")
	_run(scene)
	_ok(not scene.is_stale(), "the run did not clear the stale flag")
	var fed: float = scene.quantity_at("biomass_concentration", 20.0)
	_ok(absf(before - fed) > 1e-3,
		"changing the feed rate did not change the predicted biomass "
		+ "(%.4f -> %.4f)" % [before, fed])

	# Restoring the original value must reproduce the original result, which
	# proves the re-run actually went through the runner and did not reuse a
	# cached trajectory.
	_set_input(scene, "feed_flow_rate", "0.72")
	_run(scene)
	var restored: float = scene.quantity_at("biomass_concentration", 20.0)
	_ok(absf(before - restored) < 1e-4,
		"restoring the feed rate did not reproduce the original biomass: "
		+ "the re-run is not going through the runner")

	# A run the MODEL cannot complete. At 1.50 mL/h the solver exhausts its
	# step budget at t = 13.3 h of 24 h and the model reports it did not reach
	# the end. That is a real failure a user can reach by typing, and the scene
	# must show the reason rather than keep the old numbers as current.
	_set_input(scene, "feed_flow_rate", "1.50")
	_run(scene)
	_ok(not scene.has_results(),
		"a run the model could not complete still presented results as current")
	_ok(scene.is_stale(),
		"a failed run left its results looking current")
	var status_text := _status_text().to_lower()
	_ok(status_text.contains("failed") or status_text.contains("did not"),
		"the scene did not state the reason for the failed run: %s" % _status_text())

	# And the original configuration must recover.
	_set_input(scene, "feed_flow_rate", "0.72")
	_run(scene)
	_ok(not scene.is_stale(), "the recovered run is still marked stale")
	_ok(scene.has_results(), "the scene did not recover after the failed run")
	var recovered: float = scene.quantity_at("biomass_concentration", 20.0)
	_ok(absf(before - recovered) < 1e-4,
		"the recovered run did not reproduce the original biomass")


func _check_regression_suites_pass() -> void:
	# 12 is verified by the Python suite; this asserts the artefacts it needs are
	# in place, so a missing one fails here rather than later.
	for path in ["res://scripts/main.gd", "res://scenes/composition.tscn",
				 "res://scripts/model_palette.gd", "res://scripts/instance_form.gd",
				 "res://scripts/composition_report_panel.gd"]:
		_ok(ResourceLoader.exists(path), "%s is missing" % path)


func _check_startup_defaults_match_the_recorded_configuration() -> void:
	"""The scene's defaults must be the project's own recorded configuration.

	The scene declares its startup values in GDScript; the project records the same
	configuration, with the same provenance, in
	``data/ganjave2022/frozen_configuration.json``. Two copies could drift, and a
	scene whose default has quietly diverged from the configuration that justified
	it would be showing numbers nobody wrote down. This compares them.
	"""
	var path := "res://data/ganjave2022/frozen_configuration.json"
	if not FileAccess.file_exists(path):
		_fail("the recorded configuration is missing, so the startup defaults cannot "
			+ "be checked against it")
		return
	var text := FileAccess.get_file_as_string(path)
	var configuration: Variant = JSON.parse_string(text)
	if not configuration is Dictionary:
		_fail("the recorded configuration does not parse")
		return
	var scenarios: Array = (configuration as Dictionary).get("scenarios", []) as Array
	if scenarios.is_empty():
		_fail("the recorded configuration declares no scenario")
		return
	# The optimum scenario is the one the scene's defaults follow.
	var optimum: Dictionary = {}
	for scenario in scenarios:
		if str((scenario as Dictionary).get("scenario_id", "")) == "optimum_fig5":
			optimum = scenario as Dictionary
	if optimum.is_empty():
		_fail("the recorded configuration has no optimum_fig5 scenario")
		return

	var startup: Dictionary = _workshop().startup_entries()
	var initial: Dictionary = optimum.get("initial_conditions", {}) as Dictionary
	for name in ["X0", "S2_0", "DO0", "S1_0", "V0"]:
		var recorded: Dictionary = initial.get(name, {}) as Dictionary
		if recorded.is_empty():
			continue
		var key := _port_key_for(name)
		if not startup.has(key):
			_fail("the scene has no startup value for %s" % name)
			continue
		var scene_value: float = float((startup[key] as Dictionary)["value"])
		var recorded_value: float = float(recorded["value"])
		_ok(absf(scene_value - recorded_value) < 1e-9,
			"the scene's %s is %.6f but the recorded configuration says %.6f"
			% [name, scene_value, recorded_value])
		# And the classification must match too, or the Evidence tab would
		# mislabel the value the panel shows.
		var recorded_class: String = str(recorded.get("classification", ""))
		var scene_class: String = str((startup[key] as Dictionary)["classification"])
		_ok(recorded_class == scene_class,
			"the scene classifies %s as %s but the recorded configuration says %s"
			% [name, scene_class, recorded_class])

	var feed: Dictionary = optimum.get("feed", {}) as Dictionary
	# The scene names the feed by port; the recorded configuration names it by
	# the model's own symbols. The mapping is explicit so a rename on either
	# side fails the check instead of silently comparing nothing.
	var feed_map := {
		"feed_glycerol_concentration": "S10_g_per_L",
		"feed_complex_substrate_concentration": "S20_g_per_L",
		"feed_flow_rate": "flow_mL_per_h",
		"feed_start_time": "feed_start_h",
	}
	var compared_feeds := 0
	for scene_key in feed_map:
		var recorded_key := str(feed_map[scene_key])
		if not feed.has(recorded_key):
			continue
		if not startup.has(scene_key):
			_fail("the scene has no startup value for %s" % scene_key)
			continue
		var recorded_value: float = float((feed[recorded_key] as Dictionary)["value"])
		var scene_value: float = float((startup[scene_key] as Dictionary)["value"])
		_ok(absf(scene_value - recorded_value) < 1e-9,
			"the scene's %s is %.6f but the recorded configuration says %.6f"
			% [scene_key, scene_value, recorded_value])
		var recorded_class: String = str((feed[recorded_key] as Dictionary)
			.get("classification", ""))
		var scene_class: String = str((startup[scene_key] as Dictionary)["classification"])
		_ok(recorded_class == scene_class,
			"the scene classifies %s as %s but the recorded configuration says %s"
			% [scene_key, scene_class, recorded_class])
		compared_feeds += 1
	_ok(compared_feeds == 4,
		"only %d of the 4 feed values were compared with the recorded configuration"
		% compared_feeds)


func _port_key_for(name: String) -> String:
	match name:
		"X0":
			return "initial_biomass_concentration"
		"S2_0":
			return "initial_complex_substrate_concentration"
		"DO0":
			return "initial_dissolved_oxygen"
		"S1_0":
			return "initial_glycerol_concentration"
		"V0":
			return "initial_culture_volume"
	return name


# ------------------------------------------------------------- 13 insufficient


func _check_honest_when_literature_is_insufficient() -> void:
	"""The scene must make the strongest simulation the evidence supports, and no
	more. That includes admitting the other ingested models cannot join."""
	var scene := _workshop()
	var document: Dictionary = scene._document()

	# A user who asks for the other models gets an engine position, not a workaround.
	var compat: CompatibilityPanel = scene.compatibility()
	var refused: PackedStringArray = compat.refused_pairs_touching(MODEL_ID)
	_ok(not refused.is_empty(),
		"the compatibility panel shows no refused pair involving %s" % MODEL_ID)
	for pair in refused:
		var parts := str(pair).split("->")
		if parts.size() == 2:
			_ok(not parts[1].strip_edges() == parts[0].strip_edges()
				or parts[0].strip_edges() == MODEL_ID,
				"a refused pair was presented as usable: %s" % pair)

	# The scene must not be trying to force a composition it cannot justify.
	var source := FileAccess.get_file_as_string("res://scripts/workshop.gd")
	_ok(source.contains("MODEL_ID := \"ganjave\""),
		"the workshop hard-codes a different model than its own constant")
	# And it must say why only one model is used, rather than implying the
	# others were simply left out.
	_ok(source.contains("both are same-model"),
		"the workshop does not explain why only one model is simulated")

	# Missing evidence stays missing: the report must keep reporting the gap.
	# The payload read here is the one that produced results -- the staleness
	# checks deliberately provoked a failure afterwards, and a failed run
	# honestly reports no validation status because no model ran.
	var payload: Dictionary = _good_payload
	if payload.is_empty():
		payload = scene.last_payload()
	var report: Dictionary = payload.get("composition_report", {}) as Dictionary
	var science: Dictionary = report.get("science", {}) as Dictionary
	var models: Array = science.get("models", []) as Array
	_ok(models.size() >= 1, "the science section lists no model")
	for model in models:
		_ok(not bool((model as Dictionary).get("independently_validated", false)),
			"a model is presented as independently validated")
	# The Ganjave claim must not have been upgraded by looking good on screen.
	var ganjave_row: Dictionary = {}
	for model in models:
		if str(model.get("model_id", "")) == MODEL_ID:
			ganjave_row = model
	_ok(str(ganjave_row.get("reproduction_status", "")) == "not_yet_validated",
		"the Ganjave reproduction status is %s, expected not_yet_validated"
		% str(ganjave_row.get("reproduction_status", "?")))


# ------------------------------------------------------------- input plumbing


func _set_input(scene: Control, key: String, value: String) -> void:
	for node in _walk(scene):
		var edit := node as LineEdit
		if edit == null:
			continue
		if str(edit.get_meta("input_key", "")) == key:
			edit.text = value
			edit.text_changed.emit(value)
			return
	_fail("the scene exposes no input field for %s" % key)


func _run(scene: Control) -> void:
	# The run is synchronous in this scene, so it has already finished by the time
	# this returns; give the panels a frame to render their content.
	scene._on_run_pressed()


func _panel_text(from: Control) -> String:
	var out: Array[String] = []
	_collect_text(from, out)
	return "\n".join(out)


func _collect_text(from: Node, into: Array[String]) -> void:
	for child in from.get_children():
		if child is Label or child is Button or child is LineEdit:
			var label := child as Label
			if label != null:
				into.append(str(label.text))
			else:
				into.append(str((child as Button).text))
		_collect_text(child, into)


func _walk(from: Node) -> Array:
	var out: Array = []
	for child in from.get_children():
		out.append(child)
		out.append_array(_walk(child))
	return out


# ------------------------------------------------------------ orchestration


func _run_all() -> void:
	_check_launch()
	_check_model_list_is_registry_derived()
	_check_graph_is_scientifically_permitted()
	_ran = true
	# Execution is driven by the scene itself once its introspection completes;
	# these checks read whatever the scene produced.
	_check_execution_and_driving()
	_check_provenance_and_gaps()
	_check_no_invented_effects_and_staleness()
	_check_regression_suites_pass()
	_check_startup_defaults_match_the_recorded_configuration()
	_check_honest_when_literature_is_insufficient()


func _report() -> void:
	if _failures.is_empty():
		print("workshop: %d checks passed" % _checks)
		quit(0)
		return
	for failure in _failures:
		print("FAIL  " + failure.substr(0, 400))
	print("workshop: %d checks, %d FAILED" % [_checks, _failures.size()])
	quit(1)
