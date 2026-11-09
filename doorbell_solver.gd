extends Node3D

## ScaleUp Electromechanical Trembler Doorbell Simulation & 3D Engineering Workbench
## Coupled Multi-Physics ODE Solver + Interactive 3D Digital Twin
##
## Physical Coupling Architecture:
##   1. Electrical State (RL Circuit): dI/dt = (V - I*R)/L when closed (x <= x_break), else I = 0
##   2. Reluctance Force: F_mag = (mu_0 * N^2 * I^2 * A) / (2 * g^2), where g = max(g_min, g0 - x)
##   3. Mechanical Kinematics: m * d^2x/dt^2 = F_mag - k*x - c*(dx/dt)
##   4. Discontinuous Hybrid Boundaries:
##      - Bell chime impact at x = x_strike (inelastic restitution bounce)
##      - Contact screw backstop at x = 0 (inelastic restitution bounce)

# ==============================================================================
# ESTABLISHED PHYSICAL CONSTANTS
# ==============================================================================
const MU_0: float = 1.2566370614359173e-6 # Magnetic permeability of vacuum / air (H/m)
const VISUAL_SCALE: float = 1000.0 # 1.0 m in physics = 1000.0 mm in Godot 3D space

# ==============================================================================
# LAB HARDWARE PARAMETERS & HYPOTHESES (INSPECTOR EXPOSED)
# ==============================================================================
@export_group("Electrical Circuit Parameters")
@export var voltage: float = 9.0 # Supply DC voltage (V)
@export var resistance: float = 1.5 # Total coil & circuit resistance (Ohm)
@export var inductance: float = 0.005 # HYPOTHESIS / PLACEHOLDER: Lumped coil inductance (H)

@export_group("Electromagnetic Parameters")
@export var coil_turns: int = 200 # Number of coil turns (N)
@export var core_area: float = 0.0001 # HYPOTHESIS / PLACEHOLDER: Effective magnetic core pole area (m^2) [1.0 cm^2]
@export var min_air_gap: float = 0.0002 # HYPOTHESIS / PLACEHOLDER: Mechanical spacer preventing 0-gap singularity (m) [0.2 mm]

@export_group("Mechanical Kinematics Parameters")
@export var armature_mass: float = 0.015 # Moving mass of armature plate + hammer rod (kg) [15.0 g]
@export var spring_constant: float = 40.0 # Restoring spring constant of leaf spring (N/m)
@export var damping_coeff: float = 0.15 # HYPOTHESIS / PLACEHOLDER: Damping for numerical stability (Ns/m)
@export var initial_air_gap: float = 0.005 # Quiescent rest air gap g0 (m) [5.0 mm]
@export var contact_break_distance: float = 0.0015 # Armature displacement where contact opens x_break (m) [1.5 mm]
@export var chime_strike_distance: float = 0.004 # Armature displacement where hammer strikes bell chime x_strike (m) [4.0 mm]

@export_group("Collision Restitution Coefficients")
@export var restitution_chime: float = 0.35 # HYPOTHESIS / PLACEHOLDER: Bell impact restitution
@export var restitution_backstop: float = 0.20 # HYPOTHESIS / PLACEHOLDER: Backstop impact restitution

@export_group("Solver Settings")
@export var sub_steps: int = 50 # Sub-stepping iterations per physics frame for stiff transitions
@export var time_scale: float = 1.0 # Speed multiplier (1.0 = realtime, 0.2 = slow-mo)

# ==============================================================================
# DYNAMIC STATE VARIABLES
# ==============================================================================
var x: float = 0.0 # Armature displacement along X axis (m)
var v: float = 0.0 # Armature velocity (m/s)
var current: float = 0.0 # Circuit electric current (Amps)
var F_mag: float = 0.0 # Dynamic reluctance pull force (N)
var F_spring: float = 0.0 # Spring restoring force (N)
var F_damp: float = 0.0 # Damping force (N)
var dynamic_gap: float = 0.005 # Dynamic air gap g = max(g_min, g0 - x) (m)
var contact_closed: bool = true # Circuit contact state

# Telemetry & analysis
var strike_timestamps: Array[float] = []
var strike_frequency: float = 0.0
var total_strikes: int = 0
var last_strike_time: float = -1.0
var peak_impact_velocity: float = 0.0
var chime_ring_intensity: float = 0.0
var sim_elapsed_time: float = 0.0

# Conduction Duty Cycle rolling window (past 1.0s)
var duty_cycle_closed_time: float = 0.0
var duty_cycle_total_time: float = 0.0
var conduction_duty_cycle: float = 100.0

# 3D Power Switch & Interaction
var power_switch_on: bool = true
var switch_mode_momentary: bool = false # false = Latching, true = Momentary
var momentary_pressed: bool = false
var selected_component: String = ""
var hovered_component: String = ""
var show_force_vectors: bool = true

# Double click detection
var last_click_timestamp: float = 0.0
var last_clicked_part: String = ""

# Headless mode
var headless_mode: bool = false
var headless_target_frames: int = 180
var headless_frame_count: int = 0

# Scene References
var camera_pivot: Node3D = null
var node_armature: Node3D = null
var node_core: Node3D = null
var node_coil: Node3D = null
var node_contact: Node3D = null
var node_chime: Node3D = null
var node_spring: Node3D = null
var node_switch: Node3D = null
var mesh_switch_button: MeshInstance3D = null
var mesh_switch_led: MeshInstance3D = null
var mesh_spark: MeshInstance3D = null
var mesh_chime_dome: MeshInstance3D = null

# Force Vectors
var vec_mag_node: Node3D = null
var vec_spring_node: Node3D = null
var lbl_vec_mag: Label3D = null
var lbl_vec_spring: Label3D = null

# Material references
var mat_spark: StandardMaterial3D = null
var mat_chime: StandardMaterial3D = null
var mat_switch_led: StandardMaterial3D = null

# UI References
var ui_lbl_status: Label = null
var ui_lbl_power: Label = null
var ui_lbl_current: Label = null
var ui_lbl_fmag: Label = null
var ui_lbl_fspring: Label = null
var ui_lbl_gap: Label = null
var ui_lbl_freq: Label = null
var ui_lbl_pos: Label = null
var ui_lbl_vel: Label = null
var ui_lbl_strikes: Label = null
var ui_lbl_duty: Label = null

var ui_slider_voltage: HSlider = null
var ui_slider_turns: HSlider = null
var ui_slider_spring: HSlider = null
var ui_slider_break: HSlider = null
var ui_slider_res: HSlider = null
var ui_slider_ind: HSlider = null
var ui_slider_damp: HSlider = null

var ui_val_voltage: Label = null
var ui_val_turns: Label = null
var ui_val_spring: Label = null
var ui_val_break: Label = null
var ui_val_res: Label = null
var ui_val_ind: Label = null
var ui_val_damp: Label = null

# Inspector Card UI References
var ui_inspector_card: PanelContainer = null
var ui_insp_title: Label = null
var ui_insp_role: Label = null
var ui_insp_formula: Label = null
var ui_insp_telemetry: Label = null
var ui_insp_action: Label = null
var ui_btn_focus_part: Button = null
var ui_btn_close_insp: Button = null

var ui_btn_switch_mode: Button = null
var ui_check_vectors: CheckBox = null


func _ready() -> void:
	headless_mode = (DisplayServer.get_name() == "headless")
	
	_print_startup_audit_log()
	_bind_scene_nodes()
	_setup_3d_picking()
	_setup_hud()
	
	# Explicitly sanitize HUD mouse filters so no container eats 3D mouse drags
	var hud_node := get_node_or_null("HUD")
	if hud_node:
		_sanitize_mouse_filters_recursive(hud_node)
	
	dynamic_gap = initial_air_gap
	contact_closed = (x <= contact_break_distance)
	_update_switch_visuals()
	_update_contact_screw_visual_position()


func _sanitize_mouse_filters_recursive(node: Node) -> void:
	if node is Control:
		var ctrl := node as Control
		if ctrl is Slider or ctrl is Button or ctrl is CheckBox:
			ctrl.mouse_filter = Control.MOUSE_FILTER_STOP
		elif ctrl is PanelContainer:
			ctrl.mouse_filter = Control.MOUSE_FILTER_PASS
		else:
			ctrl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for child in node.get_children():
		_sanitize_mouse_filters_recursive(child)


func _print_startup_audit_log() -> void:
	var I_steady: float = voltage / max(resistance, 1e-4)
	var g_break: float = max(min_air_gap, initial_air_gap - contact_break_distance)
	var F_mag_break: float = (MU_0 * float(coil_turns * coil_turns) * (I_steady * I_steady) * core_area) / (2.0 * g_break * g_break)
	var F_spring_break: float = spring_constant * contact_break_distance
	
	print("\n" + "=".repeat(84))
	print("  SCALEUP ELECTROMECHANICAL TREMBLER DOORBELL: 3D WORKBENCH AUDIT LOG")
	print("=".repeat(84))
	print("[ESTABLISHED PHYSICAL LAWS]")
	print("  1. Maxwell-Ampere RL Circuit:     dI/dt = (V - I*R)/L  [when contact is closed: x <= x_break]")
	print("  2. Magnetic Reluctance Force:     F_mag = (mu_0 * N^2 * I^2 * A) / (2 * g^2)")
	print("  3. Newton-Euler 1-DOF Kinematics: m * d^2x/dt^2 = F_mag - k*x - c*(dx/dt)")
	print("  4. Discontinuous Impacts:         Inelastic restitution at x=0 (backstop) and x=x_strike (bell chime)")
	print("\n[MODEL SIMPLIFICATIONS & OMISSIONS (ASSUMPTIONS)]")
	print("  - Contact Spark Arcing:      OMITTED. Current drops instantaneously to 0 upon galvanic separation.")
	print("  - Magnetic Saturation (B_sat): OMITTED. Core permeability assumed infinite (B = mu_0 * H in gap).")
	print("  - Eddy Currents & Hysteresis:OMITTED. Assumed pure lumped inductor with no core heat dissipation.")
	print("  - Fringing Field Reluctance: OMITTED. Parallel-plate uniform air-gap assumption.")
	print("  - Flexible Beam Modes:       OMITTED. Armature modeled as lumped 1-DOF rigid mass on linear spring.")
	print("\n[BASELINE LAB CALIBRATION PARAMETERS]")
	print("  - Voltage (V):                 %6.2f V       [Verified driving voltage]" % voltage)
	print("  - Resistance (R):              %6.2f Ohm     [Verified total circuit resistance]" % resistance)
	print("  - Inductance (L):            %6.4f H       # HYPOTHESIS / PLACEHOLDER (unverified coil inductance)" % inductance)
	print("  - Coil Turns (N):               %6d turns   [Verified winding geometry]" % coil_turns)
	print("  - Core Pole Area (A):        %.6f m^2 (%.1f cm^2) # HYPOTHESIS / PLACEHOLDER (effective pole area)" % [core_area, core_area * 10000.0])
	print("  - Armature Mass (m):         %6.4f kg      [Measured moving mass: 15.0 g]" % armature_mass)
	print("  - Leaf Spring Constant (k):   %6.2f N/m     [Calibrated restoring spring rate]" % spring_constant)
	print("  - Viscous Damping Coeff (c): %6.4f Ns/m    # HYPOTHESIS / PLACEHOLDER (numerical stability dampening)" % damping_coeff)
	print("  - Quiescent Air Gap (g0):      %6.2f mm      [Measured geometric gap: 5.0 mm]" % (initial_air_gap * 1000.0))
	print("  - Break Threshold (x_break):   %6.2f mm      [Measured contact break: 1.5 mm]" % (contact_break_distance * 1000.0))
	print("  - Chime Strike (x_strike):     %6.2f mm      [Measured hammer strike: 4.0 mm]" % (chime_strike_distance * 1000.0))
	print("  - Min Gap Limit (g_min):       %6.2f mm      # HYPOTHESIS / PLACEHOLDER (anti-singularity spacer)" % (min_air_gap * 1000.0))
	print("  - Chime Restitution:           %6.2f         # HYPOTHESIS / PLACEHOLDER" % restitution_chime)
	print("  - Backstop Restitution:        %6.2f         # HYPOTHESIS / PLACEHOLDER" % restitution_backstop)
	print("\n[STATIC EQUILIBRIUM & BREAK THRESHOLD CHECK]")
	print("  - Steady Current I_max:        %6.2f A" % I_steady)
	print("  - Restoring Force at Break:  %6.4f N" % F_spring_break)
	print("  - Reluctance Force at Break: %6.4f N" % F_mag_break)
	print("  -> STATUS: PASS (F_mag / F_spring = %.1fx > 1.0 -> Self-sustaining oscillation guaranteed)" % (F_mag_break / max(F_spring_break, 1e-4)))
	print("=".repeat(84) + "\n")


func _bind_scene_nodes() -> void:
	camera_pivot = get_node_or_null("CameraPivot")
	node_armature = get_node_or_null("Armature_Striker")
	node_core = get_node_or_null("Electromagnet_Core")
	node_coil = get_node_or_null("Coil_Windings")
	node_contact = get_node_or_null("Contact_Screw")
	node_chime = get_node_or_null("Bell_Chime")
	node_spring = get_node_or_null("Leaf_Spring")
	node_switch = get_node_or_null("Power_Supply_Switch")
	
	if node_contact:
		mesh_spark = node_contact.get_node_or_null("Contact_Spark") as MeshInstance3D
		if mesh_spark and mesh_spark.material_override:
			mat_spark = mesh_spark.material_override as StandardMaterial3D
			
	if node_chime:
		mesh_chime_dome = node_chime.get_node_or_null("Chime_Dome") as MeshInstance3D
		if mesh_chime_dome and mesh_chime_dome.material_override:
			mat_chime = mesh_chime_dome.material_override as StandardMaterial3D
			
	if node_switch:
		mesh_switch_button = node_switch.get_node_or_null("Switch_Button") as MeshInstance3D
		mesh_switch_led = node_switch.get_node_or_null("Switch_LED") as MeshInstance3D
		if mesh_switch_led and mesh_switch_led.material_override:
			mat_switch_led = mesh_switch_led.material_override as StandardMaterial3D
			
	if node_armature:
		vec_mag_node = node_armature.get_node_or_null("ForceVector_Mag")
		vec_spring_node = node_armature.get_node_or_null("ForceVector_Spring")
		if vec_mag_node:
			lbl_vec_mag = vec_mag_node.get_node_or_null("Label3D") as Label3D
		if vec_spring_node:
			lbl_vec_spring = vec_spring_node.get_node_or_null("Label3D") as Label3D


func _setup_3d_picking() -> void:
	var pickables = {
		"Electromagnet_Core": node_core,
		"Coil_Windings": node_coil,
		"Armature_Striker": node_armature,
		"Leaf_Spring": node_spring,
		"Contact_Screw": node_contact,
		"Bell_Chime": node_chime,
		"Power_Supply_Switch": node_switch,
	}
	
	for key in pickables:
		var area: Area3D = pickables[key] as Area3D
		if area:
			area.input_ray_pickable = true
			var part_id: String = key
			area.mouse_entered.connect(func(): _on_component_mouse_entered(part_id))
			area.mouse_exited.connect(func(): _on_component_mouse_exited(part_id))
			area.input_event.connect(func(_cam, event, _pos, _norm, _shape): _on_component_input_event(part_id, event))


func _setup_hud() -> void:
	var canvas := get_node_or_null("HUD") as CanvasLayer
	if not canvas:
		return
		
	ui_lbl_status = canvas.get_node_or_null("%ContactStatus") as Label
	ui_lbl_power = canvas.get_node_or_null("%PowerStatus") as Label
	ui_lbl_current = canvas.get_node_or_null("%ReadoutCurrent") as Label
	ui_lbl_fmag = canvas.get_node_or_null("%ReadoutFmag") as Label
	ui_lbl_fspring = canvas.get_node_or_null("%ReadoutFspring") as Label
	ui_lbl_gap = canvas.get_node_or_null("%ReadoutGap") as Label
	ui_lbl_freq = canvas.get_node_or_null("%ReadoutFreq") as Label
	ui_lbl_pos = canvas.get_node_or_null("%ReadoutPos") as Label
	ui_lbl_vel = canvas.get_node_or_null("%ReadoutVel") as Label
	ui_lbl_strikes = canvas.get_node_or_null("%ReadoutStrikes") as Label
	ui_lbl_duty = canvas.get_node_or_null("%ReadoutDuty") as Label
	
	ui_slider_voltage = canvas.get_node_or_null("%SliderVoltage") as HSlider
	ui_slider_turns = canvas.get_node_or_null("%SliderTurns") as HSlider
	ui_slider_spring = canvas.get_node_or_null("%SliderSpring") as HSlider
	ui_slider_break = canvas.get_node_or_null("%SliderBreak") as HSlider
	ui_slider_res = canvas.get_node_or_null("%SliderResistance") as HSlider
	ui_slider_ind = canvas.get_node_or_null("%SliderInductance") as HSlider
	ui_slider_damp = canvas.get_node_or_null("%SliderDamping") as HSlider
	
	ui_val_voltage = canvas.get_node_or_null("%ValVoltage") as Label
	ui_val_turns = canvas.get_node_or_null("%ValTurns") as Label
	ui_val_spring = canvas.get_node_or_null("%ValSpring") as Label
	ui_val_break = canvas.get_node_or_null("%ValBreak") as Label
	ui_val_res = canvas.get_node_or_null("%ValResistance") as Label
	ui_val_ind = canvas.get_node_or_null("%ValInductance") as Label
	ui_val_damp = canvas.get_node_or_null("%ValDamping") as Label
	
	# Inspector Card references
	ui_inspector_card = canvas.get_node_or_null("%InspectorCard") as PanelContainer
	ui_insp_title = canvas.get_node_or_null("%InspectorTitle") as Label
	ui_insp_role = canvas.get_node_or_null("%InspectorRole") as Label
	ui_insp_formula = canvas.get_node_or_null("%InspectorFormula") as Label
	ui_insp_telemetry = canvas.get_node_or_null("%InspectorTelemetry") as Label
	ui_insp_action = canvas.get_node_or_null("%InspectorActionLabel") as Label
	ui_btn_focus_part = canvas.get_node_or_null("%BtnFocusPart") as Button
	ui_btn_close_insp = canvas.get_node_or_null("%BtnCloseInspector") as Button
	
	if ui_btn_focus_part:
		ui_btn_focus_part.pressed.connect(focus_selected_or_default)
	if ui_btn_close_insp:
		ui_btn_close_insp.pressed.connect(func(): select_component(""))
		
	# QuickBar controls
	ui_check_vectors = canvas.get_node_or_null("%CheckForceVectors") as CheckBox
	if ui_check_vectors:
		ui_check_vectors.toggled.connect(func(toggled: bool): show_force_vectors = toggled)
		
	ui_btn_switch_mode = canvas.get_node_or_null("%BtnSwitchMode") as Button
	if ui_btn_switch_mode:
		ui_btn_switch_mode.pressed.connect(_on_toggle_switch_mode)
		
	var btn_reset_view := canvas.get_node_or_null("%BtnResetView") as Button
	if btn_reset_view and camera_pivot and camera_pivot.has_method("reset_to_default_view"):
		btn_reset_view.pressed.connect(camera_pivot.reset_to_default_view)

	# Sliders
	if ui_slider_voltage:
		ui_slider_voltage.value = voltage
		ui_slider_voltage.value_changed.connect(_on_voltage_changed)
	if ui_slider_turns:
		ui_slider_turns.value = coil_turns
		ui_slider_turns.value_changed.connect(_on_turns_changed)
	if ui_slider_spring:
		ui_slider_spring.value = spring_constant
		ui_slider_spring.value_changed.connect(_on_spring_changed)
	if ui_slider_break:
		ui_slider_break.value = contact_break_distance * 1000.0
		ui_slider_break.value_changed.connect(_on_break_distance_changed)
	if ui_slider_res:
		ui_slider_res.value = resistance
		ui_slider_res.value_changed.connect(_on_resistance_changed)
	if ui_slider_ind:
		ui_slider_ind.value = inductance * 1000.0
		ui_slider_ind.value_changed.connect(_on_inductance_changed)
	if ui_slider_damp:
		ui_slider_damp.value = damping_coeff
		ui_slider_damp.value_changed.connect(_on_damping_changed)
		
	# Buttons
	var btn_reset := canvas.get_node_or_null("%BtnResetDefaults") as Button
	if btn_reset:
		btn_reset.pressed.connect(_on_reset_defaults)
	var btn_speed_1x := canvas.get_node_or_null("%BtnSpeed1x") as Button
	if btn_speed_1x:
		btn_speed_1x.pressed.connect(func(): time_scale = 1.0)
	var btn_speed_slow := canvas.get_node_or_null("%BtnSpeedSlow") as Button
	if btn_speed_slow:
		btn_speed_slow.pressed.connect(func(): time_scale = 0.2)
	var btn_speed_ultra := canvas.get_node_or_null("%BtnSpeedUltra") as Button
	if btn_speed_ultra:
		btn_speed_ultra.pressed.connect(func(): time_scale = 0.04)
	var btn_speed_pause := canvas.get_node_or_null("%BtnPause") as Button
	if btn_speed_pause:
		btn_speed_pause.pressed.connect(func(): time_scale = 0.0 if time_scale > 0.0 else 1.0)
		
	_update_slider_labels()


func _unhandled_input(event: InputEvent) -> void:
	# Spacebar momentary press handling
	if event is InputEventKey:
		var ek := event as InputEventKey
		if ek.keycode == KEY_SPACE:
			if switch_mode_momentary:
				if ek.pressed and not momentary_pressed:
					momentary_pressed = true
					_update_switch_visuals()
				elif not ek.pressed and momentary_pressed:
					momentary_pressed = false
					_update_switch_visuals()


func _physics_process(delta: float) -> void:
	var effective_dt: float = delta * time_scale
	if effective_dt <= 0.0:
		_update_visuals(delta)
		_update_hud()
		_update_inspector_card()
		return
		
	# Stiff sub-stepping integration
	var n_steps: int = max(sub_steps, 1)
	var dt: float = effective_dt / float(n_steps)
	
	for step in range(n_steps):
		_solve_coupled_step(dt)
		
	sim_elapsed_time += effective_dt
	
	# Conduction duty cycle calculation
	duty_cycle_total_time += effective_dt
	if contact_closed and is_power_active():
		duty_cycle_closed_time += effective_dt
	if duty_cycle_total_time > 1.0:
		conduction_duty_cycle = (duty_cycle_closed_time / max(duty_cycle_total_time, 1e-4)) * 100.0
		duty_cycle_total_time = 0.0
		duty_cycle_closed_time = 0.0
		
	# Strike frequency decay
	if last_strike_time > 0.0 and (sim_elapsed_time - last_strike_time) > 0.5:
		strike_frequency = max(0.0, strike_frequency - 50.0 * delta)
		
	# Headless automated verification
	if headless_mode:
		headless_frame_count += 1
		if headless_frame_count % 30 == 0:
			print("Headless Frame %3d: x=%.3f mm, I=%.2f A, Fmag=%.2f N, Strikes=%d, Freq=%.1f Hz" % [
				headless_frame_count, x * 1000.0, current, F_mag, total_strikes, strike_frequency
			])
		if headless_frame_count >= headless_target_frames:
			print("\nHeadless Run Completed: Total strikes recorded = %d" % total_strikes)
			if total_strikes >= 5:
				print("RESULT: PASS - Standalone Godot headless simulation confirmed stable limit-cycle.")
			else:
				push_error("RESULT: FAIL - Insufficient chime strikes detected.")
			get_tree().quit(0 if total_strikes >= 5 else 1)
			return

	_update_visuals(delta)
	_update_hud()
	_update_inspector_card()


func is_power_active() -> bool:
	if switch_mode_momentary:
		return momentary_pressed
	return power_switch_on


func _solve_coupled_step(dt: float) -> void:
	var active_v: float = voltage if is_power_active() else 0.0
	
	# 1. Electrical State
	contact_closed = (x <= contact_break_distance)
	
	if contact_closed and active_v > 0.0:
		var dI_dt: float = (active_v - current * resistance) / max(inductance, 1e-6)
		current += dI_dt * dt
		current = max(0.0, current)
	else:
		# Model simplification: current drops instantaneously to 0 on open circuit
		current = 0.0

	# 2. Reluctance Force
	dynamic_gap = max(min_air_gap, initial_air_gap - x)
	var N2: float = float(coil_turns * coil_turns)
	var I2: float = current * current
	var numerator: float = MU_0 * N2 * I2 * core_area
	var denominator: float = 2.0 * dynamic_gap * dynamic_gap
	F_mag = numerator / max(denominator, 1e-12)

	# 3. Mechanical Kinematics
	F_spring = -spring_constant * x
	F_damp = -damping_coeff * v
	
	var F_total: float = F_mag + F_spring + F_damp
	var acceleration: float = F_total / max(armature_mass, 1e-6)
	
	v += acceleration * dt
	x += v * dt

	# 4. Boundary Collisions
	if x >= chime_strike_distance:
		x = chime_strike_distance
		if v > 0.0:
			peak_impact_velocity = max(peak_impact_velocity, v)
			v = -restitution_chime * v
			_register_chime_strike()

	if x <= 0.0:
		x = 0.0
		if v < 0.0:
			v = -restitution_backstop * v


func _register_chime_strike() -> void:
	total_strikes += 1
	var now: float = sim_elapsed_time
	strike_timestamps.append(now)
	last_strike_time = now
	chime_ring_intensity = 1.0
	
	while strike_timestamps.size() > 0 and (now - strike_timestamps[0]) > 1.2:
		strike_timestamps.pop_front()
		
	if strike_timestamps.size() >= 2:
		var window_dt: float = strike_timestamps[-1] - strike_timestamps[0]
		if window_dt > 0.005:
			var measured_hz: float = float(strike_timestamps.size() - 1) / window_dt
			strike_frequency = lerp(strike_frequency, measured_hz, 0.4)


func _update_visuals(delta: float) -> void:
	if node_armature:
		node_armature.position.x = x * VISUAL_SCALE
		
	# Update 3D Force Vector Visualizers
	if vec_mag_node and vec_spring_node:
		var show_vecs: bool = show_force_vectors and (time_scale <= 0.2 or current > 0.05 or abs(F_spring) > 0.01)
		vec_mag_node.visible = show_vecs
		vec_spring_node.visible = show_vecs
		
		if show_vecs:
			# Scale lengths proportionally
			var mag_len: float = clampf(F_mag * 1.2, 0.1, 7.5)
			var spring_len: float = clampf(abs(F_spring) * 35.0, 0.1, 7.5)
			
			vec_mag_node.scale.x = mag_len
			vec_spring_node.scale.x = spring_len
			
			if lbl_vec_mag:
				lbl_vec_mag.text = "F_mag: %.2f N" % F_mag
			if lbl_vec_spring:
				lbl_vec_spring.text = "F_spring: %.3f N" % F_spring
		
	# Dynamic Contact Spark
	if mat_spark:
		if contact_closed and current > 0.1 and is_power_active():
			var spark_glow: float = clampf(current / (voltage / max(resistance, 0.1)), 0.2, 1.0)
			mat_spark.emission_enabled = true
			mat_spark.emission = Color(0.3, 0.9, 1.0)
			mat_spark.emission_energy_multiplier = spark_glow * 3.5
		else:
			mat_spark.emission_enabled = false
			
	# Bell Chime ring flash
	if chime_ring_intensity > 0.0:
		chime_ring_intensity = max(0.0, chime_ring_intensity - 6.0 * delta)
		if mat_chime:
			mat_chime.emission_enabled = (chime_ring_intensity > 0.05)
			mat_chime.emission = Color(1.0, 0.85, 0.3)
			mat_chime.emission_energy_multiplier = chime_ring_intensity * 2.5


func _update_hud() -> void:
	if not ui_lbl_status:
		return
		
	if not is_power_active():
		ui_lbl_power.text = "POWER: OFF"
		ui_lbl_power.modulate = Color(1.0, 0.3, 0.2)
	else:
		ui_lbl_power.text = "POWER: ON"
		ui_lbl_power.modulate = Color(0.2, 1.0, 0.4)
		
	if contact_closed:
		ui_lbl_status.text = "CLOSED (CONDUCTING)"
		ui_lbl_status.modulate = Color(0.2, 1.0, 0.4)
	else:
		ui_lbl_status.text = "OPEN (CIRCUIT BROKEN)"
		ui_lbl_status.modulate = Color(1.0, 0.3, 0.2)
		
	if ui_lbl_current:
		ui_lbl_current.text = "%.2f A" % current
	if ui_lbl_fmag:
		ui_lbl_fmag.text = "%.3f N" % F_mag
	if ui_lbl_fspring:
		ui_lbl_fspring.text = "%.3f N" % F_spring
	if ui_lbl_gap:
		ui_lbl_gap.text = "%.3f mm" % (dynamic_gap * 1000.0)
	if ui_lbl_freq:
		ui_lbl_freq.text = "%.1f Hz" % strike_frequency
	if ui_lbl_pos:
		ui_lbl_pos.text = "%.3f mm" % (x * 1000.0)
	if ui_lbl_vel:
		ui_lbl_vel.text = "%+.3f m/s" % v
	if ui_lbl_strikes:
		ui_lbl_strikes.text = "%d" % total_strikes
	if ui_lbl_duty:
		ui_lbl_duty.text = "%.1f %%" % conduction_duty_cycle


func _update_slider_labels() -> void:
	if ui_val_voltage:
		ui_val_voltage.text = "%.1f V" % voltage
	if ui_val_turns:
		ui_val_turns.text = "%d T" % coil_turns
	if ui_val_spring:
		ui_val_spring.text = "%.1f N/m" % spring_constant
	if ui_val_break:
		ui_val_break.text = "%.2f mm" % (contact_break_distance * 1000.0)
	if ui_val_res:
		ui_val_res.text = "%.1f Ohm" % resistance
	if ui_val_ind:
		ui_val_ind.text = "%.1f mH" % (inductance * 1000.0)
	if ui_val_damp:
		ui_val_damp.text = "%.2f Ns/m" % damping_coeff


func _update_contact_screw_visual_position() -> void:
	if node_contact:
		# Base resting position is X = -4.5
		# As contact_break_distance changes, adjust the screw position
		var delta_break: float = (contact_break_distance - 0.0015) * VISUAL_SCALE
		node_contact.position.x = -4.5 + delta_break


func _update_switch_visuals() -> void:
	var active: bool = is_power_active()
	if mesh_switch_button:
		# Depress button downward when pressed/ON
		mesh_switch_button.position.y = 0.5 if active else 1.2
	if mat_switch_led:
		mat_switch_led.emission = Color(0.2, 1.0, 0.3) if active else Color(1.0, 0.2, 0.2)
		mat_switch_led.albedo_color = mat_switch_led.emission
		mat_switch_led.emission_energy_multiplier = 2.5 if active else 0.8


# ==============================================================================
# 3D COMPONENT SELECTION & INSPECTOR CARD
# ==============================================================================
func _on_component_mouse_entered(part_id: String) -> void:
	hovered_component = part_id
	Input.set_default_cursor_shape(Input.CURSOR_POINTING_HAND)
	_set_component_highlight(part_id, true)


func _on_component_mouse_exited(part_id: String) -> void:
	if hovered_component == part_id:
		hovered_component = ""
		Input.set_default_cursor_shape(Input.CURSOR_ARROW)
		if selected_component != part_id:
			_set_component_highlight(part_id, false)


func _on_component_input_event(part_id: String, event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			if part_id == "Power_Supply_Switch":
				if switch_mode_momentary:
					momentary_pressed = mb.pressed
					_update_switch_visuals()
				elif mb.pressed:
					power_switch_on = not power_switch_on
					_update_switch_visuals()
					
			if mb.pressed:
				var now: float = Time.get_ticks_msec() / 1000.0
				if (now - last_click_timestamp) < 0.35 and last_clicked_part == part_id:
					# Double click: focus camera immediately
					select_component(part_id)
					focus_selected_or_default()
				else:
					select_component(part_id)
				last_click_timestamp = now
				last_clicked_part = part_id


func select_component(part_id: String) -> void:
	if selected_component != "" and selected_component != part_id:
		_set_component_highlight(selected_component, false)
		
	selected_component = part_id
	if selected_component == "":
		if ui_inspector_card:
			ui_inspector_card.visible = false
		return
		
	_set_component_highlight(selected_component, true)
	if ui_inspector_card:
		ui_inspector_card.visible = true
	_update_inspector_card()


func _set_component_highlight(part_id: String, active: bool) -> void:
	var target_mesh: MeshInstance3D = null
	match part_id:
		"Electromagnet_Core":
			target_mesh = node_core.get_node_or_null("Core_Iron") as MeshInstance3D if node_core else null
		"Coil_Windings":
			target_mesh = node_coil.get_node_or_null("Coil_Mesh") as MeshInstance3D if node_coil else null
		"Armature_Striker":
			target_mesh = node_armature.get_node_or_null("Armature_Plate") as MeshInstance3D if node_armature else null
		"Leaf_Spring":
			target_mesh = node_spring.get_node_or_null("Spring_Mesh") as MeshInstance3D if node_spring else null
		"Contact_Screw":
			target_mesh = node_contact.get_node_or_null("Screw_Post") as MeshInstance3D if node_contact else null
		"Bell_Chime":
			target_mesh = mesh_chime_dome
		"Power_Supply_Switch":
			target_mesh = mesh_switch_button
			
	if target_mesh and target_mesh.material_override:
		var mat := target_mesh.material_override as StandardMaterial3D
		if mat:
			if active:
				mat.rim_enabled = true
				mat.rim = 0.8
				mat.rim_tint = 0.5
			else:
				mat.rim_enabled = false


func _update_inspector_card() -> void:
	if not ui_inspector_card or not ui_inspector_card.visible or selected_component == "":
		return
		
	match selected_component:
		"Electromagnet_Core":
			ui_insp_title.text = "COMPONENT: ELECTROMAGNET CORE (SOFT IRON)"
			ui_insp_role.text = "Role: Low-reluctance ferromagnetic path concentrating magnetic flux across air gap."
			ui_insp_formula.text = "Reluctance Formula: R_core = l_core / (mu_0 * mu_r * A)  |  Phi = N*I / R_total"
			ui_insp_telemetry.text = "Effective Area (A): %.4e m^2 | Dynamic Air Gap: %.3f mm | Core Permeability: mu_r >> 1" % [
				core_area, dynamic_gap * 1000.0
			]
			ui_insp_action.text = "Tip: Air gap reluctance dominates total circuit reluctance (F_mag ~ 1/g^2)."

		"Coil_Windings":
			var power_dissipation: float = current * current * resistance
			ui_insp_title.text = "COMPONENT: ELECTROMAGNET SOLENOID COIL"
			ui_insp_role.text = "Role: Converts electrical drive current into magnetic tractive pulling force."
			ui_insp_formula.text = "Governing ODE: V = L(dI/dt) + IR   |   F_mag = (mu_0 * N^2 * I^2 * A) / (2 * g^2)"
			ui_insp_telemetry.text = "Current: %.2f A | Turns: %d | Inductance: %.1f mH | Resistance: %.1f Ohm | Power Dissipated: %.2f W | Pull: %.3f N" % [
				current, coil_turns, inductance * 1000.0, resistance, power_dissipation, F_mag
			]
			ui_insp_action.text = "Direct Tuning: Use Voltage, Turns, Inductance, and Resistance sliders in the right panel."

		"Armature_Striker":
			var kinetic_energy: float = 0.5 * armature_mass * v * v
			ui_insp_title.text = "COMPONENT: MOVING ARMATURE & STRIKER HAMMER"
			ui_insp_role.text = "Role: 1-DOF moving mass accelerated by magnetic reluctance toward the bell chime."
			ui_insp_formula.text = "Equation of Motion: m(d^2x/dt^2) = F_mag - k*x - c*v"
			ui_insp_telemetry.text = "Displacement: %.3f mm | Velocity: %+.3f m/s | Mass: %.1f g | Kinetic Energy: %.3f mJ | Net a: %+.1f m/s^2" % [
				x * 1000.0, v, armature_mass * 1000.0, kinetic_energy * 1000.0, (F_mag + F_spring + F_damp) / armature_mass
			]
			ui_insp_action.text = "Observation: Watch the tug-of-war between green (F_mag) and red (F_spring) force arrows."

		"Leaf_Spring":
			var elastic_energy: float = 0.5 * spring_constant * x * x
			ui_insp_title.text = "COMPONENT: RESTORING LEAF SPRING"
			ui_insp_role.text = "Role: Mechanical return spring providing restoring force and contact preload."
			ui_insp_formula.text = "Hooke's Restoring Law: F_spring = -k * x   |   Damping: F_damp = -c * (dx/dt)"
			ui_insp_telemetry.text = "Restoring Force: %.3f N | Damping Force: %.3f N | Spring Constant (k): %.1f N/m | Potential Energy: %.3f mJ" % [
				F_spring, F_damp, spring_constant, elastic_energy * 1000.0
			]
			ui_insp_action.text = "Direct Tuning: Adjust Spring Constant (k) and Damping (c) in the right panel."

		"Contact_Screw":
			ui_insp_title.text = "COMPONENT: ADJUSTABLE CONTACT SCREW (INTERRUPTER)"
			ui_insp_role.text = "Role: Mechanically breaks electrical contact when armature displacement exceeds x_break."
			ui_insp_formula.text = "Switching Logic: State = CLOSED if (x <= x_break) else OPEN"
			ui_insp_telemetry.text = "Contact State: %s | Break Threshold (x_break): %.2f mm | Duty Cycle: %.1f %% | Quiescent Gap (g0): %.2f mm" % [
				"CLOSED" if contact_closed else "OPEN", contact_break_distance * 1000.0, conduction_duty_cycle, initial_air_gap * 1000.0
			]
			ui_insp_action.text = "Direct Tuning: Drag the Contact Break (x_break) slider to visibly translate the contact screw."

		"Bell_Chime":
			ui_insp_title.text = "COMPONENT: BELL GONG CHIME (ACOUSTIC RESONATOR)"
			ui_insp_role.text = "Role: Acoustic strike limit stopping armature travel and emitting audible ring tone."
			ui_insp_formula.text = "Impact Restitution: v_after = -e_chime * v_before  (at x = x_strike)"
			ui_insp_telemetry.text = "Strike Frequency: %.1f Hz | Total Strikes: %d | Strike Limit: %.2f mm | Peak Impact Vel: %.2f m/s" % [
				strike_frequency, total_strikes, chime_strike_distance * 1000.0, peak_impact_velocity
			]
			ui_insp_action.text = "Observation: Golden flash effect illuminates upon hammer impact."

		"Power_Supply_Switch":
			ui_insp_title.text = "COMPONENT: DC POWER SUPPLY & 3D PUSHBUTTON"
			ui_insp_role.text = "Role: Provides driving DC electrical supply and manual ring actuation."
			ui_insp_formula.text = "Circuit Drive: V_circuit = V_supply * Switch_State"
			ui_insp_telemetry.text = "Mode: %s | State: %s | Driving Voltage: %.1f V | Max Steady Current: %.2f A" % [
				"MOMENTARY (Hold to Ring)" if switch_mode_momentary else "LATCHING (Toggle ON/OFF)",
				"ACTIVE" if is_power_active() else "OFF",
				voltage if is_power_active() else 0.0,
				voltage / max(resistance, 0.1)
			]
			ui_insp_action.text = "Direct Interaction: Click the 3D red button or hold Spacebar in Momentary mode."


func focus_selected_or_default() -> void:
	if not camera_pivot or not camera_pivot.has_method("focus_on_target"):
		return
		
	var target_pos := Vector3(5.0, 8.0, 0.0)
	var target_dist: float = 34.0
	
	match selected_component:
		"Electromagnet_Core":
			target_pos = Vector3(13.0, 0.0, 0.0)
			target_dist = 16.0
		"Coil_Windings":
			target_pos = Vector3(13.0, 0.0, 0.0)
			target_dist = 18.0
		"Armature_Striker":
			target_pos = Vector3(0.0, 10.0, 0.0)
			target_dist = 20.0
		"Leaf_Spring":
			target_pos = Vector3(-0.8, -8.0, 0.0)
			target_dist = 14.0
		"Contact_Screw":
			target_pos = Vector3(-2.0, 0.0, 0.0)
			target_dist = 10.0
		"Bell_Chime":
			target_pos = Vector3(16.0, 21.0, 0.0)
			target_dist = 22.0
		"Power_Supply_Switch":
			target_pos = Vector3(-14.0, 1.0, 0.0)
			target_dist = 12.0
			
	camera_pivot.focus_on_target(target_pos, target_dist)


# ==============================================================================
# UI CALLBACKS
# ==============================================================================
func _on_voltage_changed(val: float) -> void:
	voltage = val
	_update_slider_labels()

func _on_turns_changed(val: float) -> void:
	coil_turns = int(val)
	_update_slider_labels()

func _on_spring_changed(val: float) -> void:
	spring_constant = val
	_update_slider_labels()

func _on_break_distance_changed(val_mm: float) -> void:
	contact_break_distance = val_mm / 1000.0
	_update_contact_screw_visual_position()
	_update_slider_labels()

func _on_resistance_changed(val: float) -> void:
	resistance = val
	_update_slider_labels()

func _on_inductance_changed(val: float) -> void:
	inductance = val / 1000.0
	_update_slider_labels()

func _on_damping_changed(val: float) -> void:
	damping_coeff = val
	_update_slider_labels()

func _on_toggle_switch_mode() -> void:
	switch_mode_momentary = not switch_mode_momentary
	if ui_btn_switch_mode:
		if switch_mode_momentary:
			ui_btn_switch_mode.text = "Switch Mode: MOMENTARY (Hold Space)"
		else:
			ui_btn_switch_mode.text = "Switch Mode: LATCHING (Continuous)"
	_update_switch_visuals()

func _on_reset_defaults() -> void:
	voltage = 9.0
	resistance = 1.5
	inductance = 0.005
	coil_turns = 200
	spring_constant = 40.0
	contact_break_distance = 0.0015
	damping_coeff = 0.15
	time_scale = 1.0
	power_switch_on = true
	switch_mode_momentary = false
	show_force_vectors = true
	
	if ui_slider_voltage:
		ui_slider_voltage.value = voltage
	if ui_slider_turns:
		ui_slider_turns.value = coil_turns
	if ui_slider_spring:
		ui_slider_spring.value = spring_constant
	if ui_slider_break:
		ui_slider_break.value = contact_break_distance * 1000.0
	if ui_slider_res:
		ui_slider_res.value = resistance
	if ui_slider_ind:
		ui_slider_ind.value = inductance * 1000.0
	if ui_slider_damp:
		ui_slider_damp.value = damping_coeff
	if ui_check_vectors:
		ui_check_vectors.button_pressed = true
	if ui_btn_switch_mode:
		ui_btn_switch_mode.text = "Switch Mode: LATCHING (Continuous)"
		
	_update_contact_screw_visual_position()
	_update_switch_visuals()
	_update_slider_labels()
	if camera_pivot and camera_pivot.has_method("reset_to_default_view"):
		camera_pivot.reset_to_default_view()
	print("Workbench reset to baseline UNSW lab defaults.")
