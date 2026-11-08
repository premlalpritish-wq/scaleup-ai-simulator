from pathlib import Path

code = '''class_name ReplayVesselView
extends SubViewportContainer
## High-Fidelity Godot 4 Forward+ 3D Simulation Engine.
## Tracks true solid-biomass phase transitions, milling hopper, kelp dissolution,
## centrifuge pellet sedimentation, ethanol fibrous flocculation, wet-spinning,
## 3D Instron tensile pull tester, and on-vessel 3D Stage Blackboard Cards.

const SHAFT_HEIGHT_RATIO := 0.92
const VESSEL_RADIUS := 0.52
const VESSEL_HEIGHT := 2.4
const FILL_BASE_Y := 0.11
const STAGE_SPACING := 2.35

var _viewport: SubViewport
var _world: Node3D
var _bench_root: Node3D
var _camera: Camera3D
var _pitch_axis: Node3D

var _yaw := deg_to_rad(-22.0)
var _pitch := deg_to_rad(-12.0)
var _distance := 8.5
var _dragging := false
var _panning := false
var _target := Vector3(0.0, 1.2, 0.0)
var _camera_tween: Tween

var _turbidity := 0.0
var _impeller_speed: float = 0.0
var _unverified_pulse_time: float = 0.0
var _chevron_anim_time: float = 0.0

# Legacy single-vessel pointers for backwards compatibility
var _liquid: MeshInstance3D
var _liquid_mat: StandardMaterial3D
var _impeller: Node3D
var _feed_tube: MeshInstance3D
var _sparger: MeshInstance3D
var _harvest_valve: MeshInstance3D

# Multi-vessel stage representations
var _stage_vessels: Array = []
var _active_stage_index: int = 0
var _flow_chevrons: Array = []

# Feed Preparation Unit (Stage 0: Milling Hopper)
var _hopper_node: Node3D
var _hopper_blade: Node3D

# Stage 5 Fibre tension & Instron rig
var _fibre_mesh: MeshInstance3D
var _fibre_spool: Node3D
var _fibre_particles: GPUParticles3D
var _instron_grip_top: MeshInstance3D
var _instron_gauge_label: Label3D
var _is_fibre_snapped: bool = false
var _current_fibre_load_mpa: float = 12.0
var _fibre_uts_threshold_mpa: float = 29.3

signal orbit_changed(azimuth_deg: float, elevation_deg: float, distance: float)
signal stage_clicked(stage_id: String, stage_index: int)
signal fibre_snapped(load_mpa: float)


func _process(delta: float) -> void:
	_unverified_pulse_time += delta
	_chevron_anim_time += delta * 2.5

	# Animate milling grinder blades in feed hopper
	if _hopper_blade != null:
		_hopper_blade.rotate_y(delta * 12.0)

	# Animate directional flow chevrons along interstage pipes
	for ch_mat in _flow_chevrons:
		if ch_mat is StandardMaterial3D:
			ch_mat.uv1_offset.x = -_chevron_anim_time * 0.5

	# Update physics and rotations for each stage vessel
	for sv in _stage_vessels:
		# Rotating impellers & rotors
		if sv.impeller != null:
			var spd: float = float(sv.drivers.get("rpm", 200.0)) / 60.0
			sv.impeller.rotate_y(spd * delta * 4.0)

		# Vortex meniscus swirl
		if sv.has("meniscus") and sv.meniscus != null:
			var swirl_speed: float = float(sv.drivers.get("vortex_speed", 2.0))
			sv.meniscus.rotate_y(swirl_speed * delta)

		# Centrifuge rotor high-speed blur spin
		if sv.has("rotor") and sv.rotor != null:
			var rpm: float = float(sv.drivers.get("rpm", 4500.0))
			sv.rotor.rotate_y((rpm / 60.0) * delta * 6.28)

		# Rotating take-up yarn spool in wet spinning bath
		if sv.has("spool") and sv.spool != null:
			sv.spool.rotate_z(delta * 2.8)

		# Unverified pulsing alert wireframe
		if sv.is_unverified and sv.wireframe != null:
			var pulse := 0.5 + 0.5 * sin(_unverified_pulse_time * 5.0)
			var wmat: StandardMaterial3D = sv.wireframe.material_override as StandardMaterial3D
			if wmat != null:
				wmat.albedo_color = Color(1.0, 0.2, 0.2, 0.35 + 0.55 * pulse)

	if _impeller != null and _impeller_speed > 0.0:
		_impeller.rotate_y(_impeller_speed * delta * 6.0)


func _ready() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_viewport = SubViewport.new()
	_viewport.own_world_3d = true
	_viewport.transparent_bg = false
	_viewport.msaa_3d = Viewport.MSAA_4X
	_viewport.handle_input_locally = false
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)
	_build_world()
	_apply_camera()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		match mb.button_index:
			MOUSE_BUTTON_LEFT:
				if mb.pressed:
					if Input.is_key_pressed(KEY_SHIFT):
						_panning = true
					else:
						_dragging = true
				else:
					if not _dragging and not _panning:
						_handle_click_select(mb.position)
					_dragging = false
					_panning = false
			MOUSE_BUTTON_MIDDLE:
				_panning = mb.pressed
			MOUSE_BUTTON_WHEEL_UP:
				if mb.pressed:
					_zoom(-1.0)
			MOUSE_BUTTON_WHEEL_DOWN:
				if mb.pressed:
					_zoom(1.0)
		accept_event()
	elif event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		if _dragging:
			_yaw -= mm.relative.x * 0.008
			_pitch = clampf(_pitch - mm.relative.y * 0.008, deg_to_rad(-80.0), deg_to_rad(80.0))
			_apply_camera()
			accept_event()
		elif _panning:
			var basis := Basis.from_euler(Vector3(_pitch, _yaw, 0.0))
			var right := basis.x
			var up := basis.y
			_target -= (right * mm.relative.x * 0.006) - (up * mm.relative.y * 0.006)
			_apply_camera()
			accept_event()


func _handle_click_select(screen_pos: Vector2) -> void:
	if _stage_vessels.is_empty():
		return
	var best_idx := -1
	var min_dist := 1e9
	for i in range(_stage_vessels.size()):
		var sv: Dictionary = _stage_vessels[i]
		var vpos: Vector3 = sv.root.global_position + Vector3(0, 1.1, 0)
		var sp := _camera.unproject_position(vpos)
		var d := sp.distance_to(screen_pos)
		if d < min_dist and d < 95.0:
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
	var target_pos: Vector3 = _stage_vessels[index].root.position + Vector3(0.0, 1.25, 0.0)

	if _camera_tween != null and _camera_tween.is_valid():
		_camera_tween.kill()
	_camera_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_camera_tween.tween_property(self, "_target", target_pos, duration)
	_camera_tween.tween_property(self, "_distance", 5.2, duration)
	_camera_tween.tween_property(self, "_yaw", deg_to_rad(-20.0), duration)
	_camera_tween.tween_property(self, "_pitch", deg_to_rad(-12.0), duration)
	_camera_tween.chain().tween_callback(_apply_camera)


func _zoom(direction: float) -> void:
	_distance = clampf(_distance + direction * 0.55, 2.0, 26.0)
	_apply_camera()


func reset_camera() -> void:
	if _camera_tween != null and _camera_tween.is_valid():
		_camera_tween.kill()
	_camera_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_camera_tween.tween_property(self, "_target", Vector3(0.0, 1.2, 0.0), 0.75)
	_camera_tween.tween_property(self, "_distance", maxf(7.2, float(_stage_vessels.size()) * 1.65), 0.75)
	_camera_tween.tween_property(self, "_yaw", deg_to_rad(-22.0), 0.75)
	_camera_tween.tween_property(self, "_pitch", deg_to_rad(-12.0), 0.75)
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
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.012, 0.018, 0.030)
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	e.tonemap_exposure = 1.05

	# Glow & Bloom
	e.glow_enabled = true
	e.glow_intensity = 0.85
	e.glow_bloom = 0.22
	e.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT

	# Screen-space ambient occlusion & reflections
	e.ssao_enabled = true
	e.ssao_radius = 1.2
	e.ssao_intensity = 1.4
	e.ssr_enabled = true

	# Ambient Lighting
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.42, 0.50, 0.62)
	e.ambient_light_energy = 0.75
	env.environment = e
	_world.add_child(env)

	# Studio Key Light with soft shadows
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-50.0, -135.0, 0.0)
	key.light_energy = 1.35
	key.light_color = Color(1.0, 0.98, 0.94)
	key.shadow_enabled = true
	key.shadow_bias = 0.03
	_world.add_child(key)

	# Cool Studio Rim Fill Light
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-15.0, 55.0, 0.0)
	rim.light_energy = 0.60
	rim.light_color = Color(0.55, 0.75, 1.0)
	rim.shadow_enabled = false
	_world.add_child(rim)

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


func _build_laboratory_bench() -> void:
	# Bench Top surface with dark metallic coating
	var bench_mesh := BoxMesh.new()
	bench_mesh.size = Vector3(18.0, 0.15, 4.2)
	var bench := MeshInstance3D.new()
	bench.mesh = bench_mesh
	bench.position = Vector3(0.0, -0.075, 0.0)
	var b_mat := StandardMaterial3D.new()
	b_mat.albedo_color = Color(0.06, 0.07, 0.10)
	b_mat.metallic = 0.75
	b_mat.roughness = 0.35
	bench.material_override = b_mat
	_world.add_child(bench)

	# Floor Grid
	var grid_plane := PlaneMesh.new()
	grid_plane.size = Vector2(40.0, 40.0)
	var gm := MeshInstance3D.new()
	gm.mesh = grid_plane
	gm.position = Vector3(0.0, -0.16, 0.0)
	var g_mat := StandardMaterial3D.new()
	g_mat.albedo_color = Color(0.03, 0.04, 0.05)
	g_mat.roughness = 0.95
	gm.material_override = g_mat
	_world.add_child(gm)

	# Overhead reagent distribution manifold pipe
	var mani_mesh := CylinderMesh.new()
	mani_mesh.top_radius = 0.045
	mani_mesh.bottom_radius = 0.045
	mani_mesh.height = 16.0
	var manifold := MeshInstance3D.new()
	manifold.mesh = mani_mesh
	manifold.rotation_degrees = Vector3(0.0, 0.0, 90.0)
	manifold.position = Vector3(0.0, 3.5, -0.7)
	var m_mat := StandardMaterial3D.new()
	m_mat.albedo_color = Color(0.25, 0.30, 0.38)
	m_mat.metallic = 0.85
	m_mat.roughness = 0.25
	manifold.material_override = m_mat
	_world.add_child(manifold)


# ---------------------------------------------------------------- Multi-Vessel Topology & Phase-Change Visuals

func build_anatomy_bench(unit_operations: Array) -> void:
	if _bench_root == null:
		return
	for child in _bench_root.get_children():
		child.queue_free()
	_stage_vessels.clear()
	_flow_chevrons.clear()

	if unit_operations.is_empty():
		_build_legacy_vessel()
		return

	var count := unit_operations.size()
	var total_span := float(count - 1) * STAGE_SPACING
	_target = Vector3(0.0, 1.2, 0.0)
	_distance = clampf(5.8 + float(count) * 1.7, 6.5, 22.0)

	var first_x := -total_span * 0.5

	# 0. Build Feed Preparation Unit (Dry Seaweed Fronds & Milling Grinder Hopper)
	_build_biomass_milling_hopper(Vector3(first_x - 1.75, 0.0, 0.0), first_x)

	# 1. Build Each Unit Operation Stage
	for i in range(count):
		var op: Dictionary = unit_operations[i]
		var pos_x := first_x + float(i) * STAGE_SPACING
		var pos := Vector3(pos_x, 0.0, 0.0)
		var v_data := _spawn_unit_operation(op, i, pos)
		_stage_vessels.append(v_data)

		# Overhead station spotlight
		var spot := SpotLight3D.new()
		spot.position = pos + Vector3(0.0, 3.4, 0.25)
		spot.rotation_degrees = Vector3(-80.0, 0.0, 0.0)
		spot.spot_range = 4.5
		spot.spot_angle = 32.0
		spot.light_energy = 1.15
		spot.light_color = Color(0.92, 0.96, 1.0)
		_bench_root.add_child(spot)

	# Build transfer pipes with animated directional flow chevrons
	for i in range(count - 1):
		var p1: Vector3 = _stage_vessels[i].root.position
		var p2: Vector3 = _stage_vessels[i + 1].root.position
		_build_transfer_pipe(p1, p2)

	_apply_camera()


func _build_biomass_milling_hopper(pos: Vector3, next_x: float) -> void:
	_hopper_node = Node3D.new()
	_hopper_node.name = "BiomassMillingHopper"
	_hopper_node.position = pos
	_bench_root.add_child(_hopper_node)

	var steel_mat := StandardMaterial3D.new()
	steel_mat.albedo_color = Color(0.68, 0.72, 0.78)
	steel_mat.metallic = 0.85
	steel_mat.roughness = 0.3

	# Stand
	var stand := BoxMesh.new()
	stand.size = Vector3(0.85, 0.6, 0.85)
	var sm := MeshInstance3D.new()
	sm.mesh = stand
	sm.position = Vector3(0.0, 0.3, 0.0)
	sm.material_override = steel_mat
	_hopper_node.add_child(sm)

	# Transparent Acrylic Funnel Hopper
	var funnel := CylinderMesh.new()
	funnel.top_radius = 0.45
	funnel.bottom_radius = 0.15
	funnel.height = 0.9
	var fm := MeshInstance3D.new()
	fm.mesh = funnel
	fm.position = Vector3(0.0, 1.25, 0.0)
	var f_mat := StandardMaterial3D.new()
	f_mat.albedo_color = Color(0.85, 0.92, 0.98, 0.22)
	f_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	f_mat.roughness = 0.1
	fm.material_override = f_mat
	_hopper_node.add_child(fm)

	# Whole Leafy Brown Seaweed Fronds inside top of hopper
	for fi in range(6):
		var leaf := BoxMesh.new()
		leaf.size = Vector3(0.28, 0.015, 0.12)
		var lm := MeshInstance3D.new()
		lm.mesh = leaf
		lm.rotation_degrees = Vector3(randf_range(-25, 25), randf_range(0, 360), randf_range(-25, 25))
		lm.position = Vector3(randf_range(-0.15, 0.15), 1.45 + float(fi) * 0.03, randf_range(-0.15, 0.15))
		var l_mat := StandardMaterial3D.new()
		l_mat.albedo_color = Color(0.22, 0.14, 0.05)  # Dark dried kelp brown
		l_mat.roughness = 0.9
		lm.material_override = l_mat
		_hopper_node.add_child(lm)

	# Rotating Grinder Blade Hub
	_hopper_blade = Node3D.new()
	_hopper_blade.position = Vector3(0.0, 0.78, 0.0)
	_hopper_node.add_child(_hopper_blade)
	for a in [0.0, 120.0, 240.0]:
		var blade := BoxMesh.new()
		blade.size = Vector3(0.22, 0.015, 0.03)
		var bm := MeshInstance3D.new()
		bm.mesh = blade
		bm.rotation_degrees = Vector3(0.0, a, 0.0)
		bm.position = Vector3(0.08, 0.0, 0.0).rotated(Vector3.UP, deg_to_rad(a))
		bm.material_override = steel_mat
		_hopper_blade.add_child(bm)

	# Solid Chute pouring dried milled kelp flakes into Stage 1
	var chute := CylinderMesh.new()
	chute.top_radius = 0.06
	chute.bottom_radius = 0.06
	chute.height = 1.15
	var cm := MeshInstance3D.new()
	cm.mesh = chute
	cm.rotation_degrees = Vector3(0.0, 0.0, -52.0)
	cm.position = Vector3(0.48, 0.72, 0.0)
	cm.material_override = steel_mat
	_hopper_node.add_child(cm)

	# Overhead Stage 0 Billboard Slate
	var board := _create_3d_blackboard(
		"STAGE 0: FEED PREPARATION",
		"Whole Dried Sugar Kelp Fronds (15.0 g dry)",
		"Milling Grinder -> 0.5 mm Flakes / Coarse Meal",
		"Chute Feed -> 15.0 g Solid Kelp Powder to Stage 1"
	)
	board.position = Vector3(0.0, 2.75, 0.0)
	_hopper_node.add_child(board)


func _spawn_unit_operation(op: Dictionary, index: int, pos: Vector3) -> Dictionary:
	var root := Node3D.new()
	root.name = "Stage_%d_%s" % [index, op.get("stage_id", "vessel")]
	root.position = pos
	_bench_root.add_child(root)

	var primitive: String = str(op.get("equipment_primitive", "agitated_extraction_vessel"))
	var tier: String = str(op.get("evidence_tier", "DIRECT"))
	var is_unverified := (tier == "UNVERIFIED" or str(op.get("status", "")) == "insufficient_evidence")
	var drivers: Dictionary = op.get("visual_drivers", {})
	var bb: Dictionary = op.get("blackboard", {})

	var liquid_mesh: MeshInstance3D = null
	var liquid_mat: StandardMaterial3D = null
	var impeller_node: Node3D = null
	var wireframe_mesh: MeshInstance3D = null
	var particle_sys: GPUParticles3D = null
	var pellet_mesh: MeshInstance3D = null
	var meniscus_node: MeshInstance3D = null
	var rotor_node: Node3D = null
	var spool_node: Node3D = null
	var floc_mesh: MeshInstance3D = null
	var ph_halo: MeshInstance3D = null

	var steel_mat := StandardMaterial3D.new()
	steel_mat.albedo_color = Color(0.68, 0.72, 0.78)
	steel_mat.metallic = 0.90
	steel_mat.roughness = 0.28

	# Overhead 3D Blackboard Slate Card
	var board := _create_3d_blackboard(
		"STAGE %d: %s" % [index + 1, str(op.get("title", "")).to_upper()],
		str(bb.get("what_went_in", "Feed Stream")),
		str(bb.get("physical_state", "Reaction / Processing")),
		str(bb.get("what_comes_out", "Product Yield"))
	)
	board.position = Vector3(0.0, 2.75, 0.0)
	root.add_child(board)

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

	if "centrifuge" in primitive:
		# ------------------------------------------------ STAGE 3: CENTRIFUGE
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

		# Stand base
		var stand := BoxMesh.new()
		stand.size = Vector3(1.15, 0.4, 1.15)
		var sm := MeshInstance3D.new()
		sm.mesh = stand
		sm.position = Vector3(0.0, 0.2, 0.0)
		sm.material_override = steel_mat
		root.add_child(sm)

		# Clarifying golden-amber supernatant liquid column
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
		root.add_child(liquid_mesh)

		# Compacting dark-brown solid pellet mesh at the bottom
		var p_mesh := CylinderMesh.new()
		p_mesh.top_radius = VESSEL_RADIUS * 0.34
		p_mesh.bottom_radius = VESSEL_RADIUS * 0.25
		p_mesh.height = 0.08
		pellet_mesh = MeshInstance3D.new()
		pellet_mesh.mesh = p_mesh
		pellet_mesh.position = Vector3(0.0, 0.46, 0.0)
		var pel_mat := StandardMaterial3D.new()
		pel_mat.albedo_color = Color(0.18, 0.10, 0.05)
		pel_mat.roughness = 0.85
		pellet_mesh.material_override = pel_mat
		root.add_child(pellet_mesh)

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

		# Live Floating pH indicator halo above centrifuge neutralisation port
		var halo := TorusMesh.new()
		halo.inner_radius = 0.14
		halo.outer_radius = 0.18
		ph_halo = MeshInstance3D.new()
		ph_halo.mesh = halo
		ph_halo.position = Vector3(0.0, 1.95, 0.0)
		var h_mat := StandardMaterial3D.new()
		h_mat.albedo_color = Color(0.72, 0.12, 0.85)  # Initial alkaline pH 12
		h_mat.emission_enabled = true
		h_mat.emission = Color(0.72, 0.12, 0.85)
		h_mat.emission_energy_multiplier = 1.2
		ph_halo.material_override = h_mat
		root.add_child(ph_halo)

	elif "precipitation" in primitive:
		# ------------------------------------------------ STAGE 4: PRECIPITATION TANK
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

		# Fluid bed
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
		root.add_child(liquid_mesh)

		# Coalescing 3D fibrous alginate floc mass (precipitated polymer clots)
		var floc := SphereMesh.new()
		floc.radius = 0.28
		floc.height = 0.45
		floc_mesh = MeshInstance3D.new()
		floc_mesh.mesh = floc
		floc_mesh.position = Vector3(0.0, 0.58, 0.0)
		var fl_mat := StandardMaterial3D.new()
		fl_mat.albedo_color = Color(0.96, 0.96, 0.92, 0.88)
		fl_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		fl_mat.roughness = 0.75
		floc_mesh.material_override = fl_mat
		floc_mesh.scale = Vector3(0.08, 0.08, 0.08)
		root.add_child(floc_mesh)

	elif "bath" in primitive:
		# ------------------------------------------------ STAGE 5: WET SPINNING BATH & INSTRON RIG
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

		# Coagulation bath liquid (CaCl2)
		var fluid := BoxMesh.new()
		fluid.size = Vector3(1.68, 0.42, 0.78)
		liquid_mesh = MeshInstance3D.new()
		liquid_mesh.mesh = fluid
		liquid_mesh.position = Vector3(0.0, 0.36, 0.0)
		liquid_mat = StandardMaterial3D.new()
		liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		liquid_mat.albedo_color = Color(0.20, 0.82, 0.65, 0.65)
		liquid_mesh.material_override = liquid_mat
		root.add_child(liquid_mesh)

		# Submerged Spinneret Extrusion Needle
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

		# Guide Rollers
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

		# Rotating Yarn Take-up Spool
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

		# Continuous 3D White Polymer Monofilament Thread
		var f_mesh := CylinderMesh.new()
		f_mesh.top_radius = 0.012
		f_mesh.bottom_radius = 0.012
		f_mesh.height = 1.35
		_fibre_mesh = MeshInstance3D.new()
		_fibre_mesh.mesh = f_mesh
		_fibre_mesh.rotation_degrees = Vector3(0.0, 0.0, 90.0)
		_fibre_mesh.position = Vector3(0.0, 0.42, 0.0)
		var fmat := StandardMaterial3D.new()
		fmat.albedo_color = Color(0.96, 0.98, 1.0)
		fmat.roughness = 0.35
		fmat.emission_enabled = true
		fmat.emission = Color(0.4, 0.8, 1.0)
		fmat.emission_energy_multiplier = 0.4
		_fibre_mesh.material_override = fmat
		root.add_child(_fibre_mesh)

		# Fracture particle emitter
		_fibre_particles = _create_fracture_particle_emitter()
		_fibre_particles.position = Vector3(0.0, 0.42, 0.0)
		root.add_child(_fibre_particles)

		# 3D Instron Tensile Testing Rig attached beside bath
		var instron_rig := _build_3d_instron_rig(Vector3(0.0, 0.95, -0.65))
		root.add_child(instron_rig)

	else:
		# ------------------------------------------------ STAGES 1 & 2: AGITATED EXTRACTION VESSELS
		var body_mesh := CylinderMesh.new()
		body_mesh.top_radius = VESSEL_RADIUS
		body_mesh.bottom_radius = VESSEL_RADIUS
		body_mesh.height = VESSEL_HEIGHT
		body_mesh.radial_segments = 48
		var body := MeshInstance3D.new()
		body.mesh = body_mesh
		body.position = Vector3(0.0, VESSEL_HEIGHT * 0.5, 0.0)

		# Glass with refraction and fresnel rim
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

		# Flange base
		var flange := CylinderMesh.new()
		flange.top_radius = VESSEL_RADIUS * 1.15
		flange.bottom_radius = VESSEL_RADIUS * 1.15
		flange.height = 0.08
		var fm := MeshInstance3D.new()
		fm.mesh = flange
		fm.position = Vector3(0.0, 0.04, 0.0)
		fm.material_override = steel_mat
		root.add_child(fm)

		# Liquid column
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
		root.add_child(liquid_mesh)

		# Swirling Meniscus
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
		root.add_child(meniscus_node)

		# Impeller Shaft & Blades
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

		# Top motor drive
		var motor := BoxMesh.new()
		motor.size = Vector3(0.22, 0.25, 0.22)
		var mm := MeshInstance3D.new()
		mm.mesh = motor
		mm.position = Vector3(0.0, VESSEL_HEIGHT + 0.12, 0.0)
		mm.material_override = steel_mat
		root.add_child(mm)

		# Solid Kelp Flakes Particles
		particle_sys = _create_kelp_particles(index == 0)
		particle_sys.position = Vector3(0.0, 0.65, 0.0)
		root.add_child(particle_sys)

	# If unverified, overlay pulsating red alert shell
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
		"particles": particle_sys,
		"wireframe": wireframe_mesh,
		"time_window": op.get("time_window_h", [0.0, 20.0]),
		"is_unverified": is_unverified,
		"drivers": drivers,
		"blackboard": bb,
	}


func _create_3d_blackboard(title: String, went_in: String, state_info: String, comes_out: String) -> Node3D:
	var board_node := Node3D.new()

	var bg := BoxMesh.new()
	bg.size = Vector3(1.85, 0.68, 0.02)
	var bg_mesh := MeshInstance3D.new()
	bg_mesh.mesh = bg
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.04, 0.06, 0.09, 0.92)
	mat.roughness = 0.8
	bg_mesh.material_override = mat
	board_node.add_child(bg_mesh)

	# Border
	var border := BoxMesh.new()
	border.size = Vector3(1.88, 0.71, 0.015)
	var bm := MeshInstance3D.new()
	bm.mesh = border
	bm.position = Vector3(0, 0, -0.005)
	var b_mat := StandardMaterial3D.new()
	b_mat.albedo_color = Color(0.20, 0.45, 0.70)
	bm.material_override = b_mat
	board_node.add_child(bm)

	# Text labels
	var l_title := Label3D.new()
	l_title.text = title
	l_title.font_size = 20
	l_title.modulate = Color(0.35, 0.85, 1.0)
	l_title.position = Vector3(0.0, 0.22, 0.02)
	board_node.add_child(l_title)

	var l_in := Label3D.new()
	l_in.text = "IN: " + went_in
	l_in.font_size = 14
	l_in.modulate = Color(0.92, 0.95, 1.0)
	l_in.position = Vector3(0.0, 0.08, 0.02)
	board_node.add_child(l_in)

	var l_state := Label3D.new()
	l_state.text = "STATE: " + state_info
	l_state.font_size = 13
	l_state.modulate = Color(0.98, 0.82, 0.35)
	l_state.position = Vector3(0.0, -0.06, 0.02)
	board_node.add_child(l_state)

	var l_out := Label3D.new()
	l_out.text = "OUT: " + comes_out
	l_out.font_size = 14
	l_out.modulate = Color(0.25, 0.88, 0.55)
	l_out.position = Vector3(0.0, -0.20, 0.02)
	board_node.add_child(l_out)

	return board_node


func _build_3d_instron_rig(pos: Vector3) -> Node3D:
	var rig := Node3D.new()
	rig.name = "InstronTensileRig"
	rig.position = pos

	var steel_mat := StandardMaterial3D.new()
	steel_mat.albedo_color = Color(0.70, 0.74, 0.80)
	steel_mat.metallic = 0.85
	steel_mat.roughness = 0.25

	# Base frame
	var base := BoxMesh.new()
	base.size = Vector3(0.5, 0.08, 0.35)
	var bm := MeshInstance3D.new()
	bm.mesh = base
	bm.material_override = steel_mat
	rig.add_child(bm)

	# Columns
	for cx in [-0.2, 0.2]:
		var col := CylinderMesh.new()
		col.top_radius = 0.02
		col.bottom_radius = 0.02
		col.height = 0.85
		var cm := MeshInstance3D.new()
		cm.mesh = col
		cm.position = Vector3(cx, 0.42, 0.0)
		cm.material_override = steel_mat
		rig.add_child(cm)

	# Fixed Bottom Clamp
	var b_clamp := BoxMesh.new()
	b_clamp.size = Vector3(0.12, 0.06, 0.08)
	var bcm := MeshInstance3D.new()
	bcm.mesh = b_clamp
	bcm.position = Vector3(0.0, 0.12, 0.0)
	bcm.material_override = steel_mat
	rig.add_child(bcm)

	# Moveable Top Crosshead / Grip
	var t_clamp := BoxMesh.new()
	t_clamp.size = Vector3(0.42, 0.06, 0.1)
	_instron_grip_top = MeshInstance3D.new()
	_instron_grip_top.mesh = t_clamp
	_instron_grip_top.position = Vector3(0.0, 0.55, 0.0)
	_instron_grip_top.material_override = steel_mat
	rig.add_child(_instron_grip_top)

	# Fibre Sample between clamps
	var sample := CylinderMesh.new()
	sample.top_radius = 0.008
	sample.bottom_radius = 0.008
	sample.height = 0.40
	var sm := MeshInstance3D.new()
	sm.mesh = sample
	sm.position = Vector3(0.0, 0.33, 0.0)
	var sm_mat := StandardMaterial3D.new()
	sm_mat.albedo_color = Color(0.98, 0.98, 1.0)
	sm_mat.emission_enabled = true
	sm_mat.emission = Color(0.4, 0.8, 1.0)
	sm_mat.emission_energy_multiplier = 0.5
	sm.material_override = sm_mat
	rig.add_child(sm)

	# Instron Digital Readout Label3D
	_instron_gauge_label = Label3D.new()
	_instron_gauge_label.text = "TENSILE RIG: 12.0 MPa"
	_instron_gauge_label.font_size = 18
	_instron_gauge_label.modulate = Color(0.25, 0.88, 0.55)
	_instron_gauge_label.position = Vector3(0.0, 0.88, 0.0)
	rig.add_child(_instron_gauge_label)

	return rig


func _create_kelp_particles(is_stage_1: bool) -> GPUParticles3D:
	var gp := GPUParticles3D.new()
	gp.amount = 120 if is_stage_1 else 160
	gp.lifetime = 2.8
	gp.preprocess = 0.5
	gp.explosiveness = 0.0

	var pmat := ParticleProcessMaterial.new()
	pmat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_RING
	pmat.emission_ring_radius = 0.34
	pmat.emission_ring_inner_radius = 0.05
	pmat.emission_ring_height = 0.50
	pmat.emission_ring_axis = Vector3(0, 1, 0)
	pmat.orbit_velocity_min = 0.75
	pmat.orbit_velocity_max = 1.65
	pmat.gravity = Vector3(0, -0.12, 0)
	pmat.scale_min = 0.04
	pmat.scale_max = 0.08
	gp.process_material = pmat

	var p_mesh := BoxMesh.new()
	p_mesh.size = Vector3(0.045, 0.015, 0.045)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.24, 0.15, 0.06)  # Dark seaweed brown
	mat.roughness = 0.85
	p_mesh.material = mat
	gp.draw_pass_1 = p_mesh

	return gp


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


func _build_transfer_pipe(p1: Vector3, p2: Vector3) -> void:
	var span := p2.x - p1.x
	var pipe_mesh := CylinderMesh.new()
	pipe_mesh.top_radius = 0.032
	pipe_mesh.bottom_radius = 0.032
	pipe_mesh.height = span - VESSEL_RADIUS * 1.45
	var pipe := MeshInstance3D.new()
	pipe.mesh = pipe_mesh
	pipe.rotation_degrees = Vector3(0.0, 0.0, 90.0)
	pipe.position = Vector3((p1.x + p2.x) * 0.5, 1.25, 0.0)

	var p_mat := StandardMaterial3D.new()
	p_mat.albedo_color = Color(0.22, 0.75, 0.95)
	p_mat.metallic = 0.8
	p_mat.roughness = 0.25
	p_mat.emission_enabled = true
	p_mat.emission = Color(0.12, 0.55, 0.85)
	p_mat.emission_energy_multiplier = 0.7
	pipe.material_override = p_mat
	_bench_root.add_child(pipe)
	_flow_chevrons.append(p_mat)


func update_at_time(t: float, telemetry_dict: Dictionary, schema: Dictionary = {}) -> void:
	if _stage_vessels.is_empty():
		return

	for i in range(_stage_vessels.size()):
		var sv: Dictionary = _stage_vessels[i]
		var t_win: Array = sv.time_window
		var t0: float = float(t_win[0])
		var t1: float = float(t_win[1])
		var is_active := (t >= t0 and t <= t1)
		var progress := clampf((t - t0) / maxf(t1 - t0, 0.001), 0.0, 1.0)

		# Liquid volume and color dynamics
		if sv.liquid != null and sv.liquid_mat != null:
			var drivers: Dictionary = sv.drivers
			var col_start := Color.from_string(str(drivers.get("color_start_hex", "#064e3b")), Color(0.04, 0.35, 0.22))
			var col_end := Color.from_string(str(drivers.get("color_end_hex", "#34d399")), Color(0.20, 0.82, 0.60))

			if is_active:
				sv.liquid_mat.albedo_color = col_start.lerp(col_end, progress)
				var usable := VESSEL_HEIGHT * 0.88
				var h := maxf(usable * (0.35 + 0.55 * progress), 0.1)
				sv.liquid.mesh.height = h
				sv.liquid.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)
				if sv.meniscus != null:
					sv.meniscus.position.y = FILL_BASE_Y + h
			elif t > t1:
				sv.liquid_mat.albedo_color = col_end
			else:
				sv.liquid_mat.albedo_color = col_start * 0.55

		# 1. Solid kelp flake dissolution: Stage 1 maintains solids, Stage 2 dissolves them
		if sv.particles != null:
			var pmat: ParticleProcessMaterial = sv.particles.process_material as ParticleProcessMaterial
			if pmat != null:
				if i == 0:
					# Stage 1: Solids stay intact (insoluble alginic acid in cell walls)
					pmat.scale_min = 0.04
					pmat.scale_max = 0.08
				elif i == 1:
					# Stage 2: Alkaline dissolution shrinks solid chunks by 70%
					var scale_factor := 1.0 - (0.70 * progress if is_active else (0.70 if t > t1 else 0.0))
					pmat.scale_min = 0.04 * scale_factor
					pmat.scale_max = 0.08 * scale_factor

		# 2. Centrifuge pellet compaction & pH halo transition
		if sv.pellet != null:
			var pel_h := 0.01 + (0.16 * progress if is_active else (0.16 if t > t1 else 0.01))
			sv.pellet.mesh.height = pel_h
			sv.pellet.position.y = 0.46 + pel_h * 0.5
		if sv.ph_halo != null:
			var halo_mat: StandardMaterial3D = sv.ph_halo.material_override as StandardMaterial3D
			if halo_mat != null:
				var purple := Color(0.72, 0.12, 0.85)
				var green := Color(0.12, 0.85, 0.42)
				var cur_col := purple.lerp(green, progress if is_active else (1.0 if t > t1 else 0.0))
				halo_mat.albedo_color = cur_col
				halo_mat.emission = cur_col

		# 3. Alginate floc nucleation and growth in precipitation tank
		if sv.floc != null:
			var f_scale := 0.08 + (0.85 * progress if is_active else (0.85 if t > t1 else 0.0))
			sv.floc.scale = Vector3(f_scale, f_scale, f_scale)

	# Fibre Tension test in wet spinning bath
	if _fibre_mesh != null and not _is_fibre_snapped:
		var fmat: StandardMaterial3D = _fibre_mesh.material_override as StandardMaterial3D
		if fmat != null:
			if _current_fibre_load_mpa > _fibre_uts_threshold_mpa:
				trigger_fibre_snap()
			elif _current_fibre_load_mpa > _fibre_uts_threshold_mpa * 0.85:
				fmat.albedo_color = Color(1.0, 0.75, 0.2)
			else:
				fmat.albedo_color = Color(0.96, 0.98, 1.0)


# ---------------------------------------------------------------- Interactive Sandbox Mechanics

func set_fibre_tension_load(load_mpa: float, threshold_mpa: float = 29.3) -> void:
	_current_fibre_load_mpa = load_mpa
	_fibre_uts_threshold_mpa = threshold_mpa
	if _instron_gauge_label != null:
		_instron_gauge_label.text = "TENSILE RIG: %.1f MPa" % load_mpa
		if load_mpa > threshold_mpa:
			_instron_gauge_label.modulate = Color(1.0, 0.25, 0.25)
		else:
			_instron_gauge_label.modulate = Color(0.25, 0.88, 0.55)

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
	if _fibre_mesh != null:
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
'''

Path("scripts/replay_vessel_view.gd").write_text(code, encoding="utf-8")
print("Successfully generated phase-transition replay_vessel_view.gd")
