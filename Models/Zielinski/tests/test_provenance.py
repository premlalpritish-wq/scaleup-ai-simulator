"""Provenance and unit integrity rules.

These tests encode the model's core promise: an absent value stays absent.
"""

from __future__ import annotations

import pytest

from scaleup_ai import Provenance, Quantity, QuantityError, convert, is_convertible
from scaleup_ai.units import UnitError

from models.source import ev


# --------------------------------------------------------------------------- #
# unknown stays unknown
# --------------------------------------------------------------------------- #


def test_unknown_quantity_cannot_hold_a_value():
    with pytest.raises(QuantityError, match="refusing to fabricate"):
        Quantity("q", "label", Provenance.UNKNOWN, value=0.0, unit="g")


def test_unknown_quantity_cannot_hold_a_range():
    with pytest.raises(QuantityError, match="refusing to fabricate"):
        Quantity("q", "label", Provenance.UNKNOWN, value_range=(1.0, 2.0), unit="g")


def test_unknown_quantity_is_unresolved_and_has_no_point_value():
    q = Quantity("q", "label", Provenance.UNKNOWN, unit="g")
    assert q.value is None
    assert q.point_value is None
    assert q.is_resolved is False
    assert q.basis.value == "unresolved"


def test_reported_range_is_not_collapsed_to_a_point_value():
    from models.zielinski_2019 import build_graph

    graph = build_graph()
    q = graph.node("N01").operating_conditions["growth_duration"]
    assert q.provenance is Provenance.REPORTED
    assert q.value is None
    assert q.value_range == (15.0, 16.0)


def test_no_observed_quantity_is_zero_by_default():
    """A zero must always be an explicitly reported zero, never a stand-in."""
    from models.zielinski_2019 import build_graph

    graph = build_graph()
    for location, qid, q in graph.iter_quantities():
        if q.provenance is not Provenance.UNKNOWN:
            continue
        assert q.value is None and q.value_range is None, f"{location}:{qid}"


def test_every_declared_quantity_has_a_provenance_class(graph):
    seen = 0
    for _location, _qid, q in graph.iter_quantities():
        assert isinstance(q.provenance, Provenance)
        seen += 1
    assert seen > 150


def test_derived_quantities_declare_method_and_inputs(graph):
    for _location, _qid, q in graph.iter_quantities():
        if q.provenance is not Provenance.DERIVED:
            continue
        assert q.method, "a derived value must carry its arithmetic"
        assert q.inputs, "a derived value must name its inputs"


def test_digitized_values_carry_uncertainty():
    graph = __import__("models.zielinski_2019", fromlist=["build_graph"]).build_graph()
    traj = [
        q
        for _loc, _qid, q in graph.iter_quantities()
        if q.quantity_id.startswith("od600_h")
    ]
    assert len(traj) == 19
    for q in traj:
        assert q.provenance is Provenance.DIGITIZED
        assert q.uncertainty is not None
        assert q.uncertainty.hi > q.uncertainty.lo


def test_basis_separates_observed_from_computed():
    reported_q = Quantity(
        "r", "l", Provenance.REPORTED, 1.0, "g", evidence=(ev(4, section="4.2"),)
    )
    derived_q = Quantity(
        "d", "l", Provenance.DERIVED, 1.0, "g", method="a/b", inputs=("a", "b")
    )
    assert reported_q.basis.value == "observed_reference"
    assert derived_q.basis.value == "computed"
    assert reported_q.is_observed and not derived_q.is_observed


# --------------------------------------------------------------------------- #
# evidence references
# --------------------------------------------------------------------------- #


def test_printed_page_mapping_is_checked():
    from dataclasses import replace

    assert ev(1).printed_page == 63
    assert ev(7).printed_page == 69
    # the pdf/printed page offset is enforced, not assumed
    with pytest.raises(ValueError, match="not consistent"):
        replace(ev(2, section="x"), printed_page=999)


def test_every_evidence_reference_points_into_the_article(graph):
    for _location, _qid, q in graph.iter_quantities():
        for e in q.evidence:
            assert e.source_id == "zielinski2019"
            assert 1 <= e.pdf_page <= 7
            assert e.printed_page == e.pdf_page + 62


def test_reported_quantities_are_evidence_backed(graph):
    """A reported value without a source pointer is a defect."""
    for location, qid, q in graph.iter_quantities():
        if q.provenance is not Provenance.REPORTED:
            continue
        assert q.evidence, f"{location}:{qid} is reported but cites no evidence"


def test_reported_quantities_retain_the_original_wording(graph):
    quoted = [q for _l, _i, q in graph.iter_quantities()
              if q.provenance is Provenance.REPORTED]
    with_text = [q for q in quoted if q.original_text]
    # headline numbers must be quoted verbatim; the remainder cite page+section
    for qid in (
        "inoculum_volume", "fermenter_nominal_volume", "starting_medium_volume",
        "fermenter_temperature", "od600_max", "dissolved_protein",
        "protein_after_refolding", "activity", "measured_molecular_mass",
    ):
        q = next(q for _l, _i, q in graph.iter_quantities() if q.quantity_id == qid)
        assert q.original_text, qid
    assert len(with_text) / len(quoted) > 0.4


# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #


def test_unit_conversions_are_dimension_checked():
    assert convert(4, "L", "mL") == 4000.0
    assert convert(1, "dm3", "mL") == 1000.0
    assert convert(70, "mg/dL", "g/L") == pytest.approx(0.7)
    with pytest.raises(UnitError):
        convert(1, "g", "mL")


def test_ph_is_never_linearly_converted():
    assert not is_convertible("pH", "1")
    assert not is_convertible("1", "pH")
    with pytest.raises(UnitError):
        convert(7.0, "pH", "1")


def test_unknown_unit_raises():
    with pytest.raises(UnitError, match="unknown unit"):
        convert(1, "furlong", "m")


def test_numeric_quantity_requires_a_unit():
    with pytest.raises(QuantityError, match="requires a unit"):
        Quantity("q", "l", Provenance.REPORTED, value=1.0)


def test_point_value_and_range_are_mutually_exclusive():
    with pytest.raises(QuantityError, match="either a point value or a range"):
        Quantity("q", "l", Provenance.REPORTED, value=1.0, unit="g", value_range=(1.0, 2.0))