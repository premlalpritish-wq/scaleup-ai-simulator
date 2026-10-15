class_name ModelRegistry
extends Node
## Describes the models this composition can place, read from the models
## themselves rather than hard-coded here.
##
## The registry asks the Python runner for its model list, then fetches each
## model's manifest. Ports, quantities, units, assumptions and provenance
## requirements all come from those manifests, so the canvas and the inspector
## can only ever offer a port a model actually declares.

signal models_loaded(models: Array[Dictionary])
signal load_failed(message: String)

var models: Array[Dictionary] = []
var _by_id: Dictionary = {}
var _runner: CompositionRunner = null


func setup(runner: CompositionRunner) -> void:
	_runner = runner
	runner.finished.connect(_on_runner_finished)


func load() -> void:
	# list_models emits `finished` with the model list as its payload; the main
	# window also listens, so both the registry and the UI stay in sync.
	_pending_list_request = true
	_runner.list_models()


var _pending_list_request := false


func _on_runner_finished(payload: Dictionary) -> void:
	if _pending_list_request:
		_pending_list_request = false
		_on_list_models(payload)


func _on_list_models(payload: Dictionary) -> void:
	var entries: Array = payload.get("models", [])
	if entries.is_empty():
		emit_signal("load_failed", "The runner reported no available models. Check that the Models/ directory is intact.")
		return
	models = entries
	for entry in models:
		_by_id[entry["model_id"]] = entry
	emit_signal("models_loaded", models)


func model_ids() -> Array:
	return _by_id.keys()


func is_available(model_id: String) -> bool:
	var entry = _by_id.get(model_id)
	return bool(entry and entry.get("available", false))


func label_for(model_id: String) -> String:
	var entry = _by_id.get(model_id)
	return str(entry.get("label", model_id)) if entry else model_id


## Quantity registry, for the unit dropdown and the colour legend.
func quantities() -> Array:
	return [
		{"name": "mass", "label": "mass", "colour": Color(0.45, 0.62, 0.95)},
		{"name": "mass_flow", "label": "mass flow", "colour": Color(0.40, 0.80, 0.72)},
		{"name": "mass_fraction", "label": "mass fraction", "colour": Color(0.92, 0.55, 0.62)},
		{"name": "amount", "label": "amount", "colour": Color(0.86, 0.72, 0.42)},
		{"name": "amount_flow", "label": "amount flow", "colour": Color(0.78, 0.66, 0.46)},
		{"name": "volume", "label": "volume", "colour": Color(0.62, 0.88, 0.66)},
		{"name": "volume_flow", "label": "volume flow", "colour": Color(0.56, 0.78, 0.70)},
		{"name": "time", "label": "time", "colour": Color(0.80, 0.80, 0.80)},
		{"name": "absorbance", "label": "absorbance", "colour": Color(0.72, 0.62, 0.92)},
		{"name": "dimensionless", "label": "dimensionless", "colour": Color(0.68, 0.68, 0.68)},
		{"name": "molar_concentration", "label": "molarity", "colour": Color(0.58, 0.84, 0.86)},
		{"name": "activity", "label": "activity", "colour": Color(0.90, 0.70, 0.50)},
		{"name": "ph", "label": "pH", "colour": Color(0.50, 0.72, 0.80)},
		{"name": "other", "label": "other", "colour": Color(0.55, 0.55, 0.55)},
	]


func colour_for(quantity: String) -> Color:
	for q in quantities():
		if str(q["name"]) == quantity:
			return q["colour"]
	return Color(0.55, 0.55, 0.55)


func direction_label(direction: String) -> String:
	return "input" if direction == "input" else "output"
