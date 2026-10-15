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