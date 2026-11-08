extends SceneTree
## Acceptance harness for the restored model palette.
##
## Run it from the repository root:
##
##     godot --headless --path . --script res://composition/tests/godot/palette_graph_run.gd
##
## Exit code 0 means every check passed.
##
## What it drives is the **real main scene**: `res://scenes/composition.tscn`
## is loaded, the palette's own Add buttons are pressed, the configuration form
## is opened and confirmed through its own OK button, and the graph is run
## through the same handler the Run button is wired to. Nothing here calls the
## Python layer directly, so a green run is a claim about the UI, not about the
## runner.
##
## What it does *not* claim: that any model is scientifically valid. Morris,
## Zielinski and Ganjave are checked for identity, configuration and execution.
## The values the test supplies are the operator's declarations, and the test
## states where each one comes from. Ganjave's inputs are the same literals the
## shipped `ganjave_fed_batch.json` documents, with the same reasoning.

## The editor now asks the runner six times on startup (model list, one
## manifest per registered model, the quantity contract, and the compatibility
## position), each a separate interpreter invocation. The wait is a ceiling for
## that chain, not a timing claim: every check below still asserts content.
const WAIT_SECONDS := 12.0
const REPLAY_GRAPH := "res://composition/replay/zielinski_replay.json"
const REPLAY_SCENE := "res://scenes/replay3d.tscn"

const MORRIS := "morris2011.material_balance"
const ZIELINSKI := "zielinski2019.rhi_process"
const GANJAVE := "ganjave"
const BAEZ := "baez2014.oxygen_induced"

## The three values Ganjave declares as required with no default. Sourced from
## `composition/examples/ganjave_fed_batch.json`, which records the reasoning for
## each: X0 and S2 from the medium recipe, DO0 because the paper states none.
const GANJAVE_REQUIRED := {
	"initial_biomass_concentration": "0.05",
	"initial_complex_substrate_concentration": "5.0",
	"initial_dissolved_oxygen": "100.0",
}
## The optional feed recipe the same example documents. Optional at the contract
## level; without them the run has no feed to integrate.
const GANJAVE_OPTIONAL := {
	"feed_glycerol_concentration": "175.0",
	"feed_complex_substrate_concentration": "245.0",
	"feed_flow_rate": "0.72",
	"feed_start_time": "6.0",
}

var _failures: Array[String] = []
var _checks := 0
var _scene: Control = null
var _elapsed := 0.0


func _initialize() -> void:
	change_scene_to_file("res://scenes/composition.tscn")


func _process(delta: float) -> bool:
	_elapsed += delta
	if _scene == null and current_scene != null:
		_scene = current_scene as Control
	if _scene == null or _elapsed < WAIT_SECONDS:
		return _elapsed > 120.0
	_run_all()
	_report()
	return true


func _run_all() -> void:
	_check_palette_populates_from_the_registry()
	_check_the_three_registered_models_are_offered()
	_check_unregistered_models_are_absent()
	_check_selection_creates_a_graph_instance()
	_check_the_graph_carries_the_exact_reference()
	_check_configuration_is_contract_driven()
	_check_morris_runs_through_the_ui()
	_check_zielinski_runs_through_the_ui()
	_check_ganjave_runs_through_the_ui()
	_check_a_changed_input_changes_the_result()
	_check_failure_and_stale_result_handling()
	_check_the_permitted_connection_runs_through_the_ui()
	_check_a_refused_connection_is_refused_through_the_ui()
	_check_the_composition_report_reaches_the_ui()
	_check_a_modified_graph_cannot_show_a_previous_report_as_current()
	_check_the_report_panel_holds_no_rules_of_its_own()
	_check_the_zielinski_replay_is_preserved()
	_check_the_library_reports_the_engines_compatibility_position()
	_check_every_paper_has_an_entry_that_cannot_be_placed()


# --------------------------------------------------------------------------- #
# 1-3  the palette itself
# --------------------------------------------------------------------------- #


func _palette() -> ModelPalette:
	return _scene.get("_palette")


func _form() -> InstanceForm:
	return _scene.get("_form")


func _document() -> GraphDocument:
	return _scene.get("_document")


func _canvas() -> ProcessCanvas:
	return _scene.get("_canvas")


func _registry() -> ModelRegistry:
	return _scene.get("_registry")


## The palette's rows are derived from the registry and nothing else, so the two
## must agree exactly -- no more rows, no fewer, no ids the registry did not
## report.
func _check_palette_populates_from_the_registry() -> void:
	var palette := _palette()
	_ok(palette != null, "the main scene has no model palette")
	if palette == null:
		return
	var registry := _registry()
	var registry_ids := registry.model_ids()
	registry_ids.sort()
	var palette_ids := PackedStringArray()
	for entry in palette.model_entries():
		palette_ids.append(str(entry["model_id"]))
	_ok(palette_ids.size() == registry_ids.size(),
		"the palette shows %d models and the registry reported %d"
		% [palette_ids.size(), registry_ids.size()])
	for model_id in registry_ids:
		_ok(palette_ids.has(str(model_id)),
			"%s reached the registry but not the palette" % str(model_id))
	# One Add button per row, wired to that row's model.
	for model_id in palette_ids:
		var button := palette.add_button_for(model_id)
		_ok(button != null, "%s has no Add button" % model_id)
		_ok(button != null and not button.disabled,
			"the Add button for %s is disabled although the model is registered" % model_id)
	# A row shows the identifier and the version, not just a name.
	for entry in palette.model_entries():
		var reference := str(entry["reference"])
		_ok(reference == "%s@%s" % [entry["model_id"], entry["model_version"]],
			"%s shows an ambiguous reference %s" % [entry["model_id"], reference])
		_ok(not str(entry["display_name"]).is_empty(),
			"%s shows no name at all" % entry["model_id"])


func _check_the_three_registered_models_are_offered() -> void:
	var ids := PackedStringArray()
	for entry in _palette().model_entries():
		ids.append(str(entry["model_id"]))
	for expected in [MORRIS, ZIELINSKI, GANJAVE]:
		_ok(ids.has(expected), "%s is registered but is not in the palette" % expected)
	_ok(ids.size() == 3, "expected the three registered models, got %s" % str(ids))


## Baez is deliberately not registered with the composition layer, so it must not
## appear in the **registered** model list. If it did, something would have added
## a registration behind the scenes, and the exclusion decision would have been
## made twice.
##
## Baez is visible elsewhere in the panel: check 19 covers the ingested-paper
## corpus section, which lists every paper the project was given and gives none of
## them an Add button. The two lists are deliberately different -- this one is
## placeable, that one is evidence -- and these assertions are about this one.
func _check_unregistered_models_are_absent() -> void:
	var ids := PackedStringArray()
	for entry in _palette().model_entries():
		ids.append(str(entry["model_id"]))
	_ok(not ids.has(BAEZ), "the palette offered the unregistered Baez model")
	for model_id in ids:
		_ok(not str(model_id).to_lower().contains("baez"),
			"the palette offered something Baez-shaped: %s" % model_id)
	_ok(_palette().add_button_for(BAEZ) == null, "Baez has an Add button")


# --------------------------------------------------------------------------- #
# 4-5  selection creates a graph instance
# --------------------------------------------------------------------------- #


## Press the palette's own Add button, confirm through the form's own OK button.
## `fresh` starts a new graph first; pass false to add to the graph as it stands.
func _add_through_the_ui(model_id: String, fresh := true) -> bool:
	var palette := _palette()
	var form := _form()
	if fresh:
		_scene.call("_on_new_pressed")
	var before := _document().instances.size()
	palette.add_button_for(model_id).pressed.emit()
	if str(form.configuring()) != model_id:
		_ok(false, "pressing Add for %s did not open its form" % model_id)
		return false
	form.press_ok()
	_ok(_document().instances.size() == before + 1,
		"confirming the form for %s did not add an instance" % model_id)
	return true


## Add one model with whatever configuration its own contract demands, through
## the form, and return the instance id ("" on failure).
##
## Nothing here is a default the form supplied. Zielinski declares no required
## input, so it needs none. Ganjave declares three and also refuses to choose a
## run duration, so both are supplied here -- by this test, acting as the
## operator. Morris publishes no ports until it carries a control volume, so one
## is imported from a declaration the project already ships.
func _add_configured(model_id: String) -> String:
	_scene.call("_on_new_pressed")
	var form := _form()
	_palette().add_button_for(model_id).pressed.emit()
	match model_id:
		GANJAVE:
			for port_id in GANJAVE_REQUIRED.keys():
				form.set_input_value(str(port_id), GANJAVE_REQUIRED[port_id])
			for port_id in GANJAVE_OPTIONAL.keys():
				form.set_input_value(str(port_id), GANJAVE_OPTIONAL[port_id])
			# The model states that a duration is an input of the run and that
			# this adapter will not choose one, so the form offers no default.
			form.set_parameter(["simulation"], {})
			form.set_parameter(["simulation", "mode"], "fed_batch")
			form.set_parameter(["simulation", "duration_h"], 24.0)
		MORRIS:
			form.select_template(_morris_template_index())
	form.press_ok()
	if _document().instances.is_empty():
		return ""
	return str(_document().instances[0]["instance_id"])


func _morris_template_index() -> int:
	var captions := _form().template_captions()
	for index in captions.size():
		if str(captions[index]).contains("brass_batch_chain"):
			return index
	return 0


func _check_selection_creates_a_graph_instance() -> void:
	# Zielinski declares no required input, so this check is about the palette
	# wiring alone: press Add, confirm, and the instance exists.
	if not _add_through_the_ui(ZIELINSKI):
		return
	var instances := _document().instances
	var inst: Dictionary = instances[instances.size() - 1]
	_ok(str(inst.get("instance_id", "")) != "", "the new instance has no id")
	_ok(str(inst.get("label", "")) != "", "the new instance has no label")
	# It is on the canvas, not only in the document.
	var canvas := _canvas()
	_ok(canvas.nodes.has(str(inst["instance_id"])),
		"the new instance was not drawn on the canvas")
	# It is selected, so the inspector shows it.
	_ok(str(_scene.get("_selected_instance")) == str(inst["instance_id"]),
		"the new instance was not selected")
	# A second add, without resetting the graph in between, gets a second,
	# distinct id.
	var first_id := str(inst["instance_id"])
	_add_through_the_ui(ZIELINSKI, false)
	_ok(_document().instances.size() == 2,
		"the second add did not add a second instance")
	_ok(str(_document().instances[_document().instances.size() - 1]["instance_id"]) != first_id,
		"two instances were given the same id")


## The graph must name the exact model and version the registry resolved. A bare
## id would be a different claim.
func _check_the_graph_carries_the_exact_reference() -> void:
	for model_id in [MORRIS, ZIELINSKI, GANJAVE]:
		var registry := _registry()
		var expected := registry.reference_for(model_id)
		_ok(expected != "" and not expected.ends_with("@"),
			"the registry resolved no version for %s" % model_id)
		var instance_id := _add_configured(model_id)
		_ok(instance_id != "", "%s could not be added and configured" % model_id)
		if instance_id == "":
			continue
		var inst: Dictionary = _document().find_instance(instance_id)
		_ok(str(inst.get("model_id", "")) == model_id,
			"the instance names %s, not %s" % [inst.get("model_id", "?"), model_id])
		_ok(str(inst.get("model_version", "")) == expected.get_slice("@", 1),
			"the instance carries version %s, not %s"
			% [inst.get("model_version", "?"), expected.get_slice("@", 1)])
	# An unregistered reference never becomes an instance, because the palette
	# has no row to press.
	_ok(_palette().add_button_for("no.such_model") == null,
		"an unregistered model has an Add button")


# --------------------------------------------------------------------------- #
# 6  contract-driven configuration
# --------------------------------------------------------------------------- #


## The form must ask for exactly what the manifest marks required, in the
## manifest's units, and refuse to add until they are answered.
func _check_configuration_is_contract_driven() -> void:
	var form := _form()
	var palette := _palette()
	_scene.call("_on_new_pressed")
	palette.add_button_for(GANJAVE).pressed.emit()

	var required := form.required_port_ids()
	_ok(required.size() == 3,
		"Ganjave declares 3 required inputs; the form asked for %d" % required.size())
	for port_id in GANJAVE_REQUIRED.keys():
		_ok(required.has(str(port_id)),
			"%s is required by the model and the form did not ask for it" % port_id)

	# Every required row carries the quantity and unit the model declared.
	for row in form.input_rows():
		if not bool(row.get("required", false)):
			continue
		var quantity := str(row.get("quantity", ""))
		_ok(quantity != "", "%s has no quantity" % row.get("port_id", "?"))
		_ok(_registry().canonical_quantity(quantity) != ModelRegistry.UNKNOWN_QUANTITY,
			"%s declares quantity %s, which this contract does not define"
			% [row.get("port_id", "?"), quantity])
		_ok(str(row.get("unit", "")) != "", "%s has no unit" % row.get("port_id", "?"))

	# Nothing is defaulted: with the required inputs blank the form blocks.
	_ok(not form.blocking_problems().is_empty(),
		"the form did not block an instance with no required input supplied")
	var before := _document().instances.size()
	form.press_ok()
	_ok(_document().instances.size() == before,
		"the form added an instance while required inputs were blank")

	# Supplying them clears the block and the values become literal inputs.
	for port_id in GANJAVE_REQUIRED.keys():
		_ok(form.set_input_value(str(port_id), GANJAVE_REQUIRED[port_id]),
			"%s could not be given a value" % port_id)
	_ok(form.blocking_problems().is_empty(),
		"the form still blocks after every required input was supplied: %s"
		% str(form.blocking_problems()))
	form.press_ok()
	_ok(_document().instances.size() == before + 1,
		"the form refused an instance whose required inputs were all supplied")

	var inst: Dictionary = _document().instances[_document().instances.size() - 1]
	var instance_id := str(inst["instance_id"])
	var literals: Dictionary = _document().literal_inputs
	for port_id in GANJAVE_REQUIRED.keys():
		var key := "%s/%s" % [instance_id, port_id]
		_ok(literals.has(key), "%s was typed but never reached the graph" % key)
		if literals.has(key):
			var record: Dictionary = literals[key]
			_ok(float(record.get("value", 0.0)) == float(GANJAVE_REQUIRED[port_id]),
				"%s reached the graph as %s, not as what was typed"
				% [key, str(record.get("value", "?"))])
			_ok(str(record.get("unit", "")) != "",
				"%s reached the graph with no unit" % key)
			_ok(str(record.get("source_ref", "")) != "",
				"%s reached the graph with no source_ref" % key)

	# An instance-parameterised model is blocked until it carries a declaration,
	# and the palette says why.
	_scene.call("_on_new_pressed")
	palette.add_button_for(MORRIS).pressed.emit()
	_ok(str(_registry().port_dependence_for(MORRIS)) == "instance",
		"Morris should be instance-parameterised")
	_ok(form.template_captions().size() > 1,
		"Morris offers no starting declaration; %d template(s)" % form.template_captions().size())
	_ok(not form.blocking_problems().is_empty(),
		"Morris was not blocked for having no control volume")


# --------------------------------------------------------------------------- #
# 7  execution and display, per model
# --------------------------------------------------------------------------- #


func _run() -> Dictionary:
	_scene.call("_on_run_pressed")
	var payload: Variant = _scene.get("_last_payload")
	return payload if payload is Dictionary else {}


func _output_of(payload: Dictionary, instance_id: String, port_id: String) -> Variant:
	for result in payload.get("results", []):
		if str(result.get("instance_id", "")) != instance_id:
			continue
		for output in result.get("outputs", []):
			var ref: Dictionary = output.get("ref", {})
			if str(ref.get("port_id", "")) == port_id:
				return (output.get("value", {}) as Dictionary).get("value")
	return null


## Morris declares no model-level ports, so it is added with a control volume
## taken from a declaration the project already ships, and is then run through
## the same Run button as everything else.
func _check_morris_runs_through_the_ui() -> void:
	var instance_id := _add_configured(MORRIS)
	_ok(instance_id != "", "the Morris instance was not added")
	if instance_id == "":
		return

	# Its ports came from the instance declaration, not from an invented set.
	var node: ModelNode = _canvas().nodes.get(instance_id, null)
	_ok(node != null, "the Morris instance is not on the canvas")
	if node != null:
		_ok(node.ports_source == "instance_parameterised",
			"Morris node drew its ports from %s" % node.ports_source)
		_ok(node.ports.size() > 0, "the Morris node drew no ports at all")

	var payload := _run()
	var status := str(payload.get("status", ""))
	_ok(status.begins_with("success"),
		"Morris did not run through the UI: status %s" % status)
	var results: Array = payload.get("results", [])
	_ok(results.size() == 1, "expected one executed instance, got %d" % results.size())
	if results.is_empty():
		return
	_ok(str(results[0].get("model_id", "")) == MORRIS,
		"the run executed %s, not Morris" % str(results[0].get("model_id", "")))
	var outputs: Array = results[0].get("outputs", [])
	_ok(outputs.size() > 0, "Morris produced no outputs")
	for output in outputs:
		var chain: Array = output.get("provenance_chain", [])
		_ok(not chain.is_empty(),
			"%s reached the results panel with no provenance" % str(output.get("ref", {}).get("port_id", "?")))
		break
	_ok(str(_scene.get("_results_are_current")) == "true",
		"the results were not marked current after a successful run")


## Zielinski declares no required input, so a zero-configuration instance is a
## legitimate one and must run on the terms the model declares for itself.
func _check_zielinski_runs_through_the_ui() -> void:
	_scene.call("_on_new_pressed")
	var form := _form()
	_palette().add_button_for(ZIELINSKI).pressed.emit()
	_ok(form.required_port_ids().is_empty(),
		"the Zielinski manifest marks no port required; the form asked for %d"
		% form.required_port_ids().size())
	_ok(form.blocking_problems().is_empty(),
		"a zero-configuration Zielinski instance is blocked: %s"
		% str(form.blocking_problems()))
	form.press_ok()
	_ok(_document().instances.size() == 1, "the Zielinski instance was not added")
	if _document().instances.is_empty():
		return
	var instance_id := str(_document().instances[0]["instance_id"])
	var node: ModelNode = _canvas().nodes.get(instance_id, null)
	_ok(node != null and node.ports.size() == 196,
		"the Zielinski node drew %s ports, expected 196"
		% ("none" if node == null else str(node.ports.size())))

	var payload := _run()
	var status := str(payload.get("status", ""))
	_ok(status.begins_with("success"), "Zielinski did not run: status %s" % status)
	var results: Array = payload.get("results", [])
	if results.is_empty():
		_ok(false, "Zielinski produced no executed instance")
		return
	var outputs: Array = results[0].get("outputs", [])
	_ok(outputs.size() == 196, "Zielinski produced %d outputs, expected 196" % outputs.size())
	# It must not have silently become a predictive run.
	var unresolved := 0
	for output in outputs:
		var value: Dictionary = output.get("value", {})
		if not bool(value.get("is_resolved", false)):
			unresolved += 1
	_ok(unresolved > 0,
		"a zero-configuration Zielinski run resolved everything, which means it "
		+ "was not the declared evidence replay")


func _add_ganjave_with_the_documented_recipe() -> String:
	return _add_configured(GANJAVE)


func _check_ganjave_runs_through_the_ui() -> void:
	var instance_id := _add_ganjave_with_the_documented_recipe()
	_ok(instance_id != "", "the Ganjave instance was not added")
	if instance_id == "":
		return
	var node: ModelNode = _canvas().nodes.get(instance_id, null)
	_ok(node != null and node.ports_source == "manifest",
		"the Ganjave node drew its ports from %s"
		% ("nothing" if node == null else node.ports_source))
	_ok(node != null and node.ports.size() == 15,
		"the Ganjave node drew %s ports, expected 15"
		% ("none" if node == null else str(node.ports.size())))

	var payload := _run()
	var status := str(payload.get("status", ""))
	_ok(status.begins_with("success"), "Ganjave did not run: status %s" % status)
	var results: Array = payload.get("results", [])
	if results.is_empty():
		_ok(false, "Ganjave produced no executed instance")
		return
	var outputs: Array = results[0].get("outputs", [])
	_ok(outputs.size() == 6, "Ganjave produced %d outputs, expected 6" % outputs.size())
	for port_id in ["biomass_concentration", "glycerol_concentration",
			"complex_substrate_concentration", "dissolved_oxygen",
			"culture_volume", "simulation_time"]:
		_ok(_output_of(payload, instance_id, port_id) != null,
			"%s is missing from the results" % port_id)
	# Trajectory, provenance and the model's own scientific status all survive.
	for output in outputs:
		var ref := str(output.get("ref", {}).get("port_id", "?"))
		var extra: Dictionary = (output.get("value", {}) as Dictionary).get("extra", {})
		if ref == "biomass_concentration":
			_ok(int((extra.get("trajectory", {}) as Dictionary).get("points", 0)) > 1,
				"the trajectory did not survive to the editor")
			var claim: Dictionary = extra.get("validation_claim", {})
			_ok(str(claim.get("reproduction_status", "")) == "not_yet_validated",
				"the result lost the model's own reproduction status")
			_ok(str(claim.get("implementation_status", "")) == "implemented",
				"the result lost the model's own implementation status")
		_ok(not (output.get("provenance_chain", []) as Array).is_empty(),
			"%s reached the results panel with no provenance" % ref)


# --------------------------------------------------------------------------- #
# 8  a changed input changes the result
# --------------------------------------------------------------------------- #


## The strongest evidence that the pipeline is live: the same graph, built
## through the same UI, with one declared input changed.
func _check_a_changed_input_changes_the_result() -> void:
	var instance_id := _add_ganjave_with_the_documented_recipe()
	if instance_id == "":
		_ok(false, "could not add a Ganjave instance for the perturbation check")
		return
	var first := _run()
	var baseline: Variant = _output_of(first, instance_id, "biomass_concentration")
	_ok(baseline != null, "the baseline run published no biomass concentration")
	_ok(float(first.get("error_count", 1)) == 0.0,
		"the baseline run reported %s error(s)" % str(first.get("error_count", "?")))

	# Change one declared input, through the document the form wrote to.
	var key := "%s/initial_biomass_concentration" % instance_id
	_ok(_document().literal_inputs.has(key), "the declared input is not on the graph")
	var record: Dictionary = (_document().literal_inputs[key] as Dictionary).duplicate(true)
	record["value"] = 0.5
	_document().set_literal(instance_id, "initial_biomass_concentration", record)
	_ok(_document().literal_inputs[key]["value"] == 0.5,
		"the changed input did not reach the graph document")

	var second := _run()
	var changed: Variant = _output_of(second, instance_id, "biomass_concentration")
	_ok(changed != null, "the perturbed run published no biomass concentration")
	_ok(baseline is float or baseline is int,
		"the baseline biomass is not a number: %s" % str(baseline))
	_ok(changed != baseline,
		"changing initial biomass 0.05 -> 0.5 g/L left biomass_concentration at %s; "
		% str(baseline)
		+ "the run is not reading the declared input")
	_ok(float(second.get("error_count", 1)) == 0.0,
		"the perturbed run reported %s error(s)" % str(second.get("error_count", "?")))


# --------------------------------------------------------------------------- #
# 9  failure handling and stale results
# --------------------------------------------------------------------------- #


func _check_failure_and_stale_result_handling() -> void:
	# A good run first, so there is something that could go stale.
	var instance_id := _add_ganjave_with_the_documented_recipe()
	var good := _run()
	_ok(str(good.get("status", "")).begins_with("success"), "the setup run did not succeed")
	_ok(str(_scene.get("_results_are_current")) == "true",
		"a successful run did not mark its results current")

	# Editing the graph invalidates them: a result of a graph the user has since
	# changed must not still be on screen as if it were current.
	_scene.call("_on_instance_selected", instance_id)
	_document().remove_instance(instance_id)
	_canvas().build_from_document()
	_scene.call("_invalidate_results", "an instance was removed")
	_ok(str(_scene.get("_results_are_current")) == "false",
		"results stayed current after the graph changed")
	_ok(_document().instances.is_empty(), "the instance was not removed")

	# A declared input removed from the graph is refused, and the refusal is not
	# a success. This is the engine's rule, reached through the document the form
	# wrote to -- not a check the UI performs.
	var broken := _add_ganjave_with_the_documented_recipe()
	_document().literal_inputs.erase("%s/initial_biomass_concentration" % broken)
	var refused := _run()
	_ok(not str(refused.get("status", "")).begins_with("success"),
		"a run with a required input removed reported %s"
		% str(refused.get("status", "?")))
	_ok(int(refused.get("error_count", 0)) > 0,
		"a run with a required input removed reported no error diagnostic")
	_ok((refused.get("diagnostics", []) as Array).size() > 0,
		"a refused run came back with no diagnostic explaining why")
	var named := false
	for diagnostic in refused.get("diagnostics", []):
		if str(diagnostic.get("message", "")).contains("initial_biomass_concentration"):
			named = true
	_ok(named, "the refusal does not name the input that was missing")

	# A shape error never reaches the runner at all, and never reports success.
	_scene.call("_on_new_pressed")
	var malformed: Dictionary = _document().add_instance(GANJAVE, "0.1.0", "broken", "", Vector2.ZERO, {})
	malformed.erase("parameters")
	_document().instances[_document().instances.size() - 1] = malformed
	var shape := _run()
	_ok(str(shape.get("status", "")) == "invalid",
		"a malformed instance did not stop at shape validation")
	_ok(int(shape.get("error_count", 0)) > 0, "a shape error reported no error")


# --------------------------------------------------------------------------- #
# cross-model boundaries
# --------------------------------------------------------------------------- #


## The one boundary the scientific sources support, reached the ordinary way:
## the user picks an example from the dropdown and presses Run.
func _check_the_permitted_connection_runs_through_the_ui() -> void:
	_scene.call("_on_new_pressed")
	_load_example_through_the_picker("brass_batch_chain")
	_ok(_document().connections.size() == 3,
		"the permitted boundary's graph carries %d connection(s), expected 3"
		% _document().connections.size())
	_ok(_document().instances.size() == 3,
		"the permitted boundary's graph carries %d instance(s), expected 3"
		% _document().instances.size())

	var payload := _run()
	_ok(str(payload.get("status", "")).begins_with("success"),
		"the permitted boundary did not run: %s" % str(payload.get("status", "?")))

	# The connection has to be visible on the canvas, not only in the document.
	_ok(_canvas().connections.size() == 3,
		"the connections were not drawn on the canvas")

	# And a forwarded quantity must still name where it came from.
	var alloy := ""
	for result in payload.get("results", []):
		if str(result.get("instance_id", "")) == "brass_alloying":
			alloy = str(result.get("instance_id", ""))
	_ok(alloy != "", "the downstream control volume did not run")
	var chain: Array = []
	for result in payload.get("results", []):
		if str(result.get("instance_id", "")) != "brass_alloying":
			continue
		for output in result.get("outputs", []):
			if str(output.get("ref", {}).get("port_id", "")) == "out:A:w:Cu":
				chain = output.get("provenance_chain", [])
	_ok(chain.size() == 3,
		"a quantity forwarded through an instance carries %d provenance record(s); "
		% chain.size()
		+ "it should name the upstream instance, the connection and this solve")
	if chain.size() == 3:
		_ok(str(chain[0].get("where", "")) == "instance:brass_charge",
			"the forwarded quantity does not name the instance it came from")
		_ok(str(chain[1].get("connection_id", "")) == "c2",
			"the forwarded quantity does not name the connection it crossed")
		_ok(str(chain[2].get("where", "")) == "instance:brass_alloying",
			"the forwarded quantity does not name the instance that solved it")


## A connection that is dimensionally legal and scientifically unsupported must be
## refused in the application, with the reason on screen, before anything runs.
func _check_a_refused_connection_is_refused_through_the_ui() -> void:
	for example in ["rejected_cross_model_dcw", "rejected_cross_model_fraction_volume"]:
		_scene.call("_on_new_pressed")
		_load_example_through_the_picker(example)
		_ok(_document().connections.size() == 1,
			"%s carries %d connection(s), expected 1"
			% [example, _document().connections.size()])
		var payload := _run()
		var status := str(payload.get("status", ""))
		_ok(status == "invalid",
			"%s reported %s; a scientifically unsupported connection must be "
			% [example, status]
			+ "refused before execution, not executed and quietly ignored")
		_ok((payload.get("results", []) as Array).is_empty(),
			"%s executed an instance despite the refused connection" % example)

		var named := false
		for diagnostic in payload.get("diagnostics", []):
			if str(diagnostic.get("code", "")) == "connection.cross_model_refused":
				named = true
				_ok(str(diagnostic.get("severity", "")) == "error",
					"%s: the refusal is not an error severity" % example)
				_ok(str(diagnostic.get("message", "")).contains("scientifically unsupported"),
					"%s: the refusal does not say why" % example)
				_ok(not str(diagnostic.get("remediation", "")).is_empty(),
					"%s: the refusal does not say what to do instead" % example)
				var evidence: Array = (diagnostic.get("detail", {}) as Dictionary).get("evidence", [])
				_ok(evidence.size() >= 2,
					"%s: the refusal carries no evidence" % example)
		_ok(named, "%s produced no connection.cross_model_refused diagnostic" % example)


# --------------------------------------------------------------------------- #
# the composition report, reached the ordinary way
# --------------------------------------------------------------------------- #


func _report_panel() -> CompositionReportPanel:
	var panel: Variant = _scene.get("_report")
	return panel as CompositionReportPanel


func _panel_text(panel: CompositionReportPanel) -> String:
	var out: Array[String] = []
	_collect_text(panel, out)
	return "\n".join(out)


func _collect_text(from: Node, into: Array[String]) -> void:
	for child in from.get_children():
		if child is Label or child is Button:
			into.append(str((child as Label).text))
		_collect_text(child, into)


## The whole point of the feature, checked through the UI rather than the JSON:
## a user must be able to load a graph, press Run, and read why each connection
## stands where it does -- for a graph that ran and for one that did not.
func _check_the_composition_report_reaches_the_ui() -> void:
	var panel := _report_panel()
	_ok(panel != null, "the main scene has no composition report panel")
	if panel == null:
		return
	_ok(not panel.is_stale(), "a fresh panel is already marked stale")

	# --- the graph that runs -------------------------------------------------
	_scene.call("_on_new_pressed")
	_load_example_through_the_picker("brass_batch_chain")
	var permitted := _run()
	var report: Dictionary = permitted.get("composition_report", {})
	_ok(not report.is_empty(), "a successful run published no composition report")

	var execution: Dictionary = report.get("execution", {})
	_ok(bool(execution.get("results_produced", false)),
		"the report does not record that results were produced")
	_ok(not bool(execution.get("results_invalidated", true)),
		"a fresh report is marked invalidated")

	var connections: Array = report.get("connections", [])
	_ok(connections.size() == 3,
		"the report assessed %d of 3 connection(s)" % connections.size())
	for row in connections:
		_ok(str(row.get("disposition", "")) == "permitted",
			"a permitted connection is reported as %s" % str(row.get("disposition", "?")))
		# The four questions stay apart, so a clean run is never read as
		# scientific backing.
		_ok(str((row.get("dimensional", {}) as Dictionary).get("result", "")) == "compatible",
			"a permitted connection is not reported dimensionally compatible")

	var combined: Dictionary = (report.get("science", {}) as Dictionary).get("combined_graph", {})
	_ok(not bool(combined.get("independently_validated", true)),
		"the report claims the combined graph is independently validated")
	_ok(str(combined.get("status", "")) == "not_established",
		"the combined graph's status is not 'not_established'")

	var text := _panel_text(panel)
	_ok(text.contains("permitted"),
		"the Report tab does not show the permitted disposition on screen")
	_ok(text.contains("not established") or text.contains("not_established"),
		"the Report tab does not show the combined graph's scientific status")
	_ok(text.contains("Connections (3)"),
		"the Report tab does not show a heading per connection group")

	# --- the graph that is refused ------------------------------------------
	_scene.call("_on_new_pressed")
	_load_example_through_the_picker("rejected_cross_model_dcw")
	var refused := _run()
	var refused_report: Dictionary = refused.get("composition_report", {})
	_ok(not refused_report.is_empty(),
		"a refused graph published no composition report")

	var refused_execution: Dictionary = refused_report.get("execution", {})
	_ok(not bool(refused_execution.get("results_produced", true)),
		"the report claims a refused graph produced results")
	_ok((refused.get("results", []) as Array).is_empty(),
		"a refused graph executed a model")

	var rows: Array = refused_report.get("connections", [])
	_ok(rows.size() == 1, "the refused graph's report assessed %d connection(s)" % rows.size())
	if rows.size() == 1:
		var row: Dictionary = rows[0]
		_ok(str(row.get("disposition", "")) == "scientifically_refused",
			"the dry-to-wet connection is reported as %s" % str(row.get("disposition", "?")))
		# Dimensionally compatible AND semantically refused is the whole
		# hazard: both halves have to be visible or the reason is invisible.
		_ok(str((row.get("dimensional", {}) as Dictionary).get("result", "")) == "compatible",
			"the refused connection is not reported as dimensionally compatible")
		_ok(str((row.get("semantic", {}) as Dictionary).get("result", "")) == "refused",
			"the refused connection is not reported semantically refused")
		_ok(str((row.get("semantic", {}) as Dictionary).get("rule", "")) == "composition.cross_model",
			"the refusal does not name the rule that produced it")
		_ok(((row.get("evidence", []) as Array)).size() >= 2,
			"the refusal reaches the UI with no evidence attached")
		_ok(not ((row.get("unresolved", []) as Array)).is_empty(),
			"the refusal reaches the UI with no unresolved question attached")

	var refused_text := _panel_text(panel)
	_ok(refused_text.contains("SCIENTIFICALLY REFUSED"),
		"the Report tab does not show the refusal in words")
	_ok(refused_text.contains("composition.cross_model"),
		"the Report tab does not name the rule on screen")
	_ok(refused_text.contains("Evidence"),
		"the Report tab does not show the evidence section")

	# A refused graph still needs its refusal to reach the ordinary
	# diagnostics panel, not only the report.
	var named := false
	for diagnostic in refused.get("diagnostics", []):
		if str(diagnostic.get("code", "")) == "connection.cross_model_refused":
			named = true
	_ok(named, "the refusal never reached the runner's diagnostics")


## A report that ran against an earlier graph must not be presented as a report
## about the graph now on screen.
func _check_a_modified_graph_cannot_show_a_previous_report_as_current() -> void:
	_scene.call("_on_new_pressed")
	_load_example_through_the_picker("brass_batch_chain")
	var payload := _run()
	_ok(str(payload.get("status", "")).begins_with("success"),
		"the staleness check needs a graph that ran first")

	var panel := _report_panel()
	_ok(panel != null and not panel.is_stale(),
		"the report is already stale before the graph was touched")
	_ok(bool(_scene.get("_results_are_current")),
		"a run that just finished is not marked current")

	# The ordinary way a graph changes: the operator adds to the graph that is
	# already on screen, through the palette. Reloading an example would be a
	# different graph, and a cleared report would be the right answer for that.
	# `_add_configured` cannot be used here because it starts a new graph first.
	var before: int = _document().instances.size()
	var form := _form()
	_palette().add_button_for(MORRIS).pressed.emit()
	form.select_template(_morris_template_index())
	form.press_ok()
	_ok(_document().instances.size() > before,
		"the staleness check could not add an instance to the graph")

	_ok(not bool(_scene.get("_results_are_current")),
		"editing the graph did not clear the previous run")
	_ok(panel != null and panel.is_stale(),
		"editing the graph did not mark the previous report stale")
	var text := _panel_text(panel)
	_ok(text.contains("STALE"),
		"a stale report does not say so on screen: %s" % text.substr(0, 120))


## The panel renders the runner's verdict; it must not accumulate a second copy
## of the policy. A model id or a quantity pair hard-coded here would be a rule
## that could drift from `cross_model.py` without anyone noticing.
func _check_the_report_panel_holds_no_rules_of_its_own() -> void:
	var source := FileAccess.get_file_as_string("res://scripts/composition_report_panel.gd")
	_ok(source.length() > 0, "the report panel source could not be read")
	for model_id in [MORRIS, ZIELINSKI, GANJAVE]:
		_ok(not source.contains(model_id),
			"the report panel names %s, so it carries its own model list" % model_id)
	for pair in ["mass_concentration", "volume_flow", "node:N0"]:
		_ok(not source.contains(pair),
			"the report panel names the quantity '%s', so it carries its own rule table" % pair)
	# It may know the schema it renders -- that is a version, not a rule.
	_ok(source.contains("composition-report/1"),
		"the report panel does not declare the schema it renders")


func _load_example_through_the_picker(title: String) -> void:
	var picker: OptionButton = _find_named(_scene, "ExamplePicker")
	if picker == null:
		_ok(false, "the main scene has no ExamplePicker")
		return
	for index in picker.item_count:
		if picker.get_item_text(index) == title:
			picker.selected = index
			picker.item_selected.emit(index)
			return
	_ok(false, "the example picker does not offer %s" % title)


func _find_named(from: Node, wanted: String) -> OptionButton:
	if from is OptionButton and String(from.name) == wanted:
		return from
	for child in from.get_children():
		var found := _find_named(child, wanted)
		if found != null:
			return found
	return null


# --------------------------------------------------------------------------- #
# 10  the Zielinski replay is untouched
# --------------------------------------------------------------------------- #


## The replay is a separate, predefined experiment and must stay separate and
## honestly labelled. It is not a general simulation and is not the way to reach
## a model.
func _check_the_zielinski_replay_is_preserved() -> void:
	_ok(ResourceLoader.exists(REPLAY_SCENE), "the replay scene is gone: %s" % REPLAY_SCENE)
	_ok(FileAccess.file_exists(REPLAY_GRAPH), "the replay graph is gone: %s" % REPLAY_GRAPH)

	var source := FileAccess.get_file_as_string("res://scripts/replay3d.gd").to_lower()
	_ok(source.contains("res://composition/replay/zielinski_replay.json"),
		"the replay scene no longer names its graph")
	_ok(source.contains("evidence replay"),
		"the replay scene no longer states that it is an evidence replay")
	_ok(source.contains("not a simulator") or source.contains("not a simulation"),
		"the replay scene no longer disclaims simulation")

	# The toolbar button still opens it, and still says what it is.
	var found := false
	for node in _find_buttons(_scene):
		if str(node.text) == "Zieliński replay":
			found = true
			var tip := str(node.tooltip_text).to_lower()
			_ok(tip.contains("predefined"), "the replay button does not say it is predefined")
			_ok(tip.contains("digitized"), "the replay button does not mention digitised data")
			_ok(not tip.contains("simulate"), "the replay button implies simulation")
	_ok(found, "the Zielinski replay button is gone from the toolbar")

	# And the replay's own graph still runs through the composition runner.
	var runner := CompositionRunner.new("python", ProjectSettings.globalize_path("res://composition"))
	var result_path := "user://palette_graph_run_replay.json"
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


# --------------------------------------------------------------------------- #
# 18  the compatibility column in the model library
#
# The palette must report the engine's position, not one of its own. These
# checks read the same payload the window asked the runner for and compare the
# rows against it. Nothing here claims that any model is scientifically valid,
# and no quantity pair is re-derived -- a state that is wrong is wrong in
# `ModelRegistry.integration_status()`, and these checks would see it there.
# --------------------------------------------------------------------------- #


func _check_the_library_reports_the_engines_compatibility_position() -> void:
	var registry := _registry()
	var palette := _palette()
	_ok(registry != null, "the main scene has no model registry")
	_ok(palette != null, "the main scene has no model palette")
	if registry == null or palette == null:
		return

	# 1. The engine was actually consulted. A palette that painted a verdict
	#    without asking would be asserting something `cross_model.py` owns.
	_ok(registry.compatibility_loaded(),
		"the editor never asked the compatibility engine for its position")
	if not registry.compatibility_loaded():
		return
	var scope := registry.connection_scope()
	_ok(int(scope.get("boundary_count", 0)) > 0,
		"the compatibility engine reported no ordered model pairs at all")
	_ok(str(scope.get("claim_scope", "")) != "",
		"the compatibility position arrived without the scope it claims to cover")
	_ok(str(scope.get("validation_status", "")) != "",
		"the compatibility position arrived without its validation status")

	# 2. Every registered model carries a decided state -- not the "unknown"
	#    sentinel that means the question was never put to the engine.
	var states := [
		ModelRegistry.INTEGRATION_INTEGRATE,
		ModelRegistry.INTEGRATION_INCOMPATIBLE,
		ModelRegistry.INTEGRATION_NOT_EVALUABLE,
		ModelRegistry.INTEGRATION_NOT_EVALUATED,
	]
	for entry in palette.model_entries():
		var model_id := str(entry.get("model_id", "?"))
		var integration: Dictionary = entry.get("integration", {})
		_ok(not integration.is_empty(),
			"%s has no compatibility record in the library" % model_id)
		var state := str(integration.get("state", ""))
		_ok(state != ModelRegistry.INTEGRATION_UNKNOWN,
			"%s is reported as never evaluated although the engine answered" % model_id)
		_ok(states.has(state),
			"%s reported an unrecognised compatibility state %s" % [model_id, state])
		_ok(str(integration.get("source", "")) == "composition.cross_model.describe",
			"%s credits its compatibility position to something other than the engine" % model_id)

	# 3. The row says it where a reader can see it, and the sentence is the
	#    engine's own rather than a phrase the palette composed.
	for model_id in [MORRIS, ZIELINSKI, GANJAVE]:
		var row := palette.row_for(model_id)
		_ok(row != null, "%s has no palette row" % model_id)
		if row == null:
			continue
		var label := row.find_child("IntegrationLabel", true, false) as Label
		_ok(label != null, "%s has no compatibility line in its row" % model_id)
		if label == null:
			continue
		_ok(label.text.begins_with("compatibility:"),
			"%s does not label its compatibility line: %s" % [model_id, label.text])
		var status := palette.status_for(model_id)
		_ok(label.text.contains(str(status.get("label", ""))),
			"%s shows a compatibility label the engine did not give it" % model_id)
		_ok(str(status.get("basis", "")) != "",
			"%s was given a state with no evidence basis behind it" % model_id)
		if str(status.get("basis", "")) != "":
			_ok(label.tooltip_text.contains(str(status.get("basis", ""))),
				"%s hides the engine's evidence basis from the reader" % model_id)

	# 4. Narrowing to the graph's models filters the engine's pairs; it does not
	#    invent one. Two models the engine refuses both ways, asked about each
	#    other, come back refused and name only that counterpart.
	var narrowed := registry.integration_status(GANJAVE, [ZIELINSKI])
	_ok(str(narrowed.get("state", "")) == ModelRegistry.INTEGRATION_INCOMPATIBLE,
		"asking about Ganjave against Zielinski did not report the engine's refusal")
	_ok(int(narrowed.get("permitted_count", 0)) == 0,
		"a narrowed question reported a permitted pair the engine did not")
	_ok((narrowed.get("refused_pairs", []) as Array).size() == 2,
		"a narrowed question examined %d direction(s) instead of both"
		% (narrowed.get("refused_pairs", []) as Array).size())
	for pair in narrowed.get("refused_pairs", []):
		_ok(str(pair.get("counterpart", "")) == ZIELINSKI,
			"a narrowed question reported a pair with %s, which is not in the graph"
			% str(pair.get("counterpart", "?")))
		_ok(str(pair.get("reason", "")) != "",
			"a refused pair arrived without the engine's reason")
		_ok(not bool(pair.get("permitted", true)),
			"a refusal was recorded with permitted set")

	# 5. A model the engine said nothing about is "not evaluated", never
	#    "compatible". This is the mapping's own claim, checked on a reference no
	#    boundary can name.
	var absent := registry.integration_status("no-such-model", [])
	_ok(str(absent.get("state", "")) == ModelRegistry.INTEGRATION_NOT_EVALUATED,
		"a model the engine never classified was reported as %s"
		% str(absent.get("state", "")))
	_ok(int(absent.get("permitted_count", 0)) == 0,
		"a model the engine never classified was reported as permitted")

	# 6. Same-model boundaries stay separate. Ganjave's cascade is recorded, and
	#    the library does not present it as compatibility with another model.
	var ganjave := registry.integration_status(GANJAVE, [])
	_ok((ganjave.get("own_model_pairs", []) as Array).size() == 1,
		"Ganjave's same-model cascade is not recorded as one same-model boundary")
	_ok(str(ganjave.get("state", "")) != ModelRegistry.INTEGRATION_INTEGRATE,
		"Ganjave's same-model cascade was reported as compatibility with another model")

	# 7. The library states what the position covers. The engine classifies
	#    registered models, so an artefact it does not register produces no
	#    boundary at all -- and its absence from this list must not read as a
	#    verdict. Checked here because the more tempting fix (list it anyway)
	#    is what `_check_unregistered_models_are_absent` forbids.
	var scope_label := palette.find_child("ScopeLabel", true, false) as Label
	_ok(scope_label != null, "the library has no statement of what it covers")
	if scope_label != null:
		_ok(scope_label.visible,
			"the library does not say that its verdicts cover registered models only")
		_ok(scope_label.text.contains("registered"),
			"the scope statement does not say it covers registered models: %s" % scope_label.text)
		_ok(not scope_label.text.to_lower().contains("baez"),
			"the scope statement names an unregistered artefact instead of pointing at the registry")
		_ok(scope_label.tooltip_text.contains(str(scope.get("claim_scope", ""))),
			"the scope statement drops the engine's own claim scope")


# --------------------------------------------------------------------------- #
# 19  the ingested-paper corpus
#
# Every paper under `Models/` must be visible in the library, must name its
# source, must say whether it can execute, and must NOT be placeable. The two
# halves are deliberately different lists: `model_entries()` is the registered,
# placeable set and this section is everything else the project was given.
#
# This harness cannot see the filesystem, so "no paper is silently omitted" is
# enforced on the Python side by `python -m composition.evidence.papers --check`,
# which fails when a corpus folder has no record. What is checked here is that
# whatever the index reported reached the screen intact, and that none of it
# became a component.
# --------------------------------------------------------------------------- #


func _check_every_paper_has_an_entry_that_cannot_be_placed() -> void:
	var registry := _registry()
	var palette := _palette()
	if registry == null or palette == null:
		return

	# 1. The corpus index was actually read, and it reported something.
	_ok(registry.papers_received(),
		"the editor never read the ingested-paper corpus index")
	if not registry.papers_received():
		return
	var entries: Array = palette.paper_entries()
	_ok(entries.size() > 0, "the corpus index produced no visible paper entries")
	_ok(entries.size() == registry.paper_count(),
		"%d paper(s) reached the panel out of %d the index reported"
		% [entries.size(), registry.paper_count()])

	# 2. Every entry names its source and states both statuses.
	var folders := PackedStringArray()
	for entry in entries:
		var folder := str(entry.get("folder", ""))
		folders.append(folder)
		_ok(folder != "", "a paper entry has no folder")
		_ok(str(entry.get("citation", "")).strip_edges() != "",
			"%s does not name the paper it comes from" % folder)
		_ok(str(entry.get("determination", "")) != "",
			"%s carries no determination from the corpus index" % folder)
		_ok(str(entry.get("reason", "")).strip_edges() != "",
			"%s states no reason, so it cannot be reviewed" % folder)
		var execution: Dictionary = entry.get("execution", {})
		_ok(str(execution.get("label", "")) != "" and str(execution.get("detail", "")) != "",
			"%s does not state whether it can execute" % folder)
		var integration: Dictionary = entry.get("integration", {})
		_ok(str(integration.get("label", "")) != "",
			"%s states no integration status" % folder)

	# 3. No entry is placeable: no Add button anywhere in the corpus section, and
	#    no paper folder appears in the registered model list.
	for entry in entries:
		var folder := str(entry.get("folder", "?"))
		var card := palette.paper_row_for(folder)
		_ok(card != null, "%s has no row in the corpus section" % folder)
		if card == null:
			continue
		_ok(card.find_child("AddButton", true, false) == null,
			"%s offers an Add button; an evidence-only paper must not be placeable" % folder)
	var registered_ids := PackedStringArray()
	for entry in palette.model_entries():
		registered_ids.append(str(entry.get("model_id", "")))
	for folder in folders:
		_ok(not registered_ids.has(folder),
			"a paper folder %s leaked into the placeable model list" % folder)

	# 4. Each registered model is linked to the paper that encodes it, and that
	#    entry says it is executable.
	for model_id in [MORRIS, ZIELINSKI, GANJAVE]:
		var paper := registry.paper_for_model(model_id)
		_ok(not paper.is_empty(), "%s is registered but no corpus entry names it" % model_id)
		if paper.is_empty():
			continue
		var row := registry.paper_row(paper)
		_ok(str((row.get("execution", {}) as Dictionary).get("state", "")) == "executable",
			"%s is registered but its paper entry does not say it can execute" % model_id)
		_ok(str((row.get("integration", {}) as Dictionary).get("source", ""))
			== "composition.cross_model.describe",
			"%s credits its integration status to something other than the engine" % model_id)

	# 5. A paper with no registered model gets no compatibility claim. The engine
	#    classifies registered models; saying more here would be inventing one.
	var unregistered := 0
	for entry in entries:
		if str(entry.get("model_id", "")) != "":
			continue
		unregistered += 1
		var folder := str(entry.get("folder", "?"))
		var integration: Dictionary = entry.get("integration", {})
		_ok(str(integration.get("state", "")) == ModelRegistry.INTEGRATION_NOT_EVALUATED,
			"%s was given a compatibility state although no engine position exists" % folder)
		_ok(str((entry.get("execution", {}) as Dictionary).get("state", "")) != "executable",
			"%s has no registered model but claims to be executable" % folder)
	_ok(unregistered > 0,
		"every paper in the corpus has a registered model, so the evidence-only path is untested")

	# 6. The determinations the panel shows are the index's own tally, not a
	#    count this panel made up.
	var counts := registry.paper_counts()
	var total := 0
	for key in counts.keys():
		total += int(counts[key])
	_ok(total == entries.size(),
		"the index's own tally covers %d paper(s), the panel shows %d" % [total, entries.size()])


func _find_buttons(from: Node) -> Array:
	var out: Array = []
	for child in from.get_children():
		if child is Button:
			out.append(child)
		out.append_array(_find_buttons(child))
	return out


# --------------------------------------------------------------------------- #


func _ok(condition: bool, what: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(what)


func _report() -> void:
	if _failures.is_empty():
		print("palette-graph-run: %d checks passed" % _checks)
		quit(0)
		return
	for failure in _failures:
		print("FAIL  " + failure.substr(0, 400))
	print("palette-graph-run: %d checks, %d FAILED" % [_checks, _failures.size()])
	quit(1)
