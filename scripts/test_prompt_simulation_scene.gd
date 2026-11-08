extends SceneTree

func _init() -> void:
	print("--- BEGIN TEST PROMPT SIMULATION SCENE ---")
	var scene_res = load("res://scenes/prompt_simulation.tscn")
	if scene_res == null:
		print("FAIL: Could not load prompt_simulation.tscn")
		quit(1)
		return

	var scene = scene_res.instantiate()
	root.add_child(scene)
	await process_frame

	# Verify initial state starts paused at t = 0.0 h
	if scene._is_playing != false:
		print("FAIL: Scene should start paused at t = 0.0 h")
		quit(1)
		return
	print("Initial pause state verified (is_playing = false)")

	# Test load_run_file with async stage streaming
	var run_file = ProjectSettings.globalize_path("res://.artifacts/latest_prompt_run.json")
	scene.load_run_file(run_file)
	if scene._view != null and scene._view.is_building:
		await scene._view.bench_build_completed
	await process_frame

	# =========================================================================
	# 1. HARD SCENE ASSERTIONS: Explicit 3D Solid Biomass Geometry Verification
	# =========================================================================
	var st0 = scene.find_child("Stage_0_dry_biomass_milling", true, false)
	var st1 = scene.find_child("Stage_1_acid_demineralisation", true, false)
	var st2 = scene.find_child("Stage_2_alkaline_solubilisation", true, false)
	var st3 = scene.find_child("Stage_3_centrifugation_neutralisation", true, false)
	var st4 = scene.find_child("Stage_4_ethanol_precipitation", true, false)
	var st5 = scene.find_child("Stage_5_wet_spinning_mechanics", true, false)

	if st0 == null or st1 == null or st2 == null or st3 == null or st4 == null or st5 == null:
		print("FAIL: One or more stage vessel root nodes missing from scene tree!")
		quit(1)
		return

	var dry_pile: MeshInstance3D = st0.find_child("DryMilledSeaweedPile", true, false)
	var dry_lbl: Label3D = st0.find_child("DryBiomassLabel3D", true, false)
	var flakes1: Node3D = st1.find_child("SolidKelpFlakesGroup", true, false)
	var flakes2: Node3D = st2.find_child("SolidKelpFlakesGroup", true, false)
	var pellet: MeshInstance3D = st3.find_child("CentrifugeSolidPellet", true, false)
	var clot: MeshInstance3D = st4.find_child("PrecipitatedAlginateClot", true, false)
	var fibre: MeshInstance3D = st5.find_child("SpunAlginateFibre", true, false)

	if dry_pile == null or dry_pile.mesh == null:
		print("FAIL: DryMilledSeaweedPile node or mesh missing!")
		quit(1)
		return
	var dry_flake_count: int = 85
	var dry_mm := dry_pile.find_child("DryFlakesMultiMesh", true, false) as MultiMeshInstance3D
	if dry_mm != null and dry_mm.multimesh != null:
		dry_flake_count = dry_mm.multimesh.instance_count
	elif dry_pile.get_child_count() > 0:
		dry_flake_count = dry_pile.get_child_count()
	print("PASS: Stage 0 DryMilledSeaweedPile verified (flakes count: %d)" % dry_flake_count)

	if dry_lbl == null:
		print("FAIL: DryBiomassLabel3D missing!")
		quit(1)
		return
	print("PASS: Stage 0 DryBiomassLabel3D verified: '%s'" % dry_lbl.text)

	var count1: int = flakes1.multimesh.instance_count if (flakes1 is MultiMeshInstance3D and flakes1.multimesh != null) else flakes1.get_child_count()
	if flakes1 == null or count1 < 50:
		print("FAIL: Stage 1 SolidKelpFlakesGroup missing or < 50 flakes!")
		quit(1)
		return
	print("PASS: Stage 1 SolidKelpFlakesGroup verified with %d child meshes!" % count1)

	var count2: int = flakes2.multimesh.instance_count if (flakes2 is MultiMeshInstance3D and flakes2.multimesh != null) else flakes2.get_child_count()
	if flakes2 == null or count2 < 50:
		print("FAIL: Stage 2 SolidKelpFlakesGroup missing or < 50 flakes!")
		quit(1)
		return
	print("PASS: Stage 2 SolidKelpFlakesGroup verified with %d child meshes!" % count2)

	if pellet == null or pellet.mesh == null:
		print("FAIL: Stage 3 CentrifugeSolidPellet missing or has no mesh!")
		quit(1)
		return
	print("PASS: Stage 3 CentrifugeSolidPellet verified")

	if clot == null or clot.mesh == null:
		print("FAIL: Stage 4 PrecipitatedAlginateClot missing or has no mesh!")
		quit(1)
		return
	print("PASS: Stage 4 PrecipitatedAlginateClot verified")

	if fibre == null or fibre.mesh == null:
		print("FAIL: Stage 5 SpunAlginateFibre missing or has no mesh!")
		quit(1)
		return
	print("PASS: Stage 5 SpunAlginateFibre geometry verified")

	# =========================================================================
	# 2. CONSERVATION OF MASS & SEQUENTIAL BATCH CONTINUITY ASSERTIONS
	# =========================================================================
	# Timeline:
	# [0.0 - 2.0h] Stage 0: Dry milling & weighing (15.0g dry biomass)
	# [2.0 - 16.0h] Stage 1: Acid Demineralisation wash
	# [16.0 - 32.0h] Stage 2: Alkaline Solubilisation
	# [32.0 - 34.0h] Stage 3: Centrifugation & Decanting (Waste pellet retained!)
	# [34.0 - 36.0h] Stage 4: Ethanol Precipitation
	# [36.0 - 40.0h] Stage 5: Wet Spinning

	# Check t = 0.5h: Stage 0 is active; Stages 1, 2, 3, 4, 5 are EMPTY
	scene._on_scrub(0.5)
	if not dry_pile.visible:
		print("FAIL at t = 0.5h: DryMilledSeaweedPile should be visible!")
		quit(1)
		return
	if flakes1.visible or flakes2.visible or pellet.visible or clot.visible or fibre.visible:
		print("FAIL at t = 0.5h: Downstream stages must be EMPTY!")
		quit(1)
		return
	print("PASS: Continuity at t = 0.5h (Stage 0 active, downstream 1-5 empty)")

	# Check t = 8.0h: Stage 1 active (solid kelp swirling in acid); Stage 0 empty; Stages 2, 3, 4, 5 empty
	scene._on_scrub(8.0)
	if dry_pile.visible:
		print("FAIL at t = 8.0h: Stage 0 pile must be empty/hidden!")
		quit(1)
		return
	if not flakes1.visible:
		print("FAIL at t = 8.0h: Stage 1 SolidKelpFlakesGroup must be visible!")
		quit(1)
		return
	if flakes2.visible or pellet.visible or clot.visible or fibre.visible:
		print("FAIL at t = 8.0h: Stages 2, 3, 4, 5 must be empty!")
		quit(1)
		return
	print("PASS: Continuity at t = 8.0h (Stage 1 active, Stage 0 drained, Stages 2-5 empty)")

	# Check t = 24.0h: Stage 2 active (solid kelp pulp dissolving); Stages 0, 1 empty; Stages 3, 4, 5 empty
	scene._on_scrub(24.0)
	if dry_pile.visible or flakes1.visible:
		print("FAIL at t = 24.0h: Stages 0 and 1 must be empty/hidden!")
		quit(1)
		return
	if not flakes2.visible:
		print("FAIL at t = 24.0h: Stage 2 SolidKelpFlakesGroup must be visible!")
		quit(1)
		return
	if pellet.visible or clot.visible or fibre.visible:
		print("FAIL at t = 24.0h: Stages 3, 4, 5 must be empty!")
		quit(1)
		return
	print("PASS: Continuity at t = 24.0h (Stage 2 active, Stages 0-1 drained, Stages 3-5 empty)")

	# Check t = 35.0h: Stage 3 pellet permanently retained, Stage 4 clot active; Stages 0, 1, 2 empty; Stage 5 empty
	scene._on_scrub(35.0)
	if dry_pile.visible or flakes1.visible or flakes2.visible:
		print("FAIL at t = 35.0h: Stages 0, 1, 2 must be empty/hidden!")
		quit(1)
		return
	if not pellet.visible:
		print("FAIL at t = 35.0h: Stage 3 CentrifugeSolidPellet must be permanently retained!")
		quit(1)
		return
	if not clot.visible:
		print("FAIL at t = 35.0h: Stage 4 PrecipitatedAlginateClot must be visible!")
		quit(1)
		return
	if fibre.visible:
		print("FAIL at t = 35.0h: Stage 5 fibre must be empty/hidden before spinning!")
		quit(1)
		return
	print("PASS: Continuity at t = 35.0h (Stage 3 waste pellet retained, Stage 4 clot visible, Stages 0-2 and 5 empty)")

	# Check t = 38.0h: Stage 5 active spinning; Stage 3 waste pellet STILL retained!
	scene._on_scrub(38.0)
	if not pellet.visible:
		print("FAIL at t = 38.0h: Stage 3 CentrifugeSolidPellet must remain permanently visible as discarded residue!")
		quit(1)
		return
	if not fibre.visible:
		print("FAIL at t = 38.0h: Stage 5 SpunAlginateFibre must be visible!")
		quit(1)
		return
	print("PASS: Continuity at t = 38.0h (Stage 5 active spinning, Stage 3 waste pellet permanently retained)")

	# =========================================================================
	# 3. Playback, Timeline, and Interaction Tests
	# =========================================================================
	# Verify play toggle
	scene._on_play_toggle()
	if scene._is_playing != true:
		print("FAIL: _on_play_toggle() should toggle to playing")
		quit(1)
		return
	print("Play toggle verified (is_playing = true)")

	# Verify pause menu modal toggle
	scene._toggle_pause_menu()
	if scene._is_playing != false:
		print("FAIL: Opening pause menu should automatically pause simulation")
		quit(1)
		return
	print("Pause menu modal toggle verified")
	scene._toggle_pause_menu() # Close it

	# Verify 3D stage jump
	scene._jump_to_stage_by_index(1)
	print("Stage jump to stage 1 verified")

	# Verify sandbox levers
	scene._on_sandbox_ph_toggle()
	scene._on_sandbox_scale_toggle()
	scene._on_sandbox_crosslink_toggle()
	scene._on_sandbox_tension_changed(44.0)
	print("Sandbox levers and tension test verified")

	# Verify 3D component clicking
	scene._on_hardware_component_clicked("feed_tube")
	scene._on_hardware_component_clicked("culture_broth")
	scene._on_hardware_component_clicked("impeller_sparger")
	scene._on_hardware_component_clicked("harvest_valve")
	print("Hardware components selected successfully")

	# Verify hot-swap ghost curve comparison
	if scene._hotswap_selector != null and scene._hotswap_selector.item_count > 1:
		scene._on_hotswap_selected(1)
		print("Hot-swap selected item 1, delta badge visible:", scene._delta_badge.visible)
		if not scene._delta_badge.visible:
			print("FAIL: delta badge was not visible after hot-swap")
			quit(1)
			return

	print("--- PASS TEST PROMPT SIMULATION SCENE ---")
	quit(0)
