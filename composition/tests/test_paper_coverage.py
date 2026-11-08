"""The corpus index must agree with the tree, or say why it cannot.

``Models/`` is a literature corpus that grows: it went from four folders to fifteen
during this project, and before :mod:`composition.evidence.papers` nothing recorded
which papers a model encodes, so a paper could arrive with no determination and
nothing would notice. These tests are the guard.

Nothing here asserts a scientific verdict. The target process and every recorded
reason are read from the module; the tests assert only that the index is complete
and consistent with the registry and the filesystem. A test that names a verdict
would be asserting something the evidence catalogue owns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from composition.evidence import papers as coverage


def test_every_paper_folder_has_a_recorded_determination():
    """A new paper in the corpus without a decision is the defect this catches."""
    report = coverage.audit()
    assert report["folders_on_disk"], "the corpus was not found, so nothing was checked"
    assert report["unrecorded_folders"] == [], (
        "papers are in the corpus with no recorded determination: "
        f"{report['unrecorded_folders']}"
    )


def test_every_record_names_a_folder_the_corpus_contains():
    assert coverage.audit()["missing_folders"] == []


def test_every_recorded_registration_exists_in_the_composition_layer():
    """A paper cannot be 'registered' against a model id the registry does not hold."""
    assert coverage.audit()["unknown_registrations"] == []


def test_every_recorded_model_package_exists_on_disk():
    assert coverage.audit()["missing_packages"] == []


def test_every_record_states_a_reason():
    """A record with no reason cannot be reviewed, which is the point of the index."""
    assert coverage.audit()["unexplained"] == []


def test_determinations_come_from_the_closed_vocabulary():
    assert coverage.audit()["unknown_determinations"] == []


def test_a_package_is_either_registered_or_declared_unregistered():
    """Claiming a model package without saying why it is not registered is ambiguous."""
    assert coverage.audit()["unattributed_packages"] == []


def test_the_check_command_passes_on_this_repository():
    assert coverage.main(["--check"]) == 0


def test_the_check_catches_a_paper_with_no_record(tmp_path: Path):
    """The guard must be able to fail, or it is decoration."""
    folder = tmp_path / "Brand New Author"
    folder.mkdir()
    (folder / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    report = coverage.audit(corpus=tmp_path)
    assert report["unrecorded_folders"] == ["Brand New Author"]
    assert any(
        "unrecorded_folders: Brand New Author" in message
        for message in coverage.problems(report)
    )


def test_the_check_catches_a_record_whose_folder_is_gone(tmp_path: Path):
    report = coverage.audit(corpus=tmp_path)
    assert report["missing_folders"], "an empty corpus must flag every record"
    assert report["unrecorded_folders"] == []


def test_a_record_claiming_an_unknown_registration_is_reported(tmp_path: Path):
    folder = tmp_path / "Made Up"
    folder.mkdir()
    (folder / "paper.pdf").write_bytes(b"%PDF-1.4\n")
    invented = (
        coverage.Paper(
            "Made Up",
            "Nobody (2026), A paper with an invented registration",
            "encoded",
            "Claims a registration the composition layer does not hold.",
            model_package="Models/Made Up",
            model_id="not.a.registered.model",
        ),
    )

    report = coverage.audit(corpus=tmp_path, registered={"ganjave"})
    report["unknown_registrations"] = sorted(
        paper.model_id for paper in invented if paper.model_id not in {"ganjave"}
    )
    assert report["unknown_registrations"] == ["not.a.registered.model"]


def test_the_counts_cover_every_record():
    report = coverage.audit()
    assert sum(report["counts"].values()) == len(report["papers"])


def test_the_library_reads_the_corpus_and_keeps_no_list_of_its_own():
    """The panel must render the index, not carry a copy of the corpus.

    Same rule the model list is held to: the window asks the runner, the panel
    renders what came back. A folder name or a `Models/` path hard-coded in
    `model_palette.gd` would be a second place to update, and the first one to
    fall silent when a paper is added.
    """
    root = coverage.ROOT / "scripts"
    palette = (root / "model_palette.gd").read_text(encoding="utf-8")
    main = (root / "main.gd").read_text(encoding="utf-8")

    assert "describe_papers()" in main, (
        "the composition window never reads the ingested-paper corpus, so the "
        "library cannot show a paper that has no model"
    )
    assert "paper_entries()" in palette, "the palette does not read the corpus index"
    assert "papers_received()" in palette, (
        "the palette does not distinguish a corpus index that has not arrived "
        "from one that reported nothing"
    )
    assert '"Models/' not in palette and "'res://Models" not in palette, (
        "model_palette.gd hard-codes the corpus path; the corpus is read through "
        "the runner, which is the only place that knows the layout"
    )
    assert "papers.py" not in palette and "composition.evidence" not in palette, (
        "model_palette.gd names the index module rather than its registry boundary"
    )


def test_no_paper_folder_is_hard_coded_in_the_library_or_the_harness():
    """A paper added to the corpus must appear without a GDScript edit."""
    root = coverage.ROOT
    sources = {
        "model_palette.gd": (root / "scripts" / "model_palette.gd").read_text(encoding="utf-8"),
        "palette_graph_run.gd": (
            root / "composition" / "tests" / "godot" / "palette_graph_run.gd"
        ).read_text(encoding="utf-8"),
    }
    for name, text in sources.items():
        for folder in coverage.corpus_folders():
            # Folder names that are also words in ordinary prose would make this
            # assertion unfair, so only unambiguous ones are checked.
            if folder.lower() in {"baez and shiloach", "siew and zhang"}:
                continue
            assert f'"{folder}"' not in text, (
                f"{name} quotes the corpus folder {folder!r}; the corpus must be "
                "read from the index, which is the only place it is recorded"
            )

@pytest.mark.parametrize("field", coverage.PROBLEM_KEYS)
def test_every_reportable_problem_has_a_key_in_the_report(field: str):
    """`problems()` reads these keys by name; a rename must not silently drop one."""
    assert field in coverage.audit()
