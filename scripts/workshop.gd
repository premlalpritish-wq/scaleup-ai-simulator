extends Control
## The default scene: an interactive 3D simulation workshop.
##
## ## What this is
##
## A shake-flask fed-batch culture, drawn in 3D and driven by quantities the
## composition runner actually computed. The user can change supported inputs, re-run
## through the normal runner, scrub the resulting trajectory, and inspect the evidence,
## the assumptions, and the research gaps behind every number on screen.
##
## ## Which model drives it, and why only one
##
## Ganjave. It is the only registered model that produces a time course of biological
## quantities -- biomass, substrate, dissolved oxygen, volume -- over a real operating
## range. Morris is a non-reacting control-volume balance; Zielinski is an evidence
## replay whose inputs are transcribed measurements and whose outputs are
## recomputations, not predictions.
##
## The compatibility engine permits two ordered pairs and **both are same-model**, so
## no cross-model composition is scientifically available to show. The scene says so
## in the Models tab rather than quietly using one model and letting the user assume
## the rest were combined. The Ganjave -> Ganjave forward cascade is permitted but has
## no experimental counterpart in the source, and this scene does not draw one.
##
## ## The rule about animation
##
## Nothing on screen is animated independently of the runner. The timeline reads a
## dense trajectory the runner produced and interpolates within it. When no results
## exist the flask is shown empty and says so; it does not continue moving.
##
## ## Startup configuration
##
## Defaults are declared below with the provenance of each, taken from the project's
## own recorded evaluation configuration. An acceptance test cross-checks every one
## of them against `data/ganjave2022/frozen_configuration.json`, so a default cannot
## drift away from the configuration that justified it.

const GRAPH_DIR := "user://workshop_graphs"
const RESULT_DIR := "user://workshop_results"

const MODEL_ID := "ganjave"
const MODEL_VERSION := "0.1.0"
const INSTANCE_ID := "workshop_culture"

## Reported: 500 mL PreSens baffled flask, 200 rpm, 5 cm pitch, 100 mL fill (1:5).
const FLASK_SHAKE_RPM := 200.0
const SYRINGE_ML := 20.0

## The scene's colour scale for biomass. Stated so the legend means something: the
## top of the range is the biomass this project's own evaluation recorded at the
## selected optimum, not a round number chosen for looks.
const BIOMASS_SCALE_G_PER_L := 22.0

## Startup values, each with the provenance of the source that established it.
## `classification` is shown in the Evidence tab; it is never silently upgraded.
##
## `var`, not `const`: a run refreshes the entries from the editable fields, which is
## how a user's change reaches the graph document.
var STARTUP := {
	"initial_glycerol_concentration": {
		"value": 2.76, "unit": "g/L", "classification": "reported",
		"locator": "Ganjave et al. 2022, sec. 2.2, printed p. 2",
		"note": "'The initial production medium was supplemented with 2.76 g/L glycerol'"},
	"initial_culture_volume": {
		"value": 0.1, "unit": "L", "classification": "reported",
		"locator": "Ganjave et al. 2022, sec. 2.3, printed p. 2",
		"note": "'These flasks were filled with 100 mL medium'"},
	"initial_biomass_concentration": {
		"value": 0.05, "unit": "g/L", "classification": "assumed",
		"locator": "printed p. 2, sec. 2.2: initial OD600 of 0.05",
		"note": "The paper prints an OD600 and no OD600-to-dry-cell-weight "
			+ "calibration, so this g/L value is an assumption, not a paper value."},
	"initial_complex_substrate_concentration": {
		"value": 25.0, "unit": "g/L", "classification": "derived",
		"locator": "printed p. 2, sec. 2.2: SOB is tryptone 20 g/L + yeast extract 5 g/L",
		"note": "Derived from the stated medium recipe. The paper never states the "
			+ "model's S2 input, and the outcome depends strongly on this value."},
	"initial_dissolved_oxygen": {
		"value": 100.0, "unit": "%", "classification": "assumed",
		"locator": "not stated in the paper",
		"note": "An air-saturated shake flask. The culture's own demand, not the "
			+ "starting value, sets the profile."},
	"feed_glycerol_concentration": {
		"value": 175.0, "unit": "g/L", "classification": "reported",
		"locator": "printed p. 7, sec. 3.3 and Fig. 5 caption: 17.5% glycerol",
		"note": "At the paper's own 1 % w/v = 10 g/L convention."},
	"feed_complex_substrate_concentration": {
		"value": 245.0, "unit": "g/L", "classification": "reported",
		"locator": "printed p. 7, sec. 3.3 and Fig. 5 caption: 24.5% yeast extract",
		"note": "At the paper's own 1 % w/v = 10 g/L convention."},
	"feed_flow_rate": {
		"value": 0.72, "unit": "mL/h", "classification": "reported",
		"locator": "printed p. 7, sec. 3.3: 0.72 mL/h",
		"note": "Volumetric. A mass rate would need a feed density the paper does "
			+ "not state."},
	"feed_start_time": {
		"value": 6.0, "unit": "h", "classification": "reported",
		"locator": "printed p. 3, sec. 3.1",
		"note": "Feeding begins at 6 h, the dissolved-oxygen landmark."},
}

const EDITABLE := [
	{"key": "feed_flow_rate", "label": "Feed rate", "unit": "mL/h",
	 "low": 0.0, "high": 2.0},
	{"key": "feed_glycerol_concentration", "label": "Feed glycerol", "unit": "g/L",
	 "low": 0.0, "high": 400.0},
	{"key": "feed_complex_substrate_concentration", "label": "Feed yeast extract",
	 "unit": "g/L", "low": 0.0, "high": 400.0},
	{"key": "initial_biomass_concentration", "label": "Initial biomass X0", "unit": "g/L",
	 "low": 0.0, "high": 1.0},
	{"key": "initial_complex_substrate_concentration", "label": "Initial complex S2_0",
	 "unit": "g/L", "low": 0.0, "high": 60.0},
	{"key": "initial_dissolved_oxygen", "label": "Initial DO", "unit": "%",
	 "low": 0.0, "high": 100.0},
	{"key": "feed_start_time", "label": "Feed start", "unit": "h",
	 "low": 0.0, "high": 12.0},
]

## The five quantities the runner publishes that this scene may render.
const RENDERED := [
	{"port": "biomass_concentration", "label": "Biomass", "unit": "g/L",
	 "epistemic": "calculated"},
	{"port": "glycerol_concentration", "label": "Glycerol", "unit": "g/L",
	 "epistemic": "calculated"},
	{"port": "complex_substrate_concentration", "label": "Complex substrate", "unit": "g/L",
	 "epistemic": "calculated"},
	{"port": "dissolved_oxygen", "label": "Dissolved oxygen", "unit": "%",
	 "epistemic": "calculated"},
	{"port": "culture_volume", "label": "Culture volume", "unit": "L",
	 "epistemic": "calculated"},
]

var _python_path := "python"
var _composition_dir := ""
var _runner: CompositionRunner
var _registry: ModelRegistry
var _form: InstanceForm

var _flask: ShakeFlaskView
var _evidence: EvidenceInspector
var _gaps: ResearchGapPanel
var _compat: CompatibilityPanel
var _report: CompositionReportPanel

var _status: Label
var _playhead_label: Label
var _readouts: VBoxContainer
var _timeline: HSlider
var _play_button: Button
var _banner: Label

var _manifest: Dictionary = {}
var _contract: Dictionary = {}
var _connections: Dictionary = {}
var _last_payload: Dictionary = {}

## Dense trajectories the runner produced, port_id -> { times, values, unit }.
var _trajectories: Dictionary = {}
var _duration := 24.0
var _playhead := 0.0
var _playing := false
var _play_rate := 1.0
var _stale := false
var _awaiting := ""
var _last_result_path := ""
var _inputs: Dictionary = {}
var _is_replay_mode: bool = false
var _input_fields: Array[LineEdit] = []
var _status_text := "starting"


# --------------------------------------------------------------- environment


func _ready() -> void:
	_detect_environment()
	if OS.get_name() == "Web":
		var scene_param := ""
		if JavaScriptBridge != null:
			scene_param = str(JavaScriptBridge.eval("new URLSearchParams(window.location.search).get('scene') || ''"))
		if scene_param == "replay":
			_is_replay_mode = true
			_load_replay_data()
			return

	_is_replay_mode = false
	_build_ui()
	_runner.finished.connect(_on_runner_finished)

	# Introspection first: the scene states what it is before it shows anything.
	_awaiting = "manifest"
	_runner.describe_model(MODEL_ID)
	_runner.describe_contract()
	_awaiting = "contract"
	_runner.describe_connections()


func _detect_environment() -> void:
	if OS.get_name() == "Web":
		_python_path = "python"
		_composition_dir = ""
		return
	_python_path = "python"
	var base := OS.get_executable_path().get_base_dir()
	for candidate in [base.path_join("../composition"), base.path_join("composition")]:
		var dir := DirAccess.open(candidate)
		if dir != null and dir.file_exists("composition/runner.py"):
			_composition_dir = candidate
			break
	if _composition_dir == "":
		var project_root := ProjectSettings.globalize_path("res://")
		var dir := DirAccess.open(project_root.path_join("composition"))
		if dir != null and dir.file_exists("composition/runner.py"):
			_composition_dir = project_root.path_join("composition")
	if OS.get_name() != "Web" and _composition_dir == "":
		push_error("Could not locate the composition package.")


# ------------------------------------------------------------------- UI


func _build_ui() -> void:
	_runner = CompositionRunner.new(_python_path, _composition_dir)
	add_child(_runner)
	_registry = ModelRegistry.new()
	_registry.setup(_runner)
	add_child(_registry)
	# Discovery is not optional: the scene's claim that it shows a registered
	# model is only meaningful if the registry was actually consulted.
	_registry.load()
	_form = InstanceForm.new()
	_form.setup(_registry)
	add_child(_form)

	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 4)
	add_child(root)

	root.add_child(_header())

	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 6)
	root.add_child(body)

	body.add_child(_viewport_column())
	body.add_child(_panel_column())

	root.add_child(_timeline_bar())

	_status = Label.new()
	_status.text = "starting"
	_status.add_theme_font_size_override("font_size", 10)
	_status.modulate = Color(1, 1, 1, 0.65)
	root.add_child(_status)


func _load_replay_data() -> void:
	# Trigger the existing replay button handler which changes to the replay scene
	_on_replay_pressed()


func _header() -> Control:
	var box := PanelContainer.new()
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	box.add_child(row)

	var title := Label.new()
	title.text = "Shake-flask fed-batch E. coli  --  Ganjave et al. (2022), %s %s" % [
		MODEL_ID, MODEL_VERSION]
	title.add_theme_font_size_override("font_size", 14)
	row.add_child(title)

	var subtitle := Label.new()
	subtitle.text = "one model, no connections"
	subtitle.add_theme_font_size_override("font_size", 11)
	subtitle.modulate = Color(1, 1, 1, 0.55)
	row.add_child(subtitle)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)

	# The replay stays reachable and stays labelled. It is an evidence replay of a
	# published experiment, not a general simulation, and this button says so.
	var replay := Button.new()
	replay.text = "Zielinski replay"
	replay.tooltip_text = ("Opens the Zielinski et al. (2019) evidence replay. That is a "
		+ "predefined experiment whose digitized figure data was transcribed from the "
		+ "paper; it is not a predictive simulation and its values are not computed "
		+ "from these models.")
	replay.pressed.connect(_on_replay_pressed)
	row.add_child(replay)

	var prompt := Button.new()
	prompt.text = "Prompt to simulation"
	prompt.tooltip_text = ("Describe an insulin-production run in words; ScaleUp interprets it "
		+ "against the Zielinski model, validates the configuration and executes it.")
	prompt.pressed.connect(_on_prompt_pressed)
	row.add_child(prompt)

	var run := Button.new()
	run.text = "Run simulation"
	run.pressed.connect(_on_run_pressed)
	row.add_child(run)
	return box


func _viewport_column() -> Control:
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 4)

	_banner = Label.new()
	_banner.text = "no results yet"
	_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_banner.add_theme_font_size_override("font_size", 10)
	_banner.modulate = Color(0.95, 0.82, 0.45)
	box.add_child(_banner)

	_flask = ShakeFlaskView.new()
	_flask.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_flask.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_flask.set_shaking(FLASK_SHAKE_RPM, false)
	box.add_child(_flask)

	# The honesty strip. Everything this scene deliberately does not draw, stated
	# where it can be read rather than only in a report.
	var caveat := PanelContainer.new()
	var inner := VBoxContainer.new()
	inner.add_theme_constant_override("separation", 1)
	caveat.add_child(inner)
	var caveat_title := Label.new()
	caveat_title.text = "what this scene is not"
	caveat_title.add_theme_font_size_override("font_size", 10)
	caveat_title.modulate = Color(0.95, 0.82, 0.45)
	inner.add_child(caveat_title)
	var caveat_body := Label.new()
	caveat_body.text = (
		"well-mixed bulk quantities only. No cells, bubbles, concentration "
		+ "gradients, flow patterns, vortex, mixing or reaction effects are "
		+ "drawn: the model computes no such quantity, so showing one would be "
		+ "an invented effect. Liquid colour is a legend for biomass. The bar "
		+ "beside the flask is dissolved oxygen. The platform turns because "
		+ "200 rpm is reported, not because the model computes the flow.")
	caveat_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	caveat_body.add_theme_font_size_override("font_size", 10)
	caveat_body.modulate = Color(1, 1, 1, 0.5)
	inner.add_child(caveat_body)
	box.add_child(caveat)

	_readouts = VBoxContainer.new()
	_readouts.add_theme_constant_override("separation", 1)
	box.add_child(_readouts)
	_rebuild_readouts()
	return box


func _panel_column() -> Control:
	var tabs := TabContainer.new()
	tabs.custom_minimum_size = Vector2(430, 0)
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL

	_evidence = EvidenceInspector.new()
	_evidence.setup()
	tabs.add_child(_evidence)
	_evidence.name = "Evidence"

	_gaps = ResearchGapPanel.new()
	_gaps.setup()
	tabs.add_child(_gaps)
	_gaps.name = "Gaps"

	_compat = CompatibilityPanel.new()
	_compat.setup()
	tabs.add_child(_compat)
	_compat.name = "Models"

	_report = CompositionReportPanel.new()
	tabs.add_child(_report)
	_report.name = "Report"

	return tabs


func _timeline_bar() -> Control:
	var box := PanelContainer.new()
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 3)
	box.add_child(column)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	column.add_child(row)

	_play_button = Button.new()
	_play_button.text = "Play"
	_play_button.pressed.connect(_on_play_pressed)
	row.add_child(_play_button)

	var reset := Button.new()
	reset.text = "Reset"
	reset.pressed.connect(_on_reset_pressed)
	row.add_child(reset)

	_timeline = HSlider.new()
	_timeline.min_value = 0.0
	_timeline.max_value = 1000.0
	_timeline.step = 1.0
	_timeline.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_timeline.value_changed.connect(_on_scrub)
	row.add_child(_timeline)

	_playhead_label = Label.new()
	_playhead_label.text = "t = 0.00 h"
	_playhead_label.custom_minimum_size = Vector2(112, 0)
	_playhead_label.add_theme_font_size_override("font_size", 11)
	row.add_child(_playhead_label)

	column.add_child(_input_row())
	return box


## The editable inputs. Each carries its startup classification, because the three
## conditions the paper does not state are the most scientifically interesting things
## a user can change here.
func _input_row() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	for spec in EDITABLE:
		var column := VBoxContainer.new()
		column.add_theme_constant_override("separation", 0)
		row.add_child(column)

		var label := Label.new()
		label.text = "%s [%s]" % [str(spec["label"]), str(spec["unit"])]
		label.add_theme_font_size_override("font_size", 9)
		label.modulate = Color(1, 1, 1, 0.6)
		column.add_child(label)

		var edit := LineEdit.new()
		edit.text = str(STARTUP[str(spec["key"])]["value"])
		edit.custom_minimum_size = Vector2(92, 0)
		edit.add_theme_font_size_override("font_size", 10)
		edit.tooltip_text = "%s -- %s: %s" % [
			str(spec["label"]),
			str(STARTUP[str(spec["key"])]["classification"]),
			str(STARTUP[str(spec["key"])]["note"])]
		edit.text_changed.connect(_on_input_changed)
		edit.set_meta("input_key", str(spec["key"]))
		_input_fields.append(edit)
		column.add_child(edit)
	return row


# ------------------------------------------------------------------ execution


func _on_run_pressed() -> void:
	run_simulation()


## Execute the current configuration through the normal runner path.
func run_simulation() -> void:
	_commit_inputs()
	if _awaiting != "":
		# One subprocess at a time. The runner is synchronous, and stacking
		# invocations would interleave their result documents.
		_status_text = "busy: %s" % _awaiting
		_set_status(_status_text)
		return
	if not DirAccess.dir_exists_absolute(GRAPH_DIR):
		DirAccess.make_dir_recursive_absolute(GRAPH_DIR)
	if not DirAccess.dir_exists_absolute(RESULT_DIR):
		DirAccess.make_dir_recursive_absolute(RESULT_DIR)

	var graph_path := "%s/%s.json" % [GRAPH_DIR, _document().graph_id]
	_last_result_path = "%s/%s.result.json" % [RESULT_DIR, _document().graph_id]

	var file := FileAccess.open(graph_path, FileAccess.WRITE)
	if file == null:
		_set_status("could not write the graph document")
		return
	file.store_string(JSON.stringify(_document()))
	file.close()

	_playing = false
	_play_button.text = "Play"
	_awaiting = "run"
	_set_status("running the model through the composition runner...")
	_runner.run_graph(graph_path, _last_result_path)


## The graph this scene executes: one instance, no connections.
##
## No connections is a scientific position, not a simplification. The compatibility
## engine permits no cross-model pair, and a connection invented here would make the
## graph execute while asserting a relationship no ingested source supports.
func _document() -> Dictionary:
	var literals := {}
	for key in STARTUP:
		var entry: Dictionary = STARTUP[key]
		literals["%s/%s" % [INSTANCE_ID, key]] = _literal(key, entry)
	_inputs = literals

	var instance := {
		"instance_id": INSTANCE_ID,
		"model_id": MODEL_ID,
		"model_version": MODEL_VERSION,
		"label": "Shake-flask fed-batch culture, 24 h",
		"role": "single model under simulation",
		"position": {"x": 240.0, "y": 160.0},
		"parameters": {
			"simulation": {
				"mode": "fed_batch",
				"duration_h": _duration,
				"output_times_h": [0.0, 6.0, 12.0, 18.0, 24.0, _duration],
				"solver": {
					"rtol": 1e-06,
					"atol": 1e-09,
					"h_max": 0.01,
				},
			},
		},
	}

	return {
		"contract_version": "0.1.0",
		"graph_id": "workshop-shake-flask-fed-batch",
		"title": "Ganjave et al. (2022) shake-flask fed-batch, single model, no connections",
		"description": (
			"One Ganjave instance. No connections: the compatibility engine permits "
			+ "no cross-model pair among the registered models."),
		"source_ref": ("Ganjave et al. 2022, Biotechnology Reports 33:e00694, "
			+ "doi:10.1016/j.btre.2021.e00694"),
		"instances": [instance],
		"connections": [],
		"literal_inputs": literals,
		"defaults": {},
	}


func _literal(key: String, entry: Dictionary) -> Dictionary:
	return {
		"state": "number",
		"quantity": _quantity_for(key),
		"value": entry["value"],
		"unit": entry["unit"],
		"provenance": entry["classification"],
		"source_ref": entry["locator"],
		"method": "declared graph input for the workshop scene",
		"reason": str(entry["note"]),
	}


func _quantity_for(key: String) -> String:
	match key:
		"initial_dissolved_oxygen":
			return "dimensionless"
		"feed_flow_rate":
			return "volume_flow"
		"feed_start_time":
			return "time"
		"initial_culture_volume":
			return "volume"
	return "mass_concentration"


func _on_runner_finished(payload: Dictionary) -> void:
	var kind := _awaiting
	_awaiting = ""

	if kind == "run":
		_on_run_result(payload)
	elif kind == "manifest":
		# A model whose package is absent answers with `manifest: null`. That is
		# a reportable state, not a crash: keep the empty manifest and let the
		# status line below say which model could not be described.
		var reported: Variant = payload.get("manifest", null)
		_manifest = reported if reported is Dictionary else {}
		if not _manifest.is_empty():
			_evidence.show_model(_manifest, _last_payload, _inputs)
			_awaiting = "connections"
			_runner.describe_connections()
			return
		_set_status("could not describe the model: %s" % str(payload.get("notes", "")))
	elif kind == "contract":
		_contract = payload
	elif kind == "connections":
		_connections = payload
		_compat.show_connections(_connections, MODEL_ID)
		_refresh_gaps()
		# Everything the panels need is in hand; produce the first result.
		run_simulation()
		return
	else:
		_set_status(str(payload.get("notes", "runner finished")))
		return


func _on_run_result(payload: Dictionary) -> void:
	_last_payload = payload
	var status := str(payload.get("status", "?"))
	# A run "produces" results only if an instance actually succeeded and
	# published outputs. A *failed* instance still appears in the results array,
	# so its presence alone would present a failure as a success -- and, worse,
	# would clear the duration and leave the next run asking for a zero-hour
	# simulation.
	var produced := false
	for entry in payload.get("results", []) as Array:
		var instance_status := str(entry.get("status", ""))
		if instance_status == "failed" or instance_status == "refused" \
				or instance_status == "invalid":
			continue
		if (entry.get("outputs", []) as Array).is_empty():
			continue
		produced = true

	if produced:
		_trajectories = _extract_trajectories(payload)
		_stale = false
		# Only adopt a measured duration. A run that produced no trajectory
		# leaves the previous one in place rather than silently setting the
		# simulation to zero hours.
		var measured := _max_time()
		if measured > 0.0:
			_duration = measured
		_playhead = 0.0
		_timeline.max_value = 1000.0
		_refresh_gaps()
		_evidence.show_model(_manifest, payload, _inputs)
		_report.show_report(payload)
		_set_status("%s  |  %d result(s) from the composition runner" % [
			status, payload.get("results", []).size()])
		_apply_time(0.0)
	else:
		# Execution failed or was refused. The reason is shown, and whatever is on
		# screen stays, marked as belonging to a configuration that no longer runs.
		_trajectories = {}
		_stale = true
		_flask.set_culture_volume(_nan())
		_refresh_gaps()
		_evidence.show_model(_manifest, payload, _inputs)
		_report.show_report(payload)
		var reasons := _failure_reasons(payload)
		_set_status("%s  |  %s" % [status, reasons], Color(0.95, 0.62, 0.52))


func _failure_reasons(payload: Dictionary) -> String:
	var parts := PackedStringArray()
	for diagnostic in payload.get("diagnostics", []) as Array:
		if str(diagnostic.get("severity", "")) != "error":
			continue
		parts.append("%s: %s" % [str(diagnostic.get("code", "?")),
			str(diagnostic.get("message", "")).substr(0, 150)])
		if parts.size() >= 2:
			break
	if parts.is_empty():
		parts.append(str(payload.get("notes", "no diagnostic was returned")))
	return "; ".join(parts)


## Pull the dense trajectories the runner produced out of the result document.
func _extract_trajectories(payload: Dictionary) -> Dictionary:
	var out := {}
	for result in payload.get("results", []) as Array:
		for output in result.get("outputs", []) as Array:
			var port_id := str((output.get("ref", {}) as Dictionary).get("port_id", ""))
			var value := output.get("value", {}) as Dictionary
			var trajectory := (value.get("extra", {}) as Dictionary).get("trajectory", {}) as Dictionary
			var time_axis := trajectory.get("time_axis", {}) as Dictionary
			var times := time_axis.get("values", []) as Array
			var values := trajectory.get("values", []) as Array
			if times.is_empty() or values.is_empty():
				continue
			out[port_id] = {
				"times": PackedFloat64Array(times),
				"values": PackedFloat64Array(values),
				"unit": str(trajectory.get("unit", "")),
				"quantity": str(trajectory.get("quantity", "")),
				"value_state": str(value.get("state", "")),
				"provenance": str(value.get("provenance", "")),
				"method": str(value.get("method", "")),
			}
	return out


# ------------------------------------------------------------------- timeline


func _process(delta: float) -> void:
	if not _playing or _trajectories.is_empty():
		return
	_playhead += delta * _play_rate
	if _playhead >= _duration:
		_playhead = _duration
		_playing = false
		_play_button.text = "Play"
	_timeline.set_value_no_signal(_playhead / maxf(_duration, 0.001) * 1000.0)
	_apply_time(_playhead)


func _on_play_pressed() -> void:
	if _trajectories.is_empty():
		_set_status("nothing to play: run the simulation first", Color(0.95, 0.82, 0.45))
		return
	_playing = not _playing
	_play_button.text = "Pause" if _playing else "Play"


func _on_reset_pressed() -> void:
	_playing = false
	_play_button.text = "Play"
	_playhead = 0.0
	_timeline.set_value_no_signal(0.0)
	_apply_time(0.0)


func _apply_time(t: float) -> void:
	_playhead_label.text = "t = %.2f h" % t
	if _trajectories.is_empty():
		_banner.text = "no results: nothing is rendered as a calculated value"
		_flask.set_culture_volume(_nan())
		_flask.set_dissolved_oxygen(_nan())
		_flask.set_biomass_fraction(0.0)
		_flask.set_feed_delivered(_nan())
		_rebuild_readout_values({})
		return

	var values := _sample(t)
	var biomass := float(values.get("biomass_concentration", 0.0))
	var volume := float(values.get("culture_volume", 0.0))
	var oxygen := float(values.get("dissolved_oxygen", 0.0))
	var flow := float(STARTUP["feed_flow_rate"]["value"])
	var feed_start := float(STARTUP["feed_start_time"]["value"])

	_flask.set_culture_volume(volume)
	_flask.set_biomass_fraction(biomass / BIOMASS_SCALE_G_PER_L)
	_flask.set_dissolved_oxygen(oxygen)
	_flask.set_shaking(FLASK_SHAKE_RPM, t > 0.0)
	var delivered := 0.0
	if t > feed_start:
		delivered = flow * (t - feed_start)
	_flask.set_feed_delivered(delivered, SYRINGE_ML)

	_rebuild_readout_values(values)
	_banner.text = ("%s  |  colour scale 0 - %.0f g/L biomass" % [
		"results are current" if not _stale else
			"STALE: these values belong to an earlier configuration",
		BIOMASS_SCALE_G_PER_L])


## Linear interpolation inside a trajectory the runner produced.
##
## The observation side of a comparison is never interpolated; here the *model's own*
## dense output is being read at a time the user chose, which is the same thing the
## runner's own result document contains.
func _sample(t: float) -> Dictionary:
	var out := {}
	for port_id in _trajectories:
		var series := _trajectories[port_id] as Dictionary
		var times := series["times"] as PackedFloat64Array
		var values := series["values"] as PackedFloat64Array
		if times.size() < 2:
			continue
		var clamped := clampf(t, times[0], times[times.size() - 1])
		var index := 0
		while index < times.size() - 2 and times[index + 1] < clamped:
			index += 1
		var span := times[index + 1] - times[index]
		var fraction := 0.0 if span <= 0.0 else (clamped - times[index]) / span
		out[port_id] = values[index] + fraction * (values[index + 1] - values[index])
	return out


func quantity_at(port_id: String, t: float) -> float:
	var series := _trajectories.get(port_id, {}) as Dictionary
	if series.is_empty():
		return NAN
	var single := _sample(t)
	return float(single.get(port_id, NAN))


## Fixed-precision rendering, because `%.4g` is a C/Python format and not a
## GDScript one. The width is picked from the magnitude so a volume in litres and a
## glycerol residue in tenths of a gram per litre both read cleanly.
func _format_number(value: float) -> String:
	if is_nan(value):
		return "--"
	if is_zero_approx(value):
		return "0"
	var magnitude := absf(value)
	if magnitude >= 1000.0:
		return "%d" % int(round(value))
	if magnitude >= 100.0:
		return "%d" % int(round(value))
	if magnitude >= 1.0:
		return "%.2f" % value
	return "%.4f" % value

func _max_time() -> float:
	var latest := 0.0
	for port_id in _trajectories:
		var times := (_trajectories[port_id] as Dictionary)["times"] as PackedFloat64Array
		if times.size() > 0:
			latest = maxf(latest, times[times.size() - 1])
	return latest


# ------------------------------------------------------------------ readouts


func _rebuild_readouts() -> void:
	for child in _readouts.get_children():
		_readouts.remove_child(child)
		child.queue_free()
	for spec in RENDERED:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)
		var name_label := Label.new()
		name_label.text = "%s [%s]" % [str(spec["label"]), str(spec["unit"])]
		name_label.custom_minimum_size = Vector2(168, 0)
		name_label.add_theme_font_size_override("font_size", 10)
		name_label.modulate = Color(1, 1, 1, 0.55)
		row.add_child(name_label)
		var value_label := Label.new()
		value_label.text = "--"
		value_label.add_theme_font_size_override("font_size", 11)
		value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		value_label.set_meta("readout_port", str(spec["port"]))
		row.add_child(value_label)
		var badge := Label.new()
		badge.text = str(spec["epistemic"])
		badge.add_theme_font_size_override("font_size", 9)
		badge.modulate = Color(0.52, 0.72, 0.96)
		row.add_child(badge)
		_readouts.add_child(row)


func _rebuild_readout_values(values: Dictionary) -> void:
	for spec in RENDERED:
		var port_id := str(spec["port"])
		var found := false
		for child in _readouts.get_children():
			var row := child as HBoxContainer
			if row == null:
				continue
			for element in row.get_children():
				var label := element as Label
				if label == null or str(label.get_meta("readout_port", "")) != port_id:
					continue
				if values.has(port_id):
					label.text = _format_number(float(values[port_id]))
					found = true
				else:
					label.text = "--"
		if not found:
			continue


# ------------------------------------------------------------------- inputs


func _on_input_changed(_new_text: String) -> void:
	"""An edit invalidates the previous results before anything else.

	The scene keeps showing them -- a reader mid-inspection is more helped by a stale
	number labelled stale than by an empty flask -- but nothing on screen claims to
	describe the configuration now in the editor.
	"""
	_stale = true
	_playing = false
	_play_button.text = "Play"
	_banner.text = ("STALE: the configuration has changed. Press Run to recompute; "
		+ "what is shown belongs to the previous run.")
	_set_status("inputs changed -- results are stale. Run to recompute.",
		Color(0.95, 0.82, 0.45))


## Read the current values from the editable fields.
##
## The field values are the source of truth for a run; `STARTUP` holds their declared
## defaults and their provenance, and is refreshed from the fields before execution so
## a graph document never carries a value the user did not type.
func current_inputs() -> Dictionary:
	var out := {}
	for key in STARTUP:
		out[key] = (STARTUP[key] as Dictionary).duplicate()
	for edit in _input_fields:
		var key := str(edit.get_meta("input_key", ""))
		if key == "":
			continue
		var parsed := float(edit.text)
		if is_nan(parsed):
			continue
		var entry := (out[key] as Dictionary).duplicate()
		entry["value"] = parsed
		entry["edited"] = not is_equal_approx(
			parsed, float((STARTUP[key] as Dictionary)["value"]))
		out[key] = entry
	return out


## Copy the fields back into `STARTUP` so the graph document and the panels agree.
func _commit_inputs() -> void:
	var current := current_inputs()
	for key in current:
		STARTUP[key] = current[key]


func _on_scrub(value: float) -> void:
	# Dummy function for timeline connection in workshop mode
	# Not used in replay mode (scene changes before _build_ui is called)
	pass

func _on_replay_pressed() -> void:
	get_tree().change_scene_to_file.call_deferred("res://scenes/replay3d.tscn")


func _on_prompt_pressed() -> void:
	get_tree().change_scene_to_file.call_deferred("res://scenes/prompt_simulation.tscn")


func _refresh_gaps() -> void:
	if _gaps == null:
		return
	_gaps.generate(
		_manifest,
		_contract,
		_last_payload.get("composition_report", {}) as Dictionary,
		_connections,
		_inputs,
		_last_payload.get("diagnostics", []) as Array)


func _set_status(text: String, colour: Color = Color(1, 1, 1, 0.72)) -> void:
	if _status == null:
		return
	_status.text = text
	_status.modulate = colour


func _nan() -> float:
	return NAN


# ------------------------------------------------ harness-facing accessors


func flask_view() -> ShakeFlaskView:
	return _flask


func evidence_panel() -> EvidenceInspector:
	return _evidence


func gap_panel() -> ResearchGapPanel:
	return _gaps


func compatibility() -> CompatibilityPanel:
	return _compat


func report_panel() -> CompositionReportPanel:
	return _report


func last_payload() -> Dictionary:
	return _last_payload


## True when what is on screen describes a configuration that has since changed.
##
## This reports the *staleness* flag, not whether a request is in flight --
## `busy()` answers that. The two were conflated here, which made the acceptance
## checks that exist to catch a stale result being shown as current unable to
## fail: `_awaiting` is cleared at the top of every result handler, so this
## returned false at exactly the moments it was asked.
func is_stale() -> bool:
	return _stale


func has_results() -> bool:
	return not _trajectories.is_empty()


func rendered_ports() -> PackedStringArray:
	var names := PackedStringArray()
	for spec in RENDERED:
		names.append(str(spec["port"]))
	return names


func startup_entries() -> Dictionary:
	return STARTUP


func graph_connections() -> Array:
	return _document()["connections"] as Array


func busy() -> bool:
	return _awaiting != ""

