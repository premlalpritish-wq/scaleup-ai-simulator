"""Coverage and model-fidelity gates for the paper -> model mapping.

Two questions, both answered from the tree rather than from a copy of it:

* **Coverage.** Does every paper in the corpus link to something -- a composed
  model, a standalone model, or an evidence-only record -- and does every
  standalone package exist, carry a manifest, and stay out of the composition
  registry?
* **Model fidelity.** Does each standalone package still match the paper it was
  built from, as judged by that package's own ``validate()`` (or, for the package
  that predates the gate, by its manifest snapshot and its own public API)?

Nothing here asserts a scientific verdict. The determinations and reasons belong
to :mod:`composition.evidence.papers`; the per-paper evidence belongs to each
package.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composition.adapters import REGISTRATIONS, known_models
from composition.evidence import papers as coverage
from composition.evidence import standalone


# --------------------------------------------------------------------------- #
# coverage: every paper links somewhere, and the links are real
# --------------------------------------------------------------------------- #


def test_the_three_way_split_covers_all_fifteen_papers():
    report = coverage.audit()
    execution = report["execution"]
    total = (
        len(execution["composable"])
        + len(execution["standalone"])
        + len(execution["evidence_only"])
    )
    assert total == len(report["papers"]) == 15


def test_the_split_is_exactly_what_this_step_produced():
    """Three composable, four standalone, eight evidence-only -- and no overlap."""
    execution = coverage.audit()["execution"]
    assert execution["composable"] == ["Ganjave", "Morris", "Zielinski"]
    assert execution["standalone"] == ["Baez", "Lin", "Simensen", "nanchen"]
    assert execution["evidence_only"] == [
        "Baez and Shiloach", "Bhattacharya", "Farrell", "Krause", "Lemuth",
        "Marish", "Mikiewicz", "Siew and Zhang",
    ]
    sets = [set(execution[k]) for k in execution]
    assert not (sets[0] & sets[1])
    assert not (sets[0] & sets[2])
    assert not (sets[1] & sets[2])


def test_every_paper_entry_links_to_a_model_or_a_record():
    for entry in coverage.audit()["papers"]:
        assert entry["link"], f"{entry['folder']} links nowhere"
        assert entry["link_kind"] in (
            "composed_model", "standalone_model", "evidence_only"
        )
        if entry["link_kind"] == "evidence_only":
            assert entry["evidence_record"]
            assert entry["evidence_record"].startswith("paper:")
        if entry["link_kind"] == "standalone_model":
            assert entry["standalone_module"]
            assert entry["standalone_kind"] in ("equation_model", "dataset_model")


def test_no_paper_entry_is_reported_as_both_composable_and_standalone():
    report = coverage.audit()
    assert report["conflicting_claims"] == []
    assert report["papers_without_a_link"] == []
    assert report["unlinked_model_packages"] == []
    assert report["orphan_standalone_entries"] == []


def test_the_coverage_check_passes_on_this_repository():
    assert coverage.main(["--check"]) == 0



# --------------------------------------------------------------------------- #
# the standalone registry agrees with the tree
# --------------------------------------------------------------------------- #


def test_the_standalone_registry_reports_no_structural_problems():
    report = standalone.problems()
    assert standalone.problem_messages(report) == []


def test_every_standalone_package_declares_a_paper_folder_the_corpus_has():
    recorded = {paper.folder for paper in coverage.PAPERS}
    for entry in standalone.STANDALONE_MODELS:
        assert entry.paper_folder in recorded


def test_every_standalone_entry_is_claimed_by_exactly_one_paper_record():
    for entry in standalone.STANDALONE_MODELS:
        claimants = [
            paper.folder
            for paper in coverage.PAPERS
            if paper.standalone is not None
            and paper.standalone.module == entry.module
        ]
        assert claimants == [entry.paper_folder], (
            f"{entry.module} is claimed by {claimants}"
        )


def test_the_standalone_registry_cli_passes():
    assert standalone.main(["--check", "--fidelity"]) == 0


# --------------------------------------------------------------------------- #
# model fidelity: each package against its own paper
# --------------------------------------------------------------------------- #


def test_every_standalone_model_passes_its_own_fidelity_checks():
    failures = standalone.fidelity_failures()
    assert failures == [], failures


@pytest.mark.parametrize(
    "entry",
    standalone.STANDALONE_MODELS,
    ids=[e.module for e in standalone.STANDALONE_MODELS],
)
def test_one_package_fidelity_report(entry: standalone.StandaloneModel):
    report = standalone.fidelity(entry)
    assert report["ok"], report["detail"]
    assert report["module"] == entry.module


def test_the_packages_with_a_validate_gate_run_more_than_one_check():
    """A gate that runs one trivial check is not a gate."""
    for entry in standalone.STANDALONE_MODELS:
        if not entry.validate_entry:
            continue
        report = standalone.fidelity(entry)
        assert len(report["checks"]) >= 5, (
            f"{entry.module} runs only {len(report['checks'])} checks"
        )
        assert all(c["detail"] for c in report["checks"])


def test_the_gate_can_fail(work_dir: Path):
    """The fidelity gate must be able to report a failure, or it is decoration."""
    entry = standalone.StandaloneModel(
        paper_folder="Imagined",
        package="Models/Imagined",
        module="imagined_model",
        artefact_id="imagined",
        kind="equation_model",
        scope="nothing",
    )
    report = standalone.fidelity(entry, base=work_dir)
    assert report["ok"] is False
    assert report["detail"]


# --------------------------------------------------------------------------- #
# standalone must not become composable
# --------------------------------------------------------------------------- #


def test_no_standalone_package_is_registered_with_the_composition_layer():
    registered_ids = {reg.model_id for reg in REGISTRATIONS}
    registered_packages = {reg.model_subdirectory for reg in REGISTRATIONS}
    for entry in standalone.STANDALONE_MODELS:
        assert entry.package not in registered_packages, (
            f"{entry.package} is registered as a composition model"
        )
        assert entry.module not in registered_ids, entry.module


def test_the_composition_registry_lists_only_the_three_composed_models():
    listed = {row["model_id"] for row in known_models()}
    assert listed == {
        "morris2011.material_balance",
        "zielinski2019.rhi_process",
        "ganjave",
    }


def test_no_standalone_manifest_claims_a_registration():
    for entry in standalone.STANDALONE_MODELS:
        payload = json.loads(entry.manifest_path().read_text(encoding="utf-8"))
        registration = payload.get("registration", {})
        assert registration.get("registered_in_composition_registry") is False
        assert registration.get("reason")
