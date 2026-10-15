"""ScaleUp AI core: unit registry with explicit, dimension-checked conversions.

Design constraints:
  * Conversions are explicit and whitelisted. There is no generic "parse any
    string" behaviour -- an unregistered unit raises, because a silent
    dimension mismatch would corrupt a derived quantity.
  * Quantities that are dimensionless but *not* linearly convertible (pH, log
    quantities) get their own Dimension so that `convert` refuses them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Dimension(Enum):
    VOLUME = "volume"
    VOLUME_RATE = "volume_rate"
    TIME = "time"
    TEMPERATURE = "temperature"
    MASS = "mass"
    MASS_CONCENTRATION = "mass_concentration"
    MOLAR_CONCENTRATION = "molar_concentration"
    ABSORBANCE = "absorbance"
    ABSORBANCE_PER_VOLUME = "absorbance_per_volume"
    ABSORBANCE_PER_MASS = "absorbance_per_mass"
    WAVELENGTH = "wavelength"
    DIMENSIONLESS = "dimensionless"
    ACTIVITY = "activity"
    ACTIVITY_PER_VOLUME = "activity_per_volume"
    MOLAR_MASS = "molar_mass"
    CONDUCTIVITY = "conductivity"
    RELATIVE_CENTRIFUGAL_FORCE = "relative_centrifugal_force"
    PH = "ph"  # dimensionless but NOT linearly convertible
    CONCENTRATION_FACTOR = "concentration_factor"  # e.g. 30x


class UnitError(ValueError):
    """Raised for unknown units or dimensionally invalid conversions."""


@dataclass(frozen=True)
class Unit:
    symbol: str
    dimension: Dimension
    #: value_in_base = value * to_base
    to_base: float
    note: str = ""


#: Base unit chosen per dimension (to_base == 1.0).
_U = Unit


def _reg(units: tuple[Unit, ...]) -> dict[str, Unit]:
    out: dict[str, Unit] = {}
    for u in units:
        if u.symbol in out:
            raise UnitError(f"duplicate unit symbol {u.symbol!r}")
        out[u.symbol] = u
    return out


UNITS: dict[str, Unit] = _reg(
    (
        # volume -- base = mL
        _U("mL", Dimension.VOLUME, 1.0),
        _U("L", Dimension.VOLUME, 1_000.0),
        _U("dm3", Dimension.VOLUME, 1_000.0, "reported as 'dm3' in the paper"),
        _U("cm3", Dimension.VOLUME, 1.0, "reported as 'cm3' in the paper"),
        _U("uL", Dimension.VOLUME, 0.001),
        # volume rate -- base = mL/min
        _U("mL/min", Dimension.VOLUME_RATE, 1.0),
        _U("mL/h", Dimension.VOLUME_RATE, 1.0 / 60.0),
        # time -- base = h
        _U("h", Dimension.TIME, 1.0),
        _U("min", Dimension.TIME, 1.0 / 60.0),
        _U("s", Dimension.TIME, 1.0 / 3600.0),
        _U("d", Dimension.TIME, 24.0, "day, for storage durations"),
        # temperature -- base = degC (affine offsets deliberately not applied)
        _U("degC", Dimension.TEMPERATURE, 1.0),
        _U("K", Dimension.TEMPERATURE, 1.0, "treated numerically equal to degC; no offset applied"),
        # mass -- base = g
        _U("g", Dimension.MASS, 1.0),
        _U("mg", Dimension.MASS, 0.001),
        _U("ug", Dimension.MASS, 1e-6),
        # mass concentration -- base = g/L
        _U("g/L", Dimension.MASS_CONCENTRATION, 1.0),
        _U("mg/mL", Dimension.MASS_CONCENTRATION, 1.0),
        _U("mg/dL", Dimension.MASS_CONCENTRATION, 0.01, "as reported in the paper"),
        _U("g/dL", Dimension.MASS_CONCENTRATION, 10.0),
        _U("mg/L", Dimension.MASS_CONCENTRATION, 0.001),
        _U("ug/mL", Dimension.MASS_CONCENTRATION, 0.001),
        _U("%", Dimension.DIMENSIONLESS, 0.01, "generic percent (fraction * 100)"),
        _U("g_per_100mL", Dimension.MASS_CONCENTRATION, 10.0, "w/v percent"),
        # molar concentration -- base = mol/L
        _U("M", Dimension.MOLAR_CONCENTRATION, 1.0),
        _U("mM", Dimension.MOLAR_CONCENTRATION, 1e-3),
        _U("uM", Dimension.MOLAR_CONCENTRATION, 1e-6),
        # absorbance -- base = AU (1 cm equivalent, path length NOT stated in paper)
        _U("AU", Dimension.ABSORBANCE, 1.0),
        _U("AU/mL", Dimension.ABSORBANCE_PER_VOLUME, 1.0),
        _U("AU/uL", Dimension.ABSORBANCE_PER_VOLUME, 1000.0),
        _U("g/AU", Dimension.ABSORBANCE_PER_MASS, 1.0,
           "declared dimension of the AU->mass factor; NOT supplied by the paper"),
        _U("nm", Dimension.WAVELENGTH, 1.0, "detection wavelength"),
        # dimensionless
        _U("OD600", Dimension.DIMENSIONLESS, 1.0, "optical density at 600 nm"),
        _U("g_per_L_per_OD600", Dimension.DIMENSIONLESS, 1.0,
           "grams per litre of culture per unit OD600; a descriptive ratio, not convertible"),
        _U("1", Dimension.DIMENSIONLESS, 1.0),
        _U("fold", Dimension.CONCENTRATION_FACTOR, 1.0),
        _U("mS", Dimension.CONDUCTIVITY, 1.0),
        _U("xg", Dimension.RELATIVE_CENTRIFUGAL_FORCE, 1.0),
        # activity
        _U("IU", Dimension.ACTIVITY, 1.0),
        _U("IU/L", Dimension.ACTIVITY_PER_VOLUME, 1.0),
        # molar mass
        _U("Da", Dimension.MOLAR_MASS, 1.0),
        # non-linearly-convertible
        _U("pH", Dimension.PH, 1.0, "log10 of H+ activity; never linearly convertible"),
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
    """True only for a registered, same-dimension, linearly-convertible pair."""
    if src not in UNITS or dst not in UNITS:
        return False
    s, d = UNITS[src], UNITS[dst]
    return s.dimension == d.dimension and s.dimension is not Dimension.PH


def convert(value: float, src: str, dst: str) -> float:
    """Convert `value` from `src` to `dst`. Raises on any invalid conversion."""
    s, d = unit(src), unit(dst)
    if s.dimension is not d.dimension:
        raise UnitError(
            f"cannot convert {src!r} ({s.dimension.value}) to {dst!r} "
            f"({d.dimension.value}): dimension mismatch"
        )
    if s.dimension is Dimension.PH:
        raise UnitError("pH is logarithmically scaled and is never linearly convertible")
    if s.dimension is Dimension.TEMPERATURE and src != dst:
        # Kelvin offsets would have to be applied; refuse rather than guess.
        if (src, dst) == ("K", "degC"):
            return value - 273.15
        if (src, dst) == ("degC", "K"):
            return value + 273.15
    return (value * s.to_base) / d.to_base


def normalize(value: float, src: str, dst: str) -> float | None:
    """Like `convert` but returns None when the conversion is not possible.

    Used by the reporting layer so a non-convertible pair surfaces as
    'original unit retained' rather than an exception during serialization.
    """
    try:
        return convert(value, src, dst)
    except UnitError:
        return None