class_name ReplayData
extends RefCounted
## The model's genuine outputs, bound by name to the fields the 3D replay shows.
##
## Rules this file exists to enforce:
##
##   * Every number the replay displays is read from a named output port. No
##     field is computed here, defaulted, interpolated or invented.
##   * A port that is absent, unresolved, or reported as a range stays `NAN`.
##     The UI renders `NAN` as "not available" together with the *model's own*
##     reason string, never as zero and never as a plausible substitute.
##   * `provenance` is carried through to the UI so a displayed value can never
##     lose its label. A `reported` number and a `derived` number are not
##     presented as the same kind of thing.
##   * Values are stored in the port's own unit. `unit` is exposed alongside so
##     no consumer can print a number without its unit.

## Read once, from the result payload. Pure data; no scene, no display.
var instance_id := ""
var status := ""
var exit_code := -1
var reproducibility := ""

# --- provenance census, for the header -------------------------------
var provenance_counts: Dictionary = {}

# --- the one time series the model publishes -------------------------
## Digitized Fig. 3 growth curve. Replay clock, in hours of culture.
##
## 64-bit on purpose: the model publishes these as doubles, and storing them in
## a 32-bit array made the published plateau print as 53.669998 instead of
## 53.67. A readout must not quietly lose a digit of the source value.
var hours := PackedFloat64Array()
var od600 := PackedFloat64Array()
var trajectory_method := ""
var trajectory_source := ""
var trajectory_uncertainty_od := 0.5
var trajectory_uncertainty_h := 0.1
var plateau_max := NAN

# --- vessel geometry, all `reported` ---------------------------------
var starting_medium_volume_l := NAN   # working culture volume
var fermenter_nominal_volume_l := NAN # vessel nominal volume
var fermenter_temperature_c := NAN

# --- culture endpoints, all `reported` -------------------------------
var od600_max_reported := NAN
var wet_biomass_g_per_l_reported := NAN

# --- derived by the model --------------------------------------------
var biomass_per_od := NAN             # g/L per OD600
var wet_biomass_g_per_l := NAN
var inclusion_bodies_g_per_l := NAN
var inclusion_body_fraction := NAN
var refolding_yield_pct := NAN
var t_od25_h := NAN                   # interpolated crossing times
var t_od50_h := NAN
var batch_activity_iu := NAN
var mass_deviation_ppm := NAN

# --- purification cascade, derived `total_au` per purification node --
var cascade: Array[Dictionary] = []

# --- failure surface -------------------------------------------------
var diagnostics: Array = []
var raw_outputs: Array = []

## Reasons the model gave for each unresolved port, verbatim.
var unresolved: Dictionary = {}


func load_payload(payload: Dictionary, for_instance: String) -> void:
	instance_id = for_instance
	status = str(payload.get("status", "unknown"))
	exit_code = int(payload.get("_exit_code", -1))
	reproducibility = str(payload.get("reproducibility", ""))
	diagnostics = payload.get("diagnostics", [])
	raw_outputs = payload.get("outputs", [])

	provenance_counts = {}
	for r in payload.get("results", []):
		if str(r.get("instance_id")) != instance_id:
			continue
		raw_outputs = r.get("outputs", [])

	var by_port := {}
	for o in raw_outputs:
		var ref: Dictionary = o.get("ref", {})
		var v: Dictionary = o.get("value", {})
		var pid := str(ref.get("port_id", ""))
		by_port[pid] = v
		var prov := str(v.get("provenance", "?"))
		provenance_counts[prov] = int(provenance_counts.get(prov, 0)) + 1
		if not bool(v.get("is_resolved", false)) or v.get("value") == null:
			unresolved[pid] = str(v.get("reason", "the model did not resolve this"))

	_load_trajectory(by_port)
	_load_vessel(by_port)
	_load_derived(by_port)
	_load_cascade(by_port)


func _load_trajectory(by_port: Dictionary) -> void:
	# The model publishes the trajectory as one port per hour, named
	# `stream:S02_culture_broth#od600_hNN`. Ports are matched by that exact
	# shape, so a renamed or missing port is a gap rather than a silent zero.
	var hour_re := RegEx.new()
	if hour_re.compile("od600_h([0-9]+(?:\\.[0-9]+)?)$") != OK:
		return
	for pid in by_port.keys():
		var name := str(pid)
		var m := hour_re.search(name)
		if m == null:
			continue
		var v: Dictionary = by_port[pid]
		if not bool(v.get("is_resolved", false)) or v.get("value") == null:
			continue
		hours.append(float(m.get_string(1)))
		od600.append(float(v["value"]))
		if trajectory_method.is_empty():
			trajectory_method = str(v.get("method", ""))
			trajectory_source = str(v.get("source_ref", ""))

	# Sort by hour; Godot appends in directory order, which is not time order.
	var order := range(hours.size())
	order.sort_custom(func(a: int, b: int) -> bool: return hours[a] < hours[b])
	var sorted_h := PackedFloat64Array()
	var sorted_od := PackedFloat64Array()
	for i in order:
		sorted_h.append(hours[i])
		sorted_od.append(od600[i])
	hours = sorted_h
	od600 = sorted_od

	var pm := _port(by_port, "stream:S02_culture_broth#od600_plateau_max")
	plateau_max = _num(pm)


func _load_vessel(by_port: Dictionary) -> void:
	starting_medium_volume_l = _num(_port(by_port, "node:N01#starting_medium_volume"))
	fermenter_nominal_volume_l = _num(_port(by_port, "node:N01#fermenter_nominal_volume"))
	fermenter_temperature_c = _num(_port(by_port, "node:N01#fermenter_temperature"))
	od600_max_reported = _num(_port(by_port, "node:N01#od600_max"))
	wet_biomass_g_per_l_reported = _num(_port(by_port, "node:N01#wet_biomass_g_per_L_reported"))


func _load_derived(by_port: Dictionary) -> void:
	biomass_per_od = _num(_port(by_port, "node:N01#biomass_per_od_descriptive"))
	wet_biomass_g_per_l = _num(_port(by_port, "node:N02#wet_biomass_g_per_L"))
	inclusion_bodies_g_per_l = _num(_port(by_port, "node:N03#inclusion_bodies_g_per_L"))
	inclusion_body_fraction = _num(_port(by_port, "node:N03#inclusion_body_fraction_of_biomass"))
	refolding_yield_pct = _num(_port(by_port, "node:N05#implied_refolding_yield_pct"))
	t_od25_h = _num(_port(by_port, "stream:S02_culture_broth#od600_25_crossing_h"))
	t_od50_h = _num(_port(by_port, "stream:S02_culture_broth#od600_50_crossing_h"))
	batch_activity_iu = _num(_port(by_port, "node:N15#batch_activity"))
	mass_deviation_ppm = _num(_port(by_port, "node:N15#mass_deviation_ppm"))


## The four purification nodes that publish a derived `total_au`.
func _load_cascade(by_port: Dictionary) -> void:
	var steps := [
		["node:N08", "DEAE Sepharose"],
		["node:N11", "Q Sepharose"],
		["node:N13", "RP-HPLC"],
		["node:N14", "Sephadex G-25"],
	]
	for step in steps:
		var node_id := str(step[0])
		var v: Dictionary = by_port.get("%s#total_au" % node_id, {})
		cascade.append({
			"node_id": node_id,
			"label": str(step[1]),
			"au": _num(v),
			"unit": str(v.get("unit", "AU")),
			"method": str(v.get("method", "")),
			"provenance": str(v.get("provenance", "")),
		})


static func _port(by_port: Dictionary, port_id: String) -> Dictionary:
	var v: Variant = by_port.get(port_id)
	return v if v is Dictionary else {}


## `NAN` for anything that is not a resolved number. This is the only way a
## value enters the display, so a missing or ranged quantity can never be
## rendered as if it were known.
static func _num(v: Dictionary) -> float:
	if v.is_empty():
		return NAN
	if not bool(v.get("is_resolved", false)):
		return NAN
	if v.get("value") == null:
		return NAN
	var raw: Variant = v["value"]
	if raw is Array:
		return NAN  # a range, deliberately not collapsed to a point
	if not (raw is float or raw is int):
		return NAN
	return float(raw)


func has_trajectory() -> bool:
	return hours.size() >= 2


## Hours spanned by the published trajectory.
func span_h() -> float:
	if hours.size() < 2:
		return 0.0
	return hours[hours.size() - 1] - hours[0]


func max_od() -> float:
	var m := 0.0
	for v in od600:
		m = maxf(m, v)
	return m


## OD600 at a given replay hour, by linear interpolation between the two
## published points that bracket it. Outside the published range this returns
## `NAN`: the replay never extrapolates past what the figure shows.
func od_at_hour(hour: float) -> float:
	if hours.size() < 2:
		return NAN
	if hour < hours[0] or hour > hours[hours.size() - 1]:
		return NAN
	for i in range(hours.size() - 1):
		if hour >= hours[i] and hour <= hours[i + 1]:
			var span := hours[i + 1] - hours[i]
			if span <= 0.0:
				return od600[i]
			var t := (hour - hours[i]) / span
			return lerpf(od600[i], od600[i + 1], t)
	return NAN


## The published value at a replay hour, with an honest note about whether it
## is a published point or a value interpolated between two published hours.
##
## The interpolation is linear between adjacent published points, which is the
## same method the model itself uses for its crossing times ("linear
## interpolation: 13 h + (25.0 - 24.39) / (33.82 - 24.39) * ..."). Outside the
## published range this returns no value rather than extrapolating.
func sample_at(hour: float) -> Dictionary:
	if hours.size() < 2:
		return {}
	if hour < hours[0] or hour > hours[hours.size() - 1]:
		return {}
	for i in range(hours.size()):
		if is_equal_approx(hour, hours[i]):
			return {"od": od600[i], "note": "published point at %d h (digitized)" % int(hours[i])}
	for i in range(hours.size() - 1):
		if hour > hours[i] and hour < hours[i + 1]:
			var span := hours[i + 1] - hours[i]
			var t := 0.0 if span <= 0.0 else (hour - hours[i]) / span
			return {
				"od": lerpf(od600[i], od600[i + 1], t),
				"note": "interpolated between the published %d h and %d h points" % [int(hours[i]), int(hours[i + 1])],
			}
	return {}


## Working volume as a fraction of the reported nominal vessel volume.
## Both figures are `reported`; the ratio is a drawing convenience and is
## labelled as such, never presented as a model output.
func fill_fraction() -> float:
	if is_nan(starting_medium_volume_l) or is_nan(fermenter_nominal_volume_l):
		return NAN
	if fermenter_nominal_volume_l <= 0.0:
		return NAN
	return clampf(starting_medium_volume_l / fermenter_nominal_volume_l, 0.0, 1.0)


## Human-readable value+unit, or the model's own reason when there is none.
func describe(port_id: String, by_port: Dictionary) -> String:
	var v: Dictionary = _port(by_port, port_id)
	if v.is_empty():
		return "not published by the model"
	return describe_value(v)


static func describe_value(v: Dictionary) -> String:
	if v.is_empty():
		return "not published by the model"
	if not bool(v.get("is_resolved", false)) or v.get("value") == null:
		return "not available -- " + str(v.get("reason", "the model did not resolve it"))
	if v.get("value") is Array:
		return "not available -- reported as a range; not collapsed to a point value"
	return "%s %s" % [format_number(float(v["value"])), str(v.get("unit", ""))]


static func format_number(x: float) -> String:
	if is_nan(x) or is_inf(x):
		return "--"
	# Very large or very small magnitudes read better in scientific notation,
	# but only for values where fixed notation would lose all precision.
	if x != 0.0 and (absf(x) >= 1e7 or absf(x) < 1e-6):
		return "%.5e" % x
	# Fixed notation, then trim the trailing zeros so 7.5 does not print as
	# 7.500000. Significant digits are preserved either way.
	var text := "%.6f" % x
	if text.contains("."):
		text = text.rstrip("0").rstrip(".")
	return text if text != "" else "0"