"""Tests for the research-to-simulation workflow.

The suite is deliberately offline.  It uses the shipped pecan corpus, which is
real open-access JATS XML, and never calls Europe PMC or any other live service.
Every failure test asserts that the workflow stops instead of filling a gap.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from composition.adapters import REGISTRATIONS, known_models
from composition.workflow.encoding import EncodingError, encode
from composition.workflow.execute import run_workflow
from composition.workflow.extract import (
    ExtractionError,
    extract_document,
    extract_pdf,
    find_quote,
)
from composition.workflow.literature import discover, load_corpus
from composition.workflow.model_builder import build_model_spec
from composition.workflow.problem import parse_problem

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ROOT = ROOT / "composition"
FIXTURES = (
    COMPOSITION_ROOT
    / "composition"
    / "workflow"
    / "fixtures"
    / "pecan"
)
PROBLEM = FIXTURES / "problem.json"
CORPUS = FIXTURES / "sources.json"
PASSAGES = FIXTURES / "passages.json"

TARGET_SOURCE = "pecan_miRNome"
ANALOGUE_SOURCES = {"spruce_rna", "pigeonpea_rna"}
METHOD_SOURCES = {"modified_ctab", "difficult_species"}

DIRECT_STEPS = {
    "pecan_sample_handling",
    "pecan_trizol_extraction",
    "pecan_dnase_treatment",
    "pecan_quality_assessment",
    "pecan_small_rna_enrichment",
    "pecan_cdna_synthesis",
}


def _documents() -> dict:
    return {
        source_id: extract_document(
            FIXTURES / source.file, source_id
        )
        for source in load_corpus(CORPUS)
        for source_id in [source.source_id]
    }


def _passages_payload() -> dict:
    return json.loads(PASSAGES.read_text(encoding="utf-8"))


def _write_passages(path: Path, payload: dict) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _payload(run_dir: Path) -> dict:
    return json.loads(
        (run_dir / "workflow_result.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def run_dir() -> Path:
    """A writable scratch directory inside the repository.

    The system temp directory is not writable on every host, and the rest of
    this suite already avoids ``tmp_path`` for that reason.
    """
    base = COMPOSITION_ROOT / ".artifacts" / "research-workflow"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------- problem input


def test_pecan_problem_is_parsed_without_guessing() -> None:
    from composition.workflow.problem import load_problem

    problem = load_problem(PROBLEM).problem
    assert problem.blocked is False
    assert problem.organism.value == "Carya illinoinensis"
    assert problem.tissue.value == "embryo"
    assert problem.molecule.value == "total RNA"
    assert "small RNA sequencing" in problem.downstream
    assert "transcriptome sequencing" in problem.downstream
    assert problem.problem_id.startswith("problem-")
    assert problem.unknowns == ()


def test_a_problem_without_an_organism_or_molecule_is_blocked() -> None:
    problem = parse_problem("Extract RNA from the tissue.").problem
    assert problem.blocked is True
    assert "organism" in problem.unknowns
    assert "target molecule" in problem.unknowns


def test_a_blocked_problem_stops_before_literature(
    run_dir: Path,
) -> None:
    problem_path = run_dir / "problem.json"
    problem_path.write_text(
        json.dumps({"text": "Extract RNA from the tissue."}),
        encoding="utf-8",
    )
    payload, code = run_workflow(problem_path, out_dir=run_dir / "run")
    assert code == 3
    assert payload["status"] == "invalid"
    assert payload["workflow_status"] == "blocked"
    assert payload["sources"] == []
    assert payload["model"] is None
    assert payload["artifacts"]["problem_spec"].endswith("problem_spec.json")
    assert "literature_manifest" not in payload["artifacts"]


# ------------------------------------------------------------------ extraction


def test_jats_extraction_preserves_the_source_and_locates_sections() -> None:
    document = extract_document(
        FIXTURES / "sources" / "pecan_miRNome.xml", TARGET_SOURCE
    )
    assert document.extraction_method == "jats_xml_stdlib"
    assert len(document.sections) > 10
    assert "Following the removal of the pericarp and seed coat" in document.text
    start, end, section = find_quote(
        document,
        "genomic DNA contamination was eliminated using RNase-free DNase I",
    )
    assert (start, end) == (start, start + len(
        "genomic DNA contamination was eliminated using RNase-free DNase I"
    ))
    assert section is not None
    assert "2.5. RNA Isolation" in section.path


def test_a_missing_quote_raises_instead_of_softening_it() -> None:
    document = extract_document(
        FIXTURES / "sources" / "pecan_miRNome.xml", TARGET_SOURCE
    )
    with pytest.raises(ExtractionError, match="quote not found"):
        find_quote(document, "this sentence was never printed in the paper")


def test_pdf_extraction_fails_explicitly_without_pypdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(ExtractionError, match="pypdf"):
        extract_pdf(Path("does-not-exist.pdf"), "example")


# ----------------------------------------------------------------- literature


def test_the_target_source_is_always_selected_and_analogues_are_ranked() -> None:
    problem = __import__(
        "composition.workflow.problem", fromlist=["load_problem"]
    ).load_problem(PROBLEM).problem
    sources = load_corpus(CORPUS)
    discovery = discover(problem, sources)
    by_id = {item["source_id"]: item for item in discovery}
    assert by_id[TARGET_SOURCE]["selected"] is True
    assert by_id[TARGET_SOURCE]["role"] == "target_organism"
    for source_id in ANALOGUE_SOURCES:
        assert by_id[source_id]["selected"] is True
        assert by_id[source_id]["score"] > 0
        assert by_id[source_id]["reasons"]
    assert set(by_id) == {
        "pecan_miRNome",
        "spruce_rna",
        "pigeonpea_rna",
        "modified_ctab",
        "difficult_species",
    }


# -------------------------------------------------------------------- encoding


def test_every_quote_and_number_is_verified_and_specificity_is_separated() -> None:
    from composition.workflow.problem import load_problem

    problem = load_problem(PROBLEM).problem
    encoded = encode(problem, _documents(), PASSAGES)
    assert encoded.verification["quotes_checked"] == 25
    assert encoded.verification["quotes_verified"] == 25
    assert encoded.verification["numeric_values_checked"] == 66
    assert encoded.verification["numeric_values_verified"] == 66
    assert encoded.verification["failures"] == []

    direct = [c for c in encoded.claims if c.specificity == "target_organism"]
    analogue = [
        c for c in encoded.claims if c.specificity == "analogous_species"
    ]
    method = [c for c in encoded.claims if c.specificity == "method_review"]
    assert len(direct) == 6
    assert {c.source_id for c in direct} == {TARGET_SOURCE}
    assert {c.source_id for c in analogue} == ANALOGUE_SOURCES
    assert {c.source_id for c in method} == METHOD_SOURCES
    assert all(not c.hypothesis for c in direct)
    assert all(c.quote for c in encoded.claims)

    steps = {step.step_id: step for step in encoded.steps}
    for step_id in DIRECT_STEPS:
        assert steps[step_id].evidence_status == "direct_target_evidence"
        assert steps[step_id].source_ids == (TARGET_SOURCE,)
    for step_id, step in steps.items():
        if step_id in DIRECT_STEPS:
            continue
        assert step.evidence_status in {
            "analogous_species_hypothesis",
            "method_review_only",
        }
        assert TARGET_SOURCE not in step.source_ids


def test_a_changed_quote_stops_encoding(run_dir: Path) -> None:
    from composition.workflow.problem import load_problem

    payload = _passages_payload()
    payload["passages"][0]["quote"] += " (an unprinted addition)"
    bad = _write_passages(run_dir / "passages.json", payload)
    with pytest.raises(EncodingError, match="quote not found"):
        encode(load_problem(PROBLEM).problem, _documents(), bad)


def test_an_untraceable_number_stops_encoding(run_dir: Path) -> None:
    from composition.workflow.problem import load_problem

    payload = _passages_payload()
    parameters = payload["passages"][0]["parameters"]
    target = next(p for p in parameters if p.get("value_text"))
    target["value"] = 999
    target.pop("value_text", None)
    bad = _write_passages(run_dir / "passages.json", payload)
    with pytest.raises(EncodingError, match="does not appear in its own quote"):
        encode(load_problem(PROBLEM).problem, _documents(), bad)


def _roles() -> dict[str, str]:
    return {source.source_id: source.role for source in load_corpus(CORPUS)}


def test_analogue_evidence_cannot_be_relabelled_as_direct_target(
    run_dir: Path,
) -> None:
    """A spruce protocol must never masquerade as a pecan measurement."""

    from composition.workflow.problem import load_problem

    payload = _passages_payload()
    spruce = next(
        passage
        for passage in payload["passages"]
        if passage["source_id"] in ANALOGUE_SOURCES
    )
    spruce["specificity"] = "target_organism"
    spruce["organism"] = "Carya illinoinensis"
    bad = _write_passages(run_dir / "passages.json", payload)

    with pytest.raises(EncodingError, match="cannot be relabelled"):
        encode(load_problem(PROBLEM).problem, _documents(), bad, _roles())


def test_a_target_claim_must_name_the_requested_organism(run_dir: Path) -> None:
    from composition.workflow.problem import load_problem

    payload = _passages_payload()
    direct = next(
        passage
        for passage in payload["passages"]
        if passage["source_id"] == TARGET_SOURCE
        and passage["specificity"] == "target_organism"
    )
    direct["organism"] = "Picea abies"
    bad = _write_passages(run_dir / "passages.json", payload)

    with pytest.raises(EncodingError, match="but the problem asks about"):
        encode(load_problem(PROBLEM).problem, _documents(), bad, _roles())


def test_the_workflow_enforces_the_source_role_ceiling() -> None:
    from composition.workflow.problem import load_problem

    problem = load_problem(PROBLEM).problem
    encoded = encode(problem, _documents(), PASSAGES, _roles())
    assert encoded.verification["source_role_check"] == "enforced"
    for claim in encoded.claims:
        if claim.specificity == "target_organism":
            assert claim.source_id == TARGET_SOURCE
        elif claim.source_id == TARGET_SOURCE:
            assert claim.specificity == "target_organism"


# --------------------------------------------------------------- model building


def test_model_keeps_target_and_analogue_findings_apart() -> None:
    from composition.workflow.problem import load_problem

    problem = load_problem(PROBLEM).problem
    encoded = encode(problem, _documents(), PASSAGES)
    model = build_model_spec(
        problem, encoded, load_corpus_acquired()
    )
    readiness = model.readiness
    assert readiness["direct_target_claim_count"] == 6
    assert readiness["analogue_claim_count"] == 17
    assert readiness["method_review_claim_count"] == 2
    assert readiness["protocol_complete_for_target"] is False
    assert readiness["quantitative_yield_available_for_target"] is False
    assert readiness["analogue_protocol_available"] is True
    assert readiness["unresolved_parameter_count"] == 18
    assert readiness["reported_parameter_count"] == 66

    unknown_text = " ".join(model.unknowns)
    for required in (
        "trizol_volume",
        "elution_volume",
        "rna_yield",
        "rin",
    ):
        assert required in unknown_text
    assert "no target-organism RNA yield" in unknown_text

    hypotheses = " ".join(model.hypotheses)
    assert "not been validated on the target organism" in hypotheses
    assert "spruce_rna" in hypotheses
    assert "pigeonpea_rna" in hypotheses
    assert any("modified ctab" in step.label.lower() for step in model.steps)


def load_corpus_acquired():
    """Acquire the corpus without writing text artifacts, for unit tests."""
    from dataclasses import replace

    from composition.workflow.literature import acquire_selected

    corpus = load_corpus(CORPUS)
    selected = [source.source_id for source in corpus]
    acquired, _ = acquire_selected(
        selected, corpus, CORPUS.parent, CORPUS.parent / ".unused"
    )
    # The helper is only used to attach hashes and acquisition status; the
    # caller does not need the text written next to the fixture.
    return [replace(source) for source in acquired]


# --------------------------------------------------------------- end to end


def test_pecan_workflow_runs_end_to_end(run_dir: Path) -> None:
    out = run_dir / "pecan"
    payload, code = run_workflow(PROBLEM, out_dir=out, base=ROOT)
    assert code == 0
    assert payload["status"] == "success"
    assert payload["workflow_status"] == "completed"
    assert payload["error_count"] == 0

    artifacts = payload["artifacts"]
    for key in (
        "problem_spec",
        "literature_manifest",
        "research_encoded",
        "model_spec",
        "composition_graph",
        "simulation_result",
        "workflow_result",
    ):
        assert key in artifacts
        assert Path(artifacts[key]).is_file()

    literature = json.loads(
        Path(artifacts["literature_manifest"]).read_text(encoding="utf-8")
    )
    assert literature["selected_source_ids"] == [
        "pecan_miRNome",
        "spruce_rna",
        "pigeonpea_rna",
        "modified_ctab",
        "difficult_species",
    ]
    assert all(
        item["status"] == "acquired" for item in literature["acquisition"]
    )
    assert len(literature["sources"]) == 5

    encoded = json.loads(
        Path(artifacts["research_encoded"]).read_text(encoding="utf-8")
    )
    assert encoded["verification"]["quotes_verified"] == 25
    assert encoded["verification"]["numeric_values_verified"] == 66

    model = json.loads(
        Path(artifacts["model_spec"]).read_text(encoding="utf-8")
    )
    assert model["model_kind"] == "evidence_constrained_protocol_audit"
    assert model["readiness"]["quantitative_yield_available_for_target"] is False
    assert model["readiness"]["unresolved_parameter_count"] == 18

    graph = json.loads(
        Path(artifacts["composition_graph"]).read_text(encoding="utf-8")
    )
    assert len(graph["instances"]) == 1
    assert graph["connections"] == []
    assert graph["instances"][0]["model_id"] == "pecan_rna_evidence_audit"

    outputs = {
        result["outputs"][index]["ref"]["port_id"]: result["outputs"][index][
            "value"
        ]["value"]
        for result in payload["execution"]["results"]
        for index in range(len(result["outputs"]))
    }
    assert outputs["claim_count"] == 25.0
    assert outputs["direct_target_claim_count"] == 6.0
    assert outputs["analogue_claim_count"] == 17.0
    assert outputs["unresolved_parameter_count"] == 18.0
    assert outputs["quantitative_yield_available_for_target"] == 0.0
    assert outputs["protocol_complete_for_target"] == 0.0
    assert outputs["analogue_protocol_available"] == 1.0

    # No pecan yield, RIN or degradation prediction is fabricated as an output.
    for forbidden in ("predicted_yield", "degradation_rate", "yield_ug", "rin"):
        assert all(forbidden not in key.lower() for key in outputs)


def test_workflow_is_deterministic(run_dir: Path) -> None:
    first_dir = run_dir / "first"
    second_dir = run_dir / "second"
    first, first_code = run_workflow(PROBLEM, out_dir=first_dir, base=ROOT)
    second, second_code = run_workflow(PROBLEM, out_dir=second_dir, base=ROOT)
    assert (first_code, second_code) == (0, 0)
    for key in ("problem", "encoded", "model", "graph", "execution"):
        assert first[key] == second[key], key
    assert first["diagnostics"] == second["diagnostics"]
    assert first["status"] == second["status"]


def test_cli_runs_the_workflow_and_writes_a_result(run_dir: Path) -> None:
    out = run_dir / "cli"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "composition.runner",
            "--run-workflow",
            str(PROBLEM),
            "--workflow-out",
            str(out),
            "--repo-root",
            str(ROOT),
        ],
        cwd=str(COMPOSITION_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    payload = json.loads(completed.stdout)
    assert payload["status"] == "success"
    assert payload["model"]["model_id"] == "pecan_rna_evidence_audit"
    assert (out / "workflow_result.json").is_file()


def test_the_generated_model_is_not_added_to_the_global_registry() -> None:
    model_ids = {registration.model_id for registration in REGISTRATIONS}
    assert model_ids == {
        "morris2011.material_balance",
        "zielinski2019.rhi_process",
        "ganjave",
    }
    assert "pecan_rna_evidence_audit" not in model_ids
    assert all(
        item["model_id"] != "pecan_rna_evidence_audit"
        for item in known_models(ROOT)
    )


def test_source_hashes_match_the_shipped_bytes() -> None:
    for source in load_corpus(CORPUS):
        path = CORPUS.parent / source.file
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest
        assert path.is_file()


def test_the_godot_screen_uses_the_existing_python_boundary() -> None:
    """Static guard: the UI ships, and it reaches Python only through runner.gd.

    The live scene is checked by
    ``godot --headless --path . --script
    res://composition/tests/godot/research_workflow_scene.gd``.
    This test keeps the files present and the boundary direction intact when
    Godot is not installed.
    """

    scene = ROOT / "scenes" / "research_workflow.tscn"
    script = ROOT / "scripts" / "research_workflow.gd"
    runner = ROOT / "scripts" / "runner.gd"
    workshop = ROOT / "scripts" / "workshop.gd"
    for path in (scene, script, runner, workshop):
        assert path.is_file(), path

    runner_text = runner.read_text(encoding="utf-8")
    assert "func run_research_workflow(" in runner_text
    assert '"--run-workflow"' in runner_text
    assert '"--workflow-out"' in runner_text

    script_text = script.read_text(encoding="utf-8")
    assert "_runner.run_research_workflow(" in script_text
    assert "workflow_result.json" in script_text
    # The screen reads documents; it does not build a graph or run a model.
    for forbidden in ("run_graph(", "CompositionEngine", "Popen"):
        assert forbidden not in script_text

    workshop_text = workshop.read_text(encoding="utf-8")
    assert "_on_research_pressed" in workshop_text
    assert "res://scenes/research_workflow.tscn" in workshop_text
