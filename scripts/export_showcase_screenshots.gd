extends SceneTree

func _init() -> void:
	print("--- Capturing Showcase Screenshots ---")
	var scene_res = load("res://scenes/prompt_simulation.tscn")
	var scene = scene_res.instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame

	var run_file = ProjectSettings.globalize_path("res://.artifacts/latest_prompt_run.json")
	scene.load_run_file(run_file)
	if scene._view != null and scene._view.is_building:
		await scene._view.bench_build_completed

	for i in range(10):
		await process_frame

	var da := DirAccess.open("res://")
	if not da.dir_exists("assets/showcase"):
		da.make_dir_recursive("assets/showcase")

	var shots := [
		{"name": "stage_0_dry_milling.png", "time": 0.5, "focus": 0},
		{"name": "stage_2_alkaline_dissolution.png", "time": 24.0, "focus": 2},
		{"name": "stage_4_cryo_precipitation.png", "time": 35.0, "focus": 4},
		{"name": "stage_5_wet_spinning_tensile.png", "time": 38.5, "focus": 5},
		{"name": "saccharina_6stage_bench_overview.png", "time": 38.5, "focus": -1}
	]

	for item in shots:
		scene._on_scrub(float(item.time))
		if int(item.focus) >= 0:
			scene._view.focus_on_stage(int(item.focus))
		else:
			scene._view.reset_camera()

		for f in range(10):
			await process_frame

		var img := root.get_texture().get_image()
		var out_path := ProjectSettings.globalize_path("res://assets/showcase/" + str(item.name))
		var err := img.save_png(out_path)
		print("Saved %s (err=%d, size=%dx%d)" % [str(item.name), err, img.get_width(), img.get_height()])

	print("--- Showcase Screenshots Captured Successfully ---")
	quit(0)
