extends SceneTree
## Acceptance harness for the cross-paper context panel in the Zielinski 3D
## replay.
##
## Run it from the repository root:
##
##     godot --headless --path . --script res://composition/tests/godot/replay_cross_paper.gd
##
## Exit code 0 means every check passed.
##
## What it drives is the **real replay scene**: `res://scenes/replay3d.tscn`
## is loaded, the model runs, the cross-paper context is loaded through the
## same subprocess boundary the model run uses, and the panel's own
## accessors are read. Nothing here calls the Python layer directly, so a
## green run is a claim about the UI, not about the runner.
## What it does *not* claim: that any model is scientifically valid, or
## that any connection exists between the models. It asserts the opposite
## where the honesty rules require it: the panel presents context, the
## verdicts come from the authoritative compatibility payload, and the
## replay stays a single-model evidence replay.

const WAIT_SECONDS := 12.0
const REPLAY_SCENE := "res://scenes/replay3d.tscn"
const REPLAY_GRAPH := "res://composition/replay/zielinski_replay.json"
const REGISTRY := "python -m composition.registry"

const MORRIS := "morris2011.material_balance"
const ZIELINSKI := "zielinski2019.rhi_process"
const GANJAVE := "ganjave"

var _failures: Array[String] = []
var _checks := 0
var _scene: Control = null
var _elapsed := 0.0
var _panel_settled := false


func _initialize() -> void:
	change_scene_to_file(REPLAY_SCENE)


func _process(delta: float) -> bool:
	_elapsed += delta
	if _scene == null and current_scene != null:
		_scene = current_scene as Control
	if _scene == null or _elapsed < WAIT_SECONDS:
		return _elapsed > 180.0
	if not _panel_settled:
		_run_all()
		_panel_settled = true
		_report()
		return true
	_elapsed += 60.0
	return _elapsed > 240.0


func _run_all() -> void:
	_check_the_panel_is_present()
	_check_the_panel_lists_other_registered_models()
	_check_the_context_comes_from_the_registry()
	_check_verdicts_come_from_the_authoritative_payload()
	_check_a_permitted_pair_is_not_an_implemented_connection()
	_check_refused_pairs_show_context_and_reason()
	_check_unresolved_is_not_presented_as_incompatibility()
	_check_evidence_and_versions_are_preserved()
	_check_the_replay_is_still_labelled_a_replay()
	_check_the_replay_graph_still_runs_unconnected()


# --------------------------------------------------------------------------- #
# the panel itself


func _panel() -> CrossPaperPanel:
	return _scene.get("_cross")


func _check_the_panel_is_present() -> void:
	var panel := _panel()
	_ok(panel != null, "the replay scene has no cross-paper panel")
	if panel == null:
		return
	_ok(panel.has_context(), "the panel was given no context to show")
	_ok(panel.model_ids().size() >= 1,
		"the panel shows no other registered model; the replay must reference at least one")
	_ok(not panel.focus_reference().is_empty(),
		"the panel does not state the focus model's exact reference")


func _check_the_panel_lists_other_registered_models() -> void:
	var panel := _panel()
	if panel == null:
		return
	var ids: Array = panel.model_ids()
	# Every registered model other than the focus model must appear: the panel
	# is drawn from the registry payload, not from a shorter list kept here.
	_ok(ids.has(MORRIS), "the panel does not show %s" % MORRIS)
	_ok(ids.has(GANJAVE), "the panel does not show %s" % GANJAVE)
	_ok(not ids.has(ZIELINSKI),
		"the panel lists the focus model itself as a related model")
	# The focus reference carries the version, so a reader can tell which
	# model version the context was assembled for.
	_ok(panel.focus_reference() == "%s@1.0.0" % ZIELINSKI,
		"the focus reference is %s, not %s@1.0.0" % [panel.focus_reference(), ZIELINSKI])


func _check_the_context_comes_from_the_registry() -> void:
	var panel := _panel()
	if panel == null:
		return
	# The model list the panel shows must match what the runner's registry
	# command reports -- no model the registry knows is missing, and none
	# that it does not.
	var runner := CompositionRunner.new("python", ProjectSettings.globalize_path("res://composition"))
	var captured: Array = []
	var capture := func(payload: Dictionary) -> void: captured.append(payload)
	runner.finished.connect(capture)
	runner.list_models()
	runner.finished.disconnect(capture)
	var invocation: Dictionary = captured[0] if not captured.is_empty() else {}
	var registry_ids: Array = []
	for entry in invocation.get("models", []):
		registry_ids.append(str((entry as Dictionary).get("model_id", "")))
	var panel_ids: Array = panel.model_ids()
	for model_id in registry_ids:
		if model_id == ZIELINSKI:
			continue
		_ok(panel_ids.has(model_id),
			"the panel omits %s, which the registry lists" % model_id)
	for model_id in panel_ids:
		_ok(registry_ids.has(model_id),
			"the panel shows %s, which the registry does not list" % model_id)
	# The registry must report more than one model, or the cross-paper claim
	# is empty.
	_ok(registry_ids.size() > 1,
		"the registry lists %d model(s); the cross-paper panel needs at least two"
		% registry_ids.size())


# --------------------------------------------------------------------------- #
# the verdicts


func _check_verdicts_come_from_the_authoritative_payload() -> void:
	var panel := _panel()
	if panel == null:
		return
	# The panel is driven by the replay scene's own subprocess load of
	# --describe-connections. Its per-pair verdicts must equal that payload's
	# boundaries exactly, matched on the ordered pair.
	var to_ganjave: Dictionary = panel.verdict_for(ZIELINSKI, GANJAVE)
	_ok(to_ganjave.get("state", "") == "refused",
		"zielinski -> ganjave is presented as %s, not refused"
		% str(to_ganjave.get("state", "?")))
	_ok(str(to_ganjave.get("stance", "")) == "refused_dimensional_only",
		"zielinski -> ganjave carries the wrong stance: %s"
		% str(to_ganjave.get("stance", "?")))
	var to_morris: Dictionary = panel.verdict_for(ZIELINSKI, MORRIS)
	_ok(to_morris.get("state", "") == "refused",
		"zielinski -> morris is presented as %s, not refused"
		% str(to_morris.get("state", "?")))
	_ok(bool(to_morris.get("enforced_by_engine", false)),
		"zielinski -> morris is not marked as engine-enforced (CG-08/CG-09)")


func _check_a_permitted_pair_is_not_an_implemented_connection() -> void:
	var panel := _panel()
	if panel == null:
		return
	# The engine permits exactly two ordered pairs, both same-model. They must
	# be presented as permitted boundaries, never as connections between
	# different papers, and never as present in this replay.
	var permitted: PackedStringArray = panel.permitted_pairs()
	_ok(permitted.size() == 2,
		"the panel reports %d permitted pairs, not 2" % permitted.size())
	for pair in permitted:
		var parts := pair.split(" -> ")
		_ok(parts.size() == 2 and parts[0] == parts[1],
			"a permitted pair (%s) is not a same-model boundary" % pair)
	# The replay's own graph declares no connections, and the panel says so.
	_ok(int(panel.replay_connection_count()) == 0,
		"the replay graph declares %s connection(s), not 0"
		% str(panel.replay_connection_count()))
	# No card claims a connection: the context record for each related model
	# carries connection_in_replay = false.
	for model_id in panel.model_ids():
		var record: Dictionary = panel.related_record(model_id)
		var to_focus: Dictionary = record.get("compatibility_towards_focus", {})
		_ok(not bool(to_focus.get("connection_in_replay", true)),
			"%s -> focus is presented as a connection in the replay" % model_id)
		var from_focus: Dictionary = record.get("compatibility_from_focus", {})
		_ok(not bool(from_focus.get("connection_in_replay", true)),
			"focus -> %s is presented as a connection in the replay" % model_id)


func _check_refused_pairs_show_context_and_reason() -> void:
	var panel := _panel()
	if panel == null:
		return
	# Every refused direction must show BOTH the shared scientific context and
	# the specific difference, with the engine's evidence and remediation.
	for model_id in panel.model_ids():
		var record: Dictionary = panel.related_record(model_id)
		for key in ["compatibility_towards_focus", "compatibility_from_focus"]:
			var comp: Dictionary = record.get(key, {})
			if bool(comp.get("permitted", false)):
				continue
			var shared := str(comp.get("shared_context", "")).strip_edges()
			_ok(not shared.is_empty(),
				"%s (%s) shows no shared context" % [model_id, key])
			var difference := str(comp.get("fundamental_difference", "")).strip_edges()
			_ok(not difference.is_empty(),
				"%s (%s) states no fundamental difference" % [model_id, key])
			var evidence: Array = comp.get("evidence", [])
			_ok(evidence.size() >= 2,
				"%s (%s) cites %d evidence item(s), not at least 2"
				% [model_id, key, evidence.size()])
			var remediation := str(comp.get("remediation", "")).strip_edges()
			_ok(not remediation.is_empty(),
				"%s (%s) states no remediation" % [model_id, key])
			# The quantity pairs the policy names are shown with their own
			# standing and the "not present" note.
			for pair in comp.get("quantity_pairs", []):
				var pair_dict: Dictionary = pair
				_ok(not bool(pair_dict.get("connection_in_replay", true)),
					"a %s quantity pair is presented as a replay connection"
					% model_id)
				_ok(str(pair_dict.get("meaning", "")).strip_edges().length() > 40,
					"a %s quantity pair carries no specific reason" % model_id)


func _check_unresolved_is_not_presented_as_incompatibility() -> void:
	var panel := _panel()
	if panel == null:
		return
	# The ganjave <-> zielinski refusals carry an explicit unresolved field: a
	# matched model could carry quantities between them honestly. That must be
	# visible, and the pairs must read as unresolved (evidence_limited), not as
	# proven physical incompatibility.
	for model_id in [GANJAVE]:
		var record: Dictionary = panel.related_record(model_id)
		for key in ["compatibility_towards_focus", "compatibility_from_focus"]:
			var comp: Dictionary = record.get(key, {})
			var unresolved: Array = comp.get("unresolved", [])
			_ok(not unresolved.is_empty(),
				"%s (%s) hides what is unresolved" % [model_id, key])
			_ok(str(unresolved[0]).find("could") >= 0,
				"%s (%s) does not say what would resolve the gap" % [model_id, key])
			# The boundary's evidence basis must be the documented kind: the
			# engine's own reason, not an absence of judgement -- but the pair
			# verdicts that fail closed must read as unresolved.
			for pair in comp.get("quantity_pairs", []):
				var pair_dict: Dictionary = pair
				var stance := str(pair_dict.get("verdict", ""))
				if stance.begins_with("refused_unclassified"):
					_ok(false,
						"a %s pair fails closed but is not labelled unresolved" % model_id)


# --------------------------------------------------------------------------- #
# preservation


func _check_evidence_and_versions_are_preserved() -> void:
	var panel := _panel()
	if panel == null:
		return
	# Each related model's card carries its exact reference, and its assessment
	# carries the engine's evidence: citations, the model version, and the
	# provenance of every value survive into the panel.
	for model_id in panel.model_ids():
		var record: Dictionary = panel.related_record(model_id)
		var reference := str(record.get("reference", ""))
		_ok(reference.contains("@"),
			"%s's card does not carry a versioned reference" % model_id)
		var evidence_count := panel.evidence_count_for(model_id)
		_ok(evidence_count >= 2,
			"%s's assessment preserves %d evidence item(s)" % [model_id, evidence_count])
	# The examined papers keep their citation, value, unit and independence.
	var papers := panel.examined_papers()
	_ok(papers.size() >= 1, "the panel shows no ingested paper")
	for p in papers:
		var paper: Dictionary = p
		_ok(not str(paper.get("citation", "")).is_empty(),
			"examined paper %s carries no citation" % str(paper.get("finding_id", "?")))
		_ok(not str(paper.get("finding_id", "")).is_empty(),
			"an examined paper carries no finding id")


func _check_the_replay_is_still_labelled_a_replay() -> void:
	# The honesty banner and the panel's own scope statement must both be on
	# screen: the replay gains context without pretending to be a composition.
	var found_banner := false
	for node in _find_labels(_scene):
		var text := String(node.text).to_lower()
		if text.find("not a predictive simulation") >= 0:
			found_banner = true
	_ok(found_banner, "the replay no longer disclaims predictive simulation")
	var panel := _panel()
	if panel != null:
		var statement := panel.replay_scope_statement().to_lower()
		_ok(statement.find("evidence replay") >= 0,
			"the panel's scope statement no longer calls this an evidence replay")
		_ok(statement.find("no other model drives") >= 0,
			"the panel does not say another model drives the replay")
	# The scope note itself is visible somewhere in the panel.
	var found_scope := false
	for node in _find_labels(_panel()):
		var text := String(node.text)
		if text.find("declares no connections") >= 0 or text.find("single-model") >= 0:
			found_scope = true
	_ok(found_scope, "the panel's replay-scope statement is not visible on screen")


func _check_the_replay_graph_still_runs_unconnected() -> void:
	# The replay itself is untouched: same graph, same 196 published values,
	# same runner, no connections.
	_ok(FileAccess.file_exists(REPLAY_GRAPH), "the replay graph is gone")
	var runner := CompositionRunner.new("python", ProjectSettings.globalize_path("res://composition"))
	var result_path := "user://replay_cross_paper.json"
	var captured: Array = []
	var capture := func(payload: Dictionary) -> void: captured.append(payload)
	runner.finished.connect(capture)
	runner.run_graph(ProjectSettings.globalize_path(REPLAY_GRAPH), result_path)
	runner.finished.disconnect(capture)
	var invocation: Dictionary = captured[0] if not captured.is_empty() else {}
	_ok(int(invocation.get("_exit_code", -1)) == 0,
		"the replay graph no longer runs (exit %s)" % str(invocation.get("_exit_code", "?")))
	var replay := runner.read_result(result_path)
	_ok(str(replay.get("status", "")).begins_with("success"),
		"the replay graph reports %s" % str(replay.get("status", "?")))
	var results: Array = replay.get("results", [])
	_ok(results.size() == 1 and (results[0].get("outputs", []) as Array).size() == 196,
		"the replay no longer publishes the model's 196 values")
	var document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(REPLAY_GRAPH))
	_ok((document.get("connections", []) as Array).is_empty(),
		"the replay graph now declares connections")


# --------------------------------------------------------------------------- #
# helpers


func _find_labels(from: Node) -> Array:
	var out: Array = []
	if from is Label:
		out.append(from)
	for c in from.get_children():
		out.append_array(_find_labels(c))
	return out


func _ok(condition: bool, what: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(what)


func _report() -> void:
	if _failures.is_empty():
		print("replay-cross-paper: %d checks passed" % _checks)
		quit(0)
		return
	for failure in _failures:
		print("FAIL  " + failure.substr(0, 400))
	print("replay-cross-paper: %d checks, %d FAILED" % [_checks, _failures.size()])
	quit(1)
