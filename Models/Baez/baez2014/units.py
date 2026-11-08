"""Unit registry for the quantities Baez et al. (2014) actually print.

The design is the repository's existing one, restated for this paper: an
explicit whitelist of units, a dimension per unit, and conversion only between
two registered units of the same dimension. An unregistered symbol raises.
There is no "parse any string" path, because a silently accepted unit is a
silently wrong number.

**Base unit per dimension is the unit the paper prints.** Every equation input
is declared in the paper's own unit and converted into it, so an arithmetic
result is in the printed unit with no hidden factor:

    time                     h          (p. 6)
    volume                   L          (p. 6, feed rate in L/h)
    volume rate              L/h        (p. 6: "F(t) = feed rate (L/h)")
    mass concentration       g/L        (p. 6: XF, SF)
    mass                     g, mg      (p. 3: 494 mg/L)
    specific rate            1/h        (p. 6: "0.35 1/h"; p. 2: "1.08/h")
                          g/(g h)      (p. 6: "0.12 g/g h", as printed)
    biomass yield            g/g        (p. 6: "1.28 g/g")
    fluorescence             FU         (p. 3: "109000 FU")

`1/h` and `g/(g h)` are two spellings of **one** dimension, and they have to
be: the printed expression adds `mu_set/Y_XS` to `m`, and
`(1/h)/(g/g)` and `g/(g h)` are both a specific rate. Registering them as
unlike dimensions would forbid the paper's own equation. Both spellings are
kept so that each parameter is displayed in the unit the paper prints.

Two of these are deliberately *not* convertible, and the registry says so:

  * `FU` is its own dimension. The paper prints a fluorescence reading and a
    separate GFP mass reading; it states no relation between them for these
    cultures. See `equations.MISSING_MODELS`.
  * the dry-weight basis of a biomass concentration is not a unit. The paper
    prints "29.1 g/L (DW)"; the model keeps `g/L` and keeps the printed
    string, rather than inventing a `g/L (DW)` unit that would look like a
    distinct measurable quantity.
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
    SPECIFIC_RATE = "specific_rate"
    """A per-unit-biomass rate per unit time. `mu_set` (1/h) and the
    maintenance coefficient m (g/(g h)) are the same dimension, because the
    printed expression adds them."""
    MASS_RATIO = "mass_ratio"
    FLUORESCENCE = "fluorescence"


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
        # time -- base = h
        _U("h", Dimension.TIME, 1.0),
        _U("min", Dimension.TIME, 1.0 / 60.0),
        # volume -- base = L
        _U("L", Dimension.VOLUME, 1.0),
        _U("mL", Dimension.VOLUME, 1.0e-3),
        # volume rate -- base = L/h
        _U("L/h", Dimension.VOLUME_RATE, 1.0),
        _U("mL/h", Dimension.VOLUME_RATE, 1.0e-3),
        _U("mL/min", Dimension.VOLUME_RATE, 1.0 / 60.0),
        # mass -- base = g
        _U("g", Dimension.MASS, 1.0),
        _U("mg", Dimension.MASS, 1.0e-3),
        # mass concentration -- base = g/L
        _U("g/L", Dimension.MASS_CONCENTRATION, 1.0),
        _U("mg/L", Dimension.MASS_CONCENTRATION, 1.0e-3),
        # specific rate -- base = 1/h. Two printed spellings, one dimension:
        # the printed expression adds mu_set/Y_XS to m.
        _U("1/h", Dimension.SPECIFIC_RATE, 1.0, "specific growth rate"),
        _U("1/min", Dimension.SPECIFIC_RATE, 60.0),
        _U("g/(g h)", Dimension.SPECIFIC_RATE, 1.0,
           "maintenance coefficient, printed on p. 6 as '0.12 g/g h'; retained as printed"),
        # biomass yield on substrate -- base = g/g
        _U("g/g", Dimension.MASS_RATIO, 1.0),
        # fluorescence -- base = FU, and not convertible to mass
        _U("FU", Dimension.FLUORESCENCE, 1.0,
           "instrument reading; the paper prints no conversion to GFP mass"),
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


def require_dimension(symbol: str, expected: Dimension, *, what: str) -> str:
    """Check that `symbol` is registered and has `expected` dimension."""
    found = dimension_of(symbol)
    if found is not expected:
        raise UnitError(
            f"{what}: dimension mismatch. {symbol!r} has dimension "
            f"{found.value!r}, which is not {expected.value!r}"
        )
    return symbol