extends SceneTree
## Headless checks for the pecan workflow bench.
##
## Every one of the 18 recorded research steps must be represented by something
## the user can see and interact with, and the six pecan bench steps must show
## actual object motion sampled from the real scene. Analogue steps must leave the
## pecan bench still, and no measurement value may be invented.
##
##   godot --headless --path . --script composition/tests/godot/pecan_replay_scene.gd

const SCENE := "res://scenes/pecan_replay.tscn"

const MODES := [
	"physical", "physical", "physical", "observe", "physical", "physical",
	"analogue", "analogue", "analogue", "analogue", "analogue", "analogue",
	"analogue", "analogue", "analogue", "analogue", "analogue", "caveat",
]

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
	if _frames < 4:
		return false
	_ran = true
	_scene = current_scene
	_run_checks()
	_finish()
	return true


func _at(seconds: float) -> Dictionary:
	_scene._clock = seconds
	_scene._apply_clock()
	return _scene.probes()


func _run_checks() -> void:
	_check(_scene != null, "the pecan replay scene loaded")
	if _scene == null:
		return
	_check(_scene.stage_count() == 18, "18 evidence steps were loaded")
	_check(_scene.sim() != null, "the step-indexed bench exists")
	_check(_scene.operation_count() == 18, "all 18 steps own a slot on the bench clock")
	_check(_scene.chip_count() == 18, "the process rail exposes a chip for every step")
	_check(absf(_scene.total_seconds() - PecanProcessSim.TOTAL_SECONDS) < 0.01,
		"the timeline length is the sum of the step slots")

	_check_coverage()
	_check_physical_steps()
	_check_analogue_and_caveat()
	_check_interactions()
	_check_integrity()
	_check_workshop_entry()


func _check_coverage() -> void:
	for index in 18:
		var step_id: String = _scene.step_id_at(index)
		_check(step_id != "", "step %d has an id" % (index + 1))
		_check(_scene.step_mode_at(index) == MODES[index],
			"step %d (%s) is classified as %s" % [index + 1, step_id, MODES[index]])
		# selecting the step must show its own evidence, not a neighbour's
		_scene.select_stage(index)
		var evidence: String = _scene.evidence_text()
		_check(evidence.contains(step_id),
			"selecting step %d shows its own step id" % (index + 1))
		_check(evidence.contains(str(_scene._steps[index].get("label", "")).substr(0, 12)),
			"selecting step %d shows its label" % (index + 1))
		if MODES[index] == "analogue":
			_check(evidence.contains("NOT validated on pecan"),
				"step %d (%s) is marked as an unvalidated analogue" % [index + 1, step_id])
			_check(evidence.contains("No pecan vessel moves"),
				"step %d states the bench does not perform it" % (index + 1))
		elif MODES[index] == "caveat":
			_check(evidence.to_lower().contains("review caveat"),
				"step %d is marked as a review caveat" % (index + 1))


func _check_physical_steps() -> void:
	# 1. tissue handling: the clump is lifted in an arc and dropped into tube A
	var tissue_start: Vector3 = _at(0.20)["tissue"]
	var tissue_mid: Vector3 = _at(1.00)["tissue"]
	var tissue_end: Vector3 = _at(2.60)["tissue"]
	_check(tissue_start.distance_to(tissue_mid) > 0.3, "the tissue clump moves through the air")
	_check(tissue_mid.y > tissue_start.y + 0.05, "it rises in an arc rather than sliding")
	_check(tissue_end.distance_to(tissue_start) > 1.0, "it ends up at the tube")

	# 2. TRIzol: dispense, mix, spin, phase separation, transfer
	var empty: Dictionary = _at(3.50)
	_check(float(empty["mixed_height"]) < 0.01, "tube A starts empty")
	var filling: Dictionary = _at(4.60)
	_check(bool(filling["stream"]), "a liquid stream is visible while dispensing TRIzol")
	_check(bool(filling["droplets"]), "droplets fall from the pipette while dispensing")
	_check(float(filling["alignment_a"]) < 0.005,
		"the tip is over tube A's mouth (offset %.4f)" % float(filling["alignment_a"]))
	var filled: Dictionary = _at(5.70)
	_check(float(filled["mixed_height"]) > 0.2,
		"the liquid level rises as TRIzol is dispensed (%.3f)" % float(filled["mixed_height"]))
	_check((filling["pipette"] as Vector3).distance_to(empty["pipette"]) > 0.2,
		"the pipette physically travels between stations")

	var mixing: Dictionary = _at(6.20)
	_check(absf(float(mixing["tube_a_wobble"])) > 0.01, "the tube is shaken during mixing")
	_check(bool(mixing["bubbles"]), "bubbles rise in the tube during mixing")

	var spinning: Dictionary = _at(7.20)
	_check((spinning["tube_a"] as Vector3).distance_to(PecanProcessSim.TUBE_A_HOME) > 0.2,
		"the tube is physically moved into the rotor")
	_check(absf(float(spinning["rotor_angle"])) > 0.5, "the rotor turns")
	_check(_at(7.90)["rotor_angle"] != spinning["rotor_angle"],
		"the rotor keeps turning while the tube is inside")

	var split: Dictionary = _at(8.10)
	_check(float(split["organic_height"]) > 0.05, "a lower organic phase appears")
	_check(float(split["aqueous_height"]) > 0.05, "an upper aqueous phase appears")
	var transferred: Dictionary = _at(8.80)
	_check(float(transferred["alignment_b"]) < 0.005,
		"the tip is over tube B's mouth (offset %.4f)" % float(transferred["alignment_b"]))
	_check(bool(transferred["stream"]), "the upper phase is drawn into the pipette and dispensed")
	_check(float(_at(9.40)["tube_b_height"]) > 0.15, "tube B receives the transferred phase")

	# 3. DNase: reagent is taken from the vial and added to the RNA
	_check(float(_at(9.80)["dnase"]) < 0.01, "no DNase has been added yet")
	_check(float(_at(10.62)["alignment_dnase"]) < 0.01,
		"the pipette reaches the DNase vial (offset %.4f)" % float(_at(10.62)["alignment_dnase"]))
	_check(float(_at(11.20)["alignment_b"]) < 0.01, "the DNase is carried to the RNA tube")
	_check(float(_at(11.90)["dnase"]) > 0.4, "DNase visibly enters tube B")
	_check(bool(_at(13.20)["incubate"]), "the tube is held for incubation")

	# 4. quality assessment: a measurement is performed, no value is invented
	var loading: Dictionary = _at(15.20)
	_check(float(loading["alignment_quality"]) < 0.01,
		"the sample is loaded into a gel well (offset %.4f)" % float(loading["alignment_quality"]))
	_check(bool(_at(16.00)["gel_loaded"]), "the gel wells are loaded")
	var scanning: Dictionary = _at(16.50)
	_check(float(scanning["nanodrop"]) > 0.4, "the spectrophotometer is operated")
	_check(bool(scanning["scan_beam"]), "the measurement beam is visible")
	_check(_scene.sim().hud_text().to_lower().contains("no yield"),
		"the bench states that no yield, ratio or RIN was reported")

	# 5. PAGE enrichment: sample is loaded and a slice is excised
	var page_load: Dictionary = _at(19.40)
	_check(float(page_load["alignment_page"]) < 0.01,
		"the sample reaches the PAGE cassette (offset %.4f)" % float(page_load["alignment_page"]))
	_check(bool(page_load["stream"]), "the sample is loaded onto the gel")
	var slice: Dictionary = _at(21.30)
	_check(float(slice["slice"]) > 0.9, "the gel slice is excised and carried")
	_check((slice["slice_position"] as Vector3).y < 1.5, "the slice ends up in the collection tube")

	# 6. cDNA synthesis: 1 ug is transferred and the tube enters the heat block
	var cdna_load: Dictionary = _at(23.20)
	_check(float(cdna_load["alignment_cdna"]) < 0.01,
		"the RNA is dispensed into the cDNA tube (offset %.4f)" % float(cdna_load["alignment_cdna"]))
	_check(bool(cdna_load["stream"]), "a stream is visible while dispensing into the cDNA tube")
	var incubated: Dictionary = _at(24.80)
	_check(float(incubated["cdna"]) > 0.9, "the cDNA tube is lowered into the heat block")
	_check(bool(incubated["block_glow"]), "the heat block is visibly active")
	_check((incubated["cdna_position"] as Vector3).y < 0.14, "the tube sits inside the block")

	# scrubbing is reproducible across all of the above
	_scene._clock = 21.3
	_scene._apply_clock()
	var rescrubbed: Dictionary = _scene.probes()
	_check(str(rescrubbed["slice_position"]) == str(slice["slice_position"]),
		"scrubbing back to 21.3 reproduces the slice position")
	_check(is_equal_approx(float(rescrubbed["nanodrop"]), 0.0),
		"the spectrophotometer is idle outside its step")



func _check_analogue_and_caveat() -> void:
	# nothing on the pecan bench may move for a transferred hypothesis
	var first: Dictionary = _at(25.10)
	var last: Dictionary = _at(26.90)
	for key in ["tissue", "tube_a", "tube_b", "pipette", "mixed_height",
			"organic_height", "aqueous_height", "tube_b_height", "rotor_angle"]:
		_check(str(first[key]) == str(last[key]),
			"the bench does not move during an analogue step (%s)" % key)
	_check(float(first["analogue_pulse"]) > 0.1, "the analogue card visibly responds")
	_check(first["mode"] == "analogue", "the bench reports the analogue mode")
	_check(_scene.sim().hud_text().contains("NOT validated on pecan"),
		"the bench HUD states the hypothesis is not validated on pecan")

	# the pigeonpea branch is a different hypothesis, still not a pecan operation
	_scene.select_stage(12)
	var pigeonpea: Dictionary = _scene.probes()
	_check(pigeonpea["mode"] == "analogue", "pigeonpea steps are analogue steps too")
	_check(str(pigeonpea["tissue"]) == str(first["tissue"]),
		"switching analogue branch still leaves the bench still")
	_check(_scene.evidence_text().contains("pigeonpea"),
		"the pigeonpea step names its source species")

	# the method-review caveat is its own, unresolved marker
	_scene.select_stage(17)
	var caveat: Dictionary = _scene.probes()
	_check(caveat["mode"] == "caveat", "the final step is a method-review caveat")
	_check(float(caveat["caveat_pulse"]) > 0.1, "the caveat card visibly responds")
	_check(_scene.evidence_text().to_lower().contains("no universal rna protocol"),
		"the caveat states the unresolved question")


func _check_interactions() -> void:
	# a chip jumps the bench clock to that step's slot
	_scene.select_stage(9)
	_check(_scene.current_stage() == 9, "selecting a step changes the current step")
	_check(absf(_scene.clock() - _scene.sim().step_start(9)) < 0.01,
		"selecting a step moves the clock to its start (%.2f)" % _scene.clock())

	# clicking bench objects inspects the step they belong to
	var clicks := {
		"dnase": "pecan_dnase_treatment",
		"quality": "pecan_quality_assessment",
		"page": "pecan_small_rna_enrichment",
		"cdna": "pecan_cdna_synthesis",
		"centrifuge": "pecan_trizol_extraction",
	}
	for kind in clicks.keys():
		_scene._on_object_clicked(kind)
		_check(_scene.step_id_at(_scene.current_stage()) == clicks[kind],
			"clicking the %s selects %s" % [kind, clicks[kind]])
		_check(_scene.evidence_text().contains(str(clicks[kind])),
			"clicking the %s shows its evidence" % kind)

	# clicking the analogue kiosk follows the selected branch
	_scene.set_branch("pigeonpea")
	_check(_scene.branch() == "pigeonpea", "the analogue branch can be switched")
	_scene._on_object_clicked("reference")
	_check(_scene.current_stage() == 12,
		"clicking the kiosk inspects the first step of the current branch")

	# the camera can be sent to a station without changing the animation
	_scene.select_stage(4)
	var goal: Vector3 = _scene.focus_target()
	var expected: Vector3 = PecanProcessSim.FOCUS["page"][0]
	_check(goal.distance_to(expected) < 0.01, "the camera focuses the selected station")

	# protocol comparison reads both sides and stays non-predictive
	_scene.select_compare(2, 10)
	_check(_scene.selected_compare_a() == 2, "the pecan side of the comparison is settable")
	_check(_scene.selected_compare_b() == 10, "the transferred side is settable")
	var comparison: String = _scene.compare_text()
	_check(comparison.contains("Comparison only"), "the comparison states it is not a prediction")
	_check(comparison.contains("dnase_time"), "the comparison lists the analogue parameter")
	_check(comparison.contains("30.0"), "the comparison shows the analogue value")
	_check(comparison.contains("not pecan measurements"),
		"the comparison refuses to treat analogue values as pecan results")
	_check(comparison.contains("never executed on the pecan bench"),
		"the comparison states the transferred step is never executed")

	# an unresolved parameter can be interrogated and shows who else reports it
	_scene.select_step_id("pecan_dnase_treatment")
	_scene.select_parameter("pecan_dnase_treatment", "dnase_time")
	var detail: String = _scene.parameter_detail_text()
	_check(detail.contains("no digestion time"),
		"the parameter detail repeats the recorded basis")
	_check(detail.contains("analogous species"),
		"the parameter detail names the class of the other sources")
	_check(detail.contains("30.0"), "the parameter detail shows the analogue value")
	_check(detail.contains("not to pecan"),
		"the parameter detail refuses to substitute the analogue value")


func _check_integrity() -> void:
	# evidence stays accessible and auditable
	_scene.select_stage(1)
	var evidence: String = _scene.evidence_text()
	_check(evidence.contains("10.3390/foods13182934"), "selecting a step shows the pecan DOI")
	_check(evidence.contains("TRIzol"), "selecting a step shows the verbatim passage")
	_scene._on_object_clicked("centrifuge")
	_check(_scene.evidence_text().contains("direct evidence"),
		"clicking the centrifuge reveals the direct evidence behind it")
	_scene._on_object_clicked("reference")
	_check(_scene.evidence_text().contains("NOT validated on pecan"),
		"clicking the reference card reveals the analogue-hypothesis caveat")

	var limits: String = _scene.limitations_text()
	_check(limits.contains("not a validated quantitative RNA extraction model"),
		"the limitations tab states the model is not validated")
	_check(limits.contains("No RNA yield, RIN, purity or degradation value"),
		"the limitations tab refuses yield/RIN claims")
	_check(limits.contains("eleven are analogue hypotheses"),
		"the limitations tab separates the direct and analogue steps")

	var combined := (evidence + limits).to_lower()
	_check(not combined.contains("predicted yield"), "no predicted yield appears anywhere")
	_check(not combined.contains("predicted rin"), "no predicted RIN appears anywhere")

	# the bench never fabricates a measurement: the observation step reports the
	# absence of a reading rather than a number
	_scene.select_step_id("pecan_quality_assessment")
	var quality: String = _scene.evidence_text().to_lower()
	_check(quality.contains("no yield") or quality.contains("not stated"),
		"the quality step presents no invented measurement")
	for probe_key in ["rna_yield", "a260_a280", "rin"]:
		_check(quality.contains(probe_key.replace("_", " ")) or quality.contains(probe_key),
			"the quality step still records %s as unresolved" % probe_key)

	# playback still drives the same deterministic clock
	_scene.select_stage(0)
	var before: float = _scene.clock()
	_scene.advance(1.5)
	_check(_scene.clock() > before, "the clock advances on the scrub/play path")
	_scene.play()
	_check(_scene.is_playing(), "play starts the replay")
	_scene.pause()
	_check(not _scene.is_playing(), "pause stops it")

	_check(_scene.outputs_panel() != null, "the workflow outputs panel is still wired")


func _check_workshop_entry() -> void:
	var workshop_script = load("res://scripts/workshop.gd")
	if workshop_script != null:
		var workshop: Control = workshop_script.new()
		var header = workshop._header()
		_check(_find(header, "PecanReplayButton") != null, "the workshop header offers this replay")
		_check(_find(header, "PecanWorkflowButton") != null, "the step-graph entry is still offered")
		workshop.free()


func _find(node: Node, node_name: String) -> Node:
	if node == null:
		return null
	if str(node.name) == node_name:
		return node
	for child in node.get_children():
		var found := _find(child, node_name)
		if found != null:
			return found
	return null


func _finish() -> void:
	print("\nPECAN WORKFLOW CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)

