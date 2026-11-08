"""The feed-rate calculation, and the validation around it.

    F(t) = ((mu_set / Y_XS) + m) * (X_F * V_F / S_F) * exp(mu_set*(t - t_F))

printed on p. 6 of Baez et al. (2014). The four run inputs `X_F`, `V_F`,
`t_F` and `t` are required for every call. The paper prints values for
`mu_set`, `Y_XS`, `m` and `S_F`; it prints **no** value for `X_F`, `V_F` or
`t_F`, only their definitions, so there is nothing to default them to and
this module will not invent one.

Input-domain checks, and why each exists. These are checks on the numbers a
caller supplies, not statements about the biology:

  * a run input must be a finite real number (a `bool` is not a number here);
  * a run input must not be negative -- a negative biomass concentration or
    elapsed time is outside the domain the printed expression describes;
  * `V_F`, `S_F` and `Y_XS` must be strictly positive rather than merely
    non-negative. `S_F` and `Y_XS` appear in denominators, so zero is
    undefined there; `V_F` is the working volume at fed-batch onset and a
    bioreactor holding no culture is not a fed-batch culture, so zero is
    refused for that reason rather than because the arithmetic breaks.
    `X_F` = 0 stays allowed: it is a boundary of the printed expression, not a
    missing vessel.
  * `t` must not be earlier than `t_F`, which the contract requires and which
    the exponential makes meaningless (it would evaluate the feed profile
    backwards);
  * a supplied unit must be registered and of the input's dimension; anything
    else raises rather than being ignored.

A numerical failure is reported through the same hierarchy. `math.exp`
overflows for a long enough elapsed time, and the product can exceed the float
range for extreme inputs; both raise `FeedRateNumericalError`. That is a limit
of the arithmetic, not a statement about the process: this package imposes no
maximum cultivation time, and any value it returns for times outside the
conditions the paper supports is mathematical extrapolation of a printed
formula, not a validated process prediction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from . import equations as _eq
from . import source
from .equations import Equation
from .provenance import EvidenceRef, Quantity, derived, reported
from .units import Dimension, UnitError, convert, require_dimension

FEED_EQUATION_ID = "source_formula.exponential_feed_rate"

#: Where the parameter definitions are printed. p. 6 defines mu_set, Y_X/S, m,
#: XF, VF and SF in one sentence under the feed equation.
PARAMETER_PAGE = 6


class FeedRateError(ValueError):
    """Base class for a call that cannot be made as written."""


class MissingRunInput(FeedRateError):
    """A run-specific input was not supplied.

    Raised instead of substituting a default: the paper prints no value for
    `X_F`, `V_F` or `t_F`, so any default would be invented.
    """

    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__(
            "feed_rate requires the run-specific inputs "
            f"{list(missing)}; Baez et al. (2014) print no value for them, so "
            f"none is defaulted"
        )
        self.missing = missing


class FeedTimeBeforeStart(FeedRateError):
    """The evaluation time precedes the fed-batch start time."""

    def __init__(self, t: float, t_F: float) -> None:
        super().__init__(
            f"evaluation time t={t:g} h is earlier than the fed-batch start "
            f"time t_F={t_F:g} h; the printed expression is defined for t >= t_F"
        )
        self.t = t
        self.t_F = t_F


class FeedRateNumericalError(FeedRateError):
    """The printed expression could not be evaluated as a finite number.

    This is a limit of floating-point arithmetic, not a limit of the process.
    The message says so explicitly, because "the model refused" would otherwise
    be read as "this time is impossible".
    """

    def __init__(self, message: str, *, elapsed: float, exponent_argument: float) -> None:
        super().__init__(
            f"{message} Evaluated over {elapsed:g} h from fed-batch onset "
            f"(exponent argument {exponent_argument:g}). "
            "This is a numerical limit of evaluating the printed formula, not a "
            "statement about the culture: no maximum cultivation time is "
            "implied, and any feed rate this package returns outside the "
            "conditions the paper supports is mathematical extrapolation, not "
            "a validated process prediction."
        )
        self.elapsed = elapsed
        self.exponent_argument = exponent_argument


def _p6(section: str | None = None, quote: str | None = None) -> EvidenceRef:
    return EvidenceRef(printed_page=PARAMETER_PAGE, section=section, quote=quote)


#: The four parameters the paper prints, as reported quantities. Their values
#: are the defaults for `feed_rate`, and each one keeps its printed unit.
REPORTED_PARAMETERS: dict[str, Quantity] = {
    "mu_set": reported(
        "parameter.mu_set",
        "specific growth rate set by the feed",
        0.35,
        "1/h",
        _p6(quote="(0.35 1/h)"),
        original_unit="1/h",
        notes=(
            "Printed on p. 6 as the specific growth rate. p. 3 states the same "
            "value as 0.35/h: 'the exponential feeding was initiated to maintain "
            "a specific growth rate of 0.35/h'. This is the feed's target "
            "growth rate, not a prediction for any culture."
        ),
    ),
    "Y_XS": reported(
        "parameter.Y_XS",
        "biomass yield on glucose",
        1.28,
        "g/g",
        _p6(quote="(1.28 g/g)"),
        original_unit="g/g",
        notes=(
            "Printed on p. 6 as the biomass yield on glucose, estimated from "
            "the exponential growth phase in batch cultures. The paper does not "
            "give the estimation procedure in detail."
        ),
    ),
    "m": reported(
        "parameter.m",
        "maintenance coefficient",
        0.12,
        "g/(g h)",
        _p6(quote="(0.12 g/g h)"),
        original_unit="g/g h",
        notes="Printed on p. 6 as '0.12 g/g h'; the unit is retained as printed.",
    ),
    "S_F": reported(
        "parameter.S_F",
        "glucose concentration in the feed solution",
        141.0,
        "g/L",
        _p6(quote="(141 g/L)"),
        original_unit="g/L",
        notes=(
            "Printed on p. 6. The feed solution composition on p. 5 lists "
            "'282 g/L yeast extract, 141 g/L glucose'."
        ),
    ),
}

#: The definitions the paper prints for the three inputs it does not value.
UNVALUED_RUN_INPUTS: dict[str, str] = {
    "X_F": (
        "p. 6: 'the V_F and X_F are the volume and biomass concentration in "
        "the bioreactor at the onset of fed-batch procedure'. No number is "
        "printed for X_F."
    ),
    "V_F": (
        "p. 6: 'the V_F and X_F are the volume and biomass concentration in "
        "the bioreactor at the onset of fed-batch procedure'. No number is "
        "printed for V_F. The 4 L on p. 6 is the initial *batch* volume, "
        "before fed-batch begins, and is not V_F."
    ),
    "t_F": (
        "p. 3 reports when feeding started relative to the culture ('After "
        "five hours growth, the exponential feeding was initiated'), but no "
        "time value enters the printed equation, so t_F is supplied per run."
    ),
    "t": (
        "the time at which F(t) is evaluated. p. 6 prints F(t) as a function "
        "of t and prints no value of it, so t is supplied per run."
    ),
}

_RUN_INPUT_ORDER = ("X_F", "V_F", "t_F", "t")

_PARAMETER_DIMENSIONS: dict[str, Dimension] = {
    "mu_set": Dimension.SPECIFIC_RATE,
    "Y_XS": Dimension.MASS_RATIO,
    "m": Dimension.SPECIFIC_RATE,
    "S_F": Dimension.MASS_CONCENTRATION,
}


@dataclass(frozen=True)
class FeedRateResult:
    """One evaluation of the printed feed equation, with its full audit trail."""

    equation_id: str
    feed_rate_l_per_h: float
    inputs: Mapping[str, float]
    input_units: Mapping[str, str]
    parameters: Mapping[str, float]
    parameter_units: Mapping[str, str]
    elapsed_h: float
    exponent_argument: float
    pre_factor_l_per_h: float
    deviations: tuple[str, ...]
    source_reference: str
    printed_page: int
    notes: str = field(default="")

    @property
    def unit(self) -> str:
        return "L/h"

    @property
    def parameters_are_reported(self) -> bool:
        """True when every parameter is the value the paper prints."""
        return not self.deviations

    def to_quantity(self) -> Quantity:
        """The result as a `DERIVED` quantity, naming its inputs."""
        return derived(
            "feed_rate",
            "exponential fed-batch feed rate",
            self.feed_rate_l_per_h,
            self.unit,
            method=(
                f"{self.equation_id}: F(t) = (mu_set/Y_XS + m) * (X_F*V_F/S_F) "
                f"* exp(mu_set*(t - t_F)), evaluated at t={self.inputs['t']:g} h "
                f"with t_F={self.inputs['t_F']:g} h"
            ),
            inputs=tuple(sorted(self.inputs)) + tuple(sorted(self.parameters)),
            evidence=(EvidenceRef(printed_page=self.printed_page),),
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation_id": self.equation_id,
            "feed_rate": self.feed_rate_l_per_h,
            "unit": self.unit,
            "inputs": dict(self.inputs),
            "input_units": dict(self.input_units),
            "parameters": dict(self.parameters),
            "parameter_units": dict(self.parameter_units),
            "elapsed_h": self.elapsed_h,
            "exponent_argument": self.exponent_argument,
            "pre_factor_l_per_h": self.pre_factor_l_per_h,
            "parameters_are_reported": self.parameters_are_reported,
            "deviations": list(self.deviations),
            "source_reference": self.source_reference,
            "printed_page": self.printed_page,
        }


def _finite(value: Any, name: str) -> float:
    """Accept a real number and nothing else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be a real number, not {type(value).__name__} ({value!r})"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return number


def _resolve_units(
    names: tuple[str, ...],
    declared: Mapping[str, str],
    supplied: Mapping[str, str] | None,
) -> dict[str, str]:
    if not supplied:
        return dict(declared)
    unknown = [name for name in supplied if name not in declared]
    if unknown:
        raise UnitError(
            f"units given for inputs that do not exist: {sorted(unknown)}; "
            f"known inputs: {sorted(declared)}"
        )
    resolved = dict(declared)
    resolved.update({name: symbol for name, symbol in supplied.items()})
    return resolved


def _in_unit(value: Any, name: str, symbol: str, dimension: Dimension,
             *, positive: str | None = None) -> float:
    """Validate one supplied number and return it in the declared unit.

    `positive`, when given, is the reason this input must be strictly greater
    than zero. The reason is stated per input because the arithmetic reason and
    the domain reason are not the same thing: `S_F` and `Y_XS` are denominators
    (zero makes the expression undefined), whereas `V_F` is a multiplier and
    zero there is refused because it denotes an empty vessel, not because the
    arithmetic breaks.
    """
    require_dimension(symbol, dimension, what=name)
    number = _finite(value, name)
    if number < 0.0:
        raise ValueError(
            f"{name}={number:g} {symbol} is negative; the printed expression "
            f"describes no such input"
        )
    if positive is not None and number == 0.0:
        raise ValueError(
            f"{name}=0 {symbol} must be strictly positive: {positive}."
        )
    return number


def feed_rate(
    *,
    t: float | None = None,
    t_F: float | None = None,
    X_F: float | None = None,
    V_F: float | None = None,
    units: Mapping[str, str] | None = None,
    parameters: Mapping[str, float] | None = None,
) -> FeedRateResult:
    """Evaluate the printed exponential feed equation.

    `X_F`, `V_F`, `t_F` and `t` are required and have no defaults: the paper
    prints values for none of them. `units` maps an input name to the unit its
    value is given in; the value is converted into the unit the paper prints.
    `parameters` overrides a printed parameter for a what-if run; every
    override is recorded on the result and reported by
    `FeedRateResult.parameters_are_reported`.

    The same inputs always give the same output. There is no iteration, no
    tolerance and no state.
    """
    equation: Equation = _eq.equation(FEED_EQUATION_ID)

    supplied_run = {"X_F": X_F, "V_F": V_F, "t_F": t_F, "t": t}
    missing = tuple(name for name in _RUN_INPUT_ORDER if supplied_run[name] is None)
    if missing:
        raise MissingRunInput(missing)

    declared_input_units = {i.key: i.unit for i in equation.inputs}
    declared_parameter_units = {
        i.key: i.unit for i in equation.inputs if i.origin == "reported_parameter"
    }
    input_dimensions = {i.key: i.dimension for i in equation.inputs}

    supplied_units = _resolve_units(
        _RUN_INPUT_ORDER, declared_input_units, units
    )
    parameter_units = _resolve_units(
        tuple(REPORTED_PARAMETERS), declared_parameter_units, None
    )

    # --- run inputs ---------------------------------------------------------
    # V_F is strictly positive: it is the working volume at fed-batch onset,
    # and an empty vessel is not a fed-batch culture. X_F = 0 stays allowed --
    # it is a boundary of the printed expression, not a missing vessel.
    positive_reasons = {
        "V_F": (
            "V_F is the working volume at fed-batch onset, and a bioreactor "
            "holding no culture is not a fed-batch culture. (The printed "
            "expression still multiplies by V_F, so this is a statement about "
            "the run being described, not about the arithmetic.)"
        ),
    }
    run: dict[str, float] = {}
    for name in _RUN_INPUT_ORDER:
        run[name] = _in_unit(
            supplied_run[name],
            name,
            supplied_units[name],
            input_dimensions[name],
            positive=positive_reasons.get(name),
        )
    run = {
        name: convert(value, supplied_units[name], declared_input_units[name])
        for name, value in run.items()
    }

    if run["t"] < run["t_F"]:
        raise FeedTimeBeforeStart(run["t"], run["t_F"])

    # --- parameters ---------------------------------------------------------
    overrides = dict(parameters or {})
    unknown_parameters = [name for name in overrides if name not in REPORTED_PARAMETERS]
    if unknown_parameters:
        raise KeyError(
            f"unknown parameters {sorted(unknown_parameters)}; the printed "
            f"parameters are {sorted(REPORTED_PARAMETERS)}"
        )

    values: dict[str, float] = {}
    deviations: list[str] = []
    denominator_reasons = {
        "Y_XS": "the printed expression divides by Y_XS, so zero is undefined",
        "S_F": "the printed expression divides by S_F, so zero is undefined",
    }
    for name, reported_quantity in REPORTED_PARAMETERS.items():
        if name in overrides:
            number = _in_unit(
                overrides[name],
                f"parameter {name}",
                parameter_units[name],
                _PARAMETER_DIMENSIONS[name],
                positive=denominator_reasons.get(name),
            )
            if number != reported_quantity.value:
                deviations.append(name)
        else:
            number = float(reported_quantity.value)  # type: ignore[arg-type]
        values[name] = number

    values.update(run)

    elapsed = run["t"] - run["t_F"]
    exponent = values["mu_set"] * elapsed

    # The exponential can overflow, and the product can leave the float range
    # for extreme inputs. Both are reported through the package's own
    # exception hierarchy rather than escaping as a raw OverflowError.
    try:
        rate = equation.evaluate(values)
    except OverflowError as exc:
        raise FeedRateNumericalError(
            f"exp(mu_set*(t - t_F)) overflowed the float range ({exc}).",
            elapsed=elapsed,
            exponent_argument=exponent,
        ) from exc
    if not math.isfinite(rate):
        raise FeedRateNumericalError(
            f"the printed expression produced a non-finite feed rate ({rate!r}).",
            elapsed=elapsed,
            exponent_argument=exponent,
        )

    pre_factor = (
        (values["mu_set"] / values["Y_XS"] + values["m"])
        * (run["X_F"] * run["V_F"] / values["S_F"])
    )
    notes = ""
    if deviations:
        notes = (
            "parameters "
            + ", ".join(sorted(deviations))
            + " were supplied by the caller and are not the values the paper "
            "prints"
        )

    return FeedRateResult(
        equation_id=equation.equation_id,
        feed_rate_l_per_h=rate,
        inputs=run,
        input_units=supplied_units,
        parameters={k: values[k] for k in REPORTED_PARAMETERS},
        parameter_units=parameter_units,
        elapsed_h=elapsed,
        exponent_argument=exponent,
        pre_factor_l_per_h=pre_factor,
        deviations=tuple(sorted(deviations)),
        source_reference=source.reference(
            equation.printed_page, section="Methods: fed-batch culture"
        ),
        printed_page=equation.printed_page,
        notes=notes,
    )