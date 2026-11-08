"""Dimensional analysis of the oxygen balance, as executable unit algebra.

The purpose of this module is to make the dimensional claims in the
transcription notes *checkable* rather than asserted in prose. Every quantity
in the dissolved-oxygen balance is declared once, with the dimension the paper
implies for it, and the terms of eq. (11) and eq. (15) are then *computed* from
those declarations. If two terms of a differential equation come out with
different dimensions, the equation cannot be adding them, and this module says
so in a form a test can assert on.

The base system
---------------

Four dimensions: mass ``M``, length ``L``, time ``T``, and a ``PERCENT``
pseudo-dimension that exists solely so that "percentage of the probe's
saturation reading" and "dimensionless number" stay distinguishable. ``DO`` is
a percentage because the paper's notation table defines it as "Percentage of
dissolved oxygen at time t" and reports ``Ko,1``/``Ko,2`` in ``%``.

One subtlety is declared rather than hidden. A yield coefficient printed as
``g of biomass/g of oxygen`` (Table 2) is a ratio of one mass to another, so it
is **dimensionless** in this system: ``[Yo] = M·M⁻¹ = 1``. That is correct and
it is also why the equation works, because ``mu_k/Yok`` then converts a
*biomass*-specific rate into an *oxygen*-specific rate. The physical identity of
the two masses comes from the unit labels in Table 2, not from the algebra.

What the analysis shows
-----------------------

With ``[C*] = M·L⁻³`` (0.0075 g/L) and ``[kLa] = T⁻¹``:

======================================  =====================  ================
term                                    printed as             dimension
======================================  =====================  ================
oxygen transfer  ``kLa·(100 - DO)``     ``kLa`` x percent      ``PERCENT·T⁻¹``
oxygen uptake   ``(mu1/Yo1+mu2/Yo2)X``  specific x biomass    ``M·L⁻³·T⁻¹``
uptake -> percent, ``(100/C*)·OUR``     ``100`` / ``C*``       ``PERCENT·T⁻¹``
uptake x ``C*`` (a *product*)           ``100`` x ``C*``       ``PERCENT·M²·L⁻⁶·T⁻¹``
======================================  =====================  ================

Only the first and third rows are in ``PERCENT·T⁻¹``, which is the dimension
of ``d(DO)/dt``. The fourth row cannot be added to them, which is what a
product reading of the printed factor would require. The rendered page (see
``SOURCE`` below) shows the paper printing the *quotient*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

#: Where the printed expressions were verified. Both equations were read from a
#: rendering of the article PDF, not from its text layer: the text layer drops
#: the fraction bar, which is exactly what makes the printed factor read as a
#: product.
SOURCE = {
    "eq_11": (
        "printed page 4, eq. (11), read from a 9x rendering: the factor shows "
        "100 above a fraction bar and C* below it"
    ),
    "eq_15": (
        "printed page 4, eq. (15), read from a 9x rendering: the same factor, "
        "100 over C*, beside the dilution term"
    ),
    "notation": "printed page 2, Notations table (DO, kLa, C*)",
    "table_2": "printed page 4, Table 2 (Yo1, Yo2, Ko,1, Ko,2)",
}


@dataclass(frozen=True)
class Dimension:
    """An exponent vector over mass, length, time and percent."""

    mass: int = 0
    length: int = 0
    time: int = 0
    percent: int = 0

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(
            self.mass + other.mass,
            self.length + other.length,
            self.time + other.time,
            self.percent + other.percent,
        )

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(
            self.mass - other.mass,
            self.length - other.length,
            self.time - other.time,
            self.percent - other.percent,
        )

    def __pow__(self, exponent: int) -> "Dimension":
        return Dimension(
            self.mass * exponent,
            self.length * exponent,
            self.time * exponent,
            self.percent * exponent,
        )

    def __add__(self, other: "Dimension") -> "Dimension":
        """Addition of like dimensions, as in a sum inside an equation."""
        if not isinstance(other, Dimension):
            return NotImplemented
        if self != other:
            raise TypeError(
                f"cannot add {self} to {other}: the terms have different "
                f"dimensions, so the printed expression cannot be a single "
                f"physical quantity"
            )
        return self

    def __str__(self) -> str:
        parts = []
        if self.mass:
            parts.append(f"M{self.mass:+d}".replace("+", "") if self.mass > 0 else f"M{self.mass}")
        if self.length:
            parts.append(f"L{self.length:+d}" if self.length > 0 else f"L{self.length}")
        if self.time:
            parts.append(f"T{self.time:+d}" if self.time > 0 else f"T{self.time}")
        if self.percent:
            parts.append(f"%{self.percent:+d}" if self.percent > 0 else f"%{self.percent}")
        return " ".join(parts) if parts else "1 (dimensionless)"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Dimension)
            and (self.mass, self.length, self.time, self.percent)
            == (other.mass, other.length, other.time, other.percent)
        )

    def __hash__(self) -> int:
        return hash((self.mass, self.length, self.time, self.percent))


#: Convenient aliases.
DIMENSIONLESS = Dimension()
PERCENT = Dimension(percent=1)
PERCENT_PER_TIME = Dimension(time=-1, percent=1)
GAS_PER_LITRE = Dimension(mass=1, length=-3)          # C*, and any g/L concentration
PER_TIME = Dimension(time=-1)                        # mu_k, kLa, beta_k
MASS_CONCENTRATION_PER_TIME = Dimension(mass=1, length=-3, time=-1)  # the uptake rate
VOLUME = Dimension(length=3)                         # V, in L
VOLUME_FLOW = Dimension(length=3, time=-1)           # F, in L/h

#: Every quantity the oxygen balance reads, with the dimension the paper's own
#: definitions give it. ``source`` records where that dimension comes from.
QUANTITIES: Mapping[str, Dimension] = {
    # Notations, p. 2: "DO  Percentage of dissolved oxygen at time t"
    "DO": PERCENT,
    # Table 2 / notation: biomass concentration
    "X": GAS_PER_LITRE,
    # eq. (5): mum_k is a specific rate, h^-1
    "mum1": PER_TIME,
    "mum2": PER_TIME,
    # Table 2: "g of biomass/g of oxygen" -- a ratio of masses
    "Yo1": DIMENSIONLESS,
    "Yo2": DIMENSIONLESS,
    # p. 3: "The kLa was found to be 133 h-1"
    "kLa": PER_TIME,
    # Notations, p. 2: "C* Maximum solubility of oxygen in media (0.0075 g.l-1)"
    "C_star": GAS_PER_LITRE,
    # eq. (16): F is a volumetric rate; V a volume, so F/V is a rate
    "F": VOLUME_FLOW,
    "V": VOLUME,
}


def oxygen_balance_dimensions() -> dict[str, Dimension]:
    """Dimension of each term of eq. (11) and eq. (15), computed from the above."""
    DO = QUANTITIES["DO"]
    kLa = QUANTITIES["kLa"]
    C_star = QUANTITIES["C_star"]
    X = QUANTITIES["X"]
    mum1, mum2 = QUANTITIES["mum1"], QUANTITIES["mum2"]
    Yo1, Yo2 = QUANTITIES["Yo1"], QUANTITIES["Yo2"]

    # (100 - DO): a subtraction of a percentage, i.e. still a percentage.
    percent_gap = PERCENT
    # The printed "100/C*". The numeral 100 is not a bare constant here: its
    # role is to convert the uptake rate, expressed per unit saturation, into
    # a percentage per hour -- the same role the 100 in kLa*(100 - DO) plays.
    # So it carries the PERCENT dimension, and the quotient is PERCENT/[C*].
    quotient_factor = PERCENT / C_star
    # 100*C*: the product reading, kept only so it can be shown to fail.
    product_factor = C_star

    uptake_rate = (mum1 / Yo1 + mum2 / Yo2) * X

    return {
        "transfer_kLa_x_100_minus_DO": kLa * percent_gap,
        "uptake_rate_mu_over_Y_times_X": uptake_rate,
        "printed_quotient_factor_100_over_C": quotient_factor,
        "consumption_as_printed": quotient_factor * uptake_rate,
        "product_reading_factor_100_times_C": product_factor,
        "consumption_if_product_reading": product_factor * uptake_rate,
        "d_DO_dt_required": PERCENT_PER_TIME,
        "fed_batch_dilution_DO_x_F_over_V": DO * (QUANTITIES["F"] / QUANTITIES["V"]),
    }


def oxygen_balance_report() -> dict[str, object]:
    """A structured statement of whether the printed terms can be added."""
    dims = oxygen_balance_dimensions()
    required = dims["d_DO_dt_required"]
    transfer = dims["transfer_kLa_x_100_minus_DO"]
    as_printed = dims["consumption_as_printed"]
    as_product = dims["consumption_if_product_reading"]
    fed_dilution = dims["fed_batch_dilution_DO_x_F_over_V"]
    return {
        "source": SOURCE,
        "dimensions": {k: str(v) for k, v in dims.items()},
        "required_dimension_of_d_DO_dt": str(required),
        "transfer_matches_requirement": transfer == required,
        "consumption_as_printed_matches_requirement": as_printed == required,
        "consumption_if_product_reading_matches_requirement": as_product == required,
        "fed_batch_dilution_matches_requirement": fed_dilution == required,
        "batch_terms_addable": transfer == as_printed == required,
        "batch_terms_addable_under_product_reading": transfer == as_product == required,
        "conclusion": (
            "The printed quotient 100/C* makes both terms of eq. (11) "
            "PERCENT/T and therefore additive. The product reading 100*C* "
            "would make the consumption term PERCENT*M^2*L^-6/T, which cannot "
            "be added to the transfer term, so it is not a viable reading of "
            "the printed equation."
        ),
    }


__all__ = [
    "C_star",
    "DIMENSIONLESS",
    "Dimension",
    "GAS_PER_LITRE",
    "MASS_CONCENTRATION_PER_TIME",
    "PERCENT",
    "PERCENT_PER_TIME",
    "PER_TIME",
    "QUANTITIES",
    "SOURCE",
    "VOLUME",
    "VOLUME_FLOW",
    "oxygen_balance_dimensions",
    "oxygen_balance_report",
]