"""Versioned composition contracts.

Every type here is part of the public interface between the composition engine
and everything that drives it: the JSON graph files, the Godot editor, the JSON
runner, and the tests.  ``CONTRACT_VERSION`` is stamped onto every manifest,
graph, plan and result, and a mismatch is a load-time error rather than a
best-effort parse.

The central design decision is :class:`ValueState`.

Both existing models are emphatic that "absent" is not "zero": Zielinski's
``Quantity.__post_init__`` raises if an ``unknown`` quantity carries a value,
and Morris makes ``Unknown`` a separate type from ``Quantity`` precisely so
that a missing measurement cannot be written as a measured zero.  A composition
layer that flattened those distinctions would undo both.  So a value here is
one of six states, and only two of them carry a number:

===================  =========  =============================================
``ValueState``       has value  meaning
===================  =========  =============================================
``NUMBER``           yes        a measured or computed number
``ZERO``             yes        a number that was **stated** as zero
``RANGE``            no         reported as an interval, not collapsed
``NOT_REPORTED``     no         the model does not report this at all
``UNRESOLVED``       no         the model ran and could not determine it
``UNKNOWN``          no         declared unavailable in the source
===================  =========  =============================================

``ZERO`` is separated from ``NUMBER`` even though both hold ``0.0``, because a
stated zero is evidence and a computed zero is not, and a reader of a results
panel has to be able to tell which they are looking at.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .diagnostics import ModelDiagnostic, Origin, Severity
from .quantities import CONTRACT_VERSION, Quantity, convert

__all__ = [
    "CONTRACT_VERSION",
    "PortDirection",
    "TemporalBasis",
    "ProvenanceRequirement",
    "ValueState",
    "ValueProvenance",
    "PortDefinition",
    "ProvenanceRecord",
    "ModelValue",
    "ModelInput",
    "ModelOutput",
    "ModelInstance",
    "ModelManifest",
    "PortRef",
    "Connection",
    "CompositionGraph",
    "ExecutionStep",
    "ExecutionPlan",
    "ModelRunResult",
    "ResidualReport",
    "CompositionResult",
    "RunStatus",
    "ContractError",
    "load_graph",
    "graph_to_dict",
]


class ContractError(ValueError):
    """Raised when a document violates the contract."""


# --------------------------------------------------------------------------- #
# ports
# --------------------------------------------------------------------------- #


class PortDirection(Enum):
    INPUT = "input"
    OUTPUT = "output"

    @property
    def opposite(self) -> "PortDirection":
        return PortDirection.OUTPUT if self is PortDirection.INPUT else PortDirection.INPUT


class TemporalBasis(Enum):
    """When a value holds, which is a separate question from its quantity.

    Morris deliberately has no ``TIME`` dimension: a time basis is carried by a
    flow's unit (``kg/h``) and recorded on the stream.  That is represented
    here by ``RATE``.  Zielinski's masses are single-batch inventories
    (``INVENTORY``), and its OD600 markers are points on a trajectory
    (``TRAJECTORY_POINT``).
    """

    #: a single reference value: 224 g of wet biomass from one batch
    INVENTORY = "inventory"
    #: a rate: the "/h" in kg/h is the time basis
    RATE = "rate"
    #: a volume or amount held at an instant
    INSTANT = "instant"
    #: one marker on a measured trajectory
    TRAJECTORY_POINT = "trajectory_point"
    #: a duration
    DURATION = "duration"
    #: not time-dependent (pH, a unitless ratio, a conductivity reading)
    NOT_APPLICABLE = "not_applicable"


class ProvenanceRequirement(Enum):
    """What a resolved value on this port must be able to show.

    Mirrors the rules both models already enforce, restated at the port so the
    requirement is visible before anything runs.
    """

    #: any state; typically an INPUT that is optional
    NONE = "none"
    #: the value must carry evidence, a source_ref, a method, or be a declared
    #: assumption -- i.e. it must be possible to say where it came from
    EXPLAINED = "explained"
    #: the value must additionally be traceable to a source document or figure
    CITED = "cited"


@dataclass(frozen=True)
class PortDefinition:
    """One typed port on a model instance.

    A port is the *only* thing two models may exchange.  It states:

    * ``quantity`` -- what the number is (the compatibility key);
    * ``unit`` -- how it is printed, always resolved *as a unit of quantity*;
    * ``component`` -- which conserved entity, where one applies;
    * ``temporal_basis`` -- inventory, rate, instant, trajectory point, duration;
    * ``required`` -- whether the model cannot run without it;
    * ``provenance_requirement`` -- how far the value must be traceable.
    """

    port_id: str
    direction: PortDirection
    quantity: Quantity
    unit: str
    label: str = ""
    component: str | None = None
    #: every component present in the value.  Empty means "no component
    #: identity at all", which is different from "one component, unnamed".
    components: tuple[str, ...] = ()
    temporal_basis: TemporalBasis = TemporalBasis.NOT_APPLICABLE
    required: bool = False
    provenance_requirement: ProvenanceRequirement = ProvenanceRequirement.EXPLAINED
    #: a total that has to be attributable to named components before it may
    #: enter a component-declared control volume (CG-08)
    attribution_required: bool = False
    #: the model will determine this value rather than read it
    solvable: bool = False
    #: the value cannot be represented (e.g. an unregistered unit); the port is
    #: still declared so the gap is visible and countable
    unavailable_reason: str = ""
    description: str = ""
    #: free-form, carried through to the inspector
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.port_id:
            raise ContractError("a PortDefinition must have a port_id")
        if not self.unit and not self.unavailable_reason:
            raise ContractError(
                f"{self.port_id}: a port must declare a unit, or say why it cannot"
            )
        if self.component is not None and self.components and (
            self.component not in self.components
        ):
            raise ContractError(
                f"{self.port_id}: component {self.component!r} is not in components "
                f"{list(self.components)}"
            )

    @property
    def has_component_identity(self) -> bool:
        return bool(self.component) or bool(self.components)

    @property
    def is_usable(self) -> bool:
        return not self.unavailable_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "direction": self.direction.value,
            "quantity": self.quantity.value,
            "unit": self.unit,
            "label": self.label,
            "component": self.component,
            "components": list(self.components),
            "temporal_basis": self.temporal_basis.value,
            "required": self.required,
            "provenance_requirement": self.provenance_requirement.value,
            "attribution_required": self.attribution_required,
            "solvable": self.solvable,
            "unavailable_reason": self.unavailable_reason,
            "has_component_identity": self.has_component_identity,
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortDefinition":
        try:
            return cls(
                port_id=payload["port_id"],
                direction=PortDirection(payload["direction"]),
                quantity=Quantity(payload["quantity"]),
                unit=payload.get("unit", ""),
                label=payload.get("label", ""),
                component=payload.get("component"),
                components=tuple(payload.get("components", ()) or ()),
                temporal_basis=TemporalBasis(
                    payload.get("temporal_basis", "not_applicable")
                ),
                required=bool(payload.get("required", False)),
                provenance_requirement=ProvenanceRequirement(
                    payload.get("provenance_requirement", "explained")
                ),
                attribution_required=bool(payload.get("attribution_required", False)),
                solvable=bool(payload.get("solvable", False)),
                unavailable_reason=payload.get("unavailable_reason", ""),
                description=payload.get("description", ""),
                metadata=dict(payload.get("metadata", {})),
            )
        except KeyError as exc:
            raise ContractError(
                f"port definition is missing required field {exc.args[0]!r}"
            ) from None


# --------------------------------------------------------------------------- #
# values and provenance
# --------------------------------------------------------------------------- #


class ValueState(Enum):
    """The six ways a port can be non-numeric. See the module docstring."""

    #: a measured or computed number
    NUMBER = "number"
    #: a number the source *states* as zero.  Kept distinct from NUMBER.
    ZERO = "zero"
    #: reported as an interval; deliberately not collapsed to a point value
    RANGE = "range"
    #: the model does not report this quantity at all
    NOT_REPORTED = "not_reported"
    #: the model ran and could not determine it
    UNRESOLVED = "unresolved"
    #: declared unavailable in the source, with a recorded reason
    UNKNOWN = "unknown"

    @property
    def has_number(self) -> bool:
        return self in (ValueState.NUMBER, ValueState.ZERO)


class ValueProvenance(Enum):
    """How a value came to exist, at composition level.

    The first four mirror Zielinski's classes; Morris has three of them.
    ``TRANSFERRED`` and ``SOLVED`` are new, and both *retain* the upstream
    class in the provenance chain rather than replacing it.
    """

    REPORTED = "reported"
    DIGITIZED = "digitized"
    DERIVED = "derived"
    ASSUMED = "assumed"
    #: passed through a connection from an upstream port
    TRANSFERRED = "transferred"
    #: determined by the Morris solver
    SOLVED = "solved"
    #: the model reported it and the composition layer closed the interval --
    #: never used in v0.1, and structurally impossible, see the audit
    COLLAPSED = "collapsed"
    UNKNOWN = "unknown"

    @property
    def is_observed(self) -> bool:
        return self in (ValueProvenance.REPORTED, ValueProvenance.DIGITIZED)


@dataclass(frozen=True)
class ProvenanceRecord:
    """One hop in a value's history. A value's history is a tuple of these.

    This is what makes CG-12 answerable: to display why a number is what it is,
    walk the tuple backwards from the value, through each connection, to the
    model that produced the first one.
    """

    kind: str
    """``source`` | ``transfer`` | ``derivation`` | ``assumption`` | ``gap``"""

    producer_model: str
    producer_version: str
    where: str
    detail: str = ""
    connection_id: str | None = None
    source_port: str | None = None
    target_port: str | None = None
    method: str | None = None
    inputs: tuple[str, ...] = ()
    source_ref: str | None = None
    conversion: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "producer_model": self.producer_model,
            "producer_version": self.producer_version,
            "where": self.where,
            "detail": self.detail,
            "connection_id": self.connection_id,
            "source_port": self.source_port,
            "target_port": self.target_port,
            "method": self.method,
            "inputs": list(self.inputs),
            "source_ref": self.source_ref,
            "conversion": dict(self.conversion) if self.conversion else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProvenanceRecord":
        return cls(
            kind=payload["kind"],
            producer_model=payload["producer_model"],
            producer_version=payload["producer_version"],
            where=payload["where"],
            detail=payload.get("detail", ""),
            connection_id=payload.get("connection_id"),
            source_port=payload.get("source_port"),
            target_port=payload.get("target_port"),
            method=payload.get("method"),
            inputs=tuple(payload.get("inputs", ()) or ()),
            source_ref=payload.get("source_ref"),
            conversion=payload.get("conversion"),
        )


@dataclass(frozen=True)
class ModelValue:
    """A typed value on a port.

    Invariants enforced in ``__post_init__``:

    * only ``NUMBER`` and ``ZERO`` may carry a number;
    * only those two states may carry a value range;
    * a number requires a unit;
    * ``ZERO`` must actually be zero -- the state exists to mark a *stated*
      zero, so a non-zero value wearing the label is a bug.
    """

    state: ValueState
    quantity: Quantity
    unit: str = ""
    value: float | None = None
    value_range: tuple[float, float] | None = None
    lower: float | None = None
    upper: float | None = None
    provenance: ValueProvenance = ValueProvenance.UNKNOWN
    components: tuple[str, ...] = ()
    reason: str = ""
    source_ref: str | None = None
    method: str | None = None
    chain: tuple[ProvenanceRecord, ...] = ()
    conversion: Mapping[str, Any] | None = None
    #: free-form annotations carried through verbatim -- ``determination``,
    #: an uncertainty half-width, a mass fraction.  Never consulted by the
    #: engine; published so a reader can see it.
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state.has_number and self.value is None:
            raise ContractError(
                f"state {self.state.value!r} requires a number"
            )
        if not self.state.has_number and self.value is not None:
            raise ContractError(
                f"state {self.state.value!r} must not carry a number: the six value "
                f"states exist so that 'absent' can never be written as 'zero'"
            )
        if self.state is ValueState.ZERO and self.value != 0.0:
            raise ContractError(
                f"state 'zero' must carry 0.0, got {self.value!r}"
            )
        if self.state.has_number and not self.unit:
            raise ContractError(f"a numeric value requires a unit")
        if self.value_range and self.state is not ValueState.RANGE:
            raise ContractError(
                f"only state 'range' carries an interval, but "
                f"{self.state.value!r} has one. A range is never collapsed to a "
                f"point value."
            )
        if self.state is ValueState.RANGE and not self.value_range:
            raise ContractError("state 'range' requires a (lo, hi) interval")

    # -- constructors --------------------------------------------------------

    @classmethod
    def number(
        cls,
        value: float,
        *,
        quantity: Quantity,
        unit: str,
        provenance: ValueProvenance,
        components: Sequence[str] = (),
        source_ref: str | None = None,
        method: str | None = None,
        chain: Sequence[ProvenanceRecord] = (),
        reason: str = "",
        extra: Mapping[str, Any] | None = None,
    ) -> "ModelValue":
        """Build a numeric value, routing an exact zero to ``ZERO``.

        The zero is kept as a *stated* zero rather than folded into NUMBER,
        because a reported "0 mg/L glucose" and a computed "0" are different
        facts and the results panel has to be able to say which it is showing.
        """
        state = ValueState.ZERO if value == 0.0 else ValueState.NUMBER
        return cls(
            state=state,
            quantity=quantity,
            unit=unit,
            value=value,
            provenance=provenance,
            components=tuple(components),
            source_ref=source_ref,
            method=method,
            chain=tuple(chain),
            reason=reason,
            extra=dict(extra) if extra else {},
        )

    @classmethod
    def unavailable(
        cls,
        state: ValueState,
        *,
        quantity: Quantity,
        reason: str,
        unit: str = "",
        value_range: tuple[float, float] | None = None,
        components: Sequence[str] = (),
        source_ref: str | None = None,
        chain: Sequence[ProvenanceRecord] = (),
        extra: Mapping[str, Any] | None = None,
    ) -> "ModelValue":
        if state.has_number:
            raise ContractError("unavailable() takes a non-numeric state")
        return cls(
            state=state,
            quantity=quantity,
            unit=unit,
            value_range=value_range,
            provenance=ValueProvenance.UNKNOWN,
            components=tuple(components),
            reason=reason,
            source_ref=source_ref,
            chain=tuple(chain),
            extra=dict(extra) if extra else {},
        )

    # -- queries -------------------------------------------------------------

    @property
    def is_resolved(self) -> bool:
        return self.state.has_number

    @property
    def display(self) -> str:
        if self.state.has_number:
            return f"{self.value:g} {self.unit}".strip()
        if self.state is ValueState.RANGE and self.value_range:
            lo, hi = self.value_range
            return f"{lo:g}-{hi:g} {self.unit}".strip()
        return self.state.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "is_resolved": self.is_resolved,
            "quantity": self.quantity.value,
            "unit": self.unit,
            "value": self.value,
            "value_range": list(self.value_range) if self.value_range else None,
            "provenance": self.provenance.value,
            "components": list(self.components),
            "reason": self.reason,
            "source_ref": self.source_ref,
            "method": self.method,
            "display": self.display,
            "conversion": dict(self.conversion) if self.conversion else None,
            "extra": dict(self.extra),
            "provenance_chain": [record.to_dict() for record in self.chain],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelValue":
        vr = payload.get("value_range")
        return cls(
            state=ValueState(payload["state"]),
            quantity=Quantity(payload["quantity"]),
            unit=payload.get("unit", ""),
            value=payload.get("value"),
            value_range=(float(vr[0]), float(vr[1])) if vr else None,
            provenance=ValueProvenance(payload.get("provenance", "unknown")),
            components=tuple(payload.get("components", ()) or ()),
            reason=payload.get("reason", ""),
            source_ref=payload.get("source_ref"),
            method=payload.get("method"),
            chain=tuple(
                ProvenanceRecord.from_dict(r)
                for r in payload.get("provenance_chain", ())
            ),
            conversion=payload.get("conversion"),
            extra=dict(payload.get("extra", {})),
        )


# --------------------------------------------------------------------------- #
# manifests
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModelManifest:
    """What a model declares about itself: its identity, ports and capabilities.

    A model that cannot declare this cannot be composed.  In particular
    ``reaction_terms`` and ``conversion_models`` are not decoration: they are the
    two places where a model says what it *cannot* do, and the composition layer
    reads them to refuse a connection rather than to make one (CG-09, CG-03).
    """

    model_id: str
    model_version: str
    title: str
    adapter: str
    contract_version: str = CONTRACT_VERSION
    source_ref: str = ""
    summary: str = ""
    ports: tuple[PortDefinition, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    #: named parameter blocks shown in the inspector, e.g. control-volume modes
    parameter_sections: Mapping[str, Any] = field(default_factory=dict)
    #: things the model can do
    capabilities: tuple[str, ...] = ()
    #: things the model explicitly cannot do, each with a reason
    unsupported_capabilities: Mapping[str, str] = field(default_factory=dict)
    #: physics this model represents across a boundary. Morris: none.
    reaction_terms: tuple[str, ...] = ()
    #: unit conversions this model authorises. A connection may not perform a
    #: conversion that is neither here nor a same-quantity unit change.
    conversion_models: tuple[str, ...] = ()
    #: non-reacting by construction (Morris Chapter 4)
    non_reacting_only: bool = False
    assumptions: tuple[Mapping[str, Any], ...] = ()
    missing_information: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[ModelDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ContractError("a ModelManifest must have a model_id")
        seen: set[str] = set()
        for port in self.ports:
            if port.port_id in seen:
                raise ContractError(
                    f"{self.model_id}: duplicate port id {port.port_id!r}"
                )
            seen.add(port.port_id)

    def port(self, port_id: str) -> PortDefinition:
        for port in self.ports:
            if port.port_id == port_id:
                return port
        known = sorted(p.port_id for p in self.ports)
        raise KeyError(
            f"{self.model_id}: no port {port_id!r}. Known ports: {known[:12]}"
            f"{' ...' if len(known) > 12 else ''}"
        )

    def ports_by_direction(self, direction: PortDirection) -> tuple[PortDefinition, ...]:
        return tuple(p for p in self.ports if p.direction is direction)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "title": self.title,
            "summary": self.summary,
            "adapter": self.adapter,
            "source_ref": self.source_ref,
            "ports": [p.to_dict() for p in self.ports],
            "parameters": dict(self.parameters),
            "parameter_sections": dict(self.parameter_sections),
            "capabilities": list(self.capabilities),
            "unsupported_capabilities": dict(self.unsupported_capabilities),
            "reaction_terms": list(self.reaction_terms),
            "conversion_models": list(self.conversion_models),
            "non_reacting_only": self.non_reacting_only,
            "assumptions": [dict(a) for a in self.assumptions],
            "missing_information": [dict(m) for m in self.missing_information],
        }

    def validate_against_contract(self) -> list[ModelDiagnostic]:
        """Check a manifest against the contract it claims to implement."""
        from .diagnostics import DiagnosticCode

        out: list[ModelDiagnostic] = []
        if self.contract_version != CONTRACT_VERSION:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MANIFEST_VERSION_MISMATCH,
                    severity=Severity.ERROR,
                    message=(
                        f"manifest declares contract version "
                        f"{self.contract_version!r} but this engine implements "
                        f"{CONTRACT_VERSION!r}"
                    ),
                    where=("manifest", self.model_id),
                    origin=Origin.MANIFEST,
                    remediation=(
                        "Regenerate the manifest with the adapter installed for "
                        f"contract {CONTRACT_VERSION}."
                    ),
                    model_id=self.model_id,
                    model_version=self.model_version,
                )
            )
        for port in self.ports:
            if port.is_usable:
                continue
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.VALUE_UNIT_UNREGISTERED,
                    severity=Severity.WARNING,
                    message=(
                        f"port {port.port_id!r} carries no usable unit: "
                        f"{port.unavailable_reason}. It is declared so the gap is "
                        f"visible and countable, and it cannot be connected."
                    ),
                    where=("manifest", self.model_id, "port", port.port_id),
                    origin=Origin.MANIFEST,
                    remediation=(
                        "Supply the missing declaration to the source model, or map "
                        "the port onto a registered unit explicitly."
                    ),
                    model_id=self.model_id,
                    model_version=self.model_version,
                )
            )
        for capability, reason in self.unsupported_capabilities.items():
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CAPABILITY_UNSUPPORTED,
                    severity=Severity.INFO,
                    message=(
                        f"{self.model_id} does not support {capability!r}: {reason}"
                    ),
                    where=("manifest", self.model_id),
                    origin=Origin.MANIFEST,
                    model_id=self.model_id,
                    model_version=self.model_version,
                )
            )
        return out


# --------------------------------------------------------------------------- #
# instances, connections, graph
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModelInstance:
    """One placement of a model in a graph, with its parameters."""

    instance_id: str
    model_id: str
    model_version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    label: str = ""
    role: str = ""
    position: Mapping[str, float] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.instance_id:
            raise ContractError("a ModelInstance must have an instance_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "label": self.label,
            "role": self.role,
            "parameters": dict(self.parameters),
            "position": dict(self.position),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PortRef:
    instance_id: str
    port_id: str

    def __post_init__(self) -> None:
        if not self.instance_id or not self.port_id:
            raise ContractError(f"a PortRef needs both an instance and a port: {self}")

    @property
    def key(self) -> str:
        return f"{self.instance_id}/{self.port_id}"

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.key

    def to_dict(self) -> dict[str, str]:
        return {"instance_id": self.instance_id, "port_id": self.port_id}


@dataclass(frozen=True)
class Connection:
    """A directed link from one instance's output port to another's input port.

    ``transform`` is deliberately restricted to ``{"identity"}`` in v0.1.  A
    transformation such as a unit conversion or a rate-from-interval conversion
    has to be a *declared conversion model* on the source manifest, otherwise the
    connection is refused (CG-03).
    """

    connection_id: str
    source: PortRef
    target: PortRef
    transform: str = "identity"
    label: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.connection_id:
            raise ContractError("a Connection must have a connection_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "transform": self.transform,
            "label": self.label,
            "notes": self.notes,
        }


@dataclass
class CompositionGraph:
    """A directed acyclic graph of model instances joined by typed connections."""

    graph_id: str
    title: str
    instances: tuple[ModelInstance, ...] = ()
    connections: tuple[Connection, ...] = ()
    contract_version: str = CONTRACT_VERSION
    description: str = ""
    source_ref: str = ""
    #: instance_id/port_id -> a literal input value, supplied without a
    #: connection.  Values here are still held to every port rule.
    literal_inputs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    defaults: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""

    def instance(self, instance_id: str) -> ModelInstance:
        for inst in self.instances:
            if inst.instance_id == instance_id:
                return inst
        raise KeyError(
            f"{self.graph_id}: no instance {instance_id!r}; known: "
            f"{[i.instance_id for i in self.instances]}"
        )

    def connection(self, connection_id: str) -> Connection:
        for conn in self.connections:
            if conn.connection_id == connection_id:
                return conn
        raise KeyError(f"{self.graph_id}: no connection {connection_id!r}")

    def incoming(self, ref: PortRef) -> list[Connection]:
        return [c for c in self.connections if c.target.key == ref.key]

    def outgoing(self, ref: PortRef) -> list[Connection]:
        return [c for c in self.connections if c.source.key == ref.key]

    def edges(self) -> list[tuple[str, str]]:
        """``(upstream_instance, downstream_instance)`` pairs, deduplicated."""
        seen: list[tuple[str, str]] = []
        for conn in self.connections:
            pair = (conn.source.instance_id, conn.target.instance_id)
            if pair not in seen and pair[0] != pair[1]:
                seen.append(pair)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "graph_id": self.graph_id,
            "title": self.title,
            "description": self.description,
            "source_ref": self.source_ref,
            "instances": [i.to_dict() for i in self.instances],
            "connections": [c.to_dict() for c in self.connections],
            "literal_inputs": {
                k: dict(v) for k, v in self.literal_inputs.items()
            },
            "defaults": dict(self.defaults),
            "notes": self.notes,
        }

    def canonical(self) -> str:
        """Stable serialization used for the reproducibility digest."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def graph_to_dict(graph: CompositionGraph) -> dict[str, Any]:
    return graph.to_dict()


def load_graph(payload: Mapping[str, Any]) -> CompositionGraph:
    """Parse and structurally validate a graph document."""
    if not isinstance(payload, Mapping):
        raise ContractError("a graph document must be a JSON object")
    version = payload.get("contract_version", CONTRACT_VERSION)
    if version != CONTRACT_VERSION:
        raise ContractError(
            f"graph declares contract version {version!r}; this engine implements "
            f"{CONTRACT_VERSION!r}. Refusing to guess the rest of the document."
        )
    try:
        instances = tuple(
            ModelInstance(
                instance_id=item["instance_id"],
                model_id=item["model_id"],
                model_version=item.get("model_version", "unversioned"),
                parameters=dict(item.get("parameters", {})),
                label=item.get("label", ""),
                role=item.get("role", ""),
                position=dict(item.get("position", {})),
                notes=item.get("notes", ""),
            )
            for item in payload.get("instances", ())
        )
        connections = tuple(
            Connection(
                connection_id=item["connection_id"],
                source=PortRef(
                    instance_id=item["source"]["instance_id"],
                    port_id=item["source"]["port_id"],
                ),
                target=PortRef(
                    instance_id=item["target"]["instance_id"],
                    port_id=item["target"]["port_id"],
                ),
                transform=item.get("transform", "identity"),
                label=item.get("label", ""),
                notes=item.get("notes", ""),
            )
            for item in payload.get("connections", ())
        )
    except KeyError as exc:
        raise ContractError(
            f"graph document is missing required field {exc.args[0]!r}"
        ) from None

    seen_instances: set[str] = set()
    for inst in instances:
        if inst.instance_id in seen_instances:
            raise ContractError(f"duplicate instance id {inst.instance_id!r}")
        seen_instances.add(inst.instance_id)
    seen_connections: set[str] = set()
    for conn in connections:
        if conn.connection_id in seen_connections:
            raise ContractError(f"duplicate connection id {conn.connection_id!r}")
        seen_connections.add(conn.connection_id)
        for endpoint in (conn.source.instance_id, conn.target.instance_id):
            if endpoint not in seen_instances:
                raise ContractError(
                    f"connection {conn.connection_id!r} names instance "
                    f"{endpoint!r}, which the graph does not contain"
                )

    return CompositionGraph(
        graph_id=payload.get("graph_id", "unnamed"),
        title=payload.get("title", ""),
        instances=instances,
        connections=connections,
        contract_version=version,
        description=payload.get("description", ""),
        source_ref=payload.get("source_ref", ""),
        literal_inputs={
            k: dict(v) for k, v in (payload.get("literal_inputs") or {}).items()
        },
        defaults=dict(payload.get("defaults", {})),
        notes=payload.get("notes", ""),
    )


# --------------------------------------------------------------------------- #
# inputs and outputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModelInput:
    """One value handed to an instance, with how it got there.

    ``via`` is ``"connection"`` (it came from an upstream port), ``"literal"``
    (it was declared on the graph) or ``"default"`` (the model supplied its own).
    Keeping these apart is what lets the diagnostics view say "this number is
    *not* connected to anything", which is the difference between an audited
    result and a hard-coded one.
    """

    ref: PortRef
    value: ModelValue
    via: str = "default"
    connection_id: str | None = None
    provenance_chain: tuple[ProvenanceRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ref": self.ref.to_dict(),
            "value": self.value.to_dict(),
            "via": self.via,
            "connection_id": self.connection_id,
        }
        if self.provenance_chain:
            payload["provenance_chain"] = [r.to_dict() for r in self.provenance_chain]
        return payload


@dataclass(frozen=True)
class ModelOutput:
    """One value an instance produced."""

    ref: PortRef
    value: ModelValue
    provenance_chain: tuple[ProvenanceRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref.to_dict(),
            "value": self.value.to_dict(),
            "provenance_chain": [r.to_dict() for r in self.provenance_chain],
        }


# --------------------------------------------------------------------------- #
# plan
# --------------------------------------------------------------------------- #


class RunStatus(Enum):
    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    #: the graph did not run because it did not validate
    INVALID = "invalid"
    #: the graph ran and a model failed
    FAILED = "failed"
    #: refused on capability grounds before anything ran
    REFUSED = "refused"


@dataclass(frozen=True)
class ExecutionStep:
    """One instance's turn, with its resolved inputs."""

    index: int
    instance_id: str
    model_id: str
    model_version: str
    status: RunStatus
    inputs: tuple[ModelInput, ...] = ()
    outputs: tuple[ModelOutput, ...] = ()
    residuals: tuple["ResidualReport", ...] = ()
    unresolved: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[ModelDiagnostic, ...] = ()
    duration_note: str = ""

    @property
    def output_map(self) -> dict[str, ModelOutput]:
        return {o.ref.port_id: o for o in self.outputs}

    def output_value(self, port_id: str) -> ModelOutput | None:
        for out in self.outputs:
            if out.ref.port_id == port_id:
                return out
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "instance_id": self.instance_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "status": self.status.value,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "residuals": [r.to_dict() for r in self.residuals],
            "unresolved": [dict(u) for u in self.unresolved],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True)
class ExecutionPlan:
    """The topological order a run will follow, plus why it is that order.

    ``digest`` covers the graph, the model versions and the manifests, so two
    runs of the same plan are provably the same plan.
    """

    plan_id: str
    graph_id: str
    contract_version: str
    steps: tuple[ExecutionStep, ...]
    diagnostics: tuple[ModelDiagnostic, ...] = ()
    digest: str = ""

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(step.instance_id for step in self.steps)

    def step(self, instance_id: str) -> ExecutionStep | None:
        for step in self.steps:
            if step.instance_id == instance_id:
                return step
        return None

    def compute_digest(self, graph: CompositionGraph, manifests: Mapping[str, str]) -> str:
        """SHA-256 over graph + model versions + manifest digests.

        Deliberately excludes timestamps, paths, process ids and durations, so
        two runs of the same inputs produce the same digest (CG-13).
        """
        payload = {
            "contract_version": self.contract_version,
            "graph": json.loads(graph.canonical()),
            "model_versions": dict(sorted(manifests.items())),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "graph_id": self.graph_id,
            "contract_version": self.contract_version,
            "order": list(self.order),
            "steps": [s.to_dict() for s in self.steps],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "digest": self.digest,
        }


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResidualReport:
    """How far a balance failed to close, carried out of the model unchanged."""

    label: str
    value: float
    unit: str
    tolerance: float
    within_tolerance: bool
    quantity: Quantity = Quantity.MASS
    component: str | None = None
    contributions: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "tolerance": self.tolerance,
            "within_tolerance": self.within_tolerance,
            "quantity": self.quantity.value,
            "component": self.component,
            "contributions": [dict(c) for c in self.contributions],
        }


@dataclass(frozen=True)
class ModelRunResult:
    """Everything one instance did, including what it could not do."""

    instance_id: str
    model_id: str
    model_version: str
    status: RunStatus
    inputs: tuple[ModelInput, ...] = ()
    outputs: tuple[ModelOutput, ...] = ()
    residuals: tuple[ResidualReport, ...] = ()
    unresolved: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[ModelDiagnostic, ...] = ()
    raw_summary: Mapping[str, Any] = field(default_factory=dict)
    provenance_index: Mapping[str, tuple[ProvenanceRecord, ...]] = field(
        default_factory=dict
    )

    @property
    def output_map(self) -> dict[str, ModelOutput]:
        return {o.ref.port_id: o for o in self.outputs}

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "status": self.status.value,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "residuals": [r.to_dict() for r in self.residuals],
            "unresolved": [dict(u) for u in self.unresolved],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "raw_summary": dict(self.raw_summary),
            "provenance_index": {
                k: [r.to_dict() for r in v]
                for k, v in self.provenance_index.items()
            },
        }


@dataclass(frozen=True)
class CompositionResult:
    """The whole run: plan, per-instance results, diagnostics and a digest.

    ``reproducibility`` is a SHA-256 over every numeric output in execution
    order together with the plan digest.  Identical graphs, model versions and
    inputs produce an identical digest, and any changed number changes it
    (CG-13).
    """

    run_id: str
    graph_id: str
    contract_version: str
    status: RunStatus
    plan: ExecutionPlan
    results: tuple[ModelRunResult, ...] = ()
    diagnostics: tuple[ModelDiagnostic, ...] = ()
    provenance_index: Mapping[str, tuple[ProvenanceRecord, ...]] = field(
        default_factory=dict
    )
    reproducibility: str = ""
    model_versions: Mapping[str, str] = field(default_factory=dict)
    notes: str = ""
    #: The evidence-backed account of this graph: every connection's standing,
    #: the evidence for it, what is unresolved, and the scientific validation
    #: status of each model and of the combination. Present on every document,
    #: including one that refused before executing. ``{}`` means the caller did
    #: not build one -- which the report marks as absent rather than as clean.
    composition_report: Mapping[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[ModelDiagnostic]:
        return [d for d in self.diagnostics if d.is_error]

    @property
    def warnings(self) -> list[ModelDiagnostic]:
        return [
            d for d in self.diagnostics
            if d.severity is Severity.WARNING
        ]

    def result(self, instance_id: str) -> ModelRunResult | None:
        for res in self.results:
            if res.instance_id == instance_id:
                return res
        return None

    def compute_digest(self) -> str:
        payload: list[dict[str, Any]] = []
        for res in self.results:
            payload.append(
                {
                    "instance_id": res.instance_id,
                    "model_version": res.model_version,
                    "status": res.status.value,
                    "outputs": [
                        {
                            "port_id": out.ref.port_id,
                            "state": out.value.state.value,
                            "value": (
                                repr(out.value.value)
                                if out.value.value is not None
                                else None
                            ),
                            "unit": out.value.unit,
                        }
                        for out in res.outputs
                    ],
                    "residuals": [
                        {"label": r.label, "value": repr(r.value)}
                        for r in res.residuals
                    ],
                }
            )
        blob = json.dumps(
            {"plan": self.plan.digest, "results": payload},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "contract_version": self.contract_version,
            "status": self.status.value,
            "plan": self.plan.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "provenance_index": {
                k: [r.to_dict() for r in v]
                for k, v in self.provenance_index.items()
            },
            "reproducibility": self.reproducibility,
            "model_versions": dict(self.model_versions),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "notes": self.notes,
            "composition_report": dict(self.composition_report),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


def convert_value(
    value: ModelValue, to_unit: str, quantity: Quantity
) -> tuple[ModelValue, dict[str, Any]]:
    """Convert a numeric ``ModelValue`` into another unit of the *same* quantity.

    Returns the converted value and the :class:`Conversion` record.  Raises
    rather than approximating for every non-numeric state, so an unresolved
    value can never be laundered into a number by passing through a connection.
    """
    if not value.is_resolved:
        raise ContractError(
            f"cannot convert a value in state {value.state.value!r}: it carries no "
            f"number. An unresolved value cannot become a resolved one by being "
            f"passed through a connection."
        )
    if value.quantity is not quantity:
        raise ContractError(
            f"cannot convert a {value.quantity.value} value into {quantity.value}: "
            f"that is a change of quantity, not of unit"
        )
    conversion = convert(float(value.value), value.unit, to_unit, quantity)
    converted = ModelValue(
        state=value.state,
        quantity=quantity,
        unit=to_unit,
        value=conversion.value,
        provenance=value.provenance,
        components=value.components,
        reason=value.reason,
        source_ref=value.source_ref,
        method=value.method,
        chain=value.chain,
        conversion=conversion.to_dict(),
        extra=value.extra,
    )
    return converted, conversion.to_dict()