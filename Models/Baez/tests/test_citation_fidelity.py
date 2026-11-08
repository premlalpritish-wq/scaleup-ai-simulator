"""Citation checks against the extracted text of the printed article.

Contract test 7, second half: a citation is not trusted, it is checked. Every
value, every printed fragment and every quote this package attributes to a
printed page must actually appear in the extracted text of that page.

The PDFs under `papers/` are publications by other authors and are never read
at run time. What is read here is `baez2014/data/paper_pages.json`, the
normalised page text, regenerable from the PDF with
`baez2014.source.rebuild_paper_pages()`.
"""

from __future__ import annotations

import pytest

from baez2014 import equations, observations, source
from baez2014.feed_rate import REPORTED_PARAMETERS

#: The value strings, exactly as printed, and the page each is printed on.
VALUES_ON_PAGES = (
    (2, "1.08/h"),
    (2, "1.00/h"),
    (3, "109000 FU"),
    (3, "494 mg/L"),
    (3, "29.1 g/L"),
    (3, "7.1 g/L"),
    (6, "(0.35 1/h)"),
    (6, "(1.28 g/g)"),
    (6, "(0.12 g/g h)"),
    (6, "(141 g/L)"),
    (6, "F(t) = feed rate (L/h)"),
)


@pytest.mark.parametrize("page,fragment", VALUES_ON_PAGES)
def test_value_appears_verbatim_on_the_page_it_is_cited_to(page: int, fragment: str) -> None:
    """Numbers are checked strictly: no hyphen tolerance for a reported value."""
    assert fragment in source.page_text(page), f"{fragment!r} is not on p. {page}"


def test_printed_expression_fragment_is_on_page_6() -> None:
    assert equations.PRINTED_FRAGMENT in source.page_text(6)


def test_growth_rate_fragments_are_on_page_2(growth_rates: tuple) -> None:
    for observation in growth_rates:
        text = observation.quantity.original_text
        assert text, observation.observation_id
        assert source.page_contains(2, text), f"{observation.observation_id}: {text!r}"


def test_endpoint_fragments_are_on_page_3(endpoint: tuple) -> None:
    for observation in endpoint:
        text = observation.quantity.original_text
        assert text, observation.observation_id
        assert source.page_contains(3, text), f"{observation.observation_id}: {text!r}"


def test_parameter_quotes_are_on_page_6() -> None:
    page = source.page_text(6)
    for name, quantity in REPORTED_PARAMETERS.items():
        quote = quantity.evidence[0].quote
        assert quote in page, f"{name}: {quote!r} not on p. 6"


def test_observation_quotes_are_on_their_pages(growth_rates: tuple, endpoint: tuple) -> None:
    for observation in list(growth_rates) + list(endpoint):
        for evidence in observation.quantity.evidence:
            if evidence.quote:
                assert source.page_contains(evidence.printed_page, evidence.quote), evidence.quote


def test_condition_quotes_are_on_their_pages() -> None:
    for condition in observations.experimental_conditions():
        quote = condition.evidence.quote
        assert quote, condition.label
        assert source.page_contains(condition.evidence.printed_page, quote), (
            f"{condition.label}: {quote!r} not on p. {condition.evidence.printed_page}"
        )


def test_hyphen_tolerance_only_covers_typography() -> None:
    """`page_contains` relaxes hyphens and spaces, never content."""
    assert source.page_contains(3, "acetate accumulation reached 7.1 g/L (Figure 4B)")
    assert not source.page_contains(3, "acetate accumulation reached 7.2 g/L (Figure 4B)")
    assert not source.page_contains(2, "7.1 g/L")


def test_the_two_growth_rates_are_reported_as_insignificantly_different() -> None:
    """p. 2 states the comparison, so the package does not make its own."""
    page = source.page_text(2)
    assert "No significant changes (p = 0.05)" in page
    assert "the specific growth rate of the culture at 30% (1.08/h) and 300% (1.00/h)" in page


def test_feed_target_rate_appears_on_page_3_as_well() -> None:
    """mu_set = 0.35 h^-1 is stated in the results as well as in the methods."""
    assert "maintain a specific growth rate of 0.35/h" in source.page_text(3)


def test_endpoint_appears_in_the_abstract_on_page_1_too() -> None:
    """The same readings are printed in the abstract; the results page is cited."""
    page = source.page_text(1)
    assert "109000 FU" in page
    assert "29.1 g/L" in page
    assert observations.ENDPOINT_PAGE == 3


def test_no_data_file_other_than_the_page_text_is_shipped() -> None:
    """No digitised series, no fitted curve, no data derived from the figures."""
    data = sorted(p.name for p in source.DATA_DIR.glob("*"))
    assert data == ["paper_pages.json"]


def test_missing_model_statements_that_cite_a_page_are_true_of_it() -> None:
    """Spot-check the page claims the absence records make."""
    assert "1.08/h" in source.page_text(2) and "1.00/h" in source.page_text(2)
    assert "109000 FU" in source.page_text(3) and "494 mg/L" in source.page_text(3)
    assert "0.075 vvm" in source.page_text(6) and "100 rpm" in source.page_text(6)
    assert "5 L B. Braun bioreac" in source.page_text(5)