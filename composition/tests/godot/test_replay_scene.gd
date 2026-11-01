extends SceneTree

var _checks := 0
var _failures: Array[String] = []

func _check(condition: bool, msg: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(msg)
		print("FAIL: ", msg)

func _initialize() -> void:
	change_scene_to_file("res://scenes/replay3d.tscn")

var _ran_checks := false

func _process(_delta: float) -> bool:
	if _ran_checks:
		return true

	var root := current_scene
	if root == null:
		return false

	var executed: bool = bool(root.get("_executed"))
	if not executed:
		return false

	_ran_checks = true
	# Freeze playback during inspection
	root.set("_playing", false)
	root.call("_reset_replay_clock")

	print("Running replay scene checks on: ", root.name)

	# 1. Check data loaded
	var data: ReplayData = root.get("_data")
	_check(data != null, "ReplayData should not be null")
	_check(data.hours.size() == 19, "Expected 19 trajectory hours, got %d" % (data.hours.size() if data else 0))
	_check(data.od600.size() == 19, "Expected 19 od600 points, got %d" % (data.od600.size() if data else 0))
	_check(is_equal_approx(data.hours[0], 1.0), "First hour should be 1.0")
	_check(is_equal_approx(data.od600[0], 0.37), "First OD600 should be 0.37")
	_check(is_equal_approx(data.hours[18], 19.0), "Last hour should be 19.0")
	_check(is_equal_approx(data.od600[18], 53.67), "Last OD600 should be 53.67")

	# 2. Check initial time & OD600 readouts
	var od_readout: Label = root.get("_od_readout")
	var od_unit: Label = root.get("_od_unit")
	var clock_label: Label = root.get("_clock")
	var growth: GrowthChart = root.get("_growth")
	var timeline: HSlider = root.get("_timeline")

	_check(od_readout != null, "_od_readout should exist")
	_check(od_readout.text.contains("0.37"), "Initial OD readout should contain 0.37, got: '%s'" % od_readout.text)
	_check(od_unit.text == "OD600", "Initial unit should be OD600, got: '%s'" % od_unit.text)
	_check(clock_label.text.contains("1 hours"), "Initial clock should show 1 hours, got: '%s'" % clock_label.text)
	_check(growth != null, "GrowthChart should exist")
	_check(growth.cursor_visible == true, "Cursor marker should be visible initially")
	_check(is_equal_approx(growth.cursor_hour, 1.0), "Cursor marker should be at hour 1.0, got: %f" % growth.cursor_hour)

	# 3. Check timeline slider
	_check(timeline != null, "Timeline slider should exist")
	_check(timeline.visible == true, "Timeline slider should be visible")
	_check(is_equal_approx(timeline.min_value, 1.0), "Timeline min should be 1.0")
	_check(is_equal_approx(timeline.max_value, 19.0), "Timeline max should be 19.0")
	_check(is_equal_approx(timeline.value, 1.0), "Timeline value should be 1.0 initially")

	# 4. Check scrubbing
	root.call("_on_scrub", 13.0)
	_check(is_equal_approx(growth.cursor_hour, 13.0), "Scrubbing to 13.0 should update cursor hour")
	_check(od_readout.text.contains("24.39"), "Scrubbing to 13.0 should show density 24.39, got: '%s'" % od_readout.text)
	_check(clock_label.text.contains("13 hours"), "Scrubbing to 13.0 should show 13 hours, got: '%s'" % clock_label.text)
	_check(is_equal_approx(timeline.value, 13.0), "Timeline slider should update to 13.0")

	# 5. Check reset
	root.call("_on_reset_pressed")
	_check(is_equal_approx(growth.cursor_hour, 1.0), "Reset should return cursor hour to 1.0")
	_check(od_readout.text.contains("0.37"), "Reset should restore density 0.37, got: '%s'" % od_readout.text)
	_check(clock_label.text.contains("1 hours"), "Reset should restore clock 1 hours, got: '%s'" % clock_label.text)
	_check(is_equal_approx(timeline.value, 1.0), "Reset should restore timeline to 1.0")

	# 6. Check purification cascade
	var cascade_chart: CascadeChart = root.get("_cascade")
	_check(cascade_chart != null, "CascadeChart should exist")
	_check(data.cascade.size() == 4, "Cascade should have 4 steps")
	_check(is_equal_approx(float(data.cascade[0]["au"]), 2142.5), "DEAE Sepharose AU should be 2142.5")
	_check(is_equal_approx(float(data.cascade[1]["au"]), 626.02), "Q Sepharose AU should be 626.02")
	_check(is_equal_approx(float(data.cascade[2]["au"]), 234.74), "RP-HPLC AU should be 234.74")
	_check(is_equal_approx(float(data.cascade[3]["au"]), 111.29), "Sephadex G-25 AU should be 111.29")

	# 7. Check absent / not available quantities
	_check(data.unresolved.has("node:N01#specific_growth_rate"), "Growth rate should be unresolved")
	_check(data.unresolved.has("node:N01#dissolved_oxygen"), "Dissolved oxygen should be unresolved")
	_check(data.unresolved.has("node:N01#induction_time"), "Induction time should be unresolved")

	print("\nALL REPLAY CHECKS FINISHED: %d passed, %d failures" % [_checks, _failures.size()])
	if _failures.is_empty():
		quit(0)
	else:
		for f in _failures:
			printerr("FAILURE: ", f)
		quit(1)
	return true
