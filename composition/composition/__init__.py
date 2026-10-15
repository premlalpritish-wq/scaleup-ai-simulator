"""ScaleUp AI composition layer, contract version 0.1.0.

A typed, auditable way to connect the existing scientific models:

* :mod:`composition.contracts`   -- the versioned interface types
* :mod:`composition.quantities`  -- the quantity taxonomy and unit bridge
* :mod:`composition.diagnostics` -- one diagnostic type, codes and remediations
* :mod:`composition.engine`      -- load, connect, order, execute
* :mod:`composition.adapters`    -- one adapter per model, isolated in a worker
* :mod:`composition.runner`      -- the JSON command-line interface

The governing rule, inherited from both models and enforced here structurally:

    an absent value is never a zero, a mass is never a mass flow, and an
    unsupported connection fails with a named reason rather than producing a
    plausible number.
"""

from __future__ import annotations

from .adapters import (
    REGISTRATIONS,
    adapter_for,
    known_models,
    model_root,
    repository_root,
)
from .contracts import (
    CONTRACT_VERSION,
    CompositionGraph,
    CompositionResult,
    Connection,
    ContractError,
    ExecutionPlan,
    ExecutionStep,
    ModelInput,
    ModelInstance,
    ModelManifest,
    ModelOutput,
    ModelRunResult,
    ModelValue,
    PortDefinition,
    PortDirection,
    PortRef,
    ProvenanceRecord,
    ProvenanceRequirement,
    ResidualReport,
    RunStatus,
    TemporalBasis,
    ValueProvenance,
    ValueState,
    load_graph,
)
from .diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from .engine import CompositionEngine, CompositionError
from .quantities import (
    Quantity,
    QuantityError,
    UnitRegistry,
    convert,
    describe_registry,
)

__version__ = CONTRACT_VERSION

__all__ = [
    "CONTRACT_VERSION",
    "REGISTRATIONS",
    "CompositionEngine",
    "CompositionError",
    "CompositionGraph",
    "CompositionResult",
    "Connection",
    "ContractError",
    "DiagnosticCode",
    "ExecutionPlan",
    "ExecutionStep",
    "ModelDiagnostic",
    "ModelInput",
    "ModelInstance",
    "ModelManifest",
    "ModelOutput",
    "ModelRunResult",
    "ModelValue",
    "Origin",
    "PortDefinition",
    "PortDirection",
    "PortRef",
    "ProvenanceRecord",
    "ProvenanceRequirement",
    "Quantity",
    "QuantityError",
    "ResidualReport",
    "RunStatus",
    "Severity",
    "TemporalBasis",
    "UnitRegistry",
    "ValueProvenance",
    "ValueState",
    "adapter_for",
    "convert",
    "describe_registry",
    "known_models",
    "load_graph",
    "model_root",
    "repository_root",
]