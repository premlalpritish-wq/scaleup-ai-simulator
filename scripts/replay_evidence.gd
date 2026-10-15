class_name ReplayEvidencePanel
extends VBoxContainer
## Turns an unknown quantity from a dead end into an investigation.
##
## The panel never proposes a value for the model. It shows what is missing,
## what was searched, what was found, how each candidate's conditions differ
## from the target process, and what a reader would have to do next. A candidate
## can only be shown as validated if it passed every registered criterion, and
## nothing in this panel can set that flag.

signal proposal_requested(target_id: String, target_label: String)

var _catalogue: Dictionary = {}
var _open_target := ""
var _body: VBoxContainer = null
var _toggle: Button = null

const VERDICT_COLOUR := {
	"found": Color(0.44, 0.78, 0.52),
	"validated": Color(0.44, 0.78, 0.52),
	"unverified": Color(0.90, 0.76, 0.40),
	"incompatible": Color(0.92, 0.50, 0.42),
}
const VERDICT_PLAIN := {
	"found": "Compatible conditions, not yet validated",
	"validated": "Validated",
	"unverified": "Plausibly related, needs checking",
	"incompatible": "Incompatible conditions",
}
const INDEPENDENCE_PLAIN := {
	"external": "Independent of the target paper",
	"target_source": "NOT INDEPENDENT - the supporting text also appears in the target paper",
	"undetermined": "Independence could not be determined",
}
const MATCH_COLOUR := {
	"match": Color(0.52, 0.82, 0.58),
	"partial": Color(0.90, 0.78, 0.42),
	"mismatch": Color(0.92, 0.50, 0.42),
	"unknown": Color(0.62, 0.64, 0.70),
}


func _ready() -> void:
	add_theme_constant_override("separation", 4)


## Hand over the catalogue emitted by `python -m composition.evidence.catalogue`.
func set_catalogue(payload: Dictionary) -> void:
	_catalogue = payload
	if not _open_target.is_empty():
		_render_target(_open_target)


func has_catalogue() -> bool:
	return not _catalogue.is_empty()


## Open the investigation for one unknown output port.
func open_target(port_id: String) -> void:
	_open_target = port_id
	_build()
	_render_target(port_id)


func close_target() -> void:
	_open_target = ""
	if _body != null:
		for c in _body.get_children():
			c.queue_free()


func _build() -> void:
	for c in get_children():
		c.queue_free()
	if _catalogue.is_empty():
		add_child(_note("The evidence catalogue has not loaded yet."))
		return

	_toggle = Button.new()
	_toggle.toggle_mode = true
	_toggle.button_pressed = true
	_toggle.alignment = HORIZONTAL_ALIGNMENT_LEFT
	_toggle.add_theme_font_size_override("font_size", 12)
	add_child(_toggle)

	_body = VBoxContainer.new()
	_body.name = "EvidenceBody"
	_body.add_theme_constant_override("separation", 5)
	add_child(_body)


func _note(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 10)
	l.modulate = Color(1, 1, 1, 0.6)
	l.custom_minimum_size = Vector2(500, 0)
	return l


func _heading(text: String, colour: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 11)
	l.modulate = colour
	return l


## The model's own vocabulary is plain language everywhere else in this UI; the
## schema names appear here because this panel is the technical view.
static func _bb(text: String) -> String:
	return str(text).replace("[", "[lb]")


func _render_target(port_id: String) -> void:
	for c in _body.get_children():
		c.queue_free()
	var targets: Dictionary = _catalogue.get("targets", {})
	if not targets.has(port_id):
		_body.add_child(_note("No investigation is registered for %s." % port_id))
		return
	var t: Dictionary = targets[port_id]
	_toggle.text = "▾  Investigating: %s" % str(t.get("label", port_id))
	_toggle.button_pressed = true

	# ---- what was checked against -------------------------------------
	var record: Dictionary = _catalogue.get("records_examined", {})
	if not record.is_empty():
		_body.add_child(_heading("Records examined", Color(0.82, 0.88, 0.96)))
		_body.add_child(_note("Model: %s (v%s, doi:%s)" % [
			_bb(str(record.get("model_id", ""))),
			str(record.get("model_version", "")),
			_bb(str(record.get("model_doi", "")))]))
		_body.add_child(_note("Run %s, graph digest %s. The digest covers %s." % [
			_bb(str(record.get("run_id", ""))),
			_bb(str(record.get("graph_reproducibility_digest", "")).substr(0, 16) + "..."),
			_bb(str(record.get("digest_covers", "")))]))

	# ---- what is missing and why it matters --------------------------
	var head := _heading("What is missing", Color(0.82, 0.88, 0.96))
	_body.add_child(head)
	_body.add_child(_note(_bb(str(t.get("why_it_matters", "")))))
	var mp := str(t.get("missing_parameter", ""))
	if mp != "":
		_body.add_child(_note("Declared by the model as %s, blocking: %s" % [
			_bb(mp), _bb(", ".join(t.get("blocks", [])))]))
	_body.add_child(_note("The model still reports this as unknown. Nothing below changes that."))

	# ---- what was searched --------------------------------------------
	var scope: Dictionary = _catalogue.get("search_scope", {})
	if not scope.is_empty():
		_body.add_child(_heading("What was searched", Color(0.82, 0.88, 0.96)))
		_body.add_child(_note(_bb(str(scope.get("description", "")))))
		var qs: Array = scope.get("queries", [])
		if not qs.is_empty():
			_body.add_child(_note("Queries: " + _bb("; ".join(qs))))

	# ---- candidates ----------------------------------------------------
	var findings: Array = _catalogue.get("findings", [])
	var mine: Array = []
	for f in findings:
		if port_id in (f.get("target_quantity_ids", []) as Array):
			mine.append(f)

	if mine.is_empty():
		_body.add_child(_heading("No candidate evidence found", Color(0.92, 0.50, 0.42)))
		_body.add_child(_note("The search returned nothing applicable. Stated plainly: " +
			_bb(str(scope.get("result", "no result recorded")))))
	else:
		for f in mine:
			_render_finding(f)
		_body.add_child(_note("Overall result: %d candidate(s) examined, none validated." % mine.size()))

	# ---- the action ----------------------------------------------------
	_body.add_child(_heading("What would actually close this gap", Color(0.98, 0.84, 0.58)))
	_body.add_child(_note(
		"No published source supplies a parameter measured under this process's "
		+ "conditions. The remaining route is to build a separate, explicitly "
		+ "parameterised model and fit it to batch data from this strain, rather "
		+ "than to import a number measured somewhere else."))
	var propose := Button.new()
	propose.text = "Propose a separate model or parameter set"
	propose.tooltip_text = "Records an action. It does not change the model or any value."
	propose.pressed.connect(func() -> void:
		proposal_requested.emit(port_id, str(t.get("label", port_id))))
	_body.add_child(propose)

	_render_conflicts()


## Conflicting evidence, reported and left open. This system identifies a
## disagreement; it does not decide which source is right.
func _render_conflicts() -> void:
	var conflicts: Array = _catalogue.get("conflicts", [])
	if conflicts.is_empty():
		return
	_body.add_child(_heading("Conflicting evidence (unresolved)", Color(0.94, 0.62, 0.48)))
	for c in conflicts:
		var entry: Dictionary = c
		var cl := _note("[%s] %s" % [
			str(entry.get("conflict_id", "")), _bb(str(entry.get("explanation", "")))])
		cl.modulate = Color(0.94, 0.72, 0.62)
		_body.add_child(cl)
		_body.add_child(_note("     affects: %s   ·   %s" % [
			_bb(", ".join(entry.get("affected_records", []) as Array)),
			_bb(str(entry.get("requires", "")))]))


func _render_finding(f: Dictionary) -> void:
	var assessment: Dictionary = f.get("assessment", {})
	var verdict := str(assessment.get("verdict", "unverified"))
	var card := VBoxContainer.new()
	card.add_theme_constant_override("separation", 2)
	_body.add_child(card)

	# title row
	var title := Label.new()
	title.text = "%s  %s" % [str(f.get("finding_id", "")), str(f.get("quantity_label", ""))]
	title.add_theme_font_size_override("font_size", 11)
	card.add_child(title)

	var badge := Label.new()
	badge.text = "  %s  " % str(VERDICT_PLAIN.get(verdict, verdict)).to_upper()
	badge.add_theme_font_size_override("font_size", 10)
	badge.modulate = VERDICT_COLOUR.get(verdict, Color(1, 1, 1))
	card.add_child(badge)

	# Independence sits directly under the verdict. A source whose supporting
	# text also appears in the target paper cannot corroborate the target paper,
	# whatever its conditions happen to match, so it must not be something the
	# reader has to expand a panel to discover.
	var indep := str(assessment.get("independence", "undetermined"))
	if indep != "external":
		var ib := Label.new()
		ib.text = "  %s" % str(INDEPENDENCE_PLAIN.get(indep, indep)).to_upper()
		ib.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		ib.add_theme_font_size_override("font_size", 10)
		ib.modulate = VERDICT_COLOUR["incompatible"]
		ib.custom_minimum_size = Vector2(500, 0)
		card.add_child(ib)

	# the extracted value, with its unit and provenance
	var value_line := Label.new()
	value_line.text = "  %s %s    %s, extraction confidence %s" % [
		ReplayData.format_number(float(f.get("value", 0.0))),
		str(f.get("unit", "")),
		str(f.get("provenance", "")),
		str(f.get("extraction_confidence", ""))]
	value_line.add_theme_font_size_override("font_size", 11)
	card.add_child(value_line)

	# source, with a followable locator
	var src: Dictionary = f.get("source", {})
	var loc := Label.new()
	loc.text = "  " + _bb(str(src.get("locator", "")))
	loc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	loc.add_theme_font_size_override("font_size", 10)
	loc.modulate = Color(0.66, 0.82, 0.98)
	loc.custom_minimum_size = Vector2(500, 0)
	card.add_child(loc)

	var quote := Label.new()
	quote.text = "  “" + _bb(str(src.get("quote", ""))) + "”"
	quote.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	quote.add_theme_font_size_override("font_size", 10)
	quote.modulate = Color(1, 1, 1, 0.72)
	quote.custom_minimum_size = Vector2(500, 0)
	card.add_child(quote)

	var unc: Variant = f.get("uncertainty")
	if unc != null:
		var u: Dictionary = unc
		card.add_child(_note("     uncertainty: %s, from %s to %s — %s" % [
			str(u.get("kind", "")), ReplayData.format_number(float(u.get("lo", 0.0))),
			ReplayData.format_number(float(u.get("hi", 0.0))), _bb(str(u.get("basis", "")))]))

	# The conditions it was measured under are part of the evidence, so they are
	# shown without having to expand anything.
	var conds: Dictionary = f.get("conditions", {})
	if not conds.is_empty():
		card.add_child(_note("     measured under:"))
		for dim in ["organism", "strain", "construct", "medium", "mode",
				"temperature_c", "scale_l"]:
			if conds.has(dim):
				var cv := str((conds[dim] as Dictionary).get("value", ""))
				card.add_child(_note("       · %s: %s" % [dim, _bb(cv)]))

	# why it does not fit
	var reasons: Array = assessment.get("reasons", [])
	if verdict == "incompatible" or verdict == "unverified":
		card.add_child(_note("     why it does not fit:"))
		for r in reasons:
			var rl := _note("       · " + _bb(str(r)))
			rl.modulate = VERDICT_COLOUR.get(verdict, Color(1, 1, 1))
			card.add_child(rl)

	# what it would not settle even if adopted
	var nots: Array = f.get("does_not_resolve", [])
	if not nots.is_empty():
		card.add_child(_note("     even if adopted, it would not settle:"))
		for r in nots:
			card.add_child(_note("       · " + _bb(str(r))))

	# condition comparison and validation, behind a toggle
	var detail_body := VBoxContainer.new()
	detail_body.visible = false

	var detail := Button.new()
	detail.toggle_mode = true
	detail.text = "▸  Condition comparison and validation for %s" % str(f.get("finding_id", ""))
	detail.add_theme_font_size_override("font_size", 10)
	detail.toggled.connect(_on_detail_toggled.bind(detail, detail_body))
	card.add_child(detail)
	card.add_child(detail_body)

	for d in assessment.get("dimensions", []):
		var dim: Dictionary = d
		var m := str(dim.get("match", "unknown"))
		var line := "%s%s   %s   vs   %s" % [
			"  [critical] " if bool(dim.get("critical", false)) else "  ",
			str(dim.get("dimension", "")),
			str(dim.get("candidate", "")),
			str(dim.get("target", "")),
		]
		var dl := Label.new()
		dl.text = line
		dl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		dl.add_theme_font_size_override("font_size", 9)
		dl.modulate = MATCH_COLOUR.get(m, Color(1, 1, 1))
		dl.custom_minimum_size = Vector2(500, 0)
		detail_body.add_child(dl)

	var validation: Dictionary = f.get("validation", {})
	var passed := 0
	for res in validation.get("results", []):
		if bool((res as Dictionary).get("passed", false)):
			passed += 1
	detail_body.add_child(_note("  validation: %d of %d criteria passed — NOT validated"
		% [passed, (validation.get("results", []) as Array).size()]))
	for res in validation.get("results", []):
		var r2: Dictionary = res
		var ok := bool(r2.get("passed", false))
		detail_body.add_child(_note("    %s %s  %s" % [
			"✓" if ok else "✗", str(r2.get("criterion_id", "")),
			_bb(str(r2.get("detail", "")))]))


## Expand the condition comparison and show which criteria passed or failed.
func _on_detail_toggled(pressed: bool, detail: Button, body: VBoxContainer) -> void:
	body.visible = pressed
	var caption := "Condition comparison and validation"
	var idx := str(detail.text).find(caption)
	if idx >= 0:
		detail.text = ("▾ " if pressed else "▸ ") + str(detail.text).substr(idx)