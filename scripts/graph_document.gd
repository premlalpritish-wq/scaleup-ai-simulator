class_name GraphDocument
extends Node
## The graph document: the JSON the canvas edits and the runner consumes.
##
## This is the single source of truth for what is on the canvas. The canvas
## mutates this object; the runner serialises it to disk. Nothing here performs
## a scientific calculation -- it only records what the user connected.

const CONTRACT_VERSION := "0.1.0"

var graph_id := "untitled"
var title := "Untitled composition"
var description := ""
var instances: Array[Dictionary] = []
var connections: Array[Dictionary] = []
var literal_inputs: Dictionary = {}
var defaults: Dictionary = {}
var notes := ""
## Provenance for the document as a whole. The runner does not consume it, but
## it is present in the shipped example graphs and must survive a load/save
## round-trip rather than being silently deleted.
var source_ref := ""

var _next_instance := 1
var _next_connection := 1


func _init() -> void:
	reset()


func reset() -> void:
	graph_id = "untitled"
	title = "Untitled composition"
	description = ""
	instances = []
	connections = []
	literal_inputs = {}
	defaults = {}
	notes = ""
	source_ref = ""
	_next_instance = 1
	_next_connection = 1


func to_dict() -> Dictionary:
	var doc := {
		"contract_version": CONTRACT_VERSION,
		"graph_id": graph_id,
		"title": title,
		"description": description,
		"instances": instances,
		"connections": connections,
		"literal_inputs": literal_inputs,
		"defaults": defaults,
		"notes": notes,
	}
	# Emitted only when the document carries it, so a graph that never had one
	# does not grow an empty field on every save.
	if source_ref != "":
		doc["source_ref"] = source_ref
	return doc


func to_json() -> String:
	return JSON.stringify(to_dict(), "\t")


func from_dict(doc: Dictionary) -> void:
	reset()
	graph_id = str(doc.get("graph_id", "untitled"))
	title = str(doc.get("title", "Untitled composition"))
	description = str(doc.get("description", ""))
	instances = _as_dict_array(doc.get("instances", []))
	connections = _as_dict_array(doc.get("connections", []))
	literal_inputs = _as_dict(doc.get("literal_inputs", {}))
	defaults = _as_dict(doc.get("defaults", {}))
	notes = str(doc.get("notes", ""))
	source_ref = str(doc.get("source_ref", ""))
	_next_instance = instances.size() + 1
	_next_connection = connections.size() + 1


func from_json(text: String) -> Error:
	var json := JSON.new()
	var err := json.parse(text)
	if err != OK:
		return err
	var data = json.get_data()
	if not data is Dictionary:
		return ERR_INVALID_DATA
	from_dict(data)
	return OK


func add_instance(model_id: String, model_version: String, label: String, role: String, position: Vector2, parameters: Dictionary) -> Dictionary:
	var inst := {
		"instance_id": "n%d" % _next_instance,
		"model_id": model_id,
		"model_version": model_version,
		"label": label,
		"role": role,
		"position": {"x": position.x, "y": position.y},
		"parameters": parameters,
	}
	_next_instance += 1
	instances.append(inst)
	return inst


func remove_instance(instance_id: String) -> void:
	instances.erase(_find(instance_id))
	var kept: Array[Dictionary] = []
	for c in connections:
		if str(c["source"]["instance_id"]) != instance_id and str(c["target"]["instance_id"]) != instance_id:
			kept.append(c)
	connections = kept
	var kept_literals := {}
	for k in literal_inputs:
		if str(literal_inputs[k].get("instance_id", "")) != instance_id:
			kept_literals[k] = literal_inputs[k]
	literal_inputs = kept_literals


func find_instance(instance_id: String) -> Dictionary:
	return _find(instance_id)


func _find(instance_id: String) -> Dictionary:
	for inst in instances:
		if str(inst["instance_id"]) == instance_id:
			return inst
	return {}


func add_connection(source: Dictionary, target: Dictionary) -> Dictionary:
	var conn := {
		"connection_id": "c%d" % _next_connection,
		"source": {"instance_id": str(source["instance_id"]), "port_id": str(source["port_id"])},
		"target": {"instance_id": str(target["instance_id"]), "port_id": str(target["port_id"])},
		"transform": "identity",
		"label": "",
		"notes": "",
	}
	_next_connection += 1
	connections.append(conn)
	return conn


func remove_connection(connection_id: String) -> void:
	connections.erase(_find_connection(connection_id))


func _find_connection(connection_id: String) -> Dictionary:
	for conn in connections:
		if str(conn["connection_id"]) == connection_id:
			return conn
	return {}


func connection_at(instance_id: String, port_id: String, direction: String) -> Dictionary:
	for conn in connections:
		if direction == "output" and str(conn["source"]["instance_id"]) == instance_id and str(conn["source"]["port_id"]) == port_id:
			return conn
		if direction == "input" and str(conn["target"]["instance_id"]) == instance_id and str(conn["target"]["port_id"]) == port_id:
			return conn
	return {}


func set_literal(instance_id: String, port_id: String, spec: Dictionary) -> void:
	spec["instance_id"] = instance_id
	spec["port_id"] = port_id
	literal_inputs["%s/%s" % [instance_id, port_id]] = spec


func remove_literal(instance_id: String, port_id: String) -> void:
	literal_inputs.erase("%s/%s" % [instance_id, port_id])


func literal_for(instance_id: String, port_id: String) -> Dictionary:
	return literal_inputs.get("%s/%s" % [instance_id, port_id], {})


func _as_dict_array(value) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	if value is Array:
		for item in value:
			if item is Dictionary:
				out.append(item)
	return out


func _as_dict(value) -> Dictionary:
	if value is Dictionary:
		return value
	return {}


func validate_shape() -> Array[String]:
	"""Structural checks the canvas can make without the Python runner."""
	var problems: Array[String] = []
	var seen_instances := {}
	for inst in instances:
		var id := str(inst["instance_id"])
		if seen_instances.has(id):
			problems.append("duplicate instance id %s" % id)
		seen_instances[id] = true
		if not inst.has("model_id") or str(inst["model_id"]) == "":
			problems.append("instance %s has no model_id" % id)
		if not inst.has("parameters"):
			problems.append("instance %s has no parameters" % id)
	var seen_connections := {}
	for conn in connections:
		var cid := str(conn["connection_id"])
		if seen_connections.has(cid):
			problems.append("duplicate connection id %s" % cid)
		seen_connections[cid] = true
		var src := str(conn["source"]["instance_id"])
		var dst := str(conn["target"]["instance_id"])
		if not seen_instances.has(src):
			problems.append("connection %s names unknown instance %s" % [cid, src])
		if not seen_instances.has(dst):
			problems.append("connection %s names unknown instance %s" % [cid, dst])
		if src == dst:
			problems.append("connection %s links %s to itself" % [cid, src])
	return problems
