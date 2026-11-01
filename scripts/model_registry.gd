class_name ModelRegistry
extends Node
## Describes the models this composition can place, read from the models
## themselves rather than hard-coded here.
##
## Everything this class knows comes from the Python composition layer:
##
##   * `--list-models`      which model ids and versions exist, and whether the
##                          package behind each one is reachable;
##   * `--describe-model`   one model's manifest -- its ports, its parameter
##                          sections, its declared capabilities;
##   * `--describe-contract` the quantity and unit registry, which is the only
##                          place a quantity or a unit is allowed to come from.
##
## Nothing here infers a port from a display name, and nothing here decides
## which quantities are compatible. A model that publishes no manifest is
## reported as *instance-parameterised*, which is not the same as publishing no
## ports, and it is never filled in on the model's behalf.

signal models_loaded(models: Array[Dictionary])
signal load_failed(message: String)
signal manifest_loaded(model_id: String, manifest: Dictionary)
signal manifest_failed(model_id: String, message: String)
## Emitted when `accept_connections()` has taken a `--describe-connections`
## payload. The payload itself is not re-emitted: a listener asks
## `integration_status()` for the question it actually has.
signal connections_loaded(connections: Dictionary)
## Emitted when `accept_papers()` has taken a `--describe-papers` payload: the
## ingested-paper corpus index, which is not a model list.
signal papers_loaded(papers: Dictionary)

## Sentinels so an unavailable registry answers "I don't know" rather than "".
const UNKNOWN_QUANTITY := "unknown"
const UNKNOWN_COLOUR := Color(0.55, 0.55, 0.55)

## The four answers a library row can give about joining a model to a
## simulation. See the compatibility section at the bottom of this file.
const INTEGRATION_INTEGRATE := "integrate"
const INTEGRATION_INCOMPATIBLE := "incompatible"
const INTEGRATION_NOT_EVALUABLE := "needs_clarification"
const INTEGRATION_NOT_EVALUATED := "not_evaluated"
const INTEGRATION_UNKNOWN := "unknown"

var models: Array[Dictionary] = []
var _by_id: Dictionary = {}
var _manifests: Dictionary = {}
var _manifest_attempted: Dictionary = {}
var _quantities: Array = []
var _units_by_quantity: Dictionary = {}
var _contract_loaded := false
var _runner: CompositionRunner = null
var _pending_list_request := false
## Set while a manifest request is outstanding, so the shared `finished` signal
## can be routed to the right owner.
var _pending_manifest: Dictionary = {}
## Set while a `--describe-contract` request is outstanding.
var _pending_contract := false
## The last `--describe-connections` payload, once `accept_connections()` has
## been given one. `_boundaries` is its boundary list, filtered to entries that
## actually name two models.
var _connections: Dictionary = {}
var _boundaries: Array = []
var _connections_received := false
## The last `--describe-papers` payload: the ingested-paper corpus index. Empty
## until `accept_papers()` is given one.
var _papers: Dictionary = {}
var _papers_received := false


func setup(runner: CompositionRunner) -> void:
	_runner = runner
	runner.finished.connect(_on_runner_finished)


## Load the model list and the quantity registry.
func load() -> void:
	if _runner == null:
		emit_signal("load_failed",
			"The model registry was never given a runner, so no model can be described.")
		return
	_pending_list_request = true
	_runner.list_models()


## Ask for one model's manifest. Emits `manifest_loaded` or `manifest_failed`.
##
## Manifests are cached, including failures, so a node that is repainted does not
## respawn an interpreter; call `invalidate()` to force a fresh read.
func request_manifest(model_id: String) -> void:
	if _runner == null:
		emit_signal("manifest_failed", model_id,
			"The model registry was never given a runner, so no manifest can be read.")
		return
	if _manifests.has(model_id):
		emit_signal("manifest_loaded", model_id, _manifests[model_id])
		return
	if _manifest_attempted.has(model_id):
		emit_signal("manifest_failed", model_id,
			str(_manifest_attempted[model_id]))
		return
	_pending_manifest = {"model_id": model_id}
	_runner.describe_model(model_id)


func invalidate() -> void:
	_manifests.clear()
	_manifest_attempted.clear()


func _on_runner_finished(payload: Dictionary) -> void:
	if _pending_contract:
		_pending_contract = false
		_on_contract(payload)
		return
	if _pending_manifest.size() > 0:
		var model_id := str(_pending_manifest["model_id"])
		_pending_manifest = {}
		_on_manifest(model_id, payload)
		return
	if _pending_list_request:
		_pending_list_request = false
		_on_list_models(payload)


func _on_list_models(payload: Dictionary) -> void:
	# A discovery failure must be visible. An empty registry and a registry that
	# could not be built look identical in the canvas otherwise.
	if payload.has("_exit_code") and int(payload["_exit_code"]) != CompositionRunner.EXIT_OK:
		emit_signal("load_failed", _discovery_failure(payload))
		return
	var entries: Array = payload.get("models", [])
	if entries.is_empty():
		emit_signal("load_failed",
			"The runner reported no models. Check that the Models/ directory is "
			+ "intact and that 'python -m composition.runner --list-models' runs.")
		return
	# Rebuilt rather than reassigned: the payload is untyped JSON, and an entry
	# that is not an object is dropped instead of silently becoming a model.
	var loaded: Array[Dictionary] = []
	for entry in entries:
		if entry is Dictionary and entry.get("model_id", "") != "":
			loaded.append(entry)
	if loaded.is_empty():
		emit_signal("load_failed",
			"The runner listed %d entries but none carried a model id, so no model "
			% entries.size()
			+ "can be identified. This is a runner fault, not an empty installation.")
		return
	models = loaded
	_by_id.clear()
	for entry in models:
		_by_id[entry["model_id"]] = entry
	emit_signal("models_loaded", models)
	# Discovery is done, so the quantity registry can be asked for. Every call
	# on this boundary is synchronous, so this starts after `list_models` returns.
	load_contract()


func _discovery_failure(payload: Dictionary) -> String:
	for diagnostic in payload.get("diagnostics", []):
		return str(diagnostic.get("message", "the runner reported no models"))
	return (
		"The runner exited with code %d and listed no models.\n\n%s"
		% [int(payload.get("_exit_code", -1)), str(payload.get("_output", "")).strip_edges()]
	)


func _on_manifest(model_id: String, payload: Dictionary) -> void:
	var code := int(payload.get("_exit_code", -1))
	if code != CompositionRunner.EXIT_OK:
		# The payload names the references that would resolve. Keep it verbatim
		# rather than inventing a message.
		var message := "Model %s could not be resolved." % model_id
		for diagnostic in payload.get("diagnostics", []):
			message = str(diagnostic.get("message", message))
			break
		_manifest_attempted[model_id] = message
		emit_signal("manifest_failed", model_id, message)
		return
	if payload.get("resolved") != true:
		var message := "The runner did not resolve model %s." % model_id
		_manifest_attempted[model_id] = message
		emit_signal("manifest_failed", model_id, message)
		return
	# One record shape for both cases. `port_dependence` and `reference` describe
	# how the answer was obtained and are not fields of `ModelManifest`, so they
	# are carried alongside it rather than being re-derived or dropped.
	var manifest: Variant = payload.get("manifest")
	var source: Dictionary = manifest if manifest is Dictionary else {}
	var ports: Variant = source.get("ports", [])
	_manifests[model_id] = {
		"model_id": str(payload.get("model_id", model_id)),
		"model_version": str(payload.get("model_version", "")),
		"reference": str(payload.get("reference", "")),
		"port_dependence": str(payload.get("port_dependence", "")),
		"declared_ports": manifest is Dictionary,
		"ports": ports if ports is Array else [],
		"port_counts": payload.get("port_counts", {"input": 0, "output": 0}),
		"parameter_sections": _as_dict(source.get("parameter_sections", {})),
		"parameters": _as_dict(source.get("parameters", {})),
		"capabilities": source.get("capabilities", []),
		"unsupported_capabilities": _as_dict(source.get("unsupported_capabilities", {})),
		"reaction_terms": source.get("reaction_terms", []),
		"non_reacting_only": bool(source.get("non_reacting_only", false)),
		"source_ref": str(source.get("source_ref", "")),
		"title": str(source.get("title", "")),
		"notes": str(payload.get("notes", "")),
		"manifest": source,
	}
	_manifest_attempted.erase(model_id)
	emit_signal("manifest_loaded", model_id, _manifests[model_id])


static func _as_dict(value: Variant) -> Dictionary:
	return value if value is Dictionary else {}


# --------------------------------------------------------------------------- #
# lookups
# --------------------------------------------------------------------------- #


func model_ids() -> Array:
	return _by_id.keys()


func is_available(model_id: String) -> bool:
	var entry = _by_id.get(model_id)
	return bool(entry and entry.get("available", false))


func label_for(model_id: String) -> String:
	var entry = _by_id.get(model_id)
	return str(entry.get("label", model_id)) if entry else model_id


func has_manifest(model_id: String) -> bool:
	return _manifests.has(model_id)


## The cached manifest for `model_id`, or `{}` if none has been read yet.
##
## An empty dictionary means "not known", never "no ports". Use
## `port_dependence_for()` to tell those apart once a manifest has arrived.
func manifest_for(model_id: String) -> Dictionary:
	return _manifests.get(model_id, {})


## The exact `model_id@model_version` this registry resolved, or "".
func reference_for(model_id: String) -> String:
	var manifest := manifest_for(model_id)
	if manifest.has("reference"):
		return str(manifest["reference"])
	var entry = _by_id.get(model_id)
	if entry and entry.get("model_version", "") != "":
		return "%s@%s" % [model_id, entry["model_version"]]
	return ""


## "fixed" when the model publishes a model-level port set, "instance" when the
## ports are declared per instance, "" when no manifest has been read.
func port_dependence_for(model_id: String) -> String:
	var manifest := manifest_for(model_id)
	return str(manifest.get("port_dependence", "")) if manifest.size() > 0 else ""


## Ports declared by the model itself, as the manifest published them.
##
## Returns an empty array both when the model declares none and when its manifest
## has not been read; `port_dependence_for()` distinguishes them. The array is
## never synthesised from a port id, a display name or a parameter block.
func ports_for(model_id: String) -> Array:
	var manifest := manifest_for(model_id)
	if manifest.is_empty():
		return []
	var ports: Variant = manifest.get("ports", [])
	return ports if ports is Array else []


func port_counts_for(model_id: String) -> Dictionary:
	var manifest := manifest_for(model_id)
	if manifest.is_empty():
		return {"input": 0, "output": 0}
	return manifest.get("port_counts", {"input": 0, "output": 0})


## The model's declared parameter sections, for the inspector.
func parameter_sections_for(model_id: String) -> Dictionary:
	var manifest := manifest_for(model_id)
	if manifest.is_empty():
		return {}
	var sections: Variant = manifest.get("parameter_sections", {})
	return sections if sections is Dictionary else {}


func parameters_for(model_id: String) -> Dictionary:
	var manifest := manifest_for(model_id)
	if manifest.is_empty():
		return {}
	var parameters: Variant = manifest.get("parameters", {})
	return parameters if parameters is Dictionary else {}


# --------------------------------------------------------------------------- #
# compatibility boundary
#
# What the engine says about joining one model to another, as a model library
# renders it.
#
# `composition.cross_model` is the only authority on this question and this file
# adds no rule to it. Every state below is a function of two fields the engine
# already emitted -- `permitted` and `evidence_basis` -- and every sentence a row
# shows is the engine's own `reason`, carried through unchanged. There is no
# tolerance, no default and no model list here; change a verdict in the engine
# and the rows change with it.
#
# The four states are the four answers a library entry can honestly give:
#
#   integrate            the engine permits a connection to another model;
#   incompatible         every cross-model boundary is refused and each refusal
#                        is `documented_incompatibility` -- a source says so;
#   needs_clarification  at least one refusal is `evidence_limited`, which means
#                        the policy failed closed and *no judgement was made*.
#                        That is not evidence of incompatibility, and it is not
#                        shown as such;
#   not_evaluated        the engine returned no boundary naming this model, so
#                        nothing is known about joining it.
#
# Boundaries between a model and *itself* are carried separately in
# `own_model_pairs`. A model that may be chained to its own instances is not
# thereby compatible with anything else, and collapsing those two facts is the
# mistake this section exists to prevent.
# --------------------------------------------------------------------------- #


## Take a `--describe-connections` payload.
##
## Called by whichever window asked the runner; the registry only holds and
## maps the answer. A boundary that is not an object, or that does not name both
## a source and a target, is dropped rather than repaired, so a malformed
## boundary is reported as absent instead of being guessed at.
func accept_connections(payload: Dictionary) -> void:
	_connections = payload.duplicate(true)
	_boundaries = []
	for entry in payload.get("boundaries", []):
		if entry is Dictionary \
				and str(entry.get("source_model", "")) != "" \
				and str(entry.get("target_model", "")) != "":
			_boundaries.append(entry)
	_connections_received = true
	emit_signal("connections_loaded", _connections)


## True once the engine has actually been consulted.
func compatibility_loaded() -> bool:
	return _connections_received


## The payload's own scope statements: where the position comes from, and how
## far it claims to reach. `{}` until the engine has been consulted.
func connection_scope() -> Dictionary:
	if not _connections_received:
		return {}
	return {
		"contract_version": str(_connections.get("contract_version", "")),
		"claim_scope": str(_connections.get("claim_scope", "")),
		"validation_status": str(_connections.get("validation_status", "")),
		"boundary_count": _boundaries.size(),
		"quantity_pairs_examined": _connections.get("quantity_pairs_examined", []),
	}


## Every boundary whose source or target is `model_id`, in the order the engine
## reported them. Empty means the engine said nothing about this model -- which
## is not the same as saying it may be connected.
func boundaries_for(model_id: String) -> Array:
	var out: Array = []
	for boundary in _boundaries:
		if str(boundary.get("source_model", "")) == model_id \
				or str(boundary.get("target_model", "")) == model_id:
			out.append(boundary)
	return out


## The engine's standing for one library entry, mapped to the four states above.
##
## `counterparts` narrows the question to a set of models -- the ones already in
## the active simulation. It is only a *filter* over the engine's own boundaries:
## no verdict is re-derived, and an empty filter falls back to every other
## registered model, which is the library-wide question.
##
## The returned record always carries the engine's own `reason` for the decisive
## boundary and the full pair list, so a caller can show the evidence rather than
## the summary alone.
func integration_status(model_id: String, counterparts: Array = []) -> Dictionary:
	if not _connections_received:
		return _integration_record(INTEGRATION_UNKNOWN, "not evaluated yet",
			"The compatibility engine has not been consulted, so nothing can be "
			+ "said about joining this model to anything.",
			"", [], [], [])
	var wanted := _wanted_counterparts(model_id, counterparts)
	var cross: Array = []
	var own: Array = []
	for boundary in boundaries_for(model_id):
		var other := _other_model(boundary, model_id)
		var pair := _pair_record(boundary, other)
		if other == model_id:
			own.append(pair)
		elif wanted.is_empty() or wanted.has(other):
			cross.append(pair)

	if cross.is_empty() and own.is_empty():
		return _integration_record(INTEGRATION_NOT_EVALUATED, "not evaluated",
			"The compatibility engine reported no boundary naming this model, so "
			+ "whether it can join this simulation is unknown rather than permitted.",
			"", [], [], [])
	if cross.is_empty():
		return _integration_record(INTEGRATION_NOT_EVALUATED, "not evaluated",
			"The engine returned no cross-model boundary for this model in this "
			+ "simulation, so nothing can be said about joining it.",
			"", [], [], own)

	# One pass, three buckets. A refusal whose `evidence_basis` is
	# `evidence_limited` is kept apart from one a source documents, because the
	# two mean different things and only one of them is a judgement.
	var permitted: Array = []
	var documented: Array = []
	var limited: Array = []
	for pair in cross:
		if bool(pair.get("permitted", false)):
			permitted.append(pair)
		elif str(pair.get("basis", "")) == "evidence_limited":
			limited.append(pair)
		else:
			documented.append(pair)

	if not permitted.is_empty():
		return _integration_record(INTEGRATION_INTEGRATE, "composable",
			str(permitted[0].get("reason", "")),
			str(permitted[0].get("basis", "")),
			permitted, documented + limited, own)
	if not limited.is_empty():
		return _integration_record(INTEGRATION_NOT_EVALUABLE, "cannot be judged",
			str(limited[0].get("reason", "")), "evidence_limited",
			[], limited + documented, own)
	return _integration_record(INTEGRATION_INCOMPATIBLE,
		"cannot join this simulation",
		str(documented[0].get("reason", "")), "documented_incompatibility",
		[], documented, own)


## How many registered models fall into each state. Presentation only; the states
## themselves come from `integration_status()`.
func integration_summary(counterparts: Array = []) -> Dictionary:
	var counts := {
		INTEGRATION_INTEGRATE: 0,
		INTEGRATION_INCOMPATIBLE: 0,
		INTEGRATION_NOT_EVALUABLE: 0,
		INTEGRATION_NOT_EVALUATED: 0,
		INTEGRATION_UNKNOWN: 0,
	}
	for model_id in model_ids():
		var status := integration_status(str(model_id), counterparts)
		var state := str(status.get("state", INTEGRATION_UNKNOWN))
		counts[state] = int(counts.get(state, 0)) + 1
	return counts


## Presentation only: a colour per integration state. An unrecognised state gets
## the unknown colour rather than borrowing a decided one.
func integration_colour(state: String) -> Color:
	match state:
		INTEGRATION_INTEGRATE:
			return Color(0.56, 0.82, 0.60)
		INTEGRATION_INCOMPATIBLE:
			return Color(0.95, 0.72, 0.45)
		INTEGRATION_NOT_EVALUABLE:
			return Color(0.88, 0.82, 0.55)
		INTEGRATION_NOT_EVALUATED:
			return Color(0.72, 0.74, 0.80)
	return UNKNOWN_COLOUR


## The peers a narrowed question is about: the requested ids, minus this model,
## minus duplicates and empties.
static func _wanted_counterparts(model_id: String, counterparts: Array) -> Array:
	var wanted: Array = []
	for other in counterparts:
		var name := str(other)
		if name == "" or name == model_id or wanted.has(name):
			continue
		wanted.append(name)
	return wanted


## The model on the other side of a boundary from `model_id`.
static func _other_model(boundary: Dictionary, model_id: String) -> String:
	if str(boundary.get("source_model", "")) == model_id:
		return str(boundary.get("target_model", ""))
	return str(boundary.get("source_model", ""))


## One boundary as a row can render it, with the engine's fields named as the
## engine names them.
static func _pair_record(boundary: Dictionary, other: String) -> Dictionary:
	var unresolved: Variant = boundary.get("unresolved", [])
	return {
		"counterpart": other,
		"same_model": str(boundary.get("source_model", "")) == str(boundary.get("target_model", "")),
		"stance": str(boundary.get("stance", "")),
		"permitted": bool(boundary.get("permitted", false)),
		"basis": str(boundary.get("evidence_basis", "")),
		"reason": str(boundary.get("reason", "")),
		"remediation": str(boundary.get("remediation", "")),
		"unresolved": unresolved if unresolved is Array else [],
	}


static func _integration_record(state: String, label: String, reason: String,
		basis: String, permitted: Array, refused: Array, own: Array) -> Dictionary:
	return {
		"state": state,
		"label": label,
		"reason": reason,
		"basis": basis,
		"permitted_pairs": permitted,
		"refused_pairs": refused,
		"own_model_pairs": own,
		"permitted_count": permitted.size(),
		"refused_count": refused.size(),
		"source": "composition.cross_model.describe",
	}


# --------------------------------------------------------------------------- #
# paper corpus
#
# `Models/` is a literature corpus: one folder per paper. Some papers have a
# model package and three of those are registered; the rest do not, and the
# index says why. This section holds that index so the model library can show
# every paper it was given -- without any of them becoming placeable, because a
# paper is evidence a model rests on and never an executable component.
#
# No rule lives here. `determination` and `reason` are the index's own fields;
# `execution` restates the record's own `registered` / `model_package`; and
# `integration` is `integration_status()`, which is the engine's position.
# --------------------------------------------------------------------------- #


## Take a `--describe-papers` payload. A payload whose `papers` is not an array
## is stored as empty rather than repaired.
func accept_papers(payload: Dictionary) -> void:
	_papers = payload.duplicate(true) if payload.get("papers", []) is Array else {}
	_papers_received = true
	emit_signal("papers_loaded", _papers)


## True once the corpus index has actually been read.
func papers_received() -> bool:
	return _papers_received


## Every paper in the corpus, in the order the index reported them.
func paper_entries() -> Array:
	var out: Array = []
	var entries: Variant = _papers.get("papers", [])
	if not (entries is Array):
		return out
	for entry in entries:
		if entry is Dictionary and str(entry.get("folder", "")) != "":
			out.append(entry)
	return out


func paper_count() -> int:
	return paper_entries().size()


## How many papers the index filed under each determination, or `{}`.
func paper_counts() -> Dictionary:
	var counts: Variant = _papers.get("counts", {})
	return counts if counts is Dictionary else {}


## The corpus this index describes, for a panel that wants to name its source.
func paper_corpus() -> String:
	return str(_papers.get("corpus", ""))


## The one corpus entry a registered model encodes, or `{}` when none does. This
## is the paper -> model link the library shows on a model row.
func paper_for_model(model_id: String) -> Dictionary:
	for entry in paper_entries():
		if str(entry.get("model_id", "")) == model_id:
			return entry
	return {}


## One paper as a library row: where it lives, what was decided, whether a model
## encodes it, whether that model can run here, and the engine's position on
## joining this simulation.
##
## A paper with no registered model gets *no* compatibility claim: the engine
## classifies registered models, and saying otherwise would be this file
## inventing a verdict.
func paper_row(entry: Dictionary) -> Dictionary:
	var registered := bool(entry.get("registered", false))
	var model_id := str(entry.get("model_id", ""))
	var package := str(entry.get("model_package", ""))
	var standalone_module := str(entry.get("standalone_module", ""))
	var execution: Dictionary
	if registered:
		execution = {
			"state": "executable",
			"label": "executable",
			"detail": "registered as %s, so it can be placed from the model list above" % reference_for(model_id),
		}
	elif standalone_module != "":
		execution = {
			"state": "standalone_executable",
			"label": "executable standalone",
			"detail": "a standalone model exists at %s (module %s); it runs on its own paper's experiment and is deliberately not registered, so it cannot be placed in this graph" % [package, standalone_module],
		}
	elif package != "":
		execution = {
			"state": "not_executable_package",
			"label": "not executable here",
			"detail": "a model package exists at %s, but it is not registered with the composition layer, so it cannot be placed or run" % package,
		}
	else:
		execution = {
			"state": "evidence_only",
			"label": "evidence only",
			"detail": "no executable model exists for this paper; its findings are recorded, not run",
		}
	var integration: Dictionary
	if registered:
		integration = integration_status(model_id)
	else:
		integration = {
			"state": INTEGRATION_NOT_EVALUATED,
			"label": "no engine position",
			"reason": "The compatibility engine classifies registered models. Nothing was assessed for this paper, so nothing is claimed about it.",
			"basis": "",
			"source": "composition.cross_model.describe",
		}
	return {
		"folder": str(entry.get("folder", "")),
		"citation": str(entry.get("citation", "")),
		"determination": str(entry.get("determination", "")),
		"reason": str(entry.get("reason", "")),
		"model_id": model_id,
		"model_package": package,
		"execution": execution,
		"integration": integration,
	}


## Presentation only: a colour per paper execution state. An unrecognised state
## gets the unknown colour rather than borrowing a decided one.
func execution_colour(state: String) -> Color:
	match state:
		"executable":
			return Color(0.56, 0.82, 0.60)
		"standalone_executable":
			return Color(0.56, 0.72, 0.86)
		"not_executable_package":
			return Color(0.95, 0.82, 0.45)
	return Color(0.72, 0.74, 0.80)


# --------------------------------------------------------------------------- #
# quantity registry
#
# Populated from `--describe-contract`. There is no local list to fall out of
# step with the engine: an unlisted quantity is reported as unknown, and an
# unknown quantity is never quietly rendered as a different one.
# --------------------------------------------------------------------------- #


func load_contract() -> void:
	if _runner == null or _contract_loaded or _pending_contract:
		return
	_pending_contract = true
	_runner.describe_contract()


func _on_contract(payload: Dictionary) -> void:
	_contract_loaded = true
	_quantities.clear()
	_units_by_quantity.clear()
	for name in payload.get("quantities", []):
		_quantities.append({"name": str(name), "label": _quantity_label(str(name))})
	for name in payload.get("units_by_quantity", {}):
		_units_by_quantity[str(name)] = payload["units_by_quantity"][name]


## Quantity names this contract can express, sorted as the engine reports them.
func quantities() -> Array:
	return _quantities


func units_for(quantity: String) -> Array:
	return _units_by_quantity.get(quantity, [])


## `unknown` when the contract has not been read or the quantity is not in it.
## Never a neighbour: two quantities that are not the same are not interchangeable
## for display purposes either, because the reader has to be able to tell.
func canonical_quantity(quantity: String) -> String:
	if _quantities.is_empty():
		return UNKNOWN_QUANTITY
	for entry in _quantities:
		if str(entry["name"]) == quantity:
			return quantity
	return UNKNOWN_QUANTITY


static func _quantity_label(name: String) -> String:
	return name.replace("_", " ")


## Presentation only: a colour per quantity name.
##
## This is a lookup on the exact name, not a mapping. A quantity this palette has
## never heard of -- including one the contract has not declared -- gets
## `UNKNOWN_COLOUR`, so an unfamiliar quantity stays visibly unfamiliar instead of
## borrowing a familiar one's colour.
func colour_for(quantity: String) -> Color:
	match quantity:
		"mass": return Color(0.45, 0.62, 0.95)
		"mass_flow": return Color(0.40, 0.80, 0.72)
		"mass_fraction": return Color(0.92, 0.55, 0.62)
		"amount": return Color(0.86, 0.72, 0.42)
		"amount_flow": return Color(0.78, 0.66, 0.46)
		"volume": return Color(0.62, 0.88, 0.66)
		"volume_flow": return Color(0.56, 0.78, 0.70)
		"time": return Color(0.80, 0.80, 0.80)
		"temperature": return Color(0.88, 0.66, 0.58)
		"molar_concentration": return Color(0.58, 0.84, 0.86)
		"mass_concentration": return Color(0.60, 0.78, 0.90)
		"absorbance": return Color(0.72, 0.62, 0.92)
		"absorbance_per_volume": return Color(0.66, 0.60, 0.86)
		"absorbance_per_mass": return Color(0.62, 0.56, 0.80)
		"activity": return Color(0.90, 0.70, 0.50)
		"activity_per_volume": return Color(0.84, 0.66, 0.48)
		"molar_mass": return Color(0.70, 0.66, 0.52)
		"conductivity": return Color(0.52, 0.74, 0.72)
		"relative_centrifugal_force": return Color(0.62, 0.64, 0.78)
		"concentration_factor": return Color(0.76, 0.74, 0.56)
		"wavelength": return Color(0.70, 0.74, 0.90)
		"dimensionless": return Color(0.68, 0.68, 0.68)
		"ph": return Color(0.50, 0.72, 0.80)
	return UNKNOWN_COLOUR


func direction_label(direction: String) -> String:
	return "input" if direction == "input" else "output"
