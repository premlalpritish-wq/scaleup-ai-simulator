extends Control
## Research → evidence → model → simulation, driven by the Python workflow.
##
## ## What this screen is, and what it is not
##
## It is a *reader*. The scientific work -- problem ingestion, local literature
## discovery and acquisition, quote-verified scientific encoding, construction of
## the evidence-constrained model, and execution of that model through the real
## composition engine -- happens in `composition.workflow`. This scene builds one
## argv, hands it to `CompositionRunner.run_research_workflow`, and renders the
## document the runner wrote. It computes no claim, infers no number and fills no
## missing value; when the document is missing or malformed it says so.
##
## ## Why every panel reads from the artifacts
##
## The workflow writes one artifact per stage (`problem_spec.json`,
## `literature_manifest.json`, `research_encoded.json`, `model_spec.json`,
## `composition_graph.json`, `simulation_result.json`, `workflow_result.json`).
## The screen shows the run's own record so a reader can open the same files and
## check the screen against them. The literature manifest, which carries the
## discovery reasons and acquisition hashes, is read from the artifact path the
## payload names -- not re-derived here.
##
## ## What the screen must keep visible
##
## Direct target-organism evidence and evidence transferred from analogous species
## are shown as separate, differently coloured findings. Unknown parameters are
## listed, never hidden behind a default. An absent yield or RIN is shown as
## absent, not as zero, and the readiness block states that the model is an audit,
## not a yield model.

const PANEL_TITLE := "Research to simulation"
const FIXTURE_DIR := "res://composition/composition/workflow/fixtures"
const DEFAULT_PROBLEM := (
	"res://composition/composition/workflow/fixtures/pecan/problem.json"
)
const RUN_DIR := "user://research_workflow_runs"
const INK := Color(0.84, 0.89, 0.97)
const MUTED := Color(1, 1, 1, 0.58)
const WARN := Color(0.95, 0.78, 0.45)
const BAD := Color(0.95, 0.62, 0.55)
const GOOD := Color(0.56, 0.82, 0.60)

var _runner: CompositionRunner
var _problem_path: LineEdit
var _examples: OptionButton
var _run: Button
var _status: Label
var _artifact_dir: Label
var _problem_body: VBoxContainer
var _result_body: VBoxContainer
var _payload: Dictionary = {}
var _running := false
var _examples_by_path: Array[String] = []


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

	_runner = CompositionRunner.new("python", _detect_composition_dir())
	_runner.name = "ResearchWorkflowRunner"
	add_child(_runner)
	_runner.finished.connect(_on_runner_finished)
	_set_buttons(true)
	_status.text = (
		"No workflow has run in this session. Choose a problem document and "
		+ "press Run workflow; nothing is shown until the runner writes a result."
	)


func _detect_composition_dir() -> String:
	var root := ProjectSettings.globalize_path("res://")
	for candidate in [root.path_join("composition"), root]:
		var dir := DirAccess.open(candidate)
		if dir != null and dir.file_exists("composition/runner.py"):
			return candidate
	return ""


func _header() -> Control:
	var box := PanelContainer.new()
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	box.add_child(row)
	var title := Label.new()
	title.text = PANEL_TITLE
	title.add_theme_font_size_override("font_size", 16)
	row.add_child(title)
	var subtitle := Label.new()
	subtitle.text = (
		"problem → literature → verified claims → evidence-constrained model → runner"
	)
	subtitle.add_theme_font_size_override("font_size", 11)
	subtitle.modulate = MUTED
	row.add_child(subtitle)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	var back := Button.new()
	back.name = "BackButton"
	back.text = "Back to workshop"
	back.pressed.connect(func() -> void: get_tree().change_scene_to_file.call_deferred("res://scenes/workshop.tscn"))
	row.add_child(back)
	return box



func _left_column() -> Control:
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(520, 0)
	column.add_theme_constant_override("separation", 4)

	_section(column, "A. Problem document")
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	column.add_child(row)
	_examples = OptionButton.new()
	_examples.name = "ProblemDocuments"
	_examples.custom_minimum_size = Vector2(190, 0)
	_examples.item_selected.connect(_on_example_selected)
	row.add_child(_examples)
	_problem_path = LineEdit.new()
	_problem_path.name = "ProblemPath"
	_problem_path.text = DEFAULT_PROBLEM
	_problem_path.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_problem_path.placeholder_text = "path to a problem document (*.json)"
	row.add_child(_problem_path)

	_run = Button.new()
	_run.name = "RunWorkflowButton"
	_run.text = "Run workflow"
	_run.tooltip_text = (
		"Runs the Python research workflow for this problem document: local "
		+ "literature discovery, quote-verified encoding, model construction and "
		+ "execution through the existing composition runner."
	)
	_run.pressed.connect(_on_run_pressed)
	column.add_child(_run)

	_status = Label.new()
	_status.name = "WorkflowStatus"
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_font_size_override("font_size", 10)
	column.add_child(_status)

	_artifact_dir = Label.new()
	_artifact_dir.name = "ArtifactDirectory"
	_artifact_dir.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_artifact_dir.add_theme_font_size_override("font_size", 9)
	_artifact_dir.modulate = MUTED
	column.add_child(_artifact_dir)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	_problem_body = VBoxContainer.new()
	_problem_body.name = "ProblemSpecification"
	_problem_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_problem_body.add_theme_constant_override("separation", 2)
	scroll.add_child(_problem_body)
	_populate_examples()
	return column


func _right_column() -> Control:
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_result_body = VBoxContainer.new()
	_result_body.name = "WorkflowResult"
	_result_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_result_body.add_theme_constant_override("separation", 6)
	scroll.add_child(_result_body)
	return scroll


func _section(parent: VBoxContainer, title: String, note: String = "") -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	parent.add_child(box)
	var label := Label.new()
	label.text = title
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.70, 0.79, 0.95)
	box.add_child(label)
	if note != "":
		_paragraph(box, note, MUTED)
	return box



# --------------------------------------------------------------------- actions


func _populate_examples() -> void:
	var dir := DirAccess.open(FIXTURE_DIR)
	_examples.clear()
	_examples_by_path.clear()
	if dir == null:
		return
	for name in dir.get_directories():
		var path := FIXTURE_DIR.path_join(name).path_join("problem.json")
		if not FileAccess.file_exists(path):
			continue
		_examples_by_path.append(path)
		_examples.add_item(name)
		_examples.set_item_metadata(_examples_by_path.size() - 1, path)
	var default_index := _examples_by_path.find(DEFAULT_PROBLEM)
	if default_index >= 0:
		_examples.select(default_index)


func _on_example_selected(index: int) -> void:
	var path := str(_examples.get_item_metadata(index))
	if path != "":
		_problem_path.text = path
		_status.text = "Problem document selected. Press Run workflow to execute it."


func _set_buttons(enabled: bool) -> void:
	_run.disabled = not enabled
	_examples.disabled = not enabled
	_problem_path.editable = enabled


func _on_run_pressed() -> void:
	if _running:
		return
	var problem := _problem_path.text.strip_edges()
	if problem == "":
		_status.text = "Name a problem document first. An empty path is not a request."
		return
	var slug := problem.get_file().get_basename()
	if slug == "problem":
		slug = problem.get_base_dir().get_file()
	slug = slug.replace(" ", "_")
	var stamp := Time.get_datetime_string_from_system().replace(":", "").replace("-", "")
	stamp = stamp.replace("T", "-")
	var out_dir := RUN_DIR.path_join("%s-%s" % [slug, stamp])
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out_dir))
	var result_path := out_dir.path_join("workflow_result.json")

	_payload = {}
	_clear(_problem_body)
	_clear(_result_body)
	_running = true
	_set_buttons(false)
	_status.modulate = MUTED
	_status.text = "Running the research workflow for %s ..." % problem
	_artifact_dir.text = "artifacts: %s" % ProjectSettings.globalize_path(out_dir)
	_runner.run_research_workflow(problem, out_dir, result_path)


func _on_runner_finished(payload: Dictionary) -> void:
	_running = false
	_set_buttons(true)
	if payload.is_empty():
		_status.modulate = BAD
		_status.text = (
			"The workflow runner returned no readable document. No finding was "
			+ "substituted for it."
		)
		return
	_payload = payload
	var status := str(payload.get("status", "unknown"))
	_status.modulate = _severity_colour(status)
	_status.text = "%s — %s" % [status, CompositionRunner.status_summary(payload)]
	_render(payload)


# --------------------------------------------------------------------- render


func _render(payload: Dictionary) -> void:
	_clear(_problem_body)
	_clear(_result_body)
	_render_problem(payload.get("problem", {}))
	_render_acquisition(payload)
	_render_sources(payload)
	_render_verification(payload)
	_render_evidence_split(payload)
	_render_readiness(payload)
	_render_unknowns(payload)
	_render_assumptions(payload)
	_render_execution(payload)
	_render_outputs(payload)
	_render_diagnostics(payload)
	_render_artifacts(payload)


func _render_problem(problem: Dictionary) -> void:
	var box := _section(_problem_body, "Problem specification")
	if problem.is_empty():
		_paragraph(box, "The result document carries no problem specification.", BAD)
		return
	_field(box, "problem id", str(problem.get("problem_id", "")))
	_paragraph(box, str(problem.get("question", "")), INK)
	_tracked(box, "organism", problem.get("organism", {}))
	_tracked(box, "tissue", problem.get("tissue", {}))
	_tracked(box, "molecule", problem.get("molecule", {}))
	_field(box, "downstream", _join_list(problem.get("downstream", [])))
	_field(box, "constraints", _join_list(problem.get("constraints", [])))
	_field(box, "requested outputs", _join_list(problem.get("requested_outputs", [])))
	if bool(problem.get("blocked", false)):
		_paragraph(
			box,
			"The problem is blocked: a required field was absent, so no search or "
			+ "model was attempted.",
			BAD,
		)
	_field(box, "extraction", str(problem.get("extraction_method", "")))


func _tracked(parent: VBoxContainer, key: String, value: Variant) -> void:
	if not value is Dictionary:
		return
	var item: Dictionary = value
	var state := str(item.get("state", ""))
	var text := "not stated"
	if state != "unknown":
		text = str(item.get("value", ""))
		text += " (%s)" % state
	if str(item.get("basis", "")) != "":
		text += " — %s" % str(item.get("basis"))
	_field(parent, key, text, MUTED if state == "unknown" else INK)



func _render_acquisition(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"1. Research acquisition",
		"Which papers the local corpus offered, why each was selected, and whether "
		+ "its bytes were actually acquired. A search hit is not evidence.",
	)
	var manifest := _artifact(payload, "literature_manifest")
	if manifest.is_empty():
		_paragraph(
			box,
			"The literature manifest artifact could not be read, so selection "
			+ "reasons are not shown. The acquisition status below comes from the "
			+ "result document itself.",
			WARN,
		)
	else:
		_field(box, "corpus", str(manifest.get("corpus", "")))
		_field(box, "statement", str(manifest.get("statement", "")), MUTED)
		_field(box, "target sources", _join_list(manifest.get("target_source_ids", [])))
		_field(box, "selected", _join_list(manifest.get("selected_source_ids", [])))
		var discovery: Array = manifest.get("discovery", [])
		for item in discovery:
			if not item is Dictionary:
				continue
			var selected := bool(item.get("selected", false))
			var verdict := "selected" if selected else "not selected"
			_paragraph(
				box,
				"%s — %s (%s, %s) score %s. %s" % [
					str(item.get("source_id", "")),
					verdict,
					str(item.get("role", "")),
					str(item.get("year", "")),
					str(item.get("score", "")),
					", ".join(PackedStringArray(item.get("reasons", []))),
				],
				GOOD if selected else MUTED,
			)
	var sources: Array = payload.get("sources", [])
	var acquired := 0
	var failed := 0
	for source in sources:
		if not source is Dictionary:
			continue
		if str(source.get("acquisition_status", "")) == "acquired":
			acquired += 1
		else:
			failed += 1
	_field(box, "acquired", "%d of %d selected source(s)" % [acquired, acquired + failed],
		GOOD if failed == 0 and acquired > 0 else WARN)


func _render_sources(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"2. Source documents",
		"Every acquired document with the role the corpus declares for it and the "
		+ "SHA-256 of the exact bytes that were read.",
	)
	var sources: Array = payload.get("sources", [])
	if sources.is_empty():
		_paragraph(box, "No source document was acquired.", BAD)
		return
	for source in sources:
		if not source is Dictionary:
			continue
		var role := str(source.get("role", ""))
		_paragraph(
			box,
			"%s — %s — %s — %s" % [
				str(source.get("source_id", "")),
				role,
				str(source.get("year", "")),
				str(source.get("doi", "")),
			],
			_role_colour(role),
		)
		_paragraph(box, str(source.get("title", "")), MUTED)
		var digest := str(source.get("content_sha256", ""))
		_field(box, "acquisition", str(source.get("acquisition_status", "")))
		_field(box, "extraction", str(source.get("extraction_method", "")))
		_field(box, "sections", str(source.get("section_count", "")))
		_field(box, "sha256", digest.substr(0, 16) + ("…" if digest.length() > 16 else ""))
		_field(box, "text", str(source.get("text_path", "")))
		for diagnostic in source.get("diagnostics", []):
			_paragraph(box, str(diagnostic), WARN)


func _render_verification(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"3. Evidence verification",
		"Each claim must be found verbatim in the acquired text, and each number "
		+ "must appear in its own quote. An analogue or review source can never be "
		+ "relabelled as direct target-organism evidence.",
	)
	var encoded: Dictionary = payload.get("encoded", {}) if payload.get("encoded") is Dictionary else {}
	var verification: Dictionary = encoded.get("verification", {})
	if verification.is_empty():
		_paragraph(box, "The result document carries no verification block.", BAD)
		return
	_field(box, "quotes verified", "%s of %s" % [
		str(verification.get("quotes_verified", "?")),
		str(verification.get("quotes_checked", "?")),
	], GOOD)
	_field(box, "numbers verified", "%s of %s" % [
		str(verification.get("numeric_values_verified", "?")),
		str(verification.get("numeric_values_checked", "?")),
	], GOOD)
	_field(box, "claims", str(verification.get("claim_count", "?")))
	_field(box, "sources cited", str(verification.get("source_count", "?")))
	_field(box, "source role ceiling", str(verification.get("source_role_check", "not recorded")))
	_field(box, "method", str(verification.get("method", "")), MUTED)
	var failures: Array = verification.get("failures", [])
	_field(box, "failures", str(failures.size()), GOOD if failures.is_empty() else BAD)
	for failure in failures:
		_paragraph(box, str(failure), BAD)



func _render_evidence_split(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"4. Direct versus analogous evidence",
		"Direct evidence is about the requested organism. Analogous evidence comes "
		+ "from a different species and enters the model only as a hypothesis.",
	)
	var model := _model(payload)
	var readiness: Dictionary = model.get("readiness", {})
	if readiness.is_empty():
		_paragraph(box, "The result document carries no readiness block.", BAD)
		return
	_field(box, "direct target claims", str(readiness.get("direct_target_claim_count", "?")), GOOD)
	_field(box, "analogue claims", str(readiness.get("analogue_claim_count", "?")), WARN)
	_field(box, "method-review claims", str(readiness.get("method_review_claim_count", "?")), MUTED)
	_field(box, "direct target steps", str(readiness.get("direct_target_step_count", "?")))
	_field(box, "analogue steps", str(readiness.get("analogue_step_count", "?")))
	_field(box, "method-review steps", str(readiness.get("method_review_step_count", "?")))
	for step in model.get("steps", []):
		if not step is Dictionary:
			continue
		var status := str(step.get("evidence_status", ""))
		var hypothesis := bool(step.get("hypothesis", false))
		_paragraph(
			box,
			"%s — %s — %d parameter(s), %d unknown — %s%s" % [
				str(step.get("step_id", "")),
				status,
				int(step.get("parameters", []).size()),
				int(step.get("unknowns", []).size()),
				_join_list(step.get("source_ids", [])),
				"  [hypothesis, not a measurement on the target]" if hypothesis else "",
			],
			_step_colour(status),
		)


func _render_readiness(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"5. Model readiness",
		"A complete target protocol, a quantitative yield and an available analogue "
		+ "protocol are three different findings and are never merged.",
	)
	var readiness: Dictionary = _model(payload).get("readiness", {})
	if readiness.is_empty():
		_paragraph(box, "The result document carries no readiness block.", BAD)
		return
	_flag(box, "protocol complete for target", readiness.get("protocol_complete_for_target"))
	_flag(box, "quantitative yield for target", readiness.get("quantitative_yield_available_for_target"))
	_flag(box, "analogue protocol available", readiness.get("analogue_protocol_available"))
	_field(box, "reported parameters", str(readiness.get("reported_parameter_count", "?")))
	_field(box, "unresolved parameters", str(readiness.get("unresolved_parameter_count", "?")), WARN)
	_field(box, "evidence coverage", _ratio(readiness.get("evidence_coverage_ratio")))
	if str(readiness.get("statement", "")) != "":
		_paragraph(box, str(readiness.get("statement", "")), MUTED)


func _render_unknowns(payload: Dictionary) -> void:
	var model := _model(payload)
	var unknowns: Array = model.get("unknowns", [])
	var note := (
		"%d quantity(ies) the acquired sources do not state. They were not "
		+ "imputed, defaulted or placed at zero."
	) % unknowns.size()
	var box := _section(_result_body, "6. Unknown parameters", note)
	if unknowns.is_empty():
		_paragraph(box, "No unresolved quantity was recorded.", MUTED)
		return
	for unknown in unknowns:
		_paragraph(box, "• " + str(unknown), WARN)


func _render_assumptions(payload: Dictionary) -> void:
	var model := _model(payload)
	var box := _section(_result_body, "7. Assumptions and hypotheses")
	for assumption in model.get("assumptions", []):
		_paragraph(box, "• " + str(assumption), MUTED)
	var hypotheses: Array = model.get("hypotheses", [])
	if not hypotheses.is_empty():
		_paragraph(box, "Hypotheses carried into the model (not validated on the target):", WARN)
		for hypothesis in hypotheses:
			_paragraph(box, "• " + str(hypothesis), WARN)
	var encoded: Dictionary = payload.get("encoded", {}) if payload.get("encoded") is Dictionary else {}
	for tension in encoded.get("tensions", []):
		if tension is Dictionary:
			_paragraph(box, "tension: " + str(tension.get("statement", "")), MUTED)


func _render_execution(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"8. Execution status",
		"The workflow hands one generated graph to the existing composition runner; "
		+ "the status below is the runner's, not this screen's.",
	)
	var exit_code := int(payload.get("_exit_code", -1))
	_field(box, "workflow status", str(payload.get("status", "")))
	_field(box, "workflow state", str(payload.get("workflow_status", "")))
	if exit_code >= 0:
		_field(box, "exit code", "%d — %s" % [exit_code, CompositionRunner.exit_meaning(exit_code)])
	_field(box, "errors", str(payload.get("error_count", 0)), BAD if int(payload.get("error_count", 0)) > 0 else INK)
	_field(box, "warnings", str(payload.get("warning_count", 0)), WARN if int(payload.get("warning_count", 0)) > 0 else INK)
	var execution: Dictionary = payload.get("execution", {}) if payload.get("execution") is Dictionary else {}
	if execution.is_empty():
		_paragraph(box, "No execution document was produced. Nothing was simulated.", BAD)
		return
	_field(box, "engine status", str(execution.get("status", "")))
	_field(box, "graph", str(execution.get("graph_id", "")))
	_field(box, "run id", str(execution.get("run_id", "")), MUTED)
	var results: Array = execution.get("results", [])
	var instances := PackedStringArray()
	for result in results:
		if result is Dictionary:
			instances.append("%s (%s %s, %s)" % [
				str(result.get("instance_id", "")),
				str(result.get("model_id", "")),
				str(result.get("model_version", "")),
				str(result.get("status", "")),
			])
	_field(box, "instances", ", ".join(instances))
	var graph: Dictionary = payload.get("graph", {}) if payload.get("graph") is Dictionary else {}
	_field(box, "connections", str(graph.get("connections", []).size()))



func _render_outputs(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"9. Simulation outputs",
		"Exactly what the executed model published. These are counts and ratios about "
		+ "its evidence base; no yield, RIN or degradation value is computed anywhere.",
	)
	var results: Array = payload.get("results", [])
	if results.is_empty():
		_paragraph(box, "The run published no output. Nothing is shown as zero.", WARN)
		return
	for result in results:
		if not result is Dictionary:
			continue
		for output in result.get("outputs", []):
			if not output is Dictionary:
				continue
			var ref: Dictionary = output.get("ref", {})
			var value: Dictionary = output.get("value", {})
			var text := "not available"
			if bool(value.get("is_resolved", false)) and value.get("value") != null:
				text = str(value.get("value"))
				var unit := str(value.get("unit", ""))
				if unit != "" and unit != "1":
					text += " " + unit
			_field(box, str(ref.get("port_id", "")), text)
			var method := str(value.get("method", ""))
			if method != "":
				_paragraph(box, method, MUTED)
			var source_ref := str(value.get("source_ref", ""))
			if source_ref != "":
				_paragraph(box, "source: " + source_ref, MUTED)


func _render_diagnostics(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"10. Warnings and diagnostics",
		"Every diagnostic the workflow and the composition engine raised, including "
		+ "the ones that are findings rather than failures.",
	)
	var diagnostics: Array = payload.get("diagnostics", [])
	var execution: Dictionary = payload.get("execution", {}) if payload.get("execution") is Dictionary else {}
	var execution_diagnostics: Array = execution.get("diagnostics", [])
	if diagnostics.is_empty() and execution_diagnostics.is_empty():
		_paragraph(box, "No diagnostic was recorded.", GOOD)
		return
	for diagnostic in diagnostics + execution_diagnostics:
		if not diagnostic is Dictionary:
			continue
		var severity := str(diagnostic.get("severity", "info"))
		_paragraph(
			box,
			"[%s] %s: %s" % [
				severity,
				str(diagnostic.get("code", "")),
				str(diagnostic.get("message", "")),
			],
			_severity_colour(severity),
		)
		var remediation := str(diagnostic.get("remediation", ""))
		if remediation != "":
			_paragraph(box, remediation, MUTED)


func _render_artifacts(payload: Dictionary) -> void:
	var box := _section(
		_result_body,
		"11. Artifact locations",
		"One file per stage. The screen above is rendered from these documents.",
	)
	var artifacts: Dictionary = payload.get("artifacts", {})
	if artifacts.is_empty():
		_paragraph(box, "The run wrote no artifact paths into its result document.", BAD)
	else:
		for name in artifacts:
			_field(box, str(name), str(artifacts[name]))
	var result_path := str(payload.get("_result_path", ""))
	if result_path != "":
		_field(box, "result document", result_path)
	var output := str(payload.get("_output", "")).strip_edges()
	if output != "" and str(payload.get("status", "")) != "success":
		_paragraph(box, "runner output (stdout and stderr merged):", MUTED)
		_paragraph(box, output, MUTED)



# ------------------------------------------------------------------- helpers


func _artifact(payload: Dictionary, name: String) -> Dictionary:
	var artifacts: Dictionary = payload.get("artifacts", {})
	var path := str(artifacts.get(name, ""))
	if path == "":
		return {}
	return _runner.read_result(path)


func _model(payload: Dictionary) -> Dictionary:
	return payload.get("model", {}) if payload.get("model") is Dictionary else {}


func _field(parent: VBoxContainer, key: String, value: String,
		colour: Color = INK) -> void:
	if value.strip_edges() == "":
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var name_label := Label.new()
	name_label.text = key
	name_label.custom_minimum_size = Vector2(160, 0)
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


func _flag(parent: VBoxContainer, key: String, value: Variant) -> void:
	var yes := bool(value)
	_field(parent, key, "yes" if yes else "no", INK if yes else WARN)


func _paragraph(parent: VBoxContainer, text: String, colour: Color = INK) -> void:
	if text.strip_edges() == "":
		return
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 10)
	label.modulate = colour
	parent.add_child(label)


func _join_list(value: Variant) -> String:
	if not value is Array:
		return ""
	var parts := PackedStringArray()
	for item in value:
		parts.append(str(item))
	return ", ".join(parts)


func _ratio(value: Variant) -> String:
	if value == null:
		return ""
	return "%.2f" % float(value)


func _role_colour(role: String) -> Color:
	match role:
		"target_organism":
			return GOOD
		"analogous_protocol":
			return WARN
	return MUTED


func _step_colour(status: String) -> Color:
	if status.begins_with("direct_target"):
		return GOOD
	if status.begins_with("analogous"):
		return WARN
	return MUTED


func _severity_colour(severity: String) -> Color:
	match severity:
		"success", "completed", "ok", "info":
			return GOOD
		"success_with_warnings", "warning", "warn":
			return WARN
		"error", "failed", "invalid", "blocked":
			return BAD
	return MUTED


func _clear(parent: Node) -> void:
	if parent == null:
		return
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()



# --------------------------------------------------------------- harness API
#
# Used by `composition/tests/godot/research_workflow_scene.gd`, which runs the
# real scene headlessly and checks what it displays against the result document.

func payload() -> Dictionary:
	return _payload


func problem_input() -> String:
	return _problem_path.text if _problem_path != null else ""


func set_problem_input(path: String) -> void:
	if _problem_path != null:
		_problem_path.text = path


func run_selected_problem() -> void:
	_on_run_pressed()


func is_running() -> bool:
	return _running


func runner() -> CompositionRunner:
	return _runner

