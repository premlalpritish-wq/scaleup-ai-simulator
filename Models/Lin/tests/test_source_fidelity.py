"""Fidelity and behaviour tests for Lin et al. (2001).

These tests are the package's own evidence gate. They assert only that the
transcription matches the printed page and that the printed equations behave as
printed. They do not assert a scientific verdict, and they compare no curve to a
figure, because the paper prints no digitised curve.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from lin2000 import context, manifest, model, parameters as params, source, units
from lin2000.validate import check_parameters, validate

# --------------------------------------------------------------------------- #
# source and page numbering
# --------------------------------------------------------------------------- #


def test_every_printed_page_has_extracted_text():
    for page in range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1):
        assert source.page_text(page).strip(), f"no text for printed page {page}"


def test_the_first_page_carries_no_footer():
    assert not source.page_states_its_own_number(source.FIRST_PRINTED_PAGE)


@pytest.mark.parametrize(
    "page", range(source.FIRST_PRINTED_PAGE + 1, source.LAST_PRINTED_PAGE + 1)
)
def test_each_later_page_states_its_own_printed_number(page: int):
    assert source.page_states_its_own_number(page), (
        f"printed page {page} does not state its own number, so the "
        f"printed-page arithmetic is not evidenced"
    )


def test_pdf_page_maps_to_printed_page_by_the_stated_offset():
    assert source.pdf_page(347) == 1
    assert source.pdf_page(357) == 11
    assert source.printed_page_of(1) == 347
    assert source.printed_page_of(11) == 357


# --------------------------------------------------------------------------- #
# fidelity: the printed values are on the printed page
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,strain,value",
    [
        (p.name, strain, value)
        for p in params.TABLE_I
        for strain, value in p.values.items()
        if value is not None
    ],
)
def test_table_i_value_is_on_table_i_page(name: str, strain: str, value: float):
    text = source.page_text(params.TABLE_I_PAGE)
    candidates = [f"{value:g}"]
    if float(value).is_integer():
        candidates.append(str(int(value)))
    assert any(c in text for c in candidates), (
        f"Table I prints {name}={value} for {strain}, but p.{params.TABLE_I_PAGE} "
        f"does not carry it"
    )


@pytest.mark.parametrize(
    "quantity_id", [q.quantity_id for q in params.REPORTED_CAPACITIES]
)
def test_reported_capacity_is_on_the_abstract_page(quantity_id: str):
    q = next(q for q in params.REPORTED_CAPACITIES if q.quantity_id == quantity_id)
    assert source.page_contains(params.ABSTRACT_PAGE, f"{q.value:g}")



@pytest.mark.parametrize(
    "key", [c.key for c in context.EXPERIMENTAL_CONTEXT]
)
def test_context_quote_is_on_its_cited_page(key: str):
    cond = context.condition(key)
    assert cond.evidence.quote, f"{key} records no quote to check"
    assert source.page_contains(cond.evidence.printed_page, cond.evidence.quote), (
        f"{key} quotes {cond.evidence.quote!r}, which is not on "
        f"p.{cond.evidence.printed_page}"
    )


def test_every_declared_equation_cites_a_page_that_exists():
    for equation in manifest.PRINTED_EQUATIONS:
        page = equation["printed_page"]
        assert source.FIRST_PRINTED_PAGE <= page <= source.LAST_PRINTED_PAGE
        assert source.page_text(page).strip()


def test_the_differential_system_and_subsidiary_chain_cite_the_appendix_pages():
    pages = {e["printed_page"] for e in manifest.PRINTED_EQUATIONS}
    assert pages == {351, 356, 357}


def test_the_pulse_equation_is_attributed_to_the_method_page():
    pulse = next(e for e in manifest.PRINTED_EQUATIONS if e["id"] == "method.pulse_qScap")
    assert pulse["printed_page"] == model.PULSE_METHOD_PAGE
    assert "INT(F Si)" in pulse["statement"]
