"""Unit registry for the quantities Simensen et al. (2022) actually print.

An explicit whitelist, a dimension per unit, and conversion only between two
registered units of the same dimension. An unregistered symbol raises.

The measurement the dataset is built on is a **mass fraction of cell dry weight**,
printed as ``g gCDW-1``. ``gCDW`` is not a unit of its own: it is the biomass
basis, so the model keeps ``g/g`` and records the printed string, rather than
inventing a ``g/gCDW`` unit that would look like a distinct measurable quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Dimension(Enum):
    MASS_FRACTION = "mass_fraction"
    MASS_CONCENTRATION = "mass_concentration"
    AMOUNT_CONCENTRATION = "amount_concentration"
    MASS = "mass"
    VOLUME = "volume"
    TIME = "time"
    TEMPERATURE = "temperature"
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
        _U("g/g", Dimension.MASS_FRACTION, 1.0, "printed as 'g gCDW-1'"),
        _U("g/L", Dimension.MASS_CONCENTRATION, 1.0),
        _U("mM", Dimension.AMOUNT_CONCENTRATION, 1.0),
        _U("g", Dimension.MASS, 1.0),
        _U("L", Dimension.VOLUME, 1.0),
        _U("mL", Dimension.VOLUME, 1.0e-3),
        _U("h", Dimension.TIME, 1.0),
        _U("min", Dimension.TIME, 1.0 / 60.0),
        _U("s", Dimension.TIME, 1.0 / 3600.0),
        _U("degC", Dimension.TEMPERATURE, 1.0),
        _U("%", Dimension.PERCENT, 1.0,
           "used for both '% (w/v)' and '% (v/v)' as the paper prints them"),
    )
)


def unit(symbol: str) -> Unit:
    try:
        return UNITS[symbol]
    except KeyError:
        raise UnitError(
            f"unknown unit {symbol!r}; known units: {sorted(UNITS)}"
        ) from None


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
