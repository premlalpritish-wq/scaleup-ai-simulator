"""Fidelity and behaviour tests for Nanchen, Schicker & Sauer (2006)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nanchen2006 import context, manifest, model, source, units
from nanchen2006.validate import validate

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
def test_each_page_states_its_own_printed_number(page: int):
    assert source.page_states_its_own_number(page)


def test_pdf_page_offset():
    assert source.pdf_page(1164) == 1
    assert source.pdf_page(1172) == 9
    assert source.printed_page_of(9) == 1172


# --------------------------------------------------------------------------- #
# fidelity
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [0.37, 76, 0.09, 3])
def test_the_this_study_row_is_on_table_1(value: float):
    assert f"{value:g}" in source.page_text(model.TABLE_I_PAGE)


@pytest.mark.parametrize("reading_id",
                         [r.reading_id for r in model.REPORTED_READINGS])
def test_reported_reading_is_on_its_page(reading_id: str):
    r = next(r for r in model.REPORTED_READINGS if r.reading_id == reading_id)
    assert source.page_contains(r.evidence.printed_page, f"{r.value:g}")


@pytest.mark.parametrize("key", [c.key for c in context.EXPERIMENTAL_CONTEXT])
def test_context_quote_is_on_its_cited_page(key: str):
    cond = context.condition(key)
    assert source.page_contains(cond.evidence.printed_page, cond.evidence.quote), (
        f"{key} quotes {cond.evidence.quote!r}, not found on "
        f"p.{cond.evidence.printed_page}"
    )


def test_equation_3_is_the_implemented_one_and_1_2_are_declared_absent():
    by_id = {e["id"]: e for e in manifest.PRINTED_EQUATIONS}
    assert by_id["eq.3"]["implemented"] is True
    assert by_id["eq.1"]["implemented"] is False
    assert by_id["eq.2"]["implemented"] is False


# --------------------------------------------------------------------------- #
# the relation
# --------------------------------------------------------------------------- #


def test_q_at_zero_growth_is_the_maintenance_coefficient():
    assert model.q_glc(0.0, 76.0, 0.37) == pytest.approx(0.37)


def test_the_slope_is_one_thousand_over_the_maximal_yield():
    """1/Yglc_max is the glucose requirement per gdw; the factor is mol->mmol."""
    p = model.THIS_STUDY
    slope = (model.q_glc(1.0, p.Yglc_max, p.mglc)
             - model.q_glc(0.0, p.Yglc_max, p.mglc))
    assert slope == pytest.approx(model.MOL_PER_MMOL / p.Yglc_max)


def test_the_papers_own_worked_point():
    """At mu = 0.4 1/h the relation gives 5.63 mmol gdw-1 h-1 for MG1655."""
    q = model.q_glc(0.4, model.THIS_STUDY.Yglc_max, model.THIS_STUDY.mglc)
    assert q == pytest.approx(5.633157894736842, abs=1e-12)


def test_the_relation_round_trips():
    p = model.THIS_STUDY
    q = model.q_glc(0.25, p.Yglc_max, p.mglc)
    assert model.mu_from_q_glc(q, p.Yglc_max, p.mglc) == pytest.approx(0.25)


def test_observed_yield_is_below_the_maximal_yield():
    p = model.THIS_STUDY
    assert model.biomass_yield(0.05, p.Yglc_max, p.mglc) < model.biomass_yield(
        0.5, p.Yglc_max, p.mglc
    )
    assert model.biomass_yield(0.5, p.Yglc_max, p.mglc) < p.Yglc_max


def test_a_non_positive_yield_is_refused():
    with pytest.raises(model.ModelError):
        model.q_glc(0.1, 0.0, 0.37)



# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "src,dst,value,expected",
    [("h", "min", 1.0, 60.0), ("mL", "L", 1000.0, 1.0), ("mL/min", "L/h", 1000.0, 60.0)],
)
def test_registered_conversions(src: str, dst: str, value: float, expected: float):
    assert units.convert(value, src, dst) == pytest.approx(expected)


@pytest.mark.parametrize("src,dst",
                         [("mmol/(gdw h)", "gdw/mol"), ("1/h", "mmol/(gdw h)")])
def test_unlike_dimensions_are_refused(src: str, dst: str):
    assert not units.is_convertible(src, dst)
    with pytest.raises(units.UnitError):
        units.convert(1.0, src, dst)


# --------------------------------------------------------------------------- #
# manifest, validation, isolation
# --------------------------------------------------------------------------- #


def test_the_manifest_declares_the_source_and_the_absence_of_registration():
    m = manifest.build_manifest()
    assert m["artefact_id"] == manifest.ARTEFACT_ID
    assert m["registration"]["registered_in_composition_registry"] is False
    assert m["fitted_parameters"]["reference_as_printed"] == "This study"
    assert m["mol_per_mmol"] == 1000.0
    assert m["comparison_table_note"]


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
    for path in sorted((PACKAGE_ROOT / "nanchen2006").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            assert not stripped.startswith("import composition"), path.name
            assert not stripped.startswith("from composition"), path.name
