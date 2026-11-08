extends SceneTree
## Headless harness: load, validate and RUN a graph containing Ganjave.
##
## Run it from the repository root:
##
##     godot --headless --path . --script res://composition/tests/godot/ganjave_graph_run.gd
##
## Exit code 0 means every check passed.
##
## The other harness (`contract_boundary.gd`) proves the editor can *read* a
## manifest. This one proves the editor can *execute*: it drives the same
## `CompositionRunner` the results panel uses, on the same example graph the CLI
## runs, and reads the result document back off disk.
##
## Checked here:
##   1. Ganjave is reachable through discovery, so it can be placed at all;
##   2. the graph validates (`--plan-only`): structure before execution;
##   3. the graph executes and the result document is complete and readable;
##   4. a run that fails leaves no stale success on disk.
##
## What is *not* checked is scientific validity. The result carries the model's
## own `reproduction_status`, and this harness asserts the editor surfaces it
## rather than hiding it -- that is the claim being made.

const GRAPH := "res://composition/examples/ganjave_fed_batch.json"
const RESULT := "user://ganjave_graph_run.json"
const PLAN := "user://ganjave_graph_plan.json"
const BROKEN := "user://ganjave_graph_broken.json"

var _failures: Array[String] = []
var _checks := 0


func _initialize() -> void:
	var runner: CompositionRunner = CompositionRunner.new(
		"python", ProjectSettings.globalize_path("res://composition")
	)
	if runner.python_executable() == "":
		_fail("the runner has no python executable")
		_report()
		return

	_check_discovery(runner)
	_check_plan(runner)
	_check_run(runner)
	_check_no_stale_result(runner)

	_report()


# --------------------------------------------------------------------------- #
# 1. discovery
# --------------------------------------------------------------------------- #

func _check_discovery(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)
	var loaded: Array = []
	registry.models_loaded.connect(func(m): loaded.append(m))
	registry.load()
	if loaded.is_empty():
		_fail("discovery returned no model list")
		return
	var ids := PackedStringArray()
	for entry in loaded[0]:
		ids.append(str(entry.get("model_id", "")))
	_ok(ids.has("ganjave"), "ganjave is not reachable through discovery: %s" % str(ids))
	_ok(registry.is_available("ganjave"), "ganjave is registered but unavailable")
	_ok(
		registry.reference_for("ganjave") == "ganjave@0.1.0",
		"ganjave has no unambiguous reference: %s" % registry.reference_for("ganjave")
	)


# --------------------------------------------------------------------------- #
# 2. validation
# --------------------------------------------------------------------------- #

func _check_plan(runner: CompositionRunner) -> void:
	var path := ProjectSettings.globalize_path(PLAN)
	var invocation := _invoke(runner, GRAPH, PLAN, true)
	_ok(
		int(invocation.get("_exit_code", -1)) == 0,
		"the graph did not validate (exit %s)" % str(invocation.get("_exit_code", -1))
	)
	var plan := runner.read_result(path)
	_ok(not plan.is_empty(), "the plan document was not readable")
	_ok(str(plan.get("graph_id", "")) == "ganjave_fed_batch", "wrong graph id in the plan")


# --------------------------------------------------------------------------- #
# 3. execution
# --------------------------------------------------------------------------- #

func _check_run(runner: CompositionRunner) -> void:
	var path := ProjectSettings.globalize_path(RESULT)
	var invocation := _invoke(runner, GRAPH, RESULT, false)
	_ok(
		int(invocation.get("_exit_code", -1)) == 0,
		"the graph did not execute (exit %s)" % str(invocation.get("_exit_code", -1))
	)

	var result := runner.read_result(path)
	_ok(not result.is_empty(), "the result document was not readable")
	_ok(
		str(result.get("graph_id", "")) == "ganjave_fed_batch",
		"wrong graph id in the result"
	)
	_ok(
		str(result.get("status", "")).begins_with("success"),
		"unexpected status %s" % str(result.get("status", ""))
	)
	_ok(
		str(result.get("reproducibility", "")).length() == 64,
		"the result carries no reproducibility digest"
	)

	var results: Array = result.get("results", [])
	_ok(results.size() == 1, "expected one executed instance, got %d" % results.size())
	if results.is_empty():
		return
	var node: Dictionary = results[0]
	_ok(str(node.get("model_id", "")) == "ganjave", "wrong model executed")
	_ok(
		str(node.get("status", "")).begins_with("success"),
		"the node did not succeed: %s" % str(node.get("status", ""))
	)

	var seen := {}
	for entry in node.get("outputs", []):
		seen[str(entry["ref"]["port_id"])] = entry
	for port_id in [
		"biomass_concentration",
		"glycerol_concentration",
		"complex_substrate_concentration",
		"dissolved_oxygen",
		"culture_volume",
		"simulation_time",
	]:
		_ok(seen.has(port_id), "missing output %s" % port_id)
		if not seen.has(port_id):
			continue
		var value: Dictionary = seen[port_id]["value"]
		_ok(bool(value.get("is_resolved", false)), "%s did not resolve" % port_id)
		_ok(str(value.get("unit", "")) != "", "%s has no unit" % port_id)
		_ok(
			not (seen[port_id]["provenance_chain"] as Array).is_empty(),
			"%s carries no provenance" % port_id
		)

	if seen.has("biomass_concentration"):
		var extra: Dictionary = seen["biomass_concentration"]["value"].get("extra", {})
		var claim: Dictionary = extra.get("validation_claim", {})
		_ok(
			str(claim.get("reproduction_status", "")) == "not_yet_validated",
			"the result does not carry its reproduction status"
		)
		_ok(
			str(claim.get("implementation_status", "")) == "implemented",
			"the result does not carry its implementation status"
		)
		var trajectory: Dictionary = extra.get("trajectory", {})
		_ok(
			int(trajectory.get("points", 0)) > 1,
			"the trajectory was not carried through to the editor"
		)
		_ok(
			str(trajectory.get("time_axis", {}).get("unit", "")) == "h",
			"the trajectory time axis has no unit"
		)

	# Diagnostics must be readable and must name the open scientific question.
	var messages := ""
	var errors := 0
	for entry in result.get("diagnostics", []):
		messages += str(entry.get("message", "")) + "\n"
		if str(entry.get("severity", "")) == "error":
			errors += 1
	_ok(messages.find("not_yet_validated") >= 0, "the result does not report its status")
	_ok(messages.find("TN-02") >= 0, "the open transcription item TN-02 is not surfaced")
	_ok(errors == 0, "a successful run reported %d error diagnostics" % errors)


# --------------------------------------------------------------------------- #
# 4. no stale result
# --------------------------------------------------------------------------- #

func _check_no_stale_result(runner: CompositionRunner) -> void:
	## A failing run must overwrite the result document rather than leave the
	## previous, successful one readable. The document is written first, then a
	## deliberately invalid graph is run into the *same* path.
	var path := ProjectSettings.globalize_path(RESULT)
	_ok(not runner.read_result(path).is_empty(), "the successful result is missing to begin with")

	var file := FileAccess.open(BROKEN, FileAccess.WRITE)
	if file == null:
		_fail("could not write the deliberately broken graph")
		return
	file.store_string(
		'{"contract_version": "0.1.0", "graph_id": "gj_broken", "title": "broken",'
		+ ' "instances": [{"instance_id": "x", "model_id": "ganjave",'
		+ ' "model_version": "0.1.0", "parameters": {}}]}'
	)
	file = null

	var invocation := _invoke(runner, BROKEN, RESULT, false)
	_ok(
		int(invocation.get("_exit_code", -1)) != 0,
		"a graph with a missing required input was accepted"
	)
	var result := runner.read_result(path)
	_ok(not result.is_empty(), "the failed run left no document at all")
	_ok(
		str(result.get("graph_id", "")) == "gj_broken",
		"the document on disk is the *previous* run: a stale result survived"
	)
	_ok(
		not str(result.get("status", "")).begins_with("success"),
		"the stale document still reports success"
	)
	_ok(
		int(result.get("error_count", 0)) > 0,
		"the failed run reported no errors"
	)


# --------------------------------------------------------------------------- #

func _invoke(
	runner: CompositionRunner, graph: String, result: String, plan_only: bool
) -> Dictionary:
	var captured: Array = []
	var handler := func(p): captured.append(p)
	runner.finished.connect(handler)
	if plan_only:
		runner.plan_graph(ProjectSettings.globalize_path(graph), result)
	else:
		runner.run_graph(ProjectSettings.globalize_path(graph), result)
	runner.finished.disconnect(handler)
	if captured.is_empty():
		return {"_exit_code": -1, "_output": "the runner emitted no payload"}
	return captured[0]


func _ok(condition: bool, what: String) -> void:
	_checks += 1
	if condition:
		return
	_failures.append(what)


func _fail(what: String) -> void:
	_checks += 1
	_failures.append(what)


func _report() -> void:
	if _failures.is_empty():
		print("ganjave-graph-run: %d checks passed" % _checks)
		quit(0)
		return
	for failure in _failures:
		print("FAIL  %s" % failure.substr(0, 300))
	print("ganjave-graph-run: %d checks, %d FAILED" % [_checks, _failures.size()])
	quit(1)