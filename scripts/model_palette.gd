class_name ModelPalette
extends PanelContainer
## The model palette: every model the composition layer registered, and the only
## way to put one on the canvas.
##
## ## What it reads
##
## `_registry.model_ids()` -- which is whatever `python -m composition.runner
## --list-models` reported, and nothing else. There is **no list of model ids in
## this file**, and there must never be one: a model that is registered in
## `composition/composition/adapters/__init__.py` has to appear here without a
## GDScript edit, or a new model would again be invisible in the editor. That is
## precisely the defect this file exists to undo.
##
## ## What it shows
##
## For each registered model: the name the model published in its own manifest,
## the unambiguous `model_id@version` reference, whether its package is
## reachable, and whether its ports are fixed at model level or declared per
## instance.
##
## The name is the artefact's, never the palette's. A model that publishes no
## model-level manifest has no title to show, and its row says the identifier
## instead of a phrase this file made up -- the same rule `ModelRegistry` keeps
## about human-readable labels.
##
## ## What each row says about joining the simulation
##
## A row also carries the compatibility engine's standing for that entry, so a
## model the engine refuses cannot be mistaken for a compatible component at the
## moment it is placed. The wording is `ModelRegistry.integration_status()`'s,
## which maps two fields the engine emits -- `permitted` and `evidence_basis` --
## and nothing else. This file decides no verdict, holds no quantity pair, and
## names no model: a verdict changed in `composition/cross_model.py` reaches
## these rows without a GDScript edit.
##
## `set_active_models()` narrows the question to the models already in the graph.
## Narrowing filters the engine's boundaries; it never re-derives one, and an
## empty graph falls back to the library-wide position.
##
## The list is registered models only, and the panel states that: an artefact the
## composition layer does not register has no boundary in the engine's payload,
## so its absence from this list is not a compatibility verdict and must not be
## read as one.
##
## ## Empty and failed
##
## An empty registry and a registry that could not be built are different facts
## and are reported differently. Neither raises, and neither is rendered as an
## empty list.

## Emitted when the user has chosen a model and configured it. `parameters` is
## the instance declaration the model needs; `literals` maps
## `<port_id> -> literal input record` for the values the user supplied.
signal instance_requested(model_id: String, model_version: String, label: String, role: String, parameters: Dictionary, literals: Dictionary)

## A one-line note for the window status, for cases where no form is opened.
signal palette_message(text: String)

var _registry: ModelRegistry = null
var _form: InstanceForm = null
var _list: VBoxContainer = null
var _count_label: Label = null
var _notice: Label = null
## States what the compatibility position covers, because an artefact the
## composition layer does not register is invisible to the engine and its
## absence from this list is not a verdict about it.
var _scope: Label = null
## The ingested-paper corpus, rendered below the model list.
##
## Separate from `_rows` on purpose. `_rows` holds registered models and every
## one of them is placeable; `_paper_rows` holds every paper the project was
## given, and none of them is. Collapsing the two would make an evidence-only
## paper look like a component, which is the one thing this section exists to
## prevent.
var _papers_heading: Label = null
var _papers_count: Label = null
var _papers_list: VBoxContainer = null
var _paper_rows: Dictionary = {}
var _rows: Dictionary = {}
var _load_error := ""
## model ids whose manifest has been asked for and not yet arrived.
var _awaiting: Dictionary = {}
## The models currently in the graph. Empty means the graph is empty, and the
## rows answer the library-wide question instead of narrowing to nothing.
var _active_models: Array = []


func _init() -> void:
	# A panel the palette can sit in without the caller restyling it.
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.13, 0.14, 0.17)
	style.set_corner_radius_all(4)
	style.content_margin_left = 8.0
	style.content_margin_right = 8.0
	style.content_margin_top = 6.0
	style.content_margin_bottom = 6.0
	add_theme_stylebox_override("panel", style)


## `registry` supplies the model list and the manifests. `form` is opened when a
## model is chosen; it is the contract-driven configuration step and it owns no
## model knowledge of its own.
func setup(registry: ModelRegistry, form: InstanceForm) -> void:
	_registry = registry
	_form = form
	if _form != null and not _form.configured.is_connected(_on_form_configured):
		# The palette is what offers models, so the palette is what announces a
		# configured instance. The form emits, the palette relays, and the window
		# has exactly one signal to connect.
		_form.configured.connect(_on_form_configured)
	_build()
	if _registry != null:
		if not _registry.models_loaded.is_connected(_on_models_loaded):
			_registry.models_loaded.connect(_on_models_loaded)
		if not _registry.load_failed.is_connected(_on_load_failed):
			_registry.load_failed.connect(_on_load_failed)
		if not _registry.manifest_loaded.is_connected(_on_manifest_loaded):
			_registry.manifest_loaded.connect(_on_manifest_loaded)
		if not _registry.connections_loaded.is_connected(_on_connections_loaded):
			_registry.connections_loaded.connect(_on_connections_loaded)
		if not _registry.papers_loaded.is_connected(_on_papers_loaded):
			_registry.papers_loaded.connect(_on_papers_loaded)
		refresh()


func _build() -> void:
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 3)
	add_child(column)

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	column.add_child(head)
	var title := Label.new()
	title.text = "Models"
	title.add_theme_font_size_override("font_size", 13)
	head.add_child(title)
	_count_label = Label.new()
	_count_label.add_theme_font_size_override("font_size", 11)
	_count_label.modulate = Color(1, 1, 1, 0.6)
	head.add_child(_count_label)
	head.add_child(_spacer())

	_notice = Label.new()
	_notice.add_theme_font_size_override("font_size", 10)
	_notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_notice.modulate = Color(0.95, 0.70, 0.58)
	_notice.visible = false
	column.add_child(_notice)

	_scope = Label.new()
	_scope.name = "ScopeLabel"
	_scope.add_theme_font_size_override("font_size", 9)
	_scope.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_scope.modulate = Color(1, 1, 1, 0.42)
	_scope.visible = false
	column.add_child(_scope)

	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0, 128)
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)

	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 3)
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_list)

	_build_papers_section(column)


## The ingested-paper section: every paper the project was given, and what was
## decided about it. No row here has an Add button, and none of them is a model
## row -- a paper is shown so it cannot be silently absent, not so it can be run.
func _build_papers_section(column: VBoxContainer) -> void:
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	column.add_child(head)

	_papers_heading = Label.new()
	_papers_heading.text = "Ingested papers"
	_papers_heading.add_theme_font_size_override("font_size", 12)
	head.add_child(_papers_heading)

	_papers_count = Label.new()
	_papers_count.name = "PapersCountLabel"
	_papers_count.add_theme_font_size_override("font_size", 10)
	_papers_count.modulate = Color(1, 1, 1, 0.6)
	head.add_child(_papers_count)
	head.add_child(_spacer())

	var papers_scroll := ScrollContainer.new()
	papers_scroll.custom_minimum_size = Vector2(0, 150)
	papers_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	papers_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(papers_scroll)

	_papers_list = VBoxContainer.new()
	_papers_list.add_theme_constant_override("separation", 4)
	_papers_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	papers_scroll.add_child(_papers_list)


func _spacer() -> Control:
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return spacer


# --------------------------------------------------------------------------- #
# population
# --------------------------------------------------------------------------- #


## Rebuild the rows from the registry. Safe to call at any time; it is also what
## both registry signals call.
func refresh() -> void:
	if _list == null:
		return
	_update_scope()
	refresh_papers()
	for child in _list.get_children():
		_list.remove_child(child)
		child.queue_free()
	_rows.clear()
	_awaiting.clear()

	var ids: Array = []
	if _registry != null:
		ids = _registry.model_ids()
	ids.sort()

	if _load_error != "":
		_notice.text = _load_error
		_notice.visible = true
		_count_label.text = "unavailable"
		return
	_notice.visible = false

	if ids.is_empty():
		# An empty registry with no reported failure is its own fact, and saying
		# so is better than an empty box that looks like a rendering bug.
		_count_label.text = "none registered"
		var empty := Label.new()
		empty.text = ("No models are registered with the composition layer. "
			+ "Run 'python -m composition.runner --list-models' to see why.")
		empty.add_theme_font_size_override("font_size", 11)
		empty.modulate = Color(0.95, 0.70, 0.58)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_list.add_child(empty)
		return

	_count_label.text = _count_text(ids.size())
	for model_id in ids:
		var entry := _row(model_id)
		_list.add_child(entry)
		_rows[model_id] = entry
		# The name is the model's own, so ask for the manifest that carries it.
		# Every request here is cached by the registry, including failures, and a
		# model whose manifest never arrives simply keeps its identifier.
		_ensure_manifest(model_id)


func _ensure_manifest(model_id: String) -> void:
	if _registry == null or _registry.has_manifest(model_id):
		return
	if _awaiting.has(model_id):
		return
	_awaiting[model_id] = true
	_registry.request_manifest(model_id)


## One row per model. Returns the row so callers can find it again.
func _row(model_id: String) -> Control:
	var entry := entry_for(model_id)

	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.17, 0.19, 0.23) if entry.get("available", false) \
		else Color(0.24, 0.15, 0.15)
	style.set_corner_radius_all(3)
	style.content_margin_left = 7.0
	style.content_margin_right = 7.0
	style.content_margin_top = 4.0
	style.content_margin_bottom = 4.0
	panel.add_theme_stylebox_override("panel", style)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	panel.add_child(row)

	var text_column := VBoxContainer.new()
	text_column.add_theme_constant_override("separation", 0)
	text_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(text_column)

	var name_label := Label.new()
	name_label.name = "NameLabel"
	name_label.text = display_name(model_id)
	name_label.add_theme_font_size_override("font_size", 12)
	text_column.add_child(name_label)

	var id_label := Label.new()
	id_label.name = "IdLabel"
	id_label.text = reference_of(model_id)
	id_label.add_theme_font_size_override("font_size", 10)
	id_label.modulate = Color(1, 1, 1, 0.6)
	text_column.add_child(id_label)

	var note := Label.new()
	note.name = "NoteLabel"
	note.text = _row_note(model_id, entry)
	note.add_theme_font_size_override("font_size", 9)
	note.modulate = Color(1, 1, 1, 0.45)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text_column.add_child(note)

	# The compatibility engine's standing for this entry. A row whose model the
	# engine refuses says so before the Add button is pressed, in the engine's
	# own words, so placing it is a decision the operator has been told about.
	var integration := Label.new()
	integration.name = "IntegrationLabel"
	integration.text = _integration_text(model_id)
	integration.add_theme_font_size_override("font_size", 9)
	integration.modulate = _registry.integration_colour(_integration_state(model_id)) \
		if _registry != null else Color(1, 1, 1, 0.45)
	integration.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	integration.tooltip_text = _integration_tooltip(model_id)
	text_column.add_child(integration)

	# The paper this model encodes. A model whose source is not in the corpus
	# says so rather than showing nothing, because "no source" and "source not
	# read" are different facts.
	var source := Label.new()
	source.name = "SourceLabel"
	source.text = _source_text(model_id)
	source.add_theme_font_size_override("font_size", 9)
	source.modulate = Color(1, 1, 1, 0.42)
	source.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text_column.add_child(source)

	var add := Button.new()
	add.name = "AddButton"
	add.text = "Add"
	add.tooltip_text = "Configure %s and add it to the graph.\n\n%s" % [
		reference_of(model_id), _integration_text(model_id)]
	add.disabled = not bool(entry.get("available", false))
	add.pressed.connect(_on_add_pressed.bind(model_id))
	row.add_child(add)

	return panel


## The one-line description under the name. Every clause is something the
## registry or the manifest said; none of it is this file's opinion.
func _row_note(model_id: String, entry: Dictionary) -> String:
	if not bool(entry.get("available", false)):
		return "package not reachable at %s" % str(entry.get("package", "?"))
	var parts := PackedStringArray()
	var dependence := _registry.port_dependence_for(model_id) if _registry != null else ""
	if dependence == "instance":
		parts.append("ports declared per instance, not per model")
	elif dependence == "fixed":
		var counts := _registry.port_counts_for(model_id)
		var inputs := str(int(counts.get("input", 0)))
		var outputs := str(int(counts.get("output", 0)))
		parts.append(inputs + " in / " + outputs + " out, fixed by the model")
	if _registry != null:
		var manifest := _registry.manifest_for(model_id)
		var source_ref := str(manifest.get("source_ref", ""))
		if source_ref != "":
			parts.append(source_ref)
	return "  ·  ".join(parts)


# --------------------------------------------------------------------------- #
# compatibility
#
# The wording below renders `ModelRegistry.integration_status()`. Nothing here
# inspects a quantity, a unit or a boundary field: if a state is wrong it is
# wrong in the one mapping, and there is only one mapping.
# --------------------------------------------------------------------------- #


## The compatibility engine's standing for one entry, as this row shows it.
## `{}` when the palette has no registry to ask.
func status_for(model_id: String) -> Dictionary:
	if _registry == null:
		return {}
	return _registry.integration_status(model_id, _active_models)


## Narrow the question to the models already in the graph.
##
## Called by the window whenever the graph's model set changes. An empty array
## restores the library-wide question rather than suppressing the column,
## because "this graph is empty" is not "nothing is incompatible".
func set_active_models(model_ids: Array) -> void:
	var wanted: Array = []
	for model_id in model_ids:
		var name := str(model_id)
		if name != "" and not wanted.has(name):
			wanted.append(name)
	if wanted == _active_models:
		return
	_active_models = wanted
	_repaint_integration()


func _integration_state(model_id: String) -> String:
	return str(status_for(model_id).get("state", ModelRegistry.INTEGRATION_UNKNOWN))


## One line: the state, then the engine's own sentence, shortened for the row.
## The whole sentence is in the tooltip, so the shortening hides nothing.
func _integration_text(model_id: String) -> String:
	var status := status_for(model_id)
	if status.is_empty():
		return "compatibility: not evaluated"
	var label := str(status.get("label", "not evaluated"))
	var reason := str(status.get("reason", "")).strip_edges()
	if reason == "":
		return "compatibility: %s" % label
	return "compatibility: %s -- %s" % [label, _shorten(reason, 150)]


func _integration_tooltip(model_id: String) -> String:
	var status := status_for(model_id)
	if status.is_empty():
		return "The compatibility engine has not been consulted, so nothing is claimed."
	var lines := PackedStringArray()
	lines.append("Compatibility engine verdict: %s" % str(status.get("label", "")))
	lines.append(str(status.get("reason", "")))
	var basis := str(status.get("basis", ""))
	if basis != "":
		lines.append("Evidence basis: %s" % basis)
	for pair in status.get("refused_pairs", []):
		var remediation := str(pair.get("remediation", "")).strip_edges()
		if remediation != "":
			lines.append("What would have to exist first: %s" % remediation)
			break
	var own: Array = status.get("own_model_pairs", [])
	if not own.is_empty():
		lines.append("Boundaries with its own instances: %d recorded." % own.size())
	lines.append("Source: %s" % str(status.get("source", "")))
	return "\n".join(lines)


## State what the position covers, and only once the engine has been asked.
##
## `--describe-connections` classifies *registered* models. An artefact the
## composition layer does not register -- a package under `Models/` with no
## adapter -- produces no boundary at all, so it cannot appear in this list, and
## its absence is not a statement about it. Saying so is the difference between
## "nothing here may be composed with this simulation" and "nothing here may be".
func _update_scope() -> void:
	if _scope == null:
		return
	if _registry == null or _load_error != "" \
			or not _registry.compatibility_loaded() \
			or _registry.model_ids().is_empty():
		_scope.visible = false
		return
	var scope := _registry.connection_scope()
	_scope.text = ("compatibility covers the registered models only (%d ordered "
		+ "pair(s)). An artefact this layer does not register is not assessed, "
		+ "and its absence from this list is not a verdict about it."
		) % int(scope.get("boundary_count", 0))
	var claim := str(scope.get("claim_scope", "")).strip_edges()
	var status := str(scope.get("validation_status", "")).strip_edges()
	if claim == "":
		_scope.tooltip_text = status
	else:
		_scope.tooltip_text = claim if status == "" else "%s\n\n%s" % [claim, status]
	_scope.visible = true


## Repaint the compatibility column in place, so a row the user is looking at
## does not jump when the engine's answer arrives.
func _repaint_integration() -> void:
	if _registry == null:
		return
	_update_scope()
	for model_id in _rows.keys():
		var row: Control = _rows[model_id]
		if row == null:
			continue
		var label := row.find_child("IntegrationLabel", true, false) as Label
		if label != null:
			label.text = _integration_text(str(model_id))
			label.modulate = _registry.integration_colour(_integration_state(str(model_id)))
			label.tooltip_text = _integration_tooltip(str(model_id))
		var add := row.find_child("AddButton", true, false) as Button
		if add != null:
			add.tooltip_text = "Configure %s and add it to the graph.\n\n%s" % [
				reference_of(str(model_id)), _integration_text(str(model_id))]
	_update_count_label()


func _on_connections_loaded(_connections: Dictionary) -> void:
	_repaint_integration()


# --------------------------------------------------------------------------- #
# the ingested corpus
#
# A rendering of `ModelRegistry.paper_row()`. Nothing here decides a
# determination, an execution state or a compatibility position: this section
# shows that a paper exists and what was recorded about it, and offers no way to
# place one.
# --------------------------------------------------------------------------- #


## Every paper the corpus index reported, as a row record. Harness-facing.
func paper_entries() -> Array:
	var out: Array = []
	if _registry == null or not _registry.papers_received():
		return out
	for entry in _registry.paper_entries():
		out.append(_registry.paper_row(entry))
	return out


## The card control for one paper folder, or `null`.
func paper_row_for(folder: String) -> Control:
	return _paper_rows.get(folder, null)


func _on_papers_loaded(_papers: Dictionary) -> void:
	refresh_papers()


## Rebuild the corpus section. Self-guarding, and it reports every state rather
## than showing an empty box: an index that has not arrived and one that reported
## no papers are different facts.
func refresh_papers() -> void:
	if _papers_list == null:
		return
	for child in _papers_list.get_children():
		_papers_list.remove_child(child)
		child.queue_free()
	_paper_rows.clear()

	if _registry == null or not _registry.papers_received():
		if _papers_count != null:
			_papers_count.text = "not read"
		return

	var entries := paper_entries()
	if entries.is_empty():
		_papers_count.text = "none reported"
		_text_line(_papers_list,
			"The corpus index reported no papers. Check that Models/ still holds them.",
			Color(0.95, 0.70, 0.58), 10)
		return

	_papers_count.text = "%d paper(s)  ·  %s" % [entries.size(), _paper_count_text()]
	for entry in entries:
		_paper_card(entry)


func _paper_count_text() -> String:
	var counts := _registry.paper_counts()
	var parts := PackedStringArray()
	for key in [
		"encoded", "encoded_unregistered", "refused", "not_supportable", "candidate_input",
	]:
		var n := int(counts.get(key, 0))
		if n > 0:
			parts.append("%d %s" % [n, str(key).replace("_", " ")])
	return "  ·  ".join(parts)


func _paper_card(row: Dictionary) -> void:
	var folder := str(row.get("folder", "?"))
	var box := VBoxContainer.new()
	box.name = "Paper_" + folder
	box.add_theme_constant_override("separation", 1)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.17, 0.18, 0.21)
	style.border_color = Color(1, 1, 1, 0.08)
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 7.0
	style.content_margin_right = 7.0
	style.content_margin_top = 5.0
	style.content_margin_bottom = 5.0
	box.add_theme_stylebox_override("panel", style)

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	box.add_child(head)
	_text_line(head, folder, Color(1, 1, 1, 0.88), 10)
	head.add_child(_spacer())
	_text_line(head, str(row.get("determination", "")), Color(0.70, 0.79, 0.95), 9)

	_text_line(box, "source: %s" % str(row.get("citation", "")), Color(1, 1, 1, 0.62), 9)

	var execution: Dictionary = row.get("execution", {})
	_text_line(box, "execution: %s -- %s" % [
			str(execution.get("label", "")), str(execution.get("detail", ""))],
		_registry.execution_colour(str(execution.get("state", ""))), 9)

	var integration: Dictionary = row.get("integration", {})
	_text_line(box, "integration: %s -- %s" % [
			str(integration.get("label", "")),
			_shorten(str(integration.get("reason", "")), 130)],
		_registry.integration_colour(str(integration.get("state", ""))), 9)

	_text_line(box, "audit reason: %s" % str(row.get("reason", "")), Color(1, 1, 1, 0.42), 9)

	_papers_list.add_child(box)
	_paper_rows[folder] = box


func _text_line(parent: Control, text: String, colour: Color, size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.modulate = colour
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(label)
	return label


func _update_count_label() -> void:
	if _count_label == null or _registry == null:
		return
	var ids: Array = _registry.model_ids()
	if ids.is_empty() or _load_error != "":
		return
	_count_label.text = _count_text(ids.size())


## "<n> registered  ·  <k> incompatible  ·  ..." -- the engine's own tally, when
## it has been consulted. A state with no members is left out.
func _count_text(count: int) -> String:
	if _registry == null:
		return "%d registered" % count
	if not _registry.compatibility_loaded():
		return "%d registered  ·  compatibility not consulted" % count
	var counts := _registry.integration_summary(_active_models)
	var parts := PackedStringArray()
	parts.append("%d registered" % count)
	for state in [
		ModelRegistry.INTEGRATION_INTEGRATE,
		ModelRegistry.INTEGRATION_INCOMPATIBLE,
		ModelRegistry.INTEGRATION_NOT_EVALUABLE,
		ModelRegistry.INTEGRATION_NOT_EVALUATED,
		ModelRegistry.INTEGRATION_UNKNOWN,
	]:
		var n := int(counts.get(state, 0))
		if n > 0:
			parts.append("%d %s" % [n, _state_word(state)])
	return "  ·  ".join(parts)


static func _state_word(state: String) -> String:
	match state:
		ModelRegistry.INTEGRATION_INTEGRATE:
			return "composable"
		ModelRegistry.INTEGRATION_INCOMPATIBLE:
			return "incompatible"
		ModelRegistry.INTEGRATION_NOT_EVALUABLE:
			return "unevaluable"
		ModelRegistry.INTEGRATION_NOT_EVALUATED:
			return "not evaluated"
	return "unknown"


static func _shorten(text: String, limit: int) -> String:
	if text.length() <= limit:
		return text
	return text.substr(0, limit - 3).strip_edges() + "..."


## The paper a model row is sourced from, read from the corpus index.
func _source_text(model_id: String) -> String:
	if _registry == null or not _registry.papers_received():
		return "source: corpus not read"
	var paper := _registry.paper_for_model(model_id)
	if paper.is_empty():
		return "source: no paper in the corpus encodes this model"
	return "source: %s" % str(paper.get("citation", ""))


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #


func _on_add_pressed(model_id: String) -> void:
	if _form == null:
		emit_signal("palette_message",
			"The configuration form is not attached to this palette.")
		return
	_ensure_manifest(model_id)
	_form.open_for(model_id)


## Relay of the form's decision. The form emits; the palette announces. Keeping
## the relay here means a window that shows the palette needs one connection,
## not two, and it is the palette's own signal either way.
func _on_form_configured(model_id: String, model_version: String, label: String, role: String, parameters: Dictionary, literals: Dictionary) -> void:
	emit_signal("instance_requested", model_id, model_version, label, role, parameters, literals)


# --------------------------------------------------------------------------- #
# introspection -- the same facts the rows draw, for tests and for callers
# --------------------------------------------------------------------------- #


## One record per registered model, in the order the palette draws them.
func model_entries() -> Array:
	var out: Array = []
	if _registry == null:
		return out
	var ids: Array = _registry.model_ids()
	ids.sort()
	for model_id in ids:
		out.append({
			"model_id": str(model_id),
			"model_version": _version_of(str(model_id)),
			"reference": reference_of(str(model_id)),
			"available": _registry.is_available(str(model_id)),
			"display_name": display_name(str(model_id)),
			"port_dependence": _registry.port_dependence_for(str(model_id)),
			"title_from_manifest": str(_registry.manifest_for(str(model_id)).get("title", "")),
			"integration": status_for(str(model_id)),
		})
	return out


## The row control for one model, or `null`. Lets a caller drive the real Add
## button rather than a re-implementation of what it does.
func row_for(model_id: String) -> Control:
	return _rows.get(model_id, null)


## The Add button for one model, or `null`.
func add_button_for(model_id: String) -> Button:
	var row := row_for(model_id)
	if row == null:
		return null
	return row.find_child("AddButton", true, false) as Button


## The unambiguous reference the registry resolved, or the id when it has not.
func reference_of(model_id: String) -> String:
	if _registry == null:
		return model_id
	var reference := _registry.reference_for(model_id)
	return reference if reference != "" else model_id


## The name to print: the model's own title when it published one, and the
## identifier when it did not. Never a phrase this file composed.
func display_name(model_id: String) -> String:
	if _registry != null:
		var title := str(_registry.manifest_for(model_id).get("title", ""))
		if title.strip_edges() != "":
			return title
	return model_id


## True while the palette is showing a discovery failure rather than a list.
func has_load_error() -> bool:
	return _load_error != ""


func load_error() -> String:
	return _load_error


func _version_of(model_id: String) -> String:
	if _registry == null:
		return ""
	var reference := _registry.reference_for(model_id)
	if reference.contains("@"):
		return reference.get_slice("@", 1)
	return ""


# --------------------------------------------------------------------------- #
# registry signals
# --------------------------------------------------------------------------- #


func _on_models_loaded(_models: Array) -> void:
	_load_error = ""
	refresh()


func _on_load_failed(message: String) -> void:
	_load_error = message.strip_edges()
	refresh()
	emit_signal("palette_message", "Model discovery failed -- %s" % _load_error)


func _on_manifest_loaded(model_id: String, _manifest: Dictionary) -> void:
	_awaiting.erase(model_id)
	# The name and the port counts just changed; repaint that row in place so the
	# row the user is looking at does not jump.
	var row := row_for(model_id)
	if row == null:
		refresh()
		return
	var entry := entry_for(model_id)
	var name_label := row.find_child("NameLabel", true, false) as Label
	var note_label := row.find_child("NoteLabel", true, false) as Label
	if name_label != null:
		name_label.text = display_name(model_id)
	if note_label != null:
		note_label.text = _row_note(model_id, entry)


func entry_for(model_id: String) -> Dictionary:
	if _registry == null:
		return {}
	for entry in _registry.models:
		if str(entry.get("model_id", "")) == model_id:
			return entry
	return {}
