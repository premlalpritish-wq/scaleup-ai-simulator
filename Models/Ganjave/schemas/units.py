"""Quantities and units for the Ganjave et al. (2022) growth model.

**A unit symbol alone is not a quantity.** This model needs `g/L` for three
different things (a culture concentration, a half-saturation constant, and the
saturation concentration `C*`), `%` for two (the half-saturation `Ko,k` and the
dissolved oxygen reading itself), and `1/h` for two (the specific growth rate
and the transfer coefficient `kLa`). A flat registry cannot hold those, and a
flat conversion table would let `Ko,1 = 0.326 g/L` be accepted for a
percentage.

So units are keyed by the **pair** (quantity, symbol), exactly as the
composition layer's bridge is (`composition/composition/quantities.py`). A
conversion is possible only between two symbols of the same quantity, and
:meth:`QuantityKind.base_unit` names the unit the paper prints.

Three semantics are load-bearing here:

**Dissolved oxygen is a percentage of the saturation reading**, not a mass
fraction. Eq. (3)-(4) limit growth with ``DO/(Ko,k + DO)`` and eq. (11)/(15)
integrate ``d(DO)/dt`` in ``%/h``. Converting to a dissolved-oxygen
*concentration* needs the reported saturation concentration `C*`
(0.0075 g/L); that conversion is explicit and tested
(:func:`do_percentage_to_concentration`) and is never applied implicitly.

**The complex substrate is lumped.** `S2` is "several amino acids and
peptides" (p. 4), represented experimentally by yeast extract. It is one
modelled concentration in g/L and is not a nitrogen mass fraction.

**Feed recipes are printed as percent weight/volume** ("17.5% glycerol, 24.5%
yeast extract", Table 1) while eq. (13)/(14) need g/L. The conversion is 1 % w/v
= 10 g/L and is explicit: :func:`percent_wv_to_g_per_l`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QuantityKind(Enum):
    """What a number *is*, independent of the symbol it is printed in.

    These are the model's own semantics. `models.composition` maps each one to
    a composition-layer `Quantity` value and refuses the mappings that would be
    numerically convenient but physically wrong.
    """

    TIME = "time"
    VOLUME = "volume"
    VOLUME_FLOW = "volume_flow"
    MASS_CONCENTRATION = "mass_concentration"
    SPECIFIC_GROWTH_RATE = "specific_growth_rate"
    HALF_SATURATION_CONCENTRATION = "half_saturation_concentration"
    HALF_SATURATION_DO = "half_saturation_dissolved_oxygen"
    YIELD = "yield"
    ENZYME_RATIO = "enzyme_ratio"
    OXYGEN_TRANSFER_COEFFICIENT = "oxygen_transfer_coefficient"
    OXYGEN_SATURATION_CONCENTRATION = "oxygen_saturation_concentration"
    DISSOLVED_OXYGEN_PERCENT = "dissolved_oxygen_percent"
    FEED_PERCENT_WV = "feed_percent_weight_volume"
    OPTICAL_DENSITY = "optical_density"
    FOLD = "fold"


class UnitError(ValueError):
    """Raised for an unknown unit, or a conversion between unlike quantities."""


@dataclass(frozen=True)
class Unit:
    symbol: str
    kind: QuantityKind
    #: value_in_base = value * to_base
    to_base: float
    note: str = ""


_U = Unit

#: symbol -> Unit, per quantity. Keyed by (kind, symbol) by construction.
_REGISTRY: dict[QuantityKind, dict[str, Unit]] = {
    QuantityKind.TIME: dict(
        (u.symbol, u)
        for u in (
            _U("h", QuantityKind.TIME, 1.0, "the paper's time basis"),
            _U("min", QuantityKind.TIME, 1.0 / 60.0),
            _U("s", QuantityKind.TIME, 1.0 / 3600.0),
        )
    ),
    QuantityKind.VOLUME: dict(
        (u.symbol, u)
        for u in (
            _U("L", QuantityKind.VOLUME, 1.0),
            _U("mL", QuantityKind.VOLUME, 1.0e-3, "the flask is filled with 100 mL"),
        )
    ),
    QuantityKind.VOLUME_FLOW: dict(
        (u.symbol, u)
        for u in (
            _U("L/h", QuantityKind.VOLUME_FLOW, 1.0),
            _U("mL/h", QuantityKind.VOLUME_FLOW, 1.0e-3,
               "Table 1 reports the feed rate in mL/h"),
        )
    ),
    QuantityKind.MASS_CONCENTRATION: dict(
        (u.symbol, u)
        for u in (
            _U("g/L", QuantityKind.MASS_CONCENTRATION, 1.0,
               "X, S1 and S2 are reported in g/L"),
            _U("mg/L", QuantityKind.MASS_CONCENTRATION, 1.0e-3),
        )
    ),
    QuantityKind.SPECIFIC_GROWTH_RATE: dict(
        (u.symbol, u)
        for u in (_U("1/h", QuantityKind.SPECIFIC_GROWTH_RATE, 1.0,
                     "mum1 and mum2 are reported in h^-1"),)
    ),
    QuantityKind.HALF_SATURATION_CONCENTRATION: dict(
        (u.symbol, u)
        for u in (_U("g/L", QuantityKind.HALF_SATURATION_CONCENTRATION, 1.0,
                     "K11, K12, K22"),)
    ),
    QuantityKind.HALF_SATURATION_DO: dict(
        (u.symbol, u)
        for u in (_U("%", QuantityKind.HALF_SATURATION_DO, 1.0,
                     "Ko,1 and Ko,2 are percentages of dissolved oxygen"),)
    ),
    QuantityKind.YIELD: dict(
        (u.symbol, u)
        for u in (_U("g/g", QuantityKind.YIELD, 1.0,
                     "grams of biomass per gram of substrate or oxygen"),)
    ),
    QuantityKind.ENZYME_RATIO: dict(
        (u.symbol, u)
        for u in (_U("1", QuantityKind.ENZYME_RATIO, 1.0,
                     "the normalised enzyme fraction e_k/e_mk"),)
    ),
    QuantityKind.OXYGEN_TRANSFER_COEFFICIENT: dict(
        (u.symbol, u)
        for u in (_U("1/h", QuantityKind.OXYGEN_TRANSFER_COEFFICIENT, 1.0,
                     "kLa = 133 h^-1 for the 500 mL baffled flask at 200 rpm"),)
    ),
    QuantityKind.OXYGEN_SATURATION_CONCENTRATION: dict(
        (u.symbol, u)
        for u in (_U("g/L", QuantityKind.OXYGEN_SATURATION_CONCENTRATION, 1.0,
                     "C* = 0.0075 g/L, maximum oxygen solubility"),)
    ),
    QuantityKind.DISSOLVED_OXYGEN_PERCENT: dict(
        (u.symbol, u)
        for u in (_U("%", QuantityKind.DISSOLVED_OXYGEN_PERCENT, 1.0,
                     "percentage of the saturation reading; NOT a mass fraction"),)
    ),
    QuantityKind.FEED_PERCENT_WV: dict(
        (u.symbol, u)
        for u in (_U("% w/v", QuantityKind.FEED_PERCENT_WV, 1.0,
                     "feed recipe as printed in Table 1; 1 % w/v = 10 g/L"),)
    ),
    QuantityKind.OPTICAL_DENSITY: dict(
        (u.symbol, u)
        for u in (_U("OD600", QuantityKind.OPTICAL_DENSITY, 1.0,
                     "the paper reports no OD600-to-DCW calibration"),)
    ),
    QuantityKind.FOLD: dict(
        (u.symbol, u)
        for u in (_U("fold", QuantityKind.FOLD, 1.0),)
    ),
}

UNITS: dict[tuple[QuantityKind, str], Unit] = {
    (kind, symbol): unit for kind, table in _REGISTRY.items() for symbol, unit in table.items()
}


def base_unit(kind: QuantityKind) -> str:
    """The symbol the paper prints for this quantity."""
    table = _REGISTRY[kind]
    if not table:  # pragma: no cover - every kind above has entries
        raise UnitError(f"no unit registered for {kind.value}")
    return next(iter(table))


def unit(kind: QuantityKind, symbol: str) -> Unit:
    try:
        return _REGISTRY[kind][symbol]
    except KeyError:
        raise UnitError(
            f"{symbol!r} is not registered for {kind.value}; "
            f"registered there: {sorted(_REGISTRY[kind])}"
        ) from None


def symbols_for(kind: QuantityKind) -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY[kind]))


def is_convertible(kind: QuantityKind, src: str, dst: str) -> bool:
    return src in _REGISTRY.get(kind, {}) and dst in _REGISTRY.get(kind, {})


def convert(kind: QuantityKind, value: float, src: str, dst: str) -> float:
    """Convert within one quantity. Raises when the symbols do not fit."""
    s, d = unit(kind, src), unit(kind, dst)
    return (value * s.to_base) / d.to_base


def require(kind: QuantityKind, symbol: str, *, what: str) -> str:
    """Check a symbol is registered for this quantity and return it."""
    unit(kind, symbol)
    return symbol


def percent_wv_to_g_per_l(percent: float) -> float:
    """Feed-recipe percent weight/volume to g/L, as eq. (13)/(14) require.

    1 % w/v is 1 g per 100 mL, i.e. 10 g/L. Applied explicitly at the API
    boundary, never inside the balances.
    """
    return percent * 10.0


def g_per_l_to_percent_wv(value: float) -> float:
    """Inverse of :func:`percent_wv_to_g_per_l`."""
    return value / 10.0


def do_percentage_to_concentration(do_percent: float, c_star_g_per_l: float) -> float:
    """Dissolved-oxygen percentage to g/L, using the reported C*.

    A percentage of the saturation reading is not a mass fraction; this
    conversion needs C* and is therefore explicit and never applied implicitly.
    """
    if c_star_g_per_l <= 0.0:
        raise UnitError(
            "C* must be strictly positive to convert a dissolved-oxygen "
            f"percentage to a concentration, got {c_star_g_per_l!r} g/L"
        )
    return do_percent / 100.0 * c_star_g_per_l


def do_concentration_to_percentage(conc_g_per_l: float, c_star_g_per_l: float) -> float:
    """Inverse of :func:`do_percentage_to_concentration`."""
    if c_star_g_per_l <= 0.0:
        raise UnitError(
            "C* must be strictly positive to convert a dissolved-oxygen "
            f"concentration to a percentage, got {c_star_g_per_l!r} g/L"
        )
    return conc_g_per_l / c_star_g_per_l * 100.0