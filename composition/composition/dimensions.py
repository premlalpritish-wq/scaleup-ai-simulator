"""Wiring the Zielinski ``Dimension`` vocabulary to the composition contract.

Declared as data, not imported.  ``composition`` therefore depends on the model
only through a JSON boundary, and a change to the model's ``Dimension`` enum
shows up as an unmapped name rather than as an ``AttributeError`` deep inside
the engine.

The mapping is deliberately *many-to-one only where the physics agrees*.
``MASS`` and ``MASS_FLOW`` stay separate: Morris's whole reason for having a
``TIME``-free kind taxonomy is that a flow's unit carries its time basis, and
collapsing the two here would destroy the distinction CG-03 tests.
"""

from __future__ import annotations

from .quantities import Quantity

#: Zielinski ``Dimension.value`` -> composition ``Quantity``.
ZIELINSKI_DIMENSION_TO_QUANTITY: dict[str, Quantity] = {
    "volume": Quantity.VOLUME,
    "volume_rate": Quantity.VOLUME_FLOW,
    "time": Quantity.TIME,
    "temperature": Quantity.TEMPERATURE,
    "mass": Quantity.MASS,
    "mass_concentration": Quantity.MASS_CONCENTRATION,
    "molar_concentration": Quantity.MOLAR_CONCENTRATION,
    "absorbance": Quantity.ABSORBANCE,
    "absorbance_per_volume": Quantity.ABSORBANCE_PER_VOLUME,
    "absorbance_per_mass": Quantity.ABSORBANCE_PER_MASS,
    "wavelength": Quantity.WAVELENGTH,
    "dimensionless": Quantity.DIMENSIONLESS,
    "activity": Quantity.ACTIVITY,
    "activity_per_volume": Quantity.ACTIVITY_PER_VOLUME,
    "molar_mass": Quantity.MOLAR_MASS,
    "conductivity": Quantity.CONDUCTIVITY,
    "relative_centrifugal_force": Quantity.RELATIVE_CENTRIFUGAL_FORCE,
    "concentration_factor": Quantity.CONCENTRATION_FACTOR,
    "ph": Quantity.PH,
}

#: Morris ``QuantityKind.value`` -> composition ``Quantity``.  Identical strings
#: by construction; spelled out so the two vocabularies cannot drift.
MORRIS_KIND_TO_QUANTITY: dict[str, Quantity] = {
    "mass": Quantity.MASS,
    "mass_flow": Quantity.MASS_FLOW,
    "mass_fraction": Quantity.MASS_FRACTION,
    "amount": Quantity.AMOUNT,
    "amount_flow": Quantity.AMOUNT_FLOW,
}

#: Ganjave ``QuantityKind.value`` -> composition ``Quantity``.
#:
#: Two of these mappings are the whole reason the table is spelled out rather
#: than inherited from the symbol.  Ganjave registers ``g/L`` for a culture
#: concentration, a half-saturation constant *and* the oxygen saturation
#: concentration, and ``%`` for a half-saturation constant *and* the
#: dissolved-oxygen reading.  Only the port surface crosses the boundary, so
#: only the quantities a port can carry need a home here -- but the
#: half-saturation kinds are included so that a future port exposing one is a
#: visible, correct mapping rather than a guess.
GANJAVE_KIND_TO_QUANTITY: dict[str, Quantity] = {
    # -- quantities a Ganjave port carries ---------------------------------
    "time": Quantity.TIME,
    "volume": Quantity.VOLUME,
    "volume_flow": Quantity.VOLUME_FLOW,
    "mass_concentration": Quantity.MASS_CONCENTRATION,
    # dissolved_oxygen_percent: a percentage of the probe's saturation reading.
    # DIMENSIONLESS is Zielinski's *generic* percent reading, which is the only
    # percent this contract has that is not a mass fraction.  It is the closest
    # correct home, and Ganjave refuses the mass-fraction reading explicitly --
    # see the connection contract in ``adapters/ganjave_contract.py``.
    "dissolved_oxygen_percent": Quantity.DIMENSIONLESS,
    # -- kinds Ganjave does not currently publish as ports ------------------
    "specific_growth_rate": Quantity.DIMENSIONLESS,
    "half_saturation_concentration": Quantity.MASS_CONCENTRATION,
    "half_saturation_dissolved_oxygen": Quantity.DIMENSIONLESS,
    "yield": Quantity.DIMENSIONLESS,
    "enzyme_ratio": Quantity.DIMENSIONLESS,
    "oxygen_transfer_coefficient": Quantity.DIMENSIONLESS,
    "oxygen_saturation_concentration": Quantity.MASS_CONCENTRATION,
    "feed_percent_weight_volume": Quantity.DIMENSIONLESS,
    "optical_density": Quantity.DIMENSIONLESS,
    "fold": Quantity.DIMENSIONLESS,
}

#: The reverse direction, used when a Morris manifest declares its ports.
QUANTITY_TO_MORRIS_KIND: dict[Quantity, str] = {
    q: name for name, q in MORRIS_KIND_TO_QUANTITY.items()
}


def quantity_for_zielinski_dimension(dimension: str, unit: str) -> Quantity | None:
    """Map a Zielinski dimension to a contract quantity, or ``None`` if unmapped.

    ``None`` means the model declared a dimension this contract has never heard
    of.  That is a reportable gap, not a reason to guess: the port is published
    with ``unavailable_reason`` set and cannot be connected.
    """
    if not dimension:
        return None
    return ZIELINSKI_DIMENSION_TO_QUANTITY.get(dimension)


def quantity_for_ganjave_kind(kind: str, unit: str) -> Quantity | None:
    """Map a Ganjave ``QuantityKind.value`` to a contract quantity.

    ``None`` means the model declared a kind this contract has never heard of,
    which is a reportable gap rather than a reason to guess.  The unit is taken
    as an argument so the caller can report *which* symbol failed to resolve,
    but it never decides the quantity: ``g/L`` and ``%`` each denote two or
    three different things across the two existing models.
    """
    if not kind:
        return None
    return GANJAVE_KIND_TO_QUANTITY.get(kind)