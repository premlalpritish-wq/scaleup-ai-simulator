class_name CrossPaperPanel
extends VBoxContainer
## Renders the cross-paper scientific context for the model a scene shows.
##
## ## No rules here
##
## This panel renders two payloads and holds no model list, no quantity pair,
## no compatibility verdict and no paper of its own:
##
##   * `context` -- from `python -m composition.runner
##     --describe-cross-paper-context <model>`: the other registered models,
##     what each addresses, what it shares with the focus model, and the
##     compatibility position assembled from the registry, the manifests and
##     the evidence catalogue;
##   * `connections` -- from `python -m composition.runner
##     --describe-connections`: the authoritative compatibility system. Every
##     verdict badge, stance and permitted flag displayed here is read from
##     this payload, matched on (source model, target model), never from a
##     list kept in this file.
##
## A rule changed in `composition/composition/cross_model.py` reaches this
## panel without anything here being edited.
##
## ## What it will not claim
##
## A permitted verdict is never rendered as an implemented connection. The
## replay's own graph declares no connections; that count is read from the
## context payload and shown beside every verdict, and each card carries the
## same note. A permitted same-model boundary (Morris -> Morris, Ganjave ->
## Ganjave) is labelled as what it is: a boundary within one paper, not a
## connection between two different papers.

var _context: Dictionary = {}
var _connections: Dictionary = {}
var _focus_id := ""
var _selected := ""
var _toggle: Button = null
var _intro: VBoxContainer = null
var _list: VBoxContainer = null
var _detail: VBoxContainer = null
var _cards: Dictionary = {}

## Display states for one ordered pair. The mapping is presentation only: the
## stance, the permitted flag and the evidence basis all come from the
## authoritative connections payload.
const STATE_PERMITTED := "permitted"
const STATE_CONDITIONAL := "conditionally permitted"
const STATE_REFUSED := "refused"
const STATE_UNRESOLVED := "unresolved"
const STATE_UNDECLARED := "not assessed"

const STATE_COLOUR := {
	STATE_PERMITTED: Color(0.44, 0.78, 0.52),
	STATE_CONDITIONAL: Color(0.90, 0.76, 0.40),
	STATE_REFUSED: Color(0.92, 0.50, 0.42),
	STATE_UNRESOLVED: Color(0.66, 0.74, 0.92),
	STATE_UNDECLARED: Color(0.62, 0.66, 0.72),
}


func _ready() -> void:
	add_theme_constant_override("separation", 5)


## Show the assembled context. `connections` is the authoritative
## `--describe-connections` payload and owns every verdict on screen.
func set_context(context: Dictionary, connections: Dictionary) -> void:
	_context = context
	_connections = connections
	_focus_id = str(context.get("focus_model", ""))
	_selected = ""
	_build()
	_render()


func has_context() -> bool:
	return not _context.is_empty() and not _connections.is_empty()


# ---------------------------------------------------------- harness accessors

## Every related model the panel draws, in the order it draws them.
func model_ids() -> Array:
	var out: Array = []
	for entry in _related():
		out.append(str(entry.get("model_id", "")))
	return out


## The related model whose detail is open, or "" for none.
func selected_model() -> String:
	return _selected


## The exact `model_id@model_version` of the focus model.
func focus_reference() -> String:
	return str(_context.get("focus_reference", ""))


## The authoritative verdict for one ordered pair, from the connections
## payload. `state` is the display state above; `stance` and `evidence_basis`
## are the engine's own fields.
func verdict_for(source: String, target: String) -> Dictionary:
	for boundary in _connections.get("boundaries", []):
		if str(boundary.get("source_model", "")) == source \
				and str(boundary.get("target_model", "")) == target:
			return {
				"state": _state_of(boundary),
				"stance": str(boundary.get("stance", "")),
				"permitted": bool(boundary.get("permitted", false)),
				"evidence_basis": str(boundary.get("evidence_basis", "")),
				"enforced_by_engine": bool(boundary.get("enforced_by_engine", false)),
			}
	return {"state": STATE_UNDECLARED, "stance": "", "permitted": false,
		"evidence_basis": "", "enforced_by_engine": false}


## How many connections the replay's own graph declares. Read from the
## context payload, which read it from the graph document on disk.
func replay_connection_count() -> Variant:
	return _context.get("replay_scope", {}).get("connection_count", "?")


## The number of evidence citations one related model's assessment carries.
func evidence_count_for(model_id: String) -> int:
	for entry in _related():
		if str(entry.get("model_id", "")) == model_id:
			var comp: Dictionary = entry.get("compatibility_towards_focus", {})
			return (comp.get("evidence", []) as Array).size()
	return 0


## True when the panel draws a card for `model_id`.
func shows_model(model_id: String) -> bool:
	return _cards.has(model_id)


## The permitted ordered pairs, as `"source -> target"` strings, read from the
## authoritative connections payload.
func permitted_pairs() -> PackedStringArray:
	var names := PackedStringArray()
	for boundary in _connections.get("boundaries", []):
		if bool(boundary.get("permitted", false)):
			names.append("%s -> %s" % [str(boundary.get("source_model", "")),
				str(boundary.get("target_model", ""))])
	return names


## The model's declared gaps, as `{parameter_id, label, why_it_matters}`.
func focus_gaps() -> Array:
	return _context.get("focus", {}).get("declared_gaps", []) as Array


## The ingested papers examined against the focus model's gaps.
func examined_papers() -> Array:
	return _context.get("examined_papers", []) as Array


## True when the examined-papers section is rendered and non-empty.
func shows_examined_papers() -> bool:
	return not examined_papers().is_empty()


## The replay's own scope statement, verbatim from the context payload.
func replay_scope_statement() -> String:
	return str(_context.get("replay_scope", {}).get("statement", ""))


## One related model's full record, for tests and for the detail area.
func related_record(model_id: String) -> Dictionary:
	for entry in _related():
		if str(entry.get("model_id", "")) == model_id:
			return entry
	return {}


## Escape payload text for BBCode, the same rule the rest of this project uses.
static func _bb(text: String) -> String:
	return str(text).replace("[", "[lb]")


# ------------------------------------------------------------------ building

func _build() -> void:
	for c in get_children():
		c.queue_free()
	_cards.clear()

	var head := Label.new()
	head.text = "Connected scientific knowledge"
	head.add_theme_font_size_override("font_size", 13)
	add_child(head)

	_intro = VBoxContainer.new()
	_intro.add_theme_constant_override("separation", 4)
	add_child(_intro)

	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0, 220)
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)

	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 5)
	scroll.add_child(_list)

	_detail = VBoxContainer.new()
	_detail.add_theme_constant_override("separation", 4)
	_detail.visible = false
	add_child(_detail)


func _related() -> Array:
	return _context.get("related_models", []) as Array


func _render() -> void:
	_render_intro()
	for entry in _related():
		_list.add_child(_card(entry))
	_render_papers()


func _render_intro() -> void:
	for c in _intro.get_children():
		c.queue_free()

	var focus: Dictionary = _context.get("focus", {})
	_intro.add_child(_note(
		("Other models and papers this project has already ingested, and what the "
		+ "compatibility engine says about composing them with %s. None of them "
		+ "drives this replay.") % _bb(str(focus.get("reference", _focus_id)))))

	var scope: Dictionary = _context.get("replay_scope", {})
	_intro.add_child(_note(_bb(str(scope.get("statement", "")))))

	# The permitted pairs are reported as what they are: boundaries the engine
	# allows. None of them is a connection in this replay, and the panel says
	# so rather than leaving the permitted count to be misread.
	var permitted := permitted_pairs()
	if not permitted.is_empty():
		_intro.add_child(_note(
			("The compatibility engine permits %d ordered pair(s) -- %s. Both are "
			+ "same-model boundaries, not connections between different papers, "
			+ "and this replay declares %s connection(s).") % [
				permitted.size(), _bb(", ".join(permitted)),
				str(replay_connection_count())]))


# --------------------------------------------------------------------- cards

func _card(entry: Dictionary) -> Control:
	var model_id := str(entry.get("model_id", ""))
	var to_focus: Dictionary = entry.get("compatibility_towards_focus", {})
	var verdict := verdict_for(model_id, _focus_id)

	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	var state := str(verdict.get("state", STATE_UNDECLARED))
	var base: Color = STATE_COLOUR.get(state, STATE_COLOUR[STATE_UNDECLARED])
	style.bg_color = Color(base.r, base.g, base.b, 0.08)
	style.border_color = Color(base.r, base.g, base.b, 0.45)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 7
	style.content_margin_right = 7
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	panel.add_theme_stylebox_override("panel", style)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	panel.add_child(box)

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	box.add_child(head)

	var title := Label.new()
	title.text = _display_title(entry)
	title.add_theme_font_size_override("font_size", 11)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)

	var badge := Label.new()
	badge.text = "  %s  " % state.to_upper()
	badge.add_theme_font_size_override("font_size", 9)
	badge.modulate = base
	head.add_child(badge)

	# The exact reference and paper identity stay on the card: a reader must be
	# able to tell which model and which publication the verdict belongs to.
	_kv(box, "model", _bb(str(entry.get("reference", model_id))))
	var paper := str(entry.get("source_paper", ""))
	if paper != "":
		_kv(box, "source paper", _bb(paper))
	var doi := str(entry.get("doi", ""))
	if doi != "":
		_kv(box, "doi", _bb(doi))

	# The one-line summary of why this model matters to the current paper, and
	# the honesty note that it is context only.
	var shared := str(to_focus.get("shared_context", ""))
	if shared != "":
		_kv(box, "what it shares", _bb(shared))
	_kv(box, "status in this replay", "context only -- not connected")

	# Selection: clicking the card opens the full assessment below, without
	# leaving the replay. The button is the whole head row, so the card is
	# visibly clickable rather than hiding the affordance in a small corner.
	var open := Button.new()
	open.text = "Inspect scientific context"
	open.add_theme_font_size_override("font_size", 9)
	open.tooltip_text = "Open the full compatibility assessment for %s" % model_id
	open.pressed.connect(func() -> void: _toggle_detail(model_id))
	box.add_child(open)

	_cards[model_id] = panel
	return panel


func _toggle_detail(model_id: String) -> void:
	_selected = model_id if _selected != model_id else ""
	_render_detail()


func _render_detail() -> void:
	for c in _detail.get_children():
		c.queue_free()
	_detail.visible = not _selected.is_empty()
	if _selected.is_empty():
		return

	var entry := related_record(_selected)
	if entry.is_empty():
		return

	var to_focus: Dictionary = entry.get("compatibility_towards_focus", {})
	var from_focus: Dictionary = entry.get("compatibility_from_focus", {})

	_detail.add_child(_heading(
		"Scientific context: %s" % _bb(str(entry.get("reference", _selected))),
		Color(0.82, 0.88, 0.96)))

	# ---- what the model addresses -------------------------------------
	var addresses: Dictionary = entry.get("what_it_addresses", {})
	_kv(_detail, "what it addresses", _bb(str(addresses.get("text", ""))))
	_kv(_detail, "description origin", _bb(str(addresses.get("origin", ""))))

	var caps: Dictionary = entry.get("capabilities_block", {})
	var capabilities: Array = caps.get("capabilities", [])
	if not capabilities.is_empty():
		_kv(_detail, "declared capabilities", _bb(", ".join(capabilities)))
	var unsupported: Dictionary = caps.get("unsupported_capabilities", {})
	if not unsupported.is_empty():
		var bits := PackedStringArray()
		for k in unsupported.keys():
			bits.append("%s: %s" % [_bb(str(k)), _bb(str(unsupported[k]))])
		_kv(_detail, "declared unsupported", _bb("; ".join(bits)))

	# ---- the compatibility position, both directions -------------------
	_section(_detail, "%s -> %s" % [_selected, _focus_id])
	_render_direction(_detail, to_focus)

	_section(_detail, "%s -> %s" % [_focus_id, _selected])
	_render_direction(_detail, from_focus)

	# ---- the honesty note ------------------------------------------------
	_detail.add_child(_note(
		"No connection between these models is present in this replay. The "
		+ "quantities above are what a future, explicitly matched model could "
		+ "carry -- not values this replay reads or displays."))


func _render_direction(parent: VBoxContainer, comp: Dictionary) -> void:
	if not bool(comp.get("declared", false)):
		parent.add_child(_note("No boundary is declared for this ordered pair."))
		return
	parent.add_child(_note(_bb(str(comp.get("shared_context", "")))))
	var difference := str(comp.get("fundamental_difference", ""))
	if difference != "":
		parent.add_child(_note(_bb(difference)))
	var unresolved: Array = comp.get("unresolved", [])
	if not unresolved.is_empty():
		parent.add_child(_note("What would resolve the gap:"))
		for u in unresolved:
			parent.add_child(_note("  - " + _bb(str(u))))
	var remediation := str(comp.get("remediation", ""))
	if remediation != "":
		parent.add_child(_note("What to do instead: " + _bb(remediation)))
	var assumptions: Array = comp.get("assumptions", [])
	if not assumptions.is_empty():
		parent.add_child(_note("Required assumptions:"))
		for a in assumptions:
			parent.add_child(_note("  - " + _bb(str(a))))
	var evidence: Array = comp.get("evidence", [])
	if not evidence.is_empty():
		parent.add_child(_note("Evidence:"))
		for e in evidence:
			parent.add_child(_note("  - " + _bb(str(e))))

	# The quantity pairs the policy names, each with its own standing. These
	# are the engine's per-pair verdicts, read from the boundary data, and
	# they inherit this direction's state for colouring: the boundary's own
	# evidence basis is the authority for how the pair should read.
	var pairs: Array = comp.get("quantity_pairs", [])
	if not pairs.is_empty():
		parent.add_child(_note("Quantity pairs the policy names:"))
		var direction_state: Color = STATE_COLOUR.get(
			_state_of_verdict(str(comp.get("stance", ""))), Color(1, 1, 1))
		for p in pairs:
			var pair: Dictionary = p
			var line := "%s -> %s: %s" % [
				str(pair.get("source_quantity", "")),
				str(pair.get("target_quantity", "")),
				str(pair.get("verdict", ""))]
			var pl := _note("  - " + _bb(line))
			pl.modulate = direction_state
			parent.add_child(pl)
			var meaning := str(pair.get("meaning", ""))
			if meaning != "":
				parent.add_child(_note("      " + _bb(meaning)))
			if not bool(pair.get("connection_in_replay", false)):
				parent.add_child(_note(
					"      not present in this replay's graph"))


## The examined papers, as context for the focus model's declared gaps.
func _render_papers() -> void:
	var papers := examined_papers()
	if papers.is_empty():
		return
	var head := Button.new()
	head.toggle_mode = true
	head.button_pressed = false
	head.alignment = HORIZONTAL_ALIGNMENT_LEFT
	head.add_theme_font_size_override("font_size", 10)
	var caption := "Papers examined against this model's declared gaps (%d)" % papers.size()
	head.text = "▸  " + caption
	_list.add_child(head)

	var body := VBoxContainer.new()
	body.visible = false
	body.add_theme_constant_override("separation", 3)
	_list.add_child(body)

	head.toggled.connect(func(on: bool) -> void:
		body.visible = on
		head.text = ("▾  " if on else "▸  ") + caption)

	for p in papers:
		var paper: Dictionary = p
		var line := "%s -- %s, %s %s (%s, %s)" % [
			str(paper.get("finding_id", "")),
			_bb(str(paper.get("quantity_label", ""))),
			ReplayData.format_number(float(paper.get("value", 0.0))),
			str(paper.get("unit", "")),
			str(paper.get("verdict", "")),
			str(paper.get("independence", ""))]
		body.add_child(_note(line))
		var citation := str(paper.get("citation", ""))
		if citation != "":
			body.add_child(_note("  " + _bb(citation)))
		var locator := str(paper.get("locator", ""))
		if locator != "":
			body.add_child(_note("  " + _bb(locator)))
		var quote := str(paper.get("quote", ""))
		if quote != "":
			body.add_child(_note("  \"" + _bb(quote) + "\""))
		var nots: Array = paper.get("does_not_resolve", [])
		for n in nots:
			body.add_child(_note("  - " + _bb(str(n))))


# ------------------------------------------------------------------- helpers

func _display_title(entry: Dictionary) -> String:
	var title := str(entry.get("title", "")).strip_edges()
	if title != "":
		return title
	# The model's own rule, kept here too: a model that publishes no title is
	# named by its identifier, never by a phrase this panel composed.
	return str(entry.get("reference", "unknown model"))


func _state_of(boundary: Dictionary) -> String:
	"""The display state of one authoritative boundary."""
	var permitted := bool(boundary.get("permitted", false))
	var unresolved: Array = boundary.get("unresolved", [])
	if permitted:
		# Permitted under a stated assumption the engine itself records as
		# unresolved is conditionally permitted, not a validated coupling.
		if not unresolved.is_empty():
			return STATE_CONDITIONAL
		return STATE_PERMITTED
	var basis := str(boundary.get("evidence_basis", ""))
	if basis == "evidence_limited":
		# Failing closed because no rule classifies the pair is an absence of
		# a judgement -- never a finding of physical incompatibility.
		return STATE_UNRESOLVED
	if str(boundary.get("stance", "")) == "refused_unclassified":
		return STATE_UNRESOLVED
	if bool(boundary.get("declared", true)) or "stance" in boundary:
		return STATE_REFUSED
	return STATE_UNDECLARED


func _state_of_verdict(stance: String) -> String:
	if stance.begins_with("permitted"):
		return STATE_PERMITTED
	if stance.begins_with("refused_unclassified") or stance == "engine_refused":
		return STATE_UNRESOLVED
	if stance.begins_with("refused") or stance == "no_shared_quantity":
		return STATE_REFUSED
	return STATE_UNDECLARED


func _heading(text: String, colour: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 10)
	l.modulate = colour
	return l


func _section(parent: VBoxContainer, title: String) -> void:
	parent.add_child(_heading("== %s ==" % title, Color(0.70, 0.79, 0.95)))


func _kv(parent: VBoxContainer, key: String, value: String) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(150, 0)
	name_label.add_theme_font_size_override("font_size", 9)
	name_label.modulate = Color(1, 1, 1, 0.5)
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value_label.add_theme_font_size_override("font_size", 9)
	value_label.modulate = Color(1, 1, 1, 0.72)
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	parent.add_child(row)


func _note(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 9)
	l.modulate = Color(1, 1, 1, 0.6)
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l

