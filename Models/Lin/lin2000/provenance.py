"""Provenance types: how a number in this package came to exist.

The integrity rule is the repository's, restated for this paper:

    A value either carries a provenance class, or it does not exist.

Three classes appear, and the difference between them is the whole point:

    REPORTED  read out of the printed paper, at a stated printed page;
    DERIVED   computed by an equation the paper prints, from named inputs;
    UNKNOWN   unavailable or not stated, and never coerced to 0.0.

`Basis` is the axis that keeps a reported observation from being read as a
prediction: REPORTED is OBSERVED, DERIVED is COMPUTED, and no function here
moves a number from one class to the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from . import source
from .units import dimension_of


class Provenance(Enum):
    """How a quantitative value came to exist. Exactly one per Quantity."""

    REPORTED = "reported"
    DERIVED = "derived"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"


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
    """A pointer to the printed page that supports a value."""

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
        first, last = source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE
        if not first <= self.printed_page <= last:
            raise EvidenceError(
                f"printed page {self.printed_page} is outside the article "
                f"({first}-{last})"
            )

    @property
    def pdf_page(self) -> int:
        return source.pdf_page(self.printed_page)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "printed_page": self.printed_page,
            "pdf_page": self.pdf_page,
            "section": self.section,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class Quantity:
    """A value, its provenance, its unit, and the page that supports it."""

    quantity_id: str
    label: str
    provenance: Provenance
    value: float | None
    unit: str | None = None
    original_unit: str | None = None
    original_text: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    method: str | None = None
    inputs: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if self.provenance is Provenance.UNKNOWN:
            if self.value is not None:
                raise EvidenceError(
                    f"{self.quantity_id}: an unknown quantity must hold None, not "
                    f"{self.value!r}"
                )
            return
        if self.value is None:
            raise EvidenceError(f"{self.quantity_id}: a known quantity requires a value")
        if self.unit is None:
            raise EvidenceError(f"{self.quantity_id}: a numeric quantity requires a unit")
        dimension_of(self.unit)  # fail fast on an unregistered unit

    @property
    def basis(self) -> Basis:
        return _BASIS_BY_PROVENANCE[self.provenance]

    @property
    def printed_pages(self) -> tuple[int, ...]:
        return tuple(e.printed_page for e in self.evidence)

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
