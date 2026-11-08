class_name PecanProcessSim
extends SubViewportContainer
## Step-indexed 3D bench for the pecan RNA extraction workflow.
##
## The bench is an **illustrative mechanics animation**, not a validated model.
## Every research step in `model_spec.json` owns one slot on a single
## deterministic clock, and the slot's `mode` decides what the bench does:
##
##   physical  a pecan operation — objects actually move (tissue, pipette,
##             liquid levels, rotor, gel slice, heat block)
##   observe   a measurement is performed — the instrument is operated, but no
##             reading is invented; the pecan source reports no value
##   analogue  a hypothesis transferred from Norway spruce or pigeonpea — the
##             pecan bench does NOT move; a separate amber card pulses
##   caveat    the method-review caveat — a muted card, unresolved for pecan
##
## The paper prints no volumes, speeds, durations, yields or RIN, so no number is
## computed or shown. The clock is wall time and every motion is authored.
## Everything visible is a deterministic function of `apply_clock(t)`, so the
## replay can be scrubbed, paused and resumed without drift.

signal object_clicked(kind: String)
signal orbit_changed(azimuth_deg: float, elevation_deg: float, distance: float)

const TOTAL_SECONDS := 51.7

## One entry per recorded research step. `start`/`end` are cumulative and match
## the authored motion below; `station` is the 3D anchor a camera focus uses and
## the object a click on the bench inspects.
const STEPS := [
	{"id": "pecan_sample_handling", "label": "Collect and preserve pecan embryos",
		"start": 0.0, "end": 3.0, "mode": "physical", "station": "tissue"},
	{"id": "pecan_trizol_extraction", "label": "Extract total RNA with a TRIzol kit",
		"start": 3.0, "end": 9.5, "mode": "physical", "station": "tube_a"},
	{"id": "pecan_dnase_treatment", "label": "Remove genomic DNA with DNase I",
		"start": 9.5, "end": 13.5, "mode": "physical", "station": "dnase"},
	{"id": "pecan_quality_assessment", "label": "Assess RNA quality and concentration",
		"start": 13.5, "end": 17.5, "mode": "observe", "station": "quality"},
	{"id": "pecan_small_rna_enrichment", "label": "Enrich 18-30 nt small RNA by PAGE",
		"start": 17.5, "end": 21.5, "mode": "physical", "station": "page"},
	{"id": "pecan_cdna_synthesis", "label": "Reverse transcribe 1 ug RNA to cDNA",
		"start": 21.5, "end": 25.0, "mode": "physical", "station": "cdna"},
	{"id": "analogue_spruce_ctab_extraction", "label": "Modified CTAB extraction - Norway spruce (analogue)",
		"start": 25.0, "end": 27.2, "mode": "analogue", "station": "reference", "branch": "spruce"},
	{"id": "analogue_spruce_phase_separation", "label": "Chloroform:isoamyl phase separation - spruce (analogue)",
		"start": 27.2, "end": 29.4, "mode": "analogue", "station": "reference", "branch": "spruce"},
	{"id": "analogue_spruce_licl_precipitation", "label": "LiCl precipitation - spruce (analogue)",
		"start": 29.4, "end": 31.6, "mode": "analogue", "station": "reference", "branch": "spruce"},
	{"id": "analogue_spruce_elution", "label": "Wash, dry and elute - spruce (analogue)",
		"start": 31.6, "end": 33.8, "mode": "analogue", "station": "reference", "branch": "spruce"},
	{"id": "analogue_spruce_dnase", "label": "DNase treatment - spruce (analogue)",
		"start": 33.8, "end": 36.0, "mode": "analogue", "station": "reference", "branch": "spruce"},
	{"id": "analogue_spruce_trizol_finding", "label": "TRIzol performance - spruce (analogue result)",
		"start": 36.0, "end": 38.2, "mode": "analogue", "station": "reference", "branch": "spruce"},
	{"id": "analogue_pigeonpea_ctab_extraction", "label": "Modified CTAB extraction - pigeonpea (analogue)",
		"start": 38.2, "end": 40.4, "mode": "analogue", "station": "reference", "branch": "pigeonpea"},
	{"id": "analogue_pigeonpea_phase_separation", "label": "Phenol:chloroform phase separation - pigeonpea (analogue)",
		"start": 40.4, "end": 42.6, "mode": "analogue", "station": "reference", "branch": "pigeonpea"},
	{"id": "analogue_pigeonpea_precipitation", "label": "Isopropanol precipitation - pigeonpea (analogue)",
		"start": 42.6, "end": 44.8, "mode": "analogue", "station": "reference", "branch": "pigeonpea"},
	{"id": "analogue_pigeonpea_dnase", "label": "DNase I treatment - pigeonpea (analogue)",
		"start": 44.8, "end": 47.0, "mode": "analogue", "station": "reference", "branch": "pigeonpea"},
	{"id": "analogue_pigeonpea_quality", "label": "Yield and purity results - pigeonpea (analogue)",
		"start": 47.0, "end": 49.2, "mode": "analogue", "station": "reference", "branch": "pigeonpea"},
	{"id": "method_review_caveat", "label": "Method-review caveat: no universal RNA protocol",
		"start": 49.2, "end": 51.7, "mode": "caveat", "station": "caveat"},
]

## Camera framing per station. `focus_station` glides the camera here, so a user
## who clicks a vessel is taken to the part of the bench that vessel belongs to.
const FOCUS := {
	"tissue": [Vector3(-1.95, 1.15, 0.55), 4.9],
	"tube_a": [Vector3(-0.10, 1.30, 0.50), 5.2],
	"dnase": [Vector3(2.30, 1.20, 0.65), 4.7],
	"quality": [Vector3(3.35, 1.10, 1.55), 4.9],
	"page": [Vector3(4.45, 1.10, 1.40), 4.7],
	"cdna": [Vector3(3.45, 1.15, 0.40), 4.5],
	"reference": [Vector3(-4.75, 1.45, 1.70), 5.0],
	"caveat": [Vector3(-4.75, 1.30, 0.50), 4.4],
}
const DEFAULT_FOCUS := [Vector3(0.10, 1.25, 0.85), 9.4]

const TUBE_A_HOME := Vector3(-0.55, 1.02, 0.15)
const TUBE_B_HOME := Vector3(2.05, 1.02, 0.30)
const ROTOR_SLOT := Vector3(0.95, 1.36, 0.15)
const PIPETTE_HOME := Vector3(-1.55, 2.00, 0.75)
const BOTTLE_POS := Vector3(-1.80, 1.02, 0.55)
const DISH_POS := Vector3(-2.45, 1.02, 0.35)
const TISSUE_FROM := Vector3(-2.40, 1.12, 0.35)
const DNASE_POS := Vector3(2.85, 1.02, 0.80)
const CDNA_POS := Vector3(3.80, 1.02, 0.20)
const GEL_POS := Vector3(2.95, 1.00, 1.62)
const NANODROP_POS := Vector3(3.95, 1.00, 1.62)
const PAGE_POS := Vector3(4.80, 1.00, 1.50)
const SLICE_TUBE_POS := Vector3(4.80, 1.02, 0.30)
const KIOSK_POS := Vector3(-5.05, 1.02, 1.85)
const CAVEAT_POS := Vector3(-5.05, 1.02, 0.45)

const MODE_PHYSICAL := Color(0.52, 0.82, 0.60)
const MODE_OBSERVE := Color(0.55, 0.75, 0.98)
const MODE_ANALOGUE := Color(0.96, 0.72, 0.28)
const MODE_CAVEAT := Color(0.76, 0.79, 0.86)


var _viewport: SubViewport
var _world: Node3D
var _camera: Camera3D
var _yaw := deg_to_rad(-30.0)
var _pitch := deg_to_rad(-34.0)
var _distance := 9.4
var _target := Vector3(0.10, 1.25, 0.85)
var _target_goal := Vector3(0.10, 1.25, 0.85)
var _distance_goal := 9.4
var _dragging := false
var _press := Vector2.ZERO
var _clock := 0.0
var _branch := "spruce"

var _tissue: MeshInstance3D
var _tube_a: Node3D
var _tube_b: Node3D
var _bottle: Node3D
var _mixed: MeshInstance3D
var _aqueous: MeshInstance3D
var _organic: MeshInstance3D
var _tube_b_liquid: MeshInstance3D
var _rotor: Node3D
var _pipette: Node3D
var _stream: MeshInstance3D
var _bubbles: CPUParticles3D
var _droplets: CPUParticles3D
var _hud: Label3D
var _hud_sub: Label3D

var _dnase_vial: Node3D
var _gel_cassette: Node3D
var _well_films: Array = []
var _nanodrop: Node3D
var _nanodrop_arm: Node3D
var _scan_beam: MeshInstance3D
var _incubate_ring: MeshInstance3D
var _page_cassette: Node3D
var _gel_slice: MeshInstance3D
var _slice_tube: Node3D
var _cdna_tube: Node3D
var _cdna_block: Node3D
var _block_glow: MeshInstance3D
var _analogue_card: MeshInstance3D
var _caveat_card: MeshInstance3D

var _picked: Array = []          # {body, kind}
var _last_op := -1
var _state: Dictionary = {}


func _ready() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_viewport = SubViewport.new()
	_viewport.own_world_3d = true
	_viewport.msaa_3d = Viewport.MSAA_4X
	_viewport.handle_input_locally = false
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)
	_build_world()
	_apply_camera()
	apply_clock(0.0)


func _process(delta: float) -> void:
	var k := clampf(delta * 5.0, 0.0, 1.0)
	if not _target.is_equal_approx(_target_goal) or absf(_distance - _distance_goal) > 0.002:
		_target = _target.lerp(_target_goal, k)
		_distance = lerpf(_distance, _distance_goal, k)
		_apply_camera()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		match mb.button_index:
			MOUSE_BUTTON_LEFT:
				_dragging = mb.pressed
				if mb.pressed:
					_press = mb.position
				else:
					_try_click(mb.position)
			MOUSE_BUTTON_WHEEL_UP:
				if mb.pressed:
					_zoom(-1.0)
			MOUSE_BUTTON_WHEEL_DOWN:
				if mb.pressed:
					_zoom(1.0)
		accept_event()
	elif event is InputEventMouseMotion and _dragging:
		var mm := event as InputEventMouseMotion
		_yaw -= mm.relative.x * 0.008
		_pitch = clampf(_pitch - mm.relative.y * 0.008, deg_to_rad(-78.0), deg_to_rad(6.0))
		_apply_camera()
		accept_event()


func _try_click(position: Vector2) -> void:
	if position.distance_to(_press) > 4.0 or _camera == null:
		return
	var origin := _camera.project_ray_origin(position)
	var direction := _camera.project_ray_normal(position)
	var query := PhysicsRayQueryParameters3D.create(origin, origin + direction * 40.0)
	var hit := _viewport.world_3d.direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return
	for entry in _picked:
		if entry["body"] == hit.get("collider"):
			object_clicked.emit(str(entry["kind"]))
			return


func _zoom(direction: float) -> void:
	_distance = clampf(_distance + direction * 0.5, 3.4, 16.0)
	_distance_goal = _distance
	_apply_camera()


func reset_camera() -> void:
	_target_goal = DEFAULT_FOCUS[0]
	_distance_goal = float(DEFAULT_FOCUS[1])
	_target = _target_goal
	_distance = _distance_goal
	_apply_camera()


## Glide the camera to a named station. Deterministic motion state is untouched.
func focus_station(station: String) -> void:
	var entry: Array = FOCUS.get(station, DEFAULT_FOCUS)
	_target_goal = entry[0]
	_distance_goal = float(entry[1])


func focus_step(index: int) -> void:
	focus_station(step_station(index))


func camera_goal() -> Dictionary:
	return {"target": _target_goal, "distance": _distance_goal}


func _apply_camera() -> void:
	if _camera == null:
		return
	var basis := Basis.from_euler(Vector3(_pitch, _yaw, 0.0))
	_camera.transform = Transform3D(basis, _target + basis.z * _distance)
	orbit_changed.emit(rad_to_deg(_yaw), rad_to_deg(_pitch), _distance)


# ------------------------------------------------------------------ 3D build


func _build_world() -> void:
	_world = Node3D.new()
	_viewport.add_child(_world)
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.055, 0.063, 0.078)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.52, 0.56, 0.64)
	e.ambient_light_energy = 0.9
	env.environment = e
	_world.add_child(env)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-52.0, -128.0, 0.0)
	key.light_energy = 1.15
	key.shadow_enabled = true
	_world.add_child(key)
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-14.0, 58.0, 0.0)
	rim.light_energy = 0.45
	rim.light_color = Color(0.70, 0.80, 1.0)
	_world.add_child(rim)

	_box(_world, Vector3(11.6, 0.16, 3.5), Vector3(-0.10, 0.92, 0.55), Color(0.19, 0.20, 0.23))
	_box(_world, Vector3(20.0, 0.06, 9.0), Vector3(-0.10, 0.0, 0.55), Color(0.09, 0.10, 0.12))

	_leaf_dish()
	_trizol_bottle()
	_tube_a = _tube_a_rig()
	_tube_b = _tube_b_rig()
	_pipette = _pipette_rig()
	_centrifuge()
	_dnase_rack()
	_quality_station()
	_page_station()
	_cdna_station()
	_analogue_kiosk()
	_method_review_card()
	_particles()
	_camera = Camera3D.new()
	_camera.fov = 46.0
	_world.add_child(_camera)
	# The step banner is parented to the camera so it cannot drift off-screen
	# when the focus moves to a distant station.
	_hud = Label3D.new()
	_hud.billboard = BaseMaterial3D.BILLBOARD_DISABLED
	_hud.font_size = 26
	_hud.pixel_size = 0.0014
	_hud.width = 0.0
	_hud.autowrap_mode = TextServer.AUTOWRAP_OFF
	_hud.outline_size = 10
	_hud.outline_modulate = Color(0.02, 0.03, 0.05, 0.9)
	_hud.no_depth_test = true
	_hud.position = Vector3(0.0, 0.44, -1.5)
	_camera.add_child(_hud)
	_hud_sub = Label3D.new()
	_hud_sub.billboard = BaseMaterial3D.BILLBOARD_DISABLED
	_hud_sub.font_size = 20
	_hud_sub.pixel_size = 0.0014
	_hud_sub.width = 0.0
	_hud_sub.autowrap_mode = TextServer.AUTOWRAP_OFF
	_hud_sub.outline_size = 8
	_hud_sub.outline_modulate = Color(0.02, 0.03, 0.05, 0.9)
	_hud_sub.no_depth_test = true
	_hud_sub.position = Vector3(0.0, 0.33, -1.5)
	_hud_sub.modulate = Color(0.95, 0.78, 0.45)
	_camera.add_child(_hud_sub)


func _material(colour: Color, metallic: float = 0.0, roughness: float = 0.45,
		alpha: float = 1.0) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(colour.r, colour.g, colour.b, alpha)
	mat.metallic = metallic
	mat.roughness = roughness
	if alpha < 1.0:
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	return mat


func _box(parent: Node3D, size: Vector3, position: Vector3, colour: Color,
		metallic: float = 0.0) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = position
	instance.material_override = _material(colour, metallic)
	parent.add_child(instance)
	return instance


func _cylinder(parent: Node3D, radius: float, height: float, position: Vector3,
		colour: Color, alpha: float = 1.0, metallic: float = 0.0) -> MeshInstance3D:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = 28
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = position
	instance.material_override = _material(colour, metallic, 0.3, alpha)
	if alpha < 1.0:
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(instance)
	return instance


func _pickable(node: Node3D, kind: String, size: Vector3, offset: Vector3) -> void:
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	shape.position = offset
	body.add_child(shape)
	node.add_child(body)
	_picked.append({"body": body, "kind": kind})


## Every vessel publishes its mouth as a marker. Interactions target this node,
## so a moving vessel carries its interaction point with it and no caller needs a
## coordinate.
func _add_opening(rig: Node3D, local_y: float) -> void:
	var marker := Marker3D.new()
	marker.name = "Opening"
	marker.position = Vector3(0.0, local_y, 0.0)
	rig.add_child(marker)


func _opening(rig: Node3D) -> Marker3D:
	if rig == null:
		return null
	return rig.get_node_or_null("Opening") as Marker3D


func _tip_marker() -> Marker3D:
	if _pipette == null:
		return null
	return _pipette.get_node_or_null("TipMarker") as Marker3D


## World position of the pipette tip, derived from the marker, not from a guess.
func _tip_world() -> Vector3:
	var marker := _tip_marker()
	if marker == null:
		return _pipette.global_position
	return marker.global_position


## Where the pipette's root must sit so its tip is at `clearance` above the
## opening. Derived from the tip marker, so the tip and the vessel stay related.
func _pipette_at(opening: Node3D, clearance: float) -> Vector3:
	var marker := _tip_marker()
	if marker == null or opening == null:
		return PIPETTE_HOME
	return opening.global_position + Vector3(0.0, clearance, 0.0) - marker.position


func _move_pipette_to(opening: Node3D, clearance: float) -> void:
	_pipette.position = _pipette_at(opening, clearance)


## True when the tip is over the mouth (horizontal distance only): the vertical
## gap is the intended clearance or dip.
func _aligned(opening: Node3D, tolerance: float = 0.01) -> bool:
	if opening == null:
		return false
	var tip := _tip_world()
	var mouth := opening.global_position
	return Vector2(tip.x - mouth.x, tip.z - mouth.z).length() <= tolerance


## Draw the stream from the tip to a point inside the vessel, derived from the two
## markers. The stream is a child of the pipette, so it follows it exactly.
func _stream_to(opening: Node3D) -> void:
	var marker := _tip_marker()
	if marker == null or opening == null:
		return
	var tip_y := marker.global_position.y
	var end_y := opening.global_position.y - 0.09     # inside the mouth
	var length := maxf(tip_y - end_y, 0.02)
	_stream.visible = true
	_stream.scale = Vector3(1.0, length, 1.0)
	_stream.position = Vector3(marker.position.x, marker.position.y - length * 0.5, marker.position.z)



func _leaf_dish() -> void:
	var dish := _cylinder(_world, 0.34, 0.10, DISH_POS,
		Color(0.78, 0.80, 0.84), 0.35)
	_pickable(dish, "tissue", Vector3(0.8, 0.5, 0.8), Vector3(0.0, 0.2, 0.0))
	var leaf := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.28
	sphere.height = 0.10
	leaf.mesh = sphere
	leaf.scale = Vector3(1.5, 0.30, 0.85)
	leaf.position = DISH_POS + Vector3(0.0, 0.08, 0.0)
	leaf.material_override = _material(Color(0.30, 0.62, 0.28), 0.0, 0.65)
	_world.add_child(leaf)
	_tissue = MeshInstance3D.new()
	var clump := SphereMesh.new()
	clump.radius = 0.075
	clump.height = 0.15
	_tissue.mesh = clump
	_tissue.material_override = _material(Color(0.46, 0.36, 0.20), 0.0, 0.9)
	_tissue.position = TISSUE_FROM
	_world.add_child(_tissue)


func _trizol_bottle() -> void:
	var rig := Node3D.new()
	rig.position = BOTTLE_POS
	_world.add_child(rig)
	_cylinder(rig, 0.17, 0.46, Vector3(0.0, 0.23, 0.0),
		Color(0.72, 0.56, 0.28), 0.85)
	_pickable(rig, "trizol", Vector3(0.4, 0.7, 0.4), Vector3(0.0, 0.1, 0.0))
	_cylinder(rig, 0.06, 0.10, Vector3(0.0, 0.44, 0.0), Color(0.85, 0.86, 0.90))
	_add_opening(rig, 0.49)
	_bottle = rig


func _tube_a_rig() -> Node3D:
	var rig := Node3D.new()
	rig.position = TUBE_A_HOME
	_world.add_child(rig)
	var glass := _cylinder(rig, 0.165, 0.74, Vector3(0.0, 0.37, 0.0),
		Color(0.80, 0.87, 0.92), 0.22)
	glass.name = "TubeGlass"
	_add_opening(rig, 0.74)
	_pickable(rig, "tube_a", Vector3(0.42, 0.9, 0.42), Vector3(0.0, 0.35, 0.0))

	_mixed = _cylinder(rig, 0.145, 1.0, Vector3.ZERO, Color(0.78, 0.60, 0.28), 0.9)
	_mixed.name = "MixedLiquid"
	_mixed.scale = Vector3(1.0, 0.001, 1.0)
	_mixed.visible = false
	_organic = _cylinder(rig, 0.145, 1.0, Vector3.ZERO, Color(0.42, 0.30, 0.16), 0.95)
	_organic.name = "OrganicPhase"
	_organic.scale = Vector3(1.0, 0.001, 1.0)
	_organic.visible = false
	_aqueous = _cylinder(rig, 0.143, 1.0, Vector3.ZERO, Color(0.36, 0.76, 0.52), 0.92)
	_aqueous.name = "AqueousPhase"
	_aqueous.scale = Vector3(1.0, 0.001, 1.0)
	_aqueous.visible = false
	return rig


func _tube_b_rig() -> Node3D:
	var rig := Node3D.new()
	rig.position = TUBE_B_HOME
	_world.add_child(rig)
	var glass := _cylinder(rig, 0.155, 0.70, Vector3(0.0, 0.35, 0.0),
		Color(0.80, 0.87, 0.92), 0.22)
	glass.name = "TubeBGlass"
	_add_opening(rig, 0.70)
	_pickable(rig, "tube_b", Vector3(0.4, 0.85, 0.4), Vector3(0.0, 0.33, 0.0))
	_tube_b_liquid = _cylinder(rig, 0.135, 1.0, Vector3.ZERO, Color(0.36, 0.76, 0.52), 0.92)
	_tube_b_liquid.name = "TubeBLiquid"
	_tube_b_liquid.scale = Vector3(1.0, 0.001, 1.0)
	_tube_b_liquid.visible = false
	return rig


func _pipette_rig() -> Node3D:
	var rig := Node3D.new()
	rig.position = PIPETTE_HOME
	_world.add_child(rig)
	_cylinder(rig, 0.045, 0.62, Vector3(0.0, 0.30, 0.0), Color(0.58, 0.62, 0.70), 1.0, 0.6)
	_cylinder(rig, 0.030, 0.10, Vector3(0.0, 0.68, 0.0), Color(0.36, 0.50, 0.78), 1.0, 0.2)
	var tip := _cylinder(rig, 0.018, 0.16, Vector3(0.0, -0.06, 0.0), Color(0.86, 0.90, 0.95), 1.0, 0.0)
	tip.name = "Tip"
	var tip_marker := Marker3D.new()
	tip_marker.name = "TipMarker"
	tip_marker.position = Vector3(0.0, -0.14, 0.0)
	rig.add_child(tip_marker)
	_stream = _cylinder(rig, 0.017, 1.0, Vector3(0.0, -0.16, 0.0),
		Color(0.80, 0.62, 0.32), 0.75)
	_stream.name = "Stream"
	_stream.scale = Vector3(1.0, 0.001, 1.0)
	_stream.visible = false
	_pickable(rig, "pipette", Vector3(0.35, 1.2, 0.35), Vector3(0.0, 0.2, 0.0))
	return rig


func _centrifuge() -> void:
	var body := _box(_world, Vector3(0.95, 0.48, 0.95), Vector3(0.95, 1.16, 0.15),
		Color(0.30, 0.33, 0.38), 0.5)
	_pickable(body, "centrifuge", Vector3(1.1, 0.9, 1.1), Vector3(0.0, 0.2, 0.0))
	_cylinder(_world, 0.34, 0.05, Vector3(0.95, 1.42, 0.15), Color(0.40, 0.44, 0.50), 1.0, 0.6)
	_rotor = Node3D.new()
	_rotor.position = Vector3(0.95, 1.44, 0.15)
	_world.add_child(_rotor)
	_cylinder(_rotor, 0.28, 0.04, Vector3.ZERO, Color(0.68, 0.71, 0.76), 1.0, 0.8)
	for index in 4:
		var angle := TAU * index / 4.0
		var holder := _cylinder(_rotor, 0.055, 0.20,
			Vector3(cos(angle) * 0.20, 0.11, sin(angle) * 0.20), Color(0.82, 0.86, 0.90), 1.0, 0.1)
		holder.rotation_degrees = Vector3(0.0, 0.0, 0.0)



## Step 3 — the DNase vial. The pecan text names the enzyme but reports no
## amount, temperature or time, so the rack carries no numbers.
func _dnase_rack() -> void:
	var rig := Node3D.new()
	rig.position = DNASE_POS
	_world.add_child(rig)
	_box(rig, Vector3(0.40, 0.07, 0.30), Vector3(0.0, 0.035, 0.0), Color(0.34, 0.36, 0.42))
	_cylinder(rig, 0.080, 0.26, Vector3(0.0, 0.20, 0.0), Color(0.34, 0.60, 0.86), 0.78)
	_cylinder(rig, 0.048, 0.06, Vector3(0.0, 0.34, 0.0), Color(0.86, 0.90, 0.95))
	_add_opening(rig, 0.37)
	_pickable(rig, "dnase", Vector3(0.44, 0.52, 0.42), Vector3(0.0, 0.20, 0.0))
	_dnase_vial = rig


## Step 4 — gel cassette (four empty wells) and the spectrophotometer. The wells
## are deliberately empty: the pecan text reports no band, yield or ratio, so no
## band or readout is drawn.
func _quality_station() -> void:
	var rig := Node3D.new()
	rig.position = GEL_POS
	_world.add_child(rig)
	_box(rig, Vector3(0.90, 0.06, 0.58), Vector3(0.0, 0.03, 0.0), Color(0.22, 0.24, 0.28))
	_box(rig, Vector3(0.78, 0.035, 0.44), Vector3(0.0, 0.075, 0.0), Color(0.55, 0.74, 0.84))
	for index in 4:
		var well := _box(rig, Vector3(0.10, 0.014, 0.055),
			Vector3(-0.27 + index * 0.18, 0.096, -0.13), Color(0.11, 0.13, 0.17))
		var film := _box(rig, Vector3(0.09, 0.006, 0.048),
			Vector3(-0.27 + index * 0.18, 0.100, -0.13), Color(0.30, 0.42, 0.50))
		film.visible = false
		_well_films.append(film)
		well.name = "Well%d" % index
	_add_opening(rig, 0.12)
	_pickable(rig, "quality", Vector3(1.02, 0.34, 0.72), Vector3(0.0, 0.06, 0.0))
	_gel_cassette = rig

	var nd := Node3D.new()
	nd.position = NANODROP_POS
	_world.add_child(nd)
	_box(nd, Vector3(0.34, 0.20, 0.32), Vector3(0.0, 0.10, 0.0), Color(0.30, 0.33, 0.40), 0.4)
	_cylinder(nd, 0.045, 0.03, Vector3(0.0, 0.215, 0.0), Color(0.72, 0.76, 0.82), 1.0, 0.6)
	_nanodrop_arm = Node3D.new()
	_nanodrop_arm.position = Vector3(0.15, 0.235, 0.0)
	nd.add_child(_nanodrop_arm)
	_box(_nanodrop_arm, Vector3(0.26, 0.025, 0.05), Vector3(-0.13, 0.0, 0.0), Color(0.44, 0.48, 0.55), 0.7)
	_pickable(nd, "quality", Vector3(0.44, 0.36, 0.42), Vector3(0.0, 0.14, 0.0))
	_nanodrop = nd
	_scan_beam = _box(nd, Vector3(0.012, 0.16, 0.012), Vector3(0.0, 0.14, 0.0),
		Color(0.55, 0.86, 1.0))
	_scan_beam.visible = false


## Step 5 — PAGE cassette and the tube the excised slice goes into. The size
## window (18-30 nt) is reported; gel percentage and recovery are not.
func _page_station() -> void:
	var rig := Node3D.new()
	rig.position = PAGE_POS
	_world.add_child(rig)
	_box(rig, Vector3(0.62, 0.06, 0.36), Vector3(0.0, 0.03, 0.0), Color(0.24, 0.26, 0.31))
	var slab := _box(rig, Vector3(0.46, 0.40, 0.045), Vector3(0.0, 0.24, 0.0),
		Color(0.52, 0.70, 0.80))
	slab.rotation_degrees = Vector3(-10.0, 0.0, 0.0)
	_box(rig, Vector3(0.52, 0.03, 0.06), Vector3(0.0, 0.45, 0.06), Color(0.40, 0.43, 0.49), 0.5)
	_add_opening(rig, 0.14)
	_pickable(rig, "page", Vector3(0.68, 0.56, 0.46), Vector3(0.0, 0.16, 0.0))
	_page_cassette = rig

	_gel_slice = _box(_world, Vector3(0.13, 0.025, 0.07), Vector3.ZERO,
		Color(0.62, 0.82, 0.92))
	_gel_slice.visible = false

	_slice_tube = Node3D.new()
	_slice_tube.position = SLICE_TUBE_POS
	_world.add_child(_slice_tube)
	_cylinder(_slice_tube, 0.11, 0.42, Vector3(0.0, 0.21, 0.0), Color(0.80, 0.87, 0.92), 0.24)
	_add_opening(_slice_tube, 0.42)
	_pickable(_slice_tube, "page", Vector3(0.30, 0.50, 0.30), Vector3(0.0, 0.22, 0.0))



## Step 6 — cDNA synthesis. 1 ug total RNA per sample is the one reported input
## amount, so it is the only quantity printed on this station.
func _cdna_station() -> void:
	var rig := Node3D.new()
	rig.position = CDNA_POS
	_world.add_child(rig)
	_cdna_block = _box(rig, Vector3(0.56, 0.18, 0.42), Vector3(0.0, 0.09, 0.0),
		Color(0.28, 0.30, 0.36), 0.3)
	_block_glow = _box(rig, Vector3(0.62, 0.24, 0.48), Vector3(0.0, 0.11, 0.0),
		Color(0.95, 0.62, 0.30))
	_block_glow.material_override = _material(Color(0.95, 0.62, 0.30), 0.0, 0.4, 0.22)
	_block_glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_block_glow.visible = false
	_cdna_tube = Node3D.new()
	_cdna_tube.position = Vector3(0.0, 0.32, 0.0)
	rig.add_child(_cdna_tube)
	_cylinder(_cdna_tube, 0.065, 0.24, Vector3(0.0, 0.12, 0.0), Color(0.80, 0.87, 0.92), 0.26)
	var liquid := _cylinder(_cdna_tube, 0.052, 1.0, Vector3.ZERO, Color(0.42, 0.72, 0.90), 0.9)
	liquid.name = "CdnaLiquid"
	liquid.scale = Vector3(1.0, 0.10, 1.0)
	liquid.position = Vector3(0.0, 0.085, 0.0)
	_add_opening(_cdna_tube, 0.24)
	_pickable(rig, "cdna", Vector3(0.62, 0.56, 0.48), Vector3(0.0, 0.24, 0.0))


## Steps 7-17 — the analogue kiosk stands apart from the bench, on the left, and
## is amber. It is where a transferred protocol is *reported*, never executed: no
## pecan vessel moves for an analogue step.
func _analogue_kiosk() -> void:
	var rig := Node3D.new()
	rig.name = "AnalogueKiosk"
	rig.position = KIOSK_POS
	_world.add_child(rig)
	_box(rig, Vector3(0.10, 1.34, 0.10), Vector3(0.0, 0.67, 0.0), Color(0.35, 0.37, 0.42))
	_analogue_card = _box(rig, Vector3(1.00, 0.66, 0.06), Vector3(0.0, 1.34, 0.0),
		Color(0.92, 0.68, 0.22))
	_pickable(rig, "reference", Vector3(1.10, 0.78, 0.30), Vector3(0.0, 1.34, 0.0))
	var label := Label3D.new()
	label.name = "CardText"
	label.text = "ANALOGUE\nnot validated on pecan\nNORWAY SPRUCE"
	label.font_size = 26
	label.pixel_size = 0.002
	label.position = Vector3(0.0, 1.38, 0.08)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = Color(0.16, 0.11, 0.03)
	rig.add_child(label)


## Step 18 — the unresolved method-review card, deliberately muted and separate
## from both the pecan bench and the analogue kiosk.
func _method_review_card() -> void:
	var rig := Node3D.new()
	rig.position = CAVEAT_POS
	_world.add_child(rig)
	_box(rig, Vector3(0.08, 1.10, 0.08), Vector3(0.0, 0.55, 0.0), Color(0.34, 0.36, 0.41))
	_caveat_card = _box(rig, Vector3(0.86, 0.58, 0.06), Vector3(0.0, 1.12, 0.0),
		Color(0.60, 0.64, 0.72))
	_pickable(rig, "caveat", Vector3(0.96, 0.70, 0.28), Vector3(0.0, 1.12, 0.0))
	var label := Label3D.new()
	label.text = "? METHOD REVIEW\nno universal protocol\nunresolved for pecan"
	label.font_size = 28
	label.pixel_size = 0.002
	label.position = Vector3(0.0, 1.12, 0.08)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = Color(0.08, 0.10, 0.14)
	rig.add_child(label)


func _particles() -> void:
	_bubbles = CPUParticles3D.new()
	_bubbles.position = TUBE_A_HOME + Vector3(0.0, 0.42, 0.0)
	_bubbles.emitting = false
	_bubbles.amount = 24
	_bubbles.lifetime = 0.7
	_bubbles.direction = Vector3.UP
	_bubbles.spread = 18.0
	_bubbles.initial_velocity_min = 0.08
	_bubbles.initial_velocity_max = 0.22
	_bubbles.gravity = Vector3(0.0, 0.25, 0.0)
	_bubbles.scale_amount_min = 0.012
	_bubbles.scale_amount_max = 0.03
	var bubble_mesh := SphereMesh.new()
	bubble_mesh.radius = 1.0
	bubble_mesh.height = 2.0
	_bubbles.mesh = bubble_mesh
	_bubbles.material_override = _material(Color(0.90, 0.95, 1.0), 0.0, 0.2, 0.7)
	_world.add_child(_bubbles)

	_droplets = CPUParticles3D.new()
	_droplets.emitting = false
	_droplets.amount = 20
	_droplets.lifetime = 0.5
	_droplets.direction = Vector3.DOWN
	_droplets.gravity = Vector3(0.0, -6.0, 0.0)
	_droplets.initial_velocity_min = 0.4
	_droplets.initial_velocity_max = 1.2
	_droplets.scale_amount_min = 0.008
	_droplets.scale_amount_max = 0.018
	var drop_mesh := SphereMesh.new()
	drop_mesh.radius = 1.0
	drop_mesh.height = 2.0
	_droplets.mesh = drop_mesh
	_droplets.material_override = _material(Color(0.85, 0.66, 0.36), 0.0, 0.3, 0.9)
	_world.add_child(_droplets)

	_incubate_ring = _cylinder(_world, 0.24, 0.012, TUBE_B_HOME + Vector3(0.0, 0.30, 0.0),
		Color(0.55, 0.78, 1.0), 0.5)
	_incubate_ring.visible = false



# ------------------------------------------------------------- step metadata


func step_count() -> int:
	return STEPS.size()


func step_at(t: float) -> int:
	for index in STEPS.size():
		if t < float(STEPS[index]["end"]) or index == STEPS.size() - 1:
			return index
	return STEPS.size() - 1


func step_index_of(step_id: String) -> int:
	for index in STEPS.size():
		if str(STEPS[index]["id"]) == step_id:
			return index
	return -1


func step_label(index: int) -> String:
	return str(STEPS[clampi(index, 0, STEPS.size() - 1)]["label"])


func step_mode(index: int) -> String:
	return str(STEPS[clampi(index, 0, STEPS.size() - 1)]["mode"])


func step_station(index: int) -> String:
	return str(STEPS[clampi(index, 0, STEPS.size() - 1)]["station"])


func step_id(index: int) -> String:
	return str(STEPS[clampi(index, 0, STEPS.size() - 1)]["id"])


func step_branch(index: int) -> String:
	return str(STEPS[clampi(index, 0, STEPS.size() - 1)].get("branch", ""))


func step_start(index: int) -> float:
	return float(STEPS[clampi(index, 0, STEPS.size() - 1)]["start"])


func step_end(index: int) -> float:
	return float(STEPS[clampi(index, 0, STEPS.size() - 1)]["end"])


func step_duration(index: int) -> float:
	var clamped := clampi(index, 0, STEPS.size() - 1)
	return float(STEPS[clamped]["end"]) - float(STEPS[clamped]["start"])


func step_local(t: float) -> float:
	var index := step_at(t)
	return clampf(t - step_start(index), 0.0, step_duration(index))


func total_seconds() -> float:
	return TOTAL_SECONDS


func first_step_for_branch(branch: String) -> int:
	for index in STEPS.size():
		if step_branch(index) == branch:
			return index
	return -1


func set_branch(branch: String) -> void:
	if branch == "spruce" or branch == "pigeonpea":
		_branch = branch
	_update_card(step_at(_clock))


## The kiosk always names the species and, while an analogue step is current,
## which transferred step it is. Nothing on the pecan bench moves.
func _update_card(index: int) -> void:
	if _world == null:
		return
	var card := _world.get_node_or_null("AnalogueKiosk/CardText")
	if not (card is Label3D):
		return
	var species := "SPRUCE" if _branch == "spruce" else "PIGEONPEA"
	if step_mode(index) == "analogue":
		(card as Label3D).text = "%s ANALOGUE\nstep %d of %d\nnot validated on pecan" % [
			species, index + 1, STEPS.size()]
	else:
		(card as Label3D).text = "%s ANALOGUE\nnot validated on pecan\n%s" % [
			species, "transferred protocol"]


func branch() -> String:
	return _branch


# Compatibility names kept for the replay harness: one "operation" is one step.
func operation_at(t: float) -> int:
	return step_at(t)


func operation_count() -> int:
	return STEPS.size()


func operation_label(index: int) -> String:
	return step_label(index)


func operation_step(index: int) -> String:
	return step_id(index)


func operation_start(index: int) -> float:
	return step_start(index)


func clock() -> float:
	return _clock


func mode_colour(mode: String) -> Color:
	match mode:
		"physical":
			return MODE_PHYSICAL
		"observe":
			return MODE_OBSERVE
		"analogue":
			return MODE_ANALOGUE
		_:
			return MODE_CAVEAT


func mode_hint(index: int) -> String:
	var id := step_id(index)
	match id:
		"pecan_sample_handling":
			return "pecan bench - tissue handling; storage duration not reported"
		"pecan_trizol_extraction":
			return "pecan bench - TRIzol; volume, speed and timings not reported"
		"pecan_dnase_treatment":
			return "pecan bench - DNase; amount, temperature and time not reported"
		"pecan_quality_assessment":
			return "observation only - no yield, ratio or RIN was reported"
		"pecan_small_rna_enrichment":
			return "pecan bench - 18-30 nt window; gel % and recovery not reported"
		"pecan_cdna_synthesis":
			return "pecan bench - 1 ug RNA reported; volume and temperature not"
		"method_review_caveat":
			return "method review - no universal RNA protocol; unresolved for pecan"
		"analogue_pigeonpea_quality":
			return "analogue result - pigeonpea values; not pecan measurements"
	if step_mode(index) == "analogue":
		return "analogue hypothesis - %s only; NOT validated on pecan" % step_branch(index)
	return "step %d of %d" % [index + 1, STEPS.size()]



# -------------------------------------------------------------- simulation


## Deterministic state for one instant. Everything visible is derived here.
func apply_clock(t: float) -> void:
	_clock = clampf(t, 0.0, TOTAL_SECONDS)
	var index := step_at(_clock)
	var local := _clock - step_start(index)
	var mode := step_mode(index)
	_last_op = index

	_hud.text = "%d/%d  %s" % [index + 1, STEPS.size(), step_label(index)]
	_hud.modulate = mode_colour(mode)
	_hud_sub.text = mode_hint(index)
	_hud_sub.modulate = mode_colour(mode).lightened(0.2)
	_update_card(index)

	var st := _bench_baseline(index)
	match mode:
		"physical":
			match step_id(index):
				"pecan_sample_handling":
					_op_sample(st, local)
				"pecan_trizol_extraction":
					_op_trizol(st, local)
				"pecan_dnase_treatment":
					_op_dnase(st, local)
				"pecan_small_rna_enrichment":
					_op_page(st, local)
				"pecan_cdna_synthesis":
					_op_cdna(st, local)
		"observe":
			_op_quality(st, local)
		"analogue":
			_op_analogue(st, index)
		"caveat":
			_op_caveat(st)
	_apply_state(st)


## The bench after every completed pecan step. Steps 7-18 start from this
## settled state, so the bench does not rewind when the analogue lane begins.
func _bench_baseline(index: int) -> Dictionary:
	var settled := index >= 6
	var running_trizol := index == 1
	return {
		"mode": step_mode(index),
		"tissue_pos": TISSUE_FROM,
		"tissue_in_tube": index >= 1,
		"tube_a_pos": TUBE_A_HOME,
		"tube_a_wobble": 0.0,
		"rotor": 0.0,
		"tube_a_liquid": 0.0 if running_trizol or index == 0 else 0.58,
		"split": 0.0 if running_trizol or index == 0 else 1.0,
		"aqueous_removed": 0.0 if index < 2 else 1.0,
		"tube_b_liquid": 0.0 if index < 2 else 0.36,
		"dnase": 0.0 if index < 3 else 1.0,
		"pipette": PIPETTE_HOME,
		"stream": null,
		"bubbles": false,
		"incubate": 0.0,
		"gel_loaded": index >= 4,
		"nanodrop": 0.0,
		"nanodrop_arm": 0.0,
		"slice": 1.0 if index >= 5 else 0.0,
		"cdna": 1.0 if settled else 0.0,
		"analogue": 0.0,
		"caveat": 0.0,
	}


func _op_sample(st: Dictionary, s: float) -> void:
	var opening_a := _opening(_tube_a)
	if s < 1.75:
		var k := _smooth(_norm(s, 0.15, 1.55))
		st["tissue_pos"] = _arc(TISSUE_FROM, opening_a.global_position + Vector3.UP * 0.02, k, 0.45)
	else:
		st["tissue_in_tube"] = true


func _op_trizol(st: Dictionary, s: float) -> void:
	st["tissue_in_tube"] = true
	var opening_a := _opening(_tube_a)
	var opening_b := _opening(_tube_b)
	var bottle := _opening(_bottle)
	var home := PIPETTE_HOME
	var at_bottle := _pipette_at(bottle, 0.09)
	var over_a := _pipette_at(opening_a, 0.09)
	var dip_a := _pipette_at(opening_a, -0.16)
	var over_b := _pipette_at(opening_b, 0.09)

	# 1. aspirate TRIzol from the bottle
	if s < 0.75:
		var k := _smooth(_norm(s, 0.45, 0.62))
		st["pipette"] = home.lerp(at_bottle, k)
		if s >= 0.62:
			st["pipette"] = at_bottle.lerp(_pipette_at(bottle, -0.10), _smooth(_norm(s, 0.62, 0.75)))
	elif s < 1.40:
		st["pipette"] = at_bottle.lerp(over_a, _smooth(_norm(s, 0.75, 1.40)))
	elif s < 2.70:
		# 2. dispense over the tissue; the liquid rises only while aligned
		st["pipette"] = over_a
		st["stream"] = opening_a
		if _aligned(opening_a):
			st["tube_a_liquid"] = 0.58 * _smooth(_norm(s, 1.40, 2.70))
	elif s < 3.60:
		# 3. mix
		st["pipette"] = home
		st["tube_a_wobble"] = sin((s - 2.70) * 11.0) * 0.15 * (1.0 - _norm(s, 3.25, 3.60) * 0.4)
		st["bubbles"] = true
		st["tube_a_liquid"] = 0.58
	elif s < 4.70:
		# 4. centrifuge
		st["pipette"] = home
		st["tube_a_liquid"] = 0.58
		var into := _smooth(_norm(s, 3.60, 3.95))
		st["tube_a_pos"] = TUBE_A_HOME.lerp(ROTOR_SLOT, into)
		if s > 4.35:
			st["tube_a_pos"] = ROTOR_SLOT.lerp(TUBE_A_HOME, _smooth(_norm(s, 4.35, 4.70)))
		st["rotor"] = TAU * 10.0 * _ease_in_out(_norm(s, 3.95, 4.45))
	else:
		# 5. phase separation and transfer of the upper phase
		st["tube_a_liquid"] = 0.58
		st["split"] = _smooth(_norm(s, 4.70, 5.20))
		if s < 5.00:
			st["pipette"] = over_a.lerp(dip_a, _smooth(_norm(s, 4.70, 5.00)))
		elif s < 5.35:
			st["pipette"] = dip_a.lerp(over_b, _smooth(_norm(s, 5.00, 5.35)))
		elif s < 6.20:
			st["pipette"] = over_b
			st["stream"] = opening_b
			if _aligned(opening_b):
				st["tube_b_liquid"] = 0.36 * _smooth(_norm(s, 5.35, 6.40))
			st["aqueous_removed"] = 0.92 * _smooth(_norm(s, 5.50, 6.20))
		elif s < 6.50:
			st["pipette"] = over_b.lerp(home, _smooth(_norm(s, 6.20, 6.50)))
			st["tube_b_liquid"] = 0.36
			st["aqueous_removed"] = 0.92



func _op_dnase(st: Dictionary, s: float) -> void:
	var vial := _opening(_dnase_vial)
	var opening_b := _opening(_tube_b)
	var home := PIPETTE_HOME
	var at_vial := _pipette_at(vial, -0.06)
	var over_b := _pipette_at(opening_b, 0.09)
	if s < 0.40:
		st["pipette"] = home
	elif s < 1.10:
		st["pipette"] = home.lerp(at_vial, _smooth(_norm(s, 0.40, 1.10)))
	elif s < 1.60:
		st["pipette"] = at_vial.lerp(over_b, _smooth(_norm(s, 1.10, 1.60)))
	elif s < 2.60:
		st["pipette"] = over_b
		st["stream"] = opening_b
		if _aligned(opening_b):
			st["dnase"] = _smooth(_norm(s, 1.60, 2.60))
	elif s < 3.00:
		st["pipette"] = over_b.lerp(home, _smooth(_norm(s, 2.60, 3.00)))
		st["dnase"] = 1.0
	else:
		st["pipette"] = home
		st["dnase"] = 1.0
	st["incubate"] = sin(_norm(s, 2.60, 4.00) * PI)


## Observation: the sample is loaded into an empty well and the spectrophotometer
## arm is lowered. No band, ratio or concentration is drawn because none is
## reported by the pecan source.
func _op_quality(st: Dictionary, s: float) -> void:
	var opening_b := _opening(_tube_b)
	var gel := _opening(_gel_cassette)
	var home := PIPETTE_HOME
	var dip_b := _pipette_at(opening_b, -0.16)
	var over_gel := _pipette_at(gel, 0.07)
	if s < 0.45:
		st["pipette"] = home
	elif s < 1.00:
		st["pipette"] = home.lerp(dip_b, _smooth(_norm(s, 0.45, 1.00)))
	elif s < 1.65:
		st["pipette"] = dip_b.lerp(over_gel, _smooth(_norm(s, 1.00, 1.65)))
	elif s < 2.40:
		st["pipette"] = over_gel
		st["stream"] = gel
		if _aligned(gel):
			st["gel_loaded"] = true
	elif s < 2.85:
		st["pipette"] = over_gel.lerp(home, _smooth(_norm(s, 2.40, 2.85)))
		st["gel_loaded"] = true
	else:
		st["pipette"] = home
		st["gel_loaded"] = true
	var active := _smooth(_norm(s, 2.20, 3.00))
	if s > 3.70:
		active *= 1.0 - _smooth(_norm(s, 3.70, 4.00)) * 0.5
	st["nanodrop"] = active
	st["nanodrop_arm"] = _smooth(_norm(s, 2.20, 2.90))


func _op_page(st: Dictionary, s: float) -> void:
	var opening_b := _opening(_tube_b)
	var page := _opening(_page_cassette)
	var home := PIPETTE_HOME
	var dip_b := _pipette_at(opening_b, -0.16)
	var over_page := _pipette_at(page, 0.07)
	if s < 0.45:
		st["pipette"] = home
	elif s < 1.00:
		st["pipette"] = home.lerp(dip_b, _smooth(_norm(s, 0.45, 1.00)))
	elif s < 1.75:
		st["pipette"] = dip_b.lerp(over_page, _smooth(_norm(s, 1.00, 1.75)))
	elif s < 2.45:
		st["pipette"] = over_page
		st["stream"] = page
	elif s < 2.85:
		st["pipette"] = over_page.lerp(home, _smooth(_norm(s, 2.45, 2.85)))
	else:
		st["pipette"] = home
	st["slice"] = _smooth(_norm(s, 2.55, 3.90))


func _op_cdna(st: Dictionary, s: float) -> void:
	var opening_b := _opening(_tube_b)
	var cdna := _opening(_cdna_tube)
	var home := PIPETTE_HOME
	var dip_b := _pipette_at(opening_b, -0.16)
	var over_cdna := _pipette_at(cdna, 0.09)
	if s < 0.40:
		st["pipette"] = home
	elif s < 0.95:
		st["pipette"] = home.lerp(dip_b, _smooth(_norm(s, 0.40, 0.95)))
	elif s < 1.55:
		st["pipette"] = dip_b.lerp(over_cdna, _smooth(_norm(s, 0.95, 1.55)))
	elif s < 2.20:
		st["pipette"] = over_cdna
		st["stream"] = cdna
	elif s < 2.60:
		st["pipette"] = over_cdna.lerp(home, _smooth(_norm(s, 2.20, 2.60)))
	else:
		st["pipette"] = home
	st["cdna"] = _smooth(_norm(s, 2.10, 3.00))


## No pecan vessel moves here: the amber kiosk is the only thing that responds.
func _op_analogue(st: Dictionary, index: int) -> void:
	var local := _clock - step_start(index)
	st["analogue"] = 0.55 + 0.45 * sin(_norm(local, 0.0, step_duration(index)) * PI)


func _op_caveat(st: Dictionary) -> void:
	var index := STEPS.size() - 1
	var local := _clock - step_start(index)
	st["caveat"] = 0.55 + 0.45 * sin(_norm(local, 0.0, step_duration(index)) * PI)



# ------------------------------------------------------------ state -> scene


func _apply_state(st: Dictionary) -> void:
	_state = st

	# vessels first, so anything riding a vessel can read its position
	_tube_a.position = st["tube_a_pos"]
	_tube_a.rotation.z = float(st["tube_a_wobble"])
	_rotor.rotation.y = float(st["rotor"])
	_pipette.position = st["pipette"]

	_tissue.visible = true
	if bool(st["tissue_in_tube"]):
		_tissue.position = _tube_a.position + Vector3(0.0, 0.16, 0.0)
	else:
		_tissue.position = st["tissue_pos"]

	var total := float(st["tube_a_liquid"]) * 0.62
	var split := float(st["split"])
	var organic_h := total * 0.55 * split
	var mixed_h := total * (1.0 - split)
	var aqueous_h := total * 0.45 * split * (1.0 - float(st["aqueous_removed"]) * 0.92)
	if split <= 0.0:
		aqueous_h = 0.0
	_set_column(_mixed, mixed_h, 0.10)
	_set_column(_organic, organic_h, 0.10)
	_set_column(_aqueous, aqueous_h, 0.10 + organic_h)
	_set_column(_tube_b_liquid, float(st["tube_b_liquid"]) * 0.62, 0.08)
	if _tube_b_liquid.material_override is StandardMaterial3D:
		var mat := _tube_b_liquid.material_override as StandardMaterial3D
		mat.albedo_color = Color(0.36, 0.76, 0.52).lerp(
			Color(0.36, 0.62, 0.86), float(st["dnase"]) * 0.75)

	var stream_opening: Node3D = st["stream"]
	_stream.visible = false
	if stream_opening != null:
		var mouth := stream_opening.global_position
		var tip := _tip_world()
		if Vector2(tip.x - mouth.x, tip.z - mouth.z).length() < 0.01:
			_stream_to(stream_opening)
	_droplets.emitting = _stream.visible
	_droplets.position = _tip_world()
	_bubbles.emitting = bool(st["bubbles"])
	_bubbles.position = _tube_a.position + Vector3(0.0, 0.42, 0.0)

	var incubate := clampf(float(st["incubate"]), 0.0, 1.0)
	_incubate_ring.visible = incubate > 0.02
	_incubate_ring.position = TUBE_B_HOME + Vector3(0.0, 0.62 + 0.03 * sin(_clock * 6.0), 0.0)
	_incubate_ring.scale = Vector3(1.0 + incubate * 0.25, 1.0, 1.0 + incubate * 0.25)

	var loaded := bool(st["gel_loaded"])
	for film in _well_films:
		(film as MeshInstance3D).visible = loaded
	var scan := clampf(float(st["nanodrop"]), 0.0, 1.0)
	_scan_beam.visible = scan > 0.02
	_scan_beam.position = Vector3(0.0, 0.13 + 0.05 * sin(_clock * 5.0), 0.0)
	_nanodrop_arm.rotation.z = -deg_to_rad(75.0) * float(st["nanodrop_arm"])

	var slice := clampf(float(st["slice"]), 0.0, 1.0)
	_gel_slice.visible = slice > 0.001
	var slice_from: Vector3 = PAGE_POS + Vector3(0.10, 0.18, 0.0)
	var slice_to: Vector3 = SLICE_TUBE_POS + Vector3(0.0, 0.34, 0.0)
	var lift := _smooth(_norm(slice, 0.0, 0.55))
	var carry := _smooth(_norm(slice, 0.35, 1.0))
	var start := slice_from + Vector3(0.0, lift * 0.30, 0.0)
	_gel_slice.position = start.lerp(slice_to, carry)

	var cDNA := clampf(float(st["cdna"]), 0.0, 1.0)
	_cdna_tube.position = Vector3(0.0, lerpf(0.32, 0.13, cDNA), 0.0)
	_block_glow.visible = cDNA > 0.4

	var analogue := clampf(float(st["analogue"]), 0.0, 1.0)
	_analogue_card.scale = Vector3.ONE * (1.0 + 0.07 * analogue)
	var caveat := clampf(float(st["caveat"]), 0.0, 1.0)
	_caveat_card.scale = Vector3.ONE * (1.0 + 0.05 * caveat)


## A cylinder mesh has unit height, so `height` is its scale; `base` is the Y of
## its bottom inside the tube in local space.
func _set_column(mesh: MeshInstance3D, height: float, base: float) -> void:
	if mesh == null:
		return
	var clamped := maxf(height, 0.001)
	mesh.visible = height > 0.002
	mesh.scale = Vector3(1.0, clamped, 1.0)
	mesh.position = Vector3(0.0, base + clamped * 0.5, 0.0)


static func _norm(value: float, start: float, end: float) -> float:
	if end <= start:
		return 1.0
	return clampf((value - start) / (end - start), 0.0, 1.0)


static func _smooth(t: float) -> float:
	var x := clampf(t, 0.0, 1.0)
	return x * x * (3.0 - 2.0 * x)


static func _ease_in_out(t: float) -> float:
	var x := clampf(t, 0.0, 1.0)
	return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


## A simple arc, so the tissue clump is visibly lifted and dropped rather than
## sliding through the bench.
static func _arc(from: Vector3, to: Vector3, k: float, lift: float) -> Vector3:
	var flat := from.lerp(to, k)
	flat.y += sin(clampf(k, 0.0, 1.0) * PI) * lift
	return flat



# ------------------------------------------------------------------ harness


func probes() -> Dictionary:
	var tip := _tip_world()
	var opening_a := _opening(_tube_a)
	var opening_b := _opening(_tube_b)
	var mouth_a := opening_a.global_position if opening_a != null else Vector3.ZERO
	var mouth_b := opening_b.global_position if opening_b != null else Vector3.ZERO
	var stream_bottom := Vector3.ZERO
	if _stream.visible:
		stream_bottom = _stream.global_position - Vector3(0.0, _stream.scale.y * 0.5, 0.0)
	var openings := {
		"dnase": _opening(_dnase_vial),
		"quality": _opening(_gel_cassette),
		"page": _opening(_page_cassette),
		"cdna": _opening(_cdna_tube),
	}
	var alignment := {}
	for key in openings.keys():
		var opening: Marker3D = openings[key]
		var mouth := opening.global_position if opening != null else Vector3.ZERO
		alignment[key] = Vector2(tip.x - mouth.x, tip.z - mouth.z).length()
	return {
		"clock": _clock,
		"step": _last_op,
		"step_id": step_id(_last_op),
		"mode": step_mode(_last_op),
		"branch": _branch,
		"operation": _last_op,
		"tissue": _tissue.position,
		"tube_a": _tube_a.position,
		"tube_b": _tube_b.position,
		"tube_a_wobble": _tube_a.rotation.z,
		"mixed_height": _mixed.scale.y if _mixed.visible else 0.0,
		"organic_height": _organic.scale.y if _organic.visible else 0.0,
		"aqueous_height": _aqueous.scale.y if _aqueous.visible else 0.0,
		"tube_b_height": _tube_b_liquid.scale.y if _tube_b_liquid.visible else 0.0,
		"rotor_angle": _rotor.rotation.y,
		"pipette": _pipette.position,
		"tip": tip,
		"opening_a": mouth_a,
		"opening_b": mouth_b,
		"alignment_a": Vector2(tip.x - mouth_a.x, tip.z - mouth_a.z).length(),
		"alignment_b": Vector2(tip.x - mouth_b.x, tip.z - mouth_b.z).length(),
		"alignment_dnase": alignment["dnase"],
		"alignment_quality": alignment["quality"],
		"alignment_page": alignment["page"],
		"alignment_cdna": alignment["cdna"],
		"stream": _stream.visible,
		"stream_bottom": stream_bottom,
		"droplets": _droplets.emitting,
		"droplets_position": _droplets.position,
		"bubbles": _bubbles.emitting,
		"dnase": float(_state.get("dnase", 0.0)),
		"incubate": _incubate_ring.visible,
		"gel_loaded": bool(_state.get("gel_loaded", false)),
		"nanodrop": float(_state.get("nanodrop", 0.0)),
		"scan_beam": _scan_beam.visible,
		"slice": float(_state.get("slice", 0.0)),
		"slice_position": _gel_slice.position,
		"cdna": float(_state.get("cdna", 0.0)),
		"cdna_position": _cdna_tube.position,
		"block_glow": _block_glow.visible,
		"analogue_pulse": float(_state.get("analogue", 0.0)),
		"caveat_pulse": float(_state.get("caveat", 0.0)),
		"camera_goal": _target_goal,
	}


func hud_text() -> String:
	return _hud.text + "\n" + _hud_sub.text


func reset_view() -> void:
	reset_camera()
