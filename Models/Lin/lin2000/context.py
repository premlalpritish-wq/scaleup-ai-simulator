"""The experimental context Lin et al. (2001) ran in.

The task this package exists for is paper-faithful, so the context is a
first-class object rather than a comment: the strain, the strain's genotype, the
presence of a plasmid and whether it was induced, the medium, the reactor, the
scale and the operating conditions are each recorded with the printed page they
come from.

Everything here is read out of the paper's own text, on the printed pages the
records name. Nothing is inferred from a title. Where the paper describes two
protocols or two strains, both are recorded.

**This context is not the insulin simulation's context.** It is *E. coli* K-12
W3110 / RB791 in a phosphate-buffered mineral salt medium at 35 degC, i.e. a
different strain, plasmid, medium, reactor and temperature from
``zielinski2019.rhi_process``. Nothing here is portable to that process, and
this package makes no claim that it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .provenance import EvidenceRef


@dataclass(frozen=True)
class Condition:
    """One stated element of the experimental context, with its printed page."""

    key: str
    label: str
    value: str
    evidence: EvidenceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "evidence": self.evidence.to_dict(),
        }


def _c(key: str, label: str, value: str, page: int, section: str, quote: str) -> Condition:
    return Condition(
        key=key,
        label=label,
        value=value,
        evidence=EvidenceRef(printed_page=page, section=section, quote=quote),
    )


#: The context every number in this package belongs to. Printed pages 347-349.
EXPERIMENTAL_CONTEXT: tuple[Condition, ...] = (
    _c(
        "organism", "organism", "Escherichia coli", 347, "Title",
        "Cultivations of Escherichia coli",
    ),
    _c(
        "strain.primary", "primary strain",
        "E. coli K12 W3110 [F-, IN(rrnD-rrnE)1, l-]", 348, "Strains",
        "Cultivations of E. coli K12 W3110",
    ),
    _c(
        "strain.secondary", "secondary strain",
        "its lacIq derivative RB791 (lacIq)", 348, "Strains",
        "its lacIq derivative RB791",
    ),
    _c(
        "construct", "plasmid construct (present, not induced)",
        "some experiments used plasmid pDSCrimi or pKK177GlucC/pUBS520; "
        "these were not induced for product expression", 348, "Strains",
        "the strains contained the plasmids pDSCrimi",
    ),
    _c(
        "medium", "medium",
        "phosphate-buffered mineral salt medium (Teich et al., 1998), "
        "initial glucose 5 g/L", 348, "Cultivation Media and Conditions",
        "Phosphate-buffered mineral salt medium according to Teich",
    ),
    _c(
        "feed.medium", "feed solution",
        "same components as the medium except glucose 532 or 200 g/L, "
        "(NH4)2SO4 2.0 g/L, trace components 10 mL/L; no MgSO4 7H2O",
        348, "Cultivation Media and Conditions",
        "The feed solution contained essentially the same components",
    ),
    _c(
        "reactor", "reactor",
        "15 L or 6 L Biostat ED fermenter (B. Braun Biotech International)",
        349, "Materials and Methods",
        "All fermentations were performed in either a 15 L or a 6 L Biostat",
    ),
    _c(
        "scale", "working volume",
        "starting volume 7 L (15 L reactor) or 4 L (6 L reactor)",
        349, "Materials and Methods",
        "with a starting volume of 7 L or 4 L",
    ),
    _c(
        "temperature", "temperature", "35 degC", 349, "Materials and Methods",
        "temperature 35",
    ),
    _c(
        "ph", "pH", "7.0, controlled with 25% ammonia", 349, "Materials and Methods",
        "pH 7.0",
    ),
    _c(
        "dot", "dissolved oxygen tension held above 20% in the batch phase",
        "air 0.002 to 2 vvm, stirrer 200 to 800 rpm in cascade", 349,
        "Materials and Methods", "keep the dissolved oxygen tension (DOT) above 20%",
    ),
    _c(
        "protocol.exponential", "protocol 1 (exponential feed, Xu et al. 1999)",
        "batch 0.92 h; exponential feed, initial 5.7 mL/h, rate constant "
        "0.27 1/h, for 9.1 h; then constant at 64 mL/h for 2.5 h; then "
        "57 mL/h", 349, "Materials and Methods",
        "an exponential glucose feed was started",
    ),
    _c(
        "protocol.constant", "protocol 2 (constant feed, Teich et al. 1998)",
        "constant feed started at OD500 8, 53.2 mL/h to the end", 349,
        "Materials and Methods", "the feeding pump was started at a constant rate",
    ),
)


def context_by_key() -> dict[str, Condition]:
    return {c.key: c for c in EXPERIMENTAL_CONTEXT}


def condition(key: str) -> Condition:
    try:
        return context_by_key()[key]
    except KeyError:
        raise KeyError(f"unknown context key {key!r}") from None


#: The context this model must not be confused with: the insulin simulation's.
TARGET_PROCESS_NOTE = (
    "The composition layer's target process is Zielinski et al. (2019), "
    "E. coli 20 IBA 1 / pIBAINS in GMS medium, 4 L in a 7.5 L Bioflo Celligen "
    "310 with pH-stat glucose feeding at 30 degC. Lin et al. use a different "
    "strain, a different (uninduced) plasmid, a different medium, different "
    "reactors and 35 degC. This package is standalone: it does not register a "
    "model, does not declare ports, and transfers no parameter to that process."
)
