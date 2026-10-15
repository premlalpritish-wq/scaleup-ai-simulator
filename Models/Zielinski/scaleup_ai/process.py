"""ScaleUp AI core: process graph types.

A process is a set of typed operation nodes joined by directed material
streams. Stream identity is preserved end to end: each stream records which
node produced it, which node consumed it, and its full lineage, so any
intermediate can be traced back to the transformation that created it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator

from .provenance import (
    Assumption,
    EvidenceRef,
    MissingParameter,
    Quantity,
    QuantityError,
    Severity,
    SourceExpression,
    ValidationMessage,
    ValidationStatus,
)


class OperationKind(Enum):
    """Typed operation vocabulary.

    `is_separation`, `is_chemical_conversion` etc. let the engine reason about
    what kind of transformation occurred without hard-coding node ids.
    """

    FERMENTATION = "fermentation"
    HARVEST = "harvest"
    LYSIS = "lysis"
    DISSOLUTION = "dissolution"
    RENATURATION = "renaturation"
    CHEMICAL_MODIFICATION = "chemical_modification"
    PROTEOLYSIS = "proteolysis"
    PRECIPITATION = "precipitation"
    SALT_DISSOLUTION = "salt_dissolution"
    CHROMATOGRAPHY = "chromatography"
    CHARACTERIZATION = "characterization"


#: operation kinds that, in principle, could be mechanistically simulated
SIMULATABLE_KINDS: frozenset[OperationKind] = frozenset(
    {
        OperationKind.FERMENTATION,
        OperationKind.RENATURATION,
        OperationKind.CHEMICAL_MODIFICATION,
        OperationKind.PROTEOLYSIS,
    }
)


class StreamKind(Enum):
    FERMENTATION_MEDIUM = "fermentation_medium"
    WET_BIOMASS = "wet_biomass"
    INCLUSION_BODIES = "inclusion_bodies"
    DENATURED_PROTEIN_SOLUTION = "denatured_protein_solution"
    RENATURED_PRECURSOR = "renatured_precursor"
    CITRACONYLATED_PRECURSOR = "citraconylated_precursor"
    DIGESTED_PRECURSOR = "digested_precursor"
    CHROMATOGRAPHIC_FRACTION = "chromatographic_fraction"
    INSULIN_FRACTION = "insulin_fraction"
    CITRATE_BLOCKED_FRACTION = "citrate_blocked_fraction"
    INSULIN_ZINC_PRECIPITATE = "insulin_zinc_precipitate"
    DISSOLVED_ZINC_SALT = "dissolved_zinc_salt"
    FINAL_PRODUCT = "final_product"
    WASTE = "waste"


# --------------------------------------------------------------------------- #
# streams
# --------------------------------------------------------------------------- #


@dataclass
class MaterialStream:
    """A directed edge carrying a material state between operations."""

    stream_id: str
    name: str
    kind: StreamKind
    produced_by: str | None = None
    consumed_by: str | None = None
    lineage: tuple[str, ...] = ()
    #: named quantities attached to this stream (measurements, derived values)
    quantities: dict[str, Quantity] = field(default_factory=dict)
    description: str = ""
    evidence: tuple[EvidenceRef, ...] = ()

    def put(self, quantity: Quantity) -> Quantity:
        self.quantities[quantity.quantity_id] = quantity
        return quantity

    def get(self, quantity_id: str) -> Quantity | None:
        return self.quantities.get(quantity_id)

    def require(self, quantity_id: str) -> Quantity:
        q = self.quantities.get(quantity_id)
        if q is None:
            raise KeyError(f"stream {self.stream_id!r} has no quantity {quantity_id!r}")
        return q

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "name": self.name,
            "kind": self.kind.value,
            "produced_by": self.produced_by,
            "consumed_by": self.consumed_by,
            "lineage": list(self.lineage),
            "description": self.description,
            "quantities": {k: v.to_dict() for k, v in self.quantities.items()},
            "evidence": [e.to_dict() for e in self.evidence],
        }


# --------------------------------------------------------------------------- #
# nodes
# --------------------------------------------------------------------------- #


@dataclass
class ProcessNode:
    """A typed operation with its inputs, outputs, conditions and evidence."""

    node_id: str
    index: int
    name: str
    operation: OperationKind
    input_streams: tuple[str, ...] = ()
    output_streams: tuple[str, ...] = ()
    description: str = ""

    operating_conditions: dict[str, Quantity] = field(default_factory=dict)
    #: non-scalar conditions (buffer recipes, media identity, equipment) kept verbatim
    condition_notes: dict[str, str] = field(default_factory=dict)
    measurements: dict[str, Quantity] = field(default_factory=dict)
    calculated: dict[str, Quantity] = field(default_factory=dict)

    #: formulas exactly as printed in the paper, preserved verbatim
    source_expressions: tuple[SourceExpression, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    missing_parameters: tuple[MissingParameter, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    #: ids of registered equations the engine may evaluate for this node
    supported_equations: tuple[str, ...] = ()
    #: equations the paper implies but that the implementation refuses to run
    refused_equations: tuple[str, ...] = ()

    validation: ValidationStatus = ValidationStatus.NOT_EVALUATED
    validation_messages: list[ValidationMessage] = field(default_factory=list)

    #: figure-1 node label this node corresponds to, when one exists
    figure1_label: str | None = None

    @property
    def is_simulatable_in_principle(self) -> bool:
        return self.operation in SIMULATABLE_KINDS

    def all_quantities(self) -> dict[str, Quantity]:
        merged: dict[str, Quantity] = {}
        merged.update(self.operating_conditions)
        merged.update(self.measurements)
        merged.update(self.calculated)
        return merged

    def get(self, quantity_id: str) -> Quantity | None:
        """Look a quantity up in conditions, then measurements, then calculations."""
        return self.all_quantities().get(quantity_id)

    def require(self, quantity_id: str) -> Quantity:
        q = self.get(quantity_id)
        if q is None:
            raise KeyError(f"node {self.node_id!r} has no quantity {quantity_id!r}")
        return q

    def add_validation(self, message: ValidationMessage) -> None:
        """Fold a diagnostic into the node's validation status (worst wins)."""
        self.validation_messages.append(message)
        if message.severity is Severity.ERROR:
            self.validation = ValidationStatus.FAILED
        elif message.severity is Severity.WARNING:
            if self.validation is not ValidationStatus.FAILED:
                self.validation = ValidationStatus.WARNING
        elif self.validation is ValidationStatus.NOT_EVALUATED:
            self.validation = ValidationStatus.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "index": self.index,
            "name": self.name,
            "operation": self.operation.value,
            "figure1_label": self.figure1_label,
            "description": self.description,
            "input_streams": list(self.input_streams),
            "output_streams": list(self.output_streams),
            "operating_conditions": {k: v.to_dict() for k, v in self.operating_conditions.items()},
            "condition_notes": dict(self.condition_notes),
            "measurements": {k: v.to_dict() for k, v in self.measurements.items()},
            "calculated": {k: v.to_dict() for k, v in self.calculated.items()},
            "source_expressions": [e.to_dict() for e in self.source_expressions],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "missing_parameters": [m.to_dict() for m in self.missing_parameters],
            "supported_equations": list(self.supported_equations),
            "refused_equations": list(self.refused_equations),
            "validation": self.validation.value,
            "validation_messages": [m.to_dict() for m in self.validation_messages],
            "evidence": [e.to_dict() for e in self.evidence],
        }


# --------------------------------------------------------------------------- #
# graph
# --------------------------------------------------------------------------- #


class GraphError(ValueError):
    """Raised when the process graph is structurally invalid."""


@dataclass
class ProcessGraph:
    """An ordered, typed process definition."""

    graph_id: str
    title: str
    source_id: str
    nodes: list[ProcessNode] = field(default_factory=list)
    streams: dict[str, MaterialStream] = field(default_factory=dict)
    assumptions: tuple[Assumption, ...] = ()
    missing_parameters: tuple[MissingParameter, ...] = ()
    description: str = ""
    doi: str = ""

    # ---- construction ------------------------------------------------------
    def add_node(self, node: ProcessNode) -> ProcessNode:
        if any(n.node_id == node.node_id for n in self.nodes):
            raise GraphError(f"duplicate node id {node.node_id!r}")
        self.nodes.append(node)
        return node

    def add_stream(self, stream: MaterialStream) -> MaterialStream:
        if stream.stream_id in self.streams:
            raise GraphError(f"duplicate stream id {stream.stream_id!r}")
        self.streams[stream.stream_id] = stream
        return stream

    # ---- queries -----------------------------------------------------------
    def node(self, node_id: str) -> ProcessNode:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        raise KeyError(f"unknown node {node_id!r}")

    def stream(self, stream_id: str) -> MaterialStream:
        try:
            return self.streams[stream_id]
        except KeyError:
            raise KeyError(f"unknown stream {stream_id!r}") from None

    def iter_quantities(self) -> Iterator[tuple[str, str, Quantity]]:
        """Yield (location, quantity_id, Quantity) for the whole graph."""
        for node in self.nodes:
            for qid, q in node.operating_conditions.items():
                yield f"node:{node.node_id}", qid, q
            for qid, q in node.measurements.items():
                yield f"node:{node.node_id}", qid, q
            for qid, q in node.calculated.items():
                yield f"node:{node.node_id}", qid, q
        for sid, stream in self.streams.items():
            for qid, q in stream.quantities.items():
                yield f"stream:{sid}", qid, q

    def topological_order(self) -> list[ProcessNode]:
        """Nodes ordered so every producer precedes every consumer (Kahn's algorithm).

        A node becomes ready only once every node producing one of its input
        streams has been emitted. A node consuming a stream it also produces
        carries no dependency on itself, which is what makes a genuine cycle --
        rather than a self-loop -- raise instead of silently ordering the graph.
        """
        producer_of = {sid: s.produced_by for sid, s in self.streams.items()}
        remaining = {n.node_id: n for n in self.nodes}

        deps: dict[str, set[str]] = {}
        for node in self.nodes:
            required: set[str] = set()
            for sid in node.input_streams:
                producer = producer_of.get(sid)
                if producer is not None and producer != node.node_id:
                    required.add(producer)
            deps[node.node_id] = required

        order: list[ProcessNode] = []
        satisfied: set[str] = set()
        while remaining:
            ready = [
                nid for nid, required in deps.items()
                if nid in remaining and required <= satisfied
            ]
            if not ready:
                raise GraphError(
                    "cycle or dangling stream in graph; unresolved nodes: "
                    + ", ".join(sorted(remaining))
                )
            ready.sort(key=lambda nid: remaining[nid].index)
            for nid in ready:
                order.append(remaining.pop(nid))
                satisfied.add(nid)
        return order

    # ---- validation --------------------------------------------------------
    def validate(self) -> list[ValidationMessage]:
        """Structural checks. Returns messages; raises GraphError only on
        unrecoverable structure (missing nodes/streams, duplicate ids)."""
        msgs: list[ValidationMessage] = []
        node_ids = {n.node_id for n in self.nodes}

        for node in self.nodes:
            for sid in node.input_streams + node.output_streams:
                if sid not in self.streams:
                    msgs.append(
                        ValidationMessage(
                            severity=Severity.ERROR,
                            code="dangling_stream",
                            message=f"node {node.node_id!r} references unknown stream {sid!r}",
                            where=node.node_id,
                        )
                    )
        for sid, stream in self.streams.items():
            for ref in (stream.produced_by, stream.consumed_by):
                if ref is not None and ref not in node_ids:
                    raise GraphError(f"stream {sid!r} references unknown node {ref!r}")

        # every stream must have exactly one producer and one consumer
        for sid, stream in self.streams.items():
            producers = [n.node_id for n in self.nodes if sid in n.output_streams]
            consumers = [n.node_id for n in self.nodes if sid in n.input_streams]
            if len(producers) > 1:
                msgs.append(
                    ValidationMessage(
                        severity=Severity.ERROR,
                        code="multiple_producers",
                        message=f"stream {sid!r} produced by {producers}",
                        where=sid,
                    )
                )
            if len(consumers) > 1:
                msgs.append(
                    ValidationMessage(
                        severity=Severity.ERROR,
                        code="multiple_consumers",
                        message=f"stream {sid!r} consumed by {consumers}",
                        where=sid,
                    )
                )
            if stream.produced_by != (producers[0] if producers else None):
                msgs.append(
                    ValidationMessage(
                        severity=Severity.ERROR,
                        code="producer_mismatch",
                        message=(
                            f"stream {sid!r} declares producer {stream.produced_by!r} "
                            f"but is output by {producers}"
                        ),
                        where=sid,
                    )
                )
            if stream.consumed_by != (consumers[0] if consumers else None):
                msgs.append(
                    ValidationMessage(
                        severity=Severity.ERROR,
                        code="consumer_mismatch",
                        message=(
                            f"stream {sid!r} declares consumer {stream.consumed_by!r} "
                            f"but is input to {consumers}"
                        ),
                        where=sid,
                    )
                )

        # index must be a dense 1..N ordering
        indices = sorted(n.index for n in self.nodes)
        if indices != list(range(1, len(self.nodes) + 1)):
            msgs.append(
                ValidationMessage(
                    severity=Severity.ERROR,
                    code="bad_index_order",
                    message=f"node indices are not 1..{len(self.nodes)}: {indices}",
                    where=self.graph_id,
                )
            )

        # structural integrity of every quantity
        for location, qid, q in self.iter_quantities():
            try:
                q.__post_init__()
            except QuantityError as exc:
                msgs.append(
                    ValidationMessage(
                        severity=Severity.ERROR,
                        code="quantity_integrity",
                        message=str(exc),
                        where=f"{location}:{qid}",
                    )
                )
        return msgs

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "title": self.title,
            "source_id": self.source_id,
            "description": self.description,
            "doi": self.doi,
            "nodes": [n.to_dict() for n in self.topological_order()],
            "streams": {k: v.to_dict() for k, v in self.streams.items()},
            "assumptions": [a.to_dict() for a in self.assumptions],
            "missing_parameters": [m.to_dict() for m in self.missing_parameters],
        }