extends SceneTree
## Headless check that Godot can load and render the gap-discovery payload.

var _checks := 0
var _failures: Array[String] = []


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		print("FAIL: ", message)


func _initialize() -> void:
	var script = load("res://scripts/scientific_gap_panel.gd")
	_check(script != null, "the ScientificGapPanel script loads")
	if script == null:
		_finish()
		return
	var panel = script.new()
	get_root().add_child(panel)
	panel.setup("python", ProjectSettings.globalize_path("res://composition"))

	var file := FileAccess.open(
		"res://composition/examples/zielinski_gap_discovery.json", FileAccess.READ)
	_check(file != null, "the example gap-discovery payload opens")
	if file == null:
		_finish()
		return
	var payload = JSON.parse_string(file.get_as_text())
	file.close()
	_check(payload is Dictionary, "the example payload is a JSON object")
	if not payload is Dictionary:
		_finish()
		return

	panel.set_payload(payload)
	var gaps: Array = payload.get("gaps", [])
	_check(panel.gap_count() == gaps.size(), "every gap produced a row")
	_check(panel.summary_value("gaps") == str(gaps.size()), "the summary shows the gap count")
	_check(panel.summary_value("fully_addressed") == "0", "the summary preserves zero fully addressed gaps")
	_check(panel.summary_value("partially_addressed") == "2", "the summary shows two partially informed gaps")
	_check(panel.summary_text().contains("No classification"), "the summary states the no-upgrade rule")
	_check(panel.selected_gap().get("gap_id") == gaps[0].get("gap_id"), "the first gap is selected")
	_check(panel.paper_rows_for_selected().size() >= 1, "the selected gap shows a paper match")
	_check(panel.recommendation_for_selected().size() > 0, "the selected gap shows a recommendation")
	_check(panel.search_terms_for_selected().size() > 0, "the selected gap has search terms")

	panel.select_gap("GAP-MP-OXYGEN-TRANSFER")
	var keys: Array = []
	for paper in panel.paper_rows_for_selected():
		keys.append(str(paper.get("key", "")))
	_check("baez" in keys, "the oxygen gap shows Baez")
	_check("lin" in keys, "the oxygen gap shows Lin")
	_check(panel.recommendation_for_selected().get("gap_id") == "GAP-MP-OXYGEN-TRANSFER", "the recommendation is bound to the selected gap")
	var copy_button = panel.find_child("CopySearchTermsButton", true, false)
	_check(copy_button != null, "the copy-search-terms button is present")

	panel.select_gap("GAP-MP-FOLDING-MODEL")
	_check(panel.paper_rows_for_selected().size() == 1, "the folding gap shows only the baseline record")
	_check(panel.recommendation_for_selected().size() > 0, "the folding gap has a recommendation")

	# Exercise the real local Python bridge, not just a pre-generated file.
	panel.set_payload({})
	panel.request()
	_check(panel.payload().has("gaps"), "the panel reads the analysis from the local Python runner")
	_check(panel.gap_count() == gaps.size(), "the live analysis returns the same gap count")

	panel.set_payload({})
	_check(panel.summary_text().contains("could not be read"), "an empty payload is reported as unreadable, not as no gaps")

	panel.queue_free()
	_finish()


func _finish() -> void:
	print("\nSCIENTIFIC GAP PANEL CHECKS: %d passed, %d failures" % [_checks, _failures.size()])
	quit(0 if _failures.is_empty() else 1)
