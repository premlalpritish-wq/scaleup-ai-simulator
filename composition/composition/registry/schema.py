"""Registry records.

The central idea is that *no field is just a value*. Every field on a
:class:`RegisteredModel` is a :class:`TrackedField` carrying three things: the
value, where the value's standing comes from, and the source it was read from.
That makes three states distinguishable rather than two:

``DECLARED``   the artefact states it. Read directly.
``DERIVED``    computed from declared data by a rule stated on the field.
``UNKNOWN``    the artefact does not state it. Explicitly, never a blank.

``UNKNOWN`` is not an error and not a gap to be filled later by inference. It is
the honest answer, and it is the reason a registry can be trusted: the fields
that are missing are visible as missing.

Registration is bookkeeping. A registered model has been *identified*, not
*endorsed* -- see :attr:`RegisteredModel.scientific_status`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class Origin(Enum):
    """Where a field's standing comes from."""

    DECLARED = "declared"
    """Read verbatim from the model artefact or its manifest."""

    DERIVED = "derived"
    """Computed from declared data by a rule recorded on the field."""

    UNKNOWN = "unknown"
    """Not stated by the artefact. Never inferred, never defaulted."""


@dataclass(frozen=True)
class TrackedField:
    """A value plus how we know it."""

    value: Any
    origin: Origin
    #: What this field was read from, or the rule that produced it. Empty only
    #: when the origin is UNKNOWN.
    basis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "origin": self.origin.value, "basis": self.basis}

    @property
    def is_known(self) -> bool:
        return self.origin is not Origin.UNKNOWN


def unknown(basis: str = "") -> TrackedField:
    """An explicitly absent field. ``basis`` should say why it is absent."""
    return TrackedField(None, Origin.UNKNOWN, basis)


def declared(value: Any, basis: str) -> TrackedField:
    return TrackedField(value, Origin.DECLARED, basis)


def derived(value: Any, rule: str) -> TrackedField:
    return TrackedField(value, Origin.DERIVED, rule)


# --------------------------------------------------------------------------- #
# Artefacts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ArtefactDigest:
    """A hash of one file, and a statement of what the hash covers.

    ``covers`` is not decoration. A digest is only meaningful next to a
    definition of its scope, because "SHA-256 abc123" could reasonably mean the
    file, the package, or the model plus its data fixtures. The scope is stated
    on every digest so a reader never has to guess.
    """

    path: str
    algorithm: str
    digest: str
    byte_length: int
    covers: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "algorithm": self.algorithm,
            "digest": self.digest,
            "byte_length": self.byte_length,
            "covers": self.covers,
        }


# --------------------------------------------------------------------------- #
# Ports and conditions
# --------------------------------------------------------------------------- #


class PortDependence(Enum):
    FIXED = "fixed"
    """The model declares the same ports regardless of how it is configured."""

    INSTANCE = "instance_parameterised"
    """Ports depend on the instance's declared system; there is no fixed set."""


@dataclass(frozen=True)
class PortRecord:
    port_id: str
    direction: str
    quantity: str
    unit: str
    required: bool
    role: str
    location: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "direction": self.direction,
            "quantity": self.quantity,
            "unit": self.unit,
            "required": self.required,
            "role": self.role,
            "location": self.location,
        }


@dataclass(frozen=True)
class DeclaredCondition:
    """Something the model says it needs in order to be able to do its job.

    Taken from the artefact's own declaration of what it cannot do. This is the
    model's statement, not ours.
    """

    condition_id: str
    label: str
    why_needed: str
    why_not_implemented: str
    missing_inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "label": self.label,
            "why_needed": self.why_needed,
            "why_not_implemented": self.why_not_implemented,
            "missing_inputs": list(self.missing_inputs),
        }


# --------------------------------------------------------------------------- #
# Integrity
# --------------------------------------------------------------------------- #


class IssueKind(Enum):
    DUPLICATE_ID = "duplicate_model_id"
    MISSING_ARTEFACT = "missing_artefact"
    AMBIGUOUS_VERSION = "ambiguous_version"
    UNREGISTERED_REFERENCE = "reference_to_unregistered_model"
    REGISTRATION_FAILED = "registration_failed"


SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class RegistrationIssue:
    """A problem found while registering. Reported, never silently repaired."""

    kind: IssueKind
    subject: str
    detail: str
    severity: str = SEVERITY_ERROR

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "subject": self.subject,
            "detail": self.detail,
            "severity": self.severity,
        }


# --------------------------------------------------------------------------- #
# The registration
# --------------------------------------------------------------------------- #

#: Stated on every registration so that "it is in the registry" is never read as
#: "it is correct".
SCIENTIFIC_STATUS = (
    "registered_only",
    "Registration records that a specification artefact exists, is identified, "
    "and can be located and hashed. It does NOT establish that the model is "
    "correct, independently supported by evidence, or executable. None of "
    "those claims is made or implied by appearing here.",
)


@dataclass(frozen=True)
class RegisteredModel:
    model_id: str
    model_version: str
    title: TrackedField
    source_paper: TrackedField
    doi: TrackedField
    specification_path: TrackedField
    artefact_digests: tuple[ArtefactDigest, ...]
    package_digest: TrackedField
    ports: tuple[PortRecord, ...]
    port_dependence: PortDependence
    port_counts: Mapping[str, int]
    variables: TrackedField
    units: TrackedField
    required_conditions: tuple[DeclaredCondition, ...]
    assumptions: TrackedField
    capabilities: TrackedField
    adapter: TrackedField
    scientific_status: Mapping[str, str] = field(
        default_factory=lambda: {
            "state": SCIENTIFIC_STATUS[0],
            "means": SCIENTIFIC_STATUS[1],
            "does_not_mean": (
                "Correct, validated, independently supported, or executable. "
                "A model can be registered and still be wrong."
            ),
        }
    )
    unknown_fields: tuple[str, ...] = ()

    @property
    def reference(self) -> str:
        """The unambiguous way to name this exact model version."""
        return "%s@%s" % (self.model_id, self.model_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "reference": self.reference,
            "title": self.title.to_dict(),
            "source_paper": self.source_paper.to_dict(),
            "doi": self.doi.to_dict(),
            "specification_path": self.specification_path.to_dict(),
            "artefact_digests": [a.to_dict() for a in self.artefact_digests],
            "package_digest": self.package_digest.to_dict(),
            "ports": {
                "dependence": self.port_dependence.value,
                "counts": dict(self.port_counts),
                "records": [p.to_dict() for p in self.ports],
            },
            "variables": self.variables.to_dict(),
            "units": self.units.to_dict(),
            "required_conditions": [c.to_dict() for c in self.required_conditions],
            "assumptions": self.assumptions.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "adapter": self.adapter.to_dict(),
            "scientific_status": dict(self.scientific_status),
            "unknown_fields": list(self.unknown_fields),
        }


def known_keys(model: RegisteredModel) -> tuple[str, ...]:
    return (
        "title", "source_paper", "doi", "specification_path", "variables",
        "units", "assumptions", "capabilities", "package_digest",
    )


def collect_unknowns(model: RegisteredModel) -> tuple[str, ...]:
    """Every field on the model that the artefact does not state."""
    out = [k for k in known_keys(model) if not getattr(model, k).is_known]
    if model.port_dependence is PortDependence.INSTANCE:
        out.append("ports")
    return tuple(sorted(out))


def summarise_variables(ports: Sequence[PortRecord]) -> dict[str, list[str]]:
    """Quantity -> units seen for it, from the declared ports."""
    out: dict[str, set[str]] = {}
    for p in ports:
        out.setdefault(p.quantity, set()).add(p.unit)
    return {q: sorted(u) for q, u in sorted(out.items())}