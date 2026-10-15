"""Quantity taxonomy and the unit bridge that the composition layer owns.

Neither existing model can convert the other's units, for two independent
reasons found during the audit:

* the two registries barely overlap -- Morris has no volume, time, absorbance or
  activity dimension; Zielinski has no mass-flow, amount or amount-flow kind
  (see ``COMPOSITION_AUDIT.md`` section 3);
* where they do overlap the **base units differ** (mass is ``kg`` in Morris and
  ``g`` in Zielinski), so even a legal within-quantity conversion has to be
  declared somewhere.  This module is that somewhere.

Two rules govern everything below.

**A unit symbol alone is not a quantity.**  The symbol ``%`` is registered in
both models and means *mass fraction* in Morris and *generic percent* in
Zielinski.  ``1`` is a mass fraction in Morris and a dimensionless value in
Zielinski.  A connection is therefore legal only when the *quantities* match;
the symbol is never allowed to decide.  Units are keyed by the pair
``(quantity, symbol)`` so that both interpretations remain addressable and
neither can be reached by accident.

**A conversion never changes what a number is.**  ``kg`` -> ``g`` is a mass
conversion.  ``kg`` -> ``kg/h`` is not a conversion at all; it needs a duration
and would change the quantity from an inventory to a rate.  :func:`convert`
raises :class:`QuantityMismatch` rather than looking for a duration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

CONTRACT_VERSION = "0.1.0"
"""Version of the composition contracts this module implements."""


class QuantityError(ValueError):
    """Base class for every failure in the quantity bridge."""


class UnknownUnitError(QuantityError):
    """A symbol is not registered for the quantity it was offered with."""


class QuantityMismatch(QuantityError):
    """Two ports carry different physical quantities."""


class NonConvertibleUnitError(QuantityError):
    """Same quantity, but no linear conversion exists (pH, OD600, AU, ...)."""


# --------------------------------------------------------------------------- #
# physical quantities
# --------------------------------------------------------------------------- #


class Quantity(Enum):
    """What a number *is*, independent of the unit it happens to be printed in.

    A quantity is the compatibility key of the whole composition layer.  Two
    ports may be connected only when this matches exactly.

    The first five are Morris's ``QuantityKind`` verbatim.  The remainder exist
    because Zielinski declares values in them and those values have to be
    representable in order to be *reported as unconnectable* rather than
    silently coerced into something they are not.
    """

    # -- shared (both models) ------------------------------------------------
    MASS = "mass"
    MASS_FLOW = "mass_flow"
    MASS_FRACTION = "mass_fraction"

    # -- Morris only ---------------------------------------------------------
    AMOUNT = "amount"
    AMOUNT_FLOW = "amount_flow"

    # -- Zielinski only ------------------------------------------------------
    VOLUME = "volume"
    VOLUME_FLOW = "volume_flow"
    TIME = "time"
    TEMPERATURE = "temperature"
    MOLAR_CONCENTRATION = "molar_concentration"
    MASS_CONCENTRATION = "mass_concentration"
    ABSORBANCE = "absorbance"
    ABSORBANCE_PER_VOLUME = "absorbance_per_volume"
    ABSORBANCE_PER_MASS = "absorbance_per_mass"
    ACTIVITY = "activity"
    ACTIVITY_PER_VOLUME = "activity_per_volume"
    MOLAR_MASS = "molar_mass"
    CONDUCTIVITY = "conductivity"
    RELATIVE_CENTRIFUGAL_FORCE = "relative_centrifugal_force"
    CONCENTRATION_FACTOR = "concentration_factor"
    WAVELENGTH = "wavelength"

    # -- Zielinski "dimensionless", but NOT Morris's mass fraction -----------
    DIMENSIONLESS = "dimensionless"
    PH = "ph"


#: Quantities a Morris control volume can carry.  Taken from
#: ``schemas.material_balance.QuantityKind`` and re-stated here so the
#: composition layer never has to import the model to know this.
MORRIS_BALANCE_QUANTITIES: frozenset[Quantity] = frozenset(
    {
        Quantity.MASS,
        Quantity.MASS_FLOW,
        Quantity.MASS_FRACTION,
        Quantity.AMOUNT,
        Quantity.AMOUNT_FLOW,
    }
)


# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class UnitSpec:
    """A unit symbol bound to exactly one :class:`Quantity`.

    ``to_base`` is the same convention both models use: ``base = value * to_base``.
    ``linear`` is False for quantities that are dimensionless but not linearly
    convertible -- pH is log10 of hydrogen-ion activity, and 7.0 pH is not
    "twice" 3.5 pH.
    """

    symbol: str
    quantity: Quantity
    to_base: float
    linear: bool = True
    source_model: str = "composition"
    note: str = ""

    @property
    def key(self) -> tuple[Quantity, str]:
        return (self.quantity, self.symbol)

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.symbol


_U = UnitSpec

#: ``to_base`` values taken verbatim from the two model registries, so the
#: composition layer cannot silently disagree with either of them.
_UNITS: tuple[UnitSpec, ...] = (
    # ---- MASS: base kg (Morris's base unit) --------------------------------
    _U("kg", Quantity.MASS, 1.0, source_model="morris"),
    _U("g", Quantity.MASS, 1.0e-3, source_model="morris",
       note="Morris registers g as a mass unit, so a Zielinski gram is "
            "admissible without inventing a conversion"),
    _U("mg", Quantity.MASS, 1.0e-6, source_model="morris"),
    _U("t", Quantity.MASS, 1.0e3, source_model="morris"),
    _U("lb", Quantity.MASS, 0.45359237, source_model="morris"),
    # ---- MASS_FLOW: base kg/h ---------------------------------------------
    _U("kg/h", Quantity.MASS_FLOW, 1.0, source_model="morris"),
    _U("kg/min", Quantity.MASS_FLOW, 1.0 / 60.0, source_model="morris"),
    _U("kg/s", Quantity.MASS_FLOW, 1.0 / 3600.0, source_model="morris"),
    _U("g/h", Quantity.MASS_FLOW, 1.0e-3, source_model="morris"),
    _U("g/min", Quantity.MASS_FLOW, 1.0e-3 / 60.0, source_model="morris"),
    _U("lb/h", Quantity.MASS_FLOW, 0.45359237, source_model="morris"),
    _U("lb/min", Quantity.MASS_FLOW, 0.45359237 / 60.0, source_model="morris"),
    # ---- MASS_FRACTION -----------------------------------------------------
    _U("1", Quantity.MASS_FRACTION, 1.0, source_model="morris",
       note="the *only* dimensionless reading Morris permits, and it means mass fraction"),
    _U("%", Quantity.MASS_FRACTION, 1.0e-2, source_model="morris",
       note="in Morris a percent IS a mass fraction and enters sum(w) = 1"),
    # ---- AMOUNT / AMOUNT_FLOW ----------------------------------------------
    _U("mol", Quantity.AMOUNT, 1.0, source_model="morris"),
    _U("kmol", Quantity.AMOUNT, 1.0e3, source_model="morris"),
    _U("gmol", Quantity.AMOUNT, 1.0e-3, source_model="morris"),
    _U("lbmol", Quantity.AMOUNT, 453.59237, source_model="morris"),
    _U("mol/h", Quantity.AMOUNT_FLOW, 1.0, source_model="morris"),
    _U("kmol/h", Quantity.AMOUNT_FLOW, 1.0e3, source_model="morris"),
    _U("mol/min", Quantity.AMOUNT_FLOW, 1.0e3 / 60.0 * 1.0e-3, source_model="morris"),
    _U("kmol/min", Quantity.AMOUNT_FLOW, 1.0e3 / 60.0, source_model="morris"),
    # ---- VOLUME: base mL ---------------------------------------------------
    _U("mL", Quantity.VOLUME, 1.0, source_model="zielinski"),
    _U("L", Quantity.VOLUME, 1.0e3, source_model="zielinski"),
    _U("dm3", Quantity.VOLUME, 1.0e3, source_model="zielinski"),
    _U("cm3", Quantity.VOLUME, 1.0, source_model="zielinski"),
    _U("uL", Quantity.VOLUME, 1.0e-3, source_model="zielinski"),
    # ---- VOLUME_FLOW: base mL/min -----------------------------------------
    _U("mL/min", Quantity.VOLUME_FLOW, 1.0, source_model="zielinski"),
    _U("mL/h", Quantity.VOLUME_FLOW, 1.0 / 60.0, source_model="zielinski"),
    # ---- TIME: base h -------------------------------------------------------
    _U("h", Quantity.TIME, 1.0, source_model="zielinski"),
    _U("min", Quantity.TIME, 1.0 / 60.0, source_model="zielinski"),
    _U("s", Quantity.TIME, 1.0 / 3600.0, source_model="zielinski"),
    _U("d", Quantity.TIME, 24.0, source_model="zielinski"),
    # ---- TEMPERATURE: base degC --------------------------------------------
    _U("degC", Quantity.TEMPERATURE, 1.0, source_model="zielinski"),
    _U("K", Quantity.TEMPERATURE, 1.0, source_model="zielinski",
       note="numerically equal; the Kelvin offset is deliberately not applied"),
    # ---- MOLAR_CONCENTRATION: base mol/L -----------------------------------
    _U("M", Quantity.MOLAR_CONCENTRATION, 1.0, source_model="zielinski"),
    _U("mM", Quantity.MOLAR_CONCENTRATION, 1.0e-3, source_model="zielinski"),
    _U("uM", Quantity.MOLAR_CONCENTRATION, 1.0e-6, source_model="zielinski"),
    # ---- MASS_CONCENTRATION: base g/L -------------------------------------
    _U("g/L", Quantity.MASS_CONCENTRATION, 1.0, source_model="zielinski"),
    _U("mg/mL", Quantity.MASS_CONCENTRATION, 1.0, source_model="zielinski"),
    _U("mg/dL", Quantity.MASS_CONCENTRATION, 0.01, source_model="zielinski"),
    _U("g/dL", Quantity.MASS_CONCENTRATION, 10.0, source_model="zielinski"),
    _U("mg/L", Quantity.MASS_CONCENTRATION, 1.0e-3, source_model="zielinski"),
    _U("ug/mL", Quantity.MASS_CONCENTRATION, 1.0e-3, source_model="zielinski"),
    _U("g_per_100mL", Quantity.MASS_CONCENTRATION, 10.0, source_model="zielinski"),
    # ---- ABSORBANCE ---------------------------------------------------------
    _U("AU", Quantity.ABSORBANCE, 1.0, source_model="zielinski",
       note="instrument-relative: the spectrophotometer was water-blanked, so AU "
            "is NOT grams, molarity or IU and no conversion to them exists"),
    _U("AU/mL", Quantity.ABSORBANCE_PER_VOLUME, 1.0, source_model="zielinski"),
    _U("AU/uL", Quantity.ABSORBANCE_PER_VOLUME, 1000.0, source_model="zielinski"),
    _U("g/AU", Quantity.ABSORBANCE_PER_MASS, 1.0, source_model="zielinski",
       note="the *declared dimension* of an AU-to-mass factor. No value is supplied "
            "by the paper; declaring the dimension is not supplying the factor"),
    # ---- ACTIVITY -----------------------------------------------------------
    _U("IU", Quantity.ACTIVITY, 1.0, source_model="zielinski"),
    _U("IU/L", Quantity.ACTIVITY_PER_VOLUME, 1.0, source_model="zielinski"),
    # ---- MOLAR_MASS ---------------------------------------------------------
    _U("Da", Quantity.MOLAR_MASS, 1.0, source_model="zielinski"),
    # ---- CONDUCTIVITY / RCF / FACTOR / WAVELENGTH --------------------------
    _U("mS", Quantity.CONDUCTIVITY, 1.0, source_model="zielinski"),
    _U("xg", Quantity.RELATIVE_CENTRIFUGAL_FORCE, 1.0, source_model="zielinski"),
    _U("fold", Quantity.CONCENTRATION_FACTOR, 1.0, source_model="zielinski"),
    _U("nm", Quantity.WAVELENGTH, 1.0, source_model="zielinski"),
    # ---- DIMENSIONLESS: Zielinski's reading, NOT Morris's mass fraction ----
    _U("1", Quantity.DIMENSIONLESS, 1.0, source_model="zielinski"),
    _U("%", Quantity.DIMENSIONLESS, 1.0e-2, source_model="zielinski",
       note="a generic percent (40 % glucose, 16 % NH4OH). Same symbol as Morris's "
            "mass-fraction percent, different meaning: they are not interchangeable"),
    _U("OD600", Quantity.DIMENSIONLESS, 1.0, linear=False, source_model="zielinski",
       note="optical density: a scattering measurement, not a dimensionless number"),
    _U("g_per_L_per_OD600", Quantity.DIMENSIONLESS, 1.0, linear=False,
       source_model="zielinski"),
    # ---- PH ----------------------------------------------------------------
    _U("pH", Quantity.PH, 1.0, linear=False, source_model="zielinski"),
)


class UnitRegistry:
    """``(quantity, symbol) -> UnitSpec``, with no symbol-only lookup.

    The absence of :meth:`by_symbol` is deliberate.  A symbol-only lookup is what
    would let ``%`` and ``1`` mean two different things on two sides of a
    connection.
    """

    def __init__(self, units: tuple[UnitSpec, ...] = _UNITS) -> None:
        self._by_key: dict[tuple[Quantity, str], UnitSpec] = {}
        for spec in units:
            if spec.key in self._by_key:
                raise QuantityError(
                    f"duplicate unit registration for quantity "
                    f"{spec.quantity.value!r} symbol {spec.symbol!r}"
                )
            self._by_key[spec.key] = spec
        #: symbol -> quantities it can denote, for error messages and the UI
        self._by_symbol: dict[str, tuple[Quantity, ...]] = {}
        for (quantity, symbol) in self._by_key:
            self._by_symbol.setdefault(symbol, ())
            if quantity not in self._by_symbol[symbol]:
                self._by_symbol[symbol] += (quantity,)

    def resolve(self, symbol: str, quantity: Quantity) -> UnitSpec:
        """Look up ``symbol`` **as a unit of ``quantity``**, or explain why not."""
        try:
            return self._by_key[(quantity, symbol)]
        except KeyError:
            meanings = self._by_symbol.get(symbol)
            if meanings is None:
                other = sorted(
                    {s for (_q, s) in self._by_key if s == symbol}
                )
                raise UnknownUnitError(
                    f"unit {symbol!r} is not registered. There is no conversion "
                    f"between it and anything the composition layer knows: an "
                    f"unregistered symbol is a missing declaration, not a default."
                ) from None
            raise QuantityMismatch(
                f"unit {symbol!r} means {', '.join(sorted(m.value for m in meanings))} "
                f"in this contract, but the port declares "
                f"{quantity.value!r}. The symbol is not allowed to decide the "
                f"quantity; declare the quantity explicitly."
            ) from None

    def symbols_for(self, quantity: Quantity) -> tuple[str, ...]:
        return tuple(
            sorted(spec.symbol for spec in self._by_key.values()
                   if spec.quantity is quantity)
        )

    def units_as_written(self) -> dict[Quantity, list[str]]:
        """Every ``(quantity, symbol)`` pair, for a manifest or a UI dropdown."""
        out: dict[Quantity, list[str]] = {}
        for (quantity, symbol) in self._by_key:
            out.setdefault(quantity, []).append(symbol)
        return {q: sorted(v) for q, v in sorted(out.items(), key=lambda kv: kv[0].value)}

    def __len__(self) -> int:
        return len(self._by_key)


REGISTRY = UnitRegistry()


# --------------------------------------------------------------------------- #
# conversion
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Conversion:
    """The one conversion a connection is allowed to perform, stated explicitly."""

    value: float
    from_unit: str
    to_unit: str
    quantity: Quantity
    factor: float
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "from_unit": self.from_unit,
            "to_unit": self.to_unit,
            "quantity": self.quantity.value,
            "factor": self.factor,
            "note": self.note,
        }


def convert(
    value: float,
    from_unit: str,
    to_unit: str,
    quantity: Quantity,
) -> Conversion:
    """Convert within **one** quantity, or raise.

    ``quantity`` is mandatory and is not inferred.  A caller that has two
    quantities in hand must state which one it means; that is what stops a mass
    being converted into a mass flow because both symbols happened to share a
    ``/``.
    """
    source = REGISTRY.resolve(from_unit, quantity)
    target = REGISTRY.resolve(to_unit, quantity)

    if not source.linear or not target.linear:
        raise NonConvertibleUnitError(
            f"{from_unit!r} and {to_unit!r} are {quantity.value} but at least one is "
            f"not linearly convertible, so no conversion exists. Supply the missing "
            f"calibration explicitly, or leave the value unresolved."
        )
    if from_unit == to_unit:
        return Conversion(
            value=value,
            from_unit=from_unit,
            to_unit=to_unit,
            quantity=quantity,
            factor=1.0,
            note="identical units; no conversion performed",
        )
    factor = source.to_base / target.to_base
    return Conversion(
        value=value * factor,
        from_unit=from_unit,
        to_unit=to_unit,
        quantity=quantity,
        factor=factor,
        note=(
            f"{quantity.value} {from_unit} -> {to_unit}; factor {factor:g} "
            f"through the base unit"
        ),
    )


def quantity_of(symbol: str, *, prefer: Quantity | None = None) -> Quantity:
    """Best-effort quantity for a bare symbol, for authoring aids only.

    Returns ``prefer`` when it is valid for the symbol, else the single
    registered meaning, else raises if the symbol is ambiguous.  A connection
    check must never use this: it would reintroduce symbol-driven compatibility.
    """
    if prefer is not None:
        REGISTRY.resolve(symbol, prefer)
        return prefer
    meanings = REGISTRY._by_symbol.get(symbol)
    if not meanings:
        raise UnknownUnitError(f"unit {symbol!r} is not registered")
    if len(meanings) > 1:
        raise QuantityMismatch(
            f"unit {symbol!r} is ambiguous: it means "
            f"{', '.join(sorted(m.value for m in meanings))}. State the quantity."
        )
    return meanings[0]


def is_convertible(quantity: Quantity, from_unit: str, to_unit: str) -> bool:
    """Whether :func:`convert` would succeed. Never raises."""
    try:
        convert(1.0, from_unit, to_unit, quantity)
    except QuantityError:
        return False
    return True


def describe_registry() -> Mapping[str, object]:
    """Machine-readable dump of the registry, for manifests and the Godot UI."""
    return {
        "contract_version": CONTRACT_VERSION,
        "quantities": sorted(q.value for q in Quantity),
        "units_by_quantity": {
            q.value: sorted(u.symbol for u in REGISTRY._by_key.values()
                            if u.quantity is q)
            for q in Quantity
        },
        "ambiguous_symbols": {
            symbol: sorted(q.value for q in meanings)
            for symbol, meanings in REGISTRY._by_symbol.items()
            if len(meanings) > 1
        },
        "non_linear_symbols": sorted(
            f"{spec.quantity.value}:{spec.symbol}"
            for spec in REGISTRY._by_key.values()
            if not spec.linear
        ),
    }