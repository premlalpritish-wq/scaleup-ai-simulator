"""The experimental context Simensen et al. (2022) measured in.

The dataset is a composition *of a particular culture*: *E. coli* K-12 MG1655,
grown in a defined glucose minimal medium in a batch fermentor, sampled during
balanced exponential growth. The paper says the composition is condition-
dependent, so the condition is part of the dataset and is recorded here with the
printed page each element comes from.

**This is not the insulin simulation's context.** It is a different strain in a
different medium at a different scale and a different mode. No value here is
transferred to that process and this package makes no compatibility claim.
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
        key=key, label=label, value=value,
        evidence=EvidenceRef(printed_page=page, section=section, quote=quote),
    )


#: The context the measurement belongs to. Printed pp. 1, 3 and 7.
EXPERIMENTAL_CONTEXT: tuple[Condition, ...] = (
    _c("organism", "organism", "Escherichia coli", 1, "Title",
       "Escherichia coli biomass composition"),
    _c("strain", "strain", "E. coli K-12 MG1655 (700926, ATCC)", 3,
       "Strain, media and culture conditions", "K-12 MG1655"),
    _c("construct", "construct",
       "none: a wild-type K-12 strain was used, not a recombinant one", 3,
       "Strain, media and culture conditions", "glycerol stock solutions"),
    _c("medium", "fermentation medium",
       "modified minimal M9 with 2% (w/v) glucose, 3 mM MgSO4, 93.5 mM NH4Cl, "
       "8.5 mM NaCl, 11.5 mM KH2PO4 and 0.2% (v/v) trace minerals", 3,
       "Strain, media and culture conditions",
       "using 1 L of a modified minimal M9 medium containing 2% (w/v) glucose"),
    _c("reactor", "reactor",
       "a 3 L Eppendorf New Brunswick BioFlo 115 bioreactor, batch setup", 3,
       "Strain, media and culture conditions",
       "using a batch fermentor setup"),
    _c("scale", "working volume", "1 L in a 3 L bioreactor", 3,
       "Strain, media and culture conditions", "using 1 L of a modified minimal M9"),
    _c("temperature", "temperature", "37 degC", 3,
       "Strain, media and culture conditions", "with shaking (37"),
    _c("dissolved_oxygen", "dissolved oxygen", "held at or above 40%", 3,
       "Strain, media and culture conditions", "ensuring DO"),
    _c("growth_phase", "sampling condition",
       "balanced exponential growth, fermentation parameters monitored "
       "throughout", 3, "Strain, media and culture conditions",
       "allowing for biomass sampling in the exponential growth"),
)


def context_by_key() -> dict[str, Condition]:
    return {c.key: c for c in EXPERIMENTAL_CONTEXT}


def condition(key: str) -> Condition:
    try:
        return context_by_key()[key]
    except KeyError:
        raise KeyError(f"unknown context key {key!r}") from None


#: The context this dataset must not be confused with: the insulin process's.
TARGET_PROCESS_NOTE = (
    "The composition layer's target process is Zielinski et al. (2019), "
    "E. coli 20 IBA 1 / pIBAINS in GMS medium, 4 L in a 7.5 L Bioflo Celligen "
    "310 with pH-stat glucose feeding at 30 degC. Simensen et al. measure a "
    "wild-type MG1655 in M9 with 2% glucose, 1 L in a 3 L BioFlo 115, in batch "
    "exponential growth at 37 degC, and state that biomass composition is "
    "condition-dependent. This dataset is that measurement; it is not transferred "
    "to the insulin process."
)
