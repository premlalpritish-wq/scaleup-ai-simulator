"""The parameters and initial variables Lin et al. (2001) print, and nothing more.

Table I (printed p. 348) reports a parameter set for each of the two cultures:
the exponential-feed culture of *E. coli* W3110 and the constant-feed culture of
*E. coli* RB791. Both columns are transcribed exactly as printed, with the
paper's own "Origin/source" string, so a reader can see which numbers the
authors fitted and which they took from elsewhere.

Four rows print **two** values per strain, because the paper models the uptake
systems in two ways. Footnote c says no change in qOcap/qScap is considered
(value 0); footnote d says the synthesis of the uptake systems is controlled by
the availability of S, so qOcap and qScap change (0.51, 0.1, 0.9, 0.23, 0.35,
0.55). Those four rows are kept in `PROTOCOL_VARIANTS` with the footnote that
applies to each value, rather than being silently collapsed to one number.

The reported capacities in the abstract (printed p. 347) are stored separately:
they are stated in mmol g-1 h-1, a different dimension from Table I's g g-1 h-1,
and the paper prints no molar mass that would convert one to the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .provenance import EvidenceRef, Quantity, reported

#: Printed page of Table I.
TABLE_I_PAGE = 348
#: Printed page of the abstract.
ABSTRACT_PAGE = 347


@dataclass(frozen=True)
class Parameter:
    """One Table I row: a name, a unit, a value per culture, and its origin."""

    name: str
    unit: str
    values: dict[str, float | None]
    origin: str
    printed_page: int = TABLE_I_PAGE

    def value_for(self, strain: str) -> float | None:
        try:
            return self.values[strain]
        except KeyError:
            raise KeyError(
                f"{self.name!r} has no value for {strain!r}; "
                f"known cultures: {sorted(self.values)}"
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "values": dict(self.values),
            "origin_as_printed": self.origin,
            "printed_page": self.printed_page,
            "evidence": EvidenceRef(
                printed_page=self.printed_page, section="Table I"
            ).to_dict(),
        }


#: The two culture columns Table I prints, keyed by the label the model uses.
CULTURES = {
    "w3110_exponential": "fed-batch culture of E. coli W3110 (exponential feed)",
    "rb791_constant": "fed-batch culture of E. coli RB791 (constant feed)",
}


def _p(name: str, unit: str, a: float | None, b: float | None, origin: str) -> Parameter:
    return Parameter(
        name=name,
        unit=unit,
        values={"w3110_exponential": a, "rb791_constant": b},
        origin=origin,
    )


#: Table I, in printed order. `None` marks the printed em-dash (not applicable).
TABLE_I: tuple[Parameter, ...] = (
    _p("KS", "g/L", 0.035, 0.01, "Data fitting"),
    _p("KA", "g/L", 0.1, 0.1, "Data fitting"),
    _p("qm", "g/(g h)", 0.03, 0.03, "Data fitting"),
    _p("qSmax", "g/(g h)", 1.86, 1.5, "Experimental data, data fitting"),
    _p("qOmax", "g/(g h)", 0.607, 0.65, "Experimental data, data fitting"),
    _p("qAc,max", "g/(g h)", 0.15, 0.14402, "Experimental data, data fitting"),
    _p("YX/S,ox", "g/g", 0.51, 0.51, "Experimental data, Xu et al., 1999"),
    _p("CS", "mol C/g", 0.0333, 0.0333, "Chemical formula, Xu et al., 1999"),
    _p("CA", "mol C/g", 0.0333, 0.0333, "Chemical formula, Xu et al., 1999"),
    _p("CX", "mol C/g", 0.04, 0.04, "Stoichiometric analysis, Xu et al., 1999"),
    _p("YO/S", "g/g", 1.067, 1.067, "Stoichiometric constant, Xu et al., 1999"),
    _p("YX/S,of", "g/g", 0.15, 0.15, "Chen et al., 1997; Varma and Palsson, 1994"),
    _p("YA/S", "g/g", 0.667, 0.667, "Stoichiometric constant, Xu et al., 1999"),
    _p("YO/A", "g/g", 1.067, 1.067, "Stoichiometric constant, Xu et al., 1999"),
    _p("YX/A", "g/g", 0.35085, 0.35085,
       "Experimental data, data fitting, Xu et al., 1999"),
    _p("Si", "g/L", 532.0, 200.0, "Input concentration"),
    _p("X0", "g/L", 0.121, 0.0001, "Input concentration"),
    _p("S0", "g/L", 0.5, 5.0, "Input concentration"),
    _p("V0", "L", 7.0, 4.0, "Input concentration"),
)


def parameters_by_name() -> dict[str, Parameter]:
    return {p.name: p for p in TABLE_I}


def parameter(name: str) -> Parameter:
    try:
        return parameters_by_name()[name]
    except KeyError:
        raise KeyError(f"unknown Table I parameter {name!r}") from None


@dataclass(frozen=True)
class ProtocolVariant:
    """One of the two printed values of a protocol-dependent Table I row."""

    name: str
    unit: str
    value: float
    footnote: str
    note_as_printed: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "value": self.value,
            "footnote": self.footnote,
            "note_as_printed": self.note_as_printed,
        }


#: The four rows Table I prints twice, one value per modelling variant.
PROTOCOL_VARIANTS: tuple[ProtocolVariant, ...] = (
    ProtocolVariant("qESd", "g/(g h)", 0.9, "d",
                    "Synthesis of the uptake system for substrate is controlled "
                    "by the availability of S"),
    ProtocolVariant("qEOd", "g/(g h)", 0.35, "d",
                    "Synthesis of the uptake system for oxygen is controlled by "
                    "the availability of S"),
    ProtocolVariant("YES/X", "g/g", 0.51, "d", "growth-dependent enzyme yield"),
    ProtocolVariant("YEO/X", "g/g", 0.23, "d", "growth-dependent enzyme yield"),
)

#: The same four rows' other printed value: 0, footnote c (no change considered).
NO_CHANGE_VALUES: dict[str, float] = {"qESd": 0.0, "qEOd": 0.0}

#: The constants the appendix needs and Table I prints no number for. A caller
#: must supply them per run; the model never guesses.
UNVALUED_RUN_INPUTS: dict[str, str] = {
    "cS": (
        "the factor in the appendix's initial-value equation for rS "
        "(rS0 = cS * mu_max / (qESd + mu_max)); the paper defines the symbol but "
        "prints no value on any page"
    ),
    "cO": (
        "the factor in the appendix's initial-value equation for rO "
        "(rO0 = cO * mu_max / (qEOd + mu_max)); the paper defines the symbol but "
        "prints no value on any page"
    ),
    "kLa": (
        "the volumetric oxygen transfer coefficient equation (4) requires; Table "
        "I does not list it and the paper prints no value for these cultivations"
    ),
    "DOT_star": (
        "the saturation dissolved oxygen tension in equation (4); the paper "
        "prints the symbol DOT* in the nomenclature and no value for it"
    ),
    "H": (
        "the Henry's-law constant in equation (4); the nomenclature prints "
        "'H  constant derived from the Henry's law [14 000 % L g-1]', i.e. a "
        "value in the nomenclature rather than in Table I"
    ),
}

#: The one unvalued constant the nomenclature does print a value for.
NOMENCLATURE_CONSTANTS: dict[str, tuple[float, str]] = {
    "H": (14000.0, "% L/g"),
}


def _q(name: str, strain: str, value: float) -> Quantity:
    param = parameter(name)
    return reported(
        quantity_id=f"table_i.{name}.{strain}",
        label=name,
        value=value,
        unit=param.unit,
        evidence=EvidenceRef(
            printed_page=TABLE_I_PAGE, section="Table I",
            quote=f"{name} {param.unit}",
        ),
        original_unit="g g-1 h-1" if param.unit == "g/(g h)" else None,
        notes=f"Table I origin/source, as printed: {param.origin}",
    )


def reported_parameters() -> dict[str, Quantity]:
    """Every Table I value, as a reported Quantity keyed by ``name@culture``."""
    out: dict[str, Quantity] = {}
    for param in TABLE_I:
        for strain, value in param.values.items():
            if value is None:
                continue
            out[f"{param.name}@{strain}"] = _q(param.name, strain, value)
    return out


#: The capacities the abstract states, in the abstract's own unit.
REPORTED_CAPACITIES: tuple[Quantity, ...] = (
    reported(
        "capacity.qScap.end", "glucose uptake capacity at the end of fed-batch",
        0.6, "mmol/(g h)",
        EvidenceRef(printed_page=ABSTRACT_PAGE, section="Abstract",
                    quote="fell to about 0.6 mmol g-1 h-1"),
        original_unit="mmol g-1 h-1",
        notes="reported at mu approximately 0.02 1/h; a separate dimension from "
              "Table I's g g-1 h-1, with no printed conversion",
    ),
    reported(
        "capacity.qOcap.end", "oxygen uptake capacity at the end of fed-batch",
        5.0, "mmol/(g h)",
        EvidenceRef(printed_page=ABSTRACT_PAGE, section="Abstract",
                    quote="was 5 mmol g-1 h-1 at the end"),
        original_unit="mmol g-1 h-1",
        notes="a separate dimension from Table I's g g-1 h-1; no printed conversion",
    ),
    reported(
        "threshold.qScap.mu", "growth rate below which qScap decreases",
        0.15, "1/h",
        EvidenceRef(printed_page=ABSTRACT_PAGE, section="Abstract",
                    quote="below 0.15 h-1"),
        notes="the abstract's stated threshold, not a fitted constant",
    ),
    reported(
        "threshold.qOcap.mu", "growth rate below which qOcap decreases",
        0.25, "1/h",
        EvidenceRef(printed_page=ABSTRACT_PAGE, section="Abstract",
                    quote="below 0.25 h-1"),
        notes="the abstract's stated threshold, not a fitted constant",
    ),
)
