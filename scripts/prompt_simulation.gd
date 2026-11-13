class_name PromptSimulationScene
extends Control
## Multi-paper central library bioprocess reconstruction and Godot 4 Forward+ 3D interactive interface.
## Features diegetic 3D HUD overlays, cinematic camera choreography, 5-stage factory stepper,
## 4 glowing KPI gauges, interactive process sandbox controls, slide-out scientific dossier drawer,
## game pause menu modal, and unmissable transport controls with keyboard shortcuts.

const RESULT_PATH := "user://prompt_run.json"
const GOOD := Color(0.20, 0.85, 0.55)
const WARN := Color(0.98, 0.75, 0.25)
const BAD := Color(0.95, 0.28, 0.28)
const MUTED := Color(0.60, 0.65, 0.72)
const BG_PANEL := Color(0.05, 0.07, 0.10, 0.88)
const INSTANCE_ID := "node:N01"

var _runner: CompositionRunner
var _view: ReplayVesselView
var _hud_overlay: Control
var _growth: GrowthChart
var _cascade: CascadeChart

# Top Stepper & Live Process Story
var _stepper_container: HBoxContainer
var _stepper_buttons: Array = []
var _story_banner: Label

# Bottom Translucent Control Dock & KPI Gauges
var _bottom_dock: PanelContainer
var _time_slider: HSlider
var _play_btn: Button
var _speed_btn: Button
var _restart_btn: Button
var _step_back_btn: Button
var _step_fwd_btn: Button
var _auto_cam_btn: Button
var _pause_menu_btn: Button
var _time_display: Label
var _readout: Label
var _delta_badge: Label
var _kpi_yield: Label
var _kpi_mw: Label
var _kpi_purity: Label
var _kpi_uts: Label

# Interactive Sandbox Mode Dock (Bottom-Left)
var _sandbox_panel: PanelContainer
var _sandbox_title_label: Label
var _bio_sandbox_box: VBoxContainer
var _smr_sandbox_box: VBoxContainer
var _sandbox_ph_btn: Button
var _sandbox_scale_btn: Button
var _sandbox_crosslink_btn: Button
var _sandbox_tension_slider: HSlider
var _sandbox_tension_label: Label
var _sandbox_banner: Label

# SMR Chemical Plant Interactive Controls & HAZOP Faults
var _smr_mode: bool = false
var _smr_sc_slider: HSlider
var _smr_sc_val: Label
var _smr_temp_slider: HSlider
var _smr_temp_val: Label
var _smr_press_slider: HSlider
var _smr_press_val: Label
var _smr_btn_e105: Button
var _smr_btn_coking: Button
var _smr_btn_purge: Button
var _smr_btn_xray: Button
var _xray_enabled: bool = true
var _smr_kpis_label: Label
var _smr_fault_state: Dictionary = {
	"e105_cooling_loss": false,
	"coking_warning": false,
	"n2_purge_active": false,
	"purity_pct": 99.0,
}

# Slide-Out Right Drawer (Scientific Dossier & Charts)
var _right_drawer: PanelContainer
var _drawer_toggle_btn: Button
var _is_drawer_open: bool = false
var _prompt: TextEdit
var _status: Label
var _sim_status: Label
var _confidence_badge: Label
var _top_reality_badge: Label
var _reality_compiler_badge: Label
var _sizing_table_label: Label
var _reality_compiler_audit: Dictionary = {}
var _runtime_law_violations: Array = []
var _analogue_banner: Label
var _generate: Button
var _interpret_only: Button
var _execute: Button
var _output_tree: Tree
var _manifest_body: VBoxContainer
var _interpretation_body: VBoxContainer
var _result_body: VBoxContainer
var _diagram_rect: TextureRect
var _hotswap_selector: OptionButton

# Async Stage Streaming & Stage-Normalized Playback Pacing
var _loading_panel: PanelContainer
var _loading_label: Label
var _loading_bar: ProgressBar
var _auto_pause_on_stage: bool = false
var _auto_pause_check: CheckBox
var _prev_stage_btn: Button
var _next_stage_btn: Button
var _is_stream_settled: bool = false

# Game Pause Menu Modal & Toast Notifications
var _pause_menu_modal: PanelContainer
var _pause_backdrop: ColorRect
var _toast_panel: PanelContainer
var _toast_label: Label
var _toast_tween: Tween

# Trajectory and Process State
var _request := ""
var _interpretation: Dictionary = {}
var _result: Dictionary = {}
var _data: ReplayData
var _active_trajectory: Dictionary = {}
var _ghost_trajectory: Dictionary = {}
var _current_model_label: String = "Active Bioprocess Model"
var _ghost_label: String = ""
var _active_run_manifest: Dictionary = {}
var _anatomy_blueprint: Dictionary = {}
var _unit_operations: Array = []
var _dynamic_badges: Array = []
var _selected_component: String = ""

var _current_sim_time: float = 0.0
var _sim_duration_hours: float = 40.0
var _is_playing: bool = false   # Starts paused at t = 0.0 h so user can inspect stage 0/1
var _play_speed: float = 1.0
var _auto_follow_cam: bool = true
var _last_stage_index: int = -1

# Sandbox runtime modifications
var _sandbox_ph_mode: int = 0         # 0: pH 7.0 (Neutralised), 1: pH 12.0 (Unneutralised)
var _sandbox_scale_mode: int = 0      # 0: Scaled-Up 15.0g (33.07%), 1: Small-Scale 2.5g (26.0%)
var _sandbox_crosslink_mode: int = 0  # 0: Pure (29.3 MPa), 1: Citric-Crosslinked (43.1 MPa), 2: Blended (42.1 MPa)
var _current_tension_load: float = 12.0

# Legacy compatibility badge references
var _badge_feed: Button
var _badge_broth: Button
var _badge_impeller: Button
var _badge_harvest: Button

# WebAssembly & JavaScriptBridge integration handles
var _js_preset_cb: Variant = null
var _js_json_cb: Variant = null
var _js_msg_cb: Variant = null


func _ready() -> void:
	DisplayServer.window_set_title("ScaleUp")
	# Full-screen 3D Viewport container (takes 100% of window, overlays sit on top)
	var main_stack := Control.new()
	main_stack.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(main_stack)

	_view = ReplayVesselView.new()
	_view.set_anchors_preset(Control.PRESET_FULL_RECT)
	main_stack.add_child(_view)
	_view.stage_clicked.connect(_on_stage_clicked)
	_view.fibre_snapped.connect(_on_fibre_snapped)
	_view.bench_build_progress.connect(_on_bench_build_progress)
	_view.bench_build_completed.connect(_on_bench_build_completed)

	_hud_overlay = Control.new()
	_hud_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	_hud_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main_stack.add_child(_hud_overlay)

	# 0. Sleek Translucent Stage Streaming Game Loading Overlay
	_loading_panel = _create_loading_overlay()
	main_stack.add_child(_loading_panel)

	# 1. Top HUD: 5-Stage Factory Stepper & Process Story Banner
	main_stack.add_child(_create_top_hud())

	# 2. Bottom-Left HUD: Interactive Process Sandbox Dock (Playable Science)
	main_stack.add_child(_create_sandbox_dock())

	# 3. Bottom HUD: Enhanced Timeline Transport Bar & 4 Glowing KPI Gauges
	main_stack.add_child(_create_bottom_hud())

	# 4. Slide-Out Right Drawer: Scientific Dossier & Detailed Charts
	main_stack.add_child(_create_right_drawer())

	# 5. On-Screen Floating Toast Notification
	main_stack.add_child(_create_toast_notification())

	# 6. Centered Modal Game Pause & Simulation Control Menu (ESC)
	main_stack.add_child(_create_pause_menu_modal())

	# Legacy floating badges for backwards compatibility
	_badge_feed = _create_callout_badge("feed_tube", "[Feed System] Feed F(t) • [DIRECT]", GOOD)
	_badge_broth = _create_callout_badge("culture_broth", "[Reaction Kinetics] Primary Yield • [DIRECT]", GOOD)
	_badge_impeller = _create_callout_badge("impeller_sparger", "[Gas Transport] DO / kLa • [VERIFIED]", WARN)
	_badge_harvest = _create_callout_badge("harvest_valve", "[Downstream] Product Harvest • [DIRECT]", Color(0.4, 0.8, 1.0))
	_hud_overlay.add_child(_badge_feed)
	_hud_overlay.add_child(_badge_broth)
	_hud_overlay.add_child(_badge_impeller)
	_hud_overlay.add_child(_badge_harvest)
	_badge_feed.visible = false
	_badge_broth.visible = false
	_badge_impeller.visible = false
	_badge_harvest.visible = false

	# Background Runner
	_runner = CompositionRunner.new("python", _detect_composition_dir())
	_runner.name = "PromptRunner"
	add_child(_runner)
	_runner.finished.connect(_on_runner_finished)
	_set_buttons(true)

	# Initialize Play button display for paused start
	_update_play_btn()
	_show_toast("⏸ Simulation Paused at t = 0.0 h — Press Space to Run", 2.5)

	if OS.has_feature("web"):
		_setup_web_integration()
	else:
		var run_file_path := _get_run_file_arg()
		if run_file_path != "":
			load_run_file(run_file_path)


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return

	match event.keycode:
		KEY_SPACE:
			_on_play_toggle()
			get_viewport().set_input_as_handled()
		KEY_LEFT:
			var target_h: float = maxf(_current_sim_time - 0.5, 0.0)
			_on_scrub(target_h)
			_show_toast("⏪ Scrub: %.1f h" % target_h)
			get_viewport().set_input_as_handled()
		KEY_RIGHT:
			var target_h2: float = minf(_current_sim_time + 0.5, _sim_duration_hours)
			_on_scrub(target_h2)
			_show_toast("⏩ Scrub: %.1f h" % target_h2)
			get_viewport().set_input_as_handled()
		KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6:
			var idx: int = event.keycode - KEY_1
			_jump_to_stage_by_index(idx)
			get_viewport().set_input_as_handled()
		KEY_ESCAPE:
			_toggle_pause_menu()
			get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	delta = minf(delta, 0.05)
	if _is_playing and _sim_duration_hours > 0.0:
		var cur_idx := _get_stage_index_at_hour(_current_sim_time)
		var local_rate: float = 1.6
		if cur_idx >= 0 and cur_idx < _unit_operations.size():
			var op: Dictionary = _unit_operations[cur_idx]
			var t_win: Array = op.get("time_window_h", [0.0, 10.0])
			var stage_dur: float = maxf(float(t_win[1]) - float(t_win[0]), 0.1)
			# Stage-Normalized Pacing: every stage receives ~10.0s comfortable real screen time at 1x
			local_rate = stage_dur / 10.0

		_current_sim_time += delta * _play_speed * local_rate

		# Auto-pause on stage complete if enabled
		if _auto_pause_on_stage and cur_idx >= 0 and cur_idx < _unit_operations.size():
			var op_cur: Dictionary = _unit_operations[cur_idx]
			var t_win_cur: Array = op_cur.get("time_window_h", [0.0, 40.0])
			var stage_end: float = float(t_win_cur[1])
			if _current_sim_time >= stage_end:
				_current_sim_time = stage_end
				_is_playing = false
				_update_play_btn()
				_show_toast("⏸ Stage %d Complete: %s (Auto-Paused)" % [cur_idx + 1, op_cur.get("title", "")], 3.5)

		if _current_sim_time > _sim_duration_hours:
			_current_sim_time = 0.0

		if _time_slider != null:
			_time_slider.set_value_no_signal(_current_sim_time)
		_apply_playback_time(_current_sim_time)

		# Auto-follow camera stage tracking & inter-stage transfer focus
		if _auto_follow_cam and not _unit_operations.is_empty():
			var tracking_idx := _get_stage_index_at_hour(_current_sim_time)
			if tracking_idx != _last_stage_index and tracking_idx >= 0:
				_last_stage_index = tracking_idx
				if _view != null and _view.has_method("smooth_focus_on_stage"):
					_view.smooth_focus_on_stage(tracking_idx)

	_update_floating_badges_positions()


func _get_stage_index_at_hour(hour: float) -> int:
	for i in range(_unit_operations.size()):
		var op: Dictionary = _unit_operations[i]
		var t_win: Array = op.get("time_window_h", [0, 40])
		if hour >= float(t_win[0]) and hour <= float(t_win[1]):
			return i
	return -1


func _jump_to_stage_by_index(idx: int) -> void:
	if idx >= 0 and idx < _unit_operations.size():
		var op: Dictionary = _unit_operations[idx]
		var stage_id: String = str(op.get("stage_id", "stage_%d" % idx))
		var title: String = str(op.get("title", stage_id))
		var t_win: Array = op.get("time_window_h", [0, 0])
		var target_h := float(t_win[0])
		_on_scrub(target_h)
		_on_stage_clicked(stage_id, idx)
		_show_toast("▶ Stage %d: %s (t = %.0f h)" % [idx + 1, title, target_h])


# ---------------------------------------------------------------- HUD Creation

func _create_top_hud() -> Control:
	var container := VBoxContainer.new()
	container.set_anchors_preset(Control.PRESET_TOP_WIDE)
	container.offset_left = 32
	container.offset_right = -32
	container.offset_top = 16
	container.add_theme_constant_override("separation", 6)
	container.mouse_filter = Control.MOUSE_FILTER_IGNORE

	var header_row := HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 12)
	container.add_child(header_row)

	var logo := Label.new()
	logo.text = "SCALEUP 3D"
	logo.add_theme_font_size_override("font_size", 16)
	logo.modulate = GOOD
	header_row.add_child(logo)

	_confidence_badge = Label.new()
	_confidence_badge.text = "[Confidence: 100% • DIRECT]"
	_confidence_badge.add_theme_font_size_override("font_size", 11)
	_confidence_badge.modulate = GOOD
	header_row.add_child(_confidence_badge)

	_top_reality_badge = Label.new()
	_top_reality_badge.text = "🟢 Reality Compiler: PASSED (6/6 Physical Laws Verified)"
	_top_reality_badge.add_theme_font_size_override("font_size", 11)
	_top_reality_badge.modulate = GOOD
	header_row.add_child(_top_reality_badge)

	_analogue_banner = Label.new()
	_analogue_banner.text = "⚠️ [ANALOGUE BRIDGE WARNING: Expert verification required]"
	_analogue_banner.add_theme_font_size_override("font_size", 11)
	_analogue_banner.modulate = BAD
	_analogue_banner.visible = false
	header_row.add_child(_analogue_banner)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_row.add_child(spacer)

	_drawer_toggle_btn = Button.new()
	_drawer_toggle_btn.text = "📊 View Scientific Dossier & Charts ⏵"
	_drawer_toggle_btn.pressed.connect(_toggle_right_drawer)
	header_row.add_child(_drawer_toggle_btn)

	var menu_top_btn := Button.new()
	menu_top_btn.text = "☰ Menu (ESC)"
	menu_top_btn.pressed.connect(_toggle_pause_menu)
	header_row.add_child(menu_top_btn)

	var reset_cam_btn := Button.new()
	reset_cam_btn.text = "🎥 Reset Camera"
	reset_cam_btn.pressed.connect(func() -> void: _view.reset_camera())
	header_row.add_child(reset_cam_btn)

	# Interactive 5-Stage Stepper
	_stepper_container = HBoxContainer.new()
	_stepper_container.alignment = BoxContainer.ALIGNMENT_CENTER
	_stepper_container.add_theme_constant_override("separation", 8)
	container.add_child(_stepper_container)

	# Live Process Story Banner
	_story_banner = Label.new()
	_story_banner.text = "Initialising bioprocess simulation..."
	_story_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_story_banner.add_theme_font_size_override("font_size", 12)
	_story_banner.modulate = Color(0.85, 0.92, 1.0)
	container.add_child(_story_banner)

	return container


func _create_bottom_hud() -> Control:
	_bottom_dock = PanelContainer.new()
	_bottom_dock.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_bottom_dock.offset_left = 320  # leaves room for bottom-left sandbox dock
	_bottom_dock.offset_right = -32
	_bottom_dock.offset_bottom = -16
	_bottom_dock.custom_minimum_size = Vector2(0, 105)

	var style := StyleBoxFlat.new()
	style.bg_color = BG_PANEL
	style.corner_radius_top_left = 8
	style.corner_radius_top_right = 8
	style.corner_radius_bottom_left = 8
	style.corner_radius_bottom_right = 8
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_color = Color(0.20, 0.28, 0.38)
	_bottom_dock.add_theme_stylebox_override("panel", style)

	var main_v := VBoxContainer.new()
	main_v.add_theme_constant_override("separation", 8)
	_bottom_dock.add_child(main_v)

	# Row 1: Comprehensive Timeline Transport Bar
	var transport_row := HBoxContainer.new()
	transport_row.add_theme_constant_override("separation", 8)
	main_v.add_child(transport_row)

	_restart_btn = Button.new()
	_restart_btn.text = "⏮ 0h"
	_restart_btn.custom_minimum_size = Vector2(48, 36)
	_restart_btn.tooltip_text = "Restart timeline from 0.0 h"
	_restart_btn.pressed.connect(func() -> void:
		_on_scrub(0.0)
		_show_toast("⏮ Restarted to t = 0.0 h")
	)
	transport_row.add_child(_restart_btn)

	_step_back_btn = Button.new()
	_step_back_btn.text = "⏪ -1h"
	_step_back_btn.custom_minimum_size = Vector2(52, 36)
	_step_back_btn.tooltip_text = "Step backward 1 hour"
	_step_back_btn.pressed.connect(func() -> void:
		var target_h: float = maxf(_current_sim_time - 1.0, 0.0)
		_on_scrub(target_h)
		_show_toast("⏪ -1.0 h (t = %.1f h)" % target_h)
	)
	transport_row.add_child(_step_back_btn)

	_prev_stage_btn = Button.new()
	_prev_stage_btn.text = "⏮ Prev Stage"
	_prev_stage_btn.custom_minimum_size = Vector2(96, 36)
	_prev_stage_btn.tooltip_text = "Jump to beginning of previous unit operation stage"
	_prev_stage_btn.pressed.connect(_on_prev_stage_clicked)
	transport_row.add_child(_prev_stage_btn)

	# High-Contrast Large Play / Pause Button
	_play_btn = Button.new()
	_play_btn.custom_minimum_size = Vector2(145, 36)
	_play_btn.tooltip_text = "Toggle simulation playback (Spacebar)"
	_play_btn.pressed.connect(_on_play_toggle)
	var play_style := StyleBoxFlat.new()
	play_style.bg_color = Color(0.12, 0.18, 0.26)
	play_style.corner_radius_top_left = 6
	play_style.corner_radius_top_right = 6
	play_style.corner_radius_bottom_left = 6
	play_style.corner_radius_bottom_right = 6
	play_style.border_width_left = 2
	play_style.border_width_right = 2
	play_style.border_width_top = 2
	play_style.border_width_bottom = 2
	play_style.border_color = Color(0.20, 0.85, 0.55)
	_play_btn.add_theme_stylebox_override("normal", play_style)
	transport_row.add_child(_play_btn)

	_step_fwd_btn = Button.new()
	_step_fwd_btn.text = "+1h ⏩"
	_step_fwd_btn.custom_minimum_size = Vector2(52, 36)
	_step_fwd_btn.tooltip_text = "Step forward 1 hour"
	_step_fwd_btn.pressed.connect(func() -> void:
		var target_h2: float = minf(_current_sim_time + 1.0, _sim_duration_hours)
		_on_scrub(target_h2)
		_show_toast("⏩ +1.0 h (t = %.1f h)" % target_h2)
	)
	transport_row.add_child(_step_fwd_btn)

	_next_stage_btn = Button.new()
	_next_stage_btn.text = "Next Stage ⏭"
	_next_stage_btn.custom_minimum_size = Vector2(96, 36)
	_next_stage_btn.tooltip_text = "Jump to next unit operation stage"
	_next_stage_btn.pressed.connect(_on_next_stage_clicked)
	transport_row.add_child(_next_stage_btn)

	_time_slider = HSlider.new()
	_time_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_time_slider.min_value = 0.0
	_time_slider.max_value = 40.0
	_time_slider.step = 0.1
	_time_slider.value_changed.connect(_on_scrub)
	transport_row.add_child(_time_slider)

	_time_display = Label.new()
	_time_display.text = "t = 0.0 h / 40.0 h"
	_time_display.custom_minimum_size = Vector2(130, 0)
	_time_display.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_time_display.add_theme_font_size_override("font_size", 12)
	_time_display.modulate = Color(0.35, 0.85, 1.0)
	transport_row.add_child(_time_display)

	_speed_btn = Button.new()
	_speed_btn.text = "1.0x"
	_speed_btn.custom_minimum_size = Vector2(46, 36)
	_speed_btn.tooltip_text = "Cycle simulation speed (0.5x, 1.0x, 2.0x, 4.0x)"
	_speed_btn.pressed.connect(_on_speed_toggle)
	transport_row.add_child(_speed_btn)

	_auto_cam_btn = Button.new()
	_auto_cam_btn.text = "🎥 Follow: ON"
	_auto_cam_btn.custom_minimum_size = Vector2(98, 36)
	_auto_cam_btn.tooltip_text = "Toggle cinematic camera auto-follow along the process stages"
	_auto_cam_btn.modulate = GOOD
	_auto_cam_btn.pressed.connect(_toggle_auto_cam)
	transport_row.add_child(_auto_cam_btn)

	_auto_pause_check = CheckBox.new()
	_auto_pause_check.text = "Auto-Pause Stage"
	_auto_pause_check.tooltip_text = "Automatically pause simulation when each bioprocess stage finishes"
	_auto_pause_check.button_pressed = false
	_auto_pause_check.toggled.connect(func(pressed: bool) -> void:
		_auto_pause_on_stage = pressed
		_show_toast("Auto-Pause on Stage: %s" % ("ENABLED" if pressed else "DISABLED"), 1.8)
	)
	transport_row.add_child(_auto_pause_check)

	_pause_menu_btn = Button.new()
	_pause_menu_btn.text = "☰ Menu (ESC)"
	_pause_menu_btn.custom_minimum_size = Vector2(98, 36)
	_pause_menu_btn.tooltip_text = "Open Game Pause & Simulation Control Menu"
	_pause_menu_btn.pressed.connect(_toggle_pause_menu)
	transport_row.add_child(_pause_menu_btn)

	# Row 2: 4 Big Glowing KPI Gauges & Live Parameter Readout
	var kpi_row := HBoxContainer.new()
	kpi_row.add_theme_constant_override("separation", 16)
	main_v.add_child(kpi_row)

	_kpi_yield = _create_kpi_card("YIELD (g/g)", "0.00%", GOOD)
	_kpi_mw = _create_kpi_card("MOLECULAR WEIGHT", "251 kDa", Color(0.4, 0.75, 1.0))
	_kpi_purity = _create_kpi_card("PURITY / M:G", "91.5% (2.49)", Color(0.85, 0.55, 1.0))
	_kpi_uts = _create_kpi_card("FIBRE UTS", "29.3 MPa", Color(1.0, 0.82, 0.35))

	kpi_row.add_child(_kpi_yield.get_parent())
	kpi_row.add_child(_kpi_mw.get_parent())
	kpi_row.add_child(_kpi_purity.get_parent())
	kpi_row.add_child(_kpi_uts.get_parent())

	_readout = Label.new()
	_readout.text = "Timeline initialized. Press Space to play or scrub slider."
	_readout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_readout.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_readout.add_theme_font_size_override("font_size", 10)
	_readout.modulate = MUTED
	kpi_row.add_child(_readout)

	_delta_badge = Label.new()
	_delta_badge.name = "DeltaReadoutBadge"
	_delta_badge.text = ""
	_delta_badge.visible = false
	main_v.add_child(_delta_badge)

	return _bottom_dock


func _create_kpi_card(title: String, initial_val: String, glow_col: Color) -> Label:
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(130, 0)
	box.add_theme_constant_override("separation", 1)

	var t_lbl := Label.new()
	t_lbl.text = title
	t_lbl.add_theme_font_size_override("font_size", 9)
	t_lbl.modulate = Color(0.55, 0.62, 0.72)
	box.add_child(t_lbl)

	var v_lbl := Label.new()
	v_lbl.text = initial_val
	v_lbl.add_theme_font_size_override("font_size", 14)
	v_lbl.modulate = glow_col
	box.add_child(v_lbl)

	return v_lbl


# ---------------------------------------------------------------- Interactive Process Sandbox Dock

func _create_sandbox_dock() -> Control:
	_sandbox_panel = PanelContainer.new()
	_sandbox_panel.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_sandbox_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_sandbox_panel.offset_left = 20
	_sandbox_panel.offset_right = 310
	_sandbox_panel.offset_top = -195
	_sandbox_panel.offset_bottom = -16
	_sandbox_panel.custom_minimum_size = Vector2(290, 175)

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.06, 0.08, 0.12, 0.94)
	style.corner_radius_top_left = 8
	style.corner_radius_top_right = 8
	style.corner_radius_bottom_left = 8
	style.corner_radius_bottom_right = 8
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.border_color = Color(0.28, 0.38, 0.52)
	_sandbox_panel.add_theme_stylebox_override("panel", style)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 5)
	_sandbox_panel.add_child(v)

	_sandbox_title_label = Label.new()
	_sandbox_title_label.text = "🧪 WHAT-IF PROCESS SANDBOX"
	_sandbox_title_label.add_theme_font_size_override("font_size", 11)
	_sandbox_title_label.modulate = Color(0.35, 0.85, 1.0)
	v.add_child(_sandbox_title_label)

	_bio_sandbox_box = VBoxContainer.new()
	_bio_sandbox_box.add_theme_constant_override("separation", 5)
	v.add_child(_bio_sandbox_box)

	# 1. Neutralisation pH Lever
	_sandbox_ph_btn = Button.new()
	_sandbox_ph_btn.text = "pH State: pH 7.0 [Neutralised]"
	_sandbox_ph_btn.pressed.connect(_on_sandbox_ph_toggle)
	_bio_sandbox_box.add_child(_sandbox_ph_btn)

	# 2. Scale Mode Lever
	_sandbox_scale_btn = Button.new()
	_sandbox_scale_btn.text = "Scale: Scaled-Up 15.0g (33.07%)"
	_sandbox_scale_btn.pressed.connect(_on_sandbox_scale_toggle)
	_bio_sandbox_box.add_child(_sandbox_scale_btn)

	# 3. Fibre Crosslinking Lever
	_sandbox_crosslink_btn = Button.new()
	_sandbox_crosslink_btn.text = "Fibre: Pure Alginate (29.3 MPa)"
	_sandbox_crosslink_btn.pressed.connect(_on_sandbox_crosslink_toggle)
	_bio_sandbox_box.add_child(_sandbox_crosslink_btn)

	# 4. Mechanical Tension Pull Test Slider
	var t_row := HBoxContainer.new()
	_bio_sandbox_box.add_child(t_row)
	var t_lbl := Label.new()
	t_lbl.text = "Pull Load:"
	t_lbl.add_theme_font_size_override("font_size", 10)
	t_row.add_child(t_lbl)

	_sandbox_tension_label = Label.new()
	_sandbox_tension_label.text = "12.0 MPa"
	_sandbox_tension_label.add_theme_font_size_override("font_size", 10)
	_sandbox_tension_label.modulate = GOOD
	t_row.add_child(_sandbox_tension_label)

	_sandbox_tension_slider = HSlider.new()
	_sandbox_tension_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_sandbox_tension_slider.min_value = 0.0
	_sandbox_tension_slider.max_value = 45.0
	_sandbox_tension_slider.step = 0.5
	_sandbox_tension_slider.value = 12.0
	_sandbox_tension_slider.value_changed.connect(_on_sandbox_tension_changed)
	_bio_sandbox_box.add_child(_sandbox_tension_slider)

	# ---- SMR Chemical Plant Controls & HAZOP Faults ----
	_smr_sandbox_box = VBoxContainer.new()
	_smr_sandbox_box.add_theme_constant_override("separation", 4)
	_smr_sandbox_box.visible = false
	v.add_child(_smr_sandbox_box)

	var sc_res := _make_smr_slider_row(_smr_sandbox_box, "Steam/Carbon (S/C):", 2.0, 4.5, 0.1, 3.0, "%.2f")
	_smr_sc_slider = sc_res[0]
	_smr_sc_val = sc_res[1]
	_smr_sc_slider.value_changed.connect(_on_smr_param_changed)

	var t_res := _make_smr_slider_row(_smr_sandbox_box, "Reformer Outlet (°C):", 750.0, 960.0, 5.0, 900.0, "%.0f °C")
	_smr_temp_slider = t_res[0]
	_smr_temp_val = t_res[1]
	_smr_temp_slider.value_changed.connect(_on_smr_param_changed)

	var p_res := _make_smr_slider_row(_smr_sandbox_box, "Operating Press (bar):", 15.0, 48.0, 0.5, 38.0, "%.1f bar")
	_smr_press_slider = p_res[0]
	_smr_press_val = p_res[1]
	_smr_press_slider.value_changed.connect(_on_smr_param_changed)

	_smr_kpis_label = Label.new()
	_smr_kpis_label.text = "CH4 Slip: 2.1% | WGS CO: 94.2%\nH2: 120,000 Nm3/h | Comp: 14,200 kW"
	_smr_kpis_label.add_theme_font_size_override("font_size", 9)
	_smr_kpis_label.modulate = Color(0.55, 0.95, 1.0)
	_smr_sandbox_box.add_child(_smr_kpis_label)

	var hazop_row := VBoxContainer.new()
	hazop_row.add_theme_constant_override("separation", 3)
	_smr_sandbox_box.add_child(hazop_row)

	_smr_btn_e105 = Button.new()
	_smr_btn_e105.text = "⚡ Trigger E_105 Cooling Loss"
	_smr_btn_e105.add_theme_font_size_override("font_size", 10)
	_smr_btn_e105.pressed.connect(_on_hazop_e105_toggle)
	hazop_row.add_child(_smr_btn_e105)

	_smr_btn_coking = Button.new()
	_smr_btn_coking.text = "🔥 Trigger Low S/C Carbon Coking"
	_smr_btn_coking.add_theme_font_size_override("font_size", 10)
	_smr_btn_coking.pressed.connect(_on_hazop_coking_toggle)
	hazop_row.add_child(_smr_btn_coking)

	_smr_btn_purge = Button.new()
	_smr_btn_purge.text = "🚨 Trip Emergency N2 Purge (XV-101)"
	_smr_btn_purge.add_theme_font_size_override("font_size", 10)
	_smr_btn_purge.pressed.connect(_on_hazop_n2_purge_toggle)
	hazop_row.add_child(_smr_btn_purge)

	_smr_btn_xray = Button.new()
	_smr_btn_xray.text = "🔍 X-Ray / Cutaway View: ON"
	_smr_btn_xray.add_theme_font_size_override("font_size", 10)
	_smr_btn_xray.modulate = Color(0.55, 0.95, 1.0)
	_smr_btn_xray.pressed.connect(_on_smr_xray_toggle)
	hazop_row.add_child(_smr_btn_xray)

	_sandbox_banner = Label.new()
	_sandbox_banner.text = "System nominal. All parameters verified."
	_sandbox_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_sandbox_banner.add_theme_font_size_override("font_size", 9)
	_sandbox_banner.modulate = MUTED
	v.add_child(_sandbox_banner)

	return _sandbox_panel


func _make_smr_slider_row(parent: VBoxContainer, label_txt: String, min_v: float, max_v: float, step_v: float, init_v: float, fmt: String) -> Array:
	var row := HBoxContainer.new()
	parent.add_child(row)
	var lbl := Label.new()
	lbl.text = label_txt
	lbl.add_theme_font_size_override("font_size", 9)
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(lbl)
	var val_lbl := Label.new()
	val_lbl.text = fmt % init_v
	val_lbl.add_theme_font_size_override("font_size", 9)
	val_lbl.modulate = GOOD
	row.add_child(val_lbl)

	var sl := HSlider.new()
	sl.min_value = min_v
	sl.max_value = max_v
	sl.step = step_v
	sl.value = init_v
	sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(sl)
	return [sl, val_lbl]


func _set_sandbox_mode(is_smr: bool) -> void:
	_smr_mode = is_smr
	if _bio_sandbox_box != null:
		_bio_sandbox_box.visible = not is_smr
	if _smr_sandbox_box != null:
		_smr_sandbox_box.visible = is_smr
	if _sandbox_title_label != null:
		_sandbox_title_label.text = "⚙️ SMR PLANT & HAZOP CONTROLS" if is_smr else "🧪 WHAT-IF PROCESS SANDBOX"
	if _sandbox_panel != null:
		_sandbox_panel.visible = true
		_sandbox_panel.offset_top = -355 if is_smr else -195
		_sandbox_panel.offset_right = 315 if is_smr else 300
		_sandbox_panel.custom_minimum_size = Vector2(295, 335) if is_smr else Vector2(275, 175)
	if is_smr:
		_recalculate_smr_equilibrium()


func _on_smr_param_changed(_val: float) -> void:
	_recalculate_smr_equilibrium()


func _on_hazop_e105_toggle() -> void:
	_smr_fault_state["e105_cooling_loss"] = not bool(_smr_fault_state.get("e105_cooling_loss", false))
	_recalculate_smr_equilibrium()


func _on_hazop_coking_toggle() -> void:
	var active := not bool(_smr_fault_state.get("coking_warning", false))
	_smr_fault_state["coking_warning"] = active
	if active and _smr_sc_slider != null:
		_smr_sc_slider.value = 2.0
	elif not active and _smr_sc_slider != null and _smr_sc_slider.value < 2.5:
		_smr_sc_slider.value = 3.0
	_recalculate_smr_equilibrium()


func _on_hazop_n2_purge_toggle() -> void:
	_smr_fault_state["n2_purge_active"] = not bool(_smr_fault_state.get("n2_purge_active", false))
	_recalculate_smr_equilibrium()


func _on_smr_xray_toggle() -> void:
	_xray_enabled = not _xray_enabled
	if _smr_btn_xray != null:
		_smr_btn_xray.text = "🔍 X-Ray / Cutaway View: %s" % ("ON" if _xray_enabled else "OFF (Solid)")
		_smr_btn_xray.modulate = Color(0.55, 0.95, 1.0) if _xray_enabled else Color.WHITE
	if _view != null and _view.has_method("set_xray_cutaway"):
		_view.set_xray_cutaway(_xray_enabled)


func _recalculate_smr_equilibrium() -> void:
	if not _smr_mode or _smr_sc_slider == null:
		return
	var sc: float = _smr_sc_slider.value
	var temp_c: float = _smr_temp_slider.value
	var press: float = _smr_press_slider.value

	_smr_sc_val.text = "%.2f" % sc
	_smr_temp_val.text = "%.0f °C" % temp_c
	_smr_press_val.text = "%.1f bar" % press

	# Auto-flag carbon coking if S/C <= 2.15
	var coking_active: bool = bool(_smr_fault_state.get("coking_warning", false)) or (sc <= 2.15)
	_smr_fault_state["coking_warning"] = coking_active
	var e105_loss: bool = bool(_smr_fault_state.get("e105_cooling_loss", false))
	var n2_purge: bool = bool(_smr_fault_state.get("n2_purge_active", false))

	# Van 't Hoff temperature dependence & Le Chatelier pressure scaling tied to grounded RAG parameters
	var grounded: Dictionary = _result.get("grounded_parameters", {})
	var dh_smr_kj: float = 206.0
	if grounded.has("smr_reaction_enthalpy") and (grounded["smr_reaction_enthalpy"] is Dictionary):
		dh_smr_kj = float((grounded["smr_reaction_enthalpy"] as Dictionary).get("value", 206.0))
	var t_ref_k: float = 900.0 + 273.15
	var t_k: float = temp_c + 273.15
	var k_vant_hoff: float = exp((-dh_smr_kj * 1000.0 / 8.314) * ((1.0 / t_k) - (1.0 / t_ref_k)))
	var le_chatelier_p: float = pow(press / 38.0, 2.0)

	var r102_c2_conv_pct: float = clampf(99.5 - maxf(0.0, 2.5 - sc) * 4.0, 88.0, 100.0)
	var ch4_slip_pct: float = clampf(2.1 * (1.0 / maxf(0.05, k_vant_hoff)) * (3.0 / sc) * sqrt(le_chatelier_p), 0.25, 22.0)
	var wgs_co_conv_pct: float = clampf((96.4 + (sc - 3.0) * 1.2) - (16.5 if e105_loss else 0.0), 65.0, 99.0)
	var psa_rec_pct: float = clampf(88.0 - (0.4 if e105_loss else 0.0) - (0.5 if ch4_slip_pct > 5.0 else 0.0), 75.0, 91.0)
	var purity_pct: float = 0.0 if n2_purge else clampf(99.99 - maxf(0.0, ch4_slip_pct - 4.0) * 0.20 - (0.6 if e105_loss else 0.0), 92.0, 99.99)
	_smr_fault_state["purity_pct"] = purity_pct

	var h2_flow: float = 0.0 if n2_purge else 120000.0 * ((1.0 - ch4_slip_pct * 0.015) / (1.0 - 2.1 * 0.015)) * (wgs_co_conv_pct / 96.4) * (psa_rec_pct / 88.0)
	var comp_kw: float = 0.0 if n2_purge else 14200.0 * (h2_flow / 120000.0) * (log(400.0 / maxf(press - 4.9, 10.0)) / log(400.0 / 33.1))
	_smr_fault_state["h2_flow"] = h2_flow
	_smr_fault_state["q_scale"] = h2_flow / 120000.0 if h2_flow > 0.0 else 0.0

	var law_violations: Array = _evaluate_runtime_reality_laws(sc, temp_c, press, e105_loss, n2_purge)
	_smr_fault_state["law_violations"] = law_violations

	_smr_kpis_label.text = "R-102 C2+ Conv: %.1f%% | R-103 CH4 Slip: %.1f%%\nWGS CO: %.1f%% | H2: %.0f Nm3/h | %.0f kW" % [r102_c2_conv_pct, ch4_slip_pct, wgs_co_conv_pct, h2_flow, comp_kw]

	var is_perturbed: bool = absf(sc - 3.0) > 0.05 or absf(temp_c - 900.0) > 1.0 or absf(press - 38.0) > 0.2 or e105_loss or coking_active or n2_purge
	if _confidence_badge != null:
		if is_perturbed:
			_confidence_badge.text = "[Reduced-Order Equilibrium Perturbation Model • Van 't Hoff + Le Chatelier]"
			_confidence_badge.modulate = WARN
		else:
			var prov: Dictionary = _result.get("epistemic_provenance", {})
			var audit: Dictionary = _result.get("epistemic_audit", {})
			var peer_cnt: int = int(prov.get("tier_1_quarantine_count", 0)) + int(prov.get("tier_0_internal_bench_count", 0))
			var set_cnt: int = (audit.get("user_design_setpoints", {}) as Dictionary).size()
			var unv_cnt: int = (audit.get("unverified_assumptions", {}) as Dictionary).size()
			var gap_cnt: int = int(audit.get("gap_count", 0))
			_confidence_badge.text = "[Provenance: %d Tier 1 Peer-Reviewed • %d User Setpoints • %d Unverified Hypotheses • %d Gaps]" % [peer_cnt, set_cnt, unv_cnt, gap_cnt]
			_confidence_badge.modulate = GOOD if (gap_cnt == 0 and unv_cnt == 0) else WARN

	if _smr_btn_e105 != null:
		_smr_btn_e105.modulate = BAD if e105_loss else Color.WHITE
	if _smr_btn_coking != null:
		_smr_btn_coking.modulate = WARN if coking_active else Color.WHITE
	if _smr_btn_purge != null:
		_smr_btn_purge.modulate = BAD if n2_purge else Color.WHITE

	if n2_purge:
		_sandbox_banner.text = "🚨 SIS-101 TRIPPED: Emergency N2 Purge active (XV-101 OPEN). Burners shut down; plant depressurising."
		_sandbox_banner.modulate = BAD
	elif e105_loss:
		_sandbox_banner.text = "⚠️ E_105 COOLING LOSS: Syngas outlet 580°C! WGS equilibrium degraded (%.1f%% CO conv)." % wgs_co_conv_pct
		_sandbox_banner.modulate = BAD
	elif coking_active:
		_sandbox_banner.text = "🔥 LOW S/C COKING RISK: S/C = %.2f <= 2.15! Carbon deposition on Ni catalyst tubes." % sc
		_sandbox_banner.modulate = WARN
	else:
		_sandbox_banner.text = "Plant nominal: %.2f%% H2 purity | %.0f Nm3/h | %.0f kW." % [purity_pct, h2_flow, comp_kw]
		_sandbox_banner.modulate = GOOD

	if _story_banner != null and not _unit_operations.is_empty():
		var active_idx := clampi(_last_stage_index, 0, _unit_operations.size() - 1)
		var active_op: Dictionary = _unit_operations[active_idx]
		_story_banner.text = "▶ Unit %d00 (%s) [Continuous Steady-State] | H2 Output: %.0f Nm³/h (%.2f%% Purity @ 400 bar)" % [
			active_idx + 1, str(active_op.get("title", "")), h2_flow, purity_pct
		]

	if _view != null and _view.has_method("update_smr_process_state"):
		_view.update_smr_process_state(sc, temp_c, press, _smr_fault_state)


func _get_active_law(law_id: String) -> Dictionary:
	var laws: Array = _reality_compiler_audit.get("active_laws", [])
	for item in laws:
		if item is Dictionary and str((item as Dictionary).get("law_id", "")) == law_id:
			return item as Dictionary
	return {}


func _evaluate_runtime_reality_laws(sc: float = 3.0, temp_c: float = 900.0, press: float = 38.0, e105_loss: bool = false, n2_purge: bool = false) -> Array:
	var violations: Array = []
	if not _smr_mode:
		var compile_viols: Array = _reality_compiler_audit.get("violations", [])
		_runtime_law_violations = compile_viols
		_update_reality_compiler_badges(compile_viols)
		return compile_viols

	# 1. BOUDOUARD_CARBON_COKING
	var coking_law := _get_active_law("BOUDOUARD_CARBON_COKING")
	var coking_thresh: Dictionary = coking_law.get("threshold_parameters", {})
	var min_sc: float = float(coking_thresh.get("min_sc_ratio_ni", 2.0))
	if sc < min_sc:
		violations.append({
			"law_id": "BOUDOUARD_CARBON_COKING",
			"unit_tag": "B-101 / R-103",
			"message": "S/C=%.2f < %.2f min Ni catalyst coking limit" % [sc, min_sc],
			"equation": str(coking_law.get("governing_equation", "S/C >= min_sc_ratio_ni (2.0)")),
			"doi": str(coking_law.get("doi", "10.1016/j.ijhydene.2013.08.055")),
		})

	# 2. VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM & SINGLE_SHELL_THERMAL_SHOCK
	var vh_law := _get_active_law("VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM")
	var hx_law := _get_active_law("SINGLE_SHELL_THERMAL_SHOCK")
	var max_hx_dt: float = float((hx_law.get("threshold_parameters", {}) as Dictionary).get("max_single_hx_dt_c", 350.0))
	var e105_out_c: float = (580.0 if e105_loss else 340.0) + (temp_c - 900.0) * 0.35
	var r104_out_c: float = e105_out_c + 80.0
	var r105_out_c: float = 245.0 + (e105_out_c - 340.0) * 0.45
	if r104_out_c > 450.0 or r105_out_c > 260.0:
		violations.append({
			"law_id": "VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM",
			"unit_tag": "R-104 / R-105",
			"message": "Shift exit %.0f°C / %.0f°C exceeds catalyst sintering & equilibrium ceiling (450°C / 260°C)" % [r104_out_c, r105_out_c],
			"equation": str(vh_law.get("governing_equation", "T_shift_out <= 450 C (HTS) / 260 C (LTS); dT_ad <= 220 C")),
			"doi": str(vh_law.get("doi", "10.1016/j.ijhydene.2010.04.093")),
		})
	var e105_dt: float = absf(temp_c - e105_out_c)
	if not e105_loss and e105_dt > (max_hx_dt + 230.0):
		# E-105 is a WHB (max_whb_hx_dt_c=580°C) when nominal, flag only if exceeded
		violations.append({
			"law_id": "SINGLE_SHELL_THERMAL_SHOCK",
			"unit_tag": "E-105",
			"message": "Single-shell dT %.0f°C exceeds thermal shock limit" % e105_dt,
			"equation": str(hx_law.get("governing_equation", "|T_in - T_out| <= max_single_hx_dt_c")),
			"doi": str(hx_law.get("doi", "10.1016/B978-0-08-096659-5.00019-5")),
		})

	# 3. POLYTROPIC_COMPRESSION_DISCHARGE
	var comp_law := _get_active_law("POLYTROPIC_COMPRESSION_DISCHARGE")
	var comp_thresh: Dictionary = comp_law.get("threshold_parameters", {})
	var gamma: float = float(comp_thresh.get("gamma", 1.38))
	var eta_p: float = float(comp_thresh.get("eta_p", 0.80))
	var t_max_comp_c: float = float(comp_thresh.get("max_compressor_discharge_c", 155.0))
	var p_in_bar: float = maxf(press - 4.9, 5.0)
	var p_out_bar: float = 400.0
	var n_stages: float = 3.0
	var t_in_k: float = 40.0 + 273.15
	var t_out_k: float = t_in_k * pow(p_out_bar / p_in_bar, (gamma - 1.0) / (n_stages * gamma * eta_p))
	var t_out_c: float = t_out_k - 273.15
	if not n2_purge and t_out_c > t_max_comp_c:
		violations.append({
			"law_id": "POLYTROPIC_COMPRESSION_DISCHARGE",
			"unit_tag": "C-101..103",
			"message": "Stage discharge %.1f°C > %.1f°C seal limit (P_in=%.1f bar)" % [t_out_c, t_max_comp_c, p_in_bar],
			"equation": str(comp_law.get("governing_equation", "T_out = T_in * (P_out/P_in)^((gamma-1)/(N*gamma*eta_p)) <= 155 C")),
			"doi": str(comp_law.get("doi", "10.1016/B978-0-12-809644-4.00003-2")),
		})

	# 4. SECOND_LAW_PINCH
	var pinch_law := _get_active_law("SECOND_LAW_PINCH")
	var pinch_thresh: Dictionary = pinch_law.get("threshold_parameters", {})
	var dt_min: float = float(pinch_thresh.get("dT_min_c", 10.0))
	var flue_in_c: float = temp_c + 110.0
	var pre_ref_out_c: float = 627.0 + (temp_c - 900.0) * 0.45
	var stack_out_c: float = 130.0 + (temp_c - 900.0) * 0.45
	var approach_hot: float = flue_in_c - pre_ref_out_c
	var approach_cold: float = stack_out_c - 25.0
	var min_approach: float = minf(approach_hot, approach_cold)
	if min_approach < dt_min:
		violations.append({
			"law_id": "SECOND_LAW_PINCH",
			"unit_tag": "E-103..E-104",
			"message": "Convection pinch approach %.1f°C < dT_min %.1f°C" % [min_approach, dt_min],
			"equation": str(pinch_law.get("governing_equation", "T_hot_in - T_cold_out >= dT_min and T_hot_out - T_cold_in >= dT_min")),
			"doi": str(pinch_law.get("doi", "10.1016/0009-2509(83)80134-1")),
		})

	_runtime_law_violations = violations
	_update_reality_compiler_badges(violations)
	return violations


func _update_reality_compiler_badges(violations: Array) -> void:
	var laws_checked: int = int(_reality_compiler_audit.get("laws_checked", 6))
	if violations.is_empty():
		if _top_reality_badge != null:
			_top_reality_badge.text = "🟢 Reality Compiler: PASSED (%d/6 Physical Laws Verified)" % laws_checked
			_top_reality_badge.modulate = GOOD
		if _reality_compiler_badge != null:
			_reality_compiler_badge.text = "🟢 Reality Compiler: PASSED (%d/6 Physical Laws Verified • 0 Violations)" % laws_checked
			_reality_compiler_badge.modulate = GOOD
	else:
		var first_v: Dictionary = violations[0] if (violations[0] is Dictionary) else {}
		var first_id := str(first_v.get("law_id", "LAW_VIOLATION"))
		var first_unit := str(first_v.get("unit_tag", "UNIT"))
		var n_v: int = violations.size()
		var plural := "" if n_v == 1 else "S"
		if _top_reality_badge != null:
			_top_reality_badge.text = "🔴 Reality Compiler: %d LAW VIOLATION%s (%s on %s — see Dossier)" % [n_v, plural, first_id, first_unit]
			_top_reality_badge.modulate = BAD
		if _reality_compiler_badge != null:
			var lines: PackedStringArray = PackedStringArray()
			lines.append("🔴 Reality Compiler: %d LAW VIOLATION%s" % [n_v, plural])
			for item in violations:
				if not (item is Dictionary):
					continue
				var v: Dictionary = item as Dictionary
				lines.append("[LAW VIOLATION: %s] on %s — %s" % [
					str(v.get("law_id", "?")),
					str(v.get("unit_tag", "?")),
					str(v.get("message", "")),
				])
				lines.append("   Eq: %s | DOI: %s" % [str(v.get("equation", "")), str(v.get("doi", ""))])
			_reality_compiler_badge.text = "\n".join(lines)
			_reality_compiler_badge.modulate = BAD
	_refresh_sizing_table_label()


func _refresh_sizing_table_label() -> void:
	if _sizing_table_label == null:
		return
	var rows: Array = _reality_compiler_audit.get("mass_energy_sizing_table", [])
	if rows.is_empty():
		_sizing_table_label.text = ""
		return
	var lines: PackedStringArray = PackedStringArray()
	lines.append("📐 MASS, ENERGY & UK BS EN 13480 SIZING TABLE:")
	lines.append("Tag | m_dot [kg/h] | T_in->T_out [°C] | Q [MW] | U | LMTD | A [m²] | D×L [m] | DN")
	for item in rows:
		if not (item is Dictionary):
			continue
		var r: Dictionary = item as Dictionary
		lines.append("%s | %.0f | %.0f->%.0f | %.1f | %.0f | %.1f | %.0f | %.1f×%.1f | DN%d" % [
			str(r.get("tag", "?")),
			float(r.get("mass_flow_kg_h", 0.0)),
			float(r.get("t_in_c", 0.0)),
			float(r.get("t_out_c", 0.0)),
			float(r.get("duty_mw", 0.0)),
			float(r.get("u_w_m2k", 0.0)),
			float(r.get("dt_lmtd_k", 0.0)),
			float(r.get("area_req_m2", 0.0)),
			float(r.get("shell_d_m", 0.0)),
			float(r.get("shell_l_m", 0.0)),
			int(r.get("pipe_dn_mm", 0)),
		])
	_sizing_table_label.text = "\n".join(lines)


func _on_sandbox_ph_toggle() -> void:
	_sandbox_ph_mode = 1 if _sandbox_ph_mode == 0 else 0
	if _sandbox_ph_mode == 1:
		_sandbox_ph_btn.text = "pH State: pH 12.0 [Unneutralised]"
		_sandbox_ph_btn.modulate = WARN
		_sandbox_banner.text = "⚠️ ALKALINE DEPOLYMERISATION ACTIVE: High pH causes β-elimination polymer chain cleavage. Yield drops to 24.5%, Mw plunges."
		_sandbox_banner.modulate = WARN
		_kpi_mw.text = "110 kDa (Degraded)"
		_kpi_mw.modulate = WARN
		_show_toast("⚠️ Switched to pH 12.0 (Unneutralised)")
	else:
		_sandbox_ph_btn.text = "pH State: pH 7.0 [Neutralised]"
		_sandbox_ph_btn.modulate = Color.WHITE
		_sandbox_banner.text = "Neutralised to pH 7.0 with dropwise HCl. Polymer chains intact (251 kDa)."
		_sandbox_banner.modulate = GOOD
		_kpi_mw.text = "251 kDa"
		_kpi_mw.modulate = Color(0.4, 0.75, 1.0)
		_show_toast("✓ Neutralised to pH 7.0 (HCl Titration)")
	_apply_playback_time(_current_sim_time)


func _on_sandbox_scale_toggle() -> void:
	_sandbox_scale_mode = 1 if _sandbox_scale_mode == 0 else 0
	if _sandbox_scale_mode == 1:
		_sandbox_scale_btn.text = "Scale: Small-Scale 2.5g (26.0%)"
		_sandbox_banner.text = "Switched to initial small-scale extraction (2.5g kelp loading, 26.0% yield)."
		_show_toast("Switched to Small-Scale 2.5g Extraction")
	else:
		_sandbox_scale_btn.text = "Scale: Scaled-Up 15.0g (33.07%)"
		_sandbox_banner.text = "Switched to two-stage scaled-up extraction (15.0g kelp loading, 33.07% yield)."
		_show_toast("Switched to Scaled-Up 15.0g Extraction")
	_apply_playback_time(_current_sim_time)


func _on_sandbox_crosslink_toggle() -> void:
	_sandbox_crosslink_mode = (_sandbox_crosslink_mode + 1) % 3
	match _sandbox_crosslink_mode:
		0:
			_sandbox_crosslink_btn.text = "Fibre: Pure Alginate (29.3 MPa)"
			_kpi_uts.text = "29.3 MPa"
			_kpi_uts.modulate = Color(1.0, 0.82, 0.35)
			_sandbox_banner.text = "Pure extruded alginate monofilament. Ultimate Tensile Strength = 29.3 MPa."
			_show_toast("Fibre: Pure Alginate (29.3 MPa)")
			if _view != null and _view.has_method("reset_fibre_snap"):
				_view.reset_fibre_snap()
		1:
			_sandbox_crosslink_btn.text = "Fibre: Citric-Crosslinked (43.1 MPa)"
			_kpi_uts.text = "43.1 MPa"
			_kpi_uts.modulate = GOOD
			_sandbox_banner.text = "Citric-acid crosslinked fibre. Enhanced intermolecular ester bonds boost UTS to 43.1 MPa!"
			_show_toast("Fibre: Citric-Crosslinked (43.1 MPa)")
			if _view != null and _view.has_method("reset_fibre_snap"):
				_view.reset_fibre_snap()
		2:
			_sandbox_crosslink_btn.text = "Fibre: Blended Alginate (42.1 MPa)"
			_kpi_uts.text = "42.1 MPa"
			_kpi_uts.modulate = GOOD
			_sandbox_banner.text = "Polymer blend formulation. High flexibility and tensile strength = 42.1 MPa."
			_show_toast("Fibre: Blended Alginate (42.1 MPa)")
			if _view != null and _view.has_method("reset_fibre_snap"):
				_view.reset_fibre_snap()
	_on_sandbox_tension_changed(_current_tension_load)


func _on_sandbox_tension_changed(val: float) -> void:
	_current_tension_load = val
	_sandbox_tension_label.text = "%.1f MPa" % val

	var threshold := 29.3
	if _sandbox_crosslink_mode == 1:
		threshold = 43.1
	elif _sandbox_crosslink_mode == 2:
		threshold = 42.1

	if _view != null and _view.has_method("set_fibre_tension_load"):
		_view.set_fibre_tension_load(val, threshold)

	if val > threshold:
		_sandbox_tension_label.modulate = BAD
		_sandbox_banner.text = "💥 FIBRE FRACTURE: Applied pull tension (%.1f MPa) exceeded material UTS threshold (%.1f MPa)!" % [val, threshold]
		_sandbox_banner.modulate = BAD
	elif val > threshold * 0.85:
		_sandbox_tension_label.modulate = WARN
		_sandbox_banner.text = "⚠️ HIGH TENSION WARNING: Near mechanical yield point."
		_sandbox_banner.modulate = WARN
	else:
		_sandbox_tension_label.modulate = GOOD
		_sandbox_banner.modulate = MUTED


func _on_fibre_snapped(load_mpa: float) -> void:
	_sandbox_banner.text = "💥 PHYSICAL BREAK: Filament fractured under %.1f MPa load! Switch to Citric-Crosslinked to withstand >40 MPa." % load_mpa
	_sandbox_banner.modulate = BAD
	_show_toast("💥 FIBRE FRACTURE at %.1f MPa!" % load_mpa, 2.5)


# ---------------------------------------------------------------- Slide-Out Right Drawer

func _create_right_drawer() -> Control:
	_right_drawer = PanelContainer.new()
	_right_drawer.set_anchors_preset(Control.PRESET_RIGHT_WIDE)
	_right_drawer.offset_left = -460
	_right_drawer.offset_right = 0
	_right_drawer.offset_top = 0
	_right_drawer.offset_bottom = 0
	_right_drawer.visible = false

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.04, 0.05, 0.08, 0.96)
	style.border_width_left = 1
	style.border_color = Color(0.20, 0.28, 0.40)
	_right_drawer.add_theme_stylebox_override("panel", style)

	var scroll := ScrollContainer.new()
	scroll.set_anchors_preset(Control.PRESET_FULL_RECT)
	_right_drawer.add_child(scroll)

	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 10)
	scroll.add_child(body)

	# Header with close button
	var d_header := HBoxContainer.new()
	body.add_child(d_header)
	var d_title := Label.new()
	d_title.text = "SCIENTIFIC DOSSIER & CHARTS"
	d_title.add_theme_font_size_override("font_size", 12)
	d_title.modulate = GOOD
	d_header.add_child(d_title)
	var d_spacer := Control.new()
	d_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	d_header.add_child(d_spacer)
	var close_btn := Button.new()
	close_btn.text = "✕ Close"
	close_btn.pressed.connect(_toggle_right_drawer)
	d_header.add_child(close_btn)

	_reality_compiler_badge = Label.new()
	_reality_compiler_badge.text = "🛡 Reality Compiler: Pending verification"
	_reality_compiler_badge.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_reality_compiler_badge.add_theme_font_size_override("font_size", 10)
	_reality_compiler_badge.modulate = GOOD
	body.add_child(_reality_compiler_badge)

	_sizing_table_label = Label.new()
	_sizing_table_label.text = ""
	_sizing_table_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_sizing_table_label.add_theme_font_size_override("font_size", 9)
	_sizing_table_label.modulate = Color(0.78, 0.88, 0.98)
	body.add_child(_sizing_table_label)

	# Growth Chart in Drawer
	_growth = GrowthChart.new()
	_growth.custom_minimum_size = Vector2(420, 190)
	body.add_child(_growth)
	_growth.scrubbed.connect(_on_scrub)

	# Cascade Chart in Drawer
	_cascade = CascadeChart.new()
	_cascade.custom_minimum_size = Vector2(420, 140)
	body.add_child(_cascade)

	# Technical Isometric Diagram Preview
	_diagram_rect = TextureRect.new()
	_diagram_rect.custom_minimum_size = Vector2(420, 160)
	_diagram_rect.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL
	_diagram_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	body.add_child(_diagram_rect)

	# Status labels
	_status = Label.new()
	_status.text = "Ready."
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_font_size_override("font_size", 10)
	body.add_child(_status)

	_sim_status = Label.new()
	_sim_status.text = "Awaiting prompt..."
	_sim_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_sim_status.add_theme_font_size_override("font_size", 10)
	body.add_child(_sim_status)

	# Section: Literature Review Manifest
	_section(body, "Central Knowledge Library Grounding")
	_manifest_body = VBoxContainer.new()
	body.add_child(_manifest_body)

	# Section: Hot-swap alternative selector
	_section(body, "Hot-Swap Alternative Mechanisms")
	_hotswap_selector = OptionButton.new()
	_hotswap_selector.add_item("Current Primary Mechanism")
	_hotswap_selector.item_selected.connect(_on_hotswap_selected)
	body.add_child(_hotswap_selector)

	# Section: Prompt Input & Execution
	_section(body, "Prompt & Runner Controls")
	_prompt = TextEdit.new()
	_prompt.custom_minimum_size = Vector2(0, 75)
	_prompt.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_prompt.text = "Simulate Saccharina latissima alginate extraction and yield kinetics using the MSc dissertation model"
	body.add_child(_prompt)

	var p_btns := HBoxContainer.new()
	p_btns.add_theme_constant_override("separation", 6)
	body.add_child(p_btns)

	_generate = Button.new()
	_generate.text = "Generate Simulation"
	_generate.pressed.connect(_on_generate_pressed)
	p_btns.add_child(_generate)

	_interpret_only = Button.new()
	_interpret_only.text = "Interpret"
	_interpret_only.pressed.connect(_on_interpret_pressed)
	p_btns.add_child(_interpret_only)

	_execute = Button.new()
	_execute.text = "Execute"
	_execute.pressed.connect(_on_execute_pressed)
	p_btns.add_child(_execute)

	_interpretation_body = VBoxContainer.new()
	body.add_child(_interpretation_body)
	_result_body = VBoxContainer.new()
	body.add_child(_result_body)
	_output_tree = Tree.new()
	_output_tree.custom_minimum_size = Vector2(0, 100)
	body.add_child(_output_tree)

	return _right_drawer


func _toggle_right_drawer() -> void:
	_is_drawer_open = not _is_drawer_open
	_right_drawer.visible = _is_drawer_open
	if _is_drawer_open:
		_drawer_toggle_btn.text = "📊 Hide Scientific Dossier ⏷"
	else:
		_drawer_toggle_btn.text = "📊 View Scientific Dossier & Charts ⏵"


# ---------------------------------------------------------------- On-Screen Floating Toast

func _create_toast_notification() -> Control:
	_toast_panel = PanelContainer.new()
	_toast_panel.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_toast_panel.offset_top = 80
	_toast_panel.offset_left = -220
	_toast_panel.offset_right = 220
	_toast_panel.custom_minimum_size = Vector2(440, 36)
	_toast_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_panel.modulate.a = 0.0

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.04, 0.07, 0.12, 0.92)
	style.border_color = Color(0.20, 0.85, 0.95, 0.8)
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	_toast_panel.add_theme_stylebox_override("panel", style)

	_toast_label = Label.new()
	_toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_toast_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_toast_label.add_theme_font_size_override("font_size", 12)
	_toast_label.modulate = Color(0.90, 0.96, 1.0)
	_toast_panel.add_child(_toast_label)

	return _toast_panel


func _show_toast(msg: String, stay_sec: float = 1.4) -> void:
	if _toast_panel == null or _toast_label == null:
		return
	_toast_label.text = msg
	if _toast_tween != null and _toast_tween.is_valid():
		_toast_tween.kill()

	_toast_panel.modulate.a = 1.0
	_toast_tween = create_tween()
	_toast_tween.tween_interval(stay_sec)
	_toast_tween.tween_property(_toast_panel, "modulate:a", 0.0, 0.5)


# ---------------------------------------------------------------- Game Pause Menu Modal

func _create_pause_menu_modal() -> Control:
	var root_modal := Control.new()
	root_modal.set_anchors_preset(Control.PRESET_FULL_RECT)
	root_modal.visible = false
	root_modal.mouse_filter = Control.MOUSE_FILTER_STOP

	# Dimmed backdrop
	_pause_backdrop = ColorRect.new()
	_pause_backdrop.set_anchors_preset(Control.PRESET_FULL_RECT)
	_pause_backdrop.color = Color(0.02, 0.03, 0.06, 0.82)
	root_modal.add_child(_pause_backdrop)

	# Centered Dialog Card
	_pause_menu_modal = PanelContainer.new()
	_pause_menu_modal.set_anchors_preset(Control.PRESET_CENTER)
	_pause_menu_modal.offset_left = -225
	_pause_menu_modal.offset_top = -210
	_pause_menu_modal.offset_right = 225
	_pause_menu_modal.offset_bottom = 210
	_pause_menu_modal.custom_minimum_size = Vector2(450, 420)

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.06, 0.09, 0.14, 0.98)
	style.border_color = Color(0.20, 0.85, 0.55)
	style.border_width_left = 2
	style.border_width_right = 2
	style.border_width_top = 2
	style.border_width_bottom = 2
	style.corner_radius_top_left = 10
	style.corner_radius_top_right = 10
	style.corner_radius_bottom_left = 10
	style.corner_radius_bottom_right = 10
	style.shadow_size = 16
	style.shadow_color = Color(0, 0, 0, 0.7)
	_pause_menu_modal.add_theme_stylebox_override("panel", style)
	root_modal.add_child(_pause_menu_modal)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	_pause_menu_modal.add_child(v)

	var title := Label.new()
	title.text = "⏸ SIMULATION CONTROL & PAUSE"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 15)
	title.modulate = GOOD
	v.add_child(title)

	var sub := Label.new()
	sub.text = "ScaleUp Interactive Engine • Alginate Extraction Process"
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_font_size_override("font_size", 10)
	sub.modulate = MUTED
	v.add_child(sub)

	var sep1 := HSeparator.new()
	v.add_child(sep1)

	# Action 1: Resume Playback
	var resume_btn := Button.new()
	resume_btn.text = "▶ Resume Simulation (Space / ESC)"
	resume_btn.custom_minimum_size = Vector2(0, 40)
	resume_btn.modulate = GOOD
	resume_btn.pressed.connect(func() -> void:
		_toggle_pause_menu()
		if not _is_playing:
			_on_play_toggle()
	)
	v.add_child(resume_btn)

	# Action 2: Restart from 0.0 h
	var restart_m_btn := Button.new()
	restart_m_btn.text = "⏮ Restart Timeline from t = 0.0 h"
	restart_m_btn.custom_minimum_size = Vector2(0, 36)
	restart_m_btn.pressed.connect(func() -> void:
		_on_scrub(0.0)
		_toggle_pause_menu()
		_show_toast("⏮ Simulation Restarted from 0.0 h")
	)
	v.add_child(restart_m_btn)

	# Action 3: Camera Auto-Follow Toggle
	var cam_follow_btn := Button.new()
	cam_follow_btn.text = "🎥 Toggle Camera Auto-Follow (Active: %s)" % ("ON" if _auto_follow_cam else "OFF")
	cam_follow_btn.custom_minimum_size = Vector2(0, 36)
	cam_follow_btn.pressed.connect(func() -> void:
		_toggle_auto_cam()
		cam_follow_btn.text = "🎥 Toggle Camera Auto-Follow (Active: %s)" % ("ON" if _auto_follow_cam else "OFF")
	)
	v.add_child(cam_follow_btn)

	# Action 4: Reset Camera to Default
	var reset_cam_m_btn := Button.new()
	reset_cam_m_btn.text = "🔄 Reset Camera Orbit View"
	reset_cam_m_btn.custom_minimum_size = Vector2(0, 36)
	reset_cam_m_btn.pressed.connect(func() -> void:
		if _view != null:
			_view.reset_camera()
		_toggle_pause_menu()
		_show_toast("🎥 Camera reset to lab view")
	)
	v.add_child(reset_cam_m_btn)

	# Action 5: Open Scientific Dossier
	var dossier_btn := Button.new()
	dossier_btn.text = "📊 View Scientific Dossier & Kinetic Curves"
	dossier_btn.custom_minimum_size = Vector2(0, 36)
	dossier_btn.pressed.connect(func() -> void:
		_toggle_pause_menu()
		if not _is_drawer_open:
			_toggle_right_drawer()
	)
	v.add_child(dossier_btn)

	var sep2 := HSeparator.new()
	v.add_child(sep2)

	# Action 6: Quit
	var quit_btn := Button.new()
	quit_btn.text = "🚪 Exit Simulation to Desktop"
	quit_btn.custom_minimum_size = Vector2(0, 36)
	quit_btn.modulate = BAD
	quit_btn.pressed.connect(func() -> void:
		get_tree().quit()
	)
	v.add_child(quit_btn)

	return root_modal


func _toggle_pause_menu() -> void:
	if _pause_menu_modal == null or _pause_menu_modal.get_parent() == null:
		return
	var root_modal: Control = _pause_menu_modal.get_parent()
	var opening := not root_modal.visible
	root_modal.visible = opening
	if opening:
		if _is_playing:
			_is_playing = false
			_update_play_btn()
		_show_toast("⏸ Simulation Paused")
	else:
		_show_toast("✓ Back to Simulation")


func _toggle_auto_cam() -> void:
	_auto_follow_cam = not _auto_follow_cam
	if _auto_cam_btn != null:
		if _auto_follow_cam:
			_auto_cam_btn.text = "🎥 Follow: ON"
			_auto_cam_btn.modulate = GOOD
			_show_toast("🎥 Camera Auto-Follow: ENABLED")
		else:
			_auto_cam_btn.text = "🎥 Follow: OFF"
			_auto_cam_btn.modulate = MUTED
			_show_toast("🎥 Camera Auto-Follow: DISABLED (Free Orbit)")


# ---------------------------------------------------------------- Playback & Dynamic Binding

func _on_play_toggle() -> void:
	_is_playing = not _is_playing
	_update_play_btn()
	if _is_playing:
		_show_toast("▶ Playing Simulation")
	else:
		_show_toast("⏸ Paused (Press Space to resume)")


func _update_play_btn() -> void:
	if _play_btn == null:
		return
	if _is_playing:
		_play_btn.text = "⏸ PAUSE (Space)"
		_play_btn.modulate = WARN
	else:
		_play_btn.text = "▶ PLAY (Space)"
		_play_btn.modulate = GOOD


func _on_speed_toggle() -> void:
	if _play_speed == 1.0:
		_play_speed = 2.0
		_speed_btn.text = "2.0x"
		_show_toast("Speed: 2.0x")
	elif _play_speed == 2.0:
		_play_speed = 4.0
		_speed_btn.text = "4.0x"
		_show_toast("Speed: 4.0x")
	elif _play_speed == 4.0:
		_play_speed = 0.5
		_speed_btn.text = "0.5x"
		_show_toast("Speed: 0.5x (Slow Motion)")
	else:
		_play_speed = 1.0
		_speed_btn.text = "1.0x"
		_show_toast("Speed: 1.0x (Normal)")


func _on_scrub(hour: float) -> void:
	_current_sim_time = hour
	if _time_slider != null:
		_time_slider.set_value_no_signal(hour)
	_apply_playback_time(hour)


func _apply_playback_time(hour: float) -> void:
	if _time_display != null:
		_time_display.text = "t = %.1f h / %.1f h" % [hour, _sim_duration_hours]

	if not _active_trajectory.is_empty():
		var pt := _interpolate_trajectory_at(hour)
		var vol: float = float(pt.get("volume", 5.0))
		var biomass: float = float(pt.get("biomass", 15.0))
		var feed: float = float(pt.get("feed", 0.0))
		var y_val: float = float(pt.get("product_yield", 0.0))

		# Apply sandbox mode modifiers
		if _sandbox_ph_mode == 1:
			y_val *= 0.74
		if _sandbox_scale_mode == 1:
			y_val = minf(y_val, 0.2600)

		# Drive 3D simulation engine
		if _view != null and _view.has_method("update_at_time"):
			_view.update_at_time(hour, _active_trajectory)

		# Update KPI Readouts
		if _kpi_yield != null:
			_kpi_yield.text = "%.2f%%" % (y_val * 100.0)
		if _kpi_mw != null:
			if _sandbox_ph_mode == 1:
				_kpi_mw.text = "110 kDa"
			else:
				_kpi_mw.text = "251 kDa"
		if _kpi_purity != null:
			_kpi_purity.text = "91.5% (2.49)"
		if _kpi_uts != null:
			match _sandbox_crosslink_mode:
				0: _kpi_uts.text = "29.3 MPa"
				1: _kpi_uts.text = "43.1 MPa"
				2: _kpi_uts.text = "42.1 MPa"

		# Update 2D Growth Chart
		if _growth != null:
			_growth.set_cursor(hour, true)

		# Update narrative story banner
		_update_process_story_at_hour(hour, y_val, biomass, vol)


func _update_process_story_at_hour(hour: float, yield_val: float, biomass_val: float, vol_val: float) -> void:
	if _unit_operations.is_empty():
		_story_banner.text = "Process timeline at %.1f h: Biomass %.2f g/L, Volume %.2f L" % [hour, biomass_val, vol_val]
		return

	for i in range(_unit_operations.size()):
		var op: Dictionary = _unit_operations[i]
		var t_win: Array = op.get("time_window_h", [0, 40])
		if hour >= float(t_win[0]) and hour <= float(t_win[1]):
			var title: String = str(op.get("title", ""))
			var eq: String = str(op.get("governing_equation", ""))
			if _smr_mode or op.has("temperature_c"):
				var p_val: float = float(_smr_fault_state.get("purity_pct", op.get("h2_purity_pct", 99.99)))
				var f_val: float = float(_smr_fault_state.get("h2_flow", 120000.0))
				_story_banner.text = "▶ Unit %d00 (%s) [Continuous Steady-State] | H2 Output: %.0f Nm³/h (%.2f%% Purity @ 400 bar)" % [
					i + 1, title, f_val, p_val
				]
			else:
				_story_banner.text = "▶ Stage %d (%s) [%.0fh-%.0fh]: %s | Yield: %.2f%%" % [
					i + 1, title, float(t_win[0]), float(t_win[1]), eq, yield_val * 100.0
				]
			# Highlight active stepper button
			for b_idx in range(_stepper_buttons.size()):
				var btn: Button = _stepper_buttons[b_idx]
				if b_idx == i:
					btn.modulate = GOOD
				else:
					btn.modulate = Color.WHITE
			return


func _safe_num(arr_val: Variant, idx: int, default_val: float) -> float:
	if not (arr_val is Array):
		return default_val
	var arr: Array = arr_val
	if arr.is_empty():
		return default_val
	if idx < 0:
		return float(arr[0])
	if idx >= arr.size():
		return float(arr[arr.size() - 1])
	return float(arr[idx])


func _interpolate_trajectory_at(hour: float) -> Dictionary:
	var hours: Array = _active_trajectory.get("time_hours", [])
	if hours.is_empty():
		return {}
	var n: int = hours.size()
	var b_arr = _active_trajectory.get("biomass_g_per_L", [15.0])
	var v_arr = _active_trajectory.get("volume_L", [5.0])
	var y_arr = _active_trajectory.get("product_yield_g_per_g", [0.0])
	var f_arr = _active_trajectory.get("feed_rate_L_per_h", [0.0])
	var g_arr = _active_trajectory.get("glucose_g_per_L", [0.0])
	var d_arr = _active_trajectory.get("dissolved_oxygen_pct", [95.0])

	if hour <= float(hours[0]):
		return {
			"time": float(hours[0]),
			"biomass": _safe_num(b_arr, 0, 15.0),
			"glucose": _safe_num(g_arr, 0, 0.0),
			"volume": _safe_num(v_arr, 0, 5.0),
			"feed": _safe_num(f_arr, 0, 0.0),
			"product_yield": _safe_num(y_arr, 0, 0.0),
			"do": _safe_num(d_arr, 0, 95.0),
		}
	if hour >= float(hours[n - 1]):
		return {
			"time": float(hours[n - 1]),
			"biomass": _safe_num(b_arr, n - 1, 0.0),
			"glucose": _safe_num(g_arr, n - 1, 0.0),
			"volume": _safe_num(v_arr, n - 1, 5.0),
			"feed": _safe_num(f_arr, n - 1, 0.0),
			"product_yield": _safe_num(y_arr, n - 1, 0.3307),
			"do": _safe_num(d_arr, n - 1, 95.0),
		}

	for i in range(n - 1):
		var h0 := float(hours[i])
		var h1 := float(hours[i + 1])
		if hour >= h0 and hour <= h1:
			var span := maxf(h1 - h0, 0.0001)
			var f := (hour - h0) / span
			var b0 := _safe_num(b_arr, i, 15.0)
			var b1 := _safe_num(b_arr, i + 1, 15.0)
			var v0 := _safe_num(v_arr, i, 5.0)
			var v1 := _safe_num(v_arr, i + 1, 5.0)
			var y0 := _safe_num(y_arr, i, 0.0)
			var y1 := _safe_num(y_arr, i + 1, 0.0)
			return {
				"time": hour,
				"biomass": lerpf(b0, b1, f),
				"volume": lerpf(v0, v1, f),
				"product_yield": lerpf(y0, y1, f),
				"feed": _safe_num(f_arr, i, 0.0),
				"glucose": _safe_num(g_arr, i, 0.0),
				"do": _safe_num(d_arr, i, 95.0),
			}
	return {}


# ---------------------------------------------------------------- Multi-Stage Factory Stepper

func _build_dynamic_stepper(unit_ops: Array) -> void:
	for c in _stepper_container.get_children():
		c.queue_free()
	_stepper_buttons.clear()

	for i in range(unit_ops.size()):
		var op: Dictionary = unit_ops[i]
		var stage_id: String = str(op.get("stage_id", "stage_%d" % i))
		var title: String = str(op.get("title", stage_id))
		var t_win: Array = op.get("time_window_h", [0, 0])

		var btn := Button.new()
		if op.has("temperature_c"):
			var u_tag := str(op.get("tag", ""))
			btn.text = "[%d] %s" % [i + 1, u_tag if not u_tag.is_empty() else title.substr(0, 16)]
		else:
			btn.text = "[%d] %s" % [i + 1, title]
		btn.add_theme_font_size_override("font_size", 10)
		btn.pressed.connect(func() -> void:
			_on_stage_clicked(stage_id, i)
			_on_scrub(float(t_win[0]))
			_show_toast("Stage %d: %s" % [i + 1, title])
		)
		_stepper_container.add_child(btn)
		_stepper_buttons.append(btn)


func _on_stage_clicked(stage_id: String, stage_index: int) -> void:
	if stage_index >= 0 and stage_index < _unit_operations.size():
		var op: Dictionary = _unit_operations[stage_index]
		if _view != null and _view.has_method("smooth_focus_on_stage"):
			_view.smooth_focus_on_stage(stage_index)
		elif _view != null and _view.has_method("focus_on_stage"):
			_view.focus_on_stage(stage_index)

		if _sim_status != null:
			if op.has("temperature_c") and op.has("pressure_bar"):
				var loops_str: String = ", ".join(PackedStringArray(op.get("control_loops", [])))
				var hazop_str: String = ", ".join(PackedStringArray(op.get("hazop_interlocks", [])))
				var req_str: String = ", ".join(PackedStringArray(op.get("required_parameters", [])))
				_sim_status.text = "Stage: %s [%s]\nTemp: %.1f C | Pressure: %.1f bar | Flow: %.0f Nm3/h (%s)\nDry Flow: %.0f Nm3/h | H2 Flow: %.0f Nm3/h (%.2f%%)\nP&ID Loops: %s\nHAZOP: %s\nRAG Params: %s\nEvidence Tier: %s" % [
					str(op.get("title", stage_id)),
					str(op.get("archetype", op.get("equipment_primitive", ""))),
					float(op.get("temperature_c", 0.0)),
					float(op.get("pressure_bar", 0.0)),
					float(op.get("flow_nm3_h", 0.0)),
					str(op.get("flow_basis", "Wet")),
					float(op.get("dry_flow_nm3_h", op.get("flow_nm3_h", 0.0))),
					float(op.get("h2_flow_nm3_h", 0.0)),
					float(op.get("h2_purity_pct", 0.0)),
					loops_str if loops_str != "" else "Standard Control",
					hazop_str if hazop_str != "" else "None",
					req_str if req_str != "" else "User Design Setpoint",
					str(op.get("evidence_tier", "DIRECT"))
				]
			else:
				_sim_status.text = "Unit Operation: %s (%s)\nGoverning Equation: %s\nVerbatim Quote: %s\nDOI: %s\nEvidence Tier: %s" % [
					str(op.get("title", stage_id)),
					str(op.get("equipment_primitive", "")),
					str(op.get("governing_equation", "")),
					str(op.get("verbatim_quote", "")),
					str(op.get("doi", "")),
					str(op.get("evidence_tier", "DIRECT"))
				]
			_sim_status.modulate = GOOD if str(op.get("evidence_tier")) == "DIRECT" else WARN
			if not _is_drawer_open:
				_toggle_right_drawer()


func _build_dynamic_floating_badges(unit_ops: Array) -> void:
	_unit_operations = unit_ops
	_build_dynamic_stepper(unit_ops)
	for b in _dynamic_badges:
		b.queue_free()
	_dynamic_badges.clear()

	for i in range(unit_ops.size()):
		var op: Dictionary = unit_ops[i]
		var stage_id: String = str(op.get("stage_id", "stage_%d" % i))
		var title: String = str(op.get("title", stage_id))
		var tier: String = str(op.get("evidence_tier", "DIRECT"))
		var t_win: Array = op.get("time_window_h", [0, 0])
		var col := GOOD if tier == "DIRECT" else (WARN if tier == "ANALOGUE_BRIDGE" else Color(0.95, 0.25, 0.25))

		var label_text: String
		if op.has("temperature_c"):
			var u_tag := str(op.get("tag", ""))
			label_text = "[%d] %s" % [i + 1, u_tag if not u_tag.is_empty() else title.substr(0, 16)]
		else:
			label_text = "[%s] %s [%.0fh-%.0fh] • %s" % [
				title,
				str(op.get("equipment_primitive", "vessel")),
				float(t_win[0]),
				float(t_win[1]),
				tier
			]
		var badge := _create_callout_badge("stage_%d" % i, label_text, col)
		badge.pressed.connect(_on_stage_clicked.bind(stage_id, i))
		_hud_overlay.add_child(badge)
		_dynamic_badges.append(badge)


func _update_floating_badges_positions() -> void:
	if _view == null:
		return
	if not _dynamic_badges.is_empty():
		var cam := _view.get_camera()
		if cam == null:
			return
		var count := _unit_operations.size()
		var is_chem: bool = count > 0 and (_unit_operations[0] is Dictionary) and (_unit_operations[0] as Dictionary).has("temperature_c")
		var total_span := float(count - 1) * 1.95
		for i in range(_dynamic_badges.size()):
			var b: Button = _dynamic_badges[i]
			if not is_instance_valid(b):
				continue
			var world_pos: Vector3
			if is_chem and _view.has_method("get_stage_world_position"):
				var base_p: Vector3 = _view.get_stage_world_position(i)
				world_pos = base_p + Vector3(0.0, 0.14, 1.35)
			else:
				var pos_x := -total_span * 0.5 + float(i) * 1.95
				world_pos = Vector3(pos_x, 2.2, 0.0)
			var sp := cam.unproject_position(world_pos)
			b.position = sp + (Vector2(-48, -12) if is_chem else Vector2(-80, -25))
			b.visible = (not cam.is_position_behind(world_pos))
		return


func _create_callout_badge(comp_name: String, label_text: String, col: Color) -> Button:
	var btn := Button.new()
	btn.name = "CalloutBadge_" + comp_name
	btn.text = label_text
	btn.mouse_filter = Control.MOUSE_FILTER_STOP
	btn.add_theme_font_size_override("font_size", 9)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.10, 0.14, 0.90)
	style.border_color = col
	style.border_width_bottom = 2
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.corner_radius_bottom_left = 4
	style.corner_radius_bottom_right = 4
	style.corner_radius_top_left = 4
	style.corner_radius_top_right = 4
	btn.add_theme_stylebox_override("normal", style)
	btn.modulate = col
	btn.pressed.connect(_on_hardware_component_clicked.bind(comp_name))
	return btn


func _on_hardware_component_clicked(comp_name: String) -> void:
	_selected_component = comp_name
	var comp_title := "Hardware Component"
	var paper_info := "Empirical Mechanism"
	var quote := "Verified empirical data from primary literature."
	var equation := "Dynamic kinetic balance"

	match comp_name:
		"feed_tube":
			comp_title = "Feed Dip Tube / Reagent Inlet"
			paper_info = "Primary Feed Mechanism"
			quote = "Controlled feed trajectory maintaining optimal substrate concentration."
			equation = "F(t) = ((mu_set / Y_XS) + m) * (X_F * V_F / S_F) * exp(mu_set * (t - t_F))"
		"culture_broth":
			comp_title = "Culture Broth / Extraction Slurry"
			paper_info = "Core Primary Kinetics Mechanism"
			quote = "Governing kinetic equations for solid-liquid extraction or cellular growth."
			equation = "Y(t) = Y_max * (1 - exp(-k_ext * t))"
		"impeller_sparger":
			comp_title = "Agitator & Aeration / Gas Dispersion Assembly"
			paper_info = "Interfacial Mass Transfer Model"
			quote = "Fluid agitation and mass transfer balance: dCL/dt = kLa * (C* - CL) - qO2 * X"
			equation = "kLa = 120-180 1/h; Agitation = 250-4500 RPM"
		"harvest_valve":
			comp_title = "Downstream Harvest / Product Recovery Valve"
			paper_info = "Downstream Separation & Purification Mechanism"
			quote = "Product separation, precipitation, or wet spinning recovery accounting."
			equation = "Product yield = Y_PX * final_biomass_dcw * recovery_efficiency"

	if _sim_status != null:
		_sim_status.text = "Selected Component: %s\nGoverning Model: %s\nEquation: %s\nQuote: %s" % [
			comp_title, paper_info, equation, quote
		]
		_sim_status.modulate = GOOD
	_show_toast("Inspecting: %s" % comp_title)


# ---------------------------------------------------------------- Run File Loader

func load_run_file(path: String) -> void:
	var file_path := path
	if not FileAccess.file_exists(file_path):
		var global_p := ProjectSettings.globalize_path(path)
		if FileAccess.file_exists(global_p):
			file_path = global_p
	if not FileAccess.file_exists(file_path):
		if _status != null:
			_status.text = "Run file not found: %s" % path
		return

	var file := FileAccess.open(file_path, FileAccess.READ)
	if file == null:
		return

	var text := file.get_as_text()
	var test_json_conv := JSON.new()
	var err := test_json_conv.parse(text)
	if err != OK:
		return

	load_run_dict(test_json_conv.data)


func load_run_dict(payload: Dictionary) -> void:
	_result = payload
	if _prompt != null:
		_prompt.text = str(payload.get("prompt", ""))

	var is_halted: bool = str(payload.get("status", "")).to_upper() == "HALTED" or str(payload.get("evidence_tier", "")).to_upper() == "UNVERIFIED"
	if is_halted:
		if _status != null:
			_status.text = "HALTED: InsufficientEvidenceError (Scientific Integrity Guard)"
			_status.modulate = BAD
		if _sim_status != null:
			_sim_status.text = "Status: HALTED (Insufficient verified empirical literature)"
			_sim_status.modulate = BAD
		_reality_compiler_audit = payload.get("reality_compiler_audit", {})
		if not _reality_compiler_audit.is_empty():
			_update_reality_compiler_badges(_reality_compiler_audit.get("violations", []))
		if _confidence_badge != null:
			_confidence_badge.text = "[Confidence: 0% • HALTED: InsufficientEvidenceError]"
			_confidence_badge.modulate = BAD
		_show_toast("⚠️ InsufficientEvidenceError: Simulation Aborted", 3.0)
	else:
		if _status != null:
			_status.text = "Loaded verified run %s (cache_hit=%s)" % [
				str(payload.get("run_id", "?")),
				str(payload.get("cache_hit", true)),
			]
			_status.modulate = GOOD
		if _sim_status != null:
			_sim_status.text = "Status: %s" % str(payload.get("status", "COMPLETED"))
			_sim_status.modulate = GOOD

		var conf: float = float(payload.get("confidence_score", 100.0))
		var has_analogue: bool = bool(payload.get("has_analogue_bridge", false))
		var prov: Dictionary = payload.get("epistemic_provenance", {})
		var audit: Dictionary = payload.get("epistemic_audit", {})
		var sandbox_cfg: Dictionary = payload.get("sandbox_config", {})
		var is_chem_sandbox: bool = str(sandbox_cfg.get("mode", "")) == "chemical_plant"
		_reality_compiler_audit = payload.get("reality_compiler_audit", {})
		_set_sandbox_mode(is_chem_sandbox)
		if not is_chem_sandbox and not _reality_compiler_audit.is_empty():
			_update_reality_compiler_badges(_reality_compiler_audit.get("violations", []))
		if _confidence_badge != null:
			if not prov.is_empty() and not has_analogue:
				var t1_cnt: int = int(prov.get("tier_1_quarantine_count", 0))
				var t0_cnt: int = int(prov.get("tier_0_internal_bench_count", 0))
				var setpoints_dict: Dictionary = audit.get("user_design_setpoints", {})
				var unv_dict: Dictionary = audit.get("unverified_assumptions", {})
				var gaps_cnt: int = int(audit.get("gap_count", 0))
				var peer_cnt: int = t1_cnt + t0_cnt
				_confidence_badge.text = "[Provenance: %d Tier 1 Peer-Reviewed • %d User Setpoints • %d Unverified Hypotheses • %d Gaps]" % [peer_cnt, setpoints_dict.size(), unv_dict.size(), gaps_cnt]
				_confidence_badge.modulate = GOOD if (gaps_cnt == 0 and unv_dict.is_empty()) else WARN
			else:
				var tier_str := "ANALOGUE BRIDGE" if has_analogue else ("DIRECT" if conf >= 99.0 else "PEER-REVIEWED")
				_confidence_badge.text = "[Confidence: %d%% • %s]" % [int(conf), tier_str]
				_confidence_badge.modulate = GOOD if conf >= 90.0 else (WARN if conf >= 50.0 else BAD)
		if _analogue_banner != null:
			_analogue_banner.visible = has_analogue

	var diagram_path := str(payload.get("diagram_path", ""))
	if diagram_path != "":
		_load_diagram(diagram_path)
	elif _diagram_rect != null:
		_diagram_rect.texture = null

	var manifest: Dictionary = payload.get("literature_review_manifest", {})
	_active_run_manifest = manifest
	_render_literature_manifest(manifest)

	var trajectories: Dictionary = payload.get("trajectories", {})
	if not trajectories.is_empty():
		_active_trajectory = trajectories
		var hours: Array = trajectories.get("time_hours", [])
		if not hours.is_empty():
			_sim_duration_hours = float(hours[hours.size() - 1])
			if _time_slider != null:
				_time_slider.max_value = _sim_duration_hours
		var biomass: Array = trajectories.get("biomass_g_per_L", [])
		if _growth != null:
			_growth.set_trajectory_data(hours, biomass, _current_model_label)
		_apply_playback_time(0.0)

	var blueprint: Dictionary = payload.get("anatomy_blueprint", {})
	if not blueprint.is_empty() or payload.has("stages"):
		_anatomy_blueprint = blueprint
		var unit_ops: Array = payload.get("stages", blueprint.get("unit_operations", []))
		var conns: Array = blueprint.get("connections", payload.get("composition_graph", {}).get("edges", []))
		if _view != null and _view.has_method("set_plant_connections"):
			_view.set_plant_connections(conns)
		if _view != null and _view.has_method("build_anatomy_bench"):
			_view.build_anatomy_bench(unit_ops)
		_build_dynamic_floating_badges(unit_ops)


func load_preset(preset_name: String) -> void:
	match preset_name.to_lower():
		"ecoli", "e. coli", "e_coli", "e-coli":
			var candidates := ["res://.artifacts/ecoli_run.json", "res://composition/data/runs/ecoli_run.json", "res://assets/runs/ecoli_run.json", ".artifacts/ecoli_run.json"]
			var loaded := false
			for p in candidates:
				if FileAccess.file_exists(p):
					load_run_file(p)
					loaded = true
					break
			if not loaded:
				load_run_file("res://composition/data/runs/ecoli_run.json")
			_show_toast("🧬 Loaded Preset: E. coli Fed-Batch Fermentation", 2.2)
		"unverified", "unverified_halt", "halt", "insufficient_evidence", "insufficient":
			var candidates := ["res://.artifacts/unverified_halt_run.json", "res://composition/data/runs/unverified_halt_run.json", "res://assets/runs/unverified_halt_run.json", ".artifacts/unverified_halt_run.json"]
			var loaded := false
			for p in candidates:
				if FileAccess.file_exists(p):
					load_run_file(p)
					loaded = true
					break
			if not loaded:
				load_run_file("res://composition/data/runs/unverified_halt_run.json")
			_show_toast("⚠️ InsufficientEvidenceError: Execution Blocked (Red Alert)", 3.5)
		_: # "saccharina", default
			var candidates := ["res://.artifacts/latest_prompt_run.json", "res://composition/data/runs/latest_prompt_run.json", "res://assets/runs/latest_prompt_run.json", ".artifacts/latest_prompt_run.json"]
			var loaded := false
			for p in candidates:
				if FileAccess.file_exists(p):
					load_run_file(p)
					loaded = true
					break
			if not loaded:
				load_run_file("res://composition/data/runs/latest_prompt_run.json")
			_show_toast("🌿 Loaded Preset: Saccharina latissima Alginate Extraction", 2.2)


func _setup_web_integration() -> void:
	if not OS.has_feature("web"):
		return

	var win = JavaScriptBridge.get_interface("window")
	_js_preset_cb = JavaScriptBridge.create_callback(_on_js_switch_preset)
	if win != null:
		win.scaleupSwitchPreset = _js_preset_cb

	_js_json_cb = JavaScriptBridge.create_callback(_on_js_load_json)
	if win != null:
		win.scaleupLoadJson = _js_json_cb

	_js_msg_cb = JavaScriptBridge.create_callback(_on_js_window_message)
	if win != null:
		win.addEventListener("message", _js_msg_cb)

	# Read URL query parameters via window.location.search
	var query_var: Variant = JavaScriptBridge.eval("window.location.search")
	var query: String = str(query_var) if query_var != null else ""
	if "preset=ecoli" in query.to_lower():
		load_preset("ecoli")
	elif "preset=unverified" in query.to_lower() or "unverified_halt" in query.to_lower() or "insufficient" in query.to_lower():
		load_preset("unverified_halt")
	elif "preset=saccharina" in query.to_lower():
		load_preset("saccharina")
	elif FileAccess.file_exists("res://composition/data/smr_8unit_default.json"):
		load_run_file("res://composition/data/smr_8unit_default.json")
	else:
		load_preset("saccharina")


func _on_js_switch_preset(args: Array) -> void:
	if args.size() > 0 and args[0] != null:
		load_preset(str(args[0]))


func _on_js_load_json(args: Array) -> void:
	if args.is_empty() or args[0] == null:
		return
	var arg = args[0]
	if typeof(arg) == TYPE_STRING:
		var parser := JSON.new()
		if parser.parse(str(arg)) == OK and typeof(parser.data) == TYPE_DICTIONARY:
			load_run_dict(parser.data)
	elif typeof(arg) == TYPE_DICTIONARY:
		load_run_dict(arg)


func _on_js_window_message(args: Array) -> void:
	if args.is_empty() or args[0] == null:
		return
	var event = args[0]
	var raw_data: Variant = null
	if typeof(event) == TYPE_OBJECT:
		raw_data = event.get("data")
	elif typeof(event) == TYPE_DICTIONARY:
		raw_data = event.get("data")
	else:
		raw_data = event

	if raw_data == null:
		return

	if typeof(raw_data) == TYPE_STRING:
		var s := str(raw_data).strip_edges()
		if s.begins_with("{"):
			var parser := JSON.new()
			if parser.parse(s) == OK and typeof(parser.data) == TYPE_DICTIONARY:
				var d: Dictionary = parser.data
				if d.has("preset"):
					load_preset(str(d["preset"]))
				elif d.has("run_id") or d.has("trajectories"):
					load_run_dict(d)
		else:
			load_preset(s)
	elif typeof(raw_data) == TYPE_DICTIONARY:
		if raw_data.has("preset"):
			load_preset(str(raw_data["preset"]))
		elif raw_data.has("run_id") or raw_data.has("trajectories"):
			load_run_dict(raw_data)

func _load_diagram(rel_path: String) -> void:
	if _diagram_rect == null:
		return
	var global_path := ProjectSettings.globalize_path("res://" + rel_path)
	if not FileAccess.file_exists(global_path):
		var alt_path := ProjectSettings.globalize_path(rel_path)
		if FileAccess.file_exists(alt_path):
			global_path = alt_path
	if FileAccess.file_exists(global_path):
		var img := Image.load_from_file(global_path)
		if img != null:
			var tex := ImageTexture.create_from_image(img)
			_diagram_rect.texture = tex


func _render_literature_manifest(manifest: Dictionary) -> void:
	if _manifest_body == null:
		return
	_clear(_manifest_body)
	if manifest.is_empty():
		_paragraph(_manifest_body, "No literature review manifest provided.", MUTED)
		return

	var mode := str(manifest.get("reconstruction_mode", "central_knowledge_library"))
	var organism := str(manifest.get("target_organism", "Escherichia coli"))
	_field(_manifest_body, "Target organism", organism)
	_field(_manifest_body, "Reconstruction Mode", mode)

	var papers: Array = manifest.get("combined_papers", [])
	var paper_lines: Array = []
	for p in papers:
		if p is Dictionary:
			var title := str(p.get("title", ""))
			var doi := str(p.get("doi", ""))
			var yr := str(p.get("year", ""))
			paper_lines.append("%s (%s) — DOI: %s" % [title, yr, doi])
	_field(_manifest_body, "Combined Papers", _bullet(paper_lines), GOOD)

	var grounded_params: Dictionary = _result.get("grounded_parameters", {})
	if not grounded_params.is_empty():
		var param_lines: Array = []
		for p_key in grounded_params.keys():
			var gp: Variant = grounded_params[p_key]
			if not (gp is Dictionary):
				continue
			var gp_d: Dictionary = gp
			var val_str := "%.2f %s" % [float(gp_d.get("value", 0.0)), str(gp_d.get("unit", ""))]
			var meta_parts: Array = []
			if gp_d.get("value_min", null) != null and gp_d.get("value_max", null) != null:
				meta_parts.append("Range: %.2f - %.2f %s" % [float(gp_d["value_min"]), float(gp_d["value_max"]), str(gp_d.get("unit", ""))])
			var env: Variant = gp_d.get("operating_envelope", null)
			if env is Dictionary:
				var env_d: Dictionary = env
				var env_bits: Array = []
				if env_d.get("temperature_c", null) != null:
					env_bits.append("%.1f °C" % float(env_d["temperature_c"]))
				if env_d.get("ph", null) != null:
					env_bits.append("pH %.1f" % float(env_d["ph"]))
				if env_d.get("pressure_bar", null) != null:
					env_bits.append("%.1f bar" % float(env_d["pressure_bar"]))
				if not env_bits.is_empty():
					meta_parts.append("Envelope: " + ", ".join(PackedStringArray(env_bits)))
			var suffix := (" [" + " | ".join(PackedStringArray(meta_parts)) + "]") if not meta_parts.is_empty() else ""
			param_lines.append("%s: %s%s" % [str(p_key), val_str, suffix])
		_field(_manifest_body, "Grounded Parameters & Envelopes", _bullet(param_lines), GOOD)


func _on_hotswap_selected(index: int) -> void:
	if index <= 0:
		_ghost_trajectory = {}
		_delta_badge.visible = false
		if _growth != null and not _active_trajectory.is_empty():
			_growth.set_trajectory_data(
				_active_trajectory.get("time_hours", []),
				_active_trajectory.get("biomass_g_per_L", []),
				_current_model_label
			)
		return

	_ghost_trajectory = _active_trajectory.duplicate(true)
	_ghost_label = _current_model_label
	_delta_badge.visible = true
	_delta_badge.text = "Hot-swap alternative active: delta comparison enabled."
	_delta_badge.modulate = GOOD
	if _growth != null:
		_growth.set_trajectory_data(
			_active_trajectory.get("time_hours", []),
			_active_trajectory.get("biomass_g_per_L", []),
			"Alternative Mechanism",
			_ghost_trajectory.get("time_hours", []),
			_ghost_trajectory.get("biomass_g_per_L", []),
			_ghost_label
		)


func _on_generate_pressed() -> void:
	if _prompt.text.strip_edges() == "":
		return
	_start_interpret("interpret_and_run")


func _on_interpret_pressed() -> void:
	if _prompt.text.strip_edges() == "":
		return
	_start_interpret("interpret")


func _start_interpret(kind: String) -> void:
	_request = kind
	_status.text = "Reading prompt against knowledge library..."
	_set_buttons(false)
	_runner.interpret_prompt(_prompt.text)


func _on_execute_pressed() -> void:
	if not bool(_interpretation.get("ok", false)):
		_sim_status.text = "There is no validated configuration to execute."
		return
	_start_run()


func _start_run() -> void:
	_request = "run"
	_sim_status.text = "Executing configuration through runner..."
	_set_buttons(false)
	var result_dir := ProjectSettings.globalize_path(RESULT_PATH).get_base_dir()
	DirAccess.make_dir_recursive_absolute(result_dir)
	_runner.run_prompt(_prompt.text, RESULT_PATH)


func _on_runner_finished(payload: Dictionary) -> void:
	_set_buttons(true)
	if payload.is_empty():
		_status.text = "The prompt runner returned no readable document."
		return
	if _request == "interpret" or _request == "interpret_and_run":
		_interpretation = payload
		if _request == "interpret_and_run" and bool(payload.get("ok", false)):
			_start_run()
			return
		_status.text = "Interpretation complete."
		return
	if _request == "run":
		_result = payload
		_render_results(payload)


func _render_results(payload: Dictionary) -> void:
	_data = ReplayData.new()
	_data.load_payload(payload, INSTANCE_ID)
	if _growth != null:
		_growth.set_data(_data)
	if _cascade != null:
		_cascade.set_data(_data)
	if _data.has_trajectory():
		_on_scrub(_data.hours[0])


func _detect_composition_dir() -> String:
	var root := ProjectSettings.globalize_path("res://")
	for candidate in [root.path_join("composition"), root]:
		var dir := DirAccess.open(candidate)
		if dir != null and dir.file_exists("composition/runner.py"):
			return candidate
	return root.path_join("composition")


func _get_run_file_arg() -> String:
	var user_args := OS.get_cmdline_user_args()
	for i in range(user_args.size()):
		if user_args[i] == "--run-file" and i + 1 < user_args.size():
			return user_args[i + 1]
	var all_args := OS.get_cmdline_args()
	for i in range(all_args.size()):
		if all_args[i] == "--run-file" and i + 1 < all_args.size():
			return all_args[i + 1]
	return ""


func _set_buttons(enabled: bool) -> void:
	if _generate != null: _generate.disabled = not enabled
	if _interpret_only != null: _interpret_only.disabled = not enabled
	if _execute != null: _execute.disabled = not enabled


func _section(parent: VBoxContainer, text: String) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = Color(0.35, 0.85, 1.0)
	parent.add_child(label)


func _field(parent: VBoxContainer, title: String, value: String, col: Color = Color.WHITE) -> void:
	var l := Label.new()
	l.text = "%s: %s" % [title, value]
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 9)
	l.modulate = col
	parent.add_child(l)


func _paragraph(parent: VBoxContainer, text: String, col: Color = Color.WHITE) -> void:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 9)
	l.modulate = col
	parent.add_child(l)


func _bullet(lines: Array) -> String:
	return "\n".join(lines)


func _clear(parent: Node) -> void:
	for child in parent.get_children():
		child.queue_free()


func _create_loading_overlay() -> PanelContainer:
	var panel := PanelContainer.new()
	panel.name = "StreamingLoadingOverlay"
	panel.set_anchors_preset(Control.PRESET_CENTER_TOP)
	panel.offset_top = 68
	panel.custom_minimum_size = Vector2(580, 52)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.04, 0.07, 0.12, 0.90)
	style.corner_radius_top_left = 8
	style.corner_radius_top_right = 8
	style.corner_radius_bottom_left = 8
	style.corner_radius_bottom_right = 8
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.border_color = Color(0.20, 0.75, 0.95, 0.85)
	panel.add_theme_stylebox_override("panel", style)

	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 4)
	panel.add_child(vb)

	_loading_label = Label.new()
	_loading_label.text = "⚡ Streaming Unit Operations... [Stage 1/6]"
	_loading_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_loading_label.add_theme_font_size_override("font_size", 12)
	_loading_label.modulate = Color(0.4, 0.95, 1.0)
	vb.add_child(_loading_label)

	_loading_bar = ProgressBar.new()
	_loading_bar.min_value = 0.0
	_loading_bar.max_value = 100.0
	_loading_bar.value = 16.6
	_loading_bar.show_percentage = false
	_loading_bar.custom_minimum_size = Vector2(0, 6)
	var bar_style := StyleBoxFlat.new()
	bar_style.bg_color = Color(0.15, 0.85, 0.55)
	bar_style.corner_radius_top_left = 3
	bar_style.corner_radius_top_right = 3
	bar_style.corner_radius_bottom_left = 3
	bar_style.corner_radius_bottom_right = 3
	_loading_bar.add_theme_stylebox_override("fill", bar_style)
	vb.add_child(_loading_bar)

	return panel


func _on_bench_build_progress(cur: int, total: int, stage_title: String) -> void:
	if _loading_panel != null:
		_loading_panel.visible = true
	if _loading_label != null:
		_loading_label.text = "⚡ Streaming Unit Operations... [Stage %d/%d: %s]" % [cur, total, stage_title]
	if _loading_bar != null:
		_loading_bar.value = (float(cur) / float(total)) * 100.0


func _on_bench_build_completed() -> void:
	if _loading_label != null:
		_loading_label.text = "✓ All 6 Unit Operations Streamed & Ready (100%)"
	if _loading_bar != null:
		_loading_bar.value = 100.0

	# Fade out loading panel
	if _loading_panel != null:
		var tw := create_tween()
		tw.tween_property(_loading_panel, "modulate:a", 0.0, 0.6)
		tw.finished.connect(func(): if _loading_panel != null: _loading_panel.visible = false)

	# 1.0-second settle delay before starting paced playback
	await get_tree().create_timer(1.0).timeout
	_is_stream_settled = true
	if not _is_playing:
		_is_playing = true
		_update_play_btn()
		_show_toast("▶ Simulation Online — Stage-Normalized 1x Pacing Active", 2.5)

	var shot_path := _get_screenshot_arg()
	if not shot_path.is_empty():
		await get_tree().process_frame
		await get_tree().process_frame
		var img := get_viewport().get_texture().get_image()
		if img != null:
			img.save_png(shot_path)
		get_tree().quit()


func _get_screenshot_arg() -> String:
	var all_args := OS.get_cmdline_user_args() + OS.get_cmdline_args()
	for i in range(all_args.size()):
		if all_args[i] == "--screenshot" and i + 1 < all_args.size():
			return all_args[i + 1]
	return ""


func _on_prev_stage_clicked() -> void:
	var cur_idx: int = _get_stage_index_at_hour(_current_sim_time)
	var target_idx: int = maxi(cur_idx - 1, 0)
	_jump_to_stage_by_index(target_idx)


func _on_next_stage_clicked() -> void:
	var cur_idx: int = _get_stage_index_at_hour(_current_sim_time)
	var target_idx: int = mini(cur_idx + 1, _unit_operations.size() - 1)
	_jump_to_stage_by_index(target_idx)
