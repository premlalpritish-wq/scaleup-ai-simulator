"""Provenance types: how a number in this package came to exist.

The integrity rule is the repository's, restated for this paper:

    A value either carries a provenance class, or it does not exist.

Two classes appear in this package and the difference between them is the
whole point of it:

    REPORTED  read out of the printed paper, at a stated printed page.
    DERIVED   computed by the one equation the paper prints, from declared
              inputs.

Nothing is assumed, nothing is digitised, and nothing is fitted. `unknown`
quantities hold `None` and are never coerced to 0.0 -- enforced in
`Quantity.__post_init__`, not by convention.

`Basis` is the axis that keeps a reported observation from being read as a
prediction: REPORTED is OBSERVED, DERIVED is COMPUTED, and no function in this
package moves a number from one class to the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from . import source
from .units import Dimension, dimension_of


class Provenance(Enum):
    """How a quantitative value came to exist. Exactly one per Quantity."""

    REPORTED = "reported"
    """Explicitly stated in the printed source, at a stated printed page."""

    DERIVED = "derived"
    """Computed by a registered, transparent equation from named inputs."""

    ASSUMED = "assumed"
    """Supplied by the caller or the implementer for a stated purpose.

    Not used by any record this package publishes. It exists so that a future
    caller cannot smuggle a guess in under `reported`.
    """

    UNKNOWN = "unknown"
    """Unavailable or not stated in the paper."""


class Basis(Enum):
    """Whether a value is an observed reference reading or a computed output."""

    OBSERVED = "observed_reference"
    COMPUTED = "computed"
    ASSUMED = "assumed_input"
    UNRESOLVED = "unresolved"


_BASIS_BY_PROVENANCE: Mapping[Provenance, Basis] = {
    Provenance.REPORTED: Basis.OBSERVED,
    Provenance.DERIVED: Basis.COMPUTED,
    Provenance.ASSUMED: Basis.ASSUMED,
    Provenance.UNKNOWN: Basis.UNRESOLVED,
}


class EvidenceError(ValueError):
    """Raised when an evidence reference is not internally consistent."""


@dataclass(frozen=True)
class EvidenceRef:
    """A pointer to the printed page that supports a value.

    For this article the printed page number and the 1-based PDF page number
    are the same integer, because the article is paginated 1-7 and each page
    carries a footer that states its own printed page. `__post_init__` checks
    the arithmetic; `tests/test_source_provenance.py` checks the footers
    themselves.
    """

    printed_page: int
    section: str | None = None
    quote: str | None = None
    source_id: str = source.SOURCE_ID

    def __post_init__(self) -> None:
        if self.source_id != source.SOURCE_ID:
            raise EvidenceError(
                f"evidence names source {self.source_id!r}; this package cites "
                f"only {source.SOURCE_ID!r}"
            )
        if not source.FIRST_PRINTED_PAGE <= self.printed_page <= source.PAGE_COUNT:
            raise EvidenceError(
                f"printed page {self.printed_page} is outside the article "
                f"({source.FIRST_PRINTED_PAGE}-{source.PAGE_COUNT})"
            )

    @property
    def pdf_page(self) -> int:
        """The 1-based PDF page, which equals the printed page here."""
        return self.printed_page

    @property
    def reference(self) -> str:
        return source.reference(self.printed_page, section=self.section)

    @property
    def citation(self) -> str:
        return source.citation_for(self.printed_page, section=self.section)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "printed_page": self.printed_page,
            "pdf_page": self.pdf_page,
            "section": self.section,
            "quote": self.quote,
            "reference": self.reference,
        }


@dataclass(frozen=True)
class Condition:
    """One stated condition a reported observation was obtained under."""

    label: str
    value: str
    evidence: EvidenceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True)
class Quantity:
    """A single typed number with provenance, units and evidence.

    Invariants enforced in `__post_init__`:

      * `unknown` holds no value and no range;
      * a numeric value carries a registered unit;
      * a `derived` value carries a calculation method and names its inputs;
      * a `reported` value carries at least one evidence reference.
    """

    quantity_id: str
    label: str
    provenance: Provenance
    value: float | None = None
    unit: str | None = None

    #: unit and wording exactly as printed, before normalisation
    original_unit: str | None = None
    original_text: str | None = None

    evidence: tuple[EvidenceRef, ...] = ()
    method: str | None = None
    inputs: tuple[str, ...] = ()
    notes: str = ""

    @property
    def basis(self) -> Basis:
        return _BASIS_BY_PROVENANCE[self.provenance]

    @property
    def is_observed(self) -> bool:
        return self.basis is Basis.OBSERVED

    @property
    def is_resolved(self) -> bool:
        return self.provenance is not Provenance.UNKNOWN

    @property
    def dimension(self) -> Dimension | None:
        return dimension_of(self.unit) if self.unit else None

    @property
    def printed_pages(self) -> tuple[int, ...]:
        return tuple(e.printed_page for e in self.evidence)

    def __post_init__(self) -> None:
        if self.provenance is Provenance.UNKNOWN and self.value is not None:
            raise ValueError(
                f"{self.quantity_id}: provenance is 'unknown' so value must be "
                f"None; refusing to fabricate a default"
            )
        if self.provenance is Provenance.DERIVED:
            if not self.method:
                raise ValueError(
                    f"{self.quantity_id}: provenance is 'derived' so a transparent "
                    f"calculation method is required"
                )
            if not self.inputs:
                raise ValueError(
                    f"{self.quantity_id}: provenance is 'derived' so its input "
                    f"quantities must be named"
                )
        if self.provenance is Provenance.REPORTED and not self.evidence:
            raise ValueError(
                f"{self.quantity_id}: provenance is 'reported' so it must cite "
                f"the printed page it was read from"
            )
        if self.value is not None and not self.unit:
            raise ValueError(f"{self.quantity_id}: a numeric quantity requires a unit")
        if self.value is not None and self.unit:
            dimension_of(self.unit)  # fail fast on an unregistered unit

    def display(self) -> str:
        if self.provenance is Provenance.UNKNOWN:
            return "unknown"
        return f"{self.value:g} {self.unit}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity_id": self.quantity_id,
            "label": self.label,
            "provenance": self.provenance.value,
            "basis": self.basis.value,
            "value": self.value,
            "unit": self.unit,
            "original_unit": self.original_unit,
            "original_text": self.original_text,
            "evidence": [e.to_dict() for e in self.evidence],
            "method": self.method,
            "inputs": list(self.inputs),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ReportedObservation:
    """A reported value together with the conditions it was measured under."""

    observation_id: str
    quantity: Quantity
    conditions: tuple[Condition, ...] = ()

    @property
    def value(self) -> float | None:
        return self.quantity.value

    @property
    def unit(self) -> str | None:
        return self.quantity.unit

    @property
    def printed_pages(self) -> tuple[int, ...]:
        return self.quantity.printed_pages

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "quantity": self.quantity.to_dict(),
            "conditions": [c.to_dict() for c in self.conditions],
        }


# --------------------------------------------------------------------------- #
# constructors
# --------------------------------------------------------------------------- #


def reported(
    quantity_id: str,
    label: str,
    value: float,
    unit: str,
    evidence: EvidenceRef | Iterable[EvidenceRef],
    *,
    original_text: str | None = None,
    original_unit: str | None = None,
    notes: str = "",
) -> Quantity:
    refs = (evidence,) if isinstance(evidence, EvidenceRef) else tuple(evidence)
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.REPORTED,
        value=value,
        unit=unit,
        original_unit=original_unit,
        original_text=original_text,
        evidence=refs,
        notes=notes,
    )


def derived(
    quantity_id: str,
    label: str,
    value: float,
    unit: str,
    method: str,
    inputs: tuple[str, ...],
    evidence: Iterable[EvidenceRef] = (),
    *,
    notes: str = "",
) -> Quantity:
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.DERIVED,
        value=value,
        unit=unit,
        method=method,
        inputs=inputs,
        evidence=tuple(evidence),
        notes=notes,
    )


def unknown(
    quantity_id: str,
    label: str,
    unit: str | None = None,
    *,
    notes: str = "",
) -> Quantity:
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.UNKNOWN,
        value=None,
        unit=unit,
        notes=notes,
    )