"""Building initial conditions with honest provenance.

Constructing :class:`InitialConditions` by hand is possible and is what the
tests do, but a caller should not have to know which of the seven values the
paper reports and which it does not. This module knows.

The split it encodes, which is the whole point of the exercise:

===========================  ============  ==================================
initial condition            paper gives   provenance recorded
===========================  ============  ==================================
``S1_0`` = 2.76 g/L          yes           ``reported`` (p. 2)
``V0``  = 0.1 L              yes           ``reported`` (100 mL, p. 2)
``e1_0`` = 0.082             yes           ``reported`` (Table 2 parameter)
``e2_0`` = 0.874             yes           ``reported`` (Table 2 parameter)
``X0``                       **no**        ``assumed`` -- caller supplies
``DO0``                      **no**        ``assumed`` -- caller supplies
``S2_0``                     **no**        ``assumed`` -- caller supplies
===========================  ============  ==================================

The paper prints an initial OD600 of 0.05 and no OD600-to-dry-cell-weight
calibration, so ``X0`` cannot be derived from it. There is no default here and
there is no conversion from OD600 to g/L: supplying one would be inventing the
calibration the paper does not contain.

The builder therefore *requires* the three unresolved values. That is a
deliberate inconvenience, and :func:`build_initial_conditions` will not
substitute anything for them.
"""

from __future__ import annotations

from typing import Mapping

from schemas.parameters import ParameterSet, table2_parameter_set
from schemas.provenance import Provenance, SourceRef
from schemas.state import STATE_FIELDS, InitialCondition, InitialConditions
from schemas.units import QuantityKind

#: Values the paper states, and where.
_REPORTED = {
    "S1": (
        2.76,
        "g/L",
        QuantityKind.MASS_CONCENTRATION,
        SourceRef(
            section="2.2 Batch fermentation",
            locator="text, p. 2",
            printed_page=2,
            quote="The initial production medium was supplemented with 2.76 g/L glycerol",
        ),
        "initial glycerol of the production medium",
    ),
    "V": (
        0.1,
        "L",
        QuantityKind.VOLUME,
        SourceRef(
            section="2.3 Fed-batch fermentation in shake flask",
            locator="text, p. 2",
            printed_page=2,
            quote="These flasks were filled with 100 mL medium",
        ),
        "100 mL = 0.1 L in the 500 mL baffled flask",
    ),
}

#: Values the paper does not state; the caller must supply each one.
REQUIRED_BY_CALLER = ("X", "S2", "DO")


class MissingInitialCondition(ValueError):
    """The caller did not supply an initial condition the paper does not give."""

    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__(
            f"these initial conditions are not stated in the paper and were not "
            f"supplied: {list(missing)}. X is not derivable from the reported "
            f"initial OD600 of 0.05 because the paper prints no OD600-to-dry-cell-"
            f"weight calibration. Supply a value, or do not run."
        )
        self.missing = missing


def build_initial_conditions(
    *,
    X: float,
    S2: float,
    DO: float,
    mode: str,
    S1: float | None = None,
    V: float | None = None,
    parameters: ParameterSet | None = None,
    units: Mapping[str, str] | None = None,
    note: str = "",
) -> InitialConditions:
    """Assemble resolved initial conditions, refusing anything unresolved.

    ``X``, ``S2`` and ``DO`` are required: the paper does not state them.
    ``S1``, ``V`` and the two enzyme fractions default to the printed values and
    can be overridden for a what-if run.
    """
    parameters = parameters or table2_parameter_set()
    supplied_units = dict(units or {})

    # Bound up front: `locals()` inside a comprehension refers to the
    # comprehension's own scope, not this function's.
    caller_values = {"X": X, "S2": S2, "DO": DO}
    reported_overrides = {"S1": S1, "V": V}

    missing = tuple(
        name for name, value in caller_values.items() if value is None
    )
    if missing:
        raise MissingInitialCondition(missing)

    values: dict[str, float] = {}
    unit_symbols: dict[str, str] = {}
    provenance: dict[str, InitialCondition] = {}

    for key, (default, default_unit, kind, source, why) in _REPORTED.items():
        given = reported_overrides.get(key)
        values[key] = float(default if given is None else given)
        unit_symbols[key] = supplied_units.get(key, default_unit)
        provenance[key] = InitialCondition(
            key=key,
            value=values[key],
            unit=unit_symbols[key],
            kind=kind,
            provenance=Provenance.REPORTED,
            source=source,
            note=why if given is None else f"overridden by the caller; paper prints {default!r}",
        )

    caller_kind = {
        "X": QuantityKind.MASS_CONCENTRATION,
        "S2": QuantityKind.MASS_CONCENTRATION,
        "DO": QuantityKind.DISSOLVED_OXYGEN_PERCENT,
    }
    for key, value in caller_values.items():
        values[key] = float(value)
        unit_symbols[key] = supplied_units.get(key, STATE_FIELDS[key][2])
        provenance[key] = InitialCondition(
            key=key,
            value=values[key],
            unit=unit_symbols[key],
            kind=caller_kind[key],
            provenance=Provenance.ASSUMED,
            source=None,
            note=note or "supplied by the caller; not stated in the paper",
        )

    for key, symbol in (("e1", "e_ratio1_0"), ("e2", "e_ratio2_0")):
        value = parameters.value(symbol)
        values[key] = float(value)
        unit_symbols[key] = "1"
        parameter = parameters.parameter(symbol)
        provenance[key] = InitialCondition(
            key=key,
            value=value,
            unit="1",
            kind=QuantityKind.ENZYME_RATIO,
            provenance=Provenance.REPORTED,
            source=parameter.source,
            note=(
                "initial enzyme fraction e_k/e_mk, taken from the Table 2 "
                "parameter and used as the state of eq. (7)"
            ),
        )

    return InitialConditions(
        values=values, units=unit_symbols, provenance=provenance, mode=mode
    )