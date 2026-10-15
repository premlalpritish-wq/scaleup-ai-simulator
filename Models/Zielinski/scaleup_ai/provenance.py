"""ScaleUp AI core: provenance, evidence and quantity types.

The central integrity rule of this package:

    A value either carries a provenance class, or it does not exist.

`unknown` quantities hold `None`. They are never coerced to 0.0, never given a
fabricated default, and never replaced by a neighbouring quantity. This is
enforced structurally in `Quantity.__post_init__`, not by convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .units import Dimension, dimension_of, is_convertible


class Provenance(Enum):
    """How a quantitative value came to exist. Exactly one per Quantity."""

    REPORTED = "reported"
    """Explicitly stated in the source publication."""

    DERIVED = "derived"
    """Calculated from reported/derived inputs by a transparent registered equation."""

    DIGITIZED = "digitized"
    """Estimated by reading a published figure (e.g. marker positions in a plot)."""

    ASSUMED = "assumed"
    """Supplied by the implementer for a specific, documented purpose."""

    UNKNOWN = "unknown"
    """Unavailable or insufficiently specified in the source."""


class Basis(Enum):
    """Whether a value is an observed reference reading or an engine output.

    This is the axis that stops a replayed paper from masquerading as a
    simulation. Reported and digitized quantities are OBSERVED; anything the
    engine computed is COMPUTED.
    """

    OBSERVED = "observed_reference"
    ASSUMED = "assumed_input"
    COMPUTED = "computed"
    UNRESOLVED = "unresolved"


_BASIS_BY_PROVENANCE: Mapping[Provenance, Basis] = {
    Provenance.REPORTED: Basis.OBSERVED,
    Provenance.DIGITIZED: Basis.OBSERVED,
    Provenance.DERIVED: Basis.COMPUTED,
    Provenance.ASSUMED: Basis.ASSUMED,
    Provenance.UNKNOWN: Basis.UNRESOLVED,
}


class ValidationStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvidenceRef:
    """A pointer back to the exact place in the source that supports a value."""

    source_id: str
    pdf_page: int
    printed_page: int
    section: str | None = None
    figure: str | None = None
    quote: str | None = None

    def __post_init__(self) -> None:
        if self.pdf_page != self.printed_page - 62:
            raise ValueError(
                f"printed page {self.printed_page} is not consistent with pdf page "
                f"{self.pdf_page} for Zielinski et al. 2019 (63-69)"
            )

    @property
    def citation(self) -> str:
        bits = [f"p.{self.printed_page}"]
        if self.figure:
            bits.append(self.figure)
        if self.section:
            bits.append(self.section)
        return ", ".join(bits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "pdf_page": self.pdf_page,
            "printed_page": self.printed_page,
            "section": self.section,
            "figure": self.figure,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class Assumption:
    """An implementer-supplied bridge across a gap the paper does not close.

    Assumptions exist to be audited. Each one states what was assumed, why, and
    which quantities become conditional on it.
    """

    assumption_id: str
    statement: str
    rationale: str
    affects: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "statement": self.statement,
            "rationale": self.rationale,
            "affects": list(self.affects),
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class MissingParameter:
    """A parameter the source does not provide, and what that blocks."""

    parameter_id: str
    description: str
    reason: str
    blocks: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "description": self.description,
            "reason": self.reason,
            "blocks": list(self.blocks),
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class Uncertainty:
    """An explicit, bounded statement about how wrong a value may be."""

    kind: str
    lo: float
    hi: float
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "lo": self.lo, "hi": self.hi, "basis": self.basis}


@dataclass(frozen=True)
class SourceExpression:
    """A formula exactly as printed in the paper.

    Kept verbatim with its original variables. It is *not* executed unless it is
    registered as unambiguous -- see `equations.py`.
    """

    expression_id: str
    label: str
    expression_text: str
    variable_definitions: Mapping[str, str]
    source_unit: str
    expected_output_unit: str
    executable: bool
    ambiguity: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression_id": self.expression_id,
            "label": self.label,
            "expression_text": self.expression_text,
            "variable_definitions": dict(self.variable_definitions),
            "source_unit": self.source_unit,
            "expected_output_unit": self.expected_output_unit,
            "executable": self.executable,
            "ambiguity": self.ambiguity,
            "evidence": [e.to_dict() for e in self.evidence],
        }


# --------------------------------------------------------------------------- #
# Quantity
# --------------------------------------------------------------------------- #


class QuantityError(ValueError):
    """Raised when a Quantity violates a structural integrity rule."""


@dataclass
class Quantity:
    """A single typed number with provenance, units and evidence.

    Invariants enforced in __post_init__:
      * provenance == UNKNOWN  =>  no value and no range.
      * a value and a range are mutually exclusive (a range is never silently
        collapsed to a point value).
      * numeric values carry a registered unit.
      * DERIVED values carry a calculation method and name their inputs.
    """

    quantity_id: str
    label: str
    provenance: Provenance
    value: float | None = None
    unit: str | None = None
    value_range: tuple[float, float] | None = None

    #: unit/quantity exactly as printed in the paper, before normalization
    original_unit: str | None = None
    original_text: str | None = None

    evidence: tuple[EvidenceRef, ...] = ()
    method: str | None = None
    inputs: tuple[str, ...] = ()
    uncertainty: Uncertainty | None = None
    notes: str = ""

    # ---- provenance bookkeeping -------------------------------------------
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

    def __post_init__(self) -> None:
        if self.value is not None and self.value_range is not None:
            raise QuantityError(
                f"{self.quantity_id}: a quantity holds either a point value or a "
                f"range, never both"
            )
        if self.provenance is Provenance.UNKNOWN:
            if self.value is not None or self.value_range is not None:
                raise QuantityError(
                    f"{self.quantity_id}: provenance is 'unknown' so value must be "
                    f"None; refusing to fabricate a default"
                )
        if self.provenance is Provenance.DERIVED:
            if not self.method:
                raise QuantityError(
                    f"{self.quantity_id}: provenance is 'derived' so a transparent "
                    f"calculation method is required"
                )
            if not self.inputs:
                raise QuantityError(
                    f"{self.quantity_id}: provenance is 'derived' so its input "
                    f"quantities must be named"
                )
        if (self.value is not None or self.value_range is not None) and not self.unit:
            raise QuantityError(
                f"{self.quantity_id}: a numeric quantity requires a unit"
            )
        if self.value is not None and self.unit:
            # fail fast on unregistered units
            dimension_of(self.unit)

    # ---- accessors ---------------------------------------------------------
    @property
    def point_value(self) -> float | None:
        """The point value, or None if ranged or unknown."""
        return self.value

    def range_midpoint(self) -> float | None:
        if self.value_range is not None:
            lo, hi = self.value_range
            return (lo + hi) / 2.0
        return self.value

    def unit_convertible_to(self, target: str) -> bool:
        return bool(self.unit) and is_convertible(self.unit, target)

    def display(self) -> str:
        if self.provenance is Provenance.UNKNOWN:
            return "unknown"
        if self.value_range is not None:
            lo, hi = self.value_range
            return f"{lo:g}-{hi:g} {self.unit}".strip()
        return f"{self.value:g} {self.unit}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity_id": self.quantity_id,
            "label": self.label,
            "provenance": self.provenance.value,
            "basis": self.basis.value,
            "value": self.value,
            "unit": self.unit,
            "value_range": list(self.value_range) if self.value_range else None,
            "original_unit": self.original_unit,
            "original_text": self.original_text,
            "evidence": [e.to_dict() for e in self.evidence],
            "method": self.method,
            "inputs": list(self.inputs),
            "uncertainty": self.uncertainty.to_dict() if self.uncertainty else None,
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
    value_range: tuple[float, float] | None = None,
    uncertainty: Uncertainty | None = None,
    notes: str = "",
) -> Quantity:
    ev = (evidence,) if isinstance(evidence, EvidenceRef) else tuple(evidence)
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.REPORTED,
        value=value,
        value_range=value_range,
        unit=unit,
        original_unit=original_unit,
        original_text=original_text,
        evidence=ev,
        uncertainty=uncertainty,
        notes=notes,
    )


def digitized(
    quantity_id: str,
    label: str,
    value: float,
    unit: str,
    evidence: EvidenceRef | Iterable[EvidenceRef],
    *,
    uncertainty: Uncertainty,
    method: str,
    original_text: str | None = None,
    notes: str = "",
) -> Quantity:
    ev = (evidence,) if isinstance(evidence, EvidenceRef) else tuple(evidence)
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.DIGITIZED,
        value=value,
        unit=unit,
        original_text=original_text,
        evidence=ev,
        uncertainty=uncertainty,
        method=method,
        inputs=("figure:marker-positions",),
        notes=notes,
    )


def derived(
    quantity_id: str,
    label: str,
    value: float,
    unit: str,
    method: str,
    inputs: Sequence[str],
    evidence: Sequence[EvidenceRef] = (),
    *,
    uncertainty: Uncertainty | None = None,
    notes: str = "",
) -> Quantity:
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.DERIVED,
        value=value,
        unit=unit,
        method=method,
        inputs=tuple(inputs),
        evidence=tuple(evidence),
        uncertainty=uncertainty,
        notes=notes,
    )


def assumed(
    quantity_id: str,
    label: str,
    value: float,
    unit: str,
    assumption: Assumption,
    *,
    notes: str = "",
) -> Quantity:
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.ASSUMED,
        value=value,
        unit=unit,
        method=assumption.statement,
        evidence=assumption.evidence,
        notes=notes,
    )


def unknown(
    quantity_id: str,
    label: str,
    unit: str | None = None,
    missing: MissingParameter | None = None,
    *,
    notes: str = "",
) -> Quantity:
    return Quantity(
        quantity_id=quantity_id,
        label=label,
        provenance=Provenance.UNKNOWN,
        value=None,
        unit=unit,
        evidence=missing.evidence if missing else (),
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# diagnostics
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ValidationMessage:
    severity: Severity
    code: str
    message: str
    where: str
    evidence: tuple[EvidenceRef, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "where": self.where,
            "evidence": [e.to_dict() for e in self.evidence],
        }