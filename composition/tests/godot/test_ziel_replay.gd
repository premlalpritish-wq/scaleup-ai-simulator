extends SceneTree

func _init() -> void:
	var r := CompositionRunner.new()
	var path := "res://assets/zielinski_replay_result.json"
	print("Direct FileAccess exists: ", FileAccess.file_exists(path))
	var os_path := ProjectSettings.globalize_path(path)
	print("ProjectSettings.globalize_path: ", os_path)
	print("Globalized FileAccess exists: ", FileAccess.file_exists(os_path))
	var res := r.read_result(path)
	print("Runner read_result keys: ", res.keys().size())
	var data := ReplayData.new()
	data.load_payload(res, "zielinski_replay")
	print("Data hours size: ", data.hours.size())
	print("Data cascade size: ", data.cascade.size())
	print("Data plateau_max: ", data.plateau_max)
	for i in range(data.hours.size()):
		print("h=", data.hours[i], " od=", data.od600[i])
	for c in data.cascade:
		print("step: ", c)
	quit(0)
