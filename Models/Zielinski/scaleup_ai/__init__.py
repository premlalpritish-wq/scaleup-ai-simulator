"""ScaleUp AI core -- paper-agnostic process modelling schemas and engine.

This package is the canonical ScaleUp AI representation of a bioprocess:

    units       dimension-checked unit registry
    provenance  EvidenceRef / Quantity / Assumption / MissingParameter
    process     ProcessNode / MaterialStream / ProcessGraph
    equations   registry of transparent executable equations + declared gaps
    engine      deterministic evaluator (evidence replay + predictive)
    report      serialization of a run to JSON/CSV/Markdown

It is deliberately model-agnostic. A concrete model (for example
`models.zielinski_2019`) supplies the graph, the quantities and the wiring; it
never redefines ProcessState, ProcessGraph or the evidence records.
"""

from __future__ import annotations

from .equations import (
    EQUATIONS,
    MISSING_MODELS,
    AmbiguousEquation,
    Equation,
    MissingModel,
    equation,
    executable_equations,
    refuses_to_run,
)
from .engine import (
    CalculationTrace,
    CrossCheck,
    EquationBinding,
    ExecutionEngine,
    ExecutionMode,
    NodeResult,
    NodeStatus,
    ProcessState,
    Ref,
    Resolution,
    RunResult,
    RunSummary,
    UnresolvedResult,
    node_loc,
    stream_loc,
)
from .process import (
    GraphError,
    MaterialStream,
    OperationKind,
    ProcessGraph,
    ProcessNode,
    StreamKind,
)
from .serialize import (
    DeserializationError,
    evidence_record_from_dict,
    graph_from_dict,
    quantity_from_dict,
    resolution_from_dict,
    round_trip_graph,
    run_result_from_dict,
)
from .provenance import (
    Assumption,
    Basis,
    EvidenceRef,
    MissingParameter,
    Provenance,
    Quantity,
    QuantityError,
    Severity,
    SourceExpression,
    Uncertainty,
    ValidationMessage,
    ValidationStatus,
    assumed,
    derived,
    digitized,
    reported,
    unknown,
)
from .units import Dimension, UnitError, convert, dimension_of, is_convertible

__all__ = [
    "EQUATIONS",
    "MISSING_MODELS",
    "AmbiguousEquation",
    "Assumption",
    "Basis",
    "CalculationTrace",
    "CrossCheck",
    "DeserializationError",
    "Dimension",
    "Equation",
    "EquationBinding",
    "EvidenceRef",
    "ExecutionEngine",
    "ExecutionMode",
    "GraphError",
    "MaterialStream",
    "MissingModel",
    "MissingParameter",
    "NodeResult",
    "NodeStatus",
    "OperationKind",
    "ProcessGraph",
    "ProcessNode",
    "ProcessState",
    "Provenance",
    "Quantity",
    "QuantityError",
    "Ref",
    "Resolution",
    "RunResult",
    "RunSummary",
    "Severity",
    "SourceExpression",
    "StreamKind",
    "Uncertainty",
    "UnitError",
    "UnresolvedResult",
    "ValidationMessage",
    "ValidationStatus",
    "assumed",
    "convert",
    "derived",
    "dimension_of",
    "digitized",
    "equation",
    "evidence_record_from_dict",
    "executable_equations",
    "graph_from_dict",
    "is_convertible",
    "node_loc",
    "quantity_from_dict",
    "refuses_to_run",
    "reported",
    "resolution_from_dict",
    "round_trip_graph",
    "run_result_from_dict",
    "stream_loc",
    "unknown",
]

__version__ = "1.0.0"