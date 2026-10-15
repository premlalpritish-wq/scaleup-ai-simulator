extends Control
## 3D replay of the Zielinski recombinant-human-insulin process.
##
## Scope, stated up front because it governs everything below:
##
## The Zielinski model is an **evidence replay**, not a simulator. It publishes
## no kinetic parameter and no spatial field, so nothing here integrates an
## equation over time and nothing here draws a computed concentration, velocity
## or oxygen distribution. What the scene animates is the one time series the
## model actually publishes -- the digitized Fig. 3 growth curve -- and every
## number on screen is read from a named output port.
##
## Layout is a numbered reading order, left column then right:
##   1  reactor and operating conditions
##   2  culture growth over time
##   3  purification results
##   4  what this model cannot tell us
##   5  detailed evidence and technical diagnostics (collapsed by default)
##
## Plain-language labels are used throughout. The exact schema field names
## (`provenance`, port ids, the provenance chain) stay available in section 5.
##
## Execution reuses the composition runner through `CompositionRunner`, the same
## boundary the graph editor uses. The call is asynchronous so the window keeps
## repainting while Python runs.

const GRAPH_PATH := "res://composition/replay/zielinski_replay.json"
const INSTANCE_ID := "zielinski_replay"
const RESULT_DIR := "user://results"

## Replay speed: culture-hours per real second at 1x.
const HOURS_PER_SECOND := 1.7
const EXEC_TIMEOUT_MS := 180000

## Plain-language stand-ins for the model's provenance vocabulary. The schema
## names are unchanged underneath and are shown in section 5.
const PROVENANCE_PLAIN := {
	"reported": "stated in the source",
	"digitized": "read from a published figure",
	"derived": "calculated from the available data",
	"unknown": "not established by the available evidence",
}
const PROVENANCE_COLOUR := {
	"reported": Color(0.80, 0.84, 0.90),
	"digitized": Color(0.72, 0.82, 0.97),
	"derived": Color(0.66, 0.92, 0.68),
	"unknown": Color(0.95, 0.70, 0.58),
}

## Section 1. Operating conditions, all reported by the source.
const KEY_CONDITIONS := [
	["Working culture volume", "node:N01#starting_medium_volume"],
	["Nominal vessel volume", "node:N01#fermenter_nominal_volume"],
	["Fermenter temperature", "node:N01#fermenter_temperature"],
	["Peak density stated in the text", "node:N01#od600_max"],
]
## Section 2. Growth milestones the model itself interpolates.
const KEY_GROWTH := [
	["Time to reach OD600 = 25", "stream:S02_culture_broth#od600_25_crossing_h"],
	["Time to reach OD600 = 50", "stream:S02_culture_broth#od600_50_crossing_h"],
]
## Section 3. Purification and product characterisation.
const KEY_PURIFICATION := [
	["Wet biomass recovered", "node:N02#wet_biomass_g_per_L"],
	["Inclusion bodies", "node:N03#inclusion_bodies_g_per_L"],
	["Total biological activity", "node:N15#batch_activity"],
	["Mass deviation from theory", "node:N15#mass_deviation_ppm"],
]
## Section 4. Absent from the model -- surfaced, never worked around.
const KEY_ABSENT := [
	["Growth rate", "node:N01#specific_growth_rate"],
	["Dissolved oxygen", "node:N01#dissolved_oxygen"],
	["Induction time", "node:N01#induction_time"],
]

var _runner: CompositionRunner = null
var _data := ReplayData.new()

var _view: ReplayVesselView
var _growth: GrowthChart
var _cascade: CascadeChart

var _status: Label
var _clock: Label
var _busy: Label
var _state_chip: Label
var _progress: ProgressBar
var _od_readout: Label
var _od_unit: Label
var _od_note: Label
var _key_grid: GridContainer
var _growth_grid: GridContainer
var _purify_grid: GridContainer
var _absent_grid: GridContainer
var _absent_action: VBoxContainer
var _evidence: ReplayEvidencePanel
var _proposal_log: RichTextLabel
var _tree: Tree
var _detail: RichTextLabel
var _diagnostics: RichTextLabel
var _filter: OptionButton
var _speed: OptionButton

var _btn_start: Button
var _btn_pause: Button
var _btn_reset: Button

var _pid := -1
var _exec_started_ms := 0
var _result_path := ""

## Asynchronous handle for the evidence catalogue, kept separate from the
## model run so a slow catalogue never delays or corrupts the model result.
var _evidence_pid := -1
var _evidence_result_path := ""
var _evidence_open_request := ""
var _evidence_started_ms := 0
const EVIDENCE_TIMEOUT_MS := 60000

var _playing := false
var _hour := 0.0
var _speed_scale := 1.0
var _executed := false


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_runner = CompositionRunner.new("python", _detect_composition_dir())
	add_child(_runner)
	_build_ui()
	_reset_replay_clock()
	_set_state("Not run yet", "press Run model to execute the model")
	_start_execution()


# ------------------------------------------------------------------- layout

func _detect_composition_dir() -> String:
	var root := ProjectSettings.globalize_path("res://")
	for candidate in [root.path_join("composition"), root]:
		var dir := DirAccess.open(candidate)
		if dir != null and dir.file_exists("composition/runner.py"):
			return candidate
	return ""


func _build_ui() -> void:
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
	# The left column carries sections 1-3 and can exceed the window height, so
	# it scrolls. The 3D view consumes the wheel for zoom and calls
	# accept_event(), so orbiting and zooming still work inside it.
	var left_scroll := ScrollContainer.new()
	left_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	split.add_child(left_scroll)
	left_scroll.add_child(_build_left_column())

	var right_scroll := ScrollContainer.new()
	right_scroll.custom_minimum_size = Vector2(560, 0)
	right_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	split.add_child(right_scroll)
	right_scroll.add_child(_build_right_column())


# ------------------------------------------------- 1, 2, 3 : the main column

func _build_left_column() -> Control:
	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left.add_theme_constant_override("separation", 5)
	left.custom_minimum_size = Vector2(560, 0)

	# ---- 1. reactor and operating conditions ---------------------------
	left.add_child(_numbered_header("1", "Reactor and operating conditions"))

	_view = ReplayVesselView.new()
	_view.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_view.size_flags_stretch_ratio = 2.0
	_view.custom_minimum_size = Vector2(480, 250)
	left.add_child(_view)

	left.add_child(_note(
		"Schematic. The vessel is drawn at the stated working volume; the liquid's colour "
		+ "encodes the published density reading. It is not a simulated flow or concentration field."))

	_key_grid = _make_grid()
	left.add_child(_key_grid)

	# ---- 2. culture growth over time -----------------------------------
	left.add_child(_numbered_header("2", "Culture growth over time"))

	var readout := HBoxContainer.new()
	readout.add_theme_constant_override("separation", 8)
	left.add_child(readout)

	_od_readout = Label.new()
	_od_readout.name = "OdReadout"
	_od_readout.text = "Density: --"
	_od_readout.add_theme_font_size_override("font_size", 20)
	readout.add_child(_od_readout)

	_od_unit = Label.new()
	_od_unit.name = "OdUnit"
	_od_unit.text = ""
	_od_unit.add_theme_font_size_override("font_size", 12)
	_od_unit.modulate = Color(1, 1, 1, 0.7)
	readout.add_child(_od_unit)

	_od_note = Label.new()
	_od_note.name = "OdNote"
	_od_note.add_theme_font_size_override("font_size", 10)
	_od_note.modulate = Color(1, 1, 1, 0.6)
	_od_note.custom_minimum_size = Vector2(280, 0)
	_od_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	readout.add_child(_od_note)

	_clock = Label.new()
	_clock.name = "ClockLine"
	_clock.add_theme_font_size_override("font_size", 13)
	left.add_child(_clock)

	_growth = GrowthChart.new()
	_growth.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.add_child(_growth)

	left.add_child(_note(
		"OD600 (optical density at 600 nm) is a quick light-scattering measurement used as a "
		+ "proxy for how dense the culture is. It is not a concentration: nothing in this model "
		+ "converts it to grams per litre."))

	_growth_grid = _make_grid()
	left.add_child(_growth_grid)

	# ---- 3. purification results ---------------------------------------
	left.add_child(_numbered_header("3", "Purification results"))

	_cascade = CascadeChart.new()
	_cascade.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.add_child(_cascade)

	left.add_child(_note(
		"AU (absorbance units) is what the spectrophotometer read. The instrument was blanked "
		+ "with water, so AU is relative to this instrument and cannot be converted to a protein "
		+ "concentration, a molarity or a mass."))

	_purify_grid = _make_grid()
	left.add_child(_purify_grid)

	return left


# ------------------------------------------- 4, 5 : evidence and limitations

func _build_right_column() -> Control:
	var right := VBoxContainer.new()
	right.custom_minimum_size = Vector2(540, 0)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 6)

	# ---- title ---------------------------------------------------------
	var title := Label.new()
	title.text = "Replay published experiment"
	title.add_theme_font_size_override("font_size", 18)
	right.add_child(title)

	var subtitle := Label.new()
	subtitle.text = "Recombinant human insulin from Escherichia coli — Zieliński et al. (2019)"
	subtitle.add_theme_font_size_override("font_size", 11)
	subtitle.modulate = Color(1, 1, 1, 0.65)
	right.add_child(subtitle)

	var banner := Label.new()
	banner.text = ("This is a replay of numbers the model read out of a published paper. "
		+ "It is not a predictive simulation: the paper reports no growth kinetics, no oxygen "
		+ "transfer data and no spatial fields, so nothing here forecasts a new batch.")
	banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	banner.custom_minimum_size = Vector2(520, 0)
	banner.add_theme_font_size_override("font_size", 10)
	banner.modulate = Color(0.98, 0.86, 0.66)
	right.add_child(_framed(banner, Color(0.98, 0.86, 0.66, 0.16)))

	# ---- playback controls ---------------------------------------------
	right.add_child(_transport_row())

	_status = Label.new()
	_status.name = "StatusLine"
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.custom_minimum_size = Vector2(520, 0)
	_status.add_theme_font_size_override("font_size", 10)
	_status.modulate = Color(1, 1, 1, 0.7)
	right.add_child(_status)

	# ---- 4. what this model cannot tell us -----------------------------
	right.add_child(_numbered_header("4", "What this model cannot tell us"))
	right.add_child(_note(
		"These quantities were asked for and are genuinely unknown. The model refuses to "
		+ "substitute zero or a guess, and nothing on this screen is derived from them. "
		+ "Choose one below to see what the published literature can and cannot supply."))
	_absent_grid = _make_grid()
	right.add_child(_absent_grid)

	# The action that replaces the dead end. One button per unknown quantity,
	# built by _rebuild_key_panel once the model has reported.
	_absent_action = VBoxContainer.new()
	_absent_action.add_theme_constant_override("separation", 3)
	right.add_child(_absent_action)

	_proposal_log = RichTextLabel.new()
	_proposal_log.bbcode_enabled = true
	_proposal_log.fit_content = true
	_proposal_log.custom_minimum_size = Vector2(0, 0)
	_proposal_log.add_theme_font_size_override("normal_font_size", 10)
	_proposal_log.modulate.a = 0.0
	right.add_child(_proposal_log)

	_evidence = ReplayEvidencePanel.new()
	_evidence.name = "EvidencePanel"
	_evidence.proposal_requested.connect(_on_proposal_requested)
	right.add_child(_evidence)

	# ---- 5. detailed evidence ------------------------------------------
	right.add_child(_numbered_header("5", "Detailed evidence and technical diagnostics"))

	# Both evidence sections start closed. The default view is a short answer to
	# "what does this experiment show"; the full contract-level detail is one
	# click away and nothing is removed.
	var evidence := _collapsible("All data and evidence", false)
	right.add_child(evidence["box"])
	evidence["body"].add_child(_note(
		"Every value the model published, with the exact field names used by the data contract. "
		+ "Select a row to see its method, its source and its full provenance chain."))
	evidence["body"].add_child(_glossary())
	evidence["body"].add_child(_filter_row())

	_tree = Tree.new()
	_tree.columns = 3
	_tree.column_titles_visible = true
	_tree.set_column_title(0, "output port")
	_tree.set_column_title(1, "value")
	_tree.set_column_title(2, "provenance")
	_tree.set_column_custom_minimum_width(0, 240)
	_tree.set_column_custom_minimum_width(1, 165)
	_tree.set_column_custom_minimum_width(2, 95)
	_tree.set_column_expand(0, true)
	_tree.set_column_expand(1, false)
	_tree.set_column_expand(2, false)
	_tree.custom_minimum_size = Vector2(0, 210)
	_tree.item_selected.connect(_on_output_selected)
	evidence["body"].add_child(_tree)

	_detail = RichTextLabel.new()
	_detail.bbcode_enabled = true
	_detail.fit_content = true
	_detail.custom_minimum_size = Vector2(0, 96)
	_detail.scroll_active = false
	_detail.add_theme_font_size_override("normal_font_size", 10)
	evidence["body"].add_child(_detail)

	var technical := _collapsible("Run status and technical details", false)
	right.add_child(technical["box"])
	_diagnostics = RichTextLabel.new()
	_diagnostics.bbcode_enabled = true
	_diagnostics.fit_content = true
	_diagnostics.custom_minimum_size = Vector2(0, 130)
	_diagnostics.add_theme_font_size_override("normal_font_size", 10)
	technical["body"].add_child(_diagnostics)

	return right


# ------------------------------------------------------------- small builders

func _numbered_header(number: String, text: String) -> Control:
	var box := HBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	var n := Label.new()
	n.text = number
	n.add_theme_font_size_override("font_size", 15)
	n.modulate = Color(0.42, 0.62, 0.86)
	box.add_child(n)
	var t := Label.new()
	t.text = text
	t.add_theme_font_size_override("font_size", 15)
	t.modulate = Color(0.82, 0.88, 0.96)
	box.add_child(t)
	var rule := Control.new()
	rule.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_child(rule)
	return box


func _note(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 10)
	l.modulate = Color(1, 1, 1, 0.52)
	l.custom_minimum_size = Vector2(500, 0)
	return l


func _make_grid() -> GridContainer:
	var g := GridContainer.new()
	g.columns = 2
	g.add_theme_constant_override("h_separation", 10)
	g.add_theme_constant_override("v_separation", 2)
	return g


## A framed block with a tinted background, used for the honesty banner.
func _framed(content: Control, tint: Color) -> Control:
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = tint
	style.set_corner_radius_all(4)
	style.content_margin_left = 8.0
	style.content_margin_right = 8.0
	style.content_margin_top = 6.0
	style.content_margin_bottom = 6.0
	panel.add_theme_stylebox_override("panel", style)
	panel.add_child(content)
	return panel


## A toggleable section. Returns {"box": Control, "body": Control}.
func _collapsible(title: String, open_by_default: bool) -> Dictionary:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 3)

	var body := VBoxContainer.new()
	body.visible = open_by_default
	body.add_theme_constant_override("separation", 4)

	var head := Button.new()
	head.toggle_mode = true
	head.button_pressed = open_by_default
	head.alignment = HORIZONTAL_ALIGNMENT_LEFT
	head.text = ("▾  " if open_by_default else "▸  ") + title
	head.add_theme_font_size_override("font_size", 12)
	# `toggled` carries the new state, so the body follows the button.
	#
	# The previous handler was wired to `pressed` and only rewrote the caption;
	# it never touched `body.visible`, which was set once at construction and
	# never again. The caption changed, the panel did not -- so expanding a
	# collapsed section appeared to work while revealing nothing. The body is
	# declared before the connection so the lambda cannot capture it unset.
	head.toggled.connect(func(on: bool) -> void:
		body.visible = on
		head.text = ("▾  " if on else "▸  ") + title)
	box.add_child(head)
	box.add_child(body)
	return {"box": box, "body": body, "head": head}


func _transport_row() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	# The playback state is the single thing a first-time reader looks for, so it
	# gets a coloured chip rather than being buried in a status line.
	var chip := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.20, 0.24, 0.30)
	style.set_corner_radius_all(4)
	style.content_margin_left = 10.0
	style.content_margin_right = 10.0
	style.content_margin_top = 5.0
	style.content_margin_bottom = 5.0
	chip.add_theme_stylebox_override("panel", style)
	_state_chip = Label.new()
	_state_chip.name = "StateChip"
	_state_chip.text = "Not run yet"
	_state_chip.add_theme_font_size_override("font_size", 12)
	chip.add_child(_state_chip)
	chip.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(chip)

	_btn_start = Button.new()
	_btn_start.text = "Run model"
	_btn_start.tooltip_text = "Execute the process model and load its published values"
	_btn_start.pressed.connect(_on_start_pressed)
	row.add_child(_btn_start)

	_btn_pause = Button.new()
	_btn_pause.text = "Pause"
	_btn_pause.tooltip_text = "Freeze or resume the replay"
	_btn_pause.disabled = true
	_btn_pause.pressed.connect(_on_pause_pressed)
	row.add_child(_btn_pause)

	_btn_reset = Button.new()
	_btn_reset.text = "Reset"
	_btn_reset.tooltip_text = "Return the replay to the start of the published batch"
	_btn_reset.pressed.connect(_on_reset_pressed)
	row.add_child(_btn_reset)

	var speed_label := Label.new()
	speed_label.text = "Playback speed"
	speed_label.add_theme_font_size_override("font_size", 10)
	speed_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(speed_label)

	var speed_gap := Control.new()
	speed_gap.custom_minimum_size = Vector2(6, 0)
	row.add_child(speed_gap)

	_speed = OptionButton.new()
	for pair in [["0.5x", 0.5], ["1x", 1.0], ["2x", 2.0], ["4x", 4.0]]:
		_speed.add_item(str(pair[0]))
		_speed.set_item_metadata(_speed.item_count - 1, pair[1])
	_speed.select(1)
	_speed.item_selected.connect(_on_speed_selected)
	row.add_child(_speed)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)

	var back := Button.new()
	back.text = "Back to graph editor"
	back.pressed.connect(_on_back_pressed)
	row.add_child(back)

	_busy = Label.new()
	_busy.name = "BusyLine"
	_busy.text = ""
	_busy.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_busy.add_theme_font_size_override("font_size", 10)
	_busy.modulate = Color(1, 1, 1, 0.6)
	_busy.custom_minimum_size = Vector2(520, 0)

	_progress = ProgressBar.new()
	_progress.max_value = 100.0
	_progress.show_percentage = false

	var stack := VBoxContainer.new()
	stack.add_child(row)
	stack.add_child(_progress)
	stack.add_child(_busy)
	return stack


func _filter_row() -> Control:
	var row := HBoxContainer.new()
	var fl := Label.new()
	fl.text = "Show only "
	fl.add_theme_font_size_override("font_size", 10)
	row.add_child(fl)
	_filter = OptionButton.new()
	_filter.name = "ProvenanceFilter"
	for name in ["all outputs", "stated in the source", "read from a published figure",
			"calculated", "not established"]:
		_filter.add_item(name)
	_filter.item_selected.connect(_on_filter_selected)
	row.add_child(_filter)
	return row


func _glossary() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	var heading := Label.new()
	heading.text = "What the labels on every value mean"
	heading.add_theme_font_size_override("font_size", 10)
	heading.modulate = Color(0.66, 0.80, 0.96)
	box.add_child(heading)
	var lines := PackedStringArray([
		"stated in the source — the number appears in the published paper (schema field: reported)",
		"read from a published figure — the number was measured off a graph in the paper (schema field: digitized)",
		"calculated from the available data — the model computed it from stated inputs (schema field: derived)",
		"not established by the available evidence — the paper does not say, so no value is shown (schema field: unknown)",
	])
	for line in lines:
		var l := Label.new()
		l.text = "•  " + line
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.add_theme_font_size_override("font_size", 9)
		l.modulate = Color(1, 1, 1, 0.6)
		l.custom_minimum_size = Vector2(500, 0)
		box.add_child(l)
	return box


# --------------------------------------------------------------- execution

func _on_start_pressed() -> void:
	if _pid > 0:
		return
	if _executed:
		_playing = true
		_btn_pause.disabled = false
		_btn_pause.text = "Pause"
		_set_state("Playing", "replaying the published growth curve")
		return
	_start_execution()


func _start_execution() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(RESULT_DIR))
	_result_path = RESULT_DIR.path_join("%s.result.json" % INSTANCE_ID)
	if FileAccess.file_exists(_result_path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(_result_path))

	var argv := _runner.prepare(PackedStringArray([
		"-m", "composition.runner",
		"--graph", GRAPH_PATH,
		"--result", _result_path,
	]))
	_btn_start.disabled = true
	_btn_pause.disabled = true
	_set_state("Running the model", "this window stays live while the model executes")
	_progress.value = 0.0
	var pid := OS.create_process(_runner.python_executable(), argv)
	if pid <= 0:
		_finish_execution(-1)
		return
	_pid = pid
	_exec_started_ms = Time.get_ticks_msec()


func _poll_execution() -> void:
	if _pid <= 0:
		return
	_progress.value = 5.0 + 90.0 * (float(Time.get_ticks_msec() - _exec_started_ms) / float(EXEC_TIMEOUT_MS))
	if Time.get_ticks_msec() - _exec_started_ms > EXEC_TIMEOUT_MS:
		OS.kill(_pid)
		_pid = -1
		_finish_execution(-2)
		return
	if OS.is_process_running(_pid):
		return
	var code := OS.get_process_exit_code(_pid)
	_pid = -1
	_finish_execution(code)


func _finish_execution(code: int) -> void:
	_progress.value = 100.0
	var payload := _runner.read_result(_result_path)
	_data = ReplayData.new()
	_data.load_payload(payload, INSTANCE_ID)
	_data.exit_code = code
	_executed = true

	_view.set_fill_fraction(_data.fill_fraction())
	_growth.set_data(_data)
	_cascade.set_data(_data)
	_rebuild_key_panel()
	_rebuild_tree()
	_render_diagnostics(payload, code)

	_btn_start.disabled = false
	_btn_pause.disabled = false

	# The replay always starts at the documented initial state.
	_reset_replay_clock()
	_status.text = _headline()
	if code == 0:
		_playing = true
		_btn_pause.text = "Pause"
		_set_state("Playing", "replaying the published growth curve")
	elif code == -1:
		_playing = false
		_btn_pause.text = "Pause"
		_set_state("Run failed", "the model process could not be started")
	elif code == -2:
		_playing = false
		_btn_pause.text = "Pause"
		_set_state("Run failed", "the model exceeded %d s and was stopped" % (EXEC_TIMEOUT_MS / 1000))
	else:
		_playing = false
		_btn_pause.text = "Pause"
		_set_state("Run failed", "the model reported a failure — open Run status and technical details")


func _headline() -> String:
	if _data.raw_outputs.is_empty():
		return "No values were published. Open Run status and technical details for the reason."
	var counts := []
	for k in ["reported", "derived", "digitized", "unknown"]:
		var n := int(_data.provenance_counts.get(k, 0))
		if n > 0:
			counts.append("%d %s" % [n, str(PROVENANCE_PLAIN.get(k, k))])
	return "%d published values: %s." % [_data.raw_outputs.size(), "; ".join(counts)]


## Single source of truth for what the transport controls are doing.
func _set_state(state: String, detail: String) -> void:
	_state_chip.text = state
	var tint := Color(0.20, 0.24, 0.30)
	match state:
		"Playing":
			tint = Color(0.16, 0.32, 0.22)
		"Paused":
			tint = Color(0.34, 0.28, 0.12)
		"Replay complete":
			tint = Color(0.20, 0.26, 0.36)
		"Run failed":
			tint = Color(0.36, 0.16, 0.16)
		"Running the model":
			tint = Color(0.14, 0.22, 0.34)
	var style := StyleBoxFlat.new()
	style.bg_color = tint
	style.set_corner_radius_all(4)
	style.content_margin_left = 10.0
	style.content_margin_right = 10.0
	style.content_margin_top = 5.0
	style.content_margin_bottom = 5.0
	var chip: Variant = _state_chip.get_parent()
	if chip is PanelContainer:
		(chip as PanelContainer).add_theme_stylebox_override("panel", style)
	_busy.text = detail


# ------------------------------------------------------------------- replay

func _on_pause_pressed() -> void:
	_playing = not _playing
	_btn_pause.text = "Pause" if _playing else "Resume"
	if _playing:
		_set_state("Playing", "replaying the published growth curve")
	else:
		_set_state("Paused", "the culture time is held where you paused it")


func _on_reset_pressed() -> void:
	_playing = false
	_btn_pause.text = "Pause"
	_reset_replay_clock()
	_view.reset_camera()
	_status.text = _headline()
	_set_state("Paused", "returned to the start of the published batch")


func _on_back_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/composition.tscn")


func _on_speed_selected(index: int) -> void:
	_speed_scale = float(_speed.get_item_metadata(index))


func _reset_replay_clock() -> void:
	_hour = 0.0
	_growth.set_cursor(0.0, false)
	_view.set_turbidity(0.0)
	_od_readout.text = "Density: not shown"
	_od_unit.text = ""
	_od_note.text = ""
	_update_clock()


func _advance(delta: float) -> void:
	if not _playing or not _executed:
		return
	if not _data.has_trajectory():
		return
	_hour += delta * HOURS_PER_SECOND * _speed_scale
	var last := _data.hours[_data.hours.size() - 1]
	if _hour >= last:
		_hour = last
		_playing = false
		_btn_pause.text = "Resume"
		_set_state("Replay complete", "reached the last published culture hour")
	_growth.set_cursor(_hour, true)

	var sample := _data.sample_at(_hour)
	if sample.has("od") and not is_nan(float(sample["od"])):
		var od := float(sample["od"])
		var ref_max := _data.od600_max_reported
		if is_nan(ref_max) or ref_max <= 0.0:
			ref_max = _data.max_od()
		_view.set_turbidity(od / maxf(ref_max, 0.0001))
		_od_readout.text = "Density  %s" % ReplayData.format_number(od)
		_od_unit.text = "OD600"
		_od_note.text = str(sample.get("note", ""))
	else:
		_od_readout.text = "Density  not shown"
		_od_unit.text = ""
		_od_note.text = "outside the published culture hours"
	_update_clock()


func _update_clock() -> void:
	if not _executed:
		_clock.text = "Culture time: not available"
		return
	if not _data.has_trajectory():
		_clock.text = "Culture time: not available (the model published no growth curve)"
		return
	var first := int(_data.hours[0])
	var last := int(_data.hours[_data.hours.size() - 1])
	if _hour <= 0.0:
		_clock.text = "Culture time  0 hours   (before the first published reading, at %d h)" % first
	else:
		_clock.text = "Culture time  %s hours   (within the published %d–%d hour batch)" % [
			ReplayData.format_number(_hour), first, last]


func _process(delta: float) -> void:
	_poll_execution()
	_poll_evidence()
	_advance(delta)


## The explicit action. It records an intent and changes nothing: no value, no
## model, no published evidence. The gap stays open until someone builds and
## validates a separate parameterised model.
func _on_proposal_requested(target_id: String, target_label: String) -> void:
	# `%` binds tighter than `+`, so the substitution has to be parenthesised;
	# otherwise the first fragment ships with its placeholders unformatted.
	var line := ("[b]Proposed:[/b] a separate model or parameter set for '%s' (%s). "
		+ "Recorded as an action only - no value was proposed, nothing was merged, "
		+ "and the model still reports this as unknown.") % [
			_bb(target_label), _bb(target_id)]
	_proposal_log.text = _proposal_log.text + line + "\n"
	_proposal_log.modulate.a = 1.0


# -------------------------------------------------------------------- panels

func _rebuild_key_panel() -> void:
	for c in _key_grid.get_children():
		c.queue_free()
	for c in _growth_grid.get_children():
		c.queue_free()
	for c in _purify_grid.get_children():
		c.queue_free()
	for c in _absent_grid.get_children():
		c.queue_free()
	for c in _absent_action.get_children():
		c.queue_free()
	var by_port := {}
	for o in _data.raw_outputs:
		by_port[str((o.get("ref", {}) as Dictionary).get("port_id", ""))] = o.get("value", {})

	for entry in KEY_CONDITIONS:
		_kv(_key_grid, by_port, str(entry[0]), str(entry[1]))
	for entry in KEY_GROWTH:
		_kv(_growth_grid, by_port, str(entry[0]), str(entry[1]))
	for entry in KEY_PURIFICATION:
		_kv(_purify_grid, by_port, str(entry[0]), str(entry[1]))
	for entry in KEY_ABSENT:
		_kv(_absent_grid, by_port, str(entry[0]), str(entry[1]))
		_investigate_button(str(entry[1]), str(entry[0]))


## The action that turns a dead end into an investigation. It opens the
## evidence panel; it never proposes a value and never changes the model.
func _investigate_button(port_id: String, caption: String) -> void:
	var b := Button.new()
	b.text = "Investigate: %s" % caption
	b.add_theme_font_size_override("font_size", 10)
	b.pressed.connect(func() -> void: _on_investigate_pressed(port_id))
	_absent_action.add_child(b)


func _on_investigate_pressed(port_id: String) -> void:
	if _evidence == null:
		return
	if _evidence.has_catalogue():
		_evidence.open_target(port_id)
		return
	_evidence_open_request = port_id
	_status.text = "Loading the evidence catalogue..."
	_start_evidence_catalogue()


## Load the curated catalogue through the same verified boundary the model run
## uses, and with the same `--result <path>` file contract, so the payload is
## read from disk rather than captured from a subprocess's stdout.
func _start_evidence_catalogue() -> void:
	if _evidence_pid > 0:
		return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(RESULT_DIR))
	_evidence_result_path = RESULT_DIR.path_join("evidence_catalogue.json")
	if FileAccess.file_exists(_evidence_result_path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(_evidence_result_path))
	var argv := _runner.prepare(PackedStringArray([
		"-m", "composition.evidence",
		"--result", _evidence_result_path,
	]))
	_evidence_pid = OS.create_process(_runner.python_executable(), argv)
	_evidence_started_ms = Time.get_ticks_msec()


func _poll_evidence() -> void:
	if _evidence_pid <= 0:
		return
	if OS.is_process_running(_evidence_pid):
		if Time.get_ticks_msec() - _evidence_started_ms > EVIDENCE_TIMEOUT_MS:
			OS.kill(_evidence_pid)
			_evidence_pid = -1
			_status.text = "The evidence catalogue did not load within %d s." % (
				EVIDENCE_TIMEOUT_MS / 1000)
		return
	var code := OS.get_process_exit_code(_evidence_pid)
	_evidence_pid = -1
	if code != 0:
		_status.text = "The evidence catalogue could not be built (exit %d)." % code
		return
	if apply_evidence_catalogue(_read_text_file(_evidence_result_path)):
		_status.text = ""
		if not _evidence_open_request.is_empty():
			var port := _evidence_open_request
			_evidence_open_request = ""
			_evidence.open_target(port)
	else:
		_status.text = "The evidence catalogue was produced but could not be read."


func _read_text_file(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return ""
	var text := f.get_as_text()
	f.close()
	return text


## Load an already-captured catalogue payload, used by the harness and by any
## caller that already has the JSON.
func apply_evidence_catalogue(text: String) -> bool:
	if _evidence == null:
		return false
	var json := JSON.new()
	if json.parse(text) != OK:
		return false
	var data: Variant = json.get_data()
	if not data is Dictionary:
		return false
	_evidence.set_catalogue(data)
	return true


## One key/value row. A quantity the model could not establish is reported as
## unknown, with the model's own sentence -- never as zero or a placeholder.
func _kv(grid: GridContainer, by_port: Dictionary, caption: String, port_id: String) -> void:
	var v: Dictionary = by_port.get(port_id, {})
	var name_label := Label.new()
	name_label.text = caption
	name_label.add_theme_font_size_override("font_size", 11)
	name_label.custom_minimum_size = Vector2(215, 0)

	var value_label := Label.new()
	value_label.add_theme_font_size_override("font_size", 11)
	value_label.custom_minimum_size = Vector2(290, 0)
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	var prov := str(v.get("provenance", ""))
	if v.is_empty():
		value_label.text = "not published by the model"
		value_label.modulate = Color(0.95, 0.70, 0.58)
	elif not bool(v.get("is_resolved", false)) or v.get("value") == null:
		value_label.text = "Not known.  " + _shorten(str(v.get("reason", "")), 120)
		value_label.modulate = Color(0.95, 0.70, 0.58)
	elif prov == "":
		value_label.text = ReplayData.describe_value(v)
		value_label.modulate = Color(0.88, 0.92, 0.98)
	else:
		value_label.text = "%s   %s" % [ReplayData.describe_value(v), str(PROVENANCE_PLAIN.get(prov, prov))]
		value_label.modulate = PROVENANCE_COLOUR.get(prov, Color(0.88, 0.92, 0.98))
	grid.add_child(name_label)
	grid.add_child(value_label)


## Clip on a word boundary and mark that the text continues.
static func _shorten(text: String, limit: int) -> String:
	var clean := text.strip_edges()
	if clean.length() <= limit:
		return clean
	var cut := clean.substr(0, limit)
	var sp := cut.rfind(" ")
	if sp > limit / 2:
		cut = cut.substr(0, sp)
	return cut + " ..."


func _on_filter_selected(_index: int) -> void:
	_rebuild_tree()


## The dropdown now offers plain-language names; map them back to the schema
## values the contract actually uses.
func _selected_provenance() -> String:
	if _filter.selected < 0:
		return ""
	match _filter.selected:
		1: return "reported"
		2: return "digitized"
		3: return "derived"
		4: return "unknown"
	return ""


func _rebuild_tree() -> void:
	_tree.clear()
	var root := _tree.create_item()
	var wanted := _selected_provenance()
	var shown := 0
	for o in _data.raw_outputs:
		var ref: Dictionary = o.get("ref", {})
		var v: Dictionary = o.get("value", {})
		var prov := str(v.get("provenance", "?"))
		if wanted != "" and prov != wanted:
			continue
		var item := _tree.create_item(root)
		item.set_text(0, str(ref.get("port_id", "")))
		item.set_text(1, _tree_value(v))
		item.set_text(2, prov)
		item.set_metadata(0, str(ref.get("port_id", "")))
		item.set_custom_color(2, PROVENANCE_COLOUR.get(prov, Color(0.80, 0.82, 0.86)))
		if prov == "unknown":
			item.set_custom_color(1, Color(0.95, 0.70, 0.58))
		shown += 1

	# An empty table with no explanation reads as a rendering failure, so the
	# absence of evidence is stated in the pane itself.
	if shown == 0:
		var item := _tree.create_item(root)
		item.set_text(0, "no evidence records available")
		item.set_text(1, "-")
		item.set_text(2, "-")
		item.set_custom_color(2, Color(0.62, 0.66, 0.72))
		item.set_selectable(0, false)

	# A dataset change must never leave the previous dataset's row in the pane.
	# The waiting state is written unconditionally rather than only when the pane
	# is empty, because "empty" and "still showing the last row" are different
	# things and only the first looks like a broken pane.
	_detail.text = ("[color=#8892a0]Select a row above to see its method, its "
		+ "source and its full provenance chain.[/color]")


## Compact value for the one-line tree cell. The full reason sentence is shown
## in the detail pane below, so the column stays a fixed width.
static func _tree_value(v: Dictionary) -> String:
	if v.is_empty():
		return "--"
	if not bool(v.get("is_resolved", false)) or v.get("value") == null:
		return "not available"
	if v.get("value") is Array:
		return "range, not collapsed"
	return "%s %s" % [ReplayData.format_number(float(v["value"])), str(v.get("unit", ""))]


func _on_output_selected() -> void:
	var item := _tree.get_selected()
	if item == null:
		return
	var port_id := str(item.get_metadata(0))
	for o in _data.raw_outputs:
		if str((o.get("ref", {}) as Dictionary).get("port_id", "")) != port_id:
			continue
		var v: Dictionary = o.get("value", {})
		var prov := str(v.get("provenance", ""))
		var lines := PackedStringArray()
		lines.append("[b]%s[/b]   — %s" % [_bb(port_id), str(PROVENANCE_PLAIN.get(prov, prov))])
		lines.append("contract fields   provenance: %s    unit: %s    is_resolved: %s" % [
			_bb(prov), _bb(str(v.get("unit", ""))), str(bool(v.get("is_resolved", false)))])
		lines.append("value: %s %s" % [ReplayData.format_number(_as_float(v.get("value"))), _bb(str(v.get("unit", "")))])
		if str(v.get("method", "")) != "":
			lines.append("method: %s" % _bb(str(v.get("method", ""))))
		if str(v.get("source_ref", "")) != "":
			lines.append("source: %s" % _bb(str(v.get("source_ref", ""))))
		if str(v.get("reason", "")) != "":
			lines.append("[color=#f2a887]why it is unknown: %s[/color]" % _bb(str(v.get("reason", ""))))
		for link in o.get("provenance_chain", []):
			lines.append("chain: %s %s" % [_bb(str((link as Dictionary).get("producer_model", ""))),
				_bb(str((link as Dictionary).get("producer_version", "")))])
			lines.append("   where: %s" % _bb(str((link as Dictionary).get("where", ""))))
			lines.append("   detail: %s" % _bb(str((link as Dictionary).get("detail", ""))))
			lines.append("   source_ref: %s" % _bb(str((link as Dictionary).get("source_ref", ""))))
			# The pane is a contract between the tree and the reader. Leaving it blank
		# until a row is chosen is indistinguishable from a broken pane, so the
		# waiting state is written out too.
		if _detail.text == "":
			_detail.text = ("[color=#8892a0]Select a row above to see its method, its "
				+ "source and its full provenance chain.[/color]")
		_detail.text = "\n".join(lines)
		return


static func _as_float(v: Variant) -> float:
	if v is float or v is int:
		return float(v)
	return NAN


## Escape model-supplied text for BBCode.
##
## Diagnostics routinely contain square brackets -- the cycle message names its
## participants as `['stage_a', 'stage_b']` -- and a RichTextLabel would parse
## those as markup and silently swallow the rest of the sentence. `[lb]` is
## Godot's escape for a literal bracket.
static func _bb(text: String) -> String:
	return str(text).replace("[", "[lb]")


func _render_diagnostics(payload: Dictionary, code: int) -> void:
	var lines := PackedStringArray()

	# --- did we get a result document at all? -------------------------------
	if payload.is_empty():
		_diagnostics.text = "\n".join(PackedStringArray([
			"[b]No result document.[/b]",
			"[color=#f08a7a]The runner wrote nothing to %s, so there is no status, no "
			% _result_path,
			"diagnostics and no evidence to show. Run this by hand to see the traceback:[/color]",
			"[code]%s -m composition.runner --graph %s --result %s[/code]" % [
				_runner.python_executable(), GRAPH_PATH, _result_path],
		]))
		return

	lines.append("[b]exit code %d[/b]" % code)

	# --- run metadata -------------------------------------------------------
	# Every field below is read from the document. A field the document does not
	# carry is reported as unavailable, which is a different statement from a
	# run that succeeded with nothing to report.
	lines.append("")
	lines.append("[b]run[/b]")
	var status := str(payload.get("status", ""))
	lines.append("  status            %s" % (
		_bb(status) if status != "" else _UNRECORDED))
	lines.append("  run id            %s" % _present(payload, "run_id"))
	lines.append("  graph id          %s" % _present(payload, "graph_id"))
	lines.append("  contract version  %s" % _present(payload, "contract_version"))
	lines.append("  runner version    %s" % _present(payload, "runner_version"))
	var repro := str(payload.get("reproducibility", ""))
	lines.append("  graph digest      %s" % (
		_bb(repro.substr(0, 24) + "...") if repro != "" else _UNRECORDED))
	var versions: Dictionary = payload.get("model_versions", {})
	if versions.is_empty():
		lines.append("  model versions    %s" % _UNRECORDED)
	else:
		var parts := PackedStringArray()
		for k in versions.keys():
			parts.append("%s %s" % [_bb(str(k)), _bb(str(versions[k]))])
		lines.append("  model versions    %s" % ", ".join(parts))

	# --- diagnostics --------------------------------------------------------
# An absent "diagnostics" key and an empty list are different facts. The
	# first means the document does not have the shape this panel expects, and
	# is reported as such rather than rendered as a clean run.
	if not payload.has("diagnostics"):
		var present := PackedStringArray()
		for k in payload.keys():
			present.append(str(k))
		lines.append("")
		lines.append("[b]diagnostics[/b]")
		lines.append("  [color=#f08a7a]This result document has no 'diagnostics' field. "
			+ "The runner and this panel both expect it, so the diagnostic content "
			+ "cannot be shown. This is a schema mismatch, not a clean run.[/color]")
		lines.append("  top-level fields present: %s" % _bb(", ".join(present)))
		_diagnostics.text = "\n".join(lines)
		return

	var diags: Array = payload.get("diagnostics", [])
	var errors := 0
	var warnings := 0
	var malformed := 0
	for d in diags:
		var rec: Dictionary = d if d is Dictionary else {}
		if rec.is_empty():
			# A diagnostic entry that is not a Dictionary is a schema mismatch in
			# its own right. Naming it is more useful than skipping it, which
			# would render the run as clean.
			malformed += 1
			continue
		var sev := str(rec.get("severity", ""))
		if sev == "error":
			errors += 1
		elif sev == "warning":
			warnings += 1

	lines.append("")
	lines.append("[b]diagnostics[/b]   %d error, %d warning, %d total" % [
		errors, warnings, diags.size()])
	if malformed > 0:
		var noun := "y" if malformed == 1 else "ies"
		lines.append("  [color=#f08a7a]%d entr%s in 'diagnostics' is not a diagnostic "
			% [malformed, noun]
			+ "record and could not be read. Every entry must be an object with a "
			+ "'severity' and a 'message'. This is a schema mismatch, not a clean run.[/color]")
	if diags.is_empty():
		lines.append("  [color=#8fd18f]This run raised no diagnostics.[/color]")
	for d in diags:
		var rec: Dictionary = d if d is Dictionary else {}
		if rec.is_empty():
			malformed += 1
			continue
		var sev := str(rec.get("severity", ""))
		# The letters must not collide with BBCode tags: `[i]` is italic and
		# `[b]` is bold, so using them as severity letters leaves an unmatched
		# close tag that renders literally. E / W / N are not tags.
		var tag := "E" if sev == "error" else ("W" if sev == "warning" else "N")
		var colour := "#f08a7a" if sev == "error" else ("#e8c07a" if sev == "warning" else "#9fb0c8")
		lines.append("[color=%s][b]%s[/b][/color] %s" % [
			colour, tag, _bb(str(rec.get("message", "")))])
		var origin := ("%s %s" % [str(rec.get("origin", "")), str(rec.get("model_id", ""))]).strip_edges()
		lines.append("      [color=#8892a0]code %s  origin %s  where %s[/color]" % [
			_bb(str(rec.get("code", ""))), _bb(origin), _bb(str(rec.get("where", "")))])
		var rem := str(rec.get("remediation", ""))
		if rem != "":
			lines.append("      [color=#8892a0]%s[/color]" % _bb(rem))

	_diagnostics.text = "\n".join(lines)


## Shown wherever the result document does not carry a field. Deliberately
## different wording from "no diagnostics", because the two mean different
## things: one is missing data, the other is a run that had nothing to say.
const _UNRECORDED := "[color=#e8c07a]not recorded in this document[/color]"


## A value the document actually carries, or an explicit statement that it does not.
func _present(payload: Dictionary, key: String) -> String:
	var v: Variant = payload.get(key, null)
	if v == null or str(v) == "":
		return _UNRECORDED
	return _bb(str(v))