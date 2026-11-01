class_name ScientificGapPanel
extends PanelContainer
## Scientific gaps in the Zielinski insulin simulation and what would close them.
##
## ## The panel holds no scientific claims of its own
##
## Every gap, paper match, classification and recommendation is read from
## `composition/composition/gaps.py` through `--describe-gaps`. The panel does
## not decide relevance, does not upgrade a compatibility class and does not
## turn a missing value into a number.
##
## ## Why it owns a runner
##
## The replay scene already runs a model and fetches cross-paper context. This
## panel asks a third, independent question, so it owns a private
## `CompositionRunner`; its request cannot consume another request's answer.
##
## ## What the screen shows
##
## A summary of the analysis, the gap list with an expandable explanation, the
## papers that touch the selected gap, and the recommendation for what to find
## next. Search terms are shown as text and can be copied to the clipboard.

signal analysis_loaded(payload: Dictionary)

const PANEL_TITLE := "Scientific Gap Discovery"
const INK := Color(0.82, 0.88, 0.96)
const MUTED := Color(1, 1, 1, 0.58)
const WARN := Color(0.95, 0.78, 0.45)
const BAD := Color(0.95, 0.62, 0.55)
const GOOD := Color(0.56, 0.82, 0.60)

var _runner: CompositionRunner = null
var _ui_ready := false
var _scroll: ScrollContainer
var _body: VBoxContainer
var _status: Label
var _summary: Label
var _summary_values: Dictionary = {}
var _analyse_button: Button
var _refresh_button: Button
var _list: VBoxContainer
var _selection_label: Label
var _lit_body: VBoxContainer
var _rec_body: VBoxContainer
var _copy_status: Label

var _payload: Dictionary = {}
var _gap_data: Dictionary = {}
var _gap_bodies: Dictionary = {}
var _gap_headers: Dictionary = {}
var _gap_titles: Dictionary = {}
var _selected_gap_id := ""


func _ready() -> void:
	_ensure_ui()


func setup(python_path: String = "", composition_dir: String = "") -> void:
	_ensure_ui()
	if _runner == null:
		_runner = CompositionRunner.new(python_path, composition_dir)
		_runner.name = "ScientificGapPanelRunner"
		add_child(_runner)
		_runner.finished.connect(_on_runner_finished)
	_status.text = "Not analysed yet. Press Analyse simulation to read the model and the paper library."
	_analyse_button.disabled = false
	_refresh_button.disabled = false


# --------------------------------------------------------------------- layout

func _ensure_ui() -> void:
	if _ui_ready:
		return
	_ui_ready = true

	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 6)
	add_child(root)

	var heading := Label.new()
	heading.text = PANEL_TITLE
	heading.add_theme_font_size_override("font_size", 14)
	root.add_child(heading)

	var intro := Label.new()
	intro.text = (
		"What the project's own model, compatibility records and paper library "
		+ "do not contain -- and the specific literature that would close each gap."
	)
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.add_theme_font_size_override("font_size", 10)
	intro.modulate = MUTED
	root.add_child(intro)

	var controls := HBoxContainer.new()
	controls.add_theme_constant_override("separation", 8)
	root.add_child(controls)
	_analyse_button = Button.new()
	_analyse_button.name = "AnalyseSimulationButton"
	_analyse_button.text = "Analyse simulation"
	_analyse_button.tooltip_text = (
		"Reads the Zielinski model's declared missing parameters, the seven "
		+ "compatibility assessments and the paper index. Executes no model."
	)
	_analyse_button.pressed.connect(request)
	controls.add_child(_analyse_button)
	_refresh_button = Button.new()
	_refresh_button.name = "RefreshAnalysisButton"
	_refresh_button.text = "Refresh analysis"
	_refresh_button.pressed.connect(request)
	controls.add_child(_refresh_button)

	_status = Label.new()
	_status.name = "GapAnalysisStatus"
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_font_size_override("font_size", 10)
	_status.modulate = MUTED
	root.add_child(_status)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(_scroll)

	_body = VBoxContainer.new()
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_theme_constant_override("separation", 6)
	_scroll.add_child(_body)

	_section(_body, "A. Simulation analysis")
	_summary = Label.new()
	_summary.name = "GapAnalysisSummary"
	_summary.text = "No analysis loaded yet."
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.add_theme_font_size_override("font_size", 10)
	_summary.modulate = INK
	_body.add_child(_summary)

	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 2)
	_body.add_child(grid)
	for key in [
		"target", "gaps", "fully_addressed", "partially_addressed",
		"unresolved", "composition_enabling", "papers_assessed",
	]:
		_add_summary_row(grid, key)

	_section(_body, "B. Knowledge gaps")
	var hint := Label.new()
	hint.text = "Select a gap to inspect its variables, evidence and missing information."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_font_size_override("font_size", 10)
	hint.modulate = MUTED
	_body.add_child(hint)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 4)
	_body.add_child(_list)

	_section(_body, "C. Existing literature matches")
	_selection_label = Label.new()
	_selection_label.text = "No gap selected."
	_selection_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_selection_label.add_theme_font_size_override("font_size", 10)
	_selection_label.modulate = MUTED
	_body.add_child(_selection_label)
	_lit_body = VBoxContainer.new()
	_lit_body.add_theme_constant_override("separation", 5)
	_body.add_child(_lit_body)

	_section(_body, "D. Research recommendation")
	_rec_body = VBoxContainer.new()
	_rec_body.add_theme_constant_override("separation", 5)
	_body.add_child(_rec_body)

	_section(_body, "E. Refresh analysis")
	var refresh := Button.new()
	refresh.name = "RefreshAnalysisButtonBottom"
	refresh.text = "Refresh analysis"
	refresh.tooltip_text = "Regenerate the analysis from the current model catalogue and compatibility records."
	refresh.pressed.connect(request)
	_body.add_child(refresh)
	_copy_status = Label.new()
	_copy_status.name = "GapCopyStatus"
	_copy_status.text = ""
	_copy_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_copy_status.add_theme_font_size_override("font_size", 10)
	_copy_status.modulate = MUTED
	_body.add_child(_copy_status)


func _section(parent: VBoxContainer, title: String) -> void:
	var label := Label.new()
	label.text = title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	parent.add_child(label)


func _add_summary_row(grid: GridContainer, key: String) -> void:
	var name_label := Label.new()
	name_label.text = {
		"target": "Target simulation",
		"gaps": "Gaps identified",
		"fully_addressed": "Fully resolved by existing library",
		"partially_addressed": "Partly informed by existing papers",
		"unresolved": "Still unresolved",
		"composition_enabling": "Potentially composition-enabling",
		"papers_assessed": "Existing papers assessed",
	}.get(key, key)
	name_label.add_theme_font_size_override("font_size", 10)
	name_label.modulate = MUTED
	grid.add_child(name_label)
	var value := Label.new()
	value.name = "SummaryValue_%s" % key
	value.text = "-"
	value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value.add_theme_font_size_override("font_size", 10)
	value.modulate = INK
	value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(value)
	_summary_values[key] = value


# --------------------------------------------------------------------- request

func request() -> void:
	_ensure_ui()
	if _runner == null:
		_status.text = "No Python runner is attached to this panel."
		return
	_status.text = "Analysing the model, compatibility records and paper library..."
	_cancel_analysis_buttons()
	_runner.describe_scientific_gaps()


func _cancel_analysis_buttons() -> void:
	_analyse_button.disabled = true
	_refresh_button.disabled = true


func _on_runner_finished(payload: Dictionary) -> void:
	_analyse_button.disabled = false
	_refresh_button.disabled = false
	if payload.has("gaps"):
		set_payload(payload)
		_status.text = (
			"Analysis loaded from the local Python runner. Digest %s."
			% str(payload.get("analysis_digest", "")).substr(0, 12)
		)
		return
	var detail := str(payload.get("error", ""))
	if detail == "":
		detail = "The runner answered with a document this panel does not recognise."
	_status.text = (
		"Scientific gap analysis is unavailable. " + detail
		+ " The panel never treats a missing analysis as 'no gaps exist'."
	)


func set_payload(payload: Dictionary) -> void:
	_ensure_ui()
	_payload = payload
	_gap_data.clear()
	_gap_bodies.clear()
	_gap_headers.clear()
	_gap_titles.clear()
	_selected_gap_id = ""
	_clear_children(_list)
	_clear_children(_lit_body)
	_clear_children(_rec_body)
	if payload.is_empty():
		_summary.text = "The scientific gap analysis could not be read."
		_selection_label.text = "No gap selected."
		return
	_render_summary()
	_render_gaps()
	var gaps: Array = payload.get("gaps", [])
	if gaps.is_empty():
		var empty := Label.new()
		empty.text = "The analysis returned no gaps. That is reported as a fact, not as evidence that the simulation is complete."
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty.add_theme_font_size_override("font_size", 10)
		empty.modulate = WARN
		_list.add_child(empty)
		_selection_label.text = "No gap selected."
	else:
		select_gap(str((gaps[0] as Dictionary).get("gap_id", "")))
	_analyse_button.disabled = false
	_refresh_button.disabled = false
	analysis_loaded.emit(payload)


# --------------------------------------------------------------------- summary

func _render_summary() -> void:
	var summary: Dictionary = _payload.get("summary", {})
	var target: Dictionary = _payload.get("target", {})
	_set_summary("target", "%s -- %s@%s" % [
		str(target.get("paper", "?")),
		str(target.get("model_id", "?")),
		str(target.get("model_version", "?")),
	])
	_set_summary("gaps", str(int(summary.get("gaps", 0))))
	_set_summary("fully_addressed", str(int(summary.get("fully_addressed", 0))))
	_set_summary("partially_addressed", str(int(summary.get("partially_addressed", 0))))
	_set_summary("unresolved", str(int(summary.get("unresolved", 0))))
	_set_summary("composition_enabling", str(int(summary.get("composition_enabling", 0))))
	_set_summary("papers_assessed", str(int(summary.get("papers_assessed", 0))))
	_summary.text = (
		"%d gap(s) identified. %d are fully resolved by the existing library, "
		+ "%d are partly informed by an existing paper, and %d remain unresolved. "
		+ "%d could enable a legitimate composition; %d would improve validation. "
		+ "No classification below was upgraded because a paper is relevant."
	) % [
		int(summary.get("gaps", 0)),
		int(summary.get("fully_addressed", 0)),
		int(summary.get("partially_addressed", 0)),
		int(summary.get("unresolved", 0)),
		int(summary.get("composition_enabling", 0)),
		int(summary.get("validation_improving", 0)),
	]


func _set_summary(key: String, text: String) -> void:
	var label: Label = _summary_values.get(key)
	if label != null:
		label.text = text


# ------------------------------------------------------------------------ gaps

func _render_gaps() -> void:
	var gaps: Array = _payload.get("gaps", [])
	for value in gaps:
		if value is Dictionary:
			_add_gap(value)


func _add_gap(gap: Dictionary) -> void:
	var gap_id := str(gap.get("gap_id", ""))
	_gap_data[gap_id] = gap

	var card := VBoxContainer.new()
	card.add_theme_constant_override("separation", 1)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	card.add_child(head)

	var header := Button.new()
	header.name = "GapHeader_%s" % gap_id
	header.alignment = HORIZONTAL_ALIGNMENT_LEFT
	header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_theme_font_size_override("font_size", 10)
	var base := "%s  %s" % [gap_id, str(gap.get("title", "?"))]
	_gap_titles[gap_id] = base
	header.text = "[+] " + base
	header.tooltip_text = str(gap.get("why_it_matters", ""))
	header.pressed.connect(_on_gap_pressed.bind(gap_id))
	head.add_child(header)
	_gap_headers[gap_id] = header

	var badge := Label.new()
	badge.text = _status_text(str(gap.get("status", "")))
	badge.add_theme_font_size_override("font_size", 9)
	badge.modulate = _status_colour(str(gap.get("status", "")))
	head.add_child(badge)

	var body := VBoxContainer.new()
	body.visible = false
	body.add_theme_constant_override("separation", 1)
	card.add_child(body)
	_gap_bodies[gap_id] = body

	_field(body, "Category", str(gap.get("category_title", gap.get("category", ""))))
	_field(body, "Explanation", str(gap.get("description", "")))
	_field(body, "Why it matters here", str(gap.get("why_it_matters", "")))
	_field(body, "Relevant variables", _join(gap.get("variables", [])))
	_field(body, "Existing evidence", _format_evidence(gap.get("existing_evidence", [])))
	_field(body, "Missing information", _bullet(gap.get("missing_evidence", [])), WARN)
	if gap.get("prior_investigation") != null:
		_field(body, "Prior literature search", _format_prior(gap["prior_investigation"]), MUTED)
	_list.add_child(card)


func _on_gap_pressed(gap_id: String) -> void:
	var body: VBoxContainer = _gap_bodies.get(gap_id)
	if body != null and body.visible and _selected_gap_id == gap_id:
		body.visible = false
		var header: Button = _gap_headers.get(gap_id)
		if header != null:
			header.text = "[+] " + str(_gap_titles.get(gap_id, ""))
		return
	select_gap(gap_id)


func select_gap(gap_id: String) -> void:
	if not _gap_data.has(gap_id):
		return
	_selected_gap_id = gap_id
	for key in _gap_bodies.keys():
		var body: VBoxContainer = _gap_bodies[key]
		body.visible = (str(key) == gap_id)
		var header: Button = _gap_headers[key]
		if header != null:
			header.text = ("[-] " if str(key) == gap_id else "[+] ") + str(_gap_titles.get(key, ""))
	_render_selected()


func _render_selected() -> void:
	_clear_children(_lit_body)
	_clear_children(_rec_body)
	_selection_label.text = "No gap selected."
	_copy_status.text = ""
	if not _gap_data.has(_selected_gap_id):
		return
	var gap: Dictionary = _gap_data[_selected_gap_id]
	_selection_label.text = "%s -- %s" % [
		str(gap.get("gap_id", "")),
		str(gap.get("title", "")),
	]
	_render_literature(gap)
	_render_recommendation(gap)


# --------------------------------------------------------------- literature

func _render_literature(gap: Dictionary) -> void:
	var papers: Array = gap.get("papers", [])
	if papers.is_empty():
		_paragraph(_lit_body, "No paper in the assessed library touches this gap.", MUTED)
		return
	for value in papers:
		if not value is Dictionary:
			continue
		var paper: Dictionary = value
		var card := VBoxContainer.new()
		card.add_theme_constant_override("separation", 1)
		var title := Label.new()
		title.text = str(paper.get("citation", paper.get("display_name", "?")))
		title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		title.add_theme_font_size_override("font_size", 10)
		title.modulate = INK
		card.add_child(title)

		var meta := HBoxContainer.new()
		meta.add_theme_constant_override("separation", 10)
		var relation := Label.new()
		relation.text = _relation_text(str(paper.get("relation", "")))
		relation.add_theme_font_size_override("font_size", 9)
		relation.modulate = WARN if str(paper.get("relation", "")) == "partially_addresses" else MUTED
		meta.add_child(relation)
		var classification := Label.new()
		classification.text = "%d -- %s" % [
			int(paper.get("classification_number", 0)),
			str(paper.get("classification_label", paper.get("classification", ""))),
		]
		classification.add_theme_font_size_override("font_size", 9)
		classification.modulate = _classification_colour(int(paper.get("classification_number", 0)))
		meta.add_child(classification)
		card.add_child(meta)

		_field(card, "Relevance", str(paper.get("relevance", "")))
		_field(card, "Contributes", str(paper.get("what_information_it_contributes", "")))
		_field(card, "Remains missing", str(paper.get("what_remains_missing", "")), WARN)
		_field(card, "Suitable?", str(paper.get("suitability", "")), MUTED)
		_lit_body.add_child(card)


func _relation_text(relation: String) -> String:
	match relation:
		"partially_addresses":
			return "partly addresses this gap"
		"relevant_context":
			return "relevant context, not evidence"
		"defines_gap":
			return "baseline: defines the gap"
		"addresses":
			return "addresses this gap"
	return relation


# ------------------------------------------------------------- recommendation

func _render_recommendation(gap: Dictionary) -> void:
	var recommendation: Dictionary = gap.get("recommendation", {})
	if recommendation.is_empty():
		_paragraph(
			_rec_body,
			"No recommendation is needed: the analysis records this gap as fully addressed.",
			GOOD,
		)
		return
	_field(_rec_body, "What is needed", _bullet(recommendation.get("what_information_is_needed", [])))
	_field(_rec_body, "Why it is needed", str(recommendation.get("why_it_is_needed", "")))
	_field(_rec_body, "A suitable paper must report", _bullet(recommendation.get("suitable_paper_must_report", [])))
	_field(_rec_body, "Suggested search terms", _terms_text(gap.get("search_terms", [])))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var copy := Button.new()
	copy.name = "CopySearchTermsButton"
	copy.text = "Copy search terms"
	copy.pressed.connect(_on_copy_pressed)
	row.add_child(copy)
	_rec_body.add_child(row)
	_field(_rec_body, "ScaleUp next", str(recommendation.get("what_scaleup_can_do", "")))


func _on_copy_pressed() -> void:
	var terms := search_terms_for_selected()
	if terms.is_empty():
		_copy_status.text = "There are no search terms to copy for this gap."
		return
	DisplayServer.clipboard_set(_terms_text(terms))
	_copy_status.text = "Copied %d search term(s) to the clipboard." % terms.size()


# ------------------------------------------------------------------ formatting

func _field(parent: VBoxContainer, key: String, value: String,
		colour: Color = INK) -> void:
	if value.strip_edges() == "":
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(132, 0)
	name_label.add_theme_font_size_override("font_size", 9)
	name_label.modulate = MUTED
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value_label.add_theme_font_size_override("font_size", 10)
	value_label.modulate = colour
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	parent.add_child(row)


func _paragraph(parent: VBoxContainer, text: String, colour: Color = INK) -> void:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	parent.add_child(label)


func _join(values: Variant) -> String:
	var parts := PackedStringArray()
	if values is Array:
		for value in values:
			parts.append(str(value))
	return ", ".join(parts)


func _bullet(values: Variant) -> String:
	var parts := PackedStringArray()
	if values is Array:
		for value in values:
			parts.append("- " + str(value))
	return "\n".join(parts)


func _terms_text(values: Variant) -> String:
	var parts := PackedStringArray()
	if values is Array:
		for value in values:
			parts.append(str(value))
	elif values is PackedStringArray:
		parts = values
	return "\n".join(parts)


func _format_evidence(values: Variant) -> String:
	var parts := PackedStringArray()
	if values is Array:
		for value in values:
			if value is Dictionary:
				var entry: Dictionary = value
				parts.append("%s\n  [%s] %s" % [
					str(entry.get("statement", "")),
					str(entry.get("source", "")),
					str(entry.get("location", "")),
				])
			else:
				parts.append(str(value))
	return "\n".join(parts)


func _format_prior(value: Variant) -> String:
	if not value is Dictionary:
		return ""
	var info: Dictionary = value
	var parts := PackedStringArray()
	parts.append("%s (%s), %d candidate(s) examined." % [
		str(info.get("label", "")),
		str(info.get("port_id", "")),
		int(info.get("candidate_count", 0)),
	])
	var findings: Array = info.get("findings", [])
	for finding in findings:
		if finding is Dictionary:
			parts.append("%s -- %s [%s]" % [
				str(finding.get("finding_id", "")),
				str(finding.get("citation", "")),
				str(finding.get("verdict", "")),
			])
	var missing: Array = info.get("missing_information_required", [])
	if not missing.is_empty():
		parts.append("Still needed: " + _bullet(missing))
	return "\n".join(parts)


func _status_text(status: String) -> String:
	match status:
		"addressed":
			return "resolved"
		"partially_addressed":
			return "partly informed"
		_:
			return "unresolved"


func _status_colour(status: String) -> Color:
	match status:
		"addressed":
			return GOOD
		"partially_addressed":
			return WARN
		_:
			return MUTED


func _classification_colour(number: int) -> Color:
	match number:
		1:
			return GOOD
		2:
			return Color(0.60, 0.80, 0.86)
		3:
			return WARN
		4:
			return BAD
	return MUTED


func _clear_children(parent: Node) -> void:
	if parent == null:
		return
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()


# ------------------------------------------------------------------ harness API

func payload() -> Dictionary:
	return _payload


func gap_count() -> int:
	return _gap_data.size()


func gap_rows() -> Array:
	return _gap_data.keys()


func selected_gap() -> Dictionary:
	var gap: Dictionary = _gap_data.get(_selected_gap_id, {})
	return gap


func paper_rows_for_selected() -> Array:
	var gap := selected_gap()
	var papers: Array = gap.get("papers", [])
	return papers


func recommendation_for_selected() -> Dictionary:
	var gap := selected_gap()
	var recommendation: Dictionary = gap.get("recommendation", {})
	return recommendation


func search_terms_for_selected() -> PackedStringArray:
	var terms := PackedStringArray()
	var gap := selected_gap()
	var values: Array = gap.get("search_terms", [])
	for value in values:
		terms.append(str(value))
	return terms


func copy_search_terms() -> String:
	var terms := search_terms_for_selected()
	var text := _terms_text(terms)
	if text != "":
		DisplayServer.clipboard_set(text)
		_copy_status.text = "Copied %d search term(s) to the clipboard." % terms.size()
	return text


func summary_text() -> String:
	return _summary.text if _summary != null else ""


func summary_value(key: String) -> String:
	var label: Label = _summary_values.get(key)
	return label.text if label != null else ""
