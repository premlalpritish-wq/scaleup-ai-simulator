"""Unit registry for the quantities Nanchen et al. (2006) actually print.

An explicit whitelist, a dimension per unit, and conversion only between two
registered units of the same dimension. An unregistered symbol raises.

Two of these carry the paper's own unit caveat and say so:

  * the paper prints the maintenance coefficient as ``mmol gdw-1 h-1``
    (Table 1) and the maximal molar growth yield as ``gdw mol-1`` (Table 1),
    so Pirt's printed relation ``qglc = mu/Yglc_max + mglc`` mixes a mol and a
    mmol term. They are separate dimensions here, and the model states the
    factor of 1000 it has to apply (see ``model.MOL_PER_MMOL``);
  * ``gdw`` (gram dry weight) is not a unit of its own. It is the biomass mass
    basis, so the model keeps ``g`` and records the printed string.
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
    """Reciprocal hours: the specific growth rate, which in a steady-state
    chemostat equals the dilution rate. The paper prints both as ``h-1``."""
    AMOUNT_PER_MASS_TIME = "amount_per_mass_time"
    """``mmol gdw-1 h-1``: the maintenance coefficient mglc."""
    MASS_PER_AMOUNT = "mass_per_amount"
    """``gdw mol-1``: the maximal molar growth yield Yglc_max."""
    MASS_PER_OD = "mass_per_od"
    """``g dw per OD600``: the correlation factor the paper prints (0.41)."""
    PERCENT = "percent"
    """Dissolved-oxygen concentration, printed as ``%`` of air saturation."""


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
        _U("mL/min", Dimension.VOLUME_RATE, 0.06),
        _U("g", Dimension.MASS, 1.0),
        _U("g/L", Dimension.MASS_CONCENTRATION, 1.0),
        _U("g/L glucose", Dimension.MASS_CONCENTRATION, 1.0,
           "the limiting substrate is printed in g per liter"),
        _U("1/h", Dimension.PER_HOUR, 1.0, "growth rate = dilution rate, as printed"),
        _U("mmol/(gdw h)", Dimension.AMOUNT_PER_MASS_TIME, 1.0,
           "printed as 'mmol gdw-1 h-1'"),
        _U("gdw/mol", Dimension.MASS_PER_AMOUNT, 1.0,
           "printed as 'gdw mol-1'"),
        _U("g/OD", Dimension.MASS_PER_OD, 1.0,
           "printed as 'g [dry weight] [gdw]/OD'"),
        _U("%", Dimension.PERCENT, 1.0, "dissolved-oxygen concentration"),
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
