extends SceneTree
## Headless acceptance harness for the GDScript -> Python contract boundary.
##
## Run it from the repository root:
##
##     godot --headless --path . --script res://composition/tests/godot/contract_boundary.gd
##
## Exit code 0 means every check passed.  Anything else prints the failures and
## exits 1.
##
## What this checks is *structural only*: that a model id resolves to exactly
## one registered model, that the manifest the editor draws is the manifest the
## Python engine compiled, and that every port it publishes is addressable.  None
## of that is a claim about scientific compatibility.  Whether two ports may be
## *connected* is decided by the engine, under CG-02, CG-03, CG-08 and CG-09,
## and a refusal there is a diagnostic, not an exception in this file.

const RUNNER_MODULE := "res://scripts/runner.gd"

var _failures: Array[String] = []
var _checks := 0


func _initialize() -> void:
	var runner: CompositionRunner = CompositionRunner.new("python", _composition_dir())
	if runner.python_executable() == "":
		_fail("the runner has no python executable")
		_report()
		return

	_check_discovery(runner)
	_check_contract(runner)
	_check_manifest_of_a_fixed_port_model(runner)
	_check_manifest_of_an_instance_parameterised_model(runner)
	_check_an_unresolvable_reference(runner)
	_check_port_rendering_precedence(runner)
	_check_stdout_parsing()

	_report()


func _composition_dir() -> String:
	return ProjectSettings.globalize_path("res://composition")


func _report() -> void:
	if _failures.is_empty():
		print("contract-boundary: %d checks passed" % _checks)
		quit(0)
		return
	for failure in _failures:
		printerr("FAIL  " + failure)
	printerr("contract-boundary: %d checks, %d FAILED" % [_checks, _failures.size()])
	quit(1)


func _ok(condition: bool, what: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(what)


func _fail(what: String) -> void:
	_failures.append(what)


# --------------------------------------------------------------------------- #


func _check_discovery(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)

	var loaded: Array = []
	var failed: Array = []
	registry.models_loaded.connect(func(m): loaded.append(m))
	registry.load_failed.connect(func(msg): failed.append(msg))
	registry.load()

	_ok(failed.is_empty(), "discovery failed: %s" % str(failed))
	_ok(loaded.size() == 1, "expected exactly one models_loaded, got %d" % loaded.size())
	if loaded.is_empty():
		return

	var models: Array = loaded[0]
	# The *count* is not the contract. Registering a model must not require an
	# edit to this harness, or every future model would need a GDScript change
	# to be visible in the editor. What the boundary owes is that every model
	# the runner reports is resolvable, available and unambiguously versioned --
	# which the per-model checks below assert for whatever number there is.
	_ok(
		models.size() >= 2,
		"expected at least 2 registered models, got %d" % models.size()
	)
	_ok(
		registry.model_ids().has("ganjave"),
		"the Ganjave model is registered but did not reach discovery"
	)
	for model_id in registry.model_ids():
		_ok(registry.is_available(model_id), "%s should be available" % model_id)
		var reference := registry.reference_for(model_id)
		_ok(
			reference.begins_with(model_id + "@"),
			"%s has no unambiguous reference (got %s)" % [model_id, reference]
		)
		_ok(not reference.ends_with("@"), "%s reference names no version" % model_id)

	# Baez is deliberately unregistered. Discovery must not reach for it.
	var ids := PackedStringArray()
	for model_id in registry.model_ids():
		ids.append(model_id)
	_ok(not ids.has("baez2014.oxygen_induced"), "discovery reached an unregistered model")


func _check_contract(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)
	registry.load()

	_ok(registry.quantities().size() > 0, "the quantity registry stayed empty")
	var names := PackedStringArray()
	for entry in registry.quantities():
		names.append(str(entry["name"]))
	# These three are declared by the engine and were missing from the old
	# hand-written palette in this file.
	for expected in ["mass_concentration", "temperature", "wavelength"]:
		_ok(names.has(expected), "quantity %s is missing from the contract" % expected)
	_ok(not names.has("other"), "'other' is a UI placeholder, not a contract quantity")

	_ok(registry.canonical_quantity("mass") == "mass", "mass is a declared quantity")
	_ok(
		registry.canonical_quantity("no_such_quantity") == ModelRegistry.UNKNOWN_QUANTITY,
		"an undeclared quantity must not resolve to a neighbour"
	)
	_ok(registry.units_for("volume_flow").size() > 0, "volume_flow has no units")
	_ok(registry.units_for("no_such_quantity").is_empty(), "unknown quantity has units")
	_ok(
		registry.colour_for("no_such_quantity") == ModelRegistry.UNKNOWN_COLOUR,
		"an unknown quantity must not borrow a known one's colour"
	)
	_ok(registry.direction_label("input") == "input", "direction_label(input)")
	_ok(registry.direction_label("nonsense") == "output", "direction_label falls back")


func _check_manifest_of_a_fixed_port_model(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)
	registry.load()

	var manifests: Dictionary = {}
	var failures: Array = []
	registry.manifest_loaded.connect(
		func(id, manifest): manifests[id] = manifest
	)
	registry.manifest_failed.connect(
		func(id, msg): failures.append("%s: %s" % [id, msg])
	)
	registry.request_manifest("zielinski2019.rhi_process")

	_ok(failures.is_empty(), "manifest read failed: %s" % str(failures))
	_ok(
		manifests.has("zielinski2019.rhi_process"),
		"the Zielinski manifest did not arrive"
	)
	if not manifests.has("zielinski2019.rhi_process"):
		return

	var manifest: Dictionary = manifests["zielinski2019.rhi_process"]
	_ok(registry.port_dependence_for("zielinski2019.rhi_process") == "fixed",
		"zielinski should publish a fixed port set")
	_ok(manifest.get("reference", "") == "zielinski2019.rhi_process@1.0.0",
		"the manifest names no exact reference")

	var ports: Array = registry.ports_for("zielinski2019.rhi_process")
	_ok(ports.size() == 196, "expected 196 declared ports, got %d" % ports.size())
	var counts: Dictionary = registry.port_counts_for("zielinski2019.rhi_process")
	_ok(int(counts.get("input", 0)) + int(counts.get("output", 0)) == ports.size(),
		"the port counts do not add up to the port list")

	var seen := {}
	var declared_quantities := {}
	for entry in registry.quantities():
		declared_quantities[str(entry["name"])] = true
	for port in ports:
		var port_id := str(port["port_id"])
		_ok(not seen.has(port_id), "duplicate port id %s" % port_id)
		seen[port_id] = true
		_ok(port["direction"] in ["input", "output"], "%s has no direction" % port_id)
		_ok(declared_quantities.has(str(port["quantity"])),
			"%s declares quantity %s, which the contract does not define"
			% [port_id, str(port["quantity"])])
		_ok(str(port.get("label", "")) != "", "%s has no label to draw" % port_id)

	# Structural resolvability against the graph that ships with it.
	var graph: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(
			ProjectSettings.globalize_path("res://composition/examples/brass_batch_chain.json")
		)
	)
	for instance in graph.get("instances", []):
		if str(instance["model_id"]) != "zielinski2019.rhi_process":
			continue
		_ok(seen.has("node:N01#inoculum_volume"),
			"a port the graph document names is not in the manifest")
		_ok(seen.has("node:N01#specific_growth_rate"),
			"the one unconnectable port must still be published")

	_ok(registry.parameter_sections_for("zielinski2019.rhi_process").size() > 0,
		"the Zielinski manifest declares no parameter sections")


func _check_manifest_of_an_instance_parameterised_model(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)
	registry.load()

	var manifests: Dictionary = {}
	registry.manifest_loaded.connect(
		func(id, manifest): manifests[id] = manifest
	)
	registry.request_manifest("morris2011.material_balance")

	_ok(manifests.has("morris2011.material_balance"),
		"the Morris record did not arrive")
	if not manifests.has("morris2011.material_balance"):
		return
	_ok(
		registry.port_dependence_for("morris2011.material_balance") == "instance",
		"Morris must be reported as instance-parameterised, not as port-less"
	)
	# A refusal is not a failure, and is not filled in on the model's behalf.
	_ok(registry.ports_for("morris2011.material_balance").is_empty(),
		"an instance-parameterised model must not publish a synthesised port list")


func _check_an_unresolvable_reference(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)
	registry.load()

	var failures: Dictionary = {}
	registry.manifest_failed.connect(
		func(id, msg): failures[id] = msg
	)
	registry.request_manifest("no.such_model")

	_ok(failures.has("no.such_model"), "an unknown model id resolved to something")
	if failures.has("no.such_model"):
		var message := str(failures["no.such_model"])
		_ok(not registry.has_manifest("no.such_model"),
			"a refused reference left a manifest behind")
		_ok(message.contains("no model is registered"),
			"the refusal does not say what is registered: " + message)


func _check_port_rendering_precedence(runner: CompositionRunner) -> void:
	var registry := ModelRegistry.new()
	root.add_child(registry)
	registry.setup(runner)
	registry.load()
	registry.request_manifest("zielinski2019.rhi_process")

	# 2. the manifest, when the instance configures nothing itself
	var from_manifest := ModelNode.new()
	root.add_child(from_manifest)
	from_manifest.setup(
		{"instance_id": "n1", "model_id": "zielinski2019.rhi_process", "label": "z"},
		registry
	)
	_ok(from_manifest.ports_source == "manifest",
		"expected manifest-sourced ports, got %s" % from_manifest.ports_source)
	_ok(from_manifest.ports.size() == 196,
		"the node drew %d ports, expected 196" % from_manifest.ports.size())

	# 1. explicit configuration on the graph instance wins
	var explicit := ModelNode.new()
	root.add_child(explicit)
	explicit.setup(
		{
			"instance_id": "n2",
			"model_id": "zielinski2019.rhi_process",
			"label": "z",
			"parameters": {"ports": [
				{"port_id": "only:this", "direction": "input", "quantity": "mass",
				 "unit": "kg", "label": "hand configured"}
			]},
		},
		registry
	)
	_ok(explicit.ports_source == "instance",
		"explicit instance ports did not take precedence")
	_ok(explicit.ports.size() == 1 and explicit.ports[0]["port_id"] == "only:this",
		"the explicit port list was not used verbatim")

	# 3. the legacy fallback only where the model is instance-parameterised
	var fallback := ModelNode.new()
	root.add_child(fallback)
	fallback.setup(
		{
			"instance_id": "n3",
			"model_id": "zielinski2019.rhi_process",
			"label": "z",
			"parameters": {"system": {
				"streams": [{"stream_id": "A", "amount": {"value": 1.0}}],
				"components": [],
			}},
		},
		registry
	)
	_ok(fallback.ports_source == "manifest",
		"the Morris grammar was applied to a fixed-port model")


func _check_stdout_parsing() -> void:
	# The introspection flags answer on stdout, which Godot merges with stderr.
	# `JSON` parses every number as a float, so these compare values, not literals.
	_ok(
		CompositionRunner._parse_json_object('{"a": 1}').get("a", 0.0) == 1.0,
		"plain JSON was not parsed"
	)
	_ok(
		CompositionRunner._parse_json_object('  \n {"a": {"b": [1, 2]}} \n ')
			.get("a", {}).get("b", [])[1] == 2.0,
		"padded JSON was not parsed"
	)
	_ok(
		CompositionRunner._parse_json_object("Traceback (most recent call last):\n")
			.is_empty(),
		"a traceback with no JSON should parse to nothing"
	)
	_ok(
		CompositionRunner._parse_json_object("").is_empty(),
		"empty output should parse to nothing"
	)
	# A JSON object inside stderr noise still resolves.
	_ok(
		CompositionRunner._parse_json_object('warning: x\n{"models": [1]}')
			.get("models", [])[0] == 1.0,
		"JSON after a warning line was not found"
	)
	# A brace inside a string must not be mistaken for the end of the object.
	_ok(
		CompositionRunner._parse_json_object('{"note": "a } b"}').get("note", "") == "a } b",
		"a brace inside a string terminated the scan early"
	)
	# Exit codes keep their documented meanings.
	_ok(
		CompositionRunner.exit_meaning(0) == "the graph validated and executed",
		"exit 0 meaning"
	)
	_ok(
		CompositionRunner.exit_meaning(2) != CompositionRunner.exit_meaning(3),
		"exit 2 and 3 must not share a meaning"
	)
	_ok(
		CompositionRunner.exit_meaning(4) != CompositionRunner.exit_meaning(3),
		"exit 3 and 4 must not share a meaning"
	)
	_ok(
		CompositionRunner.exit_meaning(99) == "an undocumented exit code",
		"an undocumented exit code must say so"
	)