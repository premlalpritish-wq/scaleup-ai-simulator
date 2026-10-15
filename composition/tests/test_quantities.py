"""The six value states, and the unit bridge they sit on.

These are the tests that pin the rule the whole project exists to enforce: an
absent value is never a zero, and a mass is never a mass flow.
"""

from __future__ import annotations

import pytest

from composition.contracts import (
    ContractError,
    ModelValue,
    ValueProvenance,
    ValueState,
    convert_value,
)
from composition.quantities import (
    REGISTRY,
    NonConvertibleUnitError,
    Quantity,
    QuantityMismatch,
    UnknownUnitError,
    convert,
    describe_registry,
    quantity_of,
)


# --------------------------------------------------------------------------- #
# unit lookup is keyed by (quantity, symbol), never by symbol alone
# --------------------------------------------------------------------------- #


class TestUnitRegistry:
    def test_percent_exists_under_two_incompatible_quantities(self):
        """The audit's finding: `%` is a mass fraction in Morris and a percent
        in Zielinski. Both readings must remain addressable."""
        assert REGISTRY.resolve("%", Quantity.MASS_FRACTION).to_base == 1.0e-2
        assert REGISTRY.resolve("%", Quantity.DIMENSIONLESS).to_base == 1.0e-2

    def test_resolving_percent_without_a_quantity_is_refused(self):
        with pytest.raises(QuantityMismatch) as excinfo:
            REGISTRY.resolve("%", Quantity.MASS)
        assert "symbol is not allowed to decide the quantity" in str(excinfo.value)

    def test_one_is_also_ambiguous(self):
        assert REGISTRY.resolve("1", Quantity.MASS_FRACTION).linear
        assert REGISTRY.resolve("1", Quantity.DIMENSIONLESS).linear

    def test_unregistered_unit_raises_rather_than_defaulting(self):
        with pytest.raises(UnknownUnitError) as excinfo:
            REGISTRY.resolve("furlong", Quantity.MASS)
        assert "not registered" in str(excinfo.value)

    def test_the_models_gap_unit_is_reported_not_guessed(self):
        """Zielinski declares a specific growth rate of 1/h, which its own unit
        registry does not define. The composition contract has to say so rather
        than invent an hour inverse."""
        with pytest.raises(UnknownUnitError):
            REGISTRY.resolve("1/h", Quantity.DIMENSIONLESS)

    def test_non_linear_quantities_refuse_conversion(self):
        assert not REGISTRY.resolve("pH", Quantity.PH).linear
        assert not REGISTRY.resolve("OD600", Quantity.DIMENSIONLESS).linear

    def test_describe_registry_reports_the_ambiguous_symbols(self):
        described = describe_registry()
        assert "%" in described["ambiguous_symbols"]
        assert "1" in described["ambiguous_symbols"]
        assert "absorbance" in described["quantities"]


# --------------------------------------------------------------------------- #
# conversion is within one quantity, or it does not happen
# --------------------------------------------------------------------------- #


class TestConversion:
    def test_mass_converts_between_the_two_models_base_units(self):
        """Morris's base is kg, Zielinski's is g. The bridge is declared here,
        once, explicitly."""
        result = convert(224.0, "g", "kg", Quantity.MASS)
        assert result.value == pytest.approx(0.224)
        assert result.factor == pytest.approx(1.0e-3)

    def test_mass_flow_converts_within_itself(self):
        assert convert(2.0, "g/h", "kg/h", Quantity.MASS_FLOW).value == pytest.approx(
            0.002
        )

    def test_identical_units_are_an_identity_not_a_multiplication(self):
        result = convert(7.5, "kg", "kg", Quantity.MASS)
        assert result.factor == 1.0
        assert result.value == 7.5

    def test_ph_never_converts(self):
        with pytest.raises(NonConvertibleUnitError):
            convert(7.0, "pH", "pH", Quantity.PH)

    def test_ph_cannot_be_read_as_a_dimensionless_ratio(self):
        """pH is log10 of hydrogen-ion activity. 7.0 pH is not 7."""
        with pytest.raises(QuantityMismatch):
            convert(7.0, "pH", "1", Quantity.PH)

    def test_mass_fraction_percent_and_generic_percent_are_not_interchangeable(self):
        """Morris's % enters sum(w) = 1. Zielinski's 40 % glucose does not.
        The symbols are identical and the meanings are not."""
        mass_percent = REGISTRY.resolve("%", Quantity.MASS_FRACTION)
        plain_percent = REGISTRY.resolve("%", Quantity.DIMENSIONLESS)
        assert mass_percent.quantity is not plain_percent.quantity
        # asking for one and getting the other is impossible: the lookup is
        # keyed by the pair, so there is no way to obtain the wrong one.
        assert REGISTRY.resolve("%", Quantity.MASS_FRACTION) is mass_percent
        assert REGISTRY.resolve("%", Quantity.DIMENSIONLESS) is plain_percent

    def test_quantity_of_helper_is_only_for_authoring_aids(self):
        assert quantity_of("g", prefer=Quantity.MASS) is Quantity.MASS
        with pytest.raises(QuantityMismatch):
            quantity_of("1")


# --------------------------------------------------------------------------- #
# the six value states
# --------------------------------------------------------------------------- #


class TestValueStates:
    def test_number_and_zero_are_distinct_states(self):
        five = ModelValue.number(5.0, quantity=Quantity.MASS, unit="kg",
                                 provenance=ValueProvenance.REPORTED)
        zero = ModelValue.number(0.0, quantity=Quantity.MASS, unit="kg",
                                 provenance=ValueProvenance.SOLVED)
        assert five.state is ValueState.NUMBER
        assert zero.state is ValueState.ZERO
        assert zero.is_resolved and zero.value == 0.0

    def test_a_zero_cannot_wear_a_number_label(self):
        with pytest.raises(ContractError):
            ModelValue(state=ValueState.ZERO, quantity=Quantity.MASS, unit="kg",
                       value=3.0)

    def test_an_absent_state_may_not_carry_a_number(self):
        for state in (ValueState.UNRESOLVED, ValueState.UNKNOWN,
                      ValueState.NOT_REPORTED):
            with pytest.raises(ContractError) as excinfo:
                ModelValue(state=state, quantity=Quantity.MASS, unit="kg", value=0.0)
            assert "never be written as 'zero'" in str(excinfo.value)

    def test_a_numeric_state_requires_a_number(self):
        with pytest.raises(ContractError):
            ModelValue(state=ValueState.NUMBER, quantity=Quantity.MASS, unit="kg")

    def test_a_range_is_never_collapsed_to_a_point(self):
        ranged = ModelValue.unavailable(
            ValueState.RANGE, quantity=Quantity.TIME, unit="h",
            value_range=(15.0, 16.0),
            reason="reported as '15-16 h'",
        )
        assert not ranged.is_resolved
        assert ranged.value is None
        assert ranged.value_range == (15.0, 16.0)

    def test_only_the_range_state_may_carry_an_interval(self):
        with pytest.raises(ContractError) as excinfo:
            ModelValue(state=ValueState.NUMBER, quantity=Quantity.TIME, unit="h",
                       value=16.0, value_range=(15.0, 16.0))
        assert "never collapsed to a point value" in str(excinfo.value)

    def test_all_six_states_exist_and_only_two_hold_numbers(self):
        assert {s.value for s in ValueState} == {
            "number", "zero", "range", "not_reported", "unresolved", "unknown"
        }
        assert {s.value for s in ValueState if s.has_number} == {"number", "zero"}

    def test_round_trips_through_json(self):
        original = ModelValue.unavailable(
            ValueState.UNRESOLVED, quantity=Quantity.MASS_FLOW, unit="kg/h",
            reason="under-determined",
        )
        restored = ModelValue.from_dict(original.to_dict())
        assert restored.state is ValueState.UNRESOLVED
        assert restored.value is None
        assert restored.reason == "under-determined"


# --------------------------------------------------------------------------- #
# converting a value is not a way to resolve it
# --------------------------------------------------------------------------- #


class TestValueConversion:
    def test_a_resolved_value_converts_within_its_quantity(self):
        original = ModelValue.number(224.0, quantity=Quantity.MASS, unit="g",
                                     provenance=ValueProvenance.REPORTED)
        converted, record = convert_value(original, "kg", Quantity.MASS)
        assert converted.value == pytest.approx(0.224)
        assert converted.unit == "kg"
        assert record["factor"] == pytest.approx(1.0e-3)

    def test_an_unresolved_value_cannot_be_converted_into_a_number(self):
        unresolved = ModelValue.unavailable(
            ValueState.UNRESOLVED, quantity=Quantity.MASS, unit="kg",
            reason="under-determined",
        )
        with pytest.raises(ContractError) as excinfo:
            convert_value(unresolved, "g", Quantity.MASS)
        assert "unresolved value cannot become a resolved one" in str(
            excinfo.value
        )

    def test_a_range_cannot_be_converted_into_a_point(self):
        ranged = ModelValue.unavailable(
            ValueState.RANGE, quantity=Quantity.TIME, unit="h",
            value_range=(15.0, 16.0), reason="reported as an interval",
        )
        with pytest.raises(ContractError):
            convert_value(ranged, "min", Quantity.TIME)

    def test_conversion_across_quantities_is_refused(self):
        original = ModelValue.number(1.0, quantity=Quantity.MASS, unit="kg",
                                     provenance=ValueProvenance.REPORTED)
        with pytest.raises(ContractError) as excinfo:
            convert_value(original, "kg/h", Quantity.MASS_FLOW)
        assert "change of quantity, not of unit" in str(excinfo.value)