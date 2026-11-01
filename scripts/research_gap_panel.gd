class_name ResearchGapPanel
extends PanelContainer
## What is missing before this simulation could be more complete or defensible.
##
## ## This is a product feature, not a warning list
##
## Each gap answers six questions: what is missing, why it matters *here*, what it
## affects, what evidence supports the assessment, what would resolve it, and whether
## it blocks execution, limits interpretation, or prevents validation. A list of
## "warnings" answers none of those and is therefore useless to somebody deciding
## what to work on next.
##
## ## Every gap is generated from the project's own material
##
## The manifest's `assumptions`, its `unsupported_capabilities` and its
## `missing_information`; the quantity registry's required inputs; the composition
## report's connection dispositions; and the compatibility engine's refusals. Nothing
## is added from outside the ingested literature. Where this project has no evidence,
## the panel says the evidence is absent from the project's sources -- not that no
## research exists.
##
## ## Ranking is by documented dependency, not by a confidence score
##
## Gaps are ordered by what they block. A missing required input stops the run; a
## missing model component limits what the scene can honestly show; missing
## observations prevent validation but do not stop a prediction. No numeric
## "confidence" is invented for any of them.

const BLOCKS_EXECUTION := "blocks execution"
const LIMITS_INTERPRETATION := "limits interpretation"
const PREVENTS_VALIDATION := "prevents validation"
const LIMITS_SCOPE := "limits what can be simulated"

const IMPACT_COLOURS := {
	BLOCKS_EXECUTION: Color(0.95, 0.58, 0.52),
	LIMITS_INTERPRETATION: Color(0.95, 0.76, 0.45),
	PREVENTS_VALIDATION: Color(0.72, 0.68, 0.95),
	LIMITS_SCOPE: Color(0.62, 0.80, 0.95),
}

const CATEGORY_TITLES := {
	"A": "Missing model components",
	"B": "Missing parameters or initial conditions",
	"C": "Sources that cannot be connected",
	"D": "Missing experimental evidence",
	"E": "Unresolved scientific questions",
}

var _scroll: ScrollContainer
var _body: VBoxContainer
var _summary: Label
var _gaps: Array[Dictionary] = []
var _generated_from := ""


func setup() -> void:
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	add_child(vb)

	var heading := Label.new()
	heading.text = "Research gaps"
	heading.add_theme_font_size_override("font_size", 13)
	vb.add_child(heading)

	_summary = Label.new()
	_summary.text = "No model assessed yet."
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.add_theme_font_size_override("font_size", 10)
	_summary.modulate = Color(1, 1, 1, 0.62)
	vb.add_child(_summary)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(_scroll)

	_body = VBoxContainer.new()
	_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_body.add_theme_constant_override("separation", 4)
	_scroll.add_child(_body)


func clear() -> void:
	_gaps.clear()
	_generated_from = ""
	if _summary != null:
		_summary.text = "No model assessed yet."
	_clear_body()


## Rebuild the panel from the project's own material.
##
## `manifest`   -- `--describe-model` payload for the model being simulated
## `contract`   -- `--describe-contract` payload (the quantity registry)
## `report`     -- the composition report, if a run has happened
## `connections`-- `--describe-connections` payload, the compatibility authority
## `inputs`     -- the literal inputs the current graph declared
## `diagnostics`-- diagnostics from the last run, so a refused connection surfaces
func generate(manifest: Dictionary, contract: Dictionary, report: Dictionary,
		connections: Dictionary, inputs: Dictionary,
		diagnostics: Array) -> void:
	_gaps.clear()
	_generated_from = "manifest, quantity registry, composition report, " \
		+ "compatibility engine, declared inputs, run diagnostics"

	_missing_components(manifest, contract)
	_missing_parameters(manifest, contract, inputs)
	_rejected_sources(connections, manifest)
	_missing_evidence(manifest, report)
	_unresolved_questions(manifest)

	_render()


## The generated gaps, for the acceptance harness and for programmatic checks.
func gaps() -> Array:
	return _gaps


func categories_present() -> PackedStringArray:
	var found := {}
	for gap in _gaps:
		found[str(gap.get("category", ""))] = true
	var keys := found.keys()
	keys.sort()
	return PackedStringArray(keys)


func blocking_gaps() -> Array:
	return _gaps.filter(func(g): return str(g.get("impact", "")) == BLOCKS_EXECUTION)


# ------------------------------------------------------------ gap generators


func _add(category: String, title: String, missing: String, why: String,
		affects: String, evidence: String, resolves: String, impact: String) -> void:
	_gaps.append({
		"category": category,
		"category_title": str(CATEGORY_TITLES.get(category, category)),
		"title": title,
		"missing": missing,
		"why_it_matters": why,
		"affects": affects,
		"evidence": evidence,
		"what_would_resolve_it": resolves,
		"impact": impact,
	})


func _missing_components(manifest: Dictionary, contract: Dictionary) -> void:
	for key in manifest.get("unsupported_capabilities", {}) as Dictionary:
		var text := str(manifest["unsupported_capabilities"][key])
		var impact := LIMITS_SCOPE
		if key.begins_with("no_"):
			# A capability the paper's own model omits limits the process the
			# scene may claim to represent.
			impact = LIMITS_INTERPRETATION
		_add("A", key.replace("_", " "), text,
			"This model cannot compute it, so the simulation cannot show it and any "
			+ "expectation it would create is unsupported.",
			"the set of processes this simulation may claim to represent",
			"The model's own manifest declares the capability unsupported: \"%s\"."
			% text,
			"A model or extension that implements it, with the same connection to "
			+ "this one the compatibility engine permits.",
			impact)

	# A model that is present but cannot legally join this one is a missing
	# component too, and a more important kind: it is available and unusable.
	if _registry_has_no_spatial_quantity(contract):
		_add("A", "no spatial or transport model",
			"The quantity registry publishes no quantity that names a spatial "
			+ "extent, a gradient, a velocity or a concentration field.",
			"Nothing in the executed graph can resolve a concentration field, a "
			+ "gradient, gas holdup or a flow pattern, so the scene shows bulk "
			+ "scalars and must not depict spatial behaviour.",
			"every rendered quantity; it is why the liquid is drawn as one "
			+ "well-mixed body",
			"The contract's own quantity registry, which is the single source of "
			+ "truth for what this project can express. It lists no spatial "
			+ "quantity, so no registered model can publish one.",
			"A transport model with a quantity of its own that the registry "
			+ "admits, and a compatibility rule that permits the connection.",
			LIMITS_SCOPE)


## Whether the quantity registry contains anything spatial.
##
## The registry is the project's vocabulary. If no quantity in it names a spatial
## extent, a gradient, a velocity or a field, then no model in the project can
## publish one -- and the scene has to render bulk scalars and say so.
##
## The token list is a *detector*, not a rule: it is applied to the real registry,
## so adding a spatial quantity to the contract would make this return true and
## the gap would stop being claimed.
const _SPATIAL_TOKENS := [
	"spatial", "gradient", "velocity", "profile", "field", "position",
	"concentration_map", "turbulen", "eddy", "dispersion", "diffusion",
]


func _registry_has_no_spatial_quantity(contract: Dictionary) -> bool:
	var quantities: Array = contract.get("quantities", []) as Array
	if quantities.is_empty():
		return false
	for quantity in quantities:
		var name := str(quantity).to_lower()
		for token in _SPATIAL_TOKENS:
			if name.contains(token):
				return false
	return true


func _missing_parameters(manifest: Dictionary, contract: Dictionary,
		inputs: Dictionary) -> void:
	for port in manifest.get("ports", []) as Array:
		if str(port.get("direction", "")) != "input":
			continue
		if not bool(port.get("required", false)):
			continue
		var port_id := str(port.get("port_id", "?"))
		var literal := _literal_for(inputs, port_id)
		var supplied := not literal.is_empty()
		if not supplied:
			_add("B", "required input not supplied: %s" % port_id,
				"The model requires %s, and this run did not supply it."
				% str(port.get("label", port_id)),
				"Without it the equations cannot be evaluated, so the run is "
				+ "refused rather than approximated.",
				"the whole simulation: nothing downstream can run",
				"The manifest marks the port required, and the run diagnostics "
				+ "name it.",
				"A value with a source, declared as a graph input.",
				BLOCKS_EXECUTION)
			continue

		# Supplied, but is the source's own literature enough? A required input
		# the ingested paper does not establish is a category-B gap even though
		# the run succeeded. This is the most useful thing the panel can say
		# about a model whose inputs were partly inferred.
		var provenance := str(literal.get("provenance", "")).to_lower()
		if provenance == "reported":
			continue
		var source_ref := str(literal.get("source_ref", ""))
		_add("B", "%s is required and not established by the source" % port_id,
			"The model requires %s, and the ingested literature does not establish "
			% str(port.get("label", port_id))
			+ "it. The value in use is %s %s, declared as %s."
			% [str(literal.get("value", "?")), str(literal.get("unit", "")),
				provenance if provenance != "" else "unspecified"],
			"The run proceeds, but the result rests on a value the source does "
			+ "not establish, and the outcome can depend on it strongly.",
			"every quantity the model computes from %s" % port_id,
			"The input's own provenance: \"%s\"%s." % [
				source_ref if source_ref != "" else "no source reference",
				(" -- " + str(literal.get("reason", "")))
					if str(literal.get("reason", "")) != "" else ""],
			"A value the source states, or a measurement of the culture itself.",
			LIMITS_INTERPRETATION)


func _literal_for(inputs: Dictionary, port_id: String) -> Dictionary:
	for key in inputs:
		if str(key).split("/")[-1] == port_id:
			return inputs[key]
	return {}


func _rejected_sources(connections: Dictionary, manifest: Dictionary) -> void:
	var model_id := str(manifest.get("model_id", ""))
	for boundary in connections.get("boundaries", []) as Array:
		var source := str(boundary.get("source_model", ""))
		var target := str(boundary.get("target_model", ""))
		if source != model_id and target != model_id:
			continue
		if bool(boundary.get("permitted", false)):
			continue
		var evidence := boundary.get("evidence", []) as Array
		var unresolved := boundary.get("unresolved", []) as Array
		_add("C", "%s -> %s is refused" % [source, target],
			str(boundary.get("reason", "")),
			"This source is ingested into the project and describes this kind of "
			+ "process, but the compatibility engine refuses to connect it. Adding "
			+ "it anyway would make the graph execute while asserting a relationship "
			+ "no ingested source supports.",
			"any composed process; this is why the default simulation uses one model",
			"The compatibility engine's own position, with its evidence: %s"
			% ("; ".join(evidence).substr(0, 220) if not evidence.is_empty()
				else "the engine's recorded reason"),
			"A published relationship the engine can be given: %s"
			% ("; ".join(unresolved).substr(0, 200) if not unresolved.is_empty()
				else "evidence relating the two models, which the project's sources "
					+ "do not contain"),
			LIMITS_SCOPE)


func _missing_evidence(manifest: Dictionary, report: Dictionary) -> void:
	# The paper's time courses are figures. That is a validation gap and is stated
	# as such wherever the model declares it.
	for entry in manifest.get("assumptions", []) as Array:
		if str(entry.get("item_id", "")) != "PAPER_REPRODUCTION":
			continue
		_add("D", "no numerical observations to validate against",
			str(entry.get("summary", "")),
			"A simulation can be executed and still be unvalidated. Without "
			+ "measurements the model's predictions cannot be scored, and a "
			+ "successful run says nothing about accuracy.",
			"every predicted trajectory in this scene",
			"The model declares this itself: \"%s\"." % str(entry.get("summary", "")),
			"The authors' underlying numerical time courses, or an independent "
			+ "experiment measured the same way.",
			PREVENTS_VALIDATION)

	var execution := report.get("execution", {}) as Dictionary
	if execution.is_empty():
		return
	if bool(execution.get("results_invalidated", false)):
		_add("D", "previous results are invalidated",
			"The scene is showing results for a graph that has since changed.",
			"Rendering them as current would attribute them to a configuration that "
			+ "no longer exists.",
			"every quantity on screen",
			"The composition report records results_invalidated.",
			"Re-run the current configuration.",
			LIMITS_INTERPRETATION)

	for connection in report.get("connections", []) as Array:
		if str(connection.get("disposition", "")) == "permitted" \
				or str(connection.get("disposition", "")) == "permitted_conditionally":
			continue
		_add("D", "connection %s is %s" % [
			str(connection.get("connection_id", "?")),
			str(connection.get("disposition", "?"))],
			str(connection.get("disposition_explanation", "")),
			"A connection that does not hold cannot contribute to the result, and "
			+ "the graph is refused rather than partly executed.",
			"the composed process",
			"The composition report records the disposition and the diagnostic.",
			"Evidence or a corrected quantity that the compatibility engine can "
			+ "accept.",
			BLOCKS_EXECUTION)


func _unresolved_questions(manifest: Dictionary) -> void:
	for entry in manifest.get("assumptions", []) as Array:
		if str(entry.get("status", "")) != "unresolved":
			continue
		_add("E", str(entry.get("item_id", "?")),
			str(entry.get("summary", "")),
			"The source prints something that cannot be read unambiguously. The "
			+ "simulation takes a documented reading, and that reading is one of "
			+ "the things that decides the result.",
			"the growth kinetics, and every quantity derived from them",
			"The model's transcription note records the printed string and the "
			+ "reading taken.",
			"A clarification from the source, or an experiment that discriminates "
			+ "between the readings.",
			LIMITS_INTERPRETATION)

		for item in manifest.get("missing_information", []) as Array:
			if item is Dictionary:
				_add("E", str(item.get("item_id", "unresolved question")),
					str(item.get("summary", json_stringify(item))),
					"Recorded by the model as information the source does not give.",
					"anything that depends on it",
					"The model's own missing_information entry.",
					"The absent measurement, or a source that reports it.",
					LIMITS_INTERPRETATION)


func json_stringify(value: Variant) -> String:
	return JSON.stringify(value)


# ----------------------------------------------------------------- rendering


func _render() -> void:
	_clear_body()

	var blocking := blocking_gaps().size()
	_summary.text = "%d gap(s) generated from the %s. %d block execution." % [
		_gaps.size(), _generated_from, blocking]
	if blocking > 0:
		_summary.modulate = Color(0.95, 0.76, 0.45)

	if _gaps.is_empty():
		_note(null, "No gap was generated. That means the material consulted said "
			+ "nothing about limitations, which is itself worth checking -- it is "
			+ "not evidence that the simulation is complete.", Color(0.95, 0.82, 0.45))
		return

	var by_category := {}
	for gap in _gaps:
		var category := str(gap.get("category", ""))
		if not by_category.has(category):
			by_category[category] = []
		by_category[category].append(gap)

	for category in by_category.keys():
		_section(str(CATEGORY_TITLES.get(category, category)))
		for gap in by_category[category]:
			_card(gap)


func _section(title: String) -> void:
	var label := Label.new()
	label.text = "== %s ==" % title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	_body.add_child(label)


func _card(gap: Dictionary) -> void:
	var impact := str(gap.get("impact", ""))
	var colour: Color = IMPACT_COLOURS.get(impact, Color(1, 1, 1, 0.7))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(colour.r, colour.g, colour.b, 0.09)
	style.border_color = Color(colour.r, colour.g, colour.b, 0.42)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 7
	style.content_margin_right = 7
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	box.add_theme_stylebox_override("panel", style)

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	var title := Label.new()
	title.text = str(gap.get("title", "?"))
	title.add_theme_font_size_override("font_size", 11)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	var badge := Label.new()
	badge.text = impact
	badge.add_theme_font_size_override("font_size", 9)
	badge.modulate = colour
	head.add_child(badge)
	box.add_child(head)

	_field(box, "missing", str(gap.get("missing", "")))
	_field(box, "why it matters here", str(gap.get("why_it_matters", "")))
	_field(box, "affects", str(gap.get("affects", "")))
	_field(box, "evidence", str(gap.get("evidence", "")))
	_field(box, "resolved by", str(gap.get("what_would_resolve_it", "")))

	_body.add_child(box)


func _field(box: VBoxContainer, key: String, value: String) -> void:
	if value == "":
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(126, 0)
	name_label.add_theme_font_size_override("font_size", 10)
	name_label.modulate = Color(1, 1, 1, 0.5)
	row.add_child(name_label)
	var value_label := Label.new()
	value_label.text = value
	value_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	value_label.add_theme_font_size_override("font_size", 10)
	value_label.modulate = Color(1, 1, 1, 0.76)
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(value_label)
	box.add_child(row)


func _note(container: Variant, text: String, colour: Color) -> void:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	_body.add_child(label)


func _clear_body() -> void:
	if _body == null:
		return
	for child in _body.get_children():
		_body.remove_child(child)
		child.queue_free()
