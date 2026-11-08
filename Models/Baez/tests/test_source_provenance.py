"""Provenance: source metadata, printed pages, the article PDF, and invariants.

Contract test 7 (source references and provenance), plus the page-text
regeneration path: locating the article PDF has to work from wherever this
package sits in the repository, and regenerating must never be able to
overwrite the tracked snapshot by accident.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging

import pytest

from _baez_testkit import PAPER_PAGES_PATH
from baez2014 import observations, source
from baez2014.feed_rate import REPORTED_PARAMETERS
from baez2014.provenance import (
    Basis,
    Condition,
    EvidenceError,
    EvidenceRef,
    Provenance,
    Quantity,
    derived,
    reported,
    unknown,
)


# --------------------------------------------------------------------------- #
# the source itself
# --------------------------------------------------------------------------- #


def test_source_metadata_is_the_published_article() -> None:
    assert source.DOI == "10.1186/1475-2859-13-50"
    assert source.SOURCE_ID == "baez2014"
    assert source.AUTHORS == ("Antonino Baez", "Nadim Majdalani", "Joseph Shiloach")
    assert source.JOURNAL == "Microbial Cell Factories"
    assert source.YEAR == 2014
    assert source.ARTICLE_NUMBER == "50"
    assert source.PAGES == "1-7"
    assert source.PAGE_COUNT == 7
    assert "Microbial Cell Factories" in source.CITATION
    assert "10.1186/1475-2859-13-50" not in source.CITATION  # kept in its own field


def test_citation_and_reference_forms_agree() -> None:
    assert source.reference(6) == "Baez et al. 2014, p. 6"
    assert source.reference(3, section="Results") == "Baez et al. 2014, p. 3, Results"
    full = source.citation_for(2)
    assert full.endswith("Baez et al. 2014, p. 2") or "p. 2" in full
    assert source.AUTHORS[0].split()[-1] in full  # "Baez"


# --------------------------------------------------------------------------- #
# printed page numbering
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("page", range(2, 8))
def test_every_interior_page_states_its_own_printed_number(page: int) -> None:
    """Printed page == PDF page, established from the running footer."""
    text = source.page_text(page)
    assert text, f"page {page} is missing from the extracted text"
    assert source.footer_for(page) in text


def test_the_article_runs_from_page_1_to_page_7() -> None:
    """Page 1 carries the journal line but no 'Page N of 7' footer; pages 2-7 do."""
    first = source.page_text(1)
    assert "Baez et al. Microbial Cell Factories 2014 13:50" in first
    assert source.footer_for(1) not in first
    assert source.footer_for(source.PAGE_COUNT) in source.page_text(source.PAGE_COUNT)


def test_extracted_text_covers_exactly_the_printed_pages() -> None:
    assert sorted(source.paper_pages()) == list(range(1, source.PAGE_COUNT + 1))


def test_evidence_reference_reports_the_same_number_for_both_pages() -> None:
    evidence = EvidenceRef(printed_page=3)
    assert evidence.pdf_page == 3
    assert evidence.printed_page == 3
    assert evidence.to_dict()["pdf_page"] == evidence.to_dict()["printed_page"]


@pytest.mark.parametrize("page", [0, -1, 8, 99])
def test_evidence_outside_the_article_is_refused(page: int) -> None:
    with pytest.raises(EvidenceError, match="outside the article"):
        EvidenceRef(printed_page=page)


def test_evidence_for_another_source_is_refused() -> None:
    with pytest.raises(EvidenceError, match="cites only"):
        EvidenceRef(printed_page=2, source_id="zielinski2019")


def test_evidence_carries_its_citation_and_reference() -> None:
    evidence = EvidenceRef(printed_page=6, section="Methods", quote="(141 g/L)")
    assert evidence.reference == "Baez et al. 2014, p. 6, Methods"
    assert "p. 6" in evidence.citation
    assert evidence.to_dict()["quote"] == "(141 g/L)"


# --------------------------------------------------------------------------- #
# structural invariants
# --------------------------------------------------------------------------- #


def test_reported_requires_evidence() -> None:
    with pytest.raises(ValueError, match="must cite"):
        Quantity(
            quantity_id="x",
            label="x",
            provenance=Provenance.REPORTED,
            value=1.0,
            unit="g/L",
        )


def test_unknown_holds_no_value() -> None:
    with pytest.raises(ValueError, match="refusing to fabricate"):
        Quantity(
            quantity_id="x",
            label="x",
            provenance=Provenance.UNKNOWN,
            value=0.0,
            unit="g/L",
        )
    blank = unknown("x", "x", "g/L")
    assert blank.value is None
    assert blank.display() == "unknown"
    assert blank.basis is Basis.UNRESOLVED


def test_derived_requires_a_method_and_its_inputs() -> None:
    with pytest.raises(ValueError, match="calculation method"):
        Quantity(
            quantity_id="x",
            label="x",
            provenance=Provenance.DERIVED,
            value=1.0,
            unit="L/h",
            inputs=("a",),
        )
    with pytest.raises(ValueError, match="input quantities must be named"):
        Quantity(
            quantity_id="x",
            label="x",
            provenance=Provenance.DERIVED,
            value=1.0,
            unit="L/h",
            method="m",
        )


def test_a_numeric_quantity_needs_a_registered_unit() -> None:
    with pytest.raises(ValueError, match="requires a unit"):
        Quantity("x", "x", Provenance.REPORTED, 1.0, None,
                 evidence=(EvidenceRef(printed_page=2),))
    with pytest.raises(ValueError, match="unknown unit"):
        Quantity("x", "x", Provenance.REPORTED, 1.0, "g/dm3",
                 evidence=(EvidenceRef(printed_page=2),))


def test_basis_follows_provenance_and_nothing_else() -> None:
    assert reported("x", "x", 1.0, "g/L", EvidenceRef(printed_page=2)).basis is Basis.OBSERVED
    assert derived("x", "x", 1.0, "L/h", "m", ("a",)).basis is Basis.COMPUTED
    assert Provenance.ASSUMED.value == "assumed"


def test_quantity_serialisation_is_plain_data() -> None:
    payload = reported(
        "x", "x", 1.0, "g/L", EvidenceRef(printed_page=3, section="Results")
    ).to_dict()
    assert payload["provenance"] == "reported"
    assert payload["basis"] == "observed_reference"
    assert payload["evidence"][0]["printed_page"] == 3
    assert payload["evidence"][0]["section"] == "Results"


# --------------------------------------------------------------------------- #
# every published record cites the page the specification assigns it
# --------------------------------------------------------------------------- #


def test_growth_rates_cite_printed_page_2(growth_rates: tuple) -> None:
    for observation in growth_rates:
        assert observation.quantity.printed_pages == (2,)
        assert observation.quantity.evidence[0].section is not None


def test_endpoint_cites_printed_page_3(endpoint: tuple) -> None:
    for observation in endpoint:
        assert observation.quantity.printed_pages == (3,)
        assert observation.quantity.evidence[0].section is not None


def test_feed_parameters_and_equation_cite_printed_page_6() -> None:
    for quantity in REPORTED_PARAMETERS.values():
        assert quantity.printed_pages == (6,)
        assert quantity.evidence[0].quote
    from baez2014.equations import equation

    assert equation("source_formula.exponential_feed_rate").printed_page == 6


def test_conditions_cover_pages_5_and_6_for_setup_and_induction() -> None:
    pages = {c.evidence.printed_page for c in observations.experimental_conditions()}
    assert {5, 6} <= pages
    labels = {c.label for c in observations.experimental_conditions()}
    assert "induction (soxS promoter)" in labels
    assert "aeration and agitation" in labels


def test_condition_requires_a_page_and_a_quote() -> None:
    condition = Condition(
        label="x",
        value="y",
        evidence=EvidenceRef(printed_page=5, quote="quoted"),
    )
    assert condition.to_dict()["evidence"]["printed_page"] == 5
    with pytest.raises(EvidenceError):
        Condition(label="x", value="y", evidence=EvidenceRef(printed_page=42))


def test_four_litre_batch_volume_is_not_recorded_as_V_F() -> None:
    """The paper prints 4 L as the initial *batch* volume; V_F stays unvalued."""
    from baez2014.feed_rate import UNVALUED_RUN_INPUTS

    condition = next(
        c for c in observations.experimental_conditions()
        if c.label == "fed-batch initial volume"
    )
    assert "not V_F" in condition.value
    assert "No number is printed for V_F" in UNVALUED_RUN_INPUTS["V_F"]


def test_run_inputs_are_documented_as_unvalued_by_the_paper() -> None:
    from baez2014.feed_rate import UNVALUED_RUN_INPUTS

    assert set(UNVALUED_RUN_INPUTS) == {"X_F", "V_F", "t_F", "t"}
    for name, definition in UNVALUED_RUN_INPUTS.items():
        assert definition
        assert "p. " in definition, name


# --------------------------------------------------------------------------- #
# locating the article PDF
# --------------------------------------------------------------------------- #


def test_repository_root_is_found_by_walking_up() -> None:
    root = source.repository_root()
    assert root is not None, "repository root not found from the package location"
    assert (root / "papers").is_dir()
    assert (root / "Models").is_dir()
    assert (root / "Models" / "Baez").is_dir()


def test_pdf_candidates_are_ordered_canonical_first() -> None:
    rules = [rule for rule, _path in source.pdf_candidates()]
    assert rules[0] == "repository papers/"
    assert "package-local" in rules
    # the canonical candidate is the repository's own papers/ copy, not the
    # package-local one
    canonical = dict(source.pdf_candidates())["repository papers/"]
    assert canonical == source.PAPER_PDF
    assert canonical.parent.name == "papers"


def test_resolve_source_pdf_picks_an_existing_file_and_names_the_rule() -> None:
    path, rule = source.resolve_source_pdf()
    assert path.is_file()
    assert rule == "repository papers/"
    assert path.name == source.PDF_FILENAME


def test_pdf_resolution_is_deterministic() -> None:
    first = source.resolve_source_pdf()
    second = source.resolve_source_pdf()
    assert first == second


def test_package_local_copy_is_a_real_fallback() -> None:
    """The sibling model packages keep a copy beside their source; so does this."""
    package_local = dict(source.pdf_candidates())["package-local"]
    assert package_local.parent.name == "Baez"
    if not package_local.is_file():
        pytest.skip(
            "no package-local PDF copy; the canonical repository copy is used"
        )
    assert package_local.name == source.PDF_FILENAME


def test_missing_pdf_raises_with_every_searched_path(monkeypatch) -> None:
    """An absent PDF says where it looked and what to do, instead of FileNotFound."""
    from pathlib import Path

    canonical = Path("Z:/absent/papers/x.pdf")
    local = Path("Z:/absent/pkg/x.pdf")
    monkeypatch.setattr(
        source, "pdf_candidates",
        lambda: (("repository papers/", canonical), ("package-local", local)),
    )
    with pytest.raises(source.SourcePdfNotFound) as excinfo:
        source.resolve_source_pdf()
    message = str(excinfo.value)
    assert "repository papers/" in message
    assert "package-local" in message
    assert str(canonical) in message
    assert str(local) in message
    assert "rebuild_paper_pages()" in message


def test_no_fixed_depth_path_arithmetic_remains_in_source() -> None:
    """`parents[n]` is what broke when this package moved; assert it stays gone."""
    import re
    from pathlib import Path

    text = Path(source.__file__).read_text(encoding="utf-8")
    fixed_depth = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"\.parents\[\d+\]", line)
    ]
    assert fixed_depth == [], fixed_depth


# --------------------------------------------------------------------------- #
# regenerating the page text
# --------------------------------------------------------------------------- #


def _pypdf_or_skip():
    """pypdf is a regeneration-time dependency, not a runtime one."""
    try:
        import pypdf  # noqa: F401
    except ImportError:  # pragma: no cover - depends on the host
        pytest.skip("pypdf is not installed; regeneration cannot be exercised")
    return pypdf


@contextlib.contextmanager
def _quiet_pypdf():
    """Silence pypdf's font-parsing chatter.

    The warnings are advisory -- it extracts the text correctly without
    fontTools -- and they would otherwise bury the test output. They are not
    suppressed in the package, which never imports pypdf at all.
    """
    logger = logging.getLogger("pypdf")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous)


def test_rebuild_writes_only_where_it_is_told(tmp_path) -> None:
    """Regeneration must not be able to overwrite the tracked snapshot."""
    _pypdf_or_skip()
    before = hashlib.sha256(PAPER_PAGES_PATH.read_bytes()).hexdigest()
    out = tmp_path / "nested" / "regenerated.json"
    with _quiet_pypdf():
        pages = source.rebuild_paper_pages(output_path=out)
    after = hashlib.sha256(PAPER_PAGES_PATH.read_bytes()).hexdigest()
    assert out.is_file(), "explicit output_path was not written"
    assert before == after, "the tracked snapshot was modified by a rebuild"
    assert len(pages) == source.PAGE_COUNT


def test_regenerated_text_covers_the_seven_printed_pages(tmp_path) -> None:
    _pypdf_or_skip()
    with _quiet_pypdf():
        pages = source.rebuild_paper_pages(output_path=tmp_path / "pages.json")
    assert sorted(pages) == list(range(source.FIRST_PRINTED_PAGE, source.PAGE_COUNT + 1))
    for number, text in pages.items():
        assert text, f"page {number} came back empty"
        if number == source.FIRST_PRINTED_PAGE:
            # page 1 carries the journal line instead of a page-number footer
            assert "Microbial Cell Factories" in text
            continue
        assert source.footer_for(number) in text, f"page {number} has no page footer"


def test_regenerated_text_matches_the_tracked_snapshot(tmp_path) -> None:
    """Deterministic: the same PDF yields the same text, byte for byte.

    This compares two extractions of the same PDF against each other; it does
    not adjust any value or text to make them agree.
    """
    _pypdf_or_skip()
    out = tmp_path / "pages.json"
    with _quiet_pypdf():
        pages = source.rebuild_paper_pages(output_path=out)
    regenerated = {str(k): v for k, v in pages.items()}
    tracked = json.loads(PAPER_PAGES_PATH.read_text(encoding="utf-8"))
    assert regenerated == tracked
    assert json.loads(out.read_text(encoding="utf-8")) == tracked


def test_snapshot_check_stays_deterministic_after_regeneration(tmp_path) -> None:
    """The manifest check compares against the same tracked text, unchanged."""
    import subprocess
    import sys

    from _baez_testkit import MANIFEST_PATH, PACKAGE_ROOT

    _pypdf_or_skip()
    with _quiet_pypdf():
        source.rebuild_paper_pages(output_path=tmp_path / "pages.json")
    result = subprocess.run(
        [sys.executable, "-m", "baez2014", "--check", str(MANIFEST_PATH)],
        cwd=PACKAGE_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr