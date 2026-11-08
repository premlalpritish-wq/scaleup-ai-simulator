"""The seven-model compatibility assessment must be complete and self-consistent.

Nothing here asserts a scientific verdict of its own. The claim is narrower and
checkable: every model in the project is assessed, exactly one is the baseline,
the classifications come from the closed vocabulary, a model is reported as
contributing only when the engine permits a connection for it, and a registered
model's verdict is the one ``cross_model`` already declares rather than a second
opinion written here.
"""

from __future__ import annotations

import pytest

from composition import compatibility as compat
from composition import cross_model
from composition.adapters import REGISTRATIONS
from composition.evidence import papers as coverage


EXPECTED_KEYS = (
    "zielinski", "ganjave", "morris", "baez", "lin", "nanchen", "simensen",
)


def test_all_seven_models_are_assessed():
    assert tuple(a.key for a in compat.ASSESSMENTS) == EXPECTED_KEYS


def test_exactly_one_baseline_and_it_is_the_target_model():
    baselines = [a for a in compat.ASSESSMENTS if a.is_baseline]
    assert len(baselines) == 1
    assert baselines[0].model_id == compat.TARGET_MODEL
    assert baselines[0].classification is compat.Classification.DYNAMICALLY_COMPOSABLE
    assert baselines[0].contributes


def test_every_classification_comes_from_the_closed_vocabulary():
    assert compat.problems()["unknown_classifications"] == []
    for assessment in compat.ASSESSMENTS:
        assert assessment.classification.value in compat.CLASSIFICATION_VALUES
        assert 1 <= assessment.classification_number <= 5


def test_no_model_reached_evidence_compatibility_and_each_states_why():
    counts = compat.summary()["counts"]
    assert sum(counts.values()) == 7
    assert counts[compat.Classification.EVIDENCE_COMPATIBLE.value] == 0
    assert all(a.evidence_check for a in compat.ASSESSMENTS if not a.is_baseline)


def test_only_the_baseline_contributes_and_the_rest_are_evidence_only():
    assert [a.key for a in compat.contributors()] == ["zielinski"]
    assert {a.key for a in compat.evidence_only()} == set(EXPECTED_KEYS) - {"zielinski"}


@pytest.mark.parametrize("assessment", compat.ASSESSMENTS, ids=lambda a: a.key)
def test_every_assessment_is_explained_with_evidence(assessment):
    assert assessment.summary.strip()
    assert len(assessment.evidence) >= 2
    assert assessment.paper.strip()
    assert assessment.paper_folder.strip()
    assert assessment.inspection is not None
    assert set(assessment.inspection.to_dict()) == {
        "organism", "context", "inputs", "outputs", "units", "equations",
        "parameters", "time_scale", "assumptions",
    }


@pytest.mark.parametrize(
    "assessment",
    [a for a in compat.ASSESSMENTS if not a.contributes],
    ids=lambda a: a.key,
)
def test_a_model_that_cannot_contribute_says_why(assessment):
    assert assessment.blockers, f"{assessment.key} states no blocker"
    assert assessment.remediation.strip()


def test_the_baseline_has_no_blockers():
    assert compat.target().blockers == ()


@pytest.mark.parametrize("key", ["ganjave", "morris"])
def test_a_registered_model_verdict_is_read_from_cross_model(key: str):
    assessment = compat.by_key(key)
    boundary = compat._boundary_between(assessment.model_id)
    assert boundary is not None
    assert assessment.cross_model_stance == boundary.stance
    assert assessment.cross_model_evidence_basis == boundary.evidence_basis
    assert boundary.permitted is False


@pytest.mark.parametrize("key", ["baez", "lin", "nanchen", "simensen"])
def test_an_unregistered_model_claims_no_cross_model_stance(key: str):
    assessment = compat.by_key(key)
    assert not assessment.registered
    assert assessment.cross_model_stance == ""


def test_the_registry_and_the_assessment_cover_the_same_models():
    assert compat.problems()["registered_models_not_assessed"] == []
    assessed_ids = {a.model_id for a in compat.ASSESSMENTS if a.registered}
    assert assessed_ids == {reg.model_id for reg in REGISTRATIONS}


def test_every_assessed_paper_is_in_the_corpus_index():
    assert compat.problems()["unknown_paper_folders"] == []
    recorded = {paper.folder for paper in coverage.PAPERS}
    for assessment in compat.ASSESSMENTS:
        assert assessment.paper_folder in recorded


def test_the_assessment_reports_no_problems_on_this_repository():
    report = compat.problems()
    assert compat.problem_messages(report) == []


def test_the_check_command_passes():
    assert compat.main(["--check"]) == 0


def test_permitted_connections_are_exactly_the_engine_s_permitted_boundaries():
    expected = [
        (b.source_model, b.target_model)
        for b in cross_model.BOUNDARIES
        if b.permitted
    ]
    actual = [
        (c["source_model"], c["target_model"])
        for c in compat.permitted_connections()
    ]
    assert actual == expected


def test_no_permitted_connection_touches_the_insulin_process():
    """The core finding: the target has no incoming or outgoing legal edge."""
    touching = [c for c in compat.permitted_connections() if c["touches_target"]]
    assert touching == []
    assert compat.summary()["connections_touching_target"] == []


def test_a_contribution_without_a_permitted_boundary_is_reported(monkeypatch):
    """The guard must be able to fail, or the 'no connection' finding is vacuous."""
    baseline = compat.Assessment(
        key="zielinski",
        display_name="baseline",
        role="baseline",
        classification=compat.Classification.DYNAMICALLY_COMPOSABLE,
        contributes=True,
        summary="baseline",
        paper="p",
        paper_folder="Zielinski",
        package="Models/Zielinski",
        model_id=compat.TARGET_MODEL,
        model_version=compat.TARGET_MODEL_VERSION,
        inspection=compat._ZIELINSKI_INSPECTION,
        evidence=("a", "b"),
    )
    fabricated_claim = compat.Assessment(
        key="baez",
        display_name="Baez, but claimed as a contributor",
        role="candidate",
        classification=compat.Classification.DYNAMICALLY_COMPOSABLE,
        contributes=True,
        summary="claims to contribute",
        paper="Baez et al. (2014)",
        paper_folder="Baez",
        package="Models/Baez",
        inspection=compat._BAEZ_INSPECTION,
        evidence=("a", "b"),
        evidence_check="none",
    )
    monkeypatch.setattr(compat, "ASSESSMENTS", (baseline, fabricated_claim))
    report = compat.problems()
    assert "baez" in report["unsupported_contributions"]


def test_an_unknown_key_raises_rather_than_inventing_an_assessment():
    with pytest.raises(KeyError):
        compat.by_key("no-such-model")


def test_describe_is_a_complete_document():
    payload = compat.describe()
    assert payload["target"]["model_id"] == compat.TARGET_MODEL
    assert len(payload["assessments"]) == 7
    assert payload["summary"]["assessed"] == 7
    assert payload["connections"]["touching_target"] == []
    assert payload["connections"]["note"]
    assert payload["claim_scope"]


def test_paper_for_model_attributes_each_registered_model():
    assert compat.paper_for_model("ganjave").paper_folder == "Ganjave"
    assert compat.paper_for_model("zielinski2019.rhi_process").is_baseline
    assert compat.paper_for_model("not.a.model") is None
    assert compat.paper_for_model("") is None

