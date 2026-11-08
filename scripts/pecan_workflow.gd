extends Control
## Interactive view of the pecan RNA research workflow.
##
## This is an **evidence-audit visualisation**, not a simulator. It reads the four
## artifacts the research workflow already wrote
## (`composition/workflow_runs/pecan/`) and draws each protocol step as a node:
##
##   * green  - direct evidence, quoted from the pecan paper;
##   * amber  - an analogue hypothesis, transferred from another species;
##   * grey   - method-review evidence.
##
## Clicking a node shows the step's action, its reported and unknown parameters,
## and every supporting claim with its source, the verbatim passage, the evidence
## class and its uncertainty. Nothing is computed here: every string and number on
## screen comes from those four documents. The model publishes counts and ratios
## about its evidence base; it does not predict RNA yield, RIN or degradation, and
## this scene says so in the header and in the outputs tab.

const RUNS_DIR := "res://composition/workflow_runs"
const DEFAULT_CASE := "pecan"
const ACCENT := Color(0.42, 0.66, 1.0)
const INK := Color(0.87, 0.91, 0.97)
const MUTED := Color(1, 1, 1, 0.58)
const GOOD := Color(0.45, 0.83, 0.55)
const WARN := Color(0.96, 0.78, 0.42)
const METHOD := Color(0.68, 0.75, 0.85)

var _case_id := DEFAULT_CASE
var _selector: OptionButton
var _title: Label
var _readiness: HBoxContainer
var _graph: PecanStepGraph
var _tabs: TabContainer
var _detail: VBoxContainer
var _detail_scroll: ScrollContainer
var _outputs_holder: MarginContainer
var _unresolved_body: VBoxContainer
var _case_body: VBoxContainer
var _status: Label

var _model: Dictionary = {}
var _encoded: Dictionary = {}
var _simulation: Dictionary = {}
var _graph_doc: Dictionary = {}
var _steps: Array = []
var _claims: Dictionary = {}
var _sources: Dictionary = {}
var _selected := ""


func _ready() -> void:
	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 4)
	add_child(root)
	root.add_child(_header())

	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 8)
	root.add_child(body)

	body.add_child(_left_column())
	body.add_child(_right_column())

	_status = Label.new()
	_status.name = "CaseStatus"
	_status.add_theme_font_size_override("font_size", 10)
	_status.modulate = MUTED
	root.add_child(_status)

	_populate_case_selector()
	_load_case(_case_id)


func _header() -> Control:
	var box := PanelContainer.new()
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	box.add_child(row)

	var title := Label.new()
	title.text = "Pecan RNA extraction — evidence-audit workflow"
	title.add_theme_font_size_override("font_size", 15)
	row.add_child(title)

	var note := Label.new()
	note.text = "evidence workflow visualisation · no predictive RNA yield, RIN or degradation"
	note.add_theme_font_size_override("font_size", 10)
	note.modulate = MUTED
	row.add_child(note)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)

	var case_label := Label.new()
	case_label.text = "Case"
	case_label.add_theme_font_size_override("font_size", 10)
	case_label.modulate = MUTED
	row.add_child(case_label)
	_selector = OptionButton.new()
	_selector.name = "CaseSelector"
	_selector.custom_minimum_size = Vector2(210, 0)
	_selector.item_selected.connect(_on_case_selected)
	row.add_child(_selector)

	var back := Button.new()
	back.name = "BackButton"
	back.text = "Back to workshop"
	back.pressed.connect(func() -> void: get_tree().change_scene_to_file.call_deferred("res://scenes/workshop.tscn"))
	row.add_child(back)
	return box


func _left_column() -> Control:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 4)

	var readout := PanelContainer.new()
	var inner := VBoxContainer.new()
	readout.add_child(inner)
	_title = Label.new()
	_title.name = "CaseTitle"
	_title.add_theme_font_size_override("font_size", 12)
	inner.add_child(_title)
	var explain := Label.new()
	explain.text = (
		"Each node is one protocol step compiled from quote-verified claims. "
		+ "Direct evidence is quoted from the pecan paper; analogous evidence is a "
		+ "hypothesis transferred from another species. Arrows are protocol order "
		+ "inside an evidence class — the generated model has no connections."
	)
	explain.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	explain.add_theme_font_size_override("font_size", 9)
	explain.modulate = MUTED
	inner.add_child(explain)
	_readiness = HBoxContainer.new()
	_readiness.name = "Readiness"
	_readiness.add_theme_constant_override("separation", 6)
	inner.add_child(_readiness)
	column.add_child(readout)

	_graph = PecanStepGraph.new()
	_graph.name = "StepGraph"
	_graph.step_selected.connect(_on_step_selected)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.add_child(_graph)
	column.add_child(scroll)
	return column


func _right_column() -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(430, 0)
	_tabs = TabContainer.new()
	_tabs.name = "Panels"
	panel.add_child(_tabs)

	# 1. Step evidence
	_detail_scroll = ScrollContainer.new()
	_detail_scroll.name = "StepEvidence"
	_detail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_detail = VBoxContainer.new()
	_detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.add_theme_constant_override("separation", 4)
	_detail_scroll.add_child(_detail)
	_tabs.add_child(_detail_scroll)

	# 2. Workflow outputs — the existing composition results panel.
	_outputs_holder = MarginContainer.new()
	_outputs_holder.name = "WorkflowOutputs"
	_tabs.add_child(_outputs_holder)

	# 3. Unresolved quantities
	var unresolved_scroll := ScrollContainer.new()
	unresolved_scroll.name = "Unresolved"
	unresolved_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_unresolved_body = VBoxContainer.new()
	_unresolved_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_unresolved_body.add_theme_constant_override("separation", 2)
	unresolved_scroll.add_child(_unresolved_body)
	_tabs.add_child(unresolved_scroll)

	# 4. Case and artifacts
	var case_scroll := ScrollContainer.new()
	case_scroll.name = "CaseAndArtifacts"
	case_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_case_body = VBoxContainer.new()
	_case_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_case_body.add_theme_constant_override("separation", 2)
	case_scroll.add_child(_case_body)
	_tabs.add_child(case_scroll)
	return panel


func _populate_case_selector() -> void:
	_selector.clear()
	var cases := _available_cases()
	if cases.is_empty():
		_selector.add_item(_case_id)
		return
	for index in cases.size():
		_selector.add_item(cases[index])
		if cases[index] == _case_id:
			_selector.select(index)


func _available_cases() -> Array[String]:
	var found: Array[String] = []
	var dir := DirAccess.open(RUNS_DIR)
	if dir == null:
		return found
	for name in dir.get_directories():
		if FileAccess.file_exists(RUNS_DIR.path_join(name).path_join("model_spec.json")):
			found.append(name)
	found.sort()
	return found


func _on_case_selected(index: int) -> void:
	_load_case(str(_selector.get_item_text(index)))


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	if parsed is Dictionary:
		return parsed
	return {}



# ------------------------------------------------------------------- loading


func _load_case(case_id: String) -> void:
	_case_id = case_id
	_clear(_detail)
	_clear(_readiness)
	_clear(_unresolved_body)
	_clear(_case_body)
	for child in _outputs_holder.get_children():
		_outputs_holder.remove_child(child)
		child.queue_free()

	var base := RUNS_DIR.path_join(case_id)
	_model = _read_json(base.path_join("model_spec.json"))
	_encoded = _read_json(base.path_join("research_encoded.json"))
	_simulation = _read_json(base.path_join("simulation_result.json"))
	_graph_doc = _read_json(base.path_join("composition_graph.json"))

	if _model.is_empty() or _encoded.is_empty():
		_status.text = "Case '%s' has no compiled workflow artifacts." % case_id
		_title.text = "No case loaded"
		_graph.set_steps([])
		return

	_steps = _model.get("steps", [])
	_claims = {}
	for claim in _encoded.get("claims", []):
		_claims[str(claim.get("claim_id", ""))] = claim
	_sources = {}
	for source in _model.get("sources", []):
		_sources[str(source.get("source_id", ""))] = source

	_title.text = str(_model.get("title", case_id))
	_render_readiness()
	_graph.set_steps(_steps)
	_render_outputs()
	_render_unresolved()
	_render_case()
	_selected = ""
	_show_overview()
	var unknown_count := _unknown_parameter_count()
	_status.text = (
		"%d steps · %d claims · %d sources · %d unresolved parameter(s) · artifacts: %s"
		% [_steps.size(), _claims.size(), _sources.size(), unknown_count, base]
	)


func _render_readiness() -> void:
	var readiness: Dictionary = _model.get("readiness", {})
	_readiness.add_child(_chip("target protocol complete",
		"yes" if bool(readiness.get("protocol_complete_for_target", false)) else "no",
		GOOD if bool(readiness.get("protocol_complete_for_target", false)) else WARN))
	_readiness.add_child(_chip("target yield available",
		"yes" if bool(readiness.get("quantitative_yield_available_for_target", false)) else "no",
		GOOD if bool(readiness.get("quantitative_yield_available_for_target", false)) else WARN))
	_readiness.add_child(_chip("analogue protocol available",
		"yes" if bool(readiness.get("analogue_protocol_available", false)) else "no", METHOD))
	_readiness.add_child(_chip("model kind", str(_model.get("model_kind", "")), METHOD))


func _chip(key: String, value: String, colour: Color) -> Control:
	var label := Label.new()
	label.text = "%s: %s" % [key, value]
	label.add_theme_font_size_override("font_size", 9)
	label.modulate = colour
	return label


func _unknown_parameter_count() -> int:
	var count := 0
	for step in _steps:
		for parameter in step.get("parameters", []):
			if str(parameter.get("state", "")) == "unknown":
				count += 1
	return count


# ------------------------------------------------------------------- outputs


func _render_outputs() -> void:
	if _simulation.is_empty():
		var missing := Label.new()
		missing.text = "No simulation_result.json was found for this case."
		_outputs_holder.add_child(missing)
		return
	# Reuse the existing composition results panel untouched.
	var panel := ResultsPanel.new()
	panel.name = "Results"
	panel.setup(null)
	_outputs_holder.add_child(panel)
	panel.show_results(_simulation)


func _render_unresolved() -> void:
	var note := _label(
		"Every item below is stated by the compiled artifacts as unresolved. "
		+ "Nothing on this screen fills a gap.",
		9, MUTED)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_unresolved_body.add_child(note)

	var readiness: Dictionary = _model.get("readiness", {})
	_unresolved_body.add_child(_heading("Unresolved parameters (%d)" % _unknown_parameter_count()))
	for step in _steps:
		for parameter in step.get("parameters", []):
			if str(parameter.get("state", "")) != "unknown":
				continue
			_unresolved_body.add_child(_label(
				"• %s — %s (%s)" % [
					_human(str(parameter.get("name", ""))),
					str(step.get("label", "")),
					str(parameter.get("basis", "not stated")),
				], 9, WARN))

	var questions: Array = _model.get("unknowns", [])
	_unresolved_body.add_child(_heading("Open questions recorded by the encoder (%d)" % questions.size()))
	for question in questions:
		_unresolved_body.add_child(_label("• " + str(question), 9, INK))

	var hypotheses: Array = _model.get("hypotheses", [])
	_unresolved_body.add_child(_heading("Analogous hypotheses (%d) — not validated on pecan" % hypotheses.size()))
	for hypothesis in hypotheses:
		_unresolved_body.add_child(_label("• " + str(hypothesis), 9, WARN))
	_unresolved_body.add_child(_label(
		"Readiness flags: protocol complete for target=%s; quantitative yield=%s; analogue protocol=%s."
		% [
			str(readiness.get("protocol_complete_for_target", "?")),
			str(readiness.get("quantitative_yield_available_for_target", "?")),
			str(readiness.get("analogue_protocol_available", "?")),
		], 9, MUTED))



# ------------------------------------------------------------- step evidence


func _on_step_selected(step_id: String) -> void:
	_selected = step_id
	_show_step(step_id)
	_tabs.current_tab = 0


func _step_by_id(step_id: String) -> Dictionary:
	for step in _steps:
		if str(step.get("step_id", "")) == step_id:
			return step
	return {}


func _show_overview() -> void:
	_clear(_detail)
	_detail.add_child(_heading(_model.get("title", "Case")))
	var problem: Dictionary = _model.get("problem", {})
	_detail.add_child(_paragraph(str(problem.get("question", ""))))
	for key in ["organism", "tissue", "molecule"]:
		var tracked: Dictionary = problem.get(key, {})
		var value := str(tracked.get("value", "")) if tracked.get("value") != null else "(unknown)"
		_detail.add_child(_label("%s: %s (%s)" % [key.capitalize(), value, str(tracked.get("state", ""))], 9, INK))
	_detail.add_child(_paragraph(
		"Select a step node on the left to read its action, its reported and "
		+ "unknown parameters, and every supporting claim with its source and verbatim "
		+ "passage. Green nodes are direct pecan evidence; amber nodes are analogous "
		+ "hypotheses; grey nodes are method review."))
	_detail.add_child(_heading("Evidence mix"))
	var readiness: Dictionary = _model.get("readiness", {})
	_detail.add_child(_label(
		"direct target claims: %s · analogue claims: %s · method-review claims: %s"
		% [
			str(readiness.get("direct_target_claim_count", "?")),
			str(readiness.get("analogue_claim_count", "?")),
			str(readiness.get("method_review_claim_count", "?")),
		], 9, INK))
	_detail.add_child(_label(
		"direct steps: %s · analogue steps: %s · method-review steps: %s"
		% [
			str(readiness.get("direct_target_step_count", "?")),
			str(readiness.get("analogue_step_count", "?")),
			str(readiness.get("method_review_step_count", "?")),
		], 9, INK))
	_detail.add_child(_heading("Verification recorded by the workflow"))
	var verification: Dictionary = _encoded.get("verification", {})
	_detail.add_child(_label(
		"quotes verified: %s of %s · numbers verified: %s of %s · source-role ceiling: %s"
		% [
			str(verification.get("quotes_verified", "?")),
			str(verification.get("quotes_checked", "?")),
			str(verification.get("numeric_values_verified", "?")),
			str(verification.get("numeric_values_checked", "?")),
			str(verification.get("source_role_check", "?")),
		], 9, GOOD))


func _show_step(step_id: String) -> void:
	var step := _step_by_id(step_id)
	_clear(_detail)
	if step.is_empty():
		return
	var status := str(step.get("evidence_status", ""))
	var colour := status_colour(status)
	_detail.add_child(_heading(str(step.get("label", step_id))))
	_detail.add_child(_class_banner(status, bool(step.get("hypothesis", false))))
	_detail.add_child(_label("step id: %s · order %s" % [step_id, str(step.get("order", ""))], 9, MUTED))
	_detail.add_child(_paragraph(str(step.get("action", ""))))
	if str(step.get("notes", "")) != "":
		_detail.add_child(_paragraph(str(step.get("notes", "")), MUTED))

	_detail.add_child(_heading("Parameters"))
	for parameter in step.get("parameters", []):
		var state := str(parameter.get("state", ""))
		if state == "reported":
			_detail.add_child(_label(
				"• %s = %s %s (reported)%s" % [
					_human(str(parameter.get("name", ""))),
					_num(parameter.get("value")),
					str(parameter.get("unit", "")),
					" — " + str(parameter.get("basis", "")) if str(parameter.get("basis", "")) != "" else "",
				], 9, INK))
		else:
			_detail.add_child(_label(
				"• %s — unknown; not stated by the acquired sources (%s)" % [
					_human(str(parameter.get("name", ""))),
					str(parameter.get("basis", "")),
				], 9, WARN))

	var claims := _claims_for(step)
	_detail.add_child(_heading("Supporting claims (%d)" % claims.size()))
	if claims.is_empty():
		_detail.add_child(_label("No claim was recorded for this step.", 9, MUTED))
	for claim in claims:
		_detail.add_child(_claim_card(claim))

	var questions: Array = step.get("unknowns", [])
	if not questions.is_empty():
		_detail.add_child(_heading("Relevant uncertainty (%d)" % questions.size()))
		for question in questions:
			_detail.add_child(_label("• " + str(question), 9, WARN))
	_detail.add_child(_label("classification: " + status, 9, colour))



func _claims_for(step: Dictionary) -> Array:
	var out: Array = []
	for claim_id in step.get("claim_ids", []):
		if _claims.has(str(claim_id)):
			out.append(_claims[str(claim_id)])
	return out


func _class_banner(status: String, hypothesis: bool) -> Control:
	var text := "direct evidence — quoted from the pecan paper"
	var colour := GOOD
	if status.begins_with("analogous"):
		text = "analogue hypothesis — transferred from another species; NOT validated on pecan"
		colour = WARN
	elif status.begins_with("method"):
		text = "method review — neither a pecan measurement nor a species-specific protocol"
		colour = METHOD
	var banner := Label.new()
	banner.name = "ClassBanner"
	banner.text = text
	banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	banner.add_theme_font_size_override("font_size", 10)
	banner.modulate = colour
	if hypothesis and not status.begins_with("analogous"):
		banner.text += " (recorded as a hypothesis)"
	return banner


func _claim_card(claim: Dictionary) -> Control:
	var card := PanelContainer.new()
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	card.add_child(box)

	var specificity := str(claim.get("specificity", ""))
	box.add_child(_label(
		"%s · %s%s" % [
			_class_word(specificity),
			str(claim.get("claim_type", "")),
			" · hypothesis" if bool(claim.get("hypothesis", false)) else "",
		], 9, status_colour(specificity + "_")))

	var statement := " ".join([
		str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", "")),
	]).strip_edges()
	box.add_child(_paragraph(statement))

	var quote := Label.new()
	quote.name = "Quote"
	quote.text = "“%s”" % str(claim.get("quote", ""))
	quote.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	quote.add_theme_font_size_override("font_size", 9)
	quote.modulate = Color(0.80, 0.86, 0.94)
	box.add_child(quote)

	var source: Dictionary = _sources.get(str(claim.get("source_id", "")), {})
	box.add_child(_label(
		"%s — DOI %s — %s %s" % [
			str(source.get("title", str(claim.get("source_id", "")))),
			str(source.get("doi", "")),
			str(source.get("journal", "")),
			str(source.get("year", "")),
		], 8, MUTED))
	box.add_child(_label(
		"section: %s · organism: %s · value: %s %s" % [
			str(claim.get("section", "")),
			str(claim.get("organism", "")),
			str(claim.get("value")) if claim.get("value") != null else "—",
			str(claim.get("unit", "")),
		], 8, MUTED))
	if str(claim.get("uncertainty", "")) != "":
		box.add_child(_label("uncertainty: " + str(claim.get("uncertainty", "")), 8, WARN))
	return card



func _render_case() -> void:
	var problem: Dictionary = _model.get("problem", {})
	_case_body.add_child(_heading("Case"))
	_case_body.add_child(_paragraph(str(problem.get("question", ""))))
	_case_body.add_child(_label(
		"model: %s v%s · kind: %s" % [
			str(_model.get("model_id", "")), str(_model.get("model_version", "")),
			str(_model.get("model_kind", "")),
		], 9, MUTED))
	_case_body.add_child(_label(
		"generated graph connections: %d (single evidence-audit instance)"
		% len(_graph_doc.get("connections", [])), 9, MUTED))

	_case_body.add_child(_heading("Sources (%d)" % _sources.size()))
	for source_id in _sources:
		var source: Dictionary = _sources[source_id]
		_case_body.add_child(_label(
			"• %s — %s — DOI %s (%s)" % [
				str(source_id),
				str(source.get("title", "")),
				str(source.get("doi", "")),
				str(source.get("role", "")),
			], 8, INK))

	_case_body.add_child(_heading("Assumptions recorded by the model"))
	for assumption in _model.get("assumptions", []):
		_case_body.add_child(_label("• " + str(assumption), 9, MUTED))

	_case_body.add_child(_heading("Artifacts on disk"))
	var base := RUNS_DIR.path_join(_case_id)
	for name in ["problem_spec.json", "literature_manifest.json", "research_encoded.json",
			"model_spec.json", "composition_graph.json", "simulation_result.json"]:
		_case_body.add_child(_label("• %s" % base.path_join(name), 8, MUTED))
	_case_body.add_child(_paragraph(
		"Reproduce with: cd composition && python -m composition.runner --run-workflow "
		+ "composition/workflow/fixtures/%s/problem.json --repo-root .." % _case_id, MUTED))


# ------------------------------------------------------------------- helpers


static func status_colour(status: String) -> Color:
	if status.begins_with("direct"):
		return Color(0.45, 0.83, 0.55)
	if status.begins_with("analogous"):
		return Color(0.96, 0.78, 0.42)
	return Color(0.68, 0.75, 0.85)


static func _class_word(specificity: String) -> String:
	if specificity == "target_organism":
		return "direct (pecan)"
	if specificity == "analogous_species":
		return "analogous species"
	if specificity == "method_review":
		return "method review"
	return specificity


static func _human(name: String) -> String:
	return name.replace("_", " ")


static func _num(value: Variant) -> String:
	if value == null:
		return "—"
	return str(value)


func _heading(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	return label


func _paragraph(text: String, colour: Color = Color(0.87, 0.91, 0.97)) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	return label


func _label(text: String, size: int = 9, colour: Color = Color(0.87, 0.91, 0.97)) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.modulate = colour
	return label


func _clear(parent: Node) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()


# --------------------------------------------------------------- harness API

func case_id() -> String:
	return _case_id


func step_count() -> int:
	return _steps.size()


func edge_count() -> int:
	return _graph.edge_count() if _graph != null else 0


func graph_size() -> Vector2:
	return _graph.size if _graph != null else Vector2.ZERO


func selected_step() -> String:
	return _selected


func select_step(step_id: String) -> void:
	if _graph != null:
		_graph.select(step_id)
	_on_step_selected(step_id)


func evidence_text() -> String:
	var parts := PackedStringArray()
	for child in _detail.get_children():
		_collect_text(child, parts)
	return "\n".join(parts)


func _collect_text(node: Node, parts: PackedStringArray) -> void:
	if node is Label:
		parts.append(str((node as Label).text))
	for child in node.get_children():
		_collect_text(child, parts)


func outputs_panel() -> ResultsPanel:
	for child in _outputs_holder.get_children():
		if child is ResultsPanel:
			return child
	return null


func switch_tab(index: int) -> void:
	_tabs.current_tab = index



class PecanStepGraph extends Control:
	## Protocol steps as clickable nodes, drawn in the same visual language as the
	## existing process canvas (grid, straight connectors, dark cards).

	signal step_selected(step_id: String)

	const NODE_W := 250.0
	const NODE_H := 96.0
	const LANE_STEP := 296.0
	const ROW_STEP := 118.0
	const PAD_X := 14.0
	const PAD_TOP := 56.0
	const LANE_TITLES := ["Pecan — direct evidence", "Analogous species — hypotheses", "Method review"]
	const LANE_COLOURS := [Color(0.45, 0.83, 0.55), Color(0.96, 0.78, 0.42), Color(0.68, 0.75, 0.85)]

	var _nodes: Array = []          # {step, lane, row, rect, colour}
	var _selected := ""
	var _hover := -1
	var _rows := 1


	func set_steps(steps: Array) -> void:
		_nodes.clear()
		_selected = ""
		_hover = -1
		var lane_counts := [0, 0, 0]
		for step in steps:
			var lane := _lane_of(str(step.get("evidence_status", "")))
			var row: int = lane_counts[lane]
			lane_counts[lane] = row + 1
			var rect := Rect2(
				PAD_X + lane * LANE_STEP,
				PAD_TOP + row * ROW_STEP,
				NODE_W, NODE_H)
			_nodes.append({
				"step": step,
				"lane": lane,
				"row": row,
				"rect": rect,
				"colour": LANE_COLOURS[lane],
			})
		_rows = max(1, lane_counts[0])
		_rows = max(_rows, lane_counts[1])
		_rows = max(_rows, lane_counts[2])
		custom_minimum_size = Vector2(
			PAD_X * 2 + 3 * NODE_W + 2 * (LANE_STEP - NODE_W),
			PAD_TOP + _rows * ROW_STEP + 10)
		queue_redraw()


	func edge_count() -> int:
		var count := 0
		for lane in 3:
			var in_lane := 0
			for node in _nodes:
				if int(node["lane"]) == lane:
					in_lane += 1
			if in_lane > 1:
				count += in_lane - 1
		return count


	func select(step_id: String) -> void:
		_selected = step_id
		queue_redraw()


	static func _lane_of(status: String) -> int:
		if status.begins_with("direct"):
			return 0
		if status.begins_with("analogous"):
			return 1
		return 2


	func _node_at(position: Vector2) -> int:
		for index in _nodes.size():
			if (_nodes[index]["rect"] as Rect2).has_point(position):
				return index
		return -1



	func _draw() -> void:
		var font := ThemeDB.fallback_font
		var grid := Color(1, 1, 1, 0.045)
		var x := 0.0
		while x < size.x:
			draw_line(Vector2(x, 0), Vector2(x, size.y), grid, 1.0)
			x += 32.0
		var y := 0.0
		while y < size.y:
			draw_line(Vector2(0, y), Vector2(size.x, y), grid, 1.0)
			y += 32.0

		for lane in 3:
			draw_string(font, Vector2(PAD_X + lane * LANE_STEP, 26.0),
				LANE_TITLES[lane], HORIZONTAL_ALIGNMENT_LEFT, NODE_W, 10,
				LANE_COLOURS[lane])

		# Protocol order inside one evidence class. There are no cross-class edges:
		# the generated model has no connections at all.
		for lane in 3:
			var lane_nodes: Array = []
			for node in _nodes:
				if int(node["lane"]) == lane:
					lane_nodes.append(node)
			for index in max(0, lane_nodes.size() - 1):
				var a: Rect2 = lane_nodes[index]["rect"]
				var b: Rect2 = lane_nodes[index + 1]["rect"]
				var start := Vector2(a.position.x + a.size.x * 0.5, a.position.y + a.size.y)
				var end := Vector2(b.position.x + b.size.x * 0.5, b.position.y)
				var mid := (start.y + end.y) * 0.5
				var lane_colour: Color = LANE_COLOURS[lane]
				var colour := Color(lane_colour.r, lane_colour.g, lane_colour.b, 0.5)
				draw_line(start, Vector2(start.x, mid), colour, 1.5)
				draw_line(Vector2(start.x, mid), Vector2(end.x, mid), colour, 1.5)
				draw_line(Vector2(end.x, mid), end, colour, 1.5)
				draw_colored_polygon(PackedVector2Array([
					end, Vector2(end.x - 4, end.y - 7), Vector2(end.x + 4, end.y - 7),
				]), colour)

		for index in _nodes.size():
			_draw_node(index, font)


	func _draw_node(index: int, font: Font) -> void:
		var node: Dictionary = _nodes[index]
		var step: Dictionary = node["step"]
		var rect: Rect2 = node["rect"]
		var colour: Color = node["colour"]
		var step_id := str(step.get("step_id", ""))
		var selected := step_id == _selected
		var hovered := index == _hover

		var style := StyleBoxFlat.new()
		style.bg_color = Color(0.14, 0.20, 0.30, 0.98) if selected else Color(0.10, 0.13, 0.18, 0.96)
		style.border_color = colour if (selected or hovered) else Color(colour.r, colour.g, colour.b, 0.55)
		style.set_border_width_all(3 if selected else 1)
		style.set_corner_radius_all(8)
		draw_style_box(style, rect)

		# Colour bar on the left identifies the evidence class at a glance.
		draw_rect(Rect2(rect.position, Vector2(5, rect.size.y)), colour, true)

		var title := "%d. %s" % [int(step.get("order", 0)), str(step.get("label", step_id))]
		draw_multiline_string(font, rect.position + Vector2(14, 20), title,
			HORIZONTAL_ALIGNMENT_LEFT, rect.size.x - 22, 10, 2, Color(0.90, 0.93, 0.98))

		var status := str(step.get("evidence_status", ""))
		var klass := "direct evidence"
		if status.begins_with("analogous"):
			klass = "analogue hypothesis"
		elif status.begins_with("method"):
			klass = "method review"
		var unknown := 0
		for parameter in step.get("parameters", []):
			if str(parameter.get("state", "")) == "unknown":
				unknown += 1
		var sub := klass
		if bool(step.get("hypothesis", false)) and not status.begins_with("analogous"):
			sub += " · hypothesis"
		if unknown > 0:
			sub += " · %d unknown" % unknown
		draw_string(font, rect.position + Vector2(14, rect.size.y - 12), sub,
			HORIZONTAL_ALIGNMENT_LEFT, rect.size.x - 22, 9,
			Color(colour.r, colour.g, colour.b, 0.95))


	func _gui_input(event: InputEvent) -> void:
		if event is InputEventMouseMotion:
			var index := _node_at(event.position)
			if index != _hover:
				_hover = index
				queue_redraw()
			return
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			var index := _node_at(event.position)
			if index >= 0:
				_selected = str(_nodes[index]["step"].get("step_id", ""))
				queue_redraw()
				step_selected.emit(_selected)
				accept_event()


	func _notification(what: int) -> void:
		if what == NOTIFICATION_MOUSE_EXIT and _hover != -1:
			_hover = -1
			queue_redraw()

