extends SceneTree
## GUI verification helper: opens the pecan workflow bench in a real window,
## drives the interactions, and saves one screenshot per state.
##
##   godot --path . --script composition/tests/godot/pecan_replay_gui_capture.gd
##
## Not a test harness: the headless assertions live in `pecan_replay_scene.gd`.
## This exists so the motion and the interaction states can be inspected as
## rendered images.

const SCENE := "res://scenes/pecan_replay.tscn"
const OUT_DIR := "res://composition/.artifacts"

## [step index, clock seconds, file name]
const SHOTS := [
	[0, 1.00, "workflow_1_tissue_in_air"],
	[1, 4.60, "workflow_2_dispensing"],
	[1, 7.20, "workflow_3_centrifuge"],
	[2, 11.90, "workflow_4_dnase"],
	[3, 16.50, "workflow_5_quality_observation"],
	[4, 21.30, "workflow_6_page_slice"],
	[5, 24.80, "workflow_7_cdna_block"],
	[6, 25.80, "workflow_8_analogue_kiosk"],
	[17, 50.40, "workflow_9_method_review"],
]

var _frames := 0
var _capturing := false
var _done := false


func _initialize() -> void:
	change_scene_to_file(SCENE)


func _process(_delta: float) -> bool:
	if _done:
		return true
	if current_scene == null:
		return false
	_frames += 1
	if _frames < 30 or _capturing:
		return false
	_capturing = true
	_capture()
	return false


func _capture() -> void:
	var scene = current_scene
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT_DIR))
	scene._auto_focus = false
	for shot in SHOTS:
		var step: int = int(shot[0])
		scene._clock = float(shot[1])
		scene._apply_clock()
		scene._sim.focus_step(step)
		await _settle(40)
		await _save(String(shot[2]) + ".png")

	# Close-up on the dispensing interaction: the tip is over the mouth and the
	# stream terminates inside the tube.
	scene._clock = 4.60
	scene._apply_clock()
	var sim = scene.sim()
	var saved_distance: float = sim._distance
	var saved_target: Vector3 = sim._target
	sim._distance = 2.3
	sim._distance_goal = 2.3
	sim._target = Vector3(-0.55, 1.72, 0.15)
	sim._target_goal = sim._target
	sim._apply_camera()
	await _settle(40)
	await _save("workflow_10_dispensing_closeup.png")
	sim._distance = saved_distance
	sim._target = saved_target

	# Interaction state: the compare tab, with a pecan step and an analogue step.
	scene._auto_focus = true
	scene.select_compare(2, 10)
	scene._tabs.current_tab = 1
	await _settle(30)
	await _save("workflow_11_compare_protocols.png")

	# Interaction state: an unresolved parameter has been interrogated.
	scene.select_step_id("pecan_dnase_treatment")
	scene.select_parameter("pecan_dnase_treatment", "dnase_time")
	scene._tabs.current_tab = 0
	await _settle(20)
	await _save("workflow_12_parameter_detail.png")

	# Interaction state: pigeonpea branch on the analogue kiosk.
	scene.set_branch("pigeonpea")
	scene._tabs.current_tab = 1
	await _settle(40)
	await _save("workflow_13_pigeonpea_branch.png")

	print("GUI capture: %d shots, final clock %.2f" % [SHOTS.size() + 4, scene.clock()])
	_done = true
	quit(0)


func _settle(frames: int) -> void:
	for i in frames:
		await process_frame


func _save(name: String) -> void:
	await RenderingServer.frame_post_draw
	var image := get_root().get_texture().get_image()
	if image == null:
		print("GUI capture FAILED: no viewport image (renderer unavailable)")
		return
	var path := ProjectSettings.globalize_path(OUT_DIR).path_join(name)
	var error := image.save_png(path)
	print("GUI capture %s: %dx%d error=%d" % [name, image.get_width(), image.get_height(), error])
