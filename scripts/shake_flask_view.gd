class_name ShakeFlaskView
extends SubViewportContainer
## An orbitable 3D schematic of the 500 mL baffled shake flask the Ganjave model
## describes, driven entirely by quantities the model computes.
##
## ## What is drawn because the model computes it
##
##   * liquid level  <- `culture_volume` / the reported 500 mL flask size. This
##     genuinely rises: the feed adds volume, and `dV/dt = F` is eq. (16).
##   * liquid colour <- `biomass_concentration`, a legend-mapped encoding, stated
##     as an encoding wherever it is shown.
##   * dissolved-oxygen gauge <- `dissolved_oxygen`. The model computes a DO
##     balance because kLa = 133 h^-1 and C* = 0.0075 g/L are both printed.
##
## ## What is drawn because it is a REPORTED operating condition, not a model output
##
##   * the shaker platform turns at 200 rpm, 5 cm pitch. The paper states both.
##     The model does not compute the flow that results, and nothing on screen
##     claims it does -- see the caveat strip in the scene.
##   * the syringe pump and feed line, at the declared 0.78 mL/h.
##
## ## What is deliberately NOT drawn
##
## The Ganjave model produces well-mixed bulk scalars. It has no spatial extent, so:
##
##   * no cells, particles, flocs or solids -- no size distribution is published;
##   * no bubbles, sparger plume or gas holdup -- kLa is a lumped coefficient, and
##     the model has no gas-phase state to resolve;
##   * no concentration gradients, stratification or mixing patterns -- there is no
##     transport equation in the model at all;
##   * no molecular motion or reaction animation;
##   * no impeller, shaft or vortex -- this is a shaken flask, not a stirred tank,
##     and the model has no impeller to rotate.
##
## A cell-sized speckle or a rising bubble would look more impressive and would be a
## claim the equations do not support. The flask is drawn as a well-mixed vessel and
## labelled as one.

const FLASK_RADIUS := 0.52
const FLASK_HEIGHT := 1.30
const FILL_BASE_Y := 0.055
const SHOKER_RADIUS := 1.62
const SHOKER_THICKNESS := 0.10
## Reported: 500 mL PreSens baffled flask, 100 mL fill (1:5).
const FLASK_NOMINAL_L := 500.0

var _viewport: SubViewport
var _world: Node3D
var _camera: Camera3D
var _liquid: MeshInstance3D
var _liquid_mat: StandardMaterial3D
var _platform: Node3D
var _flask: Node3D
var _do_gauge: MeshInstance3D
var _do_gauge_mat: StandardMaterial3D
var _feed_meniscus: MeshInstance3D

var _yaw := deg_to_rad(-34.0)
var _pitch := deg_to_rad(-11.0)
var _distance := 4.6
var _dragging := false
var _target := Vector3(0.0, 0.62, 0.0)

## Reported operating conditions. Rotation is rendered context, not a model output.
var _shake_rpm := 0.0
var _shaking := true
var _phase := 0.0

## Scale for the dissolved-oxygen gauge: reported C* and the model's percentage.
var _gauge_span := 100.0

signal orbit_changed(azimuth_deg: float, elevation_deg: float, distance: float)


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


func _process(delta: float) -> void:
	# The platform turns at the reported shaking speed. Nothing about the culture
	# changes because of it in this model; see the class documentation.
	if not _shaking or _platform == null or _shake_rpm <= 0.0:
		return
	_phase = fmod(_phase + delta * _shake_rpm * TAU / 60.0, TAU)
	_platform.rotation.y = _phase


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
		_pitch = clampf(_pitch - mm.relative.y * 0.008, deg_to_rad(-80.0), deg_to_rad(80.0))
		_apply_camera()
		accept_event()


func _zoom(direction: float) -> void:
	_distance = clampf(_distance + direction * 0.35, 2.4, 10.0)
	_apply_camera()


func reset_camera() -> void:
	_yaw = deg_to_rad(-34.0)
	_pitch = deg_to_rad(-11.0)
	_distance = 4.6
	_apply_camera()


func _apply_camera() -> void:
	if _camera == null:
		return
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
	e.background_color = Color(0.043, 0.052, 0.067)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.46, 0.52, 0.62)
	e.ambient_light_energy = 0.55
	env.environment = e
	_world.add_child(env)

	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-46.0, -124.0, 0.0)
	key.light_energy = 1.05
	key.light_color = Color(1.0, 0.97, 0.93)
	key.shadow_enabled = true
	_world.add_child(key)

	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-18.0, 62.0, 0.0)
	rim.light_energy = 0.40
	rim.light_color = Color(0.66, 0.79, 1.0)
	rim.shadow_enabled = false
	_world.add_child(rim)

	_ground()
	_shaker()
	_flask_body()
	_liquid_column()
	_build_do_gauge()
	_feed_rig()

	_camera = Camera3D.new()
	_camera.fov = 44.0
	_world.add_child(_camera)


func _ground() -> void:
	var plane := PlaneMesh.new()
	plane.size = Vector2(14.0, 14.0)
	var mi := MeshInstance3D.new()
	mi.mesh = plane
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.075, 0.085, 0.10)
	mat.roughness = 0.94
	mi.material_override = mat
	_world.add_child(mi)


## The shaker platform turns; the flask and everything on it turn with it, because
## that is what a shaker does. The *culture* is unaffected in this model.
func _shaker() -> void:
	_platform = Node3D.new()
	_platform.position = Vector3(0.0, FILL_BASE_Y * 0.5, 0.0)
	_world.add_child(_platform)

	var disc := CylinderMesh.new()
	disc.top_radius = SHOKER_RADIUS
	disc.bottom_radius = SHOKER_RADIUS
	disc.height = SHOKER_THICKNESS
	disc.radial_segments = 48
	var plate := MeshInstance3D.new()
	plate.mesh = disc
	plate.position = Vector3(0.0, -FILL_BASE_Y * 0.5 + SHOKER_THICKNESS * 0.5, 0.0)
	var pmat := StandardMaterial3D.new()
	pmat.albedo_color = Color(0.22, 0.24, 0.27)
	pmat.roughness = 0.62
	pmat.metallic = 0.55
	plate.material_override = pmat
	_platform.add_child(plate)

	# The clamp arm holding the flask, so it reads as mounted rather than floating.
	var arm := BoxMesh.new()
	arm.size = Vector3(0.12, 0.10, SHOKER_RADIUS * 1.7)
	var arm_mi := MeshInstance3D.new()
	arm_mi.mesh = arm
	arm_mi.position = Vector3(0.0, SHOKER_THICKNESS * 0.5 + 0.05, 0.0)
	arm_mi.material_override = pmat
	_platform.add_child(arm_mi)


## The 500 mL baffled flask itself, with the two needle ports the paper describes:
## a short one delivers feed, the longer one draws samples.
func _flask_body() -> void:
	_flask = Node3D.new()
	_platform.add_child(_flask)

	var mesh := CylinderMesh.new()
	mesh.top_radius = FLASK_RADIUS
	mesh.bottom_radius = FLASK_RADIUS * 0.94
	mesh.height = FLASK_HEIGHT
	mesh.radial_segments = 56
	mesh.rings = 1
	mesh.cap_top = false
	mesh.cap_bottom = false
	var body := MeshInstance3D.new()
	body.mesh = mesh
	body.position = Vector3(0.0, FLASK_HEIGHT * 0.5, 0.0)
	var glass := StandardMaterial3D.new()
	glass.albedo_color = Color(0.80, 0.87, 0.92, 0.12)
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.cull_mode = BaseMaterial3D.CULL_DISABLED
	glass.roughness = 0.05
	glass.metallic = 0.0
	glass.rim_enabled = true
	glass.rim = 0.65
	body.material_override = glass
	_flask.add_child(body)

	# Neck and cotton plug.
	var neck := CylinderMesh.new()
	neck.top_radius = FLASK_RADIUS * 0.42
	neck.bottom_radius = FLASK_RADIUS * 0.46
	neck.height = 0.22
	neck.radial_segments = 32
	var neck_mi := MeshInstance3D.new()
	neck_mi.mesh = neck
	neck_mi.position = Vector3(0.0, FLASK_HEIGHT + 0.11, 0.0)
	neck_mi.material_override = glass
	_flask.add_child(neck_mi)

	var plug := CylinderMesh.new()
	plug.top_radius = FLASK_RADIUS * 0.40
	plug.bottom_radius = FLASK_RADIUS * 0.40
	plug.height = 0.09
	plug.radial_segments = 24
	var plug_mi := MeshInstance3D.new()
	plug_mi.mesh = plug
	plug_mi.position = Vector3(0.0, FLASK_HEIGHT + 0.26, 0.0)
	var plug_mat := StandardMaterial3D.new()
	plug_mat.albedo_color = Color(0.86, 0.84, 0.78)
	plug_mat.roughness = 0.95
	plug_mi.material_override = plug_mat
	_flask.add_child(plug_mi)

	# The two needles through the plug, as the paper describes them.
	_needle(Vector2(0.09, -0.05), 0.34)
	_needle(Vector2(-0.07, 0.07), 0.26)


func _needle(offset: Vector2, length: float) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.008
	mesh.bottom_radius = 0.008
	mesh.height = length
	mesh.radial_segments = 10
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = Vector3(offset.x, FLASK_HEIGHT + 0.24 + length * 0.5, offset.y)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.70, 0.74, 0.80)
	mat.metallic = 0.85
	mat.roughness = 0.28
	mi.material_override = mat
	_flask.add_child(mi)


func _liquid_column() -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = FLASK_RADIUS * 0.955
	mesh.bottom_radius = FLASK_RADIUS * 0.925
	mesh.height = 1.0
	mesh.radial_segments = 56
	_liquid = MeshInstance3D.new()
	_liquid.mesh = mesh
	_liquid_mat = StandardMaterial3D.new()
	_liquid_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_liquid_mat.roughness = 0.34
	_liquid_mat.metallic = 0.0
	_liquid_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_liquid.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_liquid.material_override = _liquid_mat
	_flask.add_child(_liquid)


## A vertical bar beside the flask whose height tracks dissolved oxygen.
## The model computes DO because kLa and C* are published; the bar is a gauge,
## not a spatial depiction of where the oxygen is.
func _build_do_gauge() -> void:
	var backing := BoxMesh.new()
	backing.size = Vector3(0.085, FLASK_HEIGHT * 0.86, 0.035)
	var b := MeshInstance3D.new()
	b.mesh = backing
	b.position = Vector3(FLASK_RADIUS * 1.45, FLASK_HEIGHT * 0.43, 0.0)
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(0.14, 0.16, 0.19)
	bmat.roughness = 0.8
	b.material_override = bmat
	_world.add_child(b)

	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.062, 1.0, 0.022)
	_do_gauge = MeshInstance3D.new()
	_do_gauge.mesh = mesh
	_do_gauge_mat = StandardMaterial3D.new()
	_do_gauge_mat.albedo_color = Color(0.30, 0.62, 0.86)
	_do_gauge_mat.emission_enabled = true
	_do_gauge_mat.emission = Color(0.16, 0.34, 0.52)
	_do_gauge_mat.emission_energy_multiplier = 0.55
	_do_gauge.material_override = _do_gauge_mat
	_do_gauge.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_world.add_child(_do_gauge)


## The external syringe pump and its feed line, at the declared flow rate. Both are
## reported hardware; the line carries no rendered flow, because the model has no
## spatial transport to depict.
func _feed_rig() -> void:
	var barrel := CylinderMesh.new()
	barrel.top_radius = 0.055
	barrel.bottom_radius = 0.055
	barrel.height = 0.62
	barrel.radial_segments = 20
	var b := MeshInstance3D.new()
	b.mesh = barrel
	b.position = Vector3(-FLASK_RADIUS * 2.15, 0.31, 0.0)
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(0.62, 0.66, 0.72, 0.30)
	bmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	bmat.roughness = 0.10
	b.material_override = bmat
	_world.add_child(b)

	# The feed solution meniscus falls as feed is delivered. Cumulative volume
	# delivered is F * t, which is arithmetic on a reported rate, not a model output.
	_feed_meniscus = MeshInstance3D.new()
	var fill := CylinderMesh.new()
	fill.top_radius = 0.049
	fill.bottom_radius = 0.049
	fill.height = 1.0
	fill.radial_segments = 20
	_feed_meniscus.mesh = fill
	var fmat := StandardMaterial3D.new()
	fmat.albedo_color = Color(0.86, 0.80, 0.52, 0.55)
	fmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_feed_meniscus.material_override = fmat
	_feed_meniscus.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_world.add_child(_feed_meniscus)

	var line := BoxMesh.new()
	line.size = Vector3(FLASK_RADIUS * 1.7, 0.016, 0.016)
	var l := MeshInstance3D.new()
	l.mesh = line
	l.position = Vector3(-FLASK_RADIUS * 1.05, FLASK_HEIGHT + 0.30, 0.0)
	var lmat := StandardMaterial3D.new()
	lmat.albedo_color = Color(0.70, 0.74, 0.80)
	lmat.roughness = 0.4
	l.material_override = lmat
	_world.add_child(l)


# ------------------------------------------------------------------ binding
#
# Every setter below takes a value the model computed. Nothing here invents a
# quantity, interpolates one the runner did not produce, or keeps animating after
# the runner has stopped.


## Liquid level from the model's culture volume, against the reported flask size.
func set_culture_volume(volume_l: float) -> void:
	if _liquid == null or is_nan(volume_l):
		_liquid.visible = false
		return
	_liquid.visible = true
	var fraction := clampf(volume_l / FLASK_NOMINAL_L, 0.0, 1.0)
	var usable := FLASK_HEIGHT * 0.93
	var h := maxf(usable * fraction, 0.001)
	_liquid.mesh.height = h
	_liquid.position = Vector3(0.0, FILL_BASE_Y + h * 0.5, 0.0)


## Biomass concentration as a bulk colour. `t` is normalised against `x_max`, so
## the caller decides the scale and the legend states it.
func set_biomass_fraction(t: float) -> void:
	if _liquid_mat == null:
		return
	_liquid_mat.albedo_color = biomass_colour(clampf(t, 0.0, 1.0))


## Dissolved oxygen, in percent, against the full 0-100 % scale.
func set_dissolved_oxygen(percent: float) -> void:
	if _do_gauge == null or is_nan(percent):
		_do_gauge.visible = false
		return
	_do_gauge.visible = true
	var usable := FLASK_HEIGHT * 0.82
	var f := clampf(percent / maxf(_gauge_span, 1.0), 0.0, 1.0)
	var h := maxf(usable * f, 0.004)
	_do_gauge.mesh.size = Vector3(0.062, h, 0.022)
	_do_gauge.position = Vector3(
		FLASK_RADIUS * 1.45, 0.02 + h * 0.5, 0.0)
	# Oxygen-poor reads as a dim slate; oxygen-rich as a bright cyan. This is a
	# legend, and it is monotonic in lightness so it survives a greyscale shot.
	var intensity := clampf(f, 0.0, 1.0)
	_do_gauge_mat.albedo_color = Color(0.24, 0.42, 0.55).lerp(
		Color(0.42, 0.82, 1.0), intensity)
	_do_gauge_mat.emission = _do_gauge_mat.albedo_color * 0.6


## Residual feed in the syringe, from the reported rate and elapsed time.
## `delivered_ml` is `flow_mL_per_h * t_h`: arithmetic on a reported rate.
func set_feed_delivered(delivered_ml: float, syringe_ml: float = 20.0) -> void:
	if _feed_meniscus == null or is_nan(delivered_ml):
		_feed_meniscus.visible = false
		return
	_feed_meniscus.visible = true
	var remaining := clampf(1.0 - delivered_ml / maxf(syringe_ml, 0.001), 0.0, 1.0)
	var h := maxf(0.60 * remaining, 0.004)
	_feed_meniscus.mesh.height = h
	_feed_meniscus.position = Vector3(-FLASK_RADIUS * 2.15, 0.02 + h * 0.5, 0.0)


## Reported shaking speed. Rendered context, not a model output.
func set_shaking(rpm: float, running: bool) -> void:
	_shake_rpm = maxf(rpm, 0.0)
	_shaking = running


## Pale straw to dark amber, monotonic in lightness.
static func biomass_colour(t: float) -> Color:
	t = clampf(t, 0.0, 1.0)
	var pale := Color(0.90, 0.88, 0.74)
	var amber := Color(0.52, 0.31, 0.09)
	return pale.lerp(amber, pow(t, 0.60))
