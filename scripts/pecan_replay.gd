extends Control
## Pecan RNA extraction — 3D process replay.
##
## The replay is built from the four compiled artifacts in
## `composition/workflow_runs/<case>/`. Every stage is one protocol step from
## `model_spec.json`; every quote, DOI, parameter and unknown shown on the right
## comes from `research_encoded.json` / `model_spec.json`, and the outputs tab is
## the existing composition `ResultsPanel` fed with `simulation_result.json`.
##
## What the 3D bench shows: a schematic laboratory — pecan leaf tissue, a tube
## rack, an extraction tube with a pipette, a centrifuge, a DNase station, a
## quality gel, a small-RNA gel, cDNA tubes and a reference-card station for
## evidence that is not a pecan bench step. The highlight and the sample tint
## encode the **evidence class** of the selected stage. Nothing is calculated and
## no yield, RIN, degradation or molecular behaviour is drawn: the artifacts
## contain none. The bench is labelled as a schematic replay wherever it appears.

const RUNS_DIR := "res://composition/workflow_runs"
## The web export excludes `composition/`, so the three compiled artifacts this
## scene needs are mirrored under `assets/pecan/`. The desktop build keeps
## reading the workflow run itself, which stays the single source of truth.
const WEB_FALLBACK_DIR := "res://assets/pecan"
const CASE_ID := "pecan"
const STAGE_SECONDS := 2.4
const ACCENT := Color(0.42, 0.66, 1.0)
const MUTED := Color(1, 1, 1, 0.6)
const GOOD := Color(0.36, 0.78, 0.47)
const WARN := Color(0.92, 0.68, 0.22)
const METHOD := Color(0.62, 0.70, 0.80)

## Which step each physical object belongs to. Every bench object now resolves to
## a recorded research step, so clicking anything is an act of inspection.
const OBJECT_STEPS := {
	"tissue": "pecan_sample_handling",
	"trizol": "pecan_trizol_extraction",
	"tube_a": "pecan_trizol_extraction",
	"tube_b": "pecan_dnase_treatment",
	"pipette": "pecan_trizol_extraction",
	"centrifuge": "pecan_trizol_extraction",
	"dnase": "pecan_dnase_treatment",
	"quality": "pecan_quality_assessment",
	"page": "pecan_small_rna_enrichment",
	"cdna": "pecan_cdna_synthesis",
	"reference": "analogue_spruce_ctab_extraction",
	"caveat": "method_review_caveat",
}

## Short names for the process rail. The rail is the map of the whole workflow:
## four lanes, one per evidence class, so the direct/analogue split is visible
## before anything is read.
const STEP_SHORT := {
	"pecan_sample_handling": "Tissue handling",
	"pecan_trizol_extraction": "TRIzol extraction",
	"pecan_dnase_treatment": "DNase treatment",
	"pecan_quality_assessment": "Quality check",
	"pecan_small_rna_enrichment": "PAGE enrichment",
	"pecan_cdna_synthesis": "cDNA synthesis",
	"analogue_spruce_ctab_extraction": "Spruce CTAB",
	"analogue_spruce_phase_separation": "Spruce phase sep.",
	"analogue_spruce_licl_precipitation": "Spruce LiCl",
	"analogue_spruce_elution": "Spruce elution",
	"analogue_spruce_dnase": "Spruce DNase",
	"analogue_spruce_trizol_finding": "Spruce TRIzol result",
	"analogue_pigeonpea_ctab_extraction": "Pigeonpea CTAB",
	"analogue_pigeonpea_phase_separation": "Pigeonpea phase sep.",
	"analogue_pigeonpea_precipitation": "Pigeonpea precipitation",
	"analogue_pigeonpea_dnase": "Pigeonpea DNase",
	"analogue_pigeonpea_quality": "Pigeonpea results",
	"method_review_caveat": "No universal protocol",
}

const LANES := [
	{"title": "PECAN BENCH · direct evidence", "first": 0, "count": 6, "colour": GOOD},
	{"title": "NORWAY SPRUCE · analogue hypothesis", "first": 6, "count": 6, "colour": WARN},
	{"title": "PIGEONPEA · analogue hypothesis", "first": 12, "count": 5, "colour": WARN},
	{"title": "METHOD REVIEW · unresolved", "first": 17, "count": 1, "colour": METHOD},
]

const MODE_COLOURS := {
	"physical": GOOD,
	"observe": ACCENT,
	"analogue": WARN,
	"caveat": METHOD,
}

var _sim: PecanProcessSim
var _tabs: TabContainer
var _evidence: VBoxContainer
var _evidence_scroll: ScrollContainer
var _outputs: MarginContainer
var _limits: VBoxContainer
var _compare: VBoxContainer
var _play_button: Button
var _stage_chip: Label
var _stage_title: Label
var _timeline: HSlider
var _speed: OptionButton
var _stages_list: VBoxContainer
var _status: Label
var _detail: Label
var _follow: CheckButton
var _compare_a: OptionButton
var _compare_b: OptionButton
var _compare_body: VBoxContainer
var _branch_label: Label

var _model: Dictionary = {}
var _encoded: Dictionary = {}
var _simulation: Dictionary = {}
var _steps: Array = []
var _claims: Dictionary = {}
var _sources: Dictionary = {}
var _index := 0
var _playing := false
var _speed_factor := 1.0
var _clock := 0.0
var _auto_focus := true
var _focused_step := -1
var _shown_step := -1



func _ready() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.07, 0.08, 0.10)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)

	var split := HSplitContainer.new()
	split.set_anchors_preset(Control.PRESET_FULL_RECT)
	split.offset_left = 8.0
	split.offset_top = 8.0
	split.offset_right = -8.0
	split.offset_bottom = -8.0
	add_child(split)

	split.add_child(_left_column())
	var right := ScrollContainer.new()
	right.custom_minimum_size = Vector2(520, 0)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	split.add_child(right)
	right.add_child(_right_column())

	_load_case()
	if _steps.is_empty():
		return
	_clock = 0.0
	_apply_clock()


func _left_column() -> Control:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 4)

	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 10)
	var title := Label.new()
	title.text = "Pecan RNA extraction — 3D process replay"
	title.add_theme_font_size_override("font_size", 14)
	header.add_child(title)
	var note := Label.new()
	note.text = "evidence audit · step-indexed bench, not a molecular simulation"
	note.add_theme_font_size_override("font_size", 10)
	note.modulate = MUTED
	header.add_child(note)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var back := Button.new()
	back.text = "Back to workshop"
	back.pressed.connect(func() -> void: get_tree().change_scene_to_file.call_deferred("res://scenes/workshop.tscn"))
	header.add_child(back)
	column.add_child(header)

	_sim = PecanProcessSim.new()
	_sim.name = "PecanSim"
	_sim.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_sim.object_clicked.connect(_on_object_clicked)
	column.add_child(_sim)

	var hint := Label.new()
	hint.name = "InteractionHint"
	hint.text = ("Click a vessel, gel, block or card to inspect it · drag to orbit · "
		+ "scroll to zoom · click a step chip to run that step")
	hint.add_theme_font_size_override("font_size", 9)
	hint.modulate = MUTED
	column.add_child(hint)

	column.add_child(_transport())
	column.add_child(_stage_list())
	return column


func _transport() -> Control:
	var stack := VBoxContainer.new()
	stack.add_theme_constant_override("separation", 3)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	_play_button = Button.new()
	_play_button.name = "PlayButton"
	_play_button.text = "Play"
	_play_button.pressed.connect(_on_play_pressed)
	row.add_child(_play_button)

	var reset := Button.new()
	reset.name = "ResetButton"
	reset.text = "Reset"
	reset.pressed.connect(_on_reset_pressed)
	row.add_child(reset)

	var backward := Button.new()
	backward.name = "PreviousButton"
	backward.text = "‹ Step"
	backward.pressed.connect(func() -> void: select_stage(_index - 1))
	row.add_child(backward)

	var forward := Button.new()
	forward.name = "NextButton"
	forward.text = "Step ›"
	forward.pressed.connect(func() -> void: select_stage(_index + 1))
	row.add_child(forward)

	var speed_label := Label.new()
	speed_label.text = "Speed"
	speed_label.add_theme_font_size_override("font_size", 10)
	speed_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(speed_label)
	_speed = OptionButton.new()
	_speed.name = "SpeedSelector"
	for pair in [["0.5x", 0.5], ["1x", 1.0], ["2x", 2.0], ["4x", 4.0]]:
		_speed.add_item(str(pair[0]))
		_speed.set_item_metadata(_speed.item_count - 1, pair[1])
	_speed.select(1)
	_speed.item_selected.connect(_on_speed_selected)
	row.add_child(_speed)

	_stage_chip = Label.new()
	_stage_chip.name = "StageChip"
	_stage_chip.text = "step 0 of 0"
	_stage_chip.add_theme_font_size_override("font_size", 11)
	_stage_chip.modulate = ACCENT
	row.add_child(_stage_chip)

	_follow = CheckButton.new()
	_follow.name = "FollowCamera"
	_follow.text = "Follow"
	_follow.button_pressed = true
	_follow.tooltip_text = "Glide the camera to the station of the current step"
	_follow.toggled.connect(_on_follow_toggled)
	row.add_child(_follow)
	stack.add_child(row)

	_timeline = HSlider.new()
	_timeline.name = "StageTimeline"
	_timeline.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_timeline.min_value = 0.0
	_timeline.max_value = PecanProcessSim.TOTAL_SECONDS
	_timeline.step = 0.05
	_timeline.value_changed.connect(_on_scrub)
	stack.add_child(_timeline)

	_stage_title = Label.new()
	_stage_title.name = "StageTitle"
	_stage_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_stage_title.add_theme_font_size_override("font_size", 11)
	stack.add_child(_stage_title)
	return stack


## The process rail: one row per evidence lane. The rows are deliberately not a
## single flat list — the split between the six pecan bench steps and the eleven
## transferred steps is the central fact of this case.
func _stage_list() -> Control:
	var scroll := ScrollContainer.new()
	scroll.name = "ProcessRail"
	scroll.custom_minimum_size = Vector2(0, 150)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_stages_list = VBoxContainer.new()
	_stages_list.name = "StageList"
	_stages_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_stages_list.add_theme_constant_override("separation", 2)
	scroll.add_child(_stages_list)
	return scroll


func _populate_rail() -> void:
	for lane_index in LANES.size():
		var lane: Dictionary = LANES[lane_index]
		var row := HBoxContainer.new()
		row.name = "Lane%d" % lane_index
		row.add_theme_constant_override("separation", 3)
		var label := Label.new()
		label.text = str(lane["title"])
		label.custom_minimum_size = Vector2(168, 0)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.add_theme_font_size_override("font_size", 8)
		label.modulate = lane["colour"]
		row.add_child(label)
		for offset in int(lane["count"]):
			var index: int = int(lane["first"]) + offset
			var step: Dictionary = _steps[index]
			var chip := Button.new()
			chip.name = "Stage%dButton" % index
			chip.alignment = HORIZONTAL_ALIGNMENT_LEFT
			chip.text = "%d %s" % [index + 1, str(STEP_SHORT.get(str(step.get("step_id", "")), step.get("label", "")))]
			chip.tooltip_text = "%s\n%s" % [str(step.get("label", "")), str(step.get("step_id", ""))]
			chip.add_theme_font_size_override("font_size", 9)
			chip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			chip.modulate = MODE_COLOURS.get(_mode_of(step), Color.WHITE)
			chip.pressed.connect(select_stage.bind(index))
			row.add_child(chip)
		_stages_list.add_child(row)


func _right_column() -> Control:
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_tabs = TabContainer.new()
	_tabs.custom_minimum_size = Vector2(500, 620)
	box.add_child(_tabs)

	_evidence_scroll = ScrollContainer.new()
	_evidence_scroll.name = "StageEvidence"
	_evidence_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var evidence_pad := MarginContainer.new()
	evidence_pad.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	evidence_pad.add_theme_constant_override("margin_left", 4)
	evidence_pad.add_theme_constant_override("margin_right", 10)
	_evidence = VBoxContainer.new()
	_evidence.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_evidence.add_theme_constant_override("separation", 4)
	evidence_pad.add_child(_evidence)
	_evidence_scroll.add_child(evidence_pad)
	_tabs.add_child(_evidence_scroll)

	_compare = VBoxContainer.new()
	_compare.name = "CompareProtocols"
	_compare.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_compare.add_theme_constant_override("separation", 4)
	_tabs.add_child(_compare)

	_outputs = MarginContainer.new()
	_outputs.name = "WorkflowOutputs"
	_tabs.add_child(_outputs)

	var limits_scroll := ScrollContainer.new()
	limits_scroll.name = "Limitations"
	limits_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_limits = VBoxContainer.new()
	_limits.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	limits_scroll.add_child(_limits)
	_tabs.add_child(limits_scroll)

	_status = Label.new()
	_status.name = "ReplayStatus"
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_font_size_override("font_size", 9)
	_status.modulate = MUTED
	box.add_child(_status)
	return box



# ------------------------------------------------------------------- loading


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	if parsed is Dictionary:
		return parsed
	return {}


func _case_dir() -> String:
	var primary := RUNS_DIR.path_join(CASE_ID)
	if FileAccess.file_exists(primary.path_join("model_spec.json")):
		return primary
	return WEB_FALLBACK_DIR


func _load_case() -> void:
	var base := _case_dir()
	_model = _read_json(base.path_join("model_spec.json"))
	_encoded = _read_json(base.path_join("research_encoded.json"))
	_simulation = _read_json(base.path_join("simulation_result.json"))
	_steps = _model.get("steps", [])
	for claim in _encoded.get("claims", []):
		_claims[str(claim.get("claim_id", ""))] = claim
	for source in _model.get("sources", []):
		_sources[str(source.get("source_id", ""))] = source

	_timeline.max_value = PecanProcessSim.TOTAL_SECONDS
	_timeline.visible = true
	_populate_rail()
	_build_compare()
	_render_outputs()
	_render_limitations()


func _render_outputs() -> void:
	for child in _outputs.get_children():
		_outputs.remove_child(child)
		child.queue_free()
	if _simulation.is_empty():
		var missing := Label.new()
		missing.text = "No simulation_result.json was found for this case."
		_outputs.add_child(missing)
		return
	var panel := ResultsPanel.new()
	panel.name = "Results"
	panel.setup(null)
	_outputs.add_child(panel)
	panel.show_results(_simulation)


func _render_limitations() -> void:
	var readiness: Dictionary = _model.get("readiness", {})
	var verification: Dictionary = _encoded.get("verification", {})
	_limits.add_child(_heading("What this replay is, and is not"))
	for line in [
		"This is an evidence audit of the literature, replayed over a schematic bench.",
		"It is not a validated quantitative RNA extraction model.",
		"No RNA yield, RIN, purity or degradation value is computed or shown.",
		"No molecular dynamics, concentration field or physical outcome is simulated.",
		"Six steps are pecan bench operations; eleven are analogue hypotheses that never move the bench.",
		"An unstated parameter stays unstated: the compare tab never substitutes an analogue value.",
		"The bench, the sample tint and the mode banner encode process state and evidence class only.",
	]:
		_limits.add_child(_paragraph("• " + line))
	_limits.add_child(_heading("Readiness recorded by the model"))
	_limits.add_child(_label(
		"target protocol complete: %s · target yield available: %s · analogue protocol available: %s"
		% [
			str(readiness.get("protocol_complete_for_target", "?")),
			str(readiness.get("quantitative_yield_available_for_target", "?")),
			str(readiness.get("analogue_protocol_available", "?")),
		], 9, WARN))
	_limits.add_child(_heading("Verification recorded by the workflow"))
	_limits.add_child(_label(
		"quotes verified: %s of %s · numbers verified: %s of %s · source-role ceiling: %s"
		% [
			str(verification.get("quotes_verified", "?")),
			str(verification.get("quotes_checked", "?")),
			str(verification.get("numeric_values_verified", "?")),
			str(verification.get("numeric_values_checked", "?")),
			str(verification.get("source_role_check", "?")),
		], 9, GOOD))
	_limits.add_child(_heading("Assumptions stated by the model"))
	for assumption in _model.get("assumptions", []):
		_limits.add_child(_paragraph("• " + str(assumption), MUTED))
	_limits.add_child(_heading("Unresolved questions (%d)" % len(_model.get("unknowns", []))))
	for question in _model.get("unknowns", []):
		_limits.add_child(_label("• " + str(question), 9, WARN))
	_limits.add_child(_heading("Artifacts on disk"))
	for name in ["model_spec.json", "research_encoded.json", "simulation_result.json"]:
		_limits.add_child(_label("• " + RUNS_DIR.path_join(CASE_ID).path_join(name), 8, MUTED))



# --------------------------------------------------------- compare protocols


func _build_compare() -> void:
	_clear(_compare)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_compare.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 5)
	scroll.add_child(box)

	box.add_child(_heading("Protocol alternatives — compare, do not predict"))
	box.add_child(_paragraph(
		"The pecan paper gives six bench steps. The remaining eleven steps are "
		+ "transferred from Norway spruce and pigeonpea. Choose one step from each "
		+ "side to see what the literature reports on each side and what stays "
		+ "unmeasured for pecan. Nothing here is applied to the pecan bench and no "
		+ "outcome is calculated."))

	var branch_row := HBoxContainer.new()
	branch_row.add_theme_constant_override("separation", 6)
	branch_row.add_child(_row_label("Focus the analogue kiosk:", 9, MUTED))
	for branch_name in ["spruce", "pigeonpea"]:
		var button := Button.new()
		button.name = "Branch%sButton" % branch_name.capitalize()
		button.text = branch_name.capitalize()
		button.pressed.connect(func() -> void: set_branch(branch_name))
		branch_row.add_child(button)
	_branch_label = _row_label("current analogue branch: spruce", 9, WARN)
	_branch_label.name = "BranchLabel"
	branch_row.add_child(_branch_label)
	box.add_child(branch_row)

	var selects := HBoxContainer.new()
	selects.add_theme_constant_override("separation", 6)
	selects.add_child(_row_label("Pecan bench step", 9, GOOD))
	_compare_a = OptionButton.new()
	_compare_a.name = "CompareA"
	_compare_a.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for index in 6:
		_compare_a.add_item("%d %s" % [index + 1, str(STEP_SHORT.get(str(_steps[index].get("step_id", "")), ""))])
		_compare_a.set_item_metadata(_compare_a.item_count - 1, index)
	_compare_a.item_selected.connect(_on_compare_changed)
	selects.add_child(_compare_a)

	selects.add_child(_row_label("Transferred step", 9, WARN))
	_compare_b = OptionButton.new()
	_compare_b.name = "CompareB"
	_compare_b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for index in range(6, _steps.size()):
		_compare_b.add_item("%d %s" % [index + 1, str(STEP_SHORT.get(str(_steps[index].get("step_id", "")), ""))])
		_compare_b.set_item_metadata(_compare_b.item_count - 1, index)
	_compare_b.item_selected.connect(_on_compare_changed)
	selects.add_child(_compare_b)
	box.add_child(selects)

	_compare_body = VBoxContainer.new()
	_compare_body.name = "CompareBody"
	_compare_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_compare_body.add_theme_constant_override("separation", 5)
	box.add_child(_compare_body)

	# sensible default: the pecan DNase step against the spruce DNase step
	select_compare(
		_sim.step_index_of("pecan_dnase_treatment"),
		_sim.step_index_of("analogue_spruce_dnase"))


func _on_compare_changed(_value: int) -> void:
	render_compare()


func set_branch(branch_name: String) -> void:
	_sim.set_branch(branch_name)
	if _branch_label != null:
		_branch_label.text = "current analogue branch: " + branch_name
	var first := _sim.first_step_for_branch(branch_name)
	if first < 0:
		return
	select_compare(selected_compare_a(), first)
	# Show the kiosk handling this branch without yanking the user off the
	# compare tab: only the bench clock and camera move.
	_playing = false
	_play_button.text = "Play"
	_clock = _sim.step_start(first)
	_apply_clock()
	_sim.focus_step(first)


func branch() -> String:
	return _sim.branch()


func select_compare(a_index: int, b_index: int) -> void:
	if _compare_a == null or _compare_b == null:
		return
	var a := clampi(a_index, 0, 5)
	var b := clampi(b_index, 6, _steps.size() - 1)
	for item in _compare_a.item_count:
		if int(_compare_a.get_item_metadata(item)) == a:
			_compare_a.select(item)
	for item in _compare_b.item_count:
		if int(_compare_b.get_item_metadata(item)) == b:
			_compare_b.select(item)
	render_compare()


func selected_compare_a() -> int:
	if _compare_a == null or _compare_a.selected < 0:
		return 2
	return int(_compare_a.get_item_metadata(_compare_a.selected))


func selected_compare_b() -> int:
	if _compare_b == null or _compare_b.selected < 0:
		return 10
	return int(_compare_b.get_item_metadata(_compare_b.selected))


func render_compare() -> void:
	if _compare_body == null or _steps.is_empty():
		return
	_clear(_compare_body)
	var a: Dictionary = _steps[selected_compare_a()]
	var b: Dictionary = _steps[selected_compare_b()]
	var caveat := _label(
		"Comparison only. No yield, RIN, purity, degradation or outcome is predicted, "
		+ "and the selected transferred step is never executed on the pecan bench.",
		9, WARN)
	caveat.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_compare_body.add_child(caveat)

	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 6)
	columns.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.add_child(_compare_column(a, "A · pecan bench", GOOD))
	columns.add_child(_compare_column(b, "B · transferred / unresolved", _claim_colour(_specificity(b))))
	_compare_body.add_child(columns)

	var note := _shared_parameter_note(a, b)
	if note != "":
		var panel := PanelContainer.new()
		var box := VBoxContainer.new()
		box.add_theme_constant_override("separation", 2)
		panel.add_child(box)
		box.add_child(_heading("What the other side would add"))
		box.add_child(_paragraph(note, WARN))
		_compare_body.add_child(panel)


func _compare_column(step: Dictionary, title: String, colour: Color) -> Control:
	var card := PanelContainer.new()
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.custom_minimum_size = Vector2(230, 0)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 2)
	card.add_child(box)
	box.add_child(_label(title, 9, colour))
	box.add_child(_paragraph(str(step.get("label", ""))))
	box.add_child(_paragraph(str(step.get("action", "")), MUTED))

	var reported: Array = []
	var unresolved: Array = []
	for parameter in step.get("parameters", []):
		if str(parameter.get("state", "")) == "reported":
			reported.append(parameter)
		else:
			unresolved.append(parameter)
	box.add_child(_label("Reported (%d)" % reported.size(), 9,
		GOOD if _mode_of(step) == "physical" else WARN))
	if reported.is_empty():
		box.add_child(_label("nothing stated for this parameter set", 9, MUTED))
	for parameter in reported:
		box.add_child(_label("• " + _parameter_text(parameter), 9, Color(0.87, 0.91, 0.97)))
	box.add_child(_label("Not reported / unresolved (%d)" % unresolved.size(), 9, WARN))
	for parameter in unresolved:
		box.add_child(_label("• " + _human(str(parameter.get("name", ""))), 9, MUTED))
	box.add_child(_label("Supporting passages: %d" % _claims_for(step).size(), 9, MUTED))
	return card


## What the compared step would add, and — just as important — why it cannot be
## treated as a pecan value. Computed from the artifacts, never inferred.
func _shared_parameter_note(a: Dictionary, b: Dictionary) -> String:
	var a_unknown: Array = []
	for parameter in a.get("parameters", []):
		if str(parameter.get("state", "")) != "reported":
			a_unknown.append(str(parameter.get("name", "")))
	var additions := PackedStringArray()
	for parameter in b.get("parameters", []):
		if str(parameter.get("state", "")) == "reported" and a_unknown.has(str(parameter.get("name", ""))):
			additions.append(_parameter_text(parameter))
	if additions.is_empty():
		return ""
	var scope := "the pecan source"
	if _mode_of(b) == "analogue":
		scope = "the %s protocol" % str(b.get("step_id", "")).replace("analogue_", "").split("_")[0]
	return ("For the parameters the pecan step leaves open, %s reports: %s. "
		+ "Those are not pecan measurements and do not show what pecan would do; "
		+ "they only show what a different species' protocol specifies.") % [
			scope, ", ".join(additions)]


func compare_text() -> String:
	var parts := PackedStringArray()
	_collect(_compare_body, parts)
	return "\n".join(parts)


static func _parameter_text(parameter: Dictionary) -> String:
	return "%s = %s %s" % [
		str(parameter.get("name", "")),
		str(parameter.get("value", "")),
		str(parameter.get("unit", ""))]


static func _specificity(step: Dictionary) -> String:
	var status := str(step.get("evidence_status", ""))
	if status.begins_with("direct"):
		return "target_organism"
	if status.begins_with("analogous"):
		return "analogous_species"
	return "method_review"


static func _mode_of(step: Dictionary) -> String:
	var step_id := str(step.get("step_id", ""))
	if step_id.begins_with("analogue_"):
		return "analogue"
	if step_id == "method_review_caveat":
		return "caveat"
	if step_id == "pecan_quality_assessment":
		return "observe"
	if step_id.begins_with("pecan_"):
		return "physical"
	var status := str(step.get("evidence_status", ""))
	if status.begins_with("analogous"):
		return "analogue"
	if status.begins_with("direct"):
		return "physical"
	return "caveat"



## Selecting a step is the primary interaction: it moves the bench to that step's
## slot, shows its evidence and glides the camera to its station.
func select_stage(index: int) -> void:
	if _steps.is_empty():
		return
	_index = clampi(index, 0, _steps.size() - 1)
	_clock = _sim.step_start(_index)
	_playing = false
	_play_button.text = "Play"
	_focused_step = -1
	_shown_step = -1
	_tabs.current_tab = 0
	_apply_clock()


## Jump the animation to the start of an operation and show its evidence.
func select_operation(index: int) -> void:
	var count := _sim.operation_count()
	var clamped := clampi(index, 0, count - 1)
	_clock = _sim.operation_start(clamped)
	_playing = false
	_play_button.text = "Play"
	_apply_clock()


func _apply_clock() -> void:
	_sim.apply_clock(_clock)
	var step := _sim.step_at(_clock)
	_index = clampi(step, 0, _steps.size() - 1)
	_stage_chip.text = "step %d of %d · %.1fs / %.0fs" % [
		step + 1, _sim.step_count(), _clock, _sim.total_seconds()]
	if not is_equal_approx(_timeline.value, _clock):
		_timeline.set_value_no_signal(_clock)
	_stage_title.text = "%s — %s" % [
		_sim.step_label(step), _class_label(_steps[_index])]
	_stage_title.modulate = MODE_COLOURS.get(_sim.step_mode(step), MUTED)
	if _shown_step != _index:
		_shown_step = _index
		_show_stage(_steps[_index])
		_highlight_stage_button()
	if _auto_focus and _focused_step != step:
		_focused_step = step
		_sim.focus_step(step)


func _on_follow_toggled(pressed: bool) -> void:
	_auto_focus = pressed
	_focused_step = -1
	if pressed:
		_sim.focus_step(_sim.step_at(_clock))


## A click on the bench is an inspection, not just a jump: the step is selected
## (which moves the clock to it and glides the camera to its station).
func _on_object_clicked(kind: String) -> void:
	var step_id := str(OBJECT_STEPS.get(kind, ""))
	if kind == "reference":
		var branch_first := _sim.first_step_for_branch(_sim.branch())
		if branch_first >= 0:
			step_id = str(_steps[branch_first].get("step_id", step_id))
	if step_id == "":
		return
	for index in _steps.size():
		if str(_steps[index].get("step_id", "")) == step_id:
			select_stage(index)
			_sim.focus_station(_sim.step_station(index))
			return


func _on_play_pressed() -> void:
	if _steps.is_empty():
		return
	if not _playing and _clock >= PecanProcessSim.TOTAL_SECONDS - 0.01:
		_clock = 0.0
		_apply_clock()
	_playing = not _playing
	_play_button.text = "Pause" if _playing else "Play"


func _on_reset_pressed() -> void:
	_playing = false
	_play_button.text = "Play"
	_clock = 0.0
	_apply_clock()


func _on_speed_selected(index: int) -> void:
	_speed_factor = float(_speed.get_item_metadata(index))


func _on_scrub(value: float) -> void:
	_playing = false
	_play_button.text = "Play"
	_clock = clampf(value, 0.0, PecanProcessSim.TOTAL_SECONDS)
	_apply_clock()


func _process(delta: float) -> void:
	if not _playing or _steps.is_empty():
		return
	_clock += delta * _speed_factor
	if _clock >= PecanProcessSim.TOTAL_SECONDS:
		_clock = PecanProcessSim.TOTAL_SECONDS
		_playing = false
		_play_button.text = "Play"
	_apply_clock()


func _highlight_stage_button() -> void:
	for index in _steps.size():
		var button := _stages_list.find_child("Stage%dButton" % index, true, false)
		if button is Button:
			var base: Color = MODE_COLOURS.get(_mode_of(_steps[index]), Color.WHITE)
			(button as Button).modulate = base.lightened(0.35) if index == _index else base.darkened(0.15)


# ------------------------------------------------------------ stage evidence


static func _mode_word(mode: String) -> String:
	match mode:
		"physical":
			return "PHYSICAL OPERATION · pecan bench — objects move"
		"observe":
			return "OBSERVATION / MEASUREMENT · instrument operated, no reading invented"
		"analogue":
			return "HYPOTHESIS / ANALOGUE · reported for another species, NOT pecan"
		_:
			return "UNRESOLVED / METHOD REVIEW · no universal protocol"


func _show_stage(step: Dictionary) -> void:
	_clear(_evidence)
	var step_id := str(step.get("step_id", ""))
	var mode := _mode_of(step)

	var mode_banner := Label.new()
	mode_banner.name = "ModeBanner"
	mode_banner.text = _mode_word(mode)
	mode_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	mode_banner.add_theme_font_size_override("font_size", 10)
	mode_banner.modulate = MODE_COLOURS.get(mode, MUTED)
	_evidence.add_child(mode_banner)

	_evidence.add_child(_heading(str(step.get("label", step_id))))
	var banner := Label.new()
	banner.name = "ClassBanner"
	banner.text = _class_label(step)
	banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	banner.add_theme_font_size_override("font_size", 10)
	banner.modulate = _class_colour(step)
	_evidence.add_child(banner)
	_evidence.add_child(_label("step id: %s · order %s" % [step_id, str(step.get("order", ""))], 9, MUTED))
	_evidence.add_child(_paragraph(str(step.get("action", ""))))
	if mode == "analogue":
		_evidence.add_child(_paragraph(
			"The bench does not perform this step. No pecan vessel moves, because the "
			+ "only support for it is a protocol or result reported in another species.",
			WARN))
	elif mode == "caveat":
		_evidence.add_child(_paragraph(
			"This is a review caveat, not an operation. It marks what the workflow "
			+ "cannot settle: which protocol is suitable for pecan, and whether any of "
			+ "them was tested on pecan.", METHOD))

	_evidence.add_child(_heading("Parameters"))
	var unknown_parameters: Array = []
	for parameter in step.get("parameters", []):
		if str(parameter.get("state", "")) == "reported":
			var provenance := "reported in the pecan methods"
			if mode == "analogue":
				provenance = "reported in the analogue source — not a pecan value"
			elif mode == "caveat":
				provenance = "reported in the review's cited studies — not a pecan value"
			_evidence.add_child(_label(
				"• %s = %s %s (%s)" % [
					_human(str(parameter.get("name", ""))),
					str(parameter.get("value")),
					str(parameter.get("unit", "")),
					provenance,
				], 9, Color(0.87, 0.91, 0.97)))
		else:
			unknown_parameters.append(parameter)
	if unknown_parameters.is_empty():
		if mode == "analogue":
			_evidence.add_child(_label(
				"every parameter of this analogue step is stated in its own source — "
				+ "none of them is a pecan measurement", 9, WARN))
		elif mode == "caveat":
			_evidence.add_child(_label(
				"every parameter here comes from the review's cited studies — "
				+ "none of them settles the pecan protocol", 9, METHOD))
		else:
			_evidence.add_child(_label("every parameter of this step is stated", 9, GOOD))
	else:
		_evidence.add_child(_label(
			"%d parameter(s) are not stated — press one to see why and who else reports it:"
			% unknown_parameters.size(), 9, WARN))
		for parameter in unknown_parameters:
			var button := Button.new()
			button.text = "• %s — not stated  ›" % _human(str(parameter.get("name", "")))
			button.alignment = HORIZONTAL_ALIGNMENT_LEFT
			button.flat = true
			button.add_theme_font_size_override("font_size", 9)
			button.modulate = WARN
			button.pressed.connect(_show_parameter_detail.bind(
				str(step.get("step_id", "")), str(parameter.get("name", ""))))
			_evidence.add_child(button)

	_detail = _label(
		"Press an unknown parameter to see its basis and whether another step reports it.",
		9, MUTED)
	_detail.name = "ParameterDetail"
	_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_evidence.add_child(_detail)

	var claims := _claims_for(step)
	_evidence.add_child(_heading("Supporting evidence (%d)" % claims.size()))
	for claim in claims:
		_evidence.add_child(_claim_card(claim))

	var questions: Array = step.get("unknowns", [])
	if not questions.is_empty():
		_evidence.add_child(_heading("Relevant uncertainty (%d)" % questions.size()))
		for question in questions:
			_evidence.add_child(_label("• " + str(question), 9, WARN))
	_status.text = (
		"Step %d of %d · %s · %s. The bench is an authored, illustrative animation: "
		+ "it shows the reported operations and their order, not calculated volumes, "
		+ "speeds or outcomes."
	) % [
		_sim.step_at(_clock) + 1, _sim.step_count(),
		_sim.step_label(_sim.step_at(_clock)), _class_label(step)]


## Show the basis behind one unresolved parameter and whether any other acquired
## source reports a value with the same name. Nothing is inferred or converted.
func _show_parameter_detail(step_id: String, name: String) -> void:
	var step := _step_by_id(step_id)
	var basis := ""
	for parameter in step.get("parameters", []):
		if str(parameter.get("name", "")) == name:
			basis = str(parameter.get("basis", "not stated by the acquired sources"))
			break
	var lines := PackedStringArray()
	lines.append("%s — %s" % [_human(name), basis])

	var elsewhere := PackedStringArray()
	for other in _steps:
		if str(other.get("step_id", "")) == step_id:
			continue
		for parameter in other.get("parameters", []):
			if str(parameter.get("name", "")) != name:
				continue
			if str(parameter.get("state", "")) == "reported":
				elsewhere.append("%s (%s): %s %s" % [
					str(STEP_SHORT.get(str(other.get("step_id", "")), str(other.get("step_id", "")))),
					_class_word(_specificity(other)),
					str(parameter.get("value")),
					str(parameter.get("unit", "")),
				])
	if elsewhere.is_empty():
		lines.append("No acquired source in this case reports a value with this name.")
	else:
		lines.append("The same parameter name is reported elsewhere in this case: "
			+ "; ".join(elsewhere) + ".")
		lines.append("Those values belong to the source species or to a review, not to pecan. "
			+ "Using one here would be an assumption, so the replay leaves it open.")
	if _detail != null:
		_detail.text = "\n".join(lines)
		_detail.modulate = Color(0.85, 0.90, 0.99)


func _step_by_id(step_id: String) -> Dictionary:
	for step in _steps:
		if str(step.get("step_id", "")) == step_id:
			return step
	return {}


func _claims_for(step: Dictionary) -> Array:
	var out: Array = []
	for claim_id in step.get("claim_ids", []):
		if _claims.has(str(claim_id)):
			out.append(_claims[str(claim_id)])
	return out


func _claim_card(claim: Dictionary) -> Control:
	var card := PanelContainer.new()
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	card.add_child(box)
	box.add_child(_label(
		"%s · %s%s" % [
			_class_word(str(claim.get("specificity", ""))),
			str(claim.get("claim_type", "")),
			" · hypothesis" if bool(claim.get("hypothesis", false)) else "",
		], 9, _claim_colour(str(claim.get("specificity", "")))))

	box.add_child(_paragraph(" ".join([
		str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", "")),
	]).strip_edges()))

	var quote := Label.new()
	quote.name = "Quote"
	quote.text = "“%s”" % str(claim.get("quote", ""))
	quote.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	quote.add_theme_font_size_override("font_size", 9)
	quote.modulate = Color(0.80, 0.86, 0.94)
	box.add_child(quote)

	var source: Dictionary = _sources.get(str(claim.get("source_id", "")), {})
	box.add_child(_label(
		"%s — DOI %s — %s %s" % [
			str(source.get("title", str(claim.get("source_id", "")))),
			str(source.get("doi", "")),
			str(source.get("journal", "")),
			str(source.get("year", "")),
		], 8, MUTED))
	box.add_child(_label(
		"section: %s · organism: %s · uncertainty: %s" % [
			str(claim.get("section", "")),
			str(claim.get("organism", "")),
			str(claim.get("uncertainty", "")) if str(claim.get("uncertainty", "")) != "" else "—",
		], 8, MUTED))
	return card



# ------------------------------------------------------------------- helpers


static func _class_of(step: Dictionary) -> String:
	var status := str(step.get("evidence_status", ""))
	if status.begins_with("direct"):
		return "direct"
	if status.begins_with("analogous"):
		return "analogue"
	return "method_review"


static func _class_label(step: Dictionary) -> String:
	var status := str(step.get("evidence_status", ""))
	if status.begins_with("direct"):
		return "direct evidence — quoted from the pecan paper"
	if status.begins_with("analogous"):
		return "analogue hypothesis — transferred from another species; NOT validated on pecan"
	return "method review — neither a pecan measurement nor a species-specific protocol"


static func _class_colour(step: Dictionary) -> Color:
	var status := str(step.get("evidence_status", ""))
	if status.begins_with("direct"):
		return GOOD
	if status.begins_with("analogous"):
		return WARN
	return METHOD


static func _claim_colour(specificity: String) -> Color:
	if specificity == "target_organism":
		return GOOD
	if specificity == "analogous_species":
		return WARN
	return METHOD


static func _class_word(specificity: String) -> String:
	if specificity == "target_organism":
		return "direct (pecan)"
	if specificity == "analogous_species":
		return "analogous species"
	if specificity == "method_review":
		return "method review"
	return specificity


static func _human(name: String) -> String:
	return name.replace("_", " ")


func _heading(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	return label


func _paragraph(text: String, colour: Color = Color(0.87, 0.91, 0.97)) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	return label


func _label(text: String, size: int = 9, colour: Color = Color(0.87, 0.91, 0.97)) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", size)
	label.modulate = colour
	return label


func _row_label(text: String, size: int = 9, colour: Color = Color(0.87, 0.91, 0.97)) -> Label:
	var label := _label(text, size, colour)
	label.autowrap_mode = TextServer.AUTOWRAP_OFF
	label.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	return label


func _clear(parent: Node) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()


# --------------------------------------------------------------- harness API

func stage_count() -> int:
	return _steps.size()


func current_stage() -> int:
	return _index


func sim() -> PecanProcessSim:
	return _sim


func clock() -> float:
	return _clock


func operation_count() -> int:
	return _sim.operation_count() if _sim != null else 0


func probes() -> Dictionary:
	return _sim.probes() if _sim != null else {}


func advance(seconds: float) -> void:
	_clock = clampf(_clock + seconds, 0.0, PecanProcessSim.TOTAL_SECONDS)
	_apply_clock()


func evidence_text() -> String:
	var parts := PackedStringArray()
	_collect(_evidence, parts)
	return "\n".join(parts)


func _collect(node: Node, parts: PackedStringArray) -> void:
	if node is Label:
		parts.append(str((node as Label).text))
	elif node is Button:
		parts.append(str((node as Button).text))
	for child in node.get_children():
		_collect(child, parts)


func step_count() -> int:
	return _steps.size()


func step_id_at(index: int) -> String:
	return _sim.step_id(index) if _sim != null else ""


func step_mode_at(index: int) -> String:
	return _sim.step_mode(index) if _sim != null else ""


func step_label_at(index: int) -> String:
	return _sim.step_label(index) if _sim != null else ""


func mode_of(step_id: String) -> String:
	var step := _step_by_id(step_id)
	return _mode_of(step) if not step.is_empty() else ""


func select_step_id(step_id: String) -> void:
	for index in _steps.size():
		if str(_steps[index].get("step_id", "")) == step_id:
			select_stage(index)
			return


func parameter_detail_text() -> String:
	return _detail.text if _detail != null else ""


func select_parameter(step_id: String, name: String) -> void:
	_show_parameter_detail(step_id, name)


func chip_count() -> int:
	var count := 0
	for index in _steps.size():
		if _stages_list.find_child("Stage%dButton" % index, true, false) != null:
			count += 1
	return count


func focus_target() -> Vector3:
	return _sim.camera_goal()["target"]


func total_seconds() -> float:
	return _sim.total_seconds() if _sim != null else PecanProcessSim.TOTAL_SECONDS


func play() -> void:
	if not _playing:
		_on_play_pressed()


func pause() -> void:
	if _playing:
		_on_play_pressed()


func is_playing() -> bool:
	return _playing


func outputs_panel() -> ResultsPanel:
	for child in _outputs.get_children():
		if child is ResultsPanel:
			return child
	return null


func limitations_text() -> String:
	var parts := PackedStringArray()
	_collect(_limits, parts)
	return "\n".join(parts)

