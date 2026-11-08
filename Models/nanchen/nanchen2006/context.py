"""The experimental context Nanchen, Schicker & Sauer (2006) ran in.

The paper developed a novel mini-scale chemostat (a 17-mL Hungate tube run at a
10-mL working volume in a water bath) and used it for glucose-limited continuous
cultivation of *E. coli* MG1655 with 13C tracing. The model this package
implements -- Pirt's chemostat relation -- is evaluated in that context, with
that context's parameters, so the context is recorded here with the printed page
it comes from.

**This is not the insulin simulation's context.** It is a different strain, a
different (non-recombinant) culture, a different medium, a 10-mL chemotstat
instead of a 4-L fed-batch, and steady state instead of a fed-batch trajectory.
Nothing here is portable to that process and this package claims no such thing.
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


#: The context every number in this package belongs to. Printed pp. 1164-1165.
EXPERIMENTAL_CONTEXT: tuple[Condition, ...] = (
    _c("organism", "organism", "Escherichia coli", 1164, "Title",
       "Cultures of Escherichia coli"),
    _c("strain", "strain", "E. coli MG1655 (F- rph-1)", 1164,
       "Strains and growth conditions", "E. coli MG1655"),
    _c("construct", "construct",
       "none: a wild-type K-12 strain was used, not a recombinant one", 1164,
       "Strains and growth conditions", "was used for all"),
    _c("medium", "medium",
       "M9 minimal medium, 1 g/L glucose as the limiting substrate, pH 7.0",
       1165, "Bioreactors", "The chemostat feed medium was M9 minimal medium"),
    _c("reactor", "reactor",
       "a 17-mL Hungate tube (Bellco Glass) with a butyl rubber septum, placed "
       "in a water bath", 1164, "Bioreactors",
       "The cultivation vessel of the continuous-culture system was a"),
    _c("scale", "working volume", "10 mL", 1164, "Bioreactors",
       "with a working volume of 10 ml"),
    _c("temperature", "temperature", "37 degC", 1164, "Bioreactors",
       "temperature was maintained at 37"),
    _c("aeration", "aeration",
       "20 mL/min, about 2 volumes per volume per minute, by negative pressure",
       1164, "Bioreactors", "the volumetric aeration rate was 20 ml/min"),
    _c("parallelism", "parallel operation",
       "eight mini-scale chemostats operated in parallel", 1164, "Abstract",
       "The parallel operation of eight such mini-scale chemostats"),
    _c("dissolved_oxygen", "dissolved oxygen",
       "above 70% at all tested dilution rates with 1 g/L glucose", 1167,
       "Results", "solved oxygen concentrations above 70% at all tested dilution"),
    _c("od_dry_weight", "OD600 to dry-weight factor",
       "0.41 g (dry weight)/OD600, used to compute specific yields and rates",
       1165, "Analytical procedures and physiological parameters",
       "0.41 g [dry weight]"),
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
    "310 with pH-stat glucose feeding at 30 degC. Nanchen et al. use a "
    "non-recombinant MG1655 in a 10-mL mini-scale chemostat at 37 degC. The "
    "maintenance coefficient and maximal molar yield here are values for that "
    "chemostat and that medium; they are not transferred to the insulin process."
)
