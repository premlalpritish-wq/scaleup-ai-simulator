"""Scientific gap discovery: evidence, traceability and honest classification.

The tests pin the properties the feature claims:

* every gap is backed by an existing record;
* a paper's compatibility classification is never changed by relevance;
* existing papers are matched to the gaps they actually touch;
* missing information is never rendered as a value;
* every unresolved gap has a recommendation;
* the analysis works when the evidence is incomplete;
* refreshing it writes nothing under ``Models/``;
* the payload is complete enough for the Godot panel to render.

The last property is also exercised in Godot by
``composition/tests/godot/test_scientific_gap_panel.gd``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from composition import compatibility as compat
from composition import gaps

ROOT = Path(__file__).resolve().parents[2]

GROWTH_GAP = "GAP-MP-GROWTH-KINETICS"
OXYGEN_GAP = "GAP-MP-OXYGEN-TRANSFER"
MEDIUM_GAP = "GAP-MP-CULTURE-MEDIUM"
FOLDING_GAP = "GAP-MP-FOLDING-MODEL"
BIO_GAP = gaps.GAP_BIOLOGICAL_CONTEXT
VALIDATION_GAP = gaps.GAP_INDEPENDENT_VALIDATION
COMPOSITION_GAP = gaps.GAP_COMPOSITION_BOUNDARY


@pytest.fixture(scope="module")
def analysis() -> dict:
    return gaps.analyse()


def _gap(analysis: dict, gap_id: str) -> dict:
    for gap in analysis["gaps"]:
        if gap["gap_id"] == gap_id:
            return gap
    raise AssertionError(f"gap {gap_id!r} was not generated")


def test_every_gap_is_evidence_backed_and_names_what_is_missing(analysis):
    assert len(analysis["gaps"]) == 12
    for gap in analysis["gaps"]:
        gap_id = gap["gap_id"]
        assert gap["category"] in gaps.CATEGORY_IDS, gap_id
        assert gap["description"].strip(), gap_id
        assert gap["why_it_matters"].strip(), gap_id
        assert gap["variables"], gap_id
        assert gap["missing_evidence"], gap_id
        assert gap["search_terms"], gap_id
        assert gap["existing_evidence"], gap_id
        for entry in gap["existing_evidence"]:
            source = ROOT / entry["source"]
            assert source.exists(), f"{gap_id}: missing source {source}"
            assert entry["statement"].strip(), gap_id
            assert entry["location"].strip(), gap_id


def test_all_seven_categories_are_present(analysis):
    present = {gap["category"] for gap in analysis["gaps"]}
    assert present == set(gaps.CATEGORY_IDS)
    assert analysis["summary"]["by_category"] == {
        "model_parameters": 2,
        "experimental_measurements": 2,
        "biological_context": 1,
        "process_conditions": 3,
        "mathematical_relationships": 2,
        "independent_validation": 1,
        "composition_blockers": 1,
    }


def test_existing_compatibility_classifications_are_preserved(analysis):
    expected = {
        assessment.key: (
            assessment.classification.value,
            assessment.classification_number,
            assessment.contributes,
        )
        for assessment in compat.ASSESSMENTS
    }
    assert len(analysis["papers"]) == len(expected)
    for paper in analysis["papers"]:
        assert paper["key"] in expected
        assert (
            paper["classification"],
            paper["classification_number"],
            paper["contributes"],
        ) == expected[paper["key"]]
    assert analysis["summary"]["classifications"] == {
        "dynamically_composable": 1,
        "contextually_relevant_not_composable": 5,
        "incompatible": 1,
    }
    assert analysis["role_legend"]["note"].startswith("No assessed paper")


def test_papers_are_matched_to_the_gaps_they_actually_touch(analysis):
    growth = _gap(analysis, GROWTH_GAP)
    oxygen = _gap(analysis, OXYGEN_GAP)
    medium = _gap(analysis, MEDIUM_GAP)

    assert set(growth["partly_addressed_by"]) == {
        "ganjave", "baez", "lin", "nanchen",
    }
    assert set(oxygen["partly_addressed_by"]) == {"baez", "lin"}
    assert medium["partly_addressed_by"] == []
    assert FOLDING_GAP in {gap["gap_id"] for gap in analysis["gaps"]}

    for gap in analysis["gaps"]:
        keys = [paper["key"] for paper in gap["papers"]]
        assert "zielinski" in keys, gap["gap_id"]
        baseline = next(p for p in gap["papers"] if p["key"] == "zielinski")
        assert baseline["relation"] == "defines_gap"

    # Simensen is relevant to biological context, but it is not a partial answer
    # to the growth-parameter gap.
    assert "simensen" in [p["key"] for p in _gap(analysis, BIO_GAP)["papers"]]
    assert "simensen" not in growth["partly_addressed_by"]

    profiles = {paper["key"]: paper for paper in analysis["papers"]}
    assert set(profiles["ganjave"]["partially_addressed_gaps"]) == {GROWTH_GAP}
    assert GROWTH_GAP not in profiles["ganjave"]["unresolved_gaps"]
    assert FOLDING_GAP in profiles["ganjave"]["unresolved_gaps"]


def test_missing_information_is_never_represented_as_known(analysis):
    assert analysis["summary"]["fully_addressed"] == 0
    assert analysis["summary"]["unresolved"] == len(analysis["gaps"])
    for gap in analysis["gaps"]:
        assert gap["status"] != "addressed", gap["gap_id"]
        assert gap.get("value") is None, gap["gap_id"]
        assert gap["missing_evidence"], gap["gap_id"]
        for paper in gap["papers"]:
            assert paper["remains_missing"].strip(), gap["gap_id"]
        if gap["status"] == "partially_addressed":
            assert gap["partly_addressed_by"], gap["gap_id"]


def test_recommendations_are_generated_for_every_unresolved_gap(analysis):
    for gap in analysis["gaps"]:
        if gap["status"] == "addressed":
            continue
        recommendation = gap["recommendation"]
        assert recommendation["gap_id"] == gap["gap_id"]
        assert recommendation["what_information_is_needed"]
        assert recommendation["why_it_is_needed"].strip()
        assert recommendation["suitable_paper_must_report"]
        assert recommendation["search_terms"] == gap["search_terms"]
        assert recommendation["what_scaleup_can_do"].strip()
    assert len(analysis["recommendations"]) == len(analysis["gaps"])


def test_the_analysis_works_with_incomplete_evidence():
    payload = gaps.analyse(model_graph={}, assessments=(), paper_records=())
    assert payload["gaps"], "the biological, validation and composition gaps must survive"
    assert payload["summary"]["papers_assessed"] == 0
    assert payload["summary"]["fully_addressed"] == 0
    assert payload["summary"]["partially_addressed"] == 0
    assert all(gap["status"] == "unresolved" for gap in payload["gaps"])
    assert any("missing or unreadable" in warning for warning in payload["warnings"])
    assert any("No compatibility assessments" in warning for warning in payload["warnings"])
    for gap in payload["gaps"]:
        assert gap["recommendation"], gap["gap_id"]


def test_refreshing_does_not_modify_the_scientific_models():
    watched = [
        gaps.MODEL_GRAPH,
        gaps.MODEL_SOURCE,
        gaps.MODEL_REPORT,
        gaps.MODEL_SUMMARY,
        gaps.COMPATIBILITY_SOURCE,
        gaps.PAPERS_SOURCE,
        gaps.EVIDENCE_SOURCE,
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}
    first = gaps.analyse()
    second = gaps.analyse()
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}
    assert before == after
    assert first["analysis_digest"] == second["analysis_digest"]
    assert first["traceability"]["read_only"] is True
    assert first["traceability"]["model_artifacts_written"] == []


def test_payload_has_the_fields_the_godot_panel_renders(analysis):
    for key in (
        "contract_version", "target", "claim_scope", "summary", "categories",
        "gaps", "papers", "recommendations", "prior_literature_search",
        "role_legend", "warnings", "traceability", "analysis_digest",
    ):
        assert key in analysis, key
    assert analysis["target"]["label"] == "Zielinski insulin production"
    assert analysis["target"]["model_id"] == compat.TARGET_MODEL
    for gap in analysis["gaps"]:
        for key in (
            "gap_id", "category", "category_title", "description",
            "why_it_matters", "variables", "existing_evidence",
            "missing_evidence", "search_terms", "composition_enabling",
            "validation_improving", "status", "papers", "recommendation",
        ):
            assert key in gap, f"{gap['gap_id']}: {key}"
        for paper in gap["papers"]:
            for key in (
                "citation", "classification", "classification_number",
                "classification_label", "relation", "relevance",
                "what_information_it_contributes", "what_remains_missing",
            ):
                assert key in paper, f"{gap['gap_id']}: paper {key}"
    # The payload must be valid JSON before Godot sees it.
    json.dumps(analysis)
    assert gaps.problems(analysis) == []


def test_the_check_command_passes():
    completed = subprocess.run(
        [sys.executable, "-m", "composition.gaps", "--check"],
        cwd=ROOT / "composition",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout
