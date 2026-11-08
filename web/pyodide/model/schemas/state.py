"""State and initial conditions for the growth model.

The state of a run is the six quantities eq. (1)-(16) integrate:

==========  ==========================================  ==========
symbol      meaning (paper's notation table, p. 2)      unit
==========  ==========================================  ==========
``X``       biomass concentration                      g/L
``S1``      glycerol concentration                     g/L
``S2``      complex nitrogen-rich substrate            g/L
``DO``      dissolved oxygen                           % of saturation
``V``       volume of the mixture                      L
``e1``      normalised key-enzyme-1 fraction e1/e_m1    1
``e2``      normalised key-enzyme-2 fraction e2/e_m2    1
==========  ==========================================  ==========

**The enzyme state is a normalised fraction, not a concentration.** Eq. (5) is
written ``mu_k = mum_k * (e_k/e_mk) * r_k`` and eq. (7) differentiates the
ratio ``e_k/e_mk`` directly, so ``e_mk`` never appears as a state and needs no
value. The two initial ratios are Table 2 parameters (`e_ratio1_0`,
`e_ratio2_0`) that are used as initial states.

Initial conditions are the second reason this module exists. The paper reports
an initial OD600 of 0.05 and an initial glycerol of 2.76 g/L, and it fills the
flask with 100 mL, but it reports **no** OD600-to-dry-cell-weight calibration,
**no** initial dissolved oxygen, and **no** initial complex-substrate
concentration as a model input. Those are therefore required from the caller:

  * ``X0``      unknown from the paper -- OD600 0.05 is not convertible to g/L
    without a calibration the paper does not print;
  * ``DO0``     unknown from the paper;
  * ``S2_0``    unknown as a model input (the SOB recipe's 5 g/L yeast extract
    is a reported medium composition, not a stated model initial condition);
  * ``S1_0``    reported: 2.76 g/L;
  * ``V0``      reported: 100 mL = 0.1 L.

:class:`InitialConditions` therefore distinguishes a supplied value from a
reported one, and refuses to simulate while anything is unresolved. Nothing
here defaults to zero: a zero biomass is a claim, not an absence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .provenance import Provenance, SourceRef, ValueState
from .units import QuantityKind, UnitError, convert, require

#: state key -> (symbol, quantity kind, printed unit)
STATE_FIELDS: dict[str, tuple[str, QuantityKind, str]] = {
    "X": ("X", QuantityKind.MASS_CONCENTRATION, "g/L"),
    "S1": ("S1", QuantityKind.MASS_CONCENTRATION, "g/L"),
    "S2": ("S2", QuantityKind.MASS_CONCENTRATION, "g/L"),
    "DO": ("DO", QuantityKind.DISSOLVED_OXYGEN_PERCENT, "%"),
    "V": ("V", QuantityKind.VOLUME, "L"),
    "e1": ("e1/e_m1", QuantityKind.ENZYME_RATIO, "1"),
    "e2": ("e2/e_m2", QuantityKind.ENZYME_RATIO, "1"),
}

#: Fields that must be strictly positive for the balances to be defined.
STRICTLY_POSITIVE = ("X", "V")

#: Fields that must be non-negative.
NON_NEGATIVE = ("X", "S1", "S2", "DO", "e1", "e2")

#: Dissolved oxygen is a percentage and cannot leave its physical range.
DO_MIN, DO_MAX = 0.0, 100.0


class StateError(ValueError):
    """Raised when a state is malformed, unresolved or physically invalid."""


class UnresolvedInitialCondition(StateError):
    """A required initial condition was not supplied.

    Raised instead of substituting a default. The paper does not state every
    initial condition, and a fabricated zero would be a claim about the culture
    that nobody made.
    """

    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__(
            "these initial conditions are unresolved and will not be defaulted: "
            f"{list(missing)}. The paper reports an initial OD600 of 0.05 but no "
            "OD600-to-dry-cell-weight calibration, no initial dissolved oxygen "
            "and no initial complex-substrate concentration as a model input, so "
            "X0, DO0 and S2_0 must be supplied explicitly."
        )
        self.missing = missing


@dataclass(frozen=True)
class State:
    """One point of a trajectory.

    **The field order is the state-vector order**, deliberately: ``from_vector``
    and ``as_vector`` are exact inverses positionally, so a derivative function
    returning a tuple in this order cannot be mis-assigned to the wrong
    variable. ``validate_state`` relies on the same order.
    """

    t: float
    X: float
    S1: float
    S2: float
    DO: float
    e1: float
    e2: float
    V: float

    def as_vector(self) -> tuple[float, ...]:
        """State vector in the fixed order the derivative functions use."""
        return (self.X, self.S1, self.S2, self.DO, self.e1, self.e2, self.V)

    @classmethod
    def from_vector(cls, t: float, vector: tuple[float, ...]) -> "State":
        if len(vector) != 7:
            raise StateError(f"a state vector has 7 components, got {len(vector)}")
        return cls(t, *vector)

    def to_dict(self) -> dict[str, Any]:
        return {
            "t_h": self.t,
            "biomass_concentration_g_per_L": self.X,
            "glycerol_concentration_g_per_L": self.S1,
            "complex_substrate_concentration_g_per_L": self.S2,
            "dissolved_oxygen_percent": self.DO,
            "enzyme_fraction_1": self.e1,
            "enzyme_fraction_2": self.e2,
            "culture_volume_L": self.V,
        }


def validate_state(state: State, *, t: float) -> None:
    """Reject a state that is not physically admissible.

    Nothing is clipped: a negative concentration is a numerical failure and is
    reported as one, because silently flooring it at zero would hide the
    integration step that produced it.
    """
    vector = state.as_vector()
    for value, name in zip(vector, ("X", "S1", "S2", "DO", "e1", "e2", "V")):
        if not math.isfinite(value):
            raise StateError(
                f"state at t={t:g} h has a non-finite {name} ({value!r}); the "
                f"integration has failed and the state is not reported as a result"
            )
    for name in NON_NEGATIVE:
        value = getattr(state, name)
        if value < 0.0:
            raise StateError(
                f"state at t={t:g} h has a negative {name} ({value!r}); "
                f"concentrations and enzyme fractions cannot be negative, and "
                f"this value is a numerical failure rather than a result"
            )
    for name in STRICTLY_POSITIVE:
        value = getattr(state, name)
        if value <= 0.0:
            raise StateError(
                f"state at t={t:g} h has {name}={value!r}; it must be strictly "
                f"positive for the balances to be defined"
            )
    if not DO_MIN <= state.DO <= DO_MAX:
        raise StateError(
            f"state at t={t:g} h has dissolved oxygen {state.DO!r} %, outside the "
            f"physical range {DO_MIN}-{DO_MAX} %"
        )


@dataclass(frozen=True)
class InitialCondition:
    """One initial value, with how it was obtained."""

    key: str
    value: float
    unit: str
    kind: QuantityKind
    provenance: Provenance
    source: SourceRef | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "symbol": STATE_FIELDS[self.key][0],
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "source": self.source.to_dict() if self.source else None,
            "note": self.note,
        }


@dataclass(frozen=True)
class InitialConditions:
    """The seven initial state values, all resolved.

    Construction refuses an unresolved or physically invalid set. `V` is stored
    in litres; a caller supplying mL must convert (or say so), because the
    dilution term F/V is a rate only when both are in the same unit.
    """

    values: Mapping[str, float]
    units: Mapping[str, str]
    provenance: Mapping[str, InitialCondition]
    mode: str

    def __post_init__(self) -> None:
        missing = [k for k in STATE_FIELDS if k not in self.values]
        if missing:
            raise UnresolvedInitialCondition(tuple(missing))
        for key, (_symbol, kind, printed) in STATE_FIELDS.items():
            unit_symbol = self.units.get(key, printed)
            require(kind, unit_symbol, what=f"initial condition {key}")
            value = float(self.values[key])
            if not math.isfinite(value):
                raise StateError(f"initial {key} is not finite ({value!r})")
            converted = convert(kind, value, unit_symbol, printed)
            self.values[key] = converted  # type: ignore[index]
            self.units[key] = printed

        if self.values["V"] <= 0.0:
            raise StateError(
                f"initial V must be strictly positive, got {self.values['V']!r} L; "
                f"the fed-batch dilution term F/V is undefined for an empty vessel"
            )
        for key in ("X", "S1", "S2", "DO", "e1", "e2"):
            if self.values[key] < 0.0:
                raise StateError(
                    f"initial {key} is negative ({self.values[key]!r}); that is not a "
                    f"physically meaningful culture"
                )
        if not DO_MIN <= self.values["DO"] <= DO_MAX:
            raise StateError(
                f"initial DO is {self.values['DO']!r} %, outside "
                f"{DO_MIN}-{DO_MAX} %"
            )
        if self.mode not in ("batch", "fed_batch"):
            raise StateError(
                f"mode must be 'batch' or 'fed_batch', got {self.mode!r}"
            )

    def initial_state(self, t: float = 0.0) -> State:
        return State(
            t=t,
            X=self.values["X"],
            S1=self.values["S1"],
            S2=self.values["S2"],
            DO=self.values["DO"],
            V=self.values["V"],
            e1=self.values["e1"],
            e2=self.values["e2"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "values": {k: self.values[k] for k in STATE_FIELDS},
            "units": {k: self.units[k] for k in STATE_FIELDS},
            "provenance": {k: self.provenance[k].to_dict() for k in STATE_FIELDS},
        }

    def provenance_summary(self) -> dict[str, str]:
        return {k: self.provenance[k].provenance.value for k in STATE_FIELDS}


def value_state_of(value: float | None) -> ValueState:
    """Map a number (or its absence) onto the composition layer's six states."""
    if value is None:
        return ValueState.UNRESOLVED
    return ValueState.ZERO if value == 0.0 else ValueState.NUMBER


def require_convertible(kind: QuantityKind, value: float, unit_symbol: str) -> float:
    """Validate a unit for a quantity and return the value in the base unit."""
    require(kind, unit_symbol, what=kind.value)
    return float(value)


__all__ = [
    "DO_MAX",
    "DO_MIN",
    "InitialCondition",
    "InitialConditions",
    "NON_NEGATIVE",
    "STATE_FIELDS",
    "STRICTLY_POSITIVE",
    "State",
    "StateError",
    "UnresolvedInitialCondition",
    "require_convertible",
    "validate_state",
    "value_state_of",
]