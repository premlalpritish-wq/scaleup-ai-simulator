class_name CascadeChart
extends Control
## The purification cascade as the model derives it.
##
## Each bar is a `total_au` value the model computed from a reported fraction
## volume times a reported AU/mL concentration. AU is instrument-relative: the
## spectrophotometer was water-blanked (Zielinski et al. 2019 sec. 2.18), and
## the unit registry defines no conversion from AU to grams, molarity or IU.
## So this chart is in AU and must not be read as a concentration or a mass.

const PAD_L := 8.0
const PAD_R := 8.0
const PAD_T := 50.0
const PAD_B := 46.0

## Drawn titles, exposed as constants so the wording can be asserted.
const TITLE := "Instrument signal after each purification step"
const SUBTITLE := "absorbance units (AU) measured by the spectrophotometer; values drop as protein is purified"
const CAVEAT := "not a protein concentration -- see the note under the chart"
const Y_AXIS := "AU"

const COL_BAR := Color(0.52, 0.74, 0.95)
const COL_MISSING := Color(0.35, 0.36, 0.40)
const COL_TEXT := Color(0.72, 0.75, 0.80)
const COL_AXIS := Color(0.45, 0.48, 0.54)

var data: ReplayData = null


func _ready() -> void:
	custom_minimum_size = Vector2(0, 162)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_data(d: ReplayData) -> void:
	data = d
	queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.10, 0.11, 0.14), true)

	if data == null or data.cascade.is_empty():
		draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 15),
			TITLE, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.80, 0.88, 0.98))
		draw_string(ThemeDB.fallback_font, Vector2(PAD_L, size.y * 0.5),
			"the model published no purification quantities",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, COL_TEXT)
		return

	var top := 0.0
	for step in data.cascade:
		var au: float = float(step["au"])
		if not is_nan(au):
			top = maxf(top, au)
	if top <= 0.0:
		top = 1.0
	top *= 1.18

	var plot := Rect2(PAD_L, PAD_T, maxf(size.x - PAD_L - PAD_R, 1.0), maxf(size.y - PAD_T - PAD_B, 1.0))
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 15),
		TITLE, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.80, 0.88, 0.98))
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 28),
		SUBTITLE, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.62, 0.66, 0.72))
	draw_string(ThemeDB.fallback_font, Vector2(PAD_L, 40),
		CAVEAT, HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color(0.95, 0.72, 0.55))

	var n := data.cascade.size()
	var slot := plot.size.x / float(n)
	var bar_w := slot * 0.52

	for i in range(n):
		var step: Dictionary = data.cascade[i]
		var au: float = float(step["au"])
		var cx := plot.position.x + slot * (float(i) + 0.5)
		var rect := Rect2(cx - bar_w * 0.5, plot.position.y, bar_w, plot.size.y)

		if is_nan(au):
			# Never draw a zero-height bar for a missing value: that reads as
			# "measured, and it was nothing".
			var missing := Rect2(rect.position, Vector2(rect.size.x, rect.size.y))
			draw_rect(missing, Color(COL_MISSING, 0.20), true)
			draw_string(ThemeDB.fallback_font, Vector2(cx - slot * 0.5, plot.end.y + 14),
				str(step["label"]), HORIZONTAL_ALIGNMENT_LEFT, slot, 9, COL_TEXT)
			draw_string(ThemeDB.fallback_font, Vector2(cx - 40, plot.end.y + 27),
				"not available", HORIZONTAL_ALIGNMENT_LEFT, slot, 9, Color(0.85, 0.62, 0.55))
			continue

		var h := plot.size.y * clampf(au / top, 0.0, 1.0)
		var bar := Rect2(rect.position.x, plot.end.y - h, rect.size.x, h)
		draw_rect(bar, COL_BAR, true)
		draw_rect(bar, COL_BAR.lightened(0.25), false, 1.0)

		draw_string(ThemeDB.fallback_font, Vector2(cx - slot * 0.5, bar.position.y - 5),
			ReplayData.format_number(au), HORIZONTAL_ALIGNMENT_CENTER, slot, 10, COL_TEXT)
		draw_string(ThemeDB.fallback_font, Vector2(cx - slot * 0.5, plot.end.y + 14),
			str(step["label"]), HORIZONTAL_ALIGNMENT_LEFT, slot, 9, COL_TEXT)

	draw_line(Vector2(plot.position.x, plot.end.y), Vector2(plot.end.x, plot.end.y), COL_AXIS, 1.0)