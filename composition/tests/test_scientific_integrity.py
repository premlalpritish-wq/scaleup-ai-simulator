"""Scientific integrity, zero-hallucination guardrails, and evidence tier enforcement tests."""
from __future__ import annotations

from pathlib import Path
import pytest

from composition import prompt
from composition.prompt import (
    BioprocessDomain,
    DomainMismatchError,
    InsufficientEvidenceError,
    classify_bioprocess_domain,
    detect_organism,
    reconstruct_from_library,
)
from composition.evidence.library_store import (
    EvidenceTier,
    CompatibilityEdgeTier,
    compute_confidence_score,
    get_library_store,
)
from composition.workflow.skill_research_bridge import (
    resolve_prompt_and_research,
    _solve_simulation_trajectories,
)

ROOT = Path(__file__).resolve().parents[2]


def test_domain_compatibility_classifier():
    """Verify classification of bioprocess operational domains."""
    # Solid-liquid extraction
    assert classify_bioprocess_domain("Simulate seaweed alginate solid-liquid extraction kinetics") == BioprocessDomain.SOLID_LIQUID_EXTRACTION
    assert classify_bioprocess_domain("Plant maceration and polyphenols extraction from kelp") == BioprocessDomain.SOLID_LIQUID_EXTRACTION

    # Microbial fermentation
    assert classify_bioprocess_domain("E. coli fed-batch fermentation with Ganjave kinetics") == BioprocessDomain.MICROBIAL_FERMENTATION
    assert classify_bioprocess_domain("Chemostat continuous culture with Pirt maintenance") == BioprocessDomain.MICROBIAL_FERMENTATION

    # Enzymatic hydrolysis
    assert classify_bioprocess_domain("Cellulase enzymatic hydrolysis and saccharification") == BioprocessDomain.ENZYMATIC_HYDROLYSIS

    # Chemical synthesis
    assert classify_bioprocess_domain("Catalytic chemical synthesis of biofuels") == BioprocessDomain.CHEMICAL_SYNTHESIS


def test_organism_detection():
    """Verify robust organism detection without false positives on English verbs/stop words."""
    assert detect_organism("Simulate Saccharina latissima alginate extraction") == "Saccharina latissima"
    assert detect_organism("Fed-batch growth of Escherichia coli in minimal medium") == "Escherichia coli"
    assert detect_organism("Chlorella vulgaris lipid accumulation kinetics") == "Chlorella vulgaris"
    assert detect_organism("Artemisia annua extraction of artemisinin") == "Artemisia annua"

    # Ensure English prompt starter words are never treated as Latin organism names
    assert detect_organism("Set the starting medium volume to 5 L and show growth.") == "Unknown Organism"


def test_domain_mismatch_rejection():
    """Verify that applying microbial fermentation models to solid-liquid extraction is strictly blocked."""
    # Attempting to model solid-liquid extraction with Ganjave growth kinetics
    with pytest.raises(DomainMismatchError) as exc_info:
        reconstruct_from_library(
            "Simulate seaweed alginate solid-liquid extraction using Ganjave growth kinetics and cybernetic regulation"
        )
    assert "Domain Mismatch" in str(exc_info.value)
    assert "cannot be modeled by microbial fermentation model" in str(exc_info.value)

    # Attempting to model solid-liquid extraction with Baez overflow metabolism
    with pytest.raises(DomainMismatchError) as exc_info2:
        reconstruct_from_library(
            "Solid-liquid extraction kinetics of kelp with Baez overflow metabolism and acetate feed"
        )
    assert "Domain Mismatch" in str(exc_info2.value)


def test_unindexed_unresearched_process_raises_insufficient_evidence():
    """Verify that an unindexed process cleanly hard-fails with InsufficientEvidenceError rather than fabricating data."""
    # Unindexed extraction process
    with pytest.raises(InsufficientEvidenceError) as exc_info:
        reconstruct_from_library(
            "Simulate plant maceration and artemisinin extraction from Artemisia annua",
        )
    err = str(exc_info.value)
    assert "Insufficient verified empirical literature found" in err
    assert "Central Knowledge Library lacks direct evidence" in err
    assert "Artemisia annua" in err

    # Unindexed fermentation process
    with pytest.raises(InsufficientEvidenceError) as exc_info2:
        reconstruct_from_library(
            "Simulate Chlorella vulgaris lipid accumulation kinetics in photobioreactor",
        )
    err2 = str(exc_info2.value)
    assert "Insufficient verified empirical literature found" in err2
    assert "Chlorella vulgaris" in err2


def test_failed_literature_search_aborts_without_hallucination(monkeypatch):
    """Verify that if literature search fails to return peer-reviewed evidence, execution is aborted."""
    # Mock external literature search to return empty records (simulating search failure)
    from composition.workflow import skill_research_bridge
    monkeypatch.setattr(skill_research_bridge, "_search_openalex_papers", lambda q, max_results=3: [])
    monkeypatch.setattr(skill_research_bridge, "_search_crossref_papers", lambda q, rows=3: [])

    with pytest.raises(InsufficientEvidenceError) as exc_info:
        resolve_prompt_and_research(
            "Simulate Streptomyces coelicolor actinorhodin antibiotic production",
            auto_research=True,
            launch_godot=False,
        )
    err = str(exc_info.value)
    assert "Insufficient verified empirical literature found" in err
    assert "Simulation aborted to prevent unverified scale-up predictions" in err


def test_verified_msc_dissertation_100_percent_fidelity():
    """Verify that MSc dissertation model executes with 100% direct evidence and empirical fidelity."""
    prompt_text = "Simulate Saccharina latissima alginate extraction and yield kinetics using the MSc dissertation model"
    result = reconstruct_from_library(prompt_text)

    assert result["ok"] is True
    assert result["confidence_score"] == 100.0
    assert result["has_analogue_bridge"] is False

    manifest = result["literature_review_manifest"]
    assert manifest["operational_domain"] == BioprocessDomain.SOLID_LIQUID_EXTRACTION
    assert manifest["target_organism"] == "Saccharina latissima"
    assert manifest["evidence_tier"] == "DIRECT"

    paper_ids = [p["paper_id"] for p in manifest["combined_papers"]]
    assert "msc_dissertation_2025" in paper_ids

    # Run solver
    traj = _solve_simulation_trajectories(manifest)
    assert traj["biomass_g_per_L"][0] == 20.0
    assert traj["product_yield_g_per_g"][-1] > 0.33  # 33.04% vs 33.07% empirical


def test_verified_ganjave_baez_fidelity():
    """Verify that indexed multi-paper E. coli fermentation runs with verified confidence score."""
    prompt_text = "Simulate E. coli fed-batch growth kinetics with Ganjave cybernetic model and Baez overflow metabolism."
    result = reconstruct_from_library(prompt_text)

    assert result["ok"] is True
    assert result["confidence_score"] > 0.0
    manifest = result["literature_review_manifest"]
    assert manifest["target_organism"] == "Escherichia coli"
    assert manifest["operational_domain"] == BioprocessDomain.MICROBIAL_FERMENTATION

    paper_ids = [p["paper_id"] for p in manifest["combined_papers"]]
    assert "ganjave2022" in paper_ids
    assert "baez2014" in paper_ids


def test_analogue_bridge_confidence_discount():
    """Verify that analogue bridges discount scientific confidence score and require expert review."""
    edges = [
        {"tier": CompatibilityEdgeTier.EXACT_MATCH},
        {"tier": CompatibilityEdgeTier.ANALOGUE_BRIDGE},
    ]
    score, tier, has_analogue = compute_confidence_score(edges)
    assert has_analogue is True
    assert tier == EvidenceTier.ANALOGUE_BRIDGE
    assert score == 85.0  # 100 - 15

    # Multiple analogue bridges
    edges_multi = [
        {"tier": CompatibilityEdgeTier.ANALOGUE_BRIDGE},
        {"tier": CompatibilityEdgeTier.ANALOGUE_BRIDGE},
    ]
    score2, tier2, has_analogue2 = compute_confidence_score(edges_multi)
    assert score2 == 70.0  # 100 - 30


def test_unverified_tier_blocks_solver():
    """Verify that unverified evidence tiers strictly prevent trajectory solver execution."""
    manifest = {
        "evidence_tier": "UNVERIFIED",
        "combined_papers": [],
    }
    with pytest.raises(InsufficientEvidenceError) as exc_info:
        _solve_simulation_trajectories(manifest)
    assert "Simulation solver blocked" in str(exc_info.value)


def test_gdscript_zero_hardcoded_model_strings():
    """Static analysis verifying that simulation GDScript files contain zero hardcoded paper/strain names."""
    import re

    forbidden_tokens = [
        "Baez",
        "Ganjave",
        "Zielinski",
        "Lin",
        "BL21",
        "W3110",
        "Biomass X",
        "Glucose S",
        "DO %",
        "Culture growth over time",
    ]

    target_files = [
        ROOT / "scripts" / "prompt_simulation.gd",
        ROOT / "scripts" / "replay_vessel_view.gd",
        ROOT / "scripts" / "growth_chart.gd",
    ]

    violations: list[str] = []
    for gd_file in target_files:
        assert gd_file.is_file(), f"Target GDScript not found: {gd_file}"
        text = gd_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            matches = list(re.finditer(r"\b" + re.escape(token) + r"\b", text))
            if matches:
                violations.append(f"{gd_file.name}: found {len(matches)} occurrences of '{token}'")

    assert not violations, "Forbidden hardcoded model/strain strings found in GDScript:\n" + "\n".join(violations)


def test_anatomy_blueprint_and_svg_generation(tmp_path):
    """Verify Stage 1 Anatomy Blueprint generation and SVG rendering for extraction and fermentation."""
    from composition.anatomy_engine import generate_anatomy_blueprint, generate_anatomy_svg

    # 1. Biopolymer solid-liquid extraction (MSc Saccharina latissima)
    bp_ext = generate_anatomy_blueprint("Simulate Saccharina latissima alginate extraction and yield kinetics using the MSc dissertation model")
    assert bp_ext["process_domain"] == "biopolymer_extraction"
    assert bp_ext["duration_hours"] == 40.0
    assert len(bp_ext["unit_operations"]) == 6
    stage_ids = [op["stage_id"] for op in bp_ext["unit_operations"]]
    assert stage_ids == [
        "dry_biomass_milling",
        "acid_demineralisation",
        "alkaline_solubilisation",
        "centrifugation_neutralisation",
        "ethanol_precipitation",
        "wet_spinning_mechanics",
    ]
    svg_out_ext = tmp_path / "extraction_anatomy.svg"
    p_ext = generate_anatomy_svg(bp_ext, svg_out_ext)
    assert p_ext.is_file() and p_ext.stat().st_size > 1000

    # 2. Microbial fermentation
    bp_ferm = generate_anatomy_blueprint("Simulate E. coli fed-batch growth with cybernetic kinetics")
    assert bp_ferm["process_domain"] == "microbial_fermentation"
    assert bp_ferm["duration_hours"] == 20.0
    assert len(bp_ferm["unit_operations"]) == 4
    ferm_stage_ids = [op["stage_id"] for op in bp_ferm["unit_operations"]]
    assert ferm_stage_ids == [
        "seed_inoculation",
        "exponential_fed_batch",
        "induction_overflow",
        "centrifugal_harvest",
    ]
    svg_out_ferm = tmp_path / "fermentation_anatomy.svg"
    p_ferm = generate_anatomy_svg(bp_ferm, svg_out_ferm)
    assert p_ferm.is_file() and p_ferm.stat().st_size > 1000

