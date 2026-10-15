class_name ReplayVesselView
extends SubViewportContainer
## An orbitable 3D schematic of the fermentation vessel.
##
## What is drawn here, and why:
##
##   * the vessel body is sized from `fermenter_nominal_volume` (7.5 L, reported);
##   * the liquid column is sized from `starting_medium_volume` (4.0 L, reported);
##   * the liquid's colour is a legend-mapped encoding of the digitized OD600.
##
## What is deliberately NOT drawn, because the model does not contain it:
##
##   * no particles, cells, bubbles or solids -- the model publishes no
##     concentration field, no cell count and no size distribution;
##   * no flow, shear, mixing or swirl -- agitation rate, air flow and kLa are
##     all explicitly unreported, which is why `dissolved_oxygen` is unknown;
##   * no moving impeller -- the shaft is static for that same reason;
##   * no temperature gradient -- 37 degC is a single reported set point;
##   * the liquid level never animates -- the working volume is reported once
##     and no feed or evaporation is reported, so the level is a constant.
##
## The liquid is therefore a bulk scalar visualisation, not a field. It is
## labelled as an encoding wherever it is shown.

const SHAFT_HEIGHT_RATIO := 0.92
const VESSEL_RADIUS := 0.55
const VESSEL_HEIGHT := 2.6
## Height of the vessel floor, just above the base flange.
const FILL_BASE_Y := 0.11

var _viewport: SubViewport
var _world: Node3D
var _camera: Camera3D
var _liquid: MeshInstance3D
var _liquid_mat: StandardMaterial3D
var _pitch_axis: Node3D
var _yaw := deg_to_rad(-28.0)
var _pitch := deg_to_rad(-8.0)
var _distance := 6.4
var _dragging := false
var _target := Vector3(0.0, VESSEL_HEIGHT * 0.45, 0.0)
var _turbidity := 0.0

signal orbit_changed(azimuth_deg: float, elevation_deg: float, distance: float)


func _ready() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_viewport = SubViewport.new()
	_viewport.own_world_3d = true
	_viewport.transparent_bg = false
	_viewport.msaa_3d = Viewport.MSAA_4X
	_viewport.handle_input_locally = false
	# A SubViewport does not present by default; without this the container
	# stays blank no matter how complete the 3D scene is.
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)
	_build_world()
	_apply_camera()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		match mb.button_index:
			MOUSE_BUTTON_LEFT:
				_dragging = mb.pressed
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
		_pitch = clampf(_pitch - mm.relative.y * 0.008, deg_to_rad(-78.0), deg_to_rad(78.0))
		_apply_camera()
		accept_event()


func _zoom(direction: float) -> void:
	_distance = clampf(_distance + direction * 0.45, 3.2, 14.0)
	_apply_camera()


## Reset the camera to its documented home position.
func reset_camera() -> void:
	_yaw = deg_to_rad(-28.0)
	_pitch = deg_to_rad(-8.0)
	_distance = 6.4
	_apply_camera()


func _apply_camera() -> void:
	if _camera == null:
		return
	# A Camera3D looks down its own -Z, so it must sit at target + basis.z * d.
	# Placing it at target - basis.z * d points it away from the subject.
	var basis := Basis.from_euler(Vector3(_pitch, _yaw, 0.0))
	_camera.transform = Transform3D(basis, _target + basis.z * _distance)
	orbit_changed.emit(rad_to_deg(_yaw), rad_to_deg(_pitch), _distance)


# ---------------------------------------------------------------- 3D content

func _build_world() -> void:
	_world = Node3D.new()
	_viewport.add_child(_world)

	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.055, 0.063, 0.078)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.52, 0.56, 0.64)
	e.ambient_light_energy = 0.65
	env.environment = e
	_world.add_child(env)

	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-52.0, -128.0, 0.0)
	key.light_energy = 1.15
	key.light_color = Color(1.0, 0.97, 0.92)
	key.shadow_enabled = true
	_world.add_child(key)

	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-14.0, 58.0, 0.0)
	rim.light_energy = 0.45
	rim.light_color = Color(0.70, 0.80, 1.0)
	rim.shadow_enabled = false
	_world.add_child(rim)

	_ground()
	_vessel()
	_liquid_column()
	_static_hardware()

	_pitch_axis = Node3D.new()
	_world.add_child(_pitch_axis)
	_camera = Camera3D.new()
	_camera.fov = 46.0
	_pitch_axis.add_child(_camera)


func _ground() -> void:
	var plane := PlaneMesh.new()
	plane.size = Vector2(16.0, 16.0)
	var mi := MeshInstance3D.new()
	mi.mesh = plane
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.10, 0.11, 0.13)
	mat.roughness = 0.92
	mat.metallic = 0.0
	mi.material_override = mat
	_world.add_child(mi)


func _vessel() -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = VESSEL_RADIUS
	mesh.bottom_radius = VESSEL_RADIUS
	mesh.height = VESSEL_HEIGHT
	mesh.radial_segments = 56
	mesh.rings = 1
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
	glass.metallic = 0.0
	glass.rim_enabled = true
	glass.rim = 0.6
	body.material_override = glass
	_world.add_child(body)

	# Base flange, so the vessel reads as standing on something. The top face is
	# left open: a capped disc this size shows through the glass as a starburst
	# of triangles and reads as debris inside the culture.
	var flange := CylinderMesh.new()
	flange.top_radius = VESSEL_RADIUS * 1.14
	flange.bottom_radius = VESSEL_RADIUS * 1.14
	flange.height = 0.09
	flange.radial_segments = 56
	flange.cap_top = false
	var fm := MeshInstance3D.new()
	fm.mesh = flange
	fm.position = Vector3(0.0, 0.045, 0.0)
	var fmat := StandardMaterial3D.new()
	fmat.albedo_color = Color(0.30, 0.33, 0.37)
	fmat.roughness = 0.55
	fmat.metallic = 0.65
	fm.material_override = fmat
	_world.add_child(fm)


func _liquid_column() -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = VESSEL_RADIUS * 0.965
	mesh.bottom_radius = VESSEL_RADIUS * 0.965
	mesh.height = 1.0          # unit height; scaled to the working volume
	mesh.radial_segments = 56
	_liquid = MeshInstance3D.new()
	_liquid.mesh = mesh
	_liquid_mat = StandardMaterial3D.new()
	_liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_liquid_mat.roughness = 0.30
	_liquid_mat.metallic = 0.0
	_liquid_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	# Shadow casting is a MeshInstance3D setting, not a material one. A
	# transparent column that casts a shadow reads as solid.
	_liquid.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_liquid.material_override = _liquid_mat
	_world.add_child(_liquid)


## Static hardware only. The shaft does not rotate and the impeller does not
## turn: the paper reports no agitation rate, so there is nothing to rotate by.
func _static_hardware() -> void:
	var shaft_mesh := CylinderMesh.new()
	shaft_mesh.top_radius = 0.028
	shaft_mesh.bottom_radius = 0.028
	shaft_mesh.height = VESSEL_HEIGHT * SHAFT_HEIGHT_RATIO
	shaft_mesh.radial_segments = 16
	var shaft := MeshInstance3D.new()
	shaft.mesh = shaft_mesh
	shaft.position = Vector3(0.0, VESSEL_HEIGHT * SHAFT_HEIGHT_RATIO * 0.5 + 0.09, 0.0)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.62, 0.64, 0.68)
	mat.roughness = 0.35
	mat.metallic = 0.8
	shaft.material_override = mat
	_world.add_child(shaft)

	var hub := BoxMesh.new()
	hub.size = Vector3(0.20, 0.22, 0.20)
	var motor := MeshInstance3D.new()
	motor.mesh = hub
	motor.position = Vector3(0.0, VESSEL_HEIGHT * SHAFT_HEIGHT_RATIO + 0.20, 0.0)
	motor.material_override = mat
	_world.add_child(motor)


# ------------------------------------------------------------------ binding

## Size the liquid column from the reported working volume. `fraction` is the
## working volume as a fraction of the reported nominal vessel volume.
func set_fill_fraction(fraction: float) -> void:
	if _liquid == null:
		return
	if is_nan(fraction):
		# No volumes were published: show an empty vessel rather than invent one.
		_liquid.visible = false
		return
	_liquid.visible = true
	var usable := VESSEL_HEIGHT * 0.94
	var h := maxf(usable * clampf(fraction, 0.0, 1.0), 0.001)
	_liquid.mesh.height = h
	# The mesh is a unit-height cylinder whose origin sits at its centre, so the
	# surface stays just above the flange as the column grows.
	_liquid.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)


## Encode the digitized OD600 as bulk colour. `t` is normalised against the
## reported `od600_max`; this is a legend, not a physical absorption model.
func set_turbidity(t: float) -> void:
	if _liquid_mat == null:
		return
	_turbidity = clampf(t, 0.0, 1.0)
	_liquid_mat.albedo_color = od_colour(_turbidity)


## Pale straw through to dark amber. Monotonic in lightness so it survives a
## greyscale screenshot.
static func od_colour(t: float) -> Color:
	t = clampf(t, 0.0, 1.0)
	var pale := Color(0.88, 0.87, 0.72)
	var amber := Color(0.55, 0.34, 0.10)
	return pale.lerp(amber, pow(t, 0.62))