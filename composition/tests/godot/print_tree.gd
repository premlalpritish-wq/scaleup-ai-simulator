extends SceneTree

func _init() -> void:
	var scene_res = load("res://scenes/prompt_simulation.tscn")
	var scene = scene_res.instantiate()
	root.add_child(scene)
	await process_frame

	var run_file = ProjectSettings.globalize_path("res://.artifacts/latest_prompt_run.json")
	print("Loading run file:", run_file)
	scene.load_run_file(run_file)
	await process_frame

	print("Children in scene:")
	_print_node(scene, 0)
	quit(0)

func _print_node(node: Node, indent: int) -> void:
	var prefix := "  ".repeat(indent)
	print("%s- %s (%s)" % [prefix, node.name, node.get_class()])
	for c in node.get_children():
		_print_node(c, indent + 1)
