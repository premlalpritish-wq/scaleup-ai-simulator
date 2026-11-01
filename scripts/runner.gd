class_name CompositionRunner
extends Node
## Invokes the Python composition runner as a subprocess.
##
## This is the *only* point where GDScript touches the scientific engine. It
## never interprets results: it checks the exit status, reads the document the
## runner produced, and hands the parsed dictionary to the panels. A missing or
## malformed document is reported as a failure, never as an empty success.
##
## Two kinds of invocation, and they carry their answer differently:
##   * graph runs write a result *file*, which is read from disk;
##   * introspection (`--list-models`, `--describe-model`, `--describe-contract`)
##     writes JSON to *stdout*, which is read from the captured output.
## Both are parsed with the same "missing or malformed means failure" rule.
##
## Exit codes, as documented in `composition/runner.py`:
##   0  the graph validated and executed (see `status` for warnings)
##   1  the graph did not validate
##   2  the graph validated and execution failed
##   3  the input was unusable
##   4  the runner itself could not run
##
## The call is synchronous. A composition run takes a few seconds for the
## graphs this project ships, and a synchronous call keeps the failure modes
## simple: either the process ran and wrote a file, or it did not.
##
## Platform notes (verified against Godot 4.7.2, Windows):
##   * `OS.execute(path, arguments, output, read_stderr, open_console)`. This
##     build has **no `env` parameter** -- it was removed. Passing
##     "KEY=VALUE" strings positionally lands them in `output`, where they are
##     silently discarded, so the child process inherits nothing. The only way
##     to export an environment variable is `OS.set_environment()`, which
##     mutates this process so children inherit it.
##   * `OS.execute_with_pipe()` is not usable here: it returns live pipe handles
##     and `blocking = true` waits for the child to exit, so any output larger
##     than the OS pipe buffer deadlocks. `OS.execute(..., read_stderr = true)`
##     drains internally and cannot.
##   * `capture_output` merges stdout and stderr into one array. They are not
##     separable through this API, so the UI labels the merged text as such
##     rather than guessing which stream produced which line.

signal finished(payload: Dictionary)

const EXIT_OK := 0
const EXIT_INVALID := 1
const EXIT_FAILED := 2
const EXIT_BAD_INPUT := 3
const EXIT_RUNNER_ERROR := 4

var _python := "python"
var _composition_dir := ""
var _is_web := OS.get_name() == "Web"
var _js_window = null
var _js_callback = null


func _init(python_path: String = "", composition_dir: String = "") -> void:
	_python = python_path if python_path != "" else "python"
	_composition_dir = composition_dir
	if _is_web:
		_js_window = JavaScriptBridge.get_interface("window")
		_js_callback = JavaScriptBridge.create_callback(_on_js_result)


## Run the graph at `graph_path`, writing results to `result_path`.
func run_graph(graph_path: String, result_path: String) -> void:
	if _is_web:
		_web_run_graph(graph_path, result_path)
		return
	var args := PackedStringArray([
		"-m", "composition.runner",
		"--graph", graph_path,
		"--result", result_path,
	])
	emit_signal("finished", _execute(args, graph_path, result_path))


## Validate only: order the graph and produce a plan, execute nothing.
func plan_graph(graph_path: String, result_path: String) -> void:
	if _is_web:
		_web_run_graph(graph_path, result_path)
		return
	var args := PackedStringArray([
		"-m", "composition.runner",
		"--graph", graph_path,
		"--result", result_path,
		"--plan-only",
	])
	emit_signal("finished", _execute(args, graph_path, result_path))


## Introspection: list the models this runner can reach.
##
## These answer questions about what *exists*; they never execute a model. All
## three write JSON to stdout and exit 0 on success, so they are read from the
## subprocess output rather than from a result file.
func list_models() -> void:
	if _is_web:
		if _js_window == null:
			emit_signal("finished", {"models":[]})
			return
		_js_window.godotPyodide.listModels(_js_callback)
		return
	var args := PackedStringArray(["-m", "composition.runner", "--list-models"])
	emit_signal("finished", _execute_introspection(args))


## Describe one registered model: its exact identity and its manifest.
##
## `model_id` may be `<id>` or `<id>@<version>`. A reference that does not
## resolve to exactly one registered model exits 3 and returns a payload naming
## the references that would -- no model is ever substituted.
func describe_model(model_id: String) -> void:
	if _is_web:
		if _js_window == null:
			emit_signal("finished", {"resolved":false,"manifest":{}})
			return
		_js_window.godotPyodide.manifest(_js_callback)
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--describe-model", model_id,
	])
	emit_signal("finished", _execute_introspection(args))


## The quantity and unit registry, which is the single source of truth for what
## this contract can express. Nothing in this editor declares its own.
func describe_contract() -> void:
	if _is_web:
		emit_signal("finished", {"quantities":{}})
		return
	var args := PackedStringArray(["-m", "composition.runner", "--describe-contract"])
	emit_signal("finished", _execute_introspection(args))


## The declared cross-model connection position: every ordered pair of registered
## models, whether a connection is permitted, the evidence, and what is unresolved.
##
## This is the *only* compatibility authority the UI consults. The workshop scene
## reads it rather than carrying its own list, so a rule change in `cross_model.py`
## reaches the interface without anything here being edited.
func describe_connections() -> void:
	if _is_web:
		emit_signal("finished", {})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--describe-connections",
	])
	emit_signal("finished", _execute_introspection(args))


## The ingested-paper corpus: every paper folder under `Models/`, the model that
## encodes it if one exists, and the recorded reason for the ones none does.
##
## This is not a model list and not a compatibility position. A paper is evidence
## a model may rest on; it is never an executable component, and nothing in the
## editor may place one as a node. Read it with `--describe-papers`.
func describe_papers() -> void:
	if _is_web:
		emit_signal("finished", {"papers": []})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--describe-papers",
	])
	emit_signal("finished", _execute_introspection(args))


## The scientific gaps in the Zielinski insulin simulation, the existing papers
## that inform each one, and the research recommendations for what remains.
##
## This is an introspection call: it reads existing model artifacts,
## compatibility records and the paper index, executes no model and writes no
## result file. A missing document is reported as a discovery failure, never as
## "no gaps exist".
func describe_scientific_gaps() -> void:
	if _is_web:
		emit_signal("finished", {})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--describe-gaps",
	])
	emit_signal("finished", _execute_introspection(args))


## Interpret a natural-language prompt against the existing Zielinski manifest.
## This runs no model. The answer is a structured configuration or a
## clarification/rejection, never generated Python or an invented value.
func interpret_prompt(prompt_text: String) -> void:
	if _is_web:
		emit_signal("finished", {})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--interpret-prompt", prompt_text,
	])
	emit_signal("finished", _execute_introspection(args))


## Interpret, validate and execute one prompt through the existing runner.
##
## The runner writes a result document, so this uses the same `_execute` path as
## the graph editor and the replay. The original replay graph is also run by the
## runner for the unchanged-baseline comparison.
func run_prompt(prompt_text: String, result_path: String) -> void:
	if _is_web:
		emit_signal("finished", {"status": "failed", "error_count": 1, "results": []})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--run-prompt", prompt_text,
		"--result", result_path,
	])
	emit_signal("finished", _execute(
		args,
		"res://composition/replay/zielinski_replay.json",
		result_path,
	))


## The standing of every model in the project against the insulin process: its
## classification, what was inspected, why it cannot contribute, and which
## dynamic connections the engine actually permits.
##
## This is *not* the cross-model position (`--describe-connections`), which covers
## ordered pairs of registered models only. It is the wider question: all seven
## papers, including the four that publish no ports at all.
func describe_compatibility() -> void:
	if _is_web:
		emit_signal("finished", {})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--describe-compatibility",
	])
	emit_signal("finished", _execute_introspection(args))


## Execute the baseline replay and the multi-model composition graph, and compare
## the insulin instance's values across the two runs.
##
## This runs two graphs, so it is slower than the introspections above. It is
## still synchronous: the caller presses a button and waits for an answer, and a
## half-rendered comparison would be worse than a short wait.
func compare_composition() -> void:
	if _is_web:
		emit_signal("finished", {})
		return
	var args := PackedStringArray([
		"-m", "composition.runner", "--compare-composition",
	])
	emit_signal("finished", _execute_introspection(args))


## The executable this runner invokes.
func python_executable() -> String:
	return _python


## The composition package directory this runner was constructed with.
func composition_directory() -> String:
	return _composition_dir


## Build the exact argv for a runner invocation and export `PYTHONPATH`.
##
## Public so that an asynchronous caller -- the 3D replay scene, which must not
## block the UI -- constructs byte-identical arguments and environment to this
## synchronous path. Keeping it here means there is one place that knows how
## GDScript crosses into Python.
func prepare(args: PackedStringArray) -> PackedStringArray:
	# The Python runner is an ordinary `pathlib` program: it has no notion of
	# Godot's `res://` / `user://` schemes. Anything virtual is resolved here,
	# at the single point where the boundary is crossed.
	var argv := PackedStringArray()
	for arg in args:
		argv.append(_to_os_path(str(arg)))
	# `composition` is not installed into the interpreter; it is imported from
	# the repository via PYTHONPATH. Godot 4.7 has no way to pass an environment
	# per-execution, so set it on this process and let the child inherit it.
	if _composition_dir != "":
		OS.set_environment("PYTHONPATH", _composition_dir)
	return argv


func _web_run_graph(graph_path: String, result_path: String) -> void:
	var file := FileAccess.open(graph_path, FileAccess.READ)
	var graph_text := "{}"
	if file != null:
		graph_text = file.get_as_text()
		file.close()
	if _js_window == null:
		emit_signal("finished", {"status":"failed","error_count":1,"diagnostics":[{"code":"runner.no_bridge","message":"JavaScript bridge unavailable."}],"results":[],"trajectories":{}})
		return
	_js_window.godotPyodide.runGraph(graph_text, _js_callback)


func _on_js_result(args: Array) -> void:
	var text := "{}"
	if args.size() > 0:
		text = str(args[0])
	var parsed := JSON.new()
	if parsed.parse(text) == OK and parsed.get_data() is Dictionary:
		var d: Dictionary = parsed.get_data()
		if d.get("ok", false):
			if d.has("manifest"):
				emit_signal("finished", {"manifest":d.get("manifest",{}),"resolved":true})
				return
			if d.has("models"):
				emit_signal("finished", {"models":d.get("models",[])})
				return
			var r: Dictionary = d.get("result", {})
			var repro := ""
			if r.has("summary"):
				repro = str(r.get("summary",{}).get("input_digest",""))
			var payload := {"status":"success","results":[{"outputs":r.get("outputs",[]),"status":"success"}],"trajectories":{},"diagnostics":r.get("diagnostics",[]),"provenance":r.get("provenance",{}),"composition_report":r.get("composition_report",{}),"model_versions":{"ganjave_fed_batch":"0.1.0"},"reproducibility":repro,"_bridge_result":r}
			emit_signal("finished", payload)
			return
		emit_signal("finished", {"status":"failed","error_count":1,"diagnostics":[{"code":"runner.bridge_error","message":str(d.get("error","bridge error"))}],"results":[],"trajectories":{}})
		return
	emit_signal("finished", {"status":"failed","error_count":1,"diagnostics":[{"code":"runner.bridge_parse","message":"Could not parse bridge response."}],"results":[],"trajectories":{}})


func _execute(args: PackedStringArray, graph_path: String, result_path: String) -> Dictionary:
	var argv := prepare(args)
	var graph_abs := _to_os_path(graph_path)
	var result_abs := _to_os_path(result_path)

	var captured: Array = []
	var code: int = OS.execute(_python, argv, captured, true, false)
	var output := "".join(captured)

	var payload := _read_result(result_abs)
	if payload.is_empty():
		payload = {
			"status": "failed",
			"error_count": 1,
			"warning_count": 0,
			"results": [],
			"diagnostics": [_runner_diagnostic(
				"runner.malformed_result",
				"The runner exited with code %d but no usable result document was found at %s.\n\n%s"
					% [code, result_abs, _invocation_report(argv, graph_abs, result_abs, output)],
				"The Python process ran but did not produce a readable result file. "
				+ "Run the command below by hand to see the full traceback."
			)],
		}
	elif payload.get("status") == null:
		payload = {
			"status": "failed",
			"error_count": 1,
			"warning_count": 0,
			"results": [],
			"diagnostics": [_runner_diagnostic(
				"runner.malformed_result",
				"The result document at %s has no 'status' field. The runner treats a malformed result as a failure rather than as an empty success.\n\n%s"
					% [result_abs, _invocation_report(argv, graph_abs, result_abs, output)],
				"Inspect the result file. It was written, but not by a runner this editor understands."
			)],
		}

	return _annotate(payload, code, output, argv, graph_abs, result_abs)


## Run an introspection invocation and read its answer from stdout.
##
## `--list-models`, `--describe-model` and `--describe-contract` write JSON to
## stdout and exit 0. Godot merges stdout with stderr, so the text is parsed
## leniently and a parse failure is reported as a discovery failure rather than
## as an empty registry -- an editor that silently shows no models is
## indistinguishable from one that has none.
func _execute_introspection(args: PackedStringArray) -> Dictionary:
	var argv := prepare(args)

	var captured: Array = []
	var code: int = OS.execute(_python, argv, captured, true, false)
	var output := "".join(captured)

	var payload := _parse_json_object(output)
	if payload.is_empty():
		payload = {
			"resolved": false,
			"models": [],
			"error_count": 1,
			"diagnostics": [_runner_diagnostic(
				"runner.malformed_result",
				"The runner exited with code %d and did not answer on stdout with a readable JSON object.\n\n%s"
					% [code, _invocation_report(argv, "", "", output)],
				"Run the command below by hand. A Python import error or a missing "
				+ "model package looks exactly like this."
			)],
		}
	return _annotate(payload, code, output, argv, "", "")


## Parse the first top-level JSON object in `text`, ignoring anything before it.
##
## `OS.execute` cannot separate stdout from stderr, so a traceback printed by the
## interpreter can precede the JSON. Taking the last balanced object is what
## makes introspection work on a machine that also prints warnings.
static func _parse_json_object(text: String) -> Dictionary:
	var trimmed := text.strip_edges()
	if trimmed.is_empty():
		return {}
	# Fast path: the whole output is the object.
	var direct := JSON.new()
	if direct.parse(trimmed) == OK and direct.get_data() is Dictionary:
		return direct.get_data()
	# Otherwise find the first '{' and try every subsequent balanced candidate.
	for start in range(trimmed.length()):
		if trimmed[start] != "{":
			continue
		var depth := 0
		var in_string := false
		var escaped := false
		for i in range(start, trimmed.length()):
			var c := trimmed[i]
			if in_string:
				if escaped:
					escaped = false
				elif c == "\\":
					escaped = true
				elif c == "\"":
					in_string = false
				continue
			if c == "\"":
				in_string = true
			elif c == "{":
				depth += 1
			elif c == "}":
				depth -= 1
				if depth == 0:
					var candidate := JSON.new()
					if candidate.parse(trimmed.substr(start, i - start + 1)) == OK \
							and candidate.get_data() is Dictionary:
						return candidate.get_data()
					break
	return {}


func _annotate(
	payload: Dictionary,
	code: int,
	output: String,
	argv: PackedStringArray,
	graph_abs: String,
	result_abs: String
) -> Dictionary:
	payload["_exit_code"] = code
	payload["_output"] = output
	payload["_python"] = _python
	payload["_argv"] = argv
	payload["_pythonpath"] = _composition_dir
	payload["_graph_path"] = graph_abs
	payload["_result_path"] = result_abs
	return payload


## Godot 4.7 merged stdout and stderr; there is no way to split them through
## `OS.execute`. Everything below is verbatim captured subprocess text.
func _invocation_report(
	argv: PackedStringArray,
	graph_abs: String,
	result_abs: String,
	output: String
) -> String:
	var lines := PackedStringArray([
		"--- how the runner was invoked ---",
		"executable : %s" % _python,
		"argv       : %s" % " ".join(argv),
		"PYTHONPATH : %s" % (_composition_dir if _composition_dir != "" else "(unset)"),
		"cwd        : %s" % _cwd_hint(),
		"graph      : %s%s" % [graph_abs, "" if FileAccess.file_exists(graph_abs) else "   [MISSING]"],
		"result     : %s%s" % [result_abs, "" if FileAccess.file_exists(result_abs) else "   [NOT WRITTEN]"],
		"",
		"--- subprocess output (stdout and stderr, merged) ---",
	])
	if output.strip_edges().is_empty():
		lines.append("(the process wrote nothing to either stream)")
	else:
		lines.append(output.strip_edges())
	return "\n".join(lines)


## The child inherits this process's working directory. Godot exposes no
## getcwd(), so the only reliable witness is what Python itself reports.
func _cwd_hint() -> String:
	var probe: Array = []
	OS.execute(_python, PackedStringArray(["-c", "import os;print(os.getcwd())"]), probe, true, false)
	return "".join(probe).strip_edges()


func _runner_diagnostic(code: String, message: String, remediation: String) -> Dictionary:
	return {
		"code": code,
		"severity": "error",
		"message": message,
		"where": ["runner"],
		"origin": "runner",
		"remediation": remediation,
	}


static func _to_os_path(path: String) -> String:
	if path.begins_with("res://") or path.begins_with("user://"):
		return ProjectSettings.globalize_path(path)
	return path


## Parse a result document written by the runner.
##
## Public so an asynchronous caller -- the 3D replay scene, which must not block
## the window -- applies exactly the same "missing or malformed means failure"
## rule as the synchronous path above.
func read_result(path: String) -> Dictionary:
	if path.begins_with("res://") and FileAccess.file_exists(path):
		return _read_result(path)
	return _read_result(_to_os_path(path))


func _read_result(path: String) -> Dictionary:
	if path == "" or not FileAccess.file_exists(path):
		return {}
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var text := f.get_as_text()
	f.close()
	var json := JSON.new()
	if json.parse(text) != OK:
		return {}
	var data: Variant = json.get_data()
	if not data is Dictionary:
		return {}
	return data


## What each documented exit code means, in the runner's own words.
##
## Every code except 3 and 4 still produces a result document that explains
## itself; the runner's own module docstring is the authority for this table.
static func exit_meaning(code: int) -> String:
	match code:
		EXIT_OK:
			return "the graph validated and executed"
		EXIT_INVALID:
			return "the graph did not validate, and nothing was executed"
		EXIT_FAILED:
			return "the graph validated, and execution failed"
		EXIT_BAD_INPUT:
			return "the input was unusable: a missing file, malformed JSON, or a document that does not satisfy the contract"
		EXIT_RUNNER_ERROR:
			return "the runner itself could not run"
	return "an undocumented exit code"


static func status_summary(payload: Dictionary) -> String:
	var status: String = str(payload.get("status", "unknown"))
	var errors: int = int(payload.get("error_count", 0))
	var warnings: int = int(payload.get("warning_count", 0))
	match status:
		"success":
			return "Executed cleanly"
		"success_with_warnings":
			return "Executed with %d warning(s)" % warnings
		"invalid":
			return "Not run -- %d error(s)" % errors
		"refused":
			return "Refused -- %d error(s)" % errors
		"failed":
			return "Execution failed -- %d error(s)" % errors
		_:
			return status


static func status_severity(payload: Dictionary) -> String:
	match str(payload.get("status", "")):
		"success":
			return "ok"
		"success_with_warnings":
			return "warning"
		"invalid", "refused":
			return "error"
		"failed":
			return "error"
	return "unknown"