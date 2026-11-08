"""Unit registry for the quantities Lin et al. (2001) actually print.

An explicit whitelist of units, a dimension per unit, and conversion only
between two registered units of the same dimension. An unregistered symbol
raises. There is no "parse any string" path, because a silently accepted unit
is a silently wrong number.

**Base unit per dimension is the unit the paper prints**, so an arithmetic
result is in the printed unit with no hidden factor:

    time                     h            (p. 348: F in L h-1)
    volume                   L            (p. 348 jargon; Table I V0 in L)
    volume rate              L/h          (p. 348 nomenclature: F [L h-1])
    mass                     g
    mass concentration       g/L          (Table I: S0, X0, Si)
    per hour                 1/h          (nomenclature: mu [h-1]; kLa [h-1])
    mass specific rate       g/(g h)      (Table I: qSmax, qOmax, qm)
    amount specific rate     mmol/(g h)   (abstract: 0.6 and 5 mmol g-1 h-1)
    mass ratio               g/g          (Table I: YX/S,ox, YO/S)
    carbon content           mol C/g      (Table I: CS, CA, CX)
    percent                  %            (nomenclature: DOT [%])

Three of these are deliberately *not* interchangeable, and the registry says so:

  * ``g/(g h)`` and ``mmol/(g h)`` both measure a specific uptake capacity, but
    the paper reports capacities in both units (Table I in g g-1 h-1, the
    abstract in mmol g-1 h-1) and prints no molar mass that would convert one to
    the other. They are separate dimensions, and the package never converts.
  * ``1/h`` (mu, kLa) and ``g/(g h)`` are algebraically related through a
    biomass concentration, which the paper does not supply for these cells, so
    they are separate dimensions too.
  * the dry-weight basis of a biomass concentration is not a unit. Where the
    paper prints "g cell dry weight per L" the model keeps ``g/L``, rather than
    inventing a ``g/L (DW)`` unit that would look like a distinct quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Dimension(Enum):
    TIME = "time"
    VOLUME = "volume"
    VOLUME_RATE = "volume_rate"
    MASS = "mass"
    MASS_CONCENTRATION = "mass_concentration"
    PER_HOUR = "per_hour"
    """A rate in reciprocal hours: the specific growth rate mu and the
    volumetric oxygen transfer coefficient kLa are both printed in 1/h."""
    MASS_SPECIFIC_RATE = "mass_specific_rate"
    """Per unit biomass mass per unit time: Table I's qSmax, qOmax, qm, qAc,max."""
    AMOUNT_SPECIFIC_RATE = "amount_specific_rate"
    """Per unit biomass mass per unit time, in moles: the abstract's capacities."""
    MASS_RATIO = "mass_ratio"
    CARBON_CONTENT = "carbon_content"
    PERCENT = "percent"


class UnitError(ValueError):
    """Raised for an unknown unit, or a conversion between unlike dimensions."""


@dataclass(frozen=True)
class Unit:
    symbol: str
    dimension: Dimension
    #: value_in_base = value * to_base
    to_base: float
    note: str = ""


_U = Unit


def _reg(units: tuple[Unit, ...]) -> dict[str, Unit]:
    out: dict[str, Unit] = {}
    for unit in units:
        if unit.symbol in out:
            raise UnitError(f"duplicate unit symbol {unit.symbol!r}")
        out[unit.symbol] = unit
    return out


UNITS: dict[str, Unit] = _reg(
    (
        _U("h", Dimension.TIME, 1.0),
        _U("min", Dimension.TIME, 1.0 / 60.0),
        _U("L", Dimension.VOLUME, 1.0),
        _U("mL", Dimension.VOLUME, 1.0e-3),
        _U("L/h", Dimension.VOLUME_RATE, 1.0),
        _U("mL/h", Dimension.VOLUME_RATE, 1.0e-3),
        _U("g", Dimension.MASS, 1.0),
        _U("g/L", Dimension.MASS_CONCENTRATION, 1.0),
        _U("mg/L", Dimension.MASS_CONCENTRATION, 1.0e-3),
        _U("1/h", Dimension.PER_HOUR, 1.0, "mu and kLa, as the nomenclature prints"),
        _U("g/(g h)", Dimension.MASS_SPECIFIC_RATE, 1.0,
           "Table I prints this as 'g g-1 h-1'"),
        _U("mmol/(g h)", Dimension.AMOUNT_SPECIFIC_RATE, 1.0,
           "abstract prints this as 'mmol g-1 h-1'"),
        _U("g/g", Dimension.MASS_RATIO, 1.0),
        _U("mol C/g", Dimension.CARBON_CONTENT, 1.0,
           "Table I prints this as 'mol C g-1'"),
        _U("%", Dimension.PERCENT, 1.0, "dissolved oxygen tension, as printed"),
    )
)


def unit(symbol: str) -> Unit:
    try:
        return UNITS[symbol]
    except KeyError:
        raise UnitError(f"unknown unit {symbol!r}; known units: {sorted(UNITS)}") from None


def dimension_of(symbol: str) -> Dimension:
    return unit(symbol).dimension


def is_convertible(src: str, dst: str) -> bool:
    """True only for a registered, same-dimension pair."""
    if src not in UNITS or dst not in UNITS:
        return False
    return UNITS[src].dimension is UNITS[dst].dimension


def convert(value: float, src: str, dst: str) -> float:
    """Convert `value` from `src` to `dst`. Raises on any invalid conversion."""
    s, d = unit(src), unit(dst)
    if s.dimension is not d.dimension:
        raise UnitError(
            f"cannot convert {src!r} ({s.dimension.value}) to {dst!r} "
            f"({d.dimension.value}): dimension mismatch"
        )
    return (value * s.to_base) / d.to_base


def require_dimension(symbol: str, expected: Dimension, *, what: str) -> str:
    """Check that `symbol` is registered and has `expected` dimension."""
    found = dimension_of(symbol)
    if found is not expected:
        raise UnitError(
            f"{what}: dimension mismatch. {symbol!r} has dimension "
            f"{found.value!r}, which is not {expected.value!r}"
        )
    return symbol
