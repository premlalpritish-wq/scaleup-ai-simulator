"""The feed-rate equation: fixtures, units, parameters, validation, determinism.

Test 1 of the contract (numerical fixtures), 2 (units and parameters), 3
(determinism) and 4 (no invented defaults) live here.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from baez2014 import equations as eq
from baez2014.feed_rate import (
    REPORTED_PARAMETERS,
    UNVALUED_RUN_INPUTS,
    FeedRateError,
    FeedRateNumericalError,
    FeedTimeBeforeStart,
    MissingRunInput,
    feed_rate,
)
from baez2014.provenance import Basis, Provenance
from baez2014.units import Dimension, UnitError, convert, dimension_of


def _case(case: dict):
    """Call the implementation exactly as the fixture specifies."""
    return feed_rate(
        t=float(case["inputs"]["t"]),
        t_F=float(case["inputs"]["t_F"]),
        X_F=float(case["inputs"]["X_F"]),
        V_F=float(case["inputs"]["V_F"]),
        units=case["input_units"],
        parameters=(
            None
            if case["parameters"] is None
            else {k: float(v) for k, v in case["parameters"].items()}
        ),
    )


# --------------------------------------------------------------------------- #
# 1. numerical fixtures
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "case_id",
    ["feed_at_onset", "one_hour_after_onset", "three_hours_after_onset",
     "same_point_in_other_units", "overridden_parameters", "zero_biomass_at_onset"],
)
def test_fixture_matches_independent_calculation(fixture_cases: dict, case_id: str) -> None:
    case = fixture_cases[case_id]
    expected = float(case["expected_feed_rate_l_per_h"])
    got = _case(case).feed_rate_l_per_h
    assert got == pytest.approx(expected, rel=case["relative_tolerance"])


def test_fixture_file_is_the_printed_equation(fixture_document: dict) -> None:
    equation = eq.equation("source_formula.exponential_feed_rate")
    assert fixture_document["equation"] == equation.statement
    assert fixture_document["output_unit"] == equation.output_unit
    assert fixture_document["equation_source"] == "Baez et al. 2014, p. 6, printed"
    assert equation.printed_page == 6
    assert fixture_document["reported_parameters"] == {
        "mu_set": "0.35 1/h",
        "Y_XS": "1.28 g/g",
        "m": "0.12 g/(g h)",
        "S_F": "141 g/L",
    }


def test_prefactor_matches_the_exact_rational_in_the_fixture(fixture_cases: dict) -> None:
    """The pre-exponential factor is pure rational arithmetic; check it exactly."""
    for case_id, case in fixture_cases.items():
        exact = Fraction(case["exact_pre_factor_l_per_h"])
        got = _case(case).pre_factor_l_per_h
        assert got == pytest.approx(float(exact), rel=1e-15), case_id


def test_exponent_argument_matches_the_exact_rational_in_the_fixture(fixture_cases: dict) -> None:
    for case_id, case in fixture_cases.items():
        exact = Fraction(case["exact_exponent_argument"])
        got = _case(case).exponent_argument
        assert got == pytest.approx(float(exact), rel=1e-15), case_id


def test_fixture_unit_conversion_case_equals_its_base_case(fixture_cases: dict) -> None:
    """The same physical point in other units is the same number."""
    converted = _case(fixture_cases["same_point_in_other_units"])
    base = _case(fixture_cases["one_hour_after_onset"])
    assert converted.feed_rate_l_per_h == pytest.approx(base.feed_rate_l_per_h, rel=1e-15)
    assert converted.input_units["X_F"] == "mg/L"
    assert converted.input_units["V_F"] == "mL"
    assert converted.inputs["X_F"] == base.inputs["X_F"]
    assert converted.inputs["V_F"] == base.inputs["V_F"]


def test_onset_case_is_exactly_the_prefactor(fixture_cases: dict) -> None:
    """At t = t_F the exponential factor is exp(0) = 1 exactly."""
    result = _case(fixture_cases["feed_at_onset"])
    assert result.elapsed_h == 0.0
    assert result.exponent_argument == 0.0
    assert result.feed_rate_l_per_h == result.pre_factor_l_per_h


def test_zero_biomass_is_zero_not_an_error(fixture_cases: dict) -> None:
    result = _case(fixture_cases["zero_biomass_at_onset"])
    assert result.feed_rate_l_per_h == 0.0


def test_output_is_in_the_printed_unit(fixture_cases: dict) -> None:
    for case in fixture_cases.values():
        result = _case(case)
        assert result.unit == "L/h"
        assert dimension_of(result.unit) is Dimension.VOLUME_RATE


# --------------------------------------------------------------------------- #
# 2. units and parameter handling
# --------------------------------------------------------------------------- #


def test_printed_parameters_are_reported_values_from_page_6() -> None:
    expected = {"mu_set": 0.35, "Y_XS": 1.28, "m": 0.12, "S_F": 141.0}
    assert set(REPORTED_PARAMETERS) == set(expected)
    for name, value in expected.items():
        quantity = REPORTED_PARAMETERS[name]
        assert quantity.value == value
        assert quantity.provenance is Provenance.REPORTED
        assert quantity.basis is Basis.OBSERVED
        assert quantity.printed_pages == (6,)


def test_default_run_uses_the_printed_parameters(fixture_cases: dict) -> None:
    result = _case(fixture_cases["feed_at_onset"])
    assert result.parameters == {
        "mu_set": 0.35,
        "Y_XS": 1.28,
        "m": 0.12,
        "S_F": 141.0,
    }
    assert result.parameters_are_reported is True
    assert result.deviations == ()


def test_parameter_override_is_recorded_not_silent(fixture_cases: dict) -> None:
    result = _case(fixture_cases["overridden_parameters"])
    assert result.parameters["mu_set"] == 0.5
    assert result.parameters_are_reported is False
    assert set(result.deviations) == {"mu_set", "Y_XS", "m"}
    assert "not the values the paper prints" in result.notes
    assert result.to_dict()["parameters_are_reported"] is False


def test_override_to_the_printed_value_is_not_a_deviation() -> None:
    result = feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, parameters={"m": 0.12})
    assert result.parameters_are_reported is True
    assert result.deviations == ()


def test_unknown_parameter_is_refused() -> None:
    with pytest.raises(KeyError, match="unknown parameters"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, parameters={"K_s": 1.0})


def test_zero_denominator_parameter_is_refused() -> None:
    with pytest.raises(ValueError, match="divides"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, parameters={"S_F": 0.0})
    with pytest.raises(ValueError, match="divides"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, parameters={"Y_XS": 0.0})


def test_units_are_converted_into_the_printed_unit() -> None:
    result = feed_rate(
        t=6.0, t_F=5.0, X_F=10_000.0, V_F=4000.0,
        units={"X_F": "mg/L", "V_F": "mL"},
    )
    assert result.inputs["X_F"] == pytest.approx(10.0)
    assert result.inputs["V_F"] == pytest.approx(4.0)
    assert result.parameter_units == {
        "mu_set": "1/h", "Y_XS": "g/g", "m": "g/(g h)", "S_F": "g/L",
    }


def test_wrong_dimension_is_refused() -> None:
    with pytest.raises(UnitError, match="dimension"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, units={"V_F": "mg"})


def test_unregistered_unit_is_refused() -> None:
    with pytest.raises(UnitError, match="unknown unit"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, units={"X_F": "g/dm3"})


def test_unit_for_an_unknown_input_is_refused() -> None:
    with pytest.raises(UnitError, match="inputs that do not exist"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0, units={"X": "g/L"})


def test_time_unit_conversion_is_applied_before_the_ordering_check() -> None:
    """t and t_F are compared after conversion into the printed unit (h)."""
    ok = feed_rate(t=360.0, t_F=300.0, X_F=10.0, V_F=4.0,
                   units={"t": "min", "t_F": "min"})
    assert ok.elapsed_h == pytest.approx(1.0)
    assert ok.inputs["t"] == pytest.approx(6.0)
    assert ok.inputs["t_F"] == pytest.approx(5.0)
    with pytest.raises(FeedTimeBeforeStart):
        # 240 min is 4 h, which is before a fed-batch start at 5 h
        feed_rate(t=240.0, t_F=5.0, X_F=10.0, V_F=4.0, units={"t": "min"})


def test_the_printed_expression_is_dimensionally_sound() -> None:
    """(mu/Y + m) is a specific rate and X*V/S is a volume, so F is L/h."""
    inputs = {i.key: i for i in eq.equation("source_formula.exponential_feed_rate").inputs}
    # mu_set/Y_XS and m must be summable, so they share one dimension even
    # though the paper prints them differently ("1/h" and "g/g h").
    assert inputs["mu_set"].dimension is Dimension.SPECIFIC_RATE
    assert inputs["m"].dimension is Dimension.SPECIFIC_RATE
    assert convert(0.12, "g/(g h)", "1/h") == 0.12
    # X_F*V_F/S_F: (g/L) * L / (g/L) == L
    product = (
        convert(10.0, "g/L", "g/L")
        * convert(4.0, "L", "L")
        / convert(141.0, "g/L", "g/L")
    )
    assert product == pytest.approx(40.0 / 141.0)
    assert dimension_of("L") is Dimension.VOLUME
    assert dimension_of("L/h") is Dimension.VOLUME_RATE


def test_result_carries_provenance_as_a_derived_quantity(fixture_cases: dict) -> None:
    quantity = _case(fixture_cases["one_hour_after_onset"]).to_quantity()
    assert quantity.provenance is Provenance.DERIVED
    assert quantity.basis is Basis.COMPUTED
    assert quantity.value == pytest.approx(0.15838706060983251)
    assert "source_formula.exponential_feed_rate" in quantity.method
    assert "X_F" in quantity.inputs and "mu_set" in quantity.inputs
    assert quantity.printed_pages == (6,)


def test_result_records_its_source(fixture_cases: dict) -> None:
    result = _case(fixture_cases["feed_at_onset"])
    assert result.equation_id == "source_formula.exponential_feed_rate"
    assert result.printed_page == 6
    assert result.source_reference == "Baez et al. 2014, p. 6, Methods: fed-batch culture"


# --------------------------------------------------------------------------- #
# 3. determinism
# --------------------------------------------------------------------------- #


def test_identical_inputs_give_bit_identical_output(fixture_cases: dict) -> None:
    case = fixture_cases["three_hours_after_onset"]
    runs = [_case(case) for _ in range(10)]
    values = {run.feed_rate_l_per_h for run in runs}
    assert len(values) == 1
    payloads = {repr(run.to_dict()) for run in runs}
    assert len(payloads) == 1


def test_determinism_survives_a_fresh_interpreter(fixture_cases: dict) -> None:
    """The result does not depend on interpreter state or on call order."""
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from baez2014.feed_rate import feed_rate\n"
        "print(repr(feed_rate(t=8.0, t_F=5.0, X_F=10.0, V_F=4.0).feed_rate_l_per_h))\n"
        % str(__import__("pathlib").Path(__file__).resolve().parents[1])
    )
    first = subprocess.run([sys.executable, "-c", script], capture_output=True,
                           text=True, check=True).stdout.strip()
    second = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, check=True).stdout.strip()
    expected = repr(_case(fixture_cases["three_hours_after_onset"]).feed_rate_l_per_h)
    assert first == second == expected


def test_exponential_term_is_the_paper_form_not_a_rearrangement() -> None:
    """A check on the arithmetic itself: exp is applied once, to mu_set*(t-t_F)."""
    result = feed_rate(t=8.0, t_F=5.0, X_F=10.0, V_F=4.0)
    expected = (
        (0.35 / 1.28 + 0.12) * (10.0 * 4.0 / 141.0) * math.exp(0.35 * 3.0)
    )
    assert result.feed_rate_l_per_h == expected
    assert result.exponent_argument == 0.35 * 3.0


# --------------------------------------------------------------------------- #
# 4. required run inputs are never defaulted
# --------------------------------------------------------------------------- #


def test_no_arguments_at_all_raises_and_names_every_input() -> None:
    with pytest.raises(MissingRunInput) as excinfo:
        feed_rate()
    assert excinfo.value.missing == ("X_F", "V_F", "t_F", "t")
    assert "none is defaulted" in str(excinfo.value)


@pytest.mark.parametrize("dropped", ["X_F", "V_F", "t_F", "t"])
def test_each_run_input_is_required(dropped: str) -> None:
    kwargs = {"t": 6.0, "t_F": 5.0, "X_F": 10.0, "V_F": 4.0}
    del kwargs[dropped]
    with pytest.raises(MissingRunInput) as excinfo:
        feed_rate(**kwargs)
    assert excinfo.value.missing == (dropped,)


def test_partial_call_names_all_the_missing_inputs() -> None:
    with pytest.raises(MissingRunInput) as excinfo:
        feed_rate(t=6.0)
    assert set(excinfo.value.missing) == {"X_F", "V_F", "t_F"}


def test_the_equation_lists_the_same_required_inputs() -> None:
    equation = eq.equation("source_formula.exponential_feed_rate")
    assert set(equation.required_run_inputs) == set(UNVALUED_RUN_INPUTS)
    assert set(equation.reported_parameters) == set(REPORTED_PARAMETERS)


def test_no_run_input_has_a_default_in_the_signature() -> None:
    import inspect

    signature = inspect.signature(feed_rate)
    for name in ("t", "t_F", "X_F", "V_F"):
        assert signature.parameters[name].default is None


# --------------------------------------------------------------------------- #
# ordering and domain
# --------------------------------------------------------------------------- #


def test_evaluation_time_may_equal_the_start_time() -> None:
    assert feed_rate(t=5.0, t_F=5.0, X_F=10.0, V_F=4.0).elapsed_h == 0.0


def test_evaluation_time_before_the_start_time_raises() -> None:
    with pytest.raises(FeedTimeBeforeStart) as excinfo:
        feed_rate(t=4.5, t_F=5.0, X_F=10.0, V_F=4.0)
    assert excinfo.value.t == 4.5
    assert excinfo.value.t_F == 5.0


@pytest.mark.parametrize("bad", ["10.0", True, [10.0], {"value": 10.0}, None])
def test_non_numeric_input_is_refused(bad: object) -> None:
    with pytest.raises((TypeError, MissingRunInput)):
        feed_rate(t=6.0, t_F=5.0, X_F=bad, V_F=4.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_input_is_refused(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        feed_rate(t=6.0, t_F=5.0, X_F=bad, V_F=4.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"X_F": -1.0, "V_F": 4.0},
        {"X_F": 10.0, "V_F": -4.0},
    ],
)
def test_negative_run_input_is_refused(kwargs: dict) -> None:
    with pytest.raises(ValueError, match="negative"):
        feed_rate(t=6.0, t_F=5.0, **kwargs)


def test_int_inputs_are_accepted() -> None:
    result = feed_rate(t=6, t_F=5, X_F=10, V_F=4)
    assert isinstance(result.feed_rate_l_per_h, float)
    assert result.inputs == {"X_F": 10.0, "V_F": 4.0, "t_F": 5.0, "t": 6.0}


# --------------------------------------------------------------------------- #
# V_F is strictly positive; X_F = 0 stays a legal boundary
# --------------------------------------------------------------------------- #


def test_positive_volume_is_accepted() -> None:
    result = feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0)
    assert result.inputs["V_F"] == 4.0
    assert result.feed_rate_l_per_h == pytest.approx(0.15838706060983251)


def test_zero_volume_is_refused() -> None:
    """A bioreactor with no working volume is not a fed-batch culture."""
    with pytest.raises(ValueError, match="V_F=0") as excinfo:
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=0.0)
    assert "strictly positive" in str(excinfo.value)
    assert "working volume" in str(excinfo.value)


def test_zero_volume_in_another_unit_is_also_refused() -> None:
    with pytest.raises(ValueError, match="V_F=0"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=0.0, units={"V_F": "mL"})


def test_negative_volume_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=-4.0)


def test_zero_biomass_stays_an_allowed_boundary() -> None:
    """X_F = 0 is a boundary of the printed expression, not a missing vessel."""
    result = feed_rate(t=5.0, t_F=5.0, X_F=0.0, V_F=4.0)
    assert result.feed_rate_l_per_h == 0.0
    assert result.inputs["X_F"] == 0.0


# --------------------------------------------------------------------------- #
# numerical range
# --------------------------------------------------------------------------- #


def test_long_but_representable_elapsed_times_still_evaluate() -> None:
    """No maximum cultivation time is invented; only the float range limits it."""
    for elapsed in (10.0, 100.0, 1000.0):
        result = feed_rate(t=elapsed, t_F=0.0, X_F=10.0, V_F=4.0)
        assert math.isfinite(result.feed_rate_l_per_h)
        assert result.feed_rate_l_per_h > 0.0


def test_exponential_overflow_raises_the_packages_own_exception() -> None:
    with pytest.raises(FeedRateNumericalError) as excinfo:
        feed_rate(t=2028.0, t_F=0.0, X_F=10.0, V_F=4.0)
    assert isinstance(excinfo.value, FeedRateError)
    assert excinfo.value.elapsed == 2028.0


def test_overflow_is_never_a_raw_arithmetic_error() -> None:
    """A `pytest.raises(FeedRateError)` can only pass if no raw error escapes.

    `math.exp` raises `OverflowError`, which is an `ArithmeticError` and not a
    `FeedRateError`; catching the package's type and then asserting the exact
    type is what proves the conversion happened rather than the call simply
    failing.
    """
    for elapsed in (5000.0, 1e6, 1e12):
        with pytest.raises(FeedRateError) as excinfo:
            feed_rate(t=elapsed, t_F=0.0, X_F=10.0, V_F=4.0)
        assert type(excinfo.value) is FeedRateNumericalError, elapsed
        assert not isinstance(excinfo.value, OverflowError)


def test_overflow_message_states_it_is_a_numerical_limit() -> None:
    with pytest.raises(FeedRateNumericalError) as excinfo:
        feed_rate(t=1e6, t_F=0.0, X_F=10.0, V_F=4.0)
    message = str(excinfo.value)
    assert "numerical limit" in message
    assert "not a statement about the culture" in message
    assert "no maximum cultivation time is implied" in message
    assert "mathematical extrapolation" in message
    assert "not a validated process prediction" in message


def test_non_finite_output_is_refused() -> None:
    """A product outside the float range is refused, not returned as inf."""
    with pytest.raises(FeedRateNumericalError):
        feed_rate(t=6.0, t_F=5.0, X_F=1e308, V_F=1e308)


def test_the_documented_fixture_still_holds_at_the_boundary() -> None:
    """The zero-biomass fixture is unaffected by the stricter V_F rule."""
    result = _case(fixture_zero := {
        "inputs": {"X_F": "0.0", "V_F": "4.0", "t_F": "5.0", "t": "5.0"},
        "input_units": {"X_F": "g/L", "V_F": "L", "t_F": "h", "t": "h"},
        "parameters": None,
    })
    assert result.feed_rate_l_per_h == pytest.approx(float(fixture_zero["inputs"]["X_F"]))