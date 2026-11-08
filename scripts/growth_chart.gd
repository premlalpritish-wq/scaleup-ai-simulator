class_name GrowthChart
extends Control
## The Fig. 3 growth curve exactly as the model publishes it.
##
## Drawn from `ReplayData`: the 19 digitized OD600 points at 1..19 h, the
## declared +/-0.5 OD uncertainty, and the two crossing times the model itself
## derives by linear interpolation. Nothing is smoothed, extrapolated or fitted,
## and the curve never extends past the last published hour.

const PAD_L := 56.0
const PAD_R := 16.0
const PAD_T := 40.0
const PAD_B := 40.0

## Drawn titles, exposed as constants so the wording can be asserted.
const TITLE := "Process Dynamics Trajectory"
const SUBTITLE := "bioprocess parameters vs process duration hours"
const Y_AXIS := "OD600"
const X_AXIS := "hours of culture"
const CAPTION := "read from the published growth figure, not calculated; each point +/-%.1f OD"

var data: ReplayData = null
signal scrubbed(hour: float)

var cursor_hour := 0.0
var cursor_visible := false

var custom_hours: Array = []
var custom_biomass: Array = []
var custom_label: String = "Biomass (g/L)"
var ghost_hours: Array = []
var ghost_biomass: Array = []
var ghost_label: String = ""
var y_axis_label: String = "OD600"

const COL_AXIS := Color(0.55, 0.58, 0.64)
const COL_GRID := Color(1, 1, 1, 0.07)
const COL_CURVE := Color(0.46, 0.78, 0.96)
const COL_BAND := Color(0.46, 0.78, 0.96, 0.16)
const COL_MARK := Color(0.85, 0.90, 0.98)
const COL_CURSOR := Color(0.98, 0.78, 0.35)
const COL_DERIVED := Color(0.66, 0.92, 0.68)
const COL_TEXT := Color(0.72, 0.75, 0.80)


func _ready() -> void:
	custom_minimum_size = Vector2(0, 198)
	mouse_filter = Control.MOUSE_FILTER_STOP
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND


func _gui_input(event: InputEvent) -> void:
	if (data == null or not data.has_trajectory()) and custom_hours.size() < 2:
		return
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			_handle_scrub(mb.position)
	elif event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		if mm.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_handle_scrub(mm.position)


func _handle_scrub(pos: Vector2) -> void:
	var r := _plot_rect()
	var t := clampf((pos.x - r.position.x) / maxf(r.size.x, 1.0), 0.0, 1.0)
	if custom_hours.size() > 1:
		var first_h: float = float(custom_hours[0])
		var last_h: float = float(custom_hours[custom_hours.size() - 1])
		var h := first_h + t * (last_h - first_h)
		scrubbed.emit(h)
	elif data != null and data.has_trajectory():
		var h := data.hours[0] + t * data.span_h()
		scrubbed.emit(h)


func set_data(d: ReplayData) -> void:
	data = d
	custom_hours.clear()
	custom_biomass.clear()
	ghost_hours.clear()
	ghost_biomass.clear()
	y_axis_label = "OD600"
	queue_redraw()


func set_trajectory_data(
	hours: Array,
	biomass: Array,
	label: String = "Primary (g/L)",
	g_hours: Array = [],
	g_biomass: Array = [],
	g_label: String = ""
) -> void:
	data = null
	custom_hours = hours
	custom_biomass = biomass
	custom_label = label
	ghost_hours = g_hours
	ghost_biomass = g_biomass
	ghost_label = g_label
	y_axis_label = "Biomass (g/L)"
	queue_redraw()


func set_cursor(hour: float, visible_now: bool) -> void:
	cursor_hour = hour
	cursor_visible = visible_now
	queue_redraw()


func _plot_rect() -> Rect2:
	return Rect2(PAD_L, PAD_T, maxf(size.x - PAD_L - PAD_R, 1.0), maxf(size.y - PAD_T - PAD_B, 1.0))


func _x_for(hour: float, r: Rect2) -> float:
	if data == null or data.hours.size() < 2:
		return r.position.x
	var t := (hour - data.hours[0]) / maxf(data.span_h(), 0.0001)
	return r.position.x + clampf(t, 0.0, 1.0) * r.size.x


func _y_for(od: float, r: Rect2, top_od: float) -> float:
	var t := clampf(od / maxf(top_od, 0.0001), 0.0, 1.0)
	return r.position.y + r.size.y - t * r.size.y


## Round up to 1/2/2.5/5 x 10^n so the tick labels are round numbers. The axis
## bound is a drawing convenience and is never presented as a model output.
static func _nice_ceiling(value: float) -> float:
	if value <= 0.0:
		return 1.0
	var magnitude := pow(10.0, floorf(log(value) / log(10.0)))
	for m in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]:
		if value <= m * magnitude:
			return m * magnitude
	return 10.0 * magnitude


func _draw() -> void:
	var r := _plot_rect()
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.10, 0.11, 0.14), true)

	if custom_hours.size() > 1:
		_draw_custom_trajectories(r)
		return

	if data == null or not data.has_trajectory():
		draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 15),
			TITLE, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.80, 0.88, 0.98))
		draw_string(ThemeDB.fallback_font, Vector2(PAD_L, size.y * 0.5),
			"the model published no growth trajectory, so there is nothing to plot",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, COL_TEXT)
		return

	# Headroom above the data so the plateau and the cursor are both visible, rounded
	# to a readable tick step so the axis labels are not arbitrary decimals.
	var top_od := maxf(data.od600_max_reported, data.max_od())
	if is_nan(top_od) or top_od <= 0.0:
		top_od = data.max_od()
	top_od = _nice_ceiling(top_od)

	# grid + y ticks
	var ticks := 5
	for i in range(ticks + 1):
		var od := top_od * float(i) / float(ticks)
		var y := _y_for(od, r, top_od)
		draw_line(Vector2(r.position.x, y), Vector2(r.end.x, y), COL_GRID, 1.0)
		draw_string(ThemeDB.fallback_font, Vector2(4, y + 4),
			ReplayData.format_number(od), HORIZONTAL_ALIGNMENT_LEFT, PAD_L - 6, 10, COL_TEXT)

	# x ticks at the published hours
	var first := data.hours[0]
	var last := data.hours[data.hours.size() - 1]
	var step := 2.0 if int(last - first) > 8 else 1.0
	var h := first
	while h <= last + 0.001:
		var x := _x_for(h, r)
		draw_line(Vector2(x, r.position.y), Vector2(x, r.end.y), COL_GRID, 1.0)
		draw_string(ThemeDB.fallback_font, Vector2(x - 10, r.end.y + 15),
			"%d" % int(h), HORIZONTAL_ALIGNMENT_LEFT, 20, 10, COL_TEXT)
		h += step

	# uncertainty band (+/- declared envelope)
	var band_top := PackedVector2Array()
	var band_bot := PackedVector2Array()
	var u := data.trajectory_uncertainty_od
	for i in range(data.hours.size()):
		band_top.append(Vector2(_x_for(data.hours[i], r), _y_for(data.od600[i] + u, r, top_od)))
	for i in range(data.hours.size() - 1, -1, -1):
		band_bot.append(Vector2(_x_for(data.hours[i], r), _y_for(data.od600[i] - u, r, top_od)))
	band_top.append_array(band_bot)
	if band_top.size() >= 3:
		draw_colored_polygon(band_top, COL_BAND)

	# the published points, joined in time order
	var poly := PackedVector2Array()
	for i in range(data.hours.size()):
		poly.append(Vector2(_x_for(data.hours[i], r), _y_for(data.od600[i], r, top_od)))
	if poly.size() >= 2:
		draw_polyline(poly, COL_CURVE, 2.0, true)
	for i in range(poly.size()):
		draw_circle(poly[i], 2.4, COL_MARK)

	# the two crossing times the model derives
	for t in [data.t_od25_h, data.t_od50_h]:
		if is_nan(t):
			continue
		if t < first or t > last:
			continue
		var x2 := _x_for(t, r)
		draw_line(Vector2(x2, r.position.y), Vector2(x2, r.end.y), Color(COL_DERIVED, 0.55), 1.0)
		draw_string(ThemeDB.fallback_font, Vector2(x2 + 3, r.position.y + 10),
			"%.2f h" % t, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, COL_DERIVED)

	# replay cursor
	if cursor_visible and cursor_hour >= first and cursor_hour <= last:
		var cx := _x_for(cursor_hour, r)
		draw_line(Vector2(cx, r.position.y), Vector2(cx, r.end.y), COL_CURSOR, 1.5)
		var od := data.od_at_hour(cursor_hour)
		if not is_nan(od):
			draw_circle(Vector2(cx, _y_for(od, r, top_od)), 4.5, COL_CURSOR)

	# frame + titles
	draw_rect(r, COL_AXIS, false, 1.0)
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 15),
		TITLE, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.80, 0.88, 0.98))
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L + 178, 15),
		SUBTITLE, HORIZONTAL_ALIGNMENT_LEFT, -1, 10, COL_TEXT)
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 28),
		CAPTION % data.trajectory_uncertainty_od,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.62, 0.66, 0.72))
	# axis captions
	draw_string(ThemeDB.fallback_font, Vector2(4, r.position.y - 6),
		Y_AXIS, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, COL_TEXT)
	draw_string(ThemeDB.fallback_font, Vector2(r.end.x - 88, r.end.y + 26),
		X_AXIS, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, COL_TEXT)

func _draw_custom_trajectories(r: Rect2) -> void:
	var max_val: float = 0.01
	for v in custom_biomass:
		if float(v) > max_val:
			max_val = float(v)
	for v in ghost_biomass:
		if float(v) > max_val:
			max_val = float(v)
	var top_val := _nice_ceiling(max_val * 1.08)

	var first_h: float = float(custom_hours[0])
	var last_h: float = float(custom_hours[custom_hours.size() - 1])
	var span_h := maxf(last_h - first_h, 0.001)

	# Grid & Y ticks
	var ticks := 5
	for i in range(ticks + 1):
		var val := top_val * float(i) / float(ticks)
		var y := r.position.y + r.size.y - clampf(val / top_val, 0.0, 1.0) * r.size.y
		draw_line(Vector2(r.position.x, y), Vector2(r.end.x, y), COL_GRID, 1.0)
		draw_string(ThemeDB.fallback_font, Vector2(4, y + 4),
			"%.1f" % val, HORIZONTAL_ALIGNMENT_LEFT, PAD_L - 6, 10, COL_TEXT)

	# X ticks
	var step_h := 2.0 if span_h > 10.0 else 1.0
	var cur_h := first_h
	while cur_h <= last_h + 0.001:
		var norm_x := (cur_h - first_h) / span_h
		var x := r.position.x + norm_x * r.size.x
		draw_line(Vector2(x, r.position.y), Vector2(x, r.end.y), COL_GRID, 1.0)
		draw_string(ThemeDB.fallback_font, Vector2(x - 10, r.end.y + 15),
			"%d" % int(cur_h), HORIZONTAL_ALIGNMENT_LEFT, 20, 10, COL_TEXT)
		cur_h += step_h

	# 1. Ghost comparison curve (if present)
	if ghost_hours.size() > 1 and ghost_biomass.size() == ghost_hours.size():
		var ghost_poly := PackedVector2Array()
		for i in range(ghost_hours.size()):
			var gh: float = float(ghost_hours[i])
			var gv: float = float(ghost_biomass[i])
			var gx := r.position.x + clampf((gh - first_h) / span_h, 0.0, 1.0) * r.size.x
			var gy := r.position.y + r.size.y - clampf(gv / top_val, 0.0, 1.0) * r.size.y
			ghost_poly.append(Vector2(gx, gy))
		
		# Draw dashed effect for ghost curve
		if ghost_poly.size() >= 2:
			for k in range(ghost_poly.size() - 1):
				if k % 2 == 0 or true:
					draw_line(ghost_poly[k], ghost_poly[k + 1], Color(0.96, 0.65, 0.28, 0.65), 2.0)
				draw_circle(ghost_poly[k], 2.0, Color(0.96, 0.65, 0.28, 0.75))

	# 2. Primary solid curve
	var poly := PackedVector2Array()
	for i in range(custom_hours.size()):
		var ch: float = float(custom_hours[i])
		var cv: float = float(custom_biomass[i])
		var px := r.position.x + clampf((ch - first_h) / span_h, 0.0, 1.0) * r.size.x
		var py := r.position.y + r.size.y - clampf(cv / top_val, 0.0, 1.0) * r.size.y
		poly.append(Vector2(px, py))
	if poly.size() >= 2:
		draw_polyline(poly, COL_CURVE, 2.2, true)
	for pt in poly:
		draw_circle(pt, 2.4, COL_MARK)

	# 3. Synchronized cursor
	if cursor_visible and cursor_hour >= first_h and cursor_hour <= last_h:
		var cx := r.position.x + clampf((cursor_hour - first_h) / span_h, 0.0, 1.0) * r.size.x
		draw_line(Vector2(cx, r.position.y), Vector2(cx, r.end.y), COL_CURSOR, 1.5)

	# 4. Frame + Header Titles + Legend
	draw_rect(r, COL_AXIS, false, 1.0)
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 15),
		"Simulated Bioprocess Growth Trajectory", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.80, 0.88, 0.98))
	
	var legend_text := "● Primary: %s" % custom_label
	if ghost_label != "":
		legend_text += "    -- Ghost Ref: %s" % ghost_label
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 28),
		legend_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color(0.70, 0.82, 0.95))
	
	draw_string(ThemeDB.fallback_font, Vector2(4, r.position.y - 6),
		y_axis_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, COL_TEXT)
	draw_string(ThemeDB.fallback_font, Vector2(r.end.x - 88, r.end.y + 26),
		"hours of culture", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, COL_TEXT)
