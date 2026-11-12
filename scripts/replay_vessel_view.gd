class_name ReplayVesselView
extends SubViewportContainer
## High-Fidelity Godot 4 Forward+ 3D Simulation Engine.
## Strict Conservation of Mass & Sequential Batch Transfer Across All 6 Stages.
## Only the active stage contains the 15.0g Saccharina latissima biomass batch.
## Future vessels are 100% empty; past vessels are drained (with Stage 3 retaining insoluble residue).
## Inter-stage glass pipes feature animated 3D TransferSlugMesh moving slugs between stages.

const SHAFT_HEIGHT_RATIO := 0.92
const VESSEL_RADIUS := 0.52
const VESSEL_HEIGHT := 2.4
const FILL_BASE_Y := 0.11
const STAGE_SPACING := 1.95

const CHEM_PLOT_POSITIONS: Array = [
	Vector3(-9.5, 0.0, 2.8),   # Unit 100: R-101A/B HDS & R-102 Pre-Reformer (Front Row)
	Vector3(-3.5, 0.0, 2.8),   # Unit 200: F-201 / R-201 Primary SMR Furnace (Front Row)
	Vector3(2.5, 0.0, 2.8),    # Unit 300: E-105 WHB & V-102 Steam Drum (Front Row)
	Vector3(8.5, 0.0, 2.8),    # Unit 400: R-301A/B Dual-Stage WGS (Front Row)
	Vector3(11.2, 0.6, -2.8),  # Unit 500: E-401 Trim Cooler & V-401 Condensate KO (Mezzanine)
	Vector3(5.5, 0.6, -2.8),   # Unit 600: C-501 / C-502 Amine CO2 Capture (Mezzanine)
	Vector3(-0.5, 0.6, -2.8),  # Unit 700: U-601 8-Bed PSA & V-601 Tail Gas Drum (Mezzanine)
	Vector3(-6.5, 0.6, -2.8),  # Unit 800: K-701 H2 Compressor & V-701A/B/C 400 bar Bullets (Mezzanine)
]

var _viewport: SubViewport
var _world: Node3D
var _bench_env_root: Node3D
var _bench_root: Node3D
var _camera: Camera3D
var _pitch_axis: Node3D

var _yaw := deg_to_rad(-22.0)
var _pitch := deg_to_rad(-10.0)
var _distance := 5.2
var _dragging := false
var _panning := false
var _target := Vector3(-2.0, 1.15, 0.0)
var _camera_tween: Tween

var _turbidity := 0.0
var _impeller_speed: float = 0.0
var _unverified_pulse_time: float = 0.0
var _chevron_anim_time: float = 0.0
var _current_sim_time: float = 0.0

# Legacy single-vessel pointers for backwards compatibility
var _liquid: MeshInstance3D
var _liquid_mat: StandardMaterial3D
var _impeller: Node3D
var _feed_tube: MeshInstance3D
var _sparger: MeshInstance3D
var _harvest_valve: MeshInstance3D

# Multi-vessel stage representations & inter-stage transfer slugs
var _stage_vessels: Array = []
var _active_stage_index: int = 0
var _flow_chevrons: Array = []
var _transfer_slugs: Array = []
var _pipe_pulses: Array = []
var _smr_refs: Dictionary = {}
var _smr_process_state: Dictionary = {
	"sc_ratio": 3.0,
	"reformer_temp_c": 850.0,
	"pressure_bar": 28.0,
	"e105_cooling_loss": false,
	"coking_warning": false,
	"n2_purge_active": false,
}

# Fibre tension & fracture state
var _fibre_mesh: MeshInstance3D
var _fibre_spool: Node3D
var _spool_yarn_mesh: MeshInstance3D
var _fibre_particles: GPUParticles3D
var _is_fibre_snapped: bool = false
var _current_fibre_load_mpa: float = 12.0
var _fibre_uts_threshold_mpa: float = 29.3

signal orbit_changed(azimuth_deg: float, elevation_deg: float, distance: float)
signal stage_clicked(stage_id: String, stage_index: int)
signal fibre_snapped(load_mpa: float)
signal bench_build_started()
signal bench_build_progress(current_stage: int, total_stages: int, stage_title: String)
signal bench_build_completed()

var is_building: bool = false
var build_progress: float = 0.0


func _process(delta: float) -> void:
	delta = minf(delta, 0.05)
	_unverified_pulse_time += delta
	_chevron_anim_time += delta * 2.2

	# Animate directional flow chevrons along interstage pipes
	for ch_mat in _flow_chevrons:
		if ch_mat is StandardMaterial3D:
			ch_mat.uv1_offset.x = -_chevron_anim_time * 0.45

	# Update physics and rotations only for active/spinning stages
	for sv in _stage_vessels:
		# Rotating mill grinder blades in Stage 0 during active milling
		if sv.has("mill_blades") and sv.mill_blades != null:
			if _current_sim_time <= 2.0:
				sv.mill_blades.rotate_y(delta * 14.0)

		# Rotating impellers only when vessel contains liquid and is active
		if sv.impeller != null and sv.has("is_active") and sv.is_active:
			var spd: float = float(sv.drivers.get("rpm", 200.0)) / 60.0
			sv.impeller.rotate_y(spd * delta * 4.0)

		# Vortex meniscus swirl only when active
		if sv.has("meniscus") and sv.meniscus != null and sv.meniscus.visible:
			var swirl_speed: float = float(sv.drivers.get("vortex_speed", 2.0))
			sv.meniscus.rotate_y(swirl_speed * delta)

		# Centrifuge rotor spin during active centrifugation (32.0 - 33.5h)
		if sv.has("rotor") and sv.rotor != null:
			if _current_sim_time >= 31.8 and _current_sim_time <= 33.6:
				var rpm: float = float(sv.drivers.get("rpm", 4500.0))
				sv.rotor.rotate_y((rpm / 60.0) * delta * 6.28)

		# Rotating take-up yarn spool in wet spinning bath (36.0 - 40.0h)
		if sv.has("spool") and sv.spool != null:
			if _current_sim_time >= 36.0 and _current_sim_time <= 40.0:
				sv.spool.rotate_z(delta * 2.5)

		# 3D Suspended Solid Kelp Flakes Swirl Dynamics only when visible
		if sv.has("flakes_group") and sv.flakes_group != null and sv.flakes_group.visible:
			var f_speed: float = float(sv.drivers.get("vortex_speed", 1.8))
			sv.flakes_group.rotate_y(f_speed * delta * 0.8)

		# Unverified pulsing alert wireframe
		if sv.is_unverified and sv.wireframe != null:
			var pulse := 0.5 + 0.5 * sin(_unverified_pulse_time * 5.0)
			var wmat: StandardMaterial3D = sv.wireframe.material_override as StandardMaterial3D
			if wmat != null:
				wmat.albedo_color = Color(1.0, 0.2, 0.2, 0.35 + 0.55 * pulse)

	if _impeller != null and _impeller_speed > 0.0:
		_impeller.rotate_y(_impeller_speed * delta * 6.0)

	# Animate ASME interstage flow pulses along elbow-routed waypoints
	var purge_active: bool = bool(_smr_process_state.get("n2_purge_active", false))
	var flow_rate_mult: float = 0.25 if purge_active else 1.0
	for p_item in _pipe_pulses:
		if not is_instance_valid(p_item.get("mesh", null)):
			continue
		var pts: Array = p_item.get("waypoints", [])
		if pts.size() < 2:
			continue
		var phase: float = fmod(float(p_item.get("phase", 0.0)) + delta * 0.42 * flow_rate_mult, 1.0)
		p_item["phase"] = phase
		var seg_count := pts.size() - 1
		var scaled := phase * float(seg_count)
		var seg_idx := mini(int(scaled), seg_count - 1)
		var local_t := scaled - float(seg_idx)
		var a: Vector3 = pts[seg_idx]
		var b: Vector3 = pts[seg_idx + 1]
		var mesh_node: MeshInstance3D = p_item["mesh"]
		mesh_node.position = a.lerp(b, local_t)
		if purge_active:
			var pm := mesh_node.material_override as StandardMaterial3D
			if pm != null:
				pm.albedo_color = Color(0.28, 0.72, 1.0)
				pm.emission = Color(0.22, 0.65, 1.0)

	# Animate PSA 4-bed cyclic adsorption states
	var psa_mats: Array = _smr_refs.get("psa_bed_mats", [])
	if not psa_mats.is_empty():
		var cycle_idx := int(floor(_unverified_pulse_time * 0.5)) % 4
		var state_colors := [
			Color(0.15, 0.88, 0.55), # Adsorption
			Color(0.95, 0.68, 0.18), # Depressurization
			Color(0.22, 0.78, 1.0),  # Purge
			Color(0.45, 0.62, 0.85), # Repressurization
		]
		for bi in range(psa_mats.size()):
			var bmat: StandardMaterial3D = psa_mats[bi] as StandardMaterial3D
			if bmat != null:
				var col: Color = state_colors[(bi + cycle_idx) % 4]
				bmat.albedo_color = col
				bmat.emission = col
				bmat.emission_energy_multiplier = 1.4 if ((bi + cycle_idx) % 4) == 0 else 0.7

	# Animate compressor fin-fan coolers
	var fans: Array = _smr_refs.get("comp_fan_nodes", [])
	for fn in fans:
		if is_instance_valid(fn):
			fn.rotate_y(delta * 9.5)

	# Animate HAZOP N2 purge flush & E_105 cooling loss alarm
	var n2_mat: StandardMaterial3D = _smr_refs.get("n2_purge_mat", null) as StandardMaterial3D
	if n2_mat != null:
		if purge_active:
			var npulse := 0.5 + 0.5 * sin(_unverified_pulse_time * 7.0)
			n2_mat.emission_enabled = true
			n2_mat.emission = Color(0.20, 0.72, 1.0)
			n2_mat.emission_energy_multiplier = 1.2 + 2.2 * npulse
		else:
			n2_mat.emission_enabled = false

	var e105_beacon: StandardMaterial3D = _smr_refs.get("e105_fault_beacon", null) as StandardMaterial3D
	if e105_beacon != null:
		if bool(_smr_process_state.get("e105_cooling_loss", false)):
			var epulse := 0.5 + 0.5 * sin(_unverified_pulse_time * 8.0)
			e105_beacon.emission_enabled = true
			e105_beacon.emission = Color(1.0, 0.18, 0.12)
			e105_beacon.emission_energy_multiplier = 1.5 + 2.5 * epulse
		else:
			e105_beacon.emission_enabled = false


func _ready() -> void:
	stretch = true
	_viewport = SubViewport.new()
	_viewport.own_world_3d = true
	_viewport.msaa_3d = Viewport.MSAA_4X
	_viewport.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
	_viewport.use_hdr_2d = true
	_viewport.scaling_3d_mode = SubViewport.SCALING_3D_MODE_FSR
	_viewport.scaling_3d_scale = 1.0
	add_child(_viewport)

	_build_world()
	_apply_camera()


# ---------------------------------------------------------------- Interactive Viewport Controls

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed:
				_dragging = true
				_handle_click_select(mb.position)
			else:
				_dragging = false
		elif mb.button_index == MOUSE_BUTTON_RIGHT:
			_panning = mb.pressed
		elif mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			_zoom(-1.0)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			_zoom(1.0)
	elif event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		if _dragging:
			_yaw -= mm.relative.x * 0.0055
			_pitch = clampf(_pitch - mm.relative.y * 0.0045, deg_to_rad(-85.0), deg_to_rad(45.0))
			_apply_camera()
		elif _panning:
			var basis := Basis.from_euler(Vector3(_pitch, _yaw, 0.0))
			var right := basis.x
			var up := basis.y
			_target -= (right * mm.relative.x - up * mm.relative.y) * 0.0065 * (_distance / 5.0)
			_apply_camera()


func _handle_click_select(screen_pos: Vector2) -> void:
	if _camera == null or _stage_vessels.is_empty():
		return
	var min_dist := 999999.0
	var best_idx := -1
	for i in range(_stage_vessels.size()):
		var sv: Dictionary = _stage_vessels[i]
		var world_pos: Vector3 = sv.root.position + Vector3(0.0, 1.2, 0.0)
		var sp := _camera.unproject_position(world_pos)
		var d := sp.distance_to(screen_pos)
		if d < 120.0 and d < min_dist:
			min_dist = d
			best_idx = i
	if best_idx >= 0:
		smooth_focus_on_stage(best_idx)
		var sel_id: String = _stage_vessels[best_idx].stage_id
		stage_clicked.emit(sel_id, best_idx)


func focus_on_stage(index: int) -> void:
	smooth_focus_on_stage(index, 0.4)


func smooth_focus_on_stage(index: int, duration: float = 0.85) -> void:
	if index < 0 or index >= _stage_vessels.size():
		return
	_active_stage_index = index
	var target_pos: Vector3 = _stage_vessels[index].root.position + Vector3(0.0, 1.15, 0.0)

	if _camera_tween != null and _camera_tween.is_valid():
		_camera_tween.kill()
	_camera_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_camera_tween.tween_property(self, "_target", target_pos, duration)
	_camera_tween.tween_property(self, "_distance", 4.5, duration)
	_camera_tween.tween_property(self, "_yaw", deg_to_rad(-20.0), duration)
	_camera_tween.tween_property(self, "_pitch", deg_to_rad(-12.0), duration)
	_camera_tween.chain().tween_callback(_apply_camera)


func _zoom(direction: float) -> void:
	_distance = clampf(_distance + direction * 0.55, 2.0, 24.0)
	_apply_camera()


func reset_camera() -> void:
	if _camera_tween != null and _camera_tween.is_valid():
		_camera_tween.kill()
	_camera_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	var is_chem := (not _stage_vessels.is_empty()) and bool(_stage_vessels[0].get("is_chemical_plant", false))
	if is_chem:
		_camera_tween.tween_property(self, "_target", Vector3(0.8, 1.8, 0.0), 0.75)
		_camera_tween.tween_property(self, "_distance", 22.5, 0.75)
		_camera_tween.tween_property(self, "_yaw", deg_to_rad(4.0), 0.75)
		_camera_tween.tween_property(self, "_pitch", deg_to_rad(-24.0), 0.75)
	else:
		_camera_tween.tween_property(self, "_target", Vector3(0.0, 1.15, 0.0), 0.75)
		_camera_tween.tween_property(self, "_distance", maxf(6.5, float(_stage_vessels.size()) * 1.5), 0.75)
		_camera_tween.tween_property(self, "_yaw", deg_to_rad(-22.0), 0.75)
		_camera_tween.tween_property(self, "_pitch", deg_to_rad(-10.0), 0.75)
	_camera_tween.chain().tween_callback(_apply_camera)


func _apply_camera() -> void:
	if _camera == null:
		return
	var basis := Basis.from_euler(Vector3(_pitch, _yaw, 0.0))
	_camera.transform = Transform3D(basis, _target + basis.z * _distance)
	orbit_changed.emit(rad_to_deg(_yaw), rad_to_deg(_pitch), _distance)


# ---------------------------------------------------------------- Forward+ Environment

func _build_world() -> void:
	_world = Node3D.new()
	_viewport.add_child(_world)

	var env := WorldEnvironment.new()
	var e := Environment.new()
	var sky := Sky.new()
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.05, 0.08, 0.14)
	sky_mat.sky_horizon_color = Color(0.15, 0.22, 0.34)
	sky_mat.ground_horizon_color = Color(0.10, 0.14, 0.20)
	sky_mat.ground_bottom_color = Color(0.04, 0.05, 0.08)
	sky_mat.sky_curve = 0.16
	sky.sky_material = sky_mat
	e.background_mode = Environment.BG_SKY
	e.sky = sky
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	e.tonemap_exposure = 1.15

	# Glow & Bloom
	e.glow_enabled = true
	e.glow_intensity = 0.70
	e.glow_bloom = 0.16
	e.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT

	# Screen-space ambient occlusion & reflections
	e.ssao_enabled = true
	e.ssao_radius = 1.2
	e.ssao_intensity = 1.25
	e.ssr_enabled = true

	# Ambient & Sky Reflection Lighting for metallic vessels and pipe rack
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.ambient_light_sky_contribution = 0.75
	e.ambient_light_energy = 1.18
	e.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.environment = e
	_world.add_child(env)

	# Studio Key Light with soft shadows
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-48.0, -135.0, 0.0)
	key.light_energy = 1.55
	key.light_color = Color(1.0, 0.98, 0.95)
	key.shadow_enabled = true
	key.shadow_bias = 0.03
	_world.add_child(key)

	# Cool Studio Rim Fill Light
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-18.0, 55.0, 0.0)
	rim.light_energy = 0.85
	rim.light_color = Color(0.58, 0.78, 1.0)
	rim.shadow_enabled = false
	_world.add_child(rim)

	# Warm Ground Bounce Fill Light (prevents dark undersides on skids/piping)
	var bounce := DirectionalLight3D.new()
	bounce.rotation_degrees = Vector3(32.0, 15.0, 0.0)
	bounce.light_energy = 0.42
	bounce.light_color = Color(0.75, 0.82, 0.92)
	bounce.shadow_enabled = false
	_world.add_child(bounce)

	_bench_env_root = Node3D.new()
	_bench_env_root.name = "BenchEnvRoot"
	_world.add_child(_bench_env_root)
	_build_laboratory_bench()

	_bench_root = Node3D.new()
	_bench_root.name = "BenchRoot"
	_world.add_child(_bench_root)

	_pitch_axis = Node3D.new()
	_world.add_child(_pitch_axis)
	_camera = Camera3D.new()
	_camera.fov = 42.0
	_pitch_axis.add_child(_camera)

	# Legacy vessel fallback
	_build_legacy_vessel()


func _clear_bench_env() -> void:
	if _bench_env_root == null:
		return
	for c in _bench_env_root.get_children():
		c.queue_free()


func _build_laboratory_bench() -> void:
	_clear_bench_env()
	var bench_mesh := BoxMesh.new()
	bench_mesh.size = Vector3(18.5, 0.16, 4.6)
	var bench := MeshInstance3D.new()
	bench.mesh = bench_mesh
	bench.position = Vector3(0.0, -0.08, 0.0)
	var b_mat := StandardMaterial3D.new()
	b_mat.albedo_color = Color(0.11, 0.135, 0.175)
	b_mat.metallic = 0.65
	b_mat.roughness = 0.42
	bench.material_override = b_mat
	_bench_env_root.add_child(bench)

	var grid_plane := PlaneMesh.new()
	grid_plane.size = Vector2(44.0, 44.0)
	var gm := MeshInstance3D.new()
	gm.mesh = grid_plane
	gm.position = Vector3(0.0, -0.17, 0.0)
	var g_mat := StandardMaterial3D.new()
	g_mat.albedo_color = Color(0.065, 0.082, 0.11)
	g_mat.roughness = 0.88
	gm.material_override = g_mat
	_bench_env_root.add_child(gm)

	var mani_mesh := CylinderMesh.new()
	mani_mesh.top_radius = 0.055
	mani_mesh.bottom_radius = 0.055
	mani_mesh.height = 17.5
	var manifold := MeshInstance3D.new()
	manifold.mesh = mani_mesh
	manifold.rotation_degrees = Vector3(0.0, 0.0, 90.0)
	manifold.position = Vector3(0.0, 3.65, -0.85)
	var m_mat := StandardMaterial3D.new()
	m_mat.albedo_color = Color(0.32, 0.38, 0.48)
	m_mat.metallic = 0.85
	m_mat.roughness = 0.25
	manifold.material_override = m_mat
	_bench_env_root.add_child(manifold)


func _build_industrial_plant_pad() -> void:
	_clear_bench_env()

	# 1. Surrounding Asphalt / Industrial Apron (60m x 60m)
	var apron_m := PlaneMesh.new()
	apron_m.size = Vector2(60.0, 60.0)
	var apron := MeshInstance3D.new()
	apron.mesh = apron_m
	apron.position = Vector3(0.0, -0.18, 0.0)
	var apron_mat := StandardMaterial3D.new()
	apron_mat.albedo_color = Color(0.06, 0.075, 0.095)
	apron_mat.roughness = 0.92
	apron.material_override = apron_mat
	_bench_env_root.add_child(apron)

	# 2. Industrial Concrete Plant Pad (28m x 13m) + Raised +0.6m Mezzanine Deck under Back Row
	var pad_mat := StandardMaterial3D.new()
	pad_mat.albedo_color = Color(0.19, 0.21, 0.24)
	pad_mat.roughness = 0.80
	pad_mat.metallic = 0.08
	_add_cad_box(_bench_env_root, Vector3(28.0, 0.18, 13.0), Vector3(0.8, -0.09, 0.0), pad_mat)

	var mezz_mat := StandardMaterial3D.new()
	mezz_mat.albedo_color = Color(0.22, 0.24, 0.28)
	mezz_mat.roughness = 0.78
	_add_cad_box(_bench_env_root, Vector3(24.0, 0.60, 3.8), Vector3(2.3, 0.30, -2.95), mezz_mat)

	# 3. Painted Yellow Safety Walkways & Perimeter Striping
	var yellow_mat := StandardMaterial3D.new()
	yellow_mat.albedo_color = Color(0.78, 0.62, 0.14)
	yellow_mat.roughness = 0.52
	for wz in [-6.35, 6.35, 0.85, -0.95]:
		_add_cad_box(_bench_env_root, Vector3(27.6, 0.015, 0.08), Vector3(0.8, 0.008, wz), yellow_mat)
	_add_cad_box(_bench_env_root, Vector3(23.8, 0.015, 0.08), Vector3(2.3, 0.608, -1.08), yellow_mat)
	for wx in [-13.05, 14.65]:
		_add_cad_box(_bench_env_root, Vector3(0.08, 0.015, 12.7), Vector3(wx, 0.008, 0.0), yellow_mat)

	# 4. Central Multi-Tier Structural Steel Overhead Pipe Rack (Spine at z = 0.0 between Front & Back Rows)
	var steel_beam_mat := StandardMaterial3D.new()
	steel_beam_mat.albedo_color = Color(0.32, 0.38, 0.46)
	steel_beam_mat.metallic = 0.84
	steel_beam_mat.roughness = 0.30

	var rack_z := 0.0
	var rack_half_w := 0.55
	var bent_xs := [-10.0, -7.0, -4.0, -1.0, 2.0, 5.0, 8.0, 11.0]
	for bx in bent_xs:
		_add_cad_box(_bench_env_root, Vector3(0.11, 3.85, 0.11), Vector3(bx, 1.925, rack_z - rack_half_w), steel_beam_mat)
		_add_cad_box(_bench_env_root, Vector3(0.11, 3.85, 0.11), Vector3(bx, 1.925, rack_z + rack_half_w), steel_beam_mat)
		_add_cad_box(_bench_env_root, Vector3(0.12, 0.10, 1.25), Vector3(bx, 2.85, rack_z), steel_beam_mat)
		_add_cad_box(_bench_env_root, Vector3(0.12, 0.10, 1.25), Vector3(bx, 3.55, rack_z), steel_beam_mat)

	for rz in [rack_z - rack_half_w, rack_z + rack_half_w]:
		_add_cad_box(_bench_env_root, Vector3(21.4, 0.10, 0.10), Vector3(0.5, 2.85, rz), steel_beam_mat)
		_add_cad_box(_bench_env_root, Vector3(21.4, 0.10, 0.10), Vector3(0.5, 3.55, rz), steel_beam_mat)


# ---------------------------------------------------------------- Multi-Vessel Topology

func build_anatomy_bench(unit_operations: Array) -> void:
	await build_anatomy_bench_async(unit_operations)


func build_anatomy_bench_async(unit_operations: Array) -> void:
	if _bench_root == null:
		return
	for child in _bench_root.get_children():
		child.queue_free()
	_stage_vessels.clear()
	_flow_chevrons.clear()
	_transfer_slugs.clear()
	_pipe_pulses.clear()
	_smr_refs.clear()

	if unit_operations.is_empty():
		_build_legacy_vessel()
		bench_build_completed.emit()
		return

	is_building = true
	build_progress = 0.0
	bench_build_started.emit()

	var count := unit_operations.size()
	var first_arch := str(unit_operations[0].get("archetype", ""))
	var is_chem_plant := first_arch in ["pre_reformer", "furnace_reformer", "shell_tube_hx", "packed_bed_reactor", "knockout_cooler", "co2_absorber", "psa_skid", "high_pressure_compressor"]
	var total_span := float(count - 1) * STAGE_SPACING

	if is_chem_plant:
		_build_industrial_plant_pad()
	else:
		_build_laboratory_bench()

	# Frame 1: Stream Stage 0 & immediately focus camera
	var op0: Dictionary = unit_operations[0]
	var pos0: Vector3 = CHEM_PLOT_POSITIONS[0] if (is_chem_plant and CHEM_PLOT_POSITIONS.size() > 0) else Vector3(-total_span * 0.5, 0.0, 0.0)
	var v_data0 := _spawn_unit_operation(op0, 0, pos0)
	_stage_vessels.append(v_data0)
	_add_stage_spotlight(pos0)

	if is_chem_plant:
		_target = Vector3(0.8, 1.8, 0.0)
		_distance = 22.5
		_yaw = deg_to_rad(4.0)
		_pitch = deg_to_rad(-24.0)
	else:
		_target = v_data0.root.position + Vector3(0.9, 1.15, 0.0)
		_distance = 4.8
		_yaw = deg_to_rad(-22.0)
		_pitch = deg_to_rad(-10.0)
	_apply_camera()
	update_batch_continuity(0.0)

	build_progress = 1.0 / float(count)
	bench_build_progress.emit(1, count, str(op0.get("title", "0. Dry Kelp Milling")))

	# Frame 2-N: Stream subsequent stages one per frame
	for i in range(1, count):
		await get_tree().process_frame
		var op: Dictionary = unit_operations[i]
		var pos_x := -total_span * 0.5 + float(i) * STAGE_SPACING
		var pos: Vector3 = CHEM_PLOT_POSITIONS[i] if (is_chem_plant and i < CHEM_PLOT_POSITIONS.size()) else Vector3(pos_x, 0.0, 0.0)
		var v_data := _spawn_unit_operation(op, i, pos)
		_stage_vessels.append(v_data)
		_add_stage_spotlight(pos)

		build_progress = float(i + 1) / float(count)
		bench_build_progress.emit(i + 1, count, str(op.get("title", "Stage %d" % i)))

	# Yield one final frame before wiring pipes and slugs
	await get_tree().process_frame
	_build_all_interstage_pipes_and_slugs()
	update_batch_continuity(0.0)

	is_building = false
	build_progress = 1.0
	bench_build_completed.emit()


func _add_stage_spotlight(pos: Vector3) -> SpotLight3D:
	var spot := SpotLight3D.new()
	spot.position = pos + Vector3(0.0, 3.2, 0.25)
	spot.rotation_degrees = Vector3(-80.0, 0.0, 0.0)
	spot.spot_range = 4.2
	spot.spot_angle = 32.0
	spot.light_energy = 1.15
	spot.light_color = Color(0.92, 0.96, 1.0)
	_bench_root.add_child(spot)
	return spot


func _spawn_unit_operation(op: Dictionary, index: int, pos: Vector3) -> Dictionary:
	var root := Node3D.new()
	root.name = "Stage_%d_%s" % [index, op.get("stage_id", "vessel")]
	root.position = pos
	_bench_root.add_child(root)

	var primitive: String = str(op.get("equipment_primitive", "agitated_extraction_vessel"))
	var tier: String = str(op.get("evidence_tier", "DIRECT"))
	var is_unverified := (tier == "UNVERIFIED" or str(op.get("status", "")) == "insufficient_evidence")
	var drivers: Dictionary = op.get("visual_drivers", {})

	var liquid_mesh: MeshInstance3D = null
	var liquid_mat: StandardMaterial3D = null
	var impeller_node: Node3D = null
	var wireframe_mesh: MeshInstance3D = null
	var pellet_mesh: MeshInstance3D = null
	var meniscus_node: MeshInstance3D = null
	var rotor_node: Node3D = null
	var spool_node: Node3D = null
	var floc_mesh: MeshInstance3D = null
	var ph_halo: MeshInstance3D = null
	var mill_blades: Node3D = null
	var flakes_group: Node3D = null
	var pile_mesh: MeshInstance3D = null
	var fronds_group: Node3D = null
	var lcd_lbl: Label3D = null
	var chute_flakes: Array = []
	var discard_label: Label3D = null
	var powder_dish: Node3D = null

	var steel_mat := StandardMaterial3D.new()
	steel_mat.albedo_color = Color(0.68, 0.72, 0.78)
	steel_mat.metallic = 0.90
	steel_mat.roughness = 0.28

	# Reagent feed drop from overhead manifold
	var feed_pipe := CylinderMesh.new()
	feed_pipe.top_radius = 0.018
	feed_pipe.bottom_radius = 0.018
	feed_pipe.height = 1.2
	var fp := MeshInstance3D.new()
	fp.mesh = feed_pipe
	fp.position = Vector3(0.0, VESSEL_HEIGHT + 0.6, -0.3)
	fp.material_override = steel_mat
	root.add_child(fp)

	var archetype: String = str(op.get("archetype", primitive))
	var is_chem_plant: bool = false

	# ------------------------------------------------ DYNAMIC CHEMICAL / SMR PLANT ARCHETYPES
	if archetype in ["pre_reformer", "furnace_reformer", "shell_tube_hx", "packed_bed_reactor", "knockout_cooler", "co2_absorber", "psa_skid", "high_pressure_compressor", "separator_unit"]:
		is_chem_plant = _build_chemical_plant_archetype(root, archetype, op, steel_mat)

	# ------------------------------------------------ STAGE 0: DRY BIOMASS MILLING & SCALE
	elif "hopper" in primitive or "mill" in primitive:
		var hopper_data := _build_dry_biomass_hopper_mill(root, op)
		mill_blades = hopper_data.get("mill_blades")
		pile_mesh = hopper_data.get("pile")
		fronds_group = hopper_data.get("fronds_group")
		lcd_lbl = hopper_data.get("lcd_lbl")
		chute_flakes = hopper_data.get("chute_flakes", [])

	# ------------------------------------------------ CENTRIFUGE
	elif "centrifuge" in primitive:
		var cone := CylinderMesh.new()
		cone.top_radius = VESSEL_RADIUS * 0.95
		cone.bottom_radius = VESSEL_RADIUS * 0.35
		cone.height = 1.4
		cone.radial_segments = 36
		var cm := MeshInstance3D.new()
		cm.mesh = cone
		cm.position = Vector3(0.0, 1.1, 0.0)
		var cone_mat := StandardMaterial3D.new()
		cone_mat.albedo_color = Color(0.24, 0.28, 0.35, 0.85)
		cone_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		cone_mat.metallic = 0.65
		cone_mat.roughness = 0.25
		cm.material_override = cone_mat
		root.add_child(cm)

		var stand := BoxMesh.new()
		stand.size = Vector3(1.15, 0.4, 1.15)
		var sm := MeshInstance3D.new()
		sm.mesh = stand
		sm.position = Vector3(0.0, 0.2, 0.0)
		sm.material_override = steel_mat
		root.add_child(sm)

		# Clarifying supernatant liquid column
		var r_mesh := CylinderMesh.new()
		r_mesh.top_radius = VESSEL_RADIUS * 0.82
		r_mesh.bottom_radius = VESSEL_RADIUS * 0.30
		r_mesh.height = 0.9
		liquid_mesh = MeshInstance3D.new()
		liquid_mesh.mesh = r_mesh
		liquid_mesh.position = Vector3(0.0, 1.15, 0.0)
		liquid_mat = StandardMaterial3D.new()
		liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		liquid_mat.albedo_color = Color(0.08, 0.55, 0.38, 0.85)
		liquid_mat.roughness = 0.15
		liquid_mesh.material_override = liquid_mat
		liquid_mesh.visible = false
		root.add_child(liquid_mesh)

		# Compacting solid pellet mesh at the bottom (starts hidden, becomes visible at t >= 32.0h)
		pellet_mesh = _build_centrifuge_pellet(root)
		pellet_mesh.visible = false

		# Discarded residue label
		discard_label = Label3D.new()
		discard_label.text = "DISCARDED INSOLUBLE KELP RESIDUE"
		discard_label.position = Vector3(0.0, 0.75, 0.0)
		discard_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		discard_label.font_size = 18
		discard_label.pixel_size = 0.0025
		discard_label.modulate = Color(0.95, 0.45, 0.35)
		discard_label.visible = false
		root.add_child(discard_label)

		# High-speed rotor assembly
		rotor_node = Node3D.new()
		rotor_node.position = Vector3(0.0, 1.25, 0.0)
		root.add_child(rotor_node)
		for a in [0.0, 90.0, 180.0, 270.0]:
			var tube := CylinderMesh.new()
			tube.top_radius = 0.035
			tube.bottom_radius = 0.025
			tube.height = 0.45
			var tm := MeshInstance3D.new()
			tm.mesh = tube
			tm.rotation_degrees = Vector3(35.0, 0.0, 0.0).rotated(Vector3.UP, deg_to_rad(a))
			tm.position = Vector3(0.16, 0.0, 0.0).rotated(Vector3.UP, deg_to_rad(a))
			tm.material_override = steel_mat
			rotor_node.add_child(tm)

		# Live Floating pH indicator halo
		var halo := TorusMesh.new()
		halo.inner_radius = 0.14
		halo.outer_radius = 0.18
		ph_halo = MeshInstance3D.new()
		ph_halo.mesh = halo
		ph_halo.position = Vector3(0.0, 1.95, 0.0)
		var h_mat := StandardMaterial3D.new()
		h_mat.albedo_color = Color(0.72, 0.12, 0.85)
		h_mat.emission_enabled = true
		h_mat.emission = Color(0.72, 0.12, 0.85)
		h_mat.emission_energy_multiplier = 1.2
		ph_halo.material_override = h_mat
		ph_halo.visible = false
		root.add_child(ph_halo)

	# ------------------------------------------------ PRECIPITATION TANK
	elif "precipitation" in primitive:
		var trough := BoxMesh.new()
		trough.size = Vector3(1.35, 1.1, 0.95)
		var tm := MeshInstance3D.new()
		tm.mesh = trough
		tm.position = Vector3(0.0, 0.65, 0.0)
		var t_mat := StandardMaterial3D.new()
		t_mat.albedo_color = Color(0.65, 0.82, 0.95, 0.28)
		t_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		t_mat.metallic = 0.2
		t_mat.roughness = 0.06
		t_mat.rim_enabled = true
		t_mat.rim = 0.95
		t_mat.rim_tint = 0.8
		tm.material_override = t_mat
		root.add_child(tm)

		var fluid := BoxMesh.new()
		fluid.size = Vector3(1.26, 0.82, 0.86)
		liquid_mesh = MeshInstance3D.new()
		liquid_mesh.mesh = fluid
		liquid_mesh.position = Vector3(0.0, 0.58, 0.0)
		liquid_mat = StandardMaterial3D.new()
		liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		liquid_mat.albedo_color = Color(0.12, 0.65, 0.50, 0.72)
		liquid_mat.roughness = 0.18
		liquid_mesh.material_override = liquid_mat
		liquid_mesh.visible = false
		root.add_child(liquid_mesh)

		# Coalescing 3D fibrous alginate clot mesh (starts hidden)
		var clot_data := _build_fibrous_alginate_clot(root)
		floc_mesh = clot_data.get("clot")
		floc_mesh.visible = false
		powder_dish = clot_data.get("dish")
		if powder_dish != null:
			powder_dish.visible = false

	# ------------------------------------------------ WET SPINNING BATH
	elif "bath" in primitive:
		var trough := BoxMesh.new()
		trough.size = Vector3(1.75, 0.55, 0.85)
		var tm := MeshInstance3D.new()
		tm.mesh = trough
		tm.position = Vector3(0.0, 0.40, 0.0)
		var t_mat := StandardMaterial3D.new()
		t_mat.albedo_color = Color(0.35, 0.45, 0.55, 0.35)
		t_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		t_mat.roughness = 0.12
		tm.material_override = t_mat
		root.add_child(tm)

		var fluid := BoxMesh.new()
		fluid.size = Vector3(1.68, 0.42, 0.78)
		liquid_mesh = MeshInstance3D.new()
		liquid_mesh.mesh = fluid
		liquid_mesh.position = Vector3(0.0, 0.36, 0.0)
		liquid_mat = StandardMaterial3D.new()
		liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		liquid_mat.albedo_color = Color(0.20, 0.82, 0.65, 0.65)
		liquid_mesh.material_override = liquid_mat
		liquid_mesh.visible = false
		root.add_child(liquid_mesh)

		var nozzle := CylinderMesh.new()
		nozzle.top_radius = 0.04
		nozzle.bottom_radius = 0.012
		nozzle.height = 0.22
		var nm := MeshInstance3D.new()
		nm.mesh = nozzle
		nm.rotation_degrees = Vector3(0.0, 0.0, -90.0)
		nm.position = Vector3(-0.65, 0.38, 0.0)
		nm.material_override = steel_mat
		root.add_child(nm)

		for rx in [-0.25, 0.25]:
			var roller := CylinderMesh.new()
			roller.top_radius = 0.045
			roller.bottom_radius = 0.045
			roller.height = 0.55
			var rm := MeshInstance3D.new()
			rm.mesh = roller
			rm.rotation_degrees = Vector3(90.0, 0.0, 0.0)
			rm.position = Vector3(rx, 0.46, 0.0)
			rm.material_override = steel_mat
			root.add_child(rm)

		spool_node = Node3D.new()
		spool_node.position = Vector3(0.68, 0.58, 0.0)
		root.add_child(spool_node)
		_fibre_spool = spool_node
		var sm := CylinderMesh.new()
		sm.top_radius = 0.12
		sm.bottom_radius = 0.12
		sm.height = 0.40
		var spool_mesh := MeshInstance3D.new()
		spool_mesh.mesh = sm
		spool_mesh.rotation_degrees = Vector3(90.0, 0.0, 0.0)
		spool_mesh.material_override = steel_mat
		spool_node.add_child(spool_mesh)

		# Spool wound yarn layer that thickens during spinning
		var ym := CylinderMesh.new()
		ym.top_radius = 0.16
		ym.bottom_radius = 0.16
		ym.height = 0.36
		_spool_yarn_mesh = MeshInstance3D.new()
		_spool_yarn_mesh.mesh = ym
		_spool_yarn_mesh.rotation_degrees = Vector3(90.0, 0.0, 0.0)
		var ymat := StandardMaterial3D.new()
		ymat.albedo_color = Color(0.96, 0.98, 1.0)
		_spool_yarn_mesh.material_override = ymat
		_spool_yarn_mesh.scale = Vector3(0.01, 1.0, 0.01)
		spool_node.add_child(_spool_yarn_mesh)

		# Extruded 3D Polymer Filament
		var f_mesh := CylinderMesh.new()
		f_mesh.top_radius = 0.012
		f_mesh.bottom_radius = 0.012
		f_mesh.height = 1.35
		_fibre_mesh = MeshInstance3D.new()
		_fibre_mesh.name = "SpunAlginateFibre"
		_fibre_mesh.mesh = f_mesh
		_fibre_mesh.rotation_degrees = Vector3(0.0, 0.0, 90.0)
		_fibre_mesh.position = Vector3(0.0, 0.42, 0.0)
		var fmat := StandardMaterial3D.new()
		fmat.albedo_color = Color(0.95, 0.98, 1.0)
		fmat.roughness = 0.35
		fmat.emission_enabled = true
		fmat.emission = Color(0.4, 0.8, 1.0)
		fmat.emission_energy_multiplier = 0.4
		_fibre_mesh.material_override = fmat
		_fibre_mesh.visible = false
		root.add_child(_fibre_mesh)

		_fibre_particles = _create_fracture_particle_emitter()
		_fibre_particles.position = Vector3(0.0, 0.42, 0.0)
		root.add_child(_fibre_particles)

		_build_tensile_tester_rig(root)

	# ------------------------------------------------ AGITATED EXTRACTION / BIOREACTOR
	else:
		var body_mesh := CylinderMesh.new()
		body_mesh.top_radius = VESSEL_RADIUS
		body_mesh.bottom_radius = VESSEL_RADIUS
		body_mesh.height = VESSEL_HEIGHT
		body_mesh.radial_segments = 48
		var body := MeshInstance3D.new()
		body.mesh = body_mesh
		body.position = Vector3(0.0, VESSEL_HEIGHT * 0.5, 0.0)

		var glass := StandardMaterial3D.new()
		glass.albedo_color = Color(0.82, 0.90, 0.96, 0.12)
		glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		glass.cull_mode = BaseMaterial3D.CULL_DISABLED
		glass.roughness = 0.06
		glass.metallic = 0.12
		glass.rim_enabled = true
		glass.rim = 0.85
		glass.rim_tint = 0.4
		body.material_override = glass
		root.add_child(body)

		var flange := CylinderMesh.new()
		flange.top_radius = VESSEL_RADIUS * 1.15
		flange.bottom_radius = VESSEL_RADIUS * 1.15
		flange.height = 0.08
		var fm := MeshInstance3D.new()
		fm.mesh = flange
		fm.position = Vector3(0.0, 0.04, 0.0)
		fm.material_override = steel_mat
		root.add_child(fm)

		var l_mesh := CylinderMesh.new()
		l_mesh.top_radius = VESSEL_RADIUS * 0.96
		l_mesh.bottom_radius = VESSEL_RADIUS * 0.96
		l_mesh.height = 1.0
		liquid_mesh = MeshInstance3D.new()
		liquid_mesh.mesh = l_mesh
		liquid_mesh.position = Vector3(0.0, FILL_BASE_Y + 0.6, 0.0)
		liquid_mat = StandardMaterial3D.new()
		liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		liquid_mat.albedo_color = Color(0.12, 0.58, 0.42, 0.78)
		liquid_mat.roughness = 0.12
		liquid_mesh.material_override = liquid_mat
		liquid_mesh.visible = false
		root.add_child(liquid_mesh)

		var men_mesh := CylinderMesh.new()
		men_mesh.top_radius = VESSEL_RADIUS * 0.94
		men_mesh.bottom_radius = VESSEL_RADIUS * 0.90
		men_mesh.height = 0.04
		meniscus_node = MeshInstance3D.new()
		meniscus_node.mesh = men_mesh
		meniscus_node.position = Vector3(0.0, FILL_BASE_Y + 1.1, 0.0)
		var m_mat := StandardMaterial3D.new()
		m_mat.albedo_color = Color(0.20, 0.75, 0.55, 0.85)
		m_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m_mat.roughness = 0.08
		meniscus_node.material_override = m_mat
		meniscus_node.visible = false
		root.add_child(meniscus_node)

		var shaft := CylinderMesh.new()
		shaft.top_radius = 0.025
		shaft.bottom_radius = 0.025
		shaft.height = VESSEL_HEIGHT * 0.88
		var sm := MeshInstance3D.new()
		sm.mesh = shaft
		sm.position = Vector3(0.0, VESSEL_HEIGHT * 0.45, 0.0)
		sm.material_override = steel_mat
		root.add_child(sm)

		impeller_node = Node3D.new()
		impeller_node.position = Vector3(0.0, 0.45, 0.0)
		root.add_child(impeller_node)

		for ang in [0.0, 90.0, 180.0, 270.0]:
			var bl := BoxMesh.new()
			bl.size = Vector3(0.18, 0.06, 0.012)
			var bm := MeshInstance3D.new()
			bm.mesh = bl
			bm.position = Vector3(0.11, 0.0, 0.0).rotated(Vector3.UP, deg_to_rad(ang))
			bm.rotation_degrees = Vector3(0.0, ang, 0.0)
			bm.material_override = steel_mat
			impeller_node.add_child(bm)

		var motor := BoxMesh.new()
		motor.size = Vector3(0.22, 0.25, 0.22)
		var mm := MeshInstance3D.new()
		mm.mesh = motor
		mm.position = Vector3(0.0, VESSEL_HEIGHT + 0.12, 0.0)
		mm.material_override = steel_mat
		root.add_child(mm)

		# Spawn explicit 3D Solid Kelp Flakes Group (120 visible irregular meshes)
		flakes_group = _build_solid_kelp_flakes_in_vessel(root, 120)
		flakes_group.visible = false

	if is_unverified:
		var wire_box := BoxMesh.new()
		wire_box.size = Vector3(VESSEL_RADIUS * 2.4, VESSEL_HEIGHT + 0.4, VESSEL_RADIUS * 2.4)
		wireframe_mesh = MeshInstance3D.new()
		wireframe_mesh.mesh = wire_box
		wireframe_mesh.position = Vector3(0.0, (VESSEL_HEIGHT + 0.4) * 0.5, 0.0)
		var w_mat := StandardMaterial3D.new()
		w_mat.albedo_color = Color(1.0, 0.2, 0.2, 0.65)
		w_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		w_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		w_mat.emission_enabled = true
		w_mat.emission = Color(1.0, 0.15, 0.15)
		w_mat.emission_energy_multiplier = 1.2
		wireframe_mesh.material_override = w_mat
		root.add_child(wireframe_mesh)

	return {
		"stage_id": op.get("stage_id", "stage_%d" % index),
		"index": index,
		"root": root,
		"liquid": liquid_mesh,
		"liquid_mat": liquid_mat,
		"impeller": impeller_node,
		"meniscus": meniscus_node,
		"rotor": rotor_node,
		"spool": spool_node,
		"floc": floc_mesh,
		"pellet": pellet_mesh,
		"ph_halo": ph_halo,
		"mill_blades": mill_blades,
		"flakes_group": flakes_group,
		"pile": pile_mesh,
		"fronds_group": fronds_group,
		"lcd_lbl": lcd_lbl,
		"chute_flakes": chute_flakes,
		"discard_label": discard_label,
		"powder_dish": powder_dish,
		"wireframe": wireframe_mesh,
		"time_window": op.get("time_window_h", [0.0, 20.0]),
		"is_unverified": is_unverified,
		"is_active": false,
		"is_chemical_plant": is_chem_plant,
		"drivers": drivers,
	}


func _add_cad_box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO) -> MeshInstance3D:
	var m := BoxMesh.new()
	m.size = size
	var inst := MeshInstance3D.new()
	inst.mesh = m
	inst.position = pos
	inst.rotation_degrees = rot_deg
	inst.material_override = mat
	parent.add_child(inst)
	return inst


func _add_cad_cyl(parent: Node3D, r_top: float, r_bot: float, h: float, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO) -> MeshInstance3D:
	var m := CylinderMesh.new()
	m.top_radius = r_top
	m.bottom_radius = r_bot
	m.height = h
	var inst := MeshInstance3D.new()
	inst.mesh = m
	inst.position = pos
	inst.rotation_degrees = rot_deg
	inst.material_override = mat
	parent.add_child(inst)
	return inst


func _add_plinth(root: Node3D, w: float, d: float, h: float = 0.18) -> void:
	var concrete_mat := StandardMaterial3D.new()
	concrete_mat.albedo_color = Color(0.26, 0.28, 0.31)
	concrete_mat.roughness = 0.88
	concrete_mat.metallic = 0.05
	_add_cad_box(root, Vector3(w, h, d), Vector3(0.0, h * 0.5, 0.0), concrete_mat)


func _add_xray_cladding(root: Node3D, size: Vector3, pos: Vector3, solid_mat: StandardMaterial3D, xray_mat: StandardMaterial3D) -> void:
	var inst := _add_cad_box(root, size, pos, xray_mat)
	if not _smr_refs.has("xray_panels"):
		_smr_refs["xray_panels"] = []
	_smr_refs["xray_panels"].append({"mesh": inst, "solid": solid_mat, "xray": xray_mat})


func set_xray_cutaway(enabled: bool) -> void:
	var panels: Array = _smr_refs.get("xray_panels", [])
	for item in panels:
		var m := item.get("mesh", null) as MeshInstance3D
		if m != null and is_instance_valid(m):
			m.material_override = item["xray"] if enabled else item["solid"]


func _add_caged_ladder(root: Node3D, x: float, z: float, y_bot: float, height: float, mat: Material) -> void:
	var y_mid := y_bot + height * 0.5
	_add_cad_cyl(root, 0.015, 0.015, height, Vector3(x - 0.11, y_mid, z), mat)
	_add_cad_cyl(root, 0.015, 0.015, height, Vector3(x + 0.11, y_mid, z), mat)
	var rung_count := maxi(3, int(height / 0.32))
	for ri in range(rung_count):
		var ry := y_bot + 0.18 + float(ri) * (height - 0.24) / float(rung_count)
		_add_cad_cyl(root, 0.010, 0.010, 0.22, Vector3(x, ry, z), mat, Vector3(0.0, 0.0, 90.0))


func _build_chemical_plant_archetype(root: Node3D, archetype: String, op: Dictionary, steel_mat: StandardMaterial3D) -> bool:
	var temp_c: float = float(op.get("temperature_c", 25.0))
	var press_bar: float = float(op.get("pressure_bar", 1.0))
	var flow_nm3: float = float(op.get("flow_nm3_h", 0.0))
	var flow_basis: String = str(op.get("flow_basis", "Wet"))
	var purity_pct: float = float(op.get("h2_purity_pct", 72.0))
	var stage_idx: int = int(op.get("index", 0))

	var dark_steel := StandardMaterial3D.new()
	dark_steel.albedo_color = Color(0.20, 0.24, 0.29)
	dark_steel.metallic = 0.82
	dark_steel.roughness = 0.35

	var vessel_steel := StandardMaterial3D.new()
	vessel_steel.albedo_color = Color(0.32, 0.36, 0.42)
	vessel_steel.metallic = 0.80
	vessel_steel.roughness = 0.35

	var safety_yellow := StandardMaterial3D.new()
	safety_yellow.albedo_color = Color(0.68, 0.54, 0.14)
	safety_yellow.metallic = 0.30
	safety_yellow.roughness = 0.52

	var ladder_steel := StandardMaterial3D.new()
	ladder_steel.albedo_color = Color(0.42, 0.46, 0.52)
	ladder_steel.metallic = 0.82
	ladder_steel.roughness = 0.32

	var copper_mat := StandardMaterial3D.new()
	copper_mat.albedo_color = Color(0.84, 0.50, 0.22)
	copper_mat.metallic = 0.88
	copper_mat.roughness = 0.24

	var xray_cladding_mat := StandardMaterial3D.new()
	xray_cladding_mat.albedo_color = Color(0.45, 0.62, 0.78, 0.14)
	xray_cladding_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	xray_cladding_mat.roughness = 0.18
	xray_cladding_mat.metallic = 0.25

	# Elevated Horizontal Header Signboard mounted at top front cornice of each unit
	var tag_names := ["R-102 PRE-REF", "F-201 SMR", "E-105 WHB", "R-301A/B WGS", "E-401 / V-401", "C-501 CO2 CAP", "U-601 PSA", "K-701 COMP"]
	var unit_cornice_ys := [3.55, 4.55, 3.55, 3.55, 2.55, 4.05, 2.95, 2.45]
	var tag_name: String = tag_names[mini(stage_idx, tag_names.size() - 1)]
	var tag_y: float = unit_cornice_ys[mini(stage_idx, unit_cornice_ys.size() - 1)]
	var tag_z := 0.95

	var plate_mat := StandardMaterial3D.new()
	plate_mat.albedo_color = Color(0.05, 0.08, 0.12, 0.92)
	plate_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	plate_mat.roughness = 0.55
	_add_cad_box(root, Vector3(1.65, 0.42, 0.04), Vector3(0.0, tag_y, tag_z), plate_mat)

	var lbl := Label3D.new()
	lbl.text = "%s (%.0f Nm3/h %s)\n%.0f°C | %.0f bar | %.2f%% H2" % [tag_name, flow_nm3, flow_basis, temp_c, press_bar, purity_pct]
	lbl.font_size = 20
	lbl.pixel_size = 0.0052
	lbl.position = Vector3(0.0, tag_y, tag_z + 0.05)
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.modulate = Color(0.62, 0.96, 1.0)
	lbl.outline_size = 5
	root.add_child(lbl)

	if not _smr_refs.has("stage_labels"):
		_smr_refs["stage_labels"] = {}
	_smr_refs["stage_labels"][stage_idx] = lbl

	if archetype == "pre_reformer":
		# Unit 100: Upstream ZnO Sulfur Guard Bed (R-101A) + Adiabatic Pre-Reformer (R-102)
		_add_plinth(root, 2.8, 2.0, 0.16)

		var gunmetal_mat := StandardMaterial3D.new()
		gunmetal_mat.albedo_color = Color(0.20, 0.25, 0.31)
		gunmetal_mat.metallic = 0.85
		gunmetal_mat.roughness = 0.30

		# Upstream ZnO Sulfur Guard Bed R-101A (left)
		_add_cad_cyl(root, 0.30, 0.32, 0.35, Vector3(-0.78, 0.34, 0.0), dark_steel)
		_add_cad_cyl(root, 0.34, 0.34, 1.65, Vector3(-0.78, 1.32, 0.0), vessel_steel)
		var g_dome := SphereMesh.new()
		g_dome.radius = 0.34
		g_dome.height = 0.38
		var gd := MeshInstance3D.new()
		gd.mesh = g_dome
		gd.position = Vector3(-0.78, 2.14, 0.0)
		gd.material_override = vessel_steel
		root.add_child(gd)

		# Main Adiabatic Pre-Reformer R-102 (right, domed refractory-lined vessel with front cutaway)
		var rx := 0.42
		var rr := 0.56
		var rh := 2.10
		_add_cad_cyl(root, rr * 0.90, rr * 0.96, 0.42, Vector3(rx, 0.36, 0.0), dark_steel)
		var y_mid := 0.58 + rh * 0.5
		_add_cad_box(root, Vector3(rr * 2.0, rh, rr * 1.15), Vector3(rx, y_mid, -rr * 0.42), gunmetal_mat)
		_add_cad_box(root, Vector3(rr * 0.52, rh, rr * 0.85), Vector3(rx - rr * 0.74, y_mid, rr * 0.42), gunmetal_mat)
		_add_cad_box(root, Vector3(rr * 0.52, rh, rr * 0.85), Vector3(rx + rr * 0.74, y_mid, rr * 0.42), gunmetal_mat)
		_add_cad_cyl(root, rr * 1.03, rr * 1.03, 0.14, Vector3(rx, 0.58 + rh - 0.05, 0.0), gunmetal_mat)
		_add_cad_cyl(root, rr * 1.03, rr * 1.03, 0.14, Vector3(rx, 0.62, 0.0), gunmetal_mat)

		var win_inst := _add_cad_box(root, Vector3(rr * 0.98, rh - 0.18, 0.04), Vector3(rx, y_mid, rr * 0.84), xray_cladding_mat)
		if not _smr_refs.has("xray_panels"):
			_smr_refs["xray_panels"] = []
		_smr_refs["xray_panels"].append({"mesh": win_inst, "solid": gunmetal_mat, "xray": xray_cladding_mat})

		var r_dome := SphereMesh.new()
		r_dome.radius = rr
		r_dome.height = rr * 1.1
		var rd := MeshInstance3D.new()
		rd.mesh = r_dome
		rd.position = Vector3(rx, 0.58 + rh, 0.0)
		rd.material_override = gunmetal_mat
		root.add_child(rd)

		# Internal Ni-Catalyst Bed + Axial Thermocouple Lance TI-102A/B/C
		var ni_mat := StandardMaterial3D.new()
		ni_mat.albedo_color = Color(0.28, 0.34, 0.30)
		ni_mat.roughness = 0.78
		ni_mat.emission_enabled = true
		ni_mat.emission = Color(0.55, 0.42, 0.18)
		ni_mat.emission_energy_multiplier = 0.38
		_add_cad_cyl(root, rr * 0.78, rr * 0.78, rh * 0.72, Vector3(rx, y_mid, 0.02), ni_mat)
		_add_cad_cyl(root, rr * 0.84, rr * 0.84, 0.05, Vector3(rx, 0.82, 0.02), ladder_steel)
		# Axial Thermocouple Lance TI-102A/B/C
		_add_cad_cyl(root, 0.022, 0.022, rh + 0.35, Vector3(rx, y_mid + 0.15, 0.26), copper_mat)

		# Cutaway fill light so Ni-catalyst bed & vessel rim are clearly illuminated
		var fill := OmniLight3D.new()
		fill.position = Vector3(rx, y_mid, rr + 0.65)
		fill.light_energy = 1.6
		fill.omni_range = 2.8
		fill.light_color = Color(0.95, 0.90, 0.82)
		root.add_child(fill)

		_add_caged_ladder(root, rx + rr + 0.14, 0.18, 0.18, rh + 0.25, ladder_steel)
		return true

	elif archetype == "furnace_reformer":
		# Unit 100: Dominant Primary SMR Radiant Furnace (2.8m W x 4.0m H x 2.2m D) + Convection + 5.2m Stack
		_add_plinth(root, 3.2, 2.6, 0.18)

		# External I-beam buckstays & corner columns
		for cx in [-1.36, -0.45, 0.45, 1.36]:
			for cz in [-1.06, 1.06]:
				_add_cad_box(root, Vector3(0.09, 3.85, 0.09), Vector3(cx, 2.10, cz), dark_steel)
		# Terrace-wall refractory back, side walls & roof arch
		_add_cad_box(root, Vector3(2.72, 3.70, 0.10), Vector3(0.0, 2.05, -1.04), dark_steel)
		_add_cad_box(root, Vector3(0.10, 3.70, 2.08), Vector3(-1.34, 2.05, 0.0), dark_steel)
		_add_cad_box(root, Vector3(0.10, 3.70, 2.08), Vector3(1.34, 2.05, 0.0), dark_steel)
		_add_cad_box(root, Vector3(2.82, 0.16, 2.20), Vector3(0.0, 3.96, 0.0), dark_steel)
		# Front X-Ray cutaway cladding wall
		_add_xray_cladding(root, Vector3(2.60, 3.55, 0.04), Vector3(0.0, 2.05, 1.04), dark_steel, xray_cladding_mat)

		# Multi-tier access platforms with thin dark-yellow safety handrails & thin metallic ladder
		for py in [1.85, 3.88]:
			_add_cad_box(root, Vector3(3.15, 0.05, 0.45), Vector3(0.0, py, 1.28), dark_steel)
			_add_cad_cyl(root, 0.015, 0.015, 3.15, Vector3(0.0, py + 0.44, 1.49), safety_yellow, Vector3(0.0, 0.0, 90.0))
			for px in [-1.52, -0.50, 0.50, 1.52]:
				_add_cad_cyl(root, 0.015, 0.015, 0.44, Vector3(px, py + 0.22, 1.49), safety_yellow)
		_add_caged_ladder(root, -1.48, 1.28, 0.18, 3.75, ladder_steel)

		# Side-mounted horizontal convection pass -> 5.2m tall cylindrical flue gas stack
		# Cutaway convection duct exposing 3 horizontal finned tube banks (Mixed Feed, Steam Superheater, BFW Economizer)
		_add_cad_box(root, Vector3(1.15, 0.95, 1.15), Vector3(-1.88, 3.35, -0.25), xray_cladding_mat)
		for ci in range(3):
			var cy := 3.05 + float(ci) * 0.28
			for cz in [-0.48, -0.16, 0.16, 0.48]:
				_add_cad_cyl(root, 0.032, 0.032, 1.05, Vector3(-1.88, cy, cz - 0.15), copper_mat, Vector3(0.0, 0.0, 90.0))
		_add_cad_cyl(root, 0.34, 0.42, 3.20, Vector3(-2.15, 3.60, -0.25), vessel_steel) # Reaches y = 5.2m!

		# Dense Bank of 24 Slender Vertical Catalyst Tubes (3 rows x 8 tubes, radius 0.035m)
		# Continuous from top inlet header (y=3.92) down into bottom refractory transfer manifold (y=0.42)
		var zone_mats: Array = []
		var zone_cols := [
			Color(0.55, 0.44, 0.36), # 520 C top inlet
			Color(0.82, 0.46, 0.20), # 640 C upper-mid
			Color(0.96, 0.50, 0.14), # 760 C lower-mid
			Color(1.00, 0.62, 0.18), # 850 C bottom radiant
		]
		var zone_energies := [0.35, 0.90, 1.65, 2.50]
		for zi in range(4):
			var zm := StandardMaterial3D.new()
			zm.albedo_color = zone_cols[zi]
			zm.metallic = 0.50
			zm.emission_enabled = true
			zm.emission = zone_cols[zi]
			zm.emission_energy_multiplier = zone_energies[zi]
			zone_mats.append(zm)
		_smr_refs["reformer_tube_mats"] = zone_mats

		for tz in [-0.44, 0.0, 0.44]:
			for ti in range(8):
				var tx := -1.05 + float(ti) * 0.30
				for zi in range(4):
					var zy := 3.48 - float(zi) * 0.875
					_add_cad_cyl(root, 0.035, 0.035, 0.875, Vector3(tx, zy, tz), zone_mats[zi])
				# Top inlet pigtail
				_add_cad_cyl(root, 0.018, 0.018, 0.25, Vector3(tx, 4.02, tz), vessel_steel)

		# Top inlet pigtail header & bottom outlet collector manifold
		_add_cad_cyl(root, 0.08, 0.08, 2.40, Vector3(0.0, 4.14, 0.0), vessel_steel, Vector3(0.0, 0.0, 90.0))
		_add_cad_cyl(root, 0.12, 0.12, 2.55, Vector3(0.0, 0.38, 0.0), dark_steel, Vector3(0.0, 0.0, 90.0))

		# 12 Radiant Floor Burners in the lanes between tube rows firing upward
		var burner_mat := StandardMaterial3D.new()
		burner_mat.albedo_color = Color(1.0, 0.44, 0.08)
		burner_mat.emission_enabled = true
		burner_mat.emission = Color(1.0, 0.40, 0.06)
		burner_mat.emission_energy_multiplier = 2.8
		_smr_refs["reformer_burner_mat"] = burner_mat
		for bz in [-0.66, -0.22, 0.22, 0.66]:
			for bx in [-0.90, 0.0, 0.90]:
				_add_cad_cyl(root, 0.01, 0.065, 0.28, Vector3(bx, 0.36, bz), burner_mat)

		# Dedicated Blue Emergency N2 Purge Header + Actuated Isolation Valve XV-101
		var n2_mat := StandardMaterial3D.new()
		n2_mat.albedo_color = Color(0.22, 0.62, 0.98)
		n2_mat.metallic = 0.72
		_smr_refs["n2_purge_mat"] = n2_mat
		_add_cad_cyl(root, 0.045, 0.045, 3.20, Vector3(-1.52, 1.85, 0.65), n2_mat)
		_add_cad_cyl(root, 0.038, 0.038, 0.55, Vector3(-1.25, 3.45, 0.65), n2_mat, Vector3(0.0, 0.0, 90.0))
		var xv_mat := StandardMaterial3D.new()
		xv_mat.albedo_color = Color(0.92, 0.30, 0.22)
		xv_mat.metallic = 0.60
		_smr_refs["xv101_mat"] = xv_mat
		_add_cad_box(root, Vector3(0.16, 0.16, 0.16), Vector3(-1.52, 2.25, 0.65), xv_mat)
		return true

	elif archetype == "shell_tube_hx":
		# Unit 200: Process Gas Waste Heat Boiler (E-105) + Elevated Steam Drum (V-102)
		_add_plinth(root, 2.6, 1.8, 0.16)

		# Twin concrete/steel saddle supports for E-105
		for sx in [-0.65, 0.65]:
			_add_cad_box(root, Vector3(0.20, 0.65, 0.86), Vector3(sx, 0.48, 0.0), dark_steel)

		# E-105 Horizontal Cutaway Shell (radius 0.52, length 2.0m)
		var hx_shell_inst := _add_cad_cyl(root, 0.52, 0.52, 1.95, Vector3(0.0, 1.18, 0.0), xray_cladding_mat, Vector3(0.0, 0.0, 90.0))
		if not _smr_refs.has("xray_panels"):
			_smr_refs["xray_panels"] = []
		_smr_refs["xray_panels"].append({"mesh": hx_shell_inst, "solid": vessel_steel, "xray": xray_cladding_mat})

		# Bolted channel head (left hot inlet) & rear shell cap
		_add_cad_cyl(root, 0.54, 0.54, 0.30, Vector3(-1.08, 1.18, 0.0), dark_steel, Vector3(0.0, 0.0, 90.0))
		_add_cad_cyl(root, 0.54, 0.54, 0.16, Vector3(1.02, 1.18, 0.0), vessel_steel, Vector3(0.0, 0.0, 90.0))

		# Tube Sheet & 5 Thin Metallic Segmental Baffles
		_add_cad_cyl(root, 0.48, 0.48, 0.04, Vector3(-0.90, 1.18, 0.0), copper_mat, Vector3(0.0, 0.0, 90.0))
		for bx in [-0.60, -0.30, 0.0, 0.30, 0.60]:
			_add_cad_cyl(root, 0.44, 0.44, 0.02, Vector3(bx, 1.18, 0.0), dark_steel, Vector3(0.0, 0.0, 90.0))

		# Dense Bundle of 18 Slender Heat-Exchanger Tubes (3x6 array, radius 0.020m)
		var hx_hot_mat := StandardMaterial3D.new()
		hx_hot_mat.albedo_color = Color(1.0, 0.46, 0.14)
		hx_hot_mat.emission_enabled = true
		hx_hot_mat.emission = Color(1.0, 0.38, 0.08)
		hx_hot_mat.emission_energy_multiplier = 1.35

		var hx_cool_mat := StandardMaterial3D.new()
		hx_cool_mat.albedo_color = Color(0.86, 0.66, 0.28)
		hx_cool_mat.metallic = 0.78
		hx_cool_mat.emission_enabled = true
		hx_cool_mat.emission = Color(0.85, 0.55, 0.15)
		hx_cool_mat.emission_energy_multiplier = 0.40
		_smr_refs["e105_outlet_mat"] = hx_cool_mat

		for ty in [0.96, 1.18, 1.40]:
			for tz in [-0.24, -0.08, 0.08, 0.24]:
				_add_cad_cyl(root, 0.020, 0.020, 0.88, Vector3(-0.44, ty, tz), hx_hot_mat, Vector3(0.0, 0.0, 90.0))
				_add_cad_cyl(root, 0.020, 0.020, 0.88, Vector3(0.44, ty, tz), hx_cool_mat, Vector3(0.0, 0.0, 90.0))

		# Elevated Horizontal Steam Drum (V-102) on 4 Structural Steel Columns + 4 Vertical Riser/Downcomer Pipes
		for sx in [-0.85, 0.85]:
			for sz in [-0.55, 0.55]:
				_add_cad_box(root, Vector3(0.08, 2.55, 0.08), Vector3(sx, 1.42, sz), dark_steel)
		_add_cad_cyl(root, 0.32, 0.32, 1.85, Vector3(0.0, 2.75, 0.0), vessel_steel, Vector3(0.0, 0.0, 90.0))
		for rx in [-0.55, -0.18, 0.18, 0.55]:
			_add_cad_cyl(root, 0.042, 0.042, 0.95, Vector3(rx, 2.05, 0.0), vessel_steel)

		var beacon_mat := StandardMaterial3D.new()
		beacon_mat.albedo_color = Color(0.25, 0.85, 0.45)
		_smr_refs["e105_fault_beacon"] = beacon_mat
		_add_cad_cyl(root, 0.055, 0.055, 0.12, Vector3(0.0, 3.16, 0.0), beacon_mat)
		return true

	elif archetype == "packed_bed_reactor":
		# Unit 300: Two-Stage Water-Gas Shift Island (R-301A HT-Shift + R-301B LT-Shift + Inter-bed Cooler)
		_add_plinth(root, 2.6, 1.8, 0.16)

		var gunmetal_mat := StandardMaterial3D.new()
		gunmetal_mat.albedo_color = Color(0.18, 0.22, 0.27)
		gunmetal_mat.metallic = 0.85
		gunmetal_mat.roughness = 0.30

		# R-301A HT-Shift Reactor (left, taller) + R-301B LT-Shift Reactor (right)
		var r_specs := [
			{"x": -0.62, "h": 2.25, "r": 0.44, "cat_col": Color(0.36, 0.20, 0.12)},
			{"x": 0.62,  "h": 1.75, "r": 0.40, "cat_col": Color(0.18, 0.34, 0.30)},
		]
		for rs in r_specs:
			var rx: float = rs["x"]
			var rh: float = rs["h"]
			var rr: float = rs["r"]
			# Cylindrical steel skirt support
			_add_cad_cyl(root, rr * 0.90, rr * 0.96, 0.45, Vector3(rx, 0.38, 0.0), dark_steel)

			# Solid dark gunmetal pressure vessel shell on back & left/right sides, leaving a narrow front cutaway slot (50% diameter)
			var y_mid := 0.60 + rh * 0.5
			_add_cad_box(root, Vector3(rr * 2.0, rh, rr * 1.15), Vector3(rx, y_mid, -rr * 0.42), gunmetal_mat)
			_add_cad_box(root, Vector3(rr * 0.52, rh, rr * 0.85), Vector3(rx - rr * 0.74, y_mid, rr * 0.42), gunmetal_mat)
			_add_cad_box(root, Vector3(rr * 0.52, rh, rr * 0.85), Vector3(rx + rr * 0.74, y_mid, rr * 0.42), gunmetal_mat)
			# Top & bottom pressure vessel collar rings
			_add_cad_cyl(root, rr * 1.03, rr * 1.03, 0.14, Vector3(rx, 0.60 + rh - 0.05, 0.0), gunmetal_mat)
			_add_cad_cyl(root, rr * 1.03, rr * 1.03, 0.14, Vector3(rx, 0.64, 0.0), gunmetal_mat)

			# Front cutaway window cover (toggled by X-Ray Cutaway button)
			var win_inst := _add_cad_box(root, Vector3(rr * 0.98, rh - 0.18, 0.04), Vector3(rx, y_mid, rr * 0.84), xray_cladding_mat)
			if not _smr_refs.has("xray_panels"):
				_smr_refs["xray_panels"] = []
			_smr_refs["xray_panels"].append({"mesh": win_inst, "solid": gunmetal_mat, "xray": xray_cladding_mat})

			# Top hemispherical dome + inlet diffuser cone
			var dome := SphereMesh.new()
			dome.radius = rr
			dome.height = rr * 1.1
			var d_inst := MeshInstance3D.new()
			d_inst.mesh = dome
			d_inst.position = Vector3(rx, 0.60 + rh, 0.0)
			d_inst.material_override = gunmetal_mat
			root.add_child(d_inst)

			# 3 Distinct Multi-Layered Packed Catalyst Beds separated by perforated support grates & quench distributor rings
			var cat_col: Color = rs["cat_col"]
			var cat_mat := StandardMaterial3D.new()
			cat_mat.albedo_color = cat_col
			cat_mat.roughness = 0.82
			cat_mat.metallic = 0.15
			cat_mat.emission_enabled = true
			cat_mat.emission = cat_col
			cat_mat.emission_energy_multiplier = 0.35

			var bed_h := (rh - 0.42) / 3.0
			for bi in range(3):
				var by := 0.82 + float(bi) * (bed_h + 0.08) + bed_h * 0.5
				_add_cad_cyl(root, rr * 0.78, rr * 0.78, bed_h, Vector3(rx, by, 0.02), cat_mat)
				# Perforated support grate & quench distributor ring below each bed
				_add_cad_cyl(root, rr * 0.84, rr * 0.84, 0.045, Vector3(rx, by - bed_h * 0.5 - 0.025, 0.02), ladder_steel)

			# Top platform ring with thin dark-yellow handrail & thin metallic ladder
			_add_cad_cyl(root, rr + 0.16, rr + 0.16, 0.035, Vector3(rx, 0.60 + rh - 0.14, 0.0), dark_steel)
			_add_cad_cyl(root, 0.015, 0.015, rr * 2.3, Vector3(rx, 0.60 + rh + 0.24, rr + 0.14), safety_yellow, Vector3(0.0, 0.0, 90.0))
			_add_caged_ladder(root, rx - rr - 0.14, 0.18, 0.18, rh + 0.25, ladder_steel)

		# Inter-bed Cooler + Crossover Pipe between R-301A and R-301B
		_add_cad_cyl(root, 0.16, 0.16, 0.72, Vector3(0.0, 0.95, 0.32), vessel_steel, Vector3(0.0, 0.0, 90.0))
		_add_cad_cyl(root, 0.045, 0.045, 0.65, Vector3(-0.32, 1.45, 0.32), vessel_steel)
		_add_cad_cyl(root, 0.045, 0.045, 0.65, Vector3(0.32, 1.45, 0.32), vessel_steel)

		# Cutaway fill light so gunmetal steel rims & 3-layer catalyst beds pop
		var wgs_fill := OmniLight3D.new()
		wgs_fill.position = Vector3(0.0, 1.65, 1.25)
		wgs_fill.light_energy = 1.8
		wgs_fill.omni_range = 3.2
		wgs_fill.light_color = Color(0.95, 0.92, 0.88)
		root.add_child(wgs_fill)
		return true

	elif archetype == "knockout_cooler":
		# Unit 500: Syngas Trim Cooler (E-401 Fin-Fan Bay) & Process Condensate Knock-Out Drum (V-401)
		_add_plinth(root, 2.8, 2.0, 0.16)

		# Fin-Fan Trim Cooler Bay (left) with 2 rotating fans
		for fx in [-1.05, -0.15]:
			for fz in [-0.55, 0.55]:
				_add_cad_box(root, Vector3(0.06, 1.45, 0.06), Vector3(fx, 0.88, fz), dark_steel)
		_add_cad_box(root, Vector3(1.05, 0.14, 1.25), Vector3(-0.60, 1.55, 0.0), vessel_steel)
		var kc_fans: Array = _smr_refs.get("comp_fan_nodes", [])
		for fz in [-0.32, 0.32]:
			var fan_hub := Node3D.new()
			fan_hub.position = Vector3(-0.60, 1.66, fz)
			root.add_child(fan_hub)
			_add_cad_box(fan_hub, Vector3(0.46, 0.02, 0.08), Vector3.ZERO, copper_mat)
			_add_cad_box(fan_hub, Vector3(0.08, 0.02, 0.46), Vector3.ZERO, copper_mat)
			kc_fans.append(fan_hub)
		_smr_refs["comp_fan_nodes"] = kc_fans

		# Vertical Process Condensate Knock-Out Drum V-401 (right) + bottom condensate boot + sight glass
		_add_cad_cyl(root, 0.38, 0.38, 0.38, Vector3(0.68, 0.35, 0.0), dark_steel)
		_add_cad_cyl(root, 0.42, 0.42, 1.45, Vector3(0.68, 1.25, 0.0), vessel_steel)
		var v_dome := SphereMesh.new()
		v_dome.radius = 0.42
		v_dome.height = 0.44
		var vd := MeshInstance3D.new()
		vd.mesh = v_dome
		vd.position = Vector3(0.68, 1.98, 0.0)
		vd.material_override = vessel_steel
		root.add_child(vd)
		# Bottom condensate boot & blue water level sight-glass
		_add_cad_cyl(root, 0.16, 0.16, 0.36, Vector3(0.68, 0.36, 0.38), vessel_steel)
		var water_mat := StandardMaterial3D.new()
		water_mat.albedo_color = Color(0.20, 0.72, 0.96)
		water_mat.emission_enabled = true
		water_mat.emission = Color(0.15, 0.60, 0.90)
		water_mat.emission_energy_multiplier = 0.65
		_add_cad_cyl(root, 0.032, 0.032, 0.55, Vector3(1.12, 0.85, 0.18), water_mat)
		return true

	elif archetype == "co2_absorber":
		# Unit 600: Amine CO2 Capture Absorber (C-501) & Stripper Column (C-502) + Reflux Condenser & Reboiler
		_add_plinth(root, 2.8, 2.0, 0.16)

		var gunmetal_mat := StandardMaterial3D.new()
		gunmetal_mat.albedo_color = Color(0.19, 0.23, 0.29)
		gunmetal_mat.metallic = 0.85
		gunmetal_mat.roughness = 0.30

		# Tall Flanged Packed Absorber Column C-501 (left, 3.5m tall) with 2 structured packing cutaway slots
		_add_cad_cyl(root, 0.44, 0.48, 0.42, Vector3(-0.55, 0.37, 0.0), dark_steel)
		_add_cad_box(root, Vector3(0.92, 2.75, 0.52), Vector3(-0.55, 1.95, -0.20), gunmetal_mat)
		_add_cad_box(root, Vector3(0.24, 2.75, 0.42), Vector3(-0.89, 1.95, 0.18), gunmetal_mat)
		_add_cad_box(root, Vector3(0.24, 2.75, 0.42), Vector3(-0.21, 1.95, 0.18), gunmetal_mat)
		var c_win := _add_cad_box(root, Vector3(0.46, 2.55, 0.04), Vector3(-0.55, 1.95, 0.38), xray_cladding_mat)
		if not _smr_refs.has("xray_panels"):
			_smr_refs["xray_panels"] = []
		_smr_refs["xray_panels"].append({"mesh": c_win, "solid": gunmetal_mat, "xray": xray_cladding_mat})
		for fy in [0.95, 1.85, 2.75, 3.30]:
			_add_cad_cyl(root, 0.49, 0.49, 0.06, Vector3(-0.55, fy, 0.0), dark_steel)
		var c_dome := SphereMesh.new()
		c_dome.radius = 0.46
		c_dome.height = 0.50
		var cd := MeshInstance3D.new()
		cd.mesh = c_dome
		cd.position = Vector3(-0.55, 3.34, 0.0)
		cd.material_override = gunmetal_mat
		root.add_child(cd)

		# 2 Structured Packing Zones inside C-501 cutaway
		var pack_mat := StandardMaterial3D.new()
		pack_mat.albedo_color = Color(0.28, 0.42, 0.62)
		pack_mat.metallic = 0.65
		pack_mat.roughness = 0.40
		pack_mat.emission_enabled = true
		pack_mat.emission = Color(0.18, 0.35, 0.55)
		pack_mat.emission_energy_multiplier = 0.32
		_add_cad_cyl(root, 0.36, 0.36, 0.90, Vector3(-0.55, 1.40, 0.02), pack_mat)
		_add_cad_cyl(root, 0.36, 0.36, 0.90, Vector3(-0.55, 2.50, 0.02), pack_mat)

		# Adjacent Amine Stripper Column C-502 (right, 2.9m tall) + Kettle Reboiler + Top Reflux Condenser
		_add_cad_cyl(root, 0.34, 0.34, 2.45, Vector3(0.62, 1.45, 0.0), vessel_steel)
		var s_dome := SphereMesh.new()
		s_dome.radius = 0.34
		s_dome.height = 0.36
		var sd := MeshInstance3D.new()
		sd.mesh = s_dome
		sd.position = Vector3(0.62, 2.68, 0.0)
		sd.material_override = vessel_steel
		root.add_child(sd)
		_add_cad_cyl(root, 0.22, 0.22, 0.85, Vector3(0.62, 0.45, 0.55), copper_mat, Vector3(0.0, 0.0, 90.0)) # Bottom reboiler
		_add_cad_cyl(root, 0.16, 0.16, 0.68, Vector3(0.62, 2.95, 0.25), dark_steel, Vector3(0.0, 0.0, 90.0)) # Top reflux condenser

		var co2_fill := OmniLight3D.new()
		co2_fill.position = Vector3(-0.55, 2.0, 1.15)
		co2_fill.light_energy = 1.6
		co2_fill.omni_range = 3.2
		co2_fill.light_color = Color(0.85, 0.92, 1.0)
		root.add_child(co2_fill)
		return true

	elif archetype == "psa_skid":
		# Unit 400: 8-Bed Pressure Swing Adsorption Matrix (2x4) + V-401 Tail Gas Surge Drum
		_add_plinth(root, 3.4, 2.2, 0.16)

		# Multi-level structural steel skid framing
		for cx in [-1.45, 0.0, 0.85]:
			for cz in [-0.88, 0.88]:
				_add_cad_box(root, Vector3(0.07, 2.45, 0.07), Vector3(cx, 1.38, cz), dark_steel)
		_add_cad_box(root, Vector3(2.40, 0.06, 1.80), Vector3(-0.30, 2.45, 0.0), dark_steel)

		# 2x4 Matrix of 8 Slender Pressure Vessels with Hemispherical Domes + Subtle LED Ring & Thin Saturation Bar
		var psa_mats: Array = []
		for row_z in [-0.46, 0.46]:
			for col_i in range(4):
				var vx := -1.18 + float(col_i) * 0.58
				_add_cad_cyl(root, 0.14, 0.14, 1.85, Vector3(vx, 1.18, row_z), vessel_steel)
				var dome := SphereMesh.new()
				dome.radius = 0.14
				dome.height = 0.22
				var d_inst := MeshInstance3D.new()
				d_inst.mesh = dome
				d_inst.position = Vector3(vx, 2.10, row_z)
				d_inst.material_override = vessel_steel
				root.add_child(d_inst)

				# Subtle LED ring status indicator + thin vertical bed saturation bar
				var led_mat := StandardMaterial3D.new()
				led_mat.albedo_color = Color(0.15, 0.88, 0.55)
				led_mat.emission_enabled = true
				led_mat.emission = Color(0.15, 0.88, 0.55)
				led_mat.emission_energy_multiplier = 1.1
				psa_mats.append(led_mat)
				_add_cad_cyl(root, 0.148, 0.148, 0.05, Vector3(vx, 1.92, row_z), led_mat)
				_add_cad_box(root, Vector3(0.025, 0.95, 0.025), Vector3(vx, 1.25, row_z + (0.14 if row_z > 0 else -0.14)), led_mat)
		_smr_refs["psa_bed_mats"] = psa_mats

		# Top product manifold piping & bottom valve rack
		_add_cad_cyl(root, 0.045, 0.045, 2.10, Vector3(-0.30, 2.35, 0.0), vessel_steel, Vector3(0.0, 0.0, 90.0))
		_add_cad_box(root, Vector3(2.20, 0.12, 1.20), Vector3(-0.30, 0.28, 0.0), dark_steel)

		# Adjacent Horizontal PSA Tail Gas Surge Drum (V-601) on Concrete Saddles
		for sx in [1.05, 1.55]:
			_add_cad_box(root, Vector3(0.12, 0.45, 0.52), Vector3(sx, 0.38, 0.0), dark_steel)
		_add_cad_cyl(root, 0.28, 0.28, 1.15, Vector3(1.30, 0.86, 0.0), vessel_steel, Vector3(0.0, 0.0, 90.0))

		var psa_fill := OmniLight3D.new()
		psa_fill.position = Vector3(-0.30, 1.85, 1.25)
		psa_fill.light_energy = 1.4
		psa_fill.omni_range = 3.5
		psa_fill.light_color = Color(0.88, 0.94, 1.0)
		root.add_child(psa_fill)
		return true

	elif archetype == "high_pressure_compressor":
		# Unit 500: 3-Stage Reciprocating Compressor House (K-501) + Bank of 3x 400 bar H2 Storage Bullets (V-501A/B/C)
		_add_plinth(root, 3.6, 2.4, 0.16)

		# 3-Stage Reciprocating Compressor Skid: Crankcase + 3 Horizontal Cylinders + Pulsation Dampeners + Electric Motor
		_add_cad_box(root, Vector3(0.85, 0.55, 1.35), Vector3(-1.05, 0.48, 0.0), dark_steel)
		_add_cad_cyl(root, 0.26, 0.26, 0.65, Vector3(-1.05, 0.52, -0.95), copper_mat, Vector3(90.0, 0.0, 0.0)) # Electric driver
		for cz in [-0.42, 0.0, 0.42]:
			_add_cad_cyl(root, 0.12, 0.12, 0.55, Vector3(-0.55, 0.52, cz), vessel_steel, Vector3(0.0, 0.0, 90.0))
			# Pulsation dampener bottle above cylinder
			_add_cad_cyl(root, 0.09, 0.09, 0.42, Vector3(-0.55, 0.86, cz), dark_steel, Vector3(0.0, 0.0, 90.0))

		# Overhead Fin-Fan Interstage Air Cooler Bay with 2 Rotating Fans
		for fx in [-1.35, -0.35]:
			for fz in [-0.72, 0.72]:
				_add_cad_box(root, Vector3(0.06, 1.55, 0.06), Vector3(fx, 0.92, fz), dark_steel)
		_add_cad_box(root, Vector3(1.15, 0.14, 1.50), Vector3(-0.85, 1.65, 0.0), vessel_steel)
		var fan_nodes: Array = _smr_refs.get("comp_fan_nodes", [])
		for fz in [-0.36, 0.36]:
			var fan_hub := Node3D.new()
			fan_hub.position = Vector3(-0.85, 1.76, fz)
			root.add_child(fan_hub)
			_add_cad_box(fan_hub, Vector3(0.56, 0.02, 0.09), Vector3.ZERO, copper_mat)
			_add_cad_box(fan_hub, Vector3(0.09, 0.02, 0.56), Vector3.ZERO, copper_mat)
			fan_nodes.append(fan_hub)
		_smr_refs["comp_fan_nodes"] = fan_nodes

		# Bank of 3 Large Horizontal 400-bar H2 Storage Bullets (V-501A/B/C) on Concrete Saddles
		var h2_tank_mat := StandardMaterial3D.new()
		h2_tank_mat.albedo_color = Color(0.18, 0.80, 0.95)
		h2_tank_mat.metallic = 0.78
		h2_tank_mat.roughness = 0.24
		for tz in [-0.62, 0.0, 0.62]:
			_add_cad_box(root, Vector3(0.14, 0.46, 0.36), Vector3(0.32, 0.38, tz), dark_steel)
			_add_cad_box(root, Vector3(0.14, 0.46, 0.36), Vector3(1.22, 0.38, tz), dark_steel)
			_add_cad_cyl(root, 0.23, 0.23, 1.45, Vector3(0.77, 0.84, tz), h2_tank_mat, Vector3(0.0, 0.0, 90.0))
		return true

	return false


func update_smr_process_state(sc_ratio: float, reformer_temp_c: float, pressure_bar: float, fault_state: Dictionary) -> void:
	_smr_process_state["sc_ratio"] = sc_ratio
	_smr_process_state["reformer_temp_c"] = reformer_temp_c
	_smr_process_state["pressure_bar"] = pressure_bar
	_smr_process_state["e105_cooling_loss"] = bool(fault_state.get("e105_cooling_loss", false))
	_smr_process_state["coking_warning"] = bool(fault_state.get("coking_warning", false))
	_smr_process_state["n2_purge_active"] = bool(fault_state.get("n2_purge_active", false))

	var temp_norm := clampf((reformer_temp_c - 750.0) / 170.0, 0.0, 1.0)
	var coking: bool = bool(_smr_process_state["coking_warning"])
	var purge: bool = bool(_smr_process_state["n2_purge_active"])
	var tube_mats: Array = _smr_refs.get("reformer_tube_mats", [])
	for idx in range(tube_mats.size()):
		var tm := tube_mats[idx] as StandardMaterial3D
		if tm == null:
			continue
		if purge:
			tm.emission = Color(0.20, 0.55, 0.95)
			tm.emission_energy_multiplier = 0.45
		elif coking:
			tm.albedo_color = Color(0.18, 0.16, 0.15)
			tm.emission = Color(0.65, 0.22, 0.05)
			tm.emission_energy_multiplier = 0.5 + 0.5 * temp_norm
		else:
			tm.emission = Color(1.0, 0.36 + 0.12 * float(idx) * 0.4, 0.08)
			tm.emission_energy_multiplier = (0.35 + 0.55 * float(idx)) * (0.65 + 0.85 * temp_norm)

	var burner_mat := _smr_refs.get("reformer_burner_mat", null) as StandardMaterial3D
	if burner_mat != null:
		burner_mat.emission_energy_multiplier = 0.2 if purge else (1.8 + 2.2 * temp_norm)

	var xv_mat := _smr_refs.get("xv101_mat", null) as StandardMaterial3D
	if xv_mat != null:
		xv_mat.albedo_color = Color(0.15, 0.95, 0.45) if purge else Color(0.92, 0.30, 0.22)

	var e105_mat := _smr_refs.get("e105_outlet_mat", null) as StandardMaterial3D
	if e105_mat != null:
		if bool(_smr_process_state["e105_cooling_loss"]):
			e105_mat.emission = Color(1.0, 0.22, 0.08)
			e105_mat.emission_energy_multiplier = 2.0
		else:
			e105_mat.emission = Color(0.85, 0.55, 0.15)
			e105_mat.emission_energy_multiplier = 0.40

	var lbls: Dictionary = _smr_refs.get("stage_labels", {})
	var e105_t := 580.0 if bool(_smr_process_state["e105_cooling_loss"]) else 350.0
	var wgs_t := 340.0 if bool(_smr_process_state["e105_cooling_loss"]) else 210.0
	var purity_val: float = float(fault_state.get("purity_pct", 99.99))
	var h2_f: float = float(fault_state.get("h2_flow", 120000.0))
	var f_scale: float = h2_f / 120000.0 if h2_f > 0.0 else 0.0
	if lbls.has(0) and is_instance_valid(lbls[0]):
		lbls[0].text = "R-102 PRE-REF (%.0f Nm3/h Wet)\n490°C | %.0f bar | S/C %.1f" % [144200.0 * f_scale, pressure_bar + 2.0, sc_ratio]
	if lbls.has(1) and is_instance_valid(lbls[1]):
		lbls[1].text = "F-201 SMR (%.0f Nm3/h Wet)\n%.0f°C | %.0f bar | 72.0%% Dry H2" % [210800.0 * f_scale, reformer_temp_c, pressure_bar]
	if lbls.has(2) and is_instance_valid(lbls[2]):
		lbls[2].text = "E-105 WHB (%.0f Nm3/h Wet)\n%.0f°C | %.0f bar | Steam" % [210800.0 * f_scale, e105_t, maxf(pressure_bar - 2.0, 1.0)]
	if lbls.has(3) and is_instance_valid(lbls[3]):
		lbls[3].text = "R-301A/B WGS (%.0f Nm3/h Wet)\n%.0f°C | %.0f bar | 80.1%% Dry H2" % [210800.0 * f_scale, wgs_t, maxf(pressure_bar - 3.0, 1.0)]
	if lbls.has(4) and is_instance_valid(lbls[4]):
		lbls[4].text = "E-401 / V-401 (%.0f Nm3/h Dry)\n40°C | %.1f bar | 80.1%% H2" % [170200.0 * f_scale, maxf(pressure_bar - 3.5, 1.0)]
	if lbls.has(5) and is_instance_valid(lbls[5]):
		lbls[5].text = "C-501 CO2 CAP (%.0f Nm3/h Dry)\n42°C | %.1f bar | 97.6%% H2" % [139700.0 * f_scale, maxf(pressure_bar - 3.8, 1.0)]
	if lbls.has(6) and is_instance_valid(lbls[6]):
		lbls[6].text = "U-601 PSA (%.0f Nm3/h Dry)\n40°C | %.0f bar | %.2f%% H2" % [h2_f, maxf(pressure_bar - 4.0, 1.0), purity_val]
	if lbls.has(7) and is_instance_valid(lbls[7]):
		lbls[7].text = "K-701 COMP (%.0f Nm3/h Dry)\n40°C | 400 bar | %.2f%% H2" % [h2_f, purity_val]


# ---------------------------------------------------------------- Inter-Stage Pipes & Animated Moving Slugs

func _build_rack_pipe_route(waypoints: Array, stream_color: Color, pipe_steel: Material, flange_mat: Material, ft_mat: Material) -> void:
	for wi in range(waypoints.size() - 1):
		var a: Vector3 = waypoints[wi]
		var b: Vector3 = waypoints[wi + 1]
		var seg_len := a.distance_to(b)
		if seg_len < 0.02:
			continue
		var mid := (a + b) * 0.5
		var dx := absf(b.x - a.x)
		var dy := absf(b.y - a.y)
		var dz := absf(b.z - a.z)
		var rot := Vector3.ZERO
		if dx >= dy and dx >= dz:
			rot = Vector3(0.0, 0.0, 90.0)
		elif dz >= dx and dz >= dy:
			rot = Vector3(90.0, 0.0, 0.0)
		_add_cad_cyl(_bench_root, 0.042, 0.042, seg_len, mid, pipe_steel, rot)
		# Elbow joint sphere at intermediate corners
		if wi > 0:
			var elb_m := SphereMesh.new()
			elb_m.radius = 0.052
			elb_m.height = 0.104
			var elb := MeshInstance3D.new()
			elb.mesh = elb_m
			elb.position = a
			elb.material_override = flange_mat
			_bench_root.add_child(elb)

	# Flanged control valve station & FT collar on mid-rack segment
	if waypoints.size() >= 4:
		var mid_idx := waypoints.size() / 2
		var va: Vector3 = waypoints[mid_idx - 1]
		var vb: Vector3 = waypoints[mid_idx]
		var vmid := (va + vb) * 0.5
		_add_cad_box(_bench_root, Vector3(0.13, 0.11, 0.11), vmid, flange_mat)
		_add_cad_cyl(_bench_root, 0.016, 0.016, 0.16, vmid + Vector3(0.0, 0.12, 0.0), flange_mat)
		_add_cad_cyl(_bench_root, 0.060, 0.060, 0.07, vmid + Vector3(0.22, 0.0, 0.0), ft_mat, Vector3(0.0, 0.0, 90.0))

	# 6 Sleek Streamlined Flow Pulses moving inside the semi-transparent pipe
	for pi in range(6):
		var pulse_m := SphereMesh.new()
		pulse_m.radius = 0.025
		pulse_m.height = 0.050
		var pulse_inst := MeshInstance3D.new()
		pulse_inst.mesh = pulse_m
		var pm := StandardMaterial3D.new()
		pm.albedo_color = stream_color
		pm.emission_enabled = true
		pm.emission = stream_color
		pm.emission_energy_multiplier = 1.65
		pulse_inst.material_override = pm
		_bench_root.add_child(pulse_inst)
		_pipe_pulses.append({
			"mesh": pulse_inst,
			"waypoints": waypoints,
			"phase": float(pi) / 6.0,
		})


func _build_all_interstage_pipes_and_slugs() -> void:
	if _stage_vessels.size() < 2:
		return

	if _stage_vessels[0].get("is_chemical_plant", false):
		var pipe_steel := StandardMaterial3D.new()
		pipe_steel.albedo_color = Color(0.55, 0.62, 0.70, 0.42)
		pipe_steel.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		pipe_steel.metallic = 0.75
		pipe_steel.roughness = 0.22

		var flange_mat := StandardMaterial3D.new()
		flange_mat.albedo_color = Color(0.28, 0.34, 0.42)
		flange_mat.metallic = 0.88
		flange_mat.roughness = 0.28

		var ft_mat := StandardMaterial3D.new()
		ft_mat.albedo_color = Color(0.20, 0.85, 0.95)
		ft_mat.metallic = 0.70

		# 1. Pre-Reformed Feed: Unit 100 R-102 (-9.5, 0, 2.8) -> Unit 200 F-201 (-3.5, 0, 2.8) top inlet (490 C)
		_build_rack_pipe_route([
			Vector3(-8.50, 2.65, 2.80),
			Vector3(-6.40, 2.65, 2.80),
			Vector3(-6.40, 4.14, 2.80),
			Vector3(-4.70, 4.14, 2.80),
		], Color(0.95, 0.72, 0.25), pipe_steel, flange_mat, ft_mat)

		# 2. Hot Syngas Transfer: Unit 200 F-201 (-3.5, 0, 2.8) bottom -> Unit 300 E-105 (2.5, 0, 2.8) inlet (850 C)
		_build_rack_pipe_route([
			Vector3(-2.25, 0.42, 2.80),
			Vector3(-0.30, 0.42, 2.80),
			Vector3(-0.30, 1.18, 2.80),
			Vector3(1.40, 1.18, 2.80),
		], Color(1.0, 0.40, 0.12), pipe_steel, flange_mat, ft_mat)

		# 3. Cooled Syngas: Unit 300 E-105 (2.5, 0, 2.8) -> Overhead Rack Tier 1 -> Unit 400 WGS (8.5, 0, 2.8)
		_build_rack_pipe_route([
			Vector3(3.55, 1.18, 2.80),
			Vector3(3.55, 2.92, 2.80),
			Vector3(3.55, 2.92, 0.20),
			Vector3(7.85, 2.92, 0.20),
			Vector3(7.85, 2.92, 2.80),
			Vector3(7.85, 2.25, 2.80),
		], Color(0.95, 0.65, 0.14), pipe_steel, flange_mat, ft_mat)

		# 4. Shifted Gas Crossover: Unit 400 WGS (8.5, 0, 2.8) -> Rack Tier 1 -> Unit 500 E-401/V-401 (11.2, 0.6, -2.8)
		_build_rack_pipe_route([
			Vector3(9.12, 1.85, 2.80),
			Vector3(9.12, 2.96, 2.80),
			Vector3(9.12, 2.96, -0.20),
			Vector3(10.60, 2.96, -0.20),
			Vector3(10.60, 2.96, -2.80),
			Vector3(10.60, 2.25, -2.80),
		], Color(0.25, 0.85, 0.58), pipe_steel, flange_mat, ft_mat)

		# 5. Dry Shifted Gas: Unit 500 V-401 (11.2, 0.6, -2.8) -> Rack Tier 1 -> Unit 600 C-501 (5.5, 0.6, -2.8)
		_build_rack_pipe_route([
			Vector3(10.50, 2.55, -2.80),
			Vector3(10.50, 2.94, -2.80),
			Vector3(10.50, 2.94, -0.35),
			Vector3(4.95, 2.94, -0.35),
			Vector3(4.95, 2.94, -2.80),
			Vector3(4.95, 1.65, -2.80),
		], Color(0.20, 0.82, 0.72), pipe_steel, flange_mat, ft_mat)

		# 6. CO2-Lean Syngas: Unit 600 C-501 (5.5, 0.6, -2.8) -> Rack Tier 1 -> Unit 700 U-601 PSA (-0.5, 0.6, -2.8)
		_build_rack_pipe_route([
			Vector3(4.95, 3.95, -2.80),
			Vector3(4.95, 3.00, -0.20),
			Vector3(0.65, 3.00, -0.20),
			Vector3(0.65, 3.00, -2.80),
			Vector3(0.65, 1.75, -2.80),
		], Color(0.18, 0.88, 0.82), pipe_steel, flange_mat, ft_mat)

		# 7. PSA Tail Gas Recycle: Unit 700 V-601 (0.8, 0.6, -2.8) -> Rack Tier 2 -> Unit 200 F-201 Burners (-3.5, 0, 2.8)
		_build_rack_pipe_route([
			Vector3(0.80, 1.75, -2.80),
			Vector3(0.80, 3.60, -2.80),
			Vector3(0.80, 3.60, 0.25),
			Vector3(-3.50, 3.60, 0.25),
			Vector3(-3.50, 3.60, 1.75),
			Vector3(-3.50, 0.45, 1.75),
		], Color(0.92, 0.72, 0.22), pipe_steel, flange_mat, ft_mat)

		# 8. 99.99% H2 Product Header: Unit 700 U-601 (-0.5, 0.6, -2.8) -> Rack Tier 2 -> Unit 800 K-701 (-6.5, 0.6, -2.8)
		_build_rack_pipe_route([
			Vector3(-0.80, 2.95, -2.80),
			Vector3(-0.80, 3.68, -2.80),
			Vector3(-0.80, 3.68, -0.25),
			Vector3(-5.50, 3.68, -0.25),
			Vector3(-5.50, 3.68, -2.80),
			Vector3(-5.50, 1.45, -2.80),
		], Color(0.22, 0.90, 1.0), pipe_steel, flange_mat, ft_mat)
		return

	var transitions: Array = [
		{"from": 0, "to": 1, "t0": 1.2, "t1": 2.0, "color": Color(0.29, 0.20, 0.10), "is_chute": true},
		{"from": 1, "to": 2, "t0": 15.0, "t1": 16.5, "color": Color(0.24, 0.16, 0.08), "is_chute": false},
		{"from": 2, "to": 3, "t0": 31.0, "t1": 32.3, "color": Color(0.60, 0.42, 0.18), "is_chute": false},
		{"from": 3, "to": 4, "t0": 33.5, "t1": 34.2, "color": Color(0.92, 0.75, 0.25), "is_chute": false},
		{"from": 4, "to": 5, "t0": 35.6, "t1": 36.3, "color": Color(0.95, 0.98, 1.0), "is_chute": false},
	]

	for tr in transitions:
		var i_from: int = tr.from
		var i_to: int = tr.to
		if i_from >= _stage_vessels.size() or i_to >= _stage_vessels.size():
			continue

		var p1: Vector3 = _stage_vessels[i_from].root.position
		var p2: Vector3 = _stage_vessels[i_to].root.position

		if tr.is_chute:
			# Chute 0 -> 1 already constructed inside _build_dry_biomass_hopper_mill
			# Add a moving slug along the chute
			var slug_m := BoxMesh.new()
			slug_m.size = Vector3(0.20, 0.06, 0.14)
			var slug_inst := MeshInstance3D.new()
			slug_inst.name = "TransferSlugMesh"
			slug_inst.mesh = slug_m
			var s_mat := StandardMaterial3D.new()
			s_mat.albedo_color = tr.color
			slug_inst.material_override = s_mat
			slug_inst.visible = false
			_bench_root.add_child(slug_inst)

			_transfer_slugs.append({
				"mesh": slug_inst,
				"from_pos": p1 + Vector3(0.25, 1.15, 0.0),
				"to_pos": p2 + Vector3(-0.25, 0.65, 0.0),
				"t_start": tr.t0,
				"t_end": tr.t1,
			})
		else:
			# Horizontal transparent interstage pipe
			var span := p2.x - p1.x
			var pipe_mesh := CylinderMesh.new()
			pipe_mesh.top_radius = 0.040
			pipe_mesh.bottom_radius = 0.040
			pipe_mesh.height = span - VESSEL_RADIUS * 1.35
			var pipe := MeshInstance3D.new()
			pipe.mesh = pipe_mesh
			pipe.rotation_degrees = Vector3(0.0, 0.0, 90.0)
			pipe.position = Vector3((p1.x + p2.x) * 0.5, 1.25, 0.0)

			# Glass/acrylic clear pipe material
			var p_mat := StandardMaterial3D.new()
			p_mat.albedo_color = Color(0.75, 0.88, 0.96, 0.35)
			p_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			p_mat.roughness = 0.10
			pipe.material_override = p_mat
			_bench_root.add_child(pipe)
			_flow_chevrons.append(p_mat)

			# 3D Moving Transfer Slug inside the pipe
			var slug_mesh := CylinderMesh.new()
			slug_mesh.top_radius = 0.035
			slug_mesh.bottom_radius = 0.035
			slug_mesh.height = 0.32
			var slug_inst := MeshInstance3D.new()
			slug_inst.name = "TransferSlugMesh"
			slug_inst.mesh = slug_mesh
			slug_inst.rotation_degrees = Vector3(0.0, 0.0, 90.0)
			var s_mat := StandardMaterial3D.new()
			s_mat.albedo_color = tr.color
			s_mat.roughness = 0.35
			slug_inst.material_override = s_mat
			slug_inst.visible = false
			_bench_root.add_child(slug_inst)

			_transfer_slugs.append({
				"mesh": slug_inst,
				"from_pos": Vector3(p1.x + VESSEL_RADIUS * 0.75, 1.25, 0.0),
				"to_pos": Vector3(p2.x - VESSEL_RADIUS * 0.75, 1.25, 0.0),
				"t_start": tr.t0,
				"t_end": tr.t1,
			})


# ---------------------------------------------------------------- Procedural 3D Solid Biomass Generators

func _build_dry_biomass_hopper_mill(stage_node: Node3D, op_data: Dictionary) -> Dictionary:
	var dark_kelp_mat := StandardMaterial3D.new()
	dark_kelp_mat.albedo_color = Color(0.24, 0.18, 0.08)
	dark_kelp_mat.roughness = 0.90
	dark_kelp_mat.metallic = 0.05

	var flake_mat := StandardMaterial3D.new()
	flake_mat.albedo_color = Color(0.29, 0.20, 0.10)
	flake_mat.roughness = 0.85

	var steel_mat := StandardMaterial3D.new()
	steel_mat.albedo_color = Color(0.70, 0.74, 0.80)
	steel_mat.metallic = 0.92
	steel_mat.roughness = 0.22

	# 1. Digital Analytical Balance Base
	var scale_mesh := BoxMesh.new()
	scale_mesh.size = Vector3(1.15, 0.18, 1.15)
	var scale_inst := MeshInstance3D.new()
	scale_inst.mesh = scale_mesh
	scale_inst.position = Vector3(0.0, 0.09, 0.0)
	var sc_mat := StandardMaterial3D.new()
	sc_mat.albedo_color = Color(0.12, 0.14, 0.18)
	sc_mat.metallic = 0.65
	sc_mat.roughness = 0.35
	scale_inst.material_override = sc_mat
	stage_node.add_child(scale_inst)

	# Weighing pan
	var pan_mesh := CylinderMesh.new()
	pan_mesh.top_radius = 0.42
	pan_mesh.bottom_radius = 0.42
	pan_mesh.height = 0.03
	var pan_inst := MeshInstance3D.new()
	pan_inst.mesh = pan_mesh
	pan_inst.position = Vector3(0.0, 0.19, 0.0)
	pan_inst.material_override = steel_mat
	stage_node.add_child(pan_inst)

	# Digital LCD Readout Screen on scale front
	var lcd_mesh := BoxMesh.new()
	lcd_mesh.size = Vector3(0.35, 0.09, 0.02)
	var lcd_inst := MeshInstance3D.new()
	lcd_inst.mesh = lcd_mesh
	lcd_inst.position = Vector3(0.0, 0.10, 0.58)
	var lcd_mat := StandardMaterial3D.new()
	lcd_mat.albedo_color = Color(0.05, 0.30, 0.50)
	lcd_mat.emission_enabled = true
	lcd_mat.emission = Color(0.15, 0.65, 0.95)
	lcd_mat.emission_energy_multiplier = 0.9
	lcd_inst.material_override = lcd_mat
	stage_node.add_child(lcd_inst)

	var lcd_lbl := Label3D.new()
	lcd_lbl.text = "15.000 g"
	lcd_lbl.position = Vector3(0.0, 0.10, 0.60)
	lcd_lbl.font_size = 18
	lcd_lbl.pixel_size = 0.0025
	lcd_lbl.modulate = Color(0.4, 0.95, 1.0)
	stage_node.add_child(lcd_lbl)

	# 2. Conical Mound of Dry Milled Seaweed Flakes (15.0 g)
	var pile_cone := CylinderMesh.new()
	pile_cone.top_radius = 0.04
	pile_cone.bottom_radius = 0.34
	pile_cone.height = 0.22
	var pile_mesh := MeshInstance3D.new()
	pile_mesh.name = "DryMilledSeaweedPile"
	pile_mesh.mesh = pile_cone
	pile_mesh.position = Vector3(0.0, 0.31, 0.0)
	pile_mesh.material_override = flake_mat
	stage_node.add_child(pile_mesh)

	# Single-Draw-Call MultiMesh for 85 flakes on/around the conical pile
	var flake_f := BoxMesh.new()
	flake_f.size = Vector3(0.065, 0.016, 0.052)
	var dry_mm := MultiMesh.new()
	dry_mm.transform_format = MultiMesh.TRANSFORM_3D
	dry_mm.use_colors = true
	dry_mm.mesh = flake_f
	dry_mm.instance_count = 85
	for i in range(85):
		var r := randf_range(0.02, 0.32)
		var theta := randf_range(0.0, TAU)
		var py := 0.22 * (1.0 - (r / 0.35)) + randf_range(-0.02, 0.03)
		var t_pos := Vector3(r * cos(theta), py - 0.11, r * sin(theta))
		var b_rot := Basis.from_euler(Vector3(randf_range(-0.5, 0.5), randf_range(0.0, TAU), randf_range(-0.5, 0.5)))
		var s_mult := randf_range(0.75, 1.25)
		b_rot = b_rot.scaled(Vector3(s_mult, s_mult, s_mult))
		dry_mm.set_instance_transform(i, Transform3D(b_rot, t_pos))
		var cv := randf_range(0.85, 1.15)
		dry_mm.set_instance_color(i, Color(0.24 * cv, 0.18 * cv, 0.10 * cv))

	var dry_mmi := MultiMeshInstance3D.new()
	dry_mmi.name = "DryFlakesMultiMesh"
	dry_mmi.multimesh = dry_mm
	dry_mmi.material_override = flake_mat
	pile_mesh.add_child(dry_mmi)

	# 3. Transparent Upper Hopper Funnel holding Whole Dried Fronds
	var funnel_mesh := CylinderMesh.new()
	funnel_mesh.top_radius = 0.48
	funnel_mesh.bottom_radius = 0.16
	funnel_mesh.height = 0.95
	var funnel := MeshInstance3D.new()
	funnel.mesh = funnel_mesh
	funnel.position = Vector3(0.0, 1.95, 0.0)
	var f_mat := StandardMaterial3D.new()
	f_mat.albedo_color = Color(0.85, 0.92, 0.98, 0.22)
	f_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	f_mat.roughness = 0.10
	f_mat.rim_enabled = true
	f_mat.rim = 0.9
	funnel.material_override = f_mat
	stage_node.add_child(funnel)

	# 12 Twisted 3D Dry Kelp Frond Meshes in the hopper
	var fronds_group := Node3D.new()
	stage_node.add_child(fronds_group)
	for fi in range(12):
		var frond := BoxMesh.new()
		frond.size = Vector3(randf_range(0.07, 0.11), randf_range(0.38, 0.52), randf_range(0.015, 0.025))
		var fr_inst := MeshInstance3D.new()
		fr_inst.mesh = frond
		var fa := float(fi) * (TAU / 12.0)
		var fr_r := randf_range(0.06, 0.24)
		fr_inst.position = Vector3(fr_r * cos(fa), 1.95 + randf_range(-0.15, 0.20), fr_r * sin(fa))
		fr_inst.rotation_degrees = Vector3(randf_range(-25.0, 25.0), rad_to_deg(fa) + randf_range(-20.0, 20.0), randf_range(15.0, 35.0))
		fr_inst.material_override = dark_kelp_mat
		fronds_group.add_child(fr_inst)

	# 4. Central Grinding Chamber with Rotary Grinder Blades
	var mill_chamber := CylinderMesh.new()
	mill_chamber.top_radius = 0.20
	mill_chamber.bottom_radius = 0.18
	mill_chamber.height = 0.35
	var mc_inst := MeshInstance3D.new()
	mc_inst.mesh = mill_chamber
	mc_inst.position = Vector3(0.0, 1.30, 0.0)
	mc_inst.material_override = steel_mat
	stage_node.add_child(mc_inst)

	var blades_node := Node3D.new()
	blades_node.position = Vector3(0.0, 1.30, 0.0)
	stage_node.add_child(blades_node)
	for ba in [0.0, 90.0, 180.0, 270.0]:
		var bm := BoxMesh.new()
		bm.size = Vector3(0.16, 0.02, 0.03)
		var bmi := MeshInstance3D.new()
		bmi.mesh = bm
		bmi.position = Vector3(0.08, 0.0, 0.0).rotated(Vector3.UP, deg_to_rad(ba))
		bmi.rotation_degrees = Vector3(0.0, ba, 0.0)
		bmi.material_override = steel_mat
		blades_node.add_child(bmi)

	# 5. Angled Solid Transfer Chute to Stage 1 (Acid Tank)
	var chute_mesh := BoxMesh.new()
	chute_mesh.size = Vector3(0.14, 0.03, 1.35)
	var chute_inst := MeshInstance3D.new()
	chute_inst.mesh = chute_mesh
	chute_inst.rotation_degrees = Vector3(28.0, 90.0, 0.0)
	chute_inst.position = Vector3(0.68, 0.85, 0.0)
	chute_inst.material_override = steel_mat
	stage_node.add_child(chute_inst)

	# Flakes sliding along chute
	var chute_flakes: Array = []
	for ci in range(12):
		var cf := BoxMesh.new()
		var csz := randf_range(0.045, 0.075)
		cf.size = Vector3(csz, 0.015, csz * 0.7)
		var cfi := MeshInstance3D.new()
		cfi.mesh = cf
		var frac := float(ci) / 12.0
		cfi.position = Vector3(lerpf(0.15, 1.25, frac), lerpf(1.15, 0.55, frac), 0.0)
		cfi.material_override = flake_mat
		cfi.visible = false
		stage_node.add_child(cfi)
		chute_flakes.append(cfi)

	# 6. Prominent Floating 3D Label directly over the 15.0 g Dry Milled Pile
	var pile_lbl := Label3D.new()
	pile_lbl.name = "DryBiomassLabel3D"
	pile_lbl.text = "RAW BIOMASS: 15.0 g Dry Milled Saccharina latissima (Sugar Kelp)"
	pile_lbl.position = Vector3(0.0, 2.75, 0.0)
	pile_lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	pile_lbl.font_size = 28
	pile_lbl.pixel_size = 0.0035
	pile_lbl.modulate = Color(0.98, 0.88, 0.55)
	pile_lbl.outline_modulate = Color(0.05, 0.05, 0.08, 0.95)
	pile_lbl.outline_render_priority = 1
	stage_node.add_child(pile_lbl)

	return {
		"mill_blades": blades_node,
		"pile": pile_mesh,
		"fronds_group": fronds_group,
		"lcd_lbl": lcd_lbl,
		"chute_flakes": chute_flakes,
	}


func _build_solid_kelp_flakes_in_vessel(stage_node: Node3D, count: int = 120) -> MultiMeshInstance3D:
	var flake_box := BoxMesh.new()
	flake_box.size = Vector3(0.085, 0.025, 0.070)

	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = flake_box
	mm.instance_count = count

	var flake_mat := StandardMaterial3D.new()
	flake_mat.albedo_color = Color(0.29, 0.21, 0.12)
	flake_mat.roughness = 0.88
	flake_mat.metallic = 0.05

	for i in range(count):
		var r := randf_range(0.08, VESSEL_RADIUS * 0.82)
		var angle := randf_range(0.0, TAU)
		var y := randf_range(-0.45, 0.45)
		var basis := Basis.from_euler(Vector3(randf_range(-0.8, 0.8), randf_range(0.0, TAU), randf_range(-0.8, 0.8)))
		var sz_x := randf_range(0.7, 1.3)
		var sz_y := randf_range(0.6, 1.4)
		var sz_z := randf_range(0.7, 1.3)
		basis = basis.scaled(Vector3(sz_x, sz_y, sz_z))
		mm.set_instance_transform(i, Transform3D(basis, Vector3(r * cos(angle), y, r * sin(angle))))
		var shade := randf_range(0.82, 1.18)
		mm.set_instance_color(i, Color(0.29 * shade, 0.21 * shade, 0.12 * shade))

	var mmi := MultiMeshInstance3D.new()
	mmi.name = "SolidKelpFlakesGroup"
	mmi.position = Vector3(0.0, 0.65, 0.0)
	mmi.multimesh = mm
	mmi.material_override = flake_mat
	stage_node.add_child(mmi)

	return mmi


func _build_centrifuge_pellet(stage_node: Node3D) -> MeshInstance3D:
	var p_mesh := CylinderMesh.new()
	p_mesh.top_radius = VESSEL_RADIUS * 0.35
	p_mesh.bottom_radius = VESSEL_RADIUS * 0.22
	p_mesh.height = 0.12
	var pellet := MeshInstance3D.new()
	pellet.name = "CentrifugeSolidPellet"
	pellet.mesh = p_mesh
	pellet.position = Vector3(0.0, 0.48, 0.0)
	var pel_mat := StandardMaterial3D.new()
	pel_mat.albedo_color = Color(0.23, 0.15, 0.08)
	pel_mat.roughness = 0.90
	pellet.material_override = pel_mat
	stage_node.add_child(pellet)
	return pellet


func _build_fibrous_alginate_clot(stage_node: Node3D) -> Dictionary:
	var clot_mesh := MeshInstance3D.new()
	clot_mesh.name = "PrecipitatedAlginateClot"
	clot_mesh.position = Vector3(0.0, 0.60, 0.0)

	var cl_mat := StandardMaterial3D.new()
	cl_mat.albedo_color = Color(0.96, 0.95, 0.92)
	cl_mat.roughness = 0.70
	cl_mat.emission_enabled = true
	cl_mat.emission = Color(0.85, 0.85, 0.80)
	cl_mat.emission_energy_multiplier = 0.25

	var core := SphereMesh.new()
	core.radius = 0.22
	core.height = 0.36
	clot_mesh.mesh = core
	clot_mesh.material_override = cl_mat
	stage_node.add_child(clot_mesh)

	for i in range(8):
		var ring := TorusMesh.new()
		ring.inner_radius = randf_range(0.12, 0.18)
		ring.outer_radius = ring.inner_radius + randf_range(0.02, 0.035)
		var rm := MeshInstance3D.new()
		rm.mesh = ring
		rm.rotation = Vector3(randf_range(0, TAU), randf_range(0, TAU), randf_range(0, TAU))
		rm.material_override = cl_mat
		clot_mesh.add_child(rm)

	# Side drying dish with milled sodium alginate powder
	var dish_root := Node3D.new()
	stage_node.add_child(dish_root)

	var dish := CylinderMesh.new()
	dish.top_radius = 0.22
	dish.bottom_radius = 0.22
	dish.height = 0.04
	var dm := MeshInstance3D.new()
	dm.mesh = dish
	dm.position = Vector3(0.95, 0.02, 0.25)
	var dmat := StandardMaterial3D.new()
	dmat.albedo_color = Color(0.85, 0.88, 0.92)
	dm.material_override = dmat
	dish_root.add_child(dm)

	var powder := SphereMesh.new()
	powder.radius = 0.16
	powder.height = 0.10
	var pm := MeshInstance3D.new()
	pm.name = "DryAlginatePowderMesh"
	pm.mesh = powder
	pm.position = Vector3(0.95, 0.06, 0.25)
	pm.material_override = cl_mat
	dish_root.add_child(pm)

	var d_lbl := Label3D.new()
	d_lbl.text = "Alginate Powder (91.5% Purity)"
	d_lbl.position = Vector3(0.95, 0.24, 0.25)
	d_lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	d_lbl.font_size = 18
	d_lbl.pixel_size = 0.0025
	d_lbl.modulate = Color(0.9, 0.95, 1.0)
	dish_root.add_child(d_lbl)

	return {
		"clot": clot_mesh,
		"dish": dish_root,
	}


func _build_tensile_tester_rig(stage_node: Node3D) -> void:
	var steel_mat := StandardMaterial3D.new()
	steel_mat.albedo_color = Color(0.72, 0.75, 0.82)
	steel_mat.metallic = 0.95
	steel_mat.roughness = 0.20

	var frame_pos := Vector3(1.15, 0.0, 0.0)

	var b_mesh := BoxMesh.new()
	b_mesh.size = Vector3(0.55, 0.08, 0.45)
	var bi := MeshInstance3D.new()
	bi.mesh = b_mesh
	bi.position = frame_pos + Vector3(0.0, 0.04, 0.0)
	bi.material_override = steel_mat
	stage_node.add_child(bi)

	for cx in [-0.20, 0.20]:
		var col_mesh := CylinderMesh.new()
		col_mesh.top_radius = 0.025
		col_mesh.bottom_radius = 0.025
		col_mesh.height = 1.35
		var ci := MeshInstance3D.new()
		ci.mesh = col_mesh
		ci.position = frame_pos + Vector3(cx, 0.72, 0.0)
		ci.material_override = steel_mat
		stage_node.add_child(ci)

	var cr_mesh := BoxMesh.new()
	cr_mesh.size = Vector3(0.48, 0.08, 0.12)
	var cri := MeshInstance3D.new()
	cri.mesh = cr_mesh
	cri.position = frame_pos + Vector3(0.0, 1.15, 0.0)
	cri.material_override = steel_mat
	stage_node.add_child(cri)

	var tf_mesh := CylinderMesh.new()
	tf_mesh.top_radius = 0.008
	tf_mesh.bottom_radius = 0.008
	tf_mesh.height = 0.85
	var tfi := MeshInstance3D.new()
	tfi.name = "TensileTestFibre"
	tfi.mesh = tf_mesh
	tfi.position = frame_pos + Vector3(0.0, 0.65, 0.0)
	var f_mat := StandardMaterial3D.new()
	f_mat.albedo_color = Color(0.95, 0.98, 1.0)
	f_mat.roughness = 0.4
	tfi.material_override = f_mat
	stage_node.add_child(tfi)

	var t_lbl := Label3D.new()
	t_lbl.text = "Instron Tensile Frame (29.3 - 43.1 MPa)"
	t_lbl.position = frame_pos + Vector3(0.0, 1.48, 0.0)
	t_lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	t_lbl.font_size = 18
	t_lbl.pixel_size = 0.0025
	t_lbl.modulate = Color(0.95, 0.85, 0.4)
	stage_node.add_child(t_lbl)


# ---------------------------------------------------------------- Dynamics & Batch Continuity

func _create_fracture_particle_emitter() -> GPUParticles3D:
	var gp := GPUParticles3D.new()
	gp.amount = 60
	gp.lifetime = 0.65
	gp.one_shot = true
	gp.emitting = false
	gp.explosiveness = 0.95

	var pmat := ParticleProcessMaterial.new()
	pmat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pmat.emission_sphere_radius = 0.08
	pmat.initial_velocity_min = 1.8
	pmat.initial_velocity_max = 3.6
	pmat.gravity = Vector3(0, -4.5, 0)
	pmat.scale_min = 0.02
	pmat.scale_max = 0.05
	gp.process_material = pmat

	var p_mesh := BoxMesh.new()
	p_mesh.size = Vector3(0.03, 0.03, 0.03)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(1.0, 0.2, 0.2)
	mat.emission_enabled = true
	mat.emission = Color(1.0, 0.2, 0.2)
	mat.emission_energy_multiplier = 2.0
	p_mesh.material = mat
	gp.draw_pass_1 = p_mesh

	return gp


func update_at_time(t: float, telemetry_dict: Dictionary, schema: Dictionary = {}) -> void:
	if _stage_vessels.is_empty():
		return
	_current_sim_time = t
	update_batch_continuity(t)


func update_batch_continuity(t: float) -> void:
	# -------------------------------------------------------------------------
	# 1. Update Inter-stage Transfer Slugs in connecting pipes
	# -------------------------------------------------------------------------
	for slug_info in _transfer_slugs:
		var s_mesh: MeshInstance3D = slug_info.mesh
		var t0: float = slug_info.t_start
		var t1: float = slug_info.t_end
		if t >= t0 and t <= t1:
			var frac := (t - t0) / maxf(t1 - t0, 0.001)
			s_mesh.visible = true
			s_mesh.position = slug_info.from_pos.lerp(slug_info.to_pos, frac)
		else:
			s_mesh.visible = false

	# -------------------------------------------------------------------------
	# 2. Stage 0: Dry Milling & Weighing (0.0 -> 2.0 h)
	# -------------------------------------------------------------------------
	if _stage_vessels.size() > 0:
		var sv0: Dictionary = _stage_vessels[0]
		var pile: MeshInstance3D = sv0.pile
		var fronds: Node3D = sv0.fronds_group
		var lcd: Label3D = sv0.lcd_lbl
		var c_flakes: Array = sv0.chute_flakes

		if t <= 1.2:
			# Milling and weighing 15.0g
			sv0.is_active = true
			if pile != null:
				pile.visible = true
				var p_scale := clampf(0.1 + (t / 1.2) * 0.9, 0.1, 1.0)
				pile.scale = Vector3(p_scale, p_scale, p_scale)
			if fronds != null:
				fronds.visible = true
				var f_scale := clampf(1.0 - (t / 1.2) * 0.7, 0.3, 1.0)
				fronds.scale = Vector3(f_scale, f_scale, f_scale)
			if lcd != null:
				lcd.text = "%.3f g" % (clampf(t / 1.2, 0.0, 1.0) * 15.0)
			for cf in c_flakes:
				cf.visible = false
		elif t <= 2.0:
			# Transferring batch down chute into Stage 1
			sv0.is_active = true
			var drain := clampf((t - 1.2) / 0.8, 0.0, 1.0)
			if pile != null:
				var p_scale := clampf(1.0 - drain, 0.0, 1.0)
				pile.scale = Vector3(p_scale, p_scale, p_scale)
				pile.visible = (p_scale > 0.01)
			if fronds != null:
				fronds.visible = false
			if lcd != null:
				lcd.text = "%.3f g" % (maxf(1.0 - drain, 0.0) * 15.0)
			for cf in c_flakes:
				cf.visible = true
		else:
			# Past stage: Stage 0 is completely empty
			sv0.is_active = false
			if pile != null:
				pile.visible = false
			if fronds != null:
				fronds.visible = false
			if lcd != null:
				lcd.text = "0.000 g"
			for cf in c_flakes:
				cf.visible = false

	# -------------------------------------------------------------------------
	# 3. Stage 1: Acid Demineralisation Wash (2.0 -> 16.0 h)
	# -------------------------------------------------------------------------
	if _stage_vessels.size() > 1:
		var sv1: Dictionary = _stage_vessels[1]
		var flakes1: Node3D = sv1.flakes_group
		var liq1: MeshInstance3D = sv1.liquid
		var men1: MeshInstance3D = sv1.meniscus

		if t < 1.2:
			# Future stage: 100% empty
			sv1.is_active = false
			if flakes1 != null: flakes1.visible = false
			if liq1 != null: liq1.visible = false
			if men1 != null: men1.visible = false
		elif t <= 2.5:
			# Receiving dry flakes from Stage 0 and filling with 4% citric acid
			sv1.is_active = true
			if flakes1 != null:
				flakes1.visible = true
				flakes1.scale = Vector3(1.0, 1.0, 1.0)
			if t >= 2.0 and liq1 != null:
				liq1.visible = true
				var fill := clampf((t - 2.0) / 0.5, 0.1, 1.0)
				var h := VESSEL_HEIGHT * 0.85 * fill
				liq1.mesh.height = h
				liq1.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				if men1 != null:
					men1.visible = true
					men1.position.y = FILL_BASE_Y + h
		elif t <= 15.0:
			# Active demineralisation: solids swirling in acid
			sv1.is_active = true
			if flakes1 != null:
				flakes1.visible = true
				flakes1.scale = Vector3(1.0, 1.0, 1.0)
			if liq1 != null:
				liq1.visible = true
				var h := VESSEL_HEIGHT * 0.85
				liq1.mesh.height = h
				liq1.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				if men1 != null:
					men1.visible = true
					men1.position.y = FILL_BASE_Y + h
		elif t <= 16.5:
			# Draining spent acid and transferring wet kelp pulp to Stage 2
			sv1.is_active = true
			var drain := clampf((t - 15.0) / 1.5, 0.0, 1.0)
			if liq1 != null:
				var h := VESSEL_HEIGHT * 0.85 * maxf(1.0 - drain, 0.02)
				liq1.mesh.height = h
				liq1.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				liq1.visible = (drain < 0.95)
				if men1 != null:
					men1.visible = (drain < 0.95)
					men1.position.y = FILL_BASE_Y + h
			if flakes1 != null:
				var f_scale := clampf(1.0 - drain, 0.0, 1.0)
				flakes1.scale = Vector3(f_scale, f_scale, f_scale)
				flakes1.visible = (f_scale > 0.05)
		else:
			# Past stage: Tank 1 is 100% empty
			sv1.is_active = false
			if flakes1 != null: flakes1.visible = false
			if liq1 != null: liq1.visible = false
			if men1 != null: men1.visible = false

	# -------------------------------------------------------------------------
	# 4. Stage 2: Alkaline Extraction & Solubilisation (16.0 -> 32.0 h)
	# -------------------------------------------------------------------------
	if _stage_vessels.size() > 2:
		var sv2: Dictionary = _stage_vessels[2]
		var flakes2: Node3D = sv2.flakes_group
		var liq2: MeshInstance3D = sv2.liquid
		var men2: MeshInstance3D = sv2.meniscus
		var lmat2: StandardMaterial3D = sv2.liquid_mat

		if t < 15.5:
			# Future stage: 100% empty
			sv2.is_active = false
			if flakes2 != null: flakes2.visible = false
			if liq2 != null: liq2.visible = false
			if men2 != null: men2.visible = false
		elif t <= 17.0:
			# Receiving wet pulp from Stage 1 and filling with 2% Na2CO3
			sv2.is_active = true
			if flakes2 != null:
				flakes2.visible = true
				flakes2.scale = Vector3(1.0, 1.0, 1.0)
			if liq2 != null:
				liq2.visible = true
				var fill := clampf((t - 15.5) / 1.5, 0.1, 1.0)
				var h := VESSEL_HEIGHT * 0.90 * fill
				liq2.mesh.height = h
				liq2.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				if men2 != null:
					men2.visible = true
					men2.position.y = FILL_BASE_Y + h
		elif t <= 31.0:
			# Active extraction: flakes dissolve by 75%, liquid thickens into amber hydrogel
			sv2.is_active = true
			var prog := (t - 17.0) / 14.0
			if flakes2 != null:
				flakes2.visible = true
				var f_scale := 1.0 - (0.75 * prog)
				flakes2.scale = Vector3(f_scale, f_scale, f_scale)
			if liq2 != null:
				liq2.visible = true
				var h := VESSEL_HEIGHT * 0.90
				liq2.mesh.height = h
				liq2.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				if lmat2 != null:
					var dark_green := Color(0.06, 0.35, 0.22)
					var amber_gel := Color(0.72, 0.45, 0.12)
					lmat2.albedo_color = dark_green.lerp(amber_gel, prog)
				if men2 != null:
					men2.visible = true
					men2.position.y = FILL_BASE_Y + h
		elif t <= 32.3:
			# Transferring thick amber slurry into Stage 3 Centrifuge
			sv2.is_active = true
			var drain := clampf((t - 31.0) / 1.3, 0.0, 1.0)
			if liq2 != null:
				var h := VESSEL_HEIGHT * 0.90 * maxf(1.0 - drain, 0.02)
				liq2.mesh.height = h
				liq2.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				liq2.visible = (drain < 0.95)
				if men2 != null:
					men2.visible = (drain < 0.95)
					men2.position.y = FILL_BASE_Y + h
			if flakes2 != null:
				var f_scale := clampf(0.25 * (1.0 - drain), 0.0, 0.25)
				flakes2.scale = Vector3(f_scale, f_scale, f_scale)
				flakes2.visible = (drain < 0.95)
		else:
			# Past stage: Tank 2 is 100% empty
			sv2.is_active = false
			if flakes2 != null: flakes2.visible = false
			if liq2 != null: liq2.visible = false
			if men2 != null: men2.visible = false

	# -------------------------------------------------------------------------
	# 5. Stage 3: Centrifugation & pH 7.0 Neutralisation (32.0 -> 34.0 h)
	# -------------------------------------------------------------------------
	if _stage_vessels.size() > 3:
		var sv3: Dictionary = _stage_vessels[3]
		var liq3: MeshInstance3D = sv3.liquid
		var pellet3: MeshInstance3D = sv3.pellet
		var halo3: MeshInstance3D = sv3.ph_halo
		var d_lbl3: Label3D = sv3.discard_label

		if t < 31.5:
			# Future stage: 100% empty
			sv3.is_active = false
			if liq3 != null: liq3.visible = false
			if pellet3 != null: pellet3.visible = false
			if halo3 != null: halo3.visible = false
			if d_lbl3 != null: d_lbl3.visible = false
		elif t <= 33.5:
			# Active centrifugation at 4500 rpm: solid pellet compacts, liquid clarifies, pH 12 -> 7
			sv3.is_active = true
			if liq3 != null:
				liq3.visible = true
			if pellet3 != null:
				pellet3.visible = true
				var pel_prog := clampf((t - 32.0) / 1.5, 0.05, 1.0)
				var pel_h := 0.03 + 0.19 * pel_prog
				pellet3.mesh.height = pel_h
				pellet3.position.y = 0.44 + pel_h * 0.5
			if halo3 != null:
				halo3.visible = true
				var halo_mat: StandardMaterial3D = halo3.material_override as StandardMaterial3D
				if halo_mat != null:
					var purple := Color(0.72, 0.12, 0.85)
					var green := Color(0.12, 0.85, 0.42)
					var prog := clampf((t - 32.0) / 1.5, 0.0, 1.0)
					var cur_col := purple.lerp(green, prog)
					halo_mat.albedo_color = cur_col
					halo_mat.emission = cur_col
			if d_lbl3 != null:
				d_lbl3.visible = false
		elif t <= 34.2:
			# Transferring golden supernatant to Stage 4 (Phase split: pellet stays behind!)
			sv3.is_active = true
			var drain := clampf((t - 33.5) / 0.7, 0.0, 1.0)
			if liq3 != null:
				var h := 0.9 * maxf(1.0 - drain, 0.01)
				liq3.mesh.height = h
				liq3.position = Vector3(0.0, 1.15 - (0.9 - h) * 0.5, 0.0)
				liq3.visible = (drain < 0.98)
			if pellet3 != null:
				# RETAINED WASTE PELLET PERMANENTLY VISIBLE
				pellet3.visible = true
			if halo3 != null:
				halo3.visible = (drain < 0.9)
			if d_lbl3 != null:
				d_lbl3.visible = true
		else:
			# Past stage: liquid decanted, BUT retained dark-brown waste pellet stays visible!
			sv3.is_active = false
			if liq3 != null: liq3.visible = false
			if halo3 != null: halo3.visible = false
			if pellet3 != null:
				pellet3.visible = true
			if d_lbl3 != null:
				d_lbl3.visible = true

	# -------------------------------------------------------------------------
	# 6. Stage 4: Chilled Ethanol Precipitation (34.0 -> 36.0 h)
	# -------------------------------------------------------------------------
	if _stage_vessels.size() > 4:
		var sv4: Dictionary = _stage_vessels[4]
		var liq4: MeshInstance3D = sv4.liquid
		var clot4: MeshInstance3D = sv4.floc
		var dish4: Node3D = sv4.powder_dish

		if t < 33.5:
			# Future stage: 100% empty
			sv4.is_active = false
			if liq4 != null: liq4.visible = false
			if clot4 != null: clot4.visible = false
			if dish4 != null: dish4.visible = false
		elif t <= 34.5:
			# Supernatant arrives from Stage 3 and chilled ethanol fills tank
			sv4.is_active = true
			if liq4 != null:
				liq4.visible = true
			if clot4 != null:
				clot4.visible = false
			if dish4 != null:
				dish4.visible = false
		elif t <= 35.6:
			# Antisolvent precipitation: white fibrous clot nucleates and expands (0.0 -> 1.0)
			sv4.is_active = true
			if liq4 != null:
				liq4.visible = true
			if clot4 != null:
				clot4.visible = true
				var c_prog := clampf((t - 34.5) / 1.1, 0.05, 1.0)
				clot4.scale = Vector3(c_prog, c_prog, c_prog)
			if dish4 != null:
				dish4.visible = true
		elif t <= 36.3:
			# Transferring white clot / spinning dope into Stage 5
			sv4.is_active = true
			var drain := clampf((t - 35.6) / 0.7, 0.0, 1.0)
			if liq4 != null:
				liq4.visible = (drain < 0.95)
			if clot4 != null:
				var c_scale := clampf(1.0 - drain, 0.0, 1.0)
				clot4.scale = Vector3(c_scale, c_scale, c_scale)
				clot4.visible = (c_scale > 0.05)
			if dish4 != null:
				dish4.visible = true
		else:
			# Past stage: Tank 4 is empty (powder dish remains as display)
			sv4.is_active = false
			if liq4 != null: liq4.visible = false
			if clot4 != null: clot4.visible = false
			if dish4 != null: dish4.visible = true

	# -------------------------------------------------------------------------
	# 7. Stage 5: Wet Spinning & Tensile Rig (36.0 -> 40.0 h)
	# -------------------------------------------------------------------------
	if _stage_vessels.size() > 5:
		var sv5: Dictionary = _stage_vessels[5]
		var liq5: MeshInstance3D = sv5.liquid

		if t < 35.8:
			# Future stage: 100% empty
			sv5.is_active = false
			if liq5 != null: liq5.visible = false
			if _fibre_mesh != null: _fibre_mesh.visible = false
			if _spool_yarn_mesh != null: _spool_yarn_mesh.scale = Vector3(0.01, 1.0, 0.01)
		elif t <= 36.2:
			# Coagulation bath filling
			sv5.is_active = true
			if liq5 != null: liq5.visible = true
			if _fibre_mesh != null: _fibre_mesh.visible = false
			if _spool_yarn_mesh != null: _spool_yarn_mesh.scale = Vector3(0.01, 1.0, 0.01)
		else:
			# Active wet spinning: continuous filament extruded, spool winding thickens
			sv5.is_active = true
			if liq5 != null: liq5.visible = true
			if _fibre_mesh != null and not _is_fibre_snapped:
				_fibre_mesh.visible = true
			if _spool_yarn_mesh != null:
				var spin_prog := clampf((t - 36.2) / 3.8, 0.05, 1.0)
				_spool_yarn_mesh.scale = Vector3(spin_prog, 1.0, spin_prog)


# ---------------------------------------------------------------- Interactive Sandbox Mechanics

func set_fibre_tension_load(load_mpa: float, threshold_mpa: float = 29.3) -> void:
	_current_fibre_load_mpa = load_mpa
	_fibre_uts_threshold_mpa = threshold_mpa
	if _current_fibre_load_mpa > _fibre_uts_threshold_mpa:
		trigger_fibre_snap()
	else:
		reset_fibre_snap()


func trigger_fibre_snap() -> void:
	if _is_fibre_snapped:
		return
	_is_fibre_snapped = true
	if _fibre_mesh != null:
		_fibre_mesh.visible = false
	if _fibre_particles != null:
		_fibre_particles.restart()
		_fibre_particles.emitting = true
	fibre_snapped.emit(_current_fibre_load_mpa)


func reset_fibre_snap() -> void:
	_is_fibre_snapped = false
	if _fibre_mesh != null and _current_sim_time >= 36.0:
		_fibre_mesh.visible = true


# ---------------------------------------------------------------- Legacy Vessel fallback

func _build_legacy_vessel() -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = VESSEL_RADIUS
	mesh.bottom_radius = VESSEL_RADIUS
	mesh.height = VESSEL_HEIGHT
	mesh.radial_segments = 48
	mesh.cap_top = false
	mesh.cap_bottom = false

	var body := MeshInstance3D.new()
	body.mesh = mesh
	body.position = Vector3(0.0, VESSEL_HEIGHT * 0.5, 0.0)
	var glass := StandardMaterial3D.new()
	glass.albedo_color = Color(0.78, 0.86, 0.90, 0.13)
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.cull_mode = BaseMaterial3D.CULL_DISABLED
	glass.roughness = 0.06
	glass.rim_enabled = true
	body.material_override = glass
	_bench_root.add_child(body)

	var flange := CylinderMesh.new()
	flange.top_radius = VESSEL_RADIUS * 1.14
	flange.bottom_radius = VESSEL_RADIUS * 1.14
	flange.height = 0.09
	flange.cap_top = false
	var fm := MeshInstance3D.new()
	fm.mesh = flange
	fm.position = Vector3(0.0, 0.045, 0.0)
	var fmat := StandardMaterial3D.new()
	fmat.albedo_color = Color(0.30, 0.33, 0.37)
	fm.material_override = fmat
	_bench_root.add_child(fm)

	var lmesh := CylinderMesh.new()
	lmesh.top_radius = VESSEL_RADIUS * 0.965
	lmesh.bottom_radius = VESSEL_RADIUS * 0.965
	lmesh.height = 1.0
	_liquid = MeshInstance3D.new()
	_liquid.mesh = lmesh
	_liquid_mat = StandardMaterial3D.new()
	_liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_liquid_mat.roughness = 0.30
	_liquid.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_liquid.material_override = _liquid_mat
	_bench_root.add_child(_liquid)

	_static_hardware()


func _static_hardware() -> void:
	var shaft_mesh := CylinderMesh.new()
	shaft_mesh.top_radius = 0.028
	shaft_mesh.bottom_radius = 0.028
	shaft_mesh.height = VESSEL_HEIGHT * SHAFT_HEIGHT_RATIO
	var shaft := MeshInstance3D.new()
	shaft.mesh = shaft_mesh
	shaft.position = Vector3(0.0, VESSEL_HEIGHT * SHAFT_HEIGHT_RATIO * 0.5 + 0.09, 0.0)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.62, 0.64, 0.68)
	mat.metallic = 0.8
	shaft.material_override = mat
	_bench_root.add_child(shaft)

	var hub := BoxMesh.new()
	hub.size = Vector3(0.20, 0.22, 0.20)
	var motor := MeshInstance3D.new()
	motor.mesh = hub
	motor.position = Vector3(0.0, VESSEL_HEIGHT * SHAFT_HEIGHT_RATIO + 0.20, 0.0)
	motor.material_override = mat
	_bench_root.add_child(motor)

	_impeller = Node3D.new()
	_impeller.position = Vector3(0.0, 0.52, 0.0)
	_bench_root.add_child(_impeller)

	for angle_deg in [0.0, 90.0, 180.0, 270.0]:
		var blade_mesh := BoxMesh.new()
		blade_mesh.size = Vector3(0.18, 0.06, 0.012)
		var blade := MeshInstance3D.new()
		blade.mesh = blade_mesh
		blade.position = Vector3(0.12, 0.0, 0.0).rotated(Vector3.UP, deg_to_rad(angle_deg))
		blade.rotation_degrees = Vector3(0.0, angle_deg, 0.0)
		blade.material_override = mat
		_impeller.add_child(blade)


func set_fill_fraction(fraction: float) -> void:
	if _liquid == null:
		return
	if is_nan(fraction):
		_liquid.visible = false
		return
	_liquid.visible = true
	var usable := VESSEL_HEIGHT * 0.94
	var h := maxf(usable * clampf(fraction, 0.0, 1.0), 0.001)
	_liquid.mesh.height = h
	_liquid.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)


func set_turbidity(t: float) -> void:
	if _liquid_mat == null:
		return
	_turbidity = clampf(t, 0.0, 1.0)
	_liquid_mat.albedo_color = od_colour(_turbidity)


static func od_colour(t: float) -> Color:
	t = clampf(t, 0.0, 1.0)
	var pale := Color(0.88, 0.87, 0.72)
	var amber := Color(0.55, 0.34, 0.10)
	return pale.lerp(amber, pow(t, 0.62))


func get_camera() -> Camera3D:
	return _camera


func get_sub_viewport() -> SubViewport:
	return _viewport


func get_world() -> Node3D:
	return _world


func set_impeller_speed(rpm_norm: float) -> void:
	_impeller_speed = clampf(rpm_norm, 0.0, 5.0)


func get_part_screen_position(part_name: String) -> Vector2:
	if _camera == null:
		return Vector2.ZERO
	var world_pos := Vector3.ZERO
	match part_name:
		"feed_tube":
			world_pos = Vector3(-VESSEL_RADIUS * 0.65, VESSEL_HEIGHT * 0.82, 0.0)
		"culture_broth":
			world_pos = Vector3(0.0, VESSEL_HEIGHT * 0.45, 0.0)
		"impeller_sparger":
			world_pos = Vector3(0.0, 0.42, 0.0)
		"harvest_valve":
			world_pos = Vector3(VESSEL_RADIUS * 0.85, 0.12, 0.0)
	return _camera.unproject_position(world_pos)
