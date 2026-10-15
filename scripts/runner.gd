class_name CompositionRunner
extends Node
## Invokes the Python composition runner as a subprocess.
##
## This is the *only* point where GDScript touches the scientific engine. It
## never interprets results: it checks the exit status, reads the result file,
## and hands the parsed document to the panels. A missing or malformed result
## file is reported as a failure, never as an empty success.
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


func _init(python_path: String = "", composition_dir: String = "") -> void:
	_python = python_path if python_path != "" else "python"
	_composition_dir = composition_dir


## Run the graph at `graph_path`, writing results to `result_path`.
func run_graph(graph_path: String, result_path: String) -> void:
	var args := PackedStringArray([
		"-m", "composition.runner",
		"--graph", graph_path,
		"--result", result_path,
	])
	emit_signal("finished", _execute(args, graph_path, result_path))


## Validate only: order the graph and produce a plan, execute nothing.
func plan_graph(graph_path: String, result_path: String) -> void:
	var args := PackedStringArray([
		"-m", "composition.runner",
		"--graph", graph_path,
		"--result", result_path,
		"--plan-only",
	])
	emit_signal("finished", _execute(args, graph_path, result_path))


func list_models() -> void:
	var args := PackedStringArray(["-m", "composition.runner", "--list-models"])
	emit_signal("finished", _execute(args, "", ""))


## The executable this runner invokes.
func python_executable() -> String:
	return _python


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