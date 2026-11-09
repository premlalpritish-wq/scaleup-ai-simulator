extends Node3D
class_name OrbitCameraRig

## Interactive 3D Orbit, Pan & Zoom Camera Controller for Godot 4
## Features:
##   - _input(event) handling: Left-Click, Right-Click, and Middle-Click drag orbit
##   - Mouse Wheel Up / Down: Smooth zoom distance
##   - Shift + Drag: Pan pivot in camera-local plane
##   - Keyboard Fallback: Arrow Keys / Q & E (Orbit), WASD (Pan), Z & X (Zoom)
##   - Focus Shortcut (F key or double-click): Smooth tween to target component
##   - Reset View (R key): Restores default workbench framing

@export var orbit_speed: float = 0.007
@export var pan_speed: float = 0.025
@export var zoom_speed: float = 2.2
@export var min_distance: float = 3.5
@export var max_distance: float = 140.0
@export var default_distance: float = 34.0
@export var default_pivot: Vector3 = Vector3(5.0, 8.0, 0.0)

var yaw: float = 0.0
var pitch: float = 0.18
var target_distance: float = 34.0
var current_distance: float = 34.0

var is_orbiting: bool = false
var is_panning: bool = false
var last_mouse_pos: Vector2 = Vector2.ZERO

@onready var camera: Camera3D = $Camera3D
var active_tween: Tween = null


func _ready() -> void:
	position = default_pivot
	target_distance = default_distance
	current_distance = default_distance
	_update_camera_transform()


func _input(event: InputEvent) -> void:
	# Check if click started over an interactive UI element (Button or Slider)
	var hovered_control := get_viewport().gui_get_hovered_control()
	var is_over_ui_interactive: bool = false
	if hovered_control:
		if hovered_control is Slider or hovered_control is Button or hovered_control is CheckBox:
			is_over_ui_interactive = true

	# Mouse button events
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		
		# Zoom via wheel (allowed anywhere except when hovering over a Slider)
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			if not (hovered_control and hovered_control is Slider):
				target_distance = clampf(target_distance - zoom_speed, min_distance, max_distance)
				_stop_tween()
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			if not (hovered_control and hovered_control is Slider):
				target_distance = clampf(target_distance + zoom_speed, min_distance, max_distance)
				_stop_tween()
				
		# Orbit / Pan initiation (Left-Click, Right-Click, or Middle-Click)
		elif mb.button_index in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE]:
			if mb.pressed:
				# If user clicks directly on a slider or button, do not capture camera drag
				if is_over_ui_interactive:
					return
				
				last_mouse_pos = mb.position
				if Input.is_key_pressed(KEY_SHIFT) or mb.button_index == MOUSE_BUTTON_MIDDLE:
					is_panning = true
					is_orbiting = false
				else:
					# Left or Right click drag orbits the camera
					is_orbiting = true
					is_panning = false
				_stop_tween()
			else:
				is_orbiting = false
				is_panning = false

	# Mouse motion events
	elif event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		if is_orbiting:
			yaw -= mm.relative.x * orbit_speed
			pitch -= mm.relative.y * orbit_speed
			pitch = clampf(pitch, -1.45, 1.45) # Clamped to ~83 degrees pitch
			_stop_tween()
			_update_camera_transform()
		elif is_panning:
			var right_dir := global_transform.basis.x
			var up_dir := global_transform.basis.y
			var delta_pan := (-right_dir * mm.relative.x + up_dir * mm.relative.y) * pan_speed * (current_distance / 30.0)
			position += delta_pan
			_stop_tween()

	# Keyboard shortcuts
	elif event is InputEventKey:
		var ek := event as InputEventKey
		if ek.pressed and not ek.echo:
			if ek.keycode == KEY_F:
				var solver = get_parent()
				if solver and solver.has_method("focus_selected_or_default"):
					solver.focus_selected_or_default()
			elif ek.keycode == KEY_R:
				reset_to_default_view()


func _process(delta: float) -> void:
	# Fallback Keyboard Orbit (Q & E or Left & Right Arrow keys)
	var orbit_key_delta := Vector2.ZERO
	if Input.is_key_pressed(KEY_Q):
		orbit_key_delta.x += 1.0
	if Input.is_key_pressed(KEY_E):
		orbit_key_delta.x -= 1.0
	if Input.is_key_pressed(KEY_UP) and not Input.is_key_pressed(KEY_SHIFT):
		orbit_key_delta.y += 1.0
	if Input.is_key_pressed(KEY_DOWN) and not Input.is_key_pressed(KEY_SHIFT):
		orbit_key_delta.y -= 1.0
	if Input.is_key_pressed(KEY_LEFT) and not Input.is_key_pressed(KEY_SHIFT):
		orbit_key_delta.x += 1.0
	if Input.is_key_pressed(KEY_RIGHT) and not Input.is_key_pressed(KEY_SHIFT):
		orbit_key_delta.x -= 1.0

	if orbit_key_delta.length_squared() > 0.0:
		yaw += orbit_key_delta.x * 2.2 * delta
		pitch += orbit_key_delta.y * 1.8 * delta
		pitch = clampf(pitch, -1.45, 1.45)
		_stop_tween()
		_update_camera_transform()

	# Keyboard Zoom (Z to zoom in, X to zoom out)
	if Input.is_key_pressed(KEY_Z):
		target_distance = clampf(target_distance - 20.0 * delta, min_distance, max_distance)
		_stop_tween()
	if Input.is_key_pressed(KEY_X):
		target_distance = clampf(target_distance + 20.0 * delta, min_distance, max_distance)
		_stop_tween()

	# Keyboard Panning (WASD or Shift + Arrows)
	var move_vec := Vector2.ZERO
	if Input.is_key_pressed(KEY_W):
		move_vec.y += 1.0
	if Input.is_key_pressed(KEY_S):
		move_vec.y -= 1.0
	if Input.is_key_pressed(KEY_A):
		move_vec.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		move_vec.x += 1.0
	if Input.is_key_pressed(KEY_SHIFT):
		if Input.is_key_pressed(KEY_UP):
			move_vec.y += 1.0
		if Input.is_key_pressed(KEY_DOWN):
			move_vec.y -= 1.0
		if Input.is_key_pressed(KEY_LEFT):
			move_vec.x -= 1.0
		if Input.is_key_pressed(KEY_RIGHT):
			move_vec.x += 1.0
		
	if move_vec.length_squared() > 0.0:
		move_vec = move_vec.normalized()
		var right_dir := global_transform.basis.x
		var up_dir := global_transform.basis.y
		var pan_step := (right_dir * move_vec.x + up_dir * move_vec.y) * 18.0 * delta * (current_distance / 30.0)
		position += pan_step
		_stop_tween()
		
	# Smooth distance lerp
	if active_tween == null:
		current_distance = lerpf(current_distance, target_distance, 14.0 * delta)
		_update_camera_transform()


func _update_camera_transform() -> void:
	rotation.y = yaw
	rotation.x = pitch
	rotation.z = 0.0
	if camera:
		camera.position = Vector3(0.0, 0.0, current_distance)


func focus_on_target(target_pos: Vector3, desired_dist: float = 12.0, duration: float = 0.6) -> void:
	_stop_tween()
	active_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	active_tween.tween_property(self, "position", target_pos, duration)
	active_tween.tween_property(self, "target_distance", desired_dist, duration)
	active_tween.tween_property(self, "current_distance", desired_dist, duration)
	active_tween.chain().tween_callback(func(): active_tween = null)


func reset_to_default_view(duration: float = 0.7) -> void:
	_stop_tween()
	active_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	active_tween.tween_property(self, "position", default_pivot, duration)
	active_tween.tween_property(self, "target_distance", default_distance, duration)
	active_tween.tween_property(self, "current_distance", default_distance, duration)
	active_tween.tween_property(self, "yaw", 0.0, duration)
	active_tween.tween_property(self, "pitch", 0.18, duration)
	active_tween.chain().tween_callback(func(): active_tween = null)


func _stop_tween() -> void:
	if active_tween and active_tween.is_valid():
		active_tween.kill()
		active_tween = null
