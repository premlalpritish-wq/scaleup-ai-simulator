"""The unit registry: an explicit whitelist, and nothing outside it."""

from __future__ import annotations

import pytest

from baez2014 import units
from baez2014.units import Dimension, UnitError, convert, dimension_of, is_convertible, unit


def test_every_printed_unit_is_registered() -> None:
    printed = {
        "h": Dimension.TIME,              # p. 6
        "L": Dimension.VOLUME,            # p. 6
        "L/h": Dimension.VOLUME_RATE,     # p. 6, "F(t) = feed rate (L/h)"
        "g/L": Dimension.MASS_CONCENTRATION,  # p. 6, X_F and S_F
        "mg/L": Dimension.MASS_CONCENTRATION,  # p. 3, 494 mg/L
        "g": Dimension.MASS,              # p. 3
        "1/h": Dimension.SPECIFIC_RATE,   # p. 6, "0.35 1/h"
        "g/g": Dimension.MASS_RATIO,      # p. 6, "1.28 g/g"
        "g/(g h)": Dimension.SPECIFIC_RATE,  # p. 6, "0.12 g/g h" as printed
        "FU": Dimension.FLUORESCENCE,     # p. 3, "109000 FU"
    }
    for symbol, dimension in printed.items():
        assert dimension_of(symbol) is dimension, symbol


def test_unknown_unit_raises_and_lists_the_registry() -> None:
    with pytest.raises(UnitError) as excinfo:
        units.unit("g/dm3")
    assert "unknown unit 'g/dm3'" in str(excinfo.value)
    assert "L/h" in str(excinfo.value)


def test_cross_dimension_conversion_is_refused() -> None:
    with pytest.raises(UnitError, match="dimension mismatch"):
        convert(1.0, "FU", "mg/L")
    with pytest.raises(UnitError, match="dimension mismatch"):
        convert(1.0, "h", "L")


def test_same_dimension_conversions_are_exact_enough() -> None:
    assert convert(141.0, "g/L", "mg/L") == pytest.approx(141000.0)
    assert convert(141000.0, "mg/L", "g/L") == pytest.approx(141.0)
    assert convert(4000.0, "mL", "L") == pytest.approx(4.0)
    assert convert(360.0, "min", "h") == pytest.approx(6.0)
    assert convert(1.0, "1/min", "1/h") == pytest.approx(60.0)


def test_the_two_printed_spellings_of_a_specific_rate_agree() -> None:
    """The paper adds mu_set/Y_XS to m, so 1/h and g/g h must be one dimension."""
    assert is_convertible("1/h", "g/(g h)")
    assert convert(0.12, "g/(g h)", "1/h") == pytest.approx(0.12)
    assert convert(0.35, "1/h", "g/(g h)") == pytest.approx(0.35)


def test_fluorescence_is_not_a_mass() -> None:
    assert not is_convertible("FU", "mg/L")
    assert not is_convertible("FU", "g/L")
    assert not is_convertible("mg/L", "FU")
    assert is_convertible("mg/L", "g/L")


def test_conversion_is_refused_for_unregistered_units_even_in_pairs() -> None:
    assert is_convertible("g/dm3", "mg/L") is False
    with pytest.raises(UnitError):
        convert(1.0, "g/dm3", "mg/L")


def test_require_dimension_states_the_mismatch() -> None:
    assert units.require_dimension("L", Dimension.VOLUME, what="V_F") == "L"
    with pytest.raises(UnitError, match="dimension mismatch"):
        units.require_dimension("FU", Dimension.VOLUME, what="V_F")


def test_printed_unit_notes_are_kept() -> None:
    assert "as printed" in unit("g/(g h)").note
    assert "no conversion to GFP mass" in unit("FU").note


def test_the_registry_holds_only_what_the_paper_needs() -> None:
    assert set(units.UNITS) == {
        "h", "min",
        "L", "mL",
        "L/h", "mL/h", "mL/min",
        "g", "mg",
        "g/L", "mg/L",
        "1/h", "1/min",
        "g/g",
        "g/(g h)",
        "FU",
    }
    for symbol, registered in units.UNITS.items():
        assert registered.dimension in set(Dimension), symbol
        assert registered.to_base > 0.0, symbol