"""Tests for Central Knowledge Library reconstruction and cross-paper literature review."""
from __future__ import annotations

import pytest
from pathlib import Path

from composition import prompt
from composition.evidence.library_store import (
    CompatibilityEdgeTier,
    MechanismRecord,
    PortSpec,
    get_library_store,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def library_store():
    store = get_library_store()
    assert store is not None
    assert len(store.papers) >= 8
    assert len(store.parameters) >= 35
    assert len(store.mechanisms) >= 8
    return store


def test_reconstruct_multi_paper_from_prompt(library_store):
    """Verify that a prompt dynamically reconstructs a multi-paper simulation solely from central_library.json."""
    prompt_text = (
        "Simulate E. coli fed-batch growth kinetics with Ganjave cybernetic model "
        "and Baez overflow metabolism."
    )
    result = prompt.reconstruct_from_library(prompt_text)
    assert result["ok"] is True
    assert result["reconstruction_mode"] == "central_knowledge_library"
    assert result["target_process"]["organism"] == "Escherichia coli"
    assert result["target_process"]["mode"] == "fed_batch"

    # Verify literature_review_manifest
    manifest = result["literature_review_manifest"]
    assert manifest is not None
    assert manifest["reconstruction_mode"] == "central_knowledge_library"
    assert manifest["target_organism"] == "Escherichia coli"

    # Check combined papers
    combined_paper_ids = [p["paper_id"] for p in manifest["combined_papers"]]
    assert "ganjave2022" in combined_paper_ids
    assert "baez2014" in combined_paper_ids

    # Check composition graph
    graph = result["composition_graph"]
    instance_ids = [inst["instance_id"] for inst in graph["instances"]]
    assert "growth_kinetics" in instance_ids
    assert "overflow_metabolism" in instance_ids
    assert graph["connections"]

    # Check empirical parameter priors
    literals = graph["literal_inputs"]
    assert "growth_kinetics/initial_biomass_concentration" in literals
    assert literals["growth_kinetics/initial_biomass_concentration"]["value"] > 0.0


def test_cross_paper_strain_condition_mismatch_flagged(library_store):
    """Verify that cross-paper strain/condition mismatches are explicitly flagged in literature_review_manifest."""
    prompt_text = (
        "Simulate fed-batch growth kinetics with Ganjave and Baez overflow metabolism."
    )
    result = prompt.reconstruct_from_library(prompt_text)
    manifest = result["literature_review_manifest"]
    connections = manifest["cross_paper_connections"]
    assert connections, "Expected at least one cross-paper connection"

    # Ganjave uses BL21(DE3) at 37 C; Baez uses W3110 at 37 C
    # The cross-paper edge must be an ANALOGUE_BRIDGE, not a silent exact match
    edge = connections[0]
    assert edge["tier"] == CompatibilityEdgeTier.ANALOGUE_BRIDGE
    assert "strain bridge" in edge["reason"].lower() or "compatible e. coli" in edge["reason"].lower()


def test_organism_conflict_flagged_as_incompatible(library_store):
    """Verify that crossing distinct organism boundaries is flagged as INCOMPATIBLE_CONSTRAINTS."""
    b_subtilis_mech = MechanismRecord(
        mechanism_id="subtilis.riboflavin",
        name="Bacillus subtilis riboflavin synthesis",
        equation_summary="Riboflavin production pathway in B. subtilis",
        input_ports=[PortSpec("glucose_uptake", "specific_rate", "mmol/(g h)")],
        output_ports=[PortSpec("riboflavin_yield", "mass_ratio", "g/g")],
        paper_id="subtilis2020",
        compatible_contexts=[{"organism": "Bacillus subtilis", "strain": "168", "mode": "batch"}],
    )
    library_store.add_mechanism(b_subtilis_mech)
    edge = library_store.compute_compatibility_edge(
        "ganjave.growth_kinetics",
        "subtilis.riboflavin",
        "glucose_uptake",
    )
    assert edge.tier == CompatibilityEdgeTier.INCOMPATIBLE_CONSTRAINTS
    assert "organism conflict" in edge.reason.lower()
    assert "escherichia coli" in edge.reason.lower()
    assert "bacillus subtilis" in edge.reason.lower()


def test_alternate_paper_models_for_hot_swapping(library_store):
    """Verify that alternate paper models for the same biological port are returned for hot-swapping."""
    prompt_text = "Simulate growth kinetics with acetate overflow and scaleup mixing"
    result = prompt.reconstruct_from_library(prompt_text)
    graph = result["composition_graph"]

    # Every node in the graph exposes alternatives
    for inst in graph["instances"]:
        assert "alternatives" in inst
        for alt in inst["alternatives"]:
            assert "mechanism_id" in alt
            assert "paper_id" in alt
            assert "paper_title" in alt
            assert "port_id" in alt

    # Manifest also carries alternatives by module
    manifest = result["literature_review_manifest"]
    alts_by_mod = manifest["alternatives_by_module"]
    assert alts_by_mod
    assert "growth_kinetics" in alts_by_mod


def test_interpret_delegates_to_central_library_when_recombining(library_store):
    """Verify that prompt.interpret() delegates to reconstruct_from_library for central library prompts."""
    prompt_text = (
        "Recombine Ganjave growth kinetics with Baez acetate overflow metabolism in fed-batch."
    )
    result = prompt.interpret(prompt_text)
    assert result["ok"] is True
    assert result["reconstruction_mode"] == "central_knowledge_library"
    assert "literature_review_manifest" in result
    combined = [p["paper_id"] for p in result["literature_review_manifest"]["combined_papers"]]
    assert "ganjave2022" in combined
    assert "baez2014" in combined


def test_interpret_single_zielinski_preserves_manifest_structure(library_store):
    """Verify that single-model Zielinski replay also exposes literature_review_manifest and alternatives."""
    prompt_text = (
        "Simulate the Zielinski insulin production process for 19 hours and show "
        "OD600, wet biomass, inclusion bodies and insulin activity."
    )
    result = prompt.interpret(prompt_text)
    assert result["ok"] is True
    manifest = result.get("literature_review_manifest")
    assert manifest is not None
    assert manifest["reconstruction_mode"] == "single_paper_evidence_replay"
    assert manifest["combined_papers"][0]["paper_id"] == "zielinski2019"
    assert "alternatives_by_module" in manifest


def test_cache_first_lookup_and_run_file_artifact_generation(library_store):
    """Verify cache-first lookup, --run-file artifact generation, and diagram linking."""
    from composition.workflow.skill_research_bridge import resolve_prompt_and_research

    prompt_text = (
        "Simulate E. coli fed-batch growth kinetics with Ganjave cybernetic model "
        "and Baez overflow metabolism."
    )
    artifact, exit_code = resolve_prompt_and_research(prompt_text, auto_research=True, launch_godot=False)
    assert exit_code == 0
    assert artifact["status"] == "COMPLETED"
    assert artifact["cache_hit"] is True
    assert artifact["prompt"] == prompt_text
    assert "diagram_path" in artifact
    assert (ROOT / artifact["diagram_path"]).is_file()

    # Manifest checks
    manifest = artifact["literature_review_manifest"]
    assert manifest is not None
    assert len(manifest["combined_papers"]) == 2
    assert manifest["cross_paper_connections"]

    # Trajectories checks
    trajectories = artifact["trajectories"]
    assert len(trajectories["time_hours"]) > 10
    assert len(trajectories["biomass_g_per_L"]) == len(trajectories["time_hours"])
    assert trajectories["biomass_g_per_L"][-1] > trajectories["biomass_g_per_L"][0]

    # Verify latest_prompt_run.json was written
    run_file = ROOT / ".artifacts" / "latest_prompt_run.json"
    assert run_file.is_file()
    import json
    saved_data = json.loads(run_file.read_text(encoding="utf-8"))
    assert saved_data["run_id"] == artifact["run_id"]


def test_offline_replay_from_central_library(monkeypatch, library_store):
    """Verify that execution replays completely offline from central_library.json without external network calls."""
    from composition.workflow import skill_research_bridge

    def mock_fail_search(*args, **kwargs):
        raise RuntimeError("External network call attempted during cached replay!")

    monkeypatch.setattr(skill_research_bridge, "_search_openalex_papers", mock_fail_search)
    monkeypatch.setattr(skill_research_bridge, "_search_crossref_papers", mock_fail_search)

    prompt_text = "Simulate E. coli fed-batch growth with acetate overflow"
    artifact, exit_code = skill_research_bridge.resolve_prompt_and_research(
        prompt_text, auto_research=True, launch_godot=False
    )
    assert exit_code == 0
    assert artifact["status"] == "COMPLETED"
    assert artifact["cache_hit"] is True
    assert len(artifact["literature_review_manifest"]["combined_papers"]) >= 1


def test_msc_dissertation_central_library_ingestion_and_simulation(library_store):
    """Verify that msc_dissertation_2025 loads from central_library.json and produces valid trajectories."""
    # 1. Paper metadata
    assert "msc_dissertation_2025" in library_store.papers
    paper = library_store.papers["msc_dissertation_2025"]
    assert "Films and Fibres" in paper.title
    assert paper.year == 2025
    assert paper.sha256 != ""

    # 2. Empirical parameters and direct biological context
    params = library_store.find_parameters_for_context(paper_id="msc_dissertation_2025")
    assert len(params) >= 9
    param_ids = {p.param_id: p for p in params}
    assert "msc_dissertation.yield_scaled_up" in param_ids
    scaled_yield = param_ids["msc_dissertation.yield_scaled_up"]
    assert scaled_yield.value == pytest.approx(0.3307, rel=1e-2)
    assert scaled_yield.biological_context.organism == "Saccharina latissima"
    assert scaled_yield.biological_context.evidence_tier == "DIRECT"

    # 3. Mechanism registration and explicit ports
    assert "msc_dissertation.bioprocess_kinetics" in library_store.mechanisms
    mech = library_store.mechanisms["msc_dissertation.bioprocess_kinetics"]
    in_ports = {p.port_id for p in mech.input_ports}
    out_ports = {p.port_id for p in mech.output_ports}
    assert {"t", "biomass"}.issubset(in_ports)
    assert {"product_yield", "feed_rate"}.issubset(out_ports)

    # 4. Reconstruction from prompt
    prompt_text = "Simulate Saccharina latissima seaweed alginate extraction and bioprocess kinetics with Morris mass balance."
    res = prompt.reconstruct_from_library(prompt_text)
    assert res["ok"] is True
    manifest = res["literature_review_manifest"]
    paper_ids = [p["paper_id"] for p in manifest["combined_papers"]]
    assert "msc_dissertation_2025" in paper_ids

    # 5. Simulation trajectory verification
    import sys
    model_pkg = ROOT / "composition" / "models" / "MscDissertation"
    if str(model_pkg) not in sys.path:
        sys.path.insert(0, str(model_pkg))
    from msc_dissertation_2025 import model
    traj = model.simulate_trajectory(duration_h=20.0, n_points=41)
    assert len(traj["time_hours"]) == 41
    assert traj["time_hours"][0] == 0.0
    assert traj["time_hours"][-1] == 20.0
    assert len(traj["product_yield_g_per_g"]) == 41
    # Yield starts at 0 and approaches asymptotic maximum (33%)
    assert traj["product_yield_g_per_g"][0] == 0.0
    assert traj["product_yield_g_per_g"][-1] == pytest.approx(0.3307, rel=1e-2)
    # Biomass decreases as polymer is extracted
    assert traj["biomass_g_per_L"][-1] < traj["biomass_g_per_L"][0]
