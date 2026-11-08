"""Fidelity and behaviour tests for Simensen et al. (2022)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simensen2022 import context, manifest, model, source, units
from simensen2022.validate import validate

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# source and page numbering
# --------------------------------------------------------------------------- #


def test_every_printed_page_has_extracted_text():
    for page in range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1):
        assert source.page_text(page).strip(), f"no text for printed page {page}"


@pytest.mark.parametrize(
    "page", range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1)
)
def test_each_page_states_its_own_footer(page: int):
    assert source.page_states_its_own_number(page)


def test_printed_page_equals_pdf_page():
    assert source.pdf_page(1) == 1
    assert source.pdf_page(17) == 17
    assert source.printed_page_of(9) == 9


# --------------------------------------------------------------------------- #
# fidelity
# --------------------------------------------------------------------------- #


def test_every_distinctive_table_value_is_on_the_table_page():
    text = source.page_text(model.TABLE_I_PAGE)
    missing = []
    for r in model.TABLE_1:
        for column in model.COLUMNS:
            cell = r.cell(column)
            if cell.value is None:
                continue
            printed = f"{cell.value:g}"
            if sum(ch.isdigit() for ch in printed) < 3:
                continue
            if printed not in text:
                missing.append(f"{r.name}@{column}={printed}")
    assert not missing, missing


@pytest.mark.parametrize("marker", ["n.d.", "-"])
def test_a_missing_value_keeps_its_printed_marker(marker: str):
    """A value the paper does not print is never a 0.0."""
    found = False
    for r in model.TABLE_1:
        for column in model.COLUMNS:
            cell = r.cell(column)
            if cell.note == marker:
                found = True
                assert cell.value is None, (
                    f"{r.name}@{column} carries value marker {marker!r} and a value"
                )
    assert found, f"no cell carries the value marker {marker!r}"


def test_a_missing_standard_deviation_keeps_its_printed_marker():
    """``NA`` marks a cell whose value is printed but whose SD is not."""
    found = False
    for r in model.TABLE_1:
        for column in model.COLUMNS:
            cell = r.cell(column)
            if cell.sd_note == "NA":
                found = True
                assert cell.value is not None
                assert cell.sd is None
    assert found, "no cell carries the SD marker 'NA'"


@pytest.mark.parametrize("statement_id",
                         [s.statement_id for s in model.REPORTED_STATEMENTS])
def test_reported_statement_is_on_its_page(statement_id: str):
    s = next(s for s in model.REPORTED_STATEMENTS if s.statement_id == statement_id)
    assert source.page_contains(s.evidence.printed_page, f"{s.value:g}")


@pytest.mark.parametrize("key", [c.key for c in context.EXPERIMENTAL_CONTEXT])
def test_context_quote_is_on_its_cited_page(key: str):
    cond = context.condition(key)
    assert source.page_contains(cond.evidence.printed_page, cond.evidence.quote), (
        f"{key} quotes {cond.evidence.quote!r}, not found on "
        f"p.{cond.evidence.printed_page}"
    )


# --------------------------------------------------------------------------- #
# the dataset
# --------------------------------------------------------------------------- #


def test_the_this_work_macromolecule_sum_reproduces_the_printed_sum():
    computed = model.computed_macromolecule_sum("this_work")
    assert computed == pytest.approx(0.8352, abs=1e-12)
    assert round(computed, 3) == pytest.approx(model.printed_sum("this_work"))


def test_the_neidhardt_sum_reproduces_its_printed_total():
    computed = model.computed_macromolecule_sum("neidhardt")
    assert computed == pytest.approx(1.0, abs=1e-12)


def test_the_composition_exposes_the_biomass_objective_fractions():
    c = model.composition("this_work")
    assert c["Protein"] == 0.54
    assert c["RNA"] == 0.190
    assert c["DNA"] == 0.013
    assert c["Carbohydrate"] == 0.0312
    assert c["Lipid"] == 0.061


def test_the_amino_acid_fractions_do_not_exceed_the_protein_pool():
    aa = model.amino_acid_sum("this_work")
    assert 0.5 < aa < 0.54


def test_a_cell_that_is_not_a_number_is_refused_rather_than_defaulted():
    with pytest.raises(model.DatasetError):
        model.mass_fraction("Rhamnose", "this_work")


def test_an_unknown_row_or_column_is_refused():
    with pytest.raises(model.DatasetError):
        model.row("Insulin")
    with pytest.raises(model.DatasetError):
        model.mass_fraction("Protein", "imagined")


def test_the_stated_coverage_and_the_table_sum_are_both_recorded():
    values = {s.statement_id: s.value for s in model.REPORTED_STATEMENTS}
    assert values["coverage.overall"] == 91.6
    assert values["sum.this_work"] == 0.835



# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #


def test_the_mass_fraction_unit_is_registered_and_not_convertible_to_mass():
    assert units.dimension_of("g/g") is units.Dimension.MASS_FRACTION
    assert not units.is_convertible("g/g", "g/L")
    with pytest.raises(units.UnitError):
        units.convert(1.0, "g/g", "g/L")


def test_registered_conversions():
    assert units.convert(1000.0, "mL", "L") == pytest.approx(1.0)
    assert units.convert(1.0, "h", "min") == pytest.approx(60.0)


# --------------------------------------------------------------------------- #
# manifest, validation, isolation
# --------------------------------------------------------------------------- #


def test_the_manifest_declares_the_source_and_the_absence_of_registration():
    m = manifest.build_manifest()
    assert m["artefact_id"] == manifest.ARTEFACT_ID
    assert m["registration"]["registered_in_composition_registry"] is False
    assert m["source"]["printed_page_equals_pdf_page"] is True
    assert m["table"]["unit_as_printed"] == "g gCDW-1"
    assert len(m["table"]["rows"]) == len(model.TABLE_1)
    assert m["printed_numeric_markers"]


def test_the_manifest_carries_the_context_it_preserves():
    keys = {c["key"] for c in manifest.build_manifest()["experimental_context"]}
    for required in ("strain", "construct", "medium", "reactor", "scale"):
        assert required in keys


def test_the_committed_manifest_matches_what_the_package_declares():
    committed = PACKAGE_ROOT / "manifest.json"
    if not committed.is_file():
        pytest.skip("manifest.json has not been generated yet")
    expected = json.dumps(
        manifest.build_manifest(), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    assert committed.read_text(encoding="utf-8") == expected


def test_validation_passes_on_this_repository():
    report = validate()
    assert report["ok"], report["failures"]


def test_the_package_does_not_import_the_composition_layer():
    for path in sorted((PACKAGE_ROOT / "simensen2022").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            assert not stripped.startswith("import composition"), path.name
            assert not stripped.startswith("from composition"), path.name
