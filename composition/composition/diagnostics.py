"""One diagnostic type for the composition layer.

Both existing models already use the same ``(code, severity, message, where)``
shape -- Zielinski's ``ValidationMessage`` and Morris's ``BalanceDiagnostic``.
The composition layer reuses that shape rather than inventing a third, and adds
two things the models do not have: a stable machine-readable ``code`` and a
``remediation`` string saying what the operator should do about it.

Every diagnostic states where it came from, so a message raised by Morris can
never be silently reclassified as a composition error (CG-11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence


class Severity(Enum):
    """Ordered by weight. Worst-wins when folding into a status."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        return {"info": 0, "warning": 1, "error": 2}[self.value]

    @classmethod
    def worst(cls, values: Iterable["Severity"]) -> "Severity":
        worst = cls.INFO
        for value in values:
            if value.rank > worst.rank:
                worst = value
        return worst


class Origin(str, Enum):
    """Which layer raised the diagnostic. Never merged away."""

    COMPOSITION = "composition"
    MANIFEST = "manifest"
    CONNECTION = "connection"
    ORDERING = "ordering"
    EXECUTION = "execution"
    #: raised inside a model and passed through untouched
    MORRIS = "morris2011"
    ZIELINSKI = "zielinski2019"
    RUNNER = "runner"


class DiagnosticCode(str, Enum):
    """Stable codes. The acceptance tests pin these strings."""

    # -- manifest ------------------------------------------------------------
    MANIFEST_INVALID = "manifest.invalid"
    MANIFEST_VERSION_MISMATCH = "manifest.contract_version_mismatch"
    MODEL_VERSION_MISMATCH = "manifest.model_version_mismatch"
    ADAPTER_MISSING = "manifest.adapter_missing"

    # -- graph structure -----------------------------------------------------
    GRAPH_DUPLICATE_INSTANCE = "graph.duplicate_instance"
    GRAPH_UNKNOWN_INSTANCE = "graph.unknown_instance"
    GRAPH_UNKNOWN_PORT = "graph.unknown_port"
    GRAPH_DUPLICATE_CONNECTION = "graph.duplicate_connection"

    # -- connection compatibility -------------------------------------------
    CONNECTION_QUANTITY_MISMATCH = "connection.quantity_mismatch"
    CONNECTION_UNIT_MISMATCH = "connection.unit_mismatch"
    CONNECTION_NON_CONVERTIBLE = "connection.unit_not_convertible"
    CONNECTION_DIRECTION = "connection.direction_invalid"
    CONNECTION_COMPONENT_MISMATCH = "connection.component_mismatch"
    CONNECTION_COMPONENT_UNATTRIBUTED = "connection.component_unattributed"
    CONNECTION_SELF_LOOP = "connection.self_loop"
    CONNECTION_MISSING_REQUIRED = "connection.missing_required_input"
    CONNECTION_CARRIES_UNRESOLVED = "connection.carries_unresolved"

    # -- capability ----------------------------------------------------------
    CAPABILITY_UNSUPPORTED = "capability.unsupported"
    CAPABILITY_REACTIVE_BALANCE_REFUSED = "capability.reactive_balance_refused"
    CAPABILITY_CONVERSION_MODEL_ABSENT = "capability.conversion_model_absent"

    # -- ordering ------------------------------------------------------------
    ORDER_CYCLE_DETECTED = "order.cycle_detected"
    ORDER_DANGLING_SOURCE = "order.dangling_source"

    # -- execution -----------------------------------------------------------
    EXECUTION_MODEL_FAILED = "execution.model_failed"
    EXECUTION_DEPENDENT_SKIPPED = "execution.dependent_skipped"
    EXECUTION_NO_OUTPUT = "execution.no_output"
    EXECUTION_RESIDUAL_OUT_OF_TOLERANCE = "execution.residual_out_of_tolerance"
    EXECUTION_UNDERDETERMINED = "execution.underdetermined"
    EXECUTION_OVERCONSTRAINED = "execution.overconstrained"
    EXECUTION_INCONSISTENT = "execution.inconsistent"
    #: a finding the model reported *while* producing its result: a contradiction
    #: in its source, a cross-check that failed, a quantity its own documentation
    #: says it cannot determine.  Carries the model's own severity, which may be
    #: error, but does not mean the model failed to run.
    MODEL_FINDING = "model.finding"

    # -- values --------------------------------------------------------------
    VALUE_UNRESOLVED = "value.unresolved"
    VALUE_UNKNOWN = "value.unknown"
    VALUE_NOT_REPORTED = "value.not_reported"
    VALUE_RANGE_NOT_COLLAPSED = "value.range_not_collapsed"
    VALUE_REPORTED_ZERO = "value.reported_zero"
    VALUE_UNIT_UNREGISTERED = "value.unit_unregistered"

    # -- runner --------------------------------------------------------------
    RUNNER_BAD_INPUT = "runner.bad_input"
    RUNNER_MALFORMED_RESULT = "runner.malformed_result"
    RUNNER_WORKER_CRASHED = "runner.worker_crashed"


@dataclass(frozen=True)
class ModelDiagnostic:
    """A message attached to a manifest, a graph, a node or a run.

    ``where`` is a tuple of address parts, e.g.
    ``("connection", "c1")`` or ``("instance", "brass_charge", "port",
    "in:A:total")``.  ``origin`` names the layer that raised it.
    """

    code: DiagnosticCode
    severity: Severity
    message: str
    where: tuple[str, ...] = ()
    origin: Origin = Origin.COMPOSITION
    remediation: str = ""
    model_id: str | None = None
    model_version: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    def prefixed(self) -> str:
        if self.origin is Origin.COMPOSITION:
            return self.message
        return f"[{self.origin.value}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.prefixed(),
            "raw_message": self.message,
            "where": list(self.where),
            "origin": self.origin.value,
            "remediation": self.remediation,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "detail": dict(self.detail),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelDiagnostic":
        return cls(
            code=DiagnosticCode(payload["code"]),
            severity=Severity(payload["severity"]),
            message=payload.get("raw_message", payload["message"]),
            where=tuple(payload.get("where", ())),
            origin=Origin(payload.get("origin", "composition")),
            remediation=payload.get("remediation", ""),
            model_id=payload.get("model_id"),
            model_version=payload.get("model_version"),
            detail=dict(payload.get("detail", {})),
        )

    @staticmethod
    def worst_severity(diagnostics: Sequence["ModelDiagnostic"]) -> Severity:
        return Severity.worst(d.severity for d in diagnostics)

    @staticmethod
    def errors(diagnostics: Iterable["ModelDiagnostic"]) -> list["ModelDiagnostic"]:
        return [d for d in diagnostics if d.is_error]

    #: Codes that mean *the model did not produce its result*. Everything else,
    #: at any severity, is a finding the model reported while producing one.
    EXECUTION_FAILURE_CODES: frozenset["DiagnosticCode"] = frozenset({
        DiagnosticCode.EXECUTION_MODEL_FAILED,
        DiagnosticCode.EXECUTION_DEPENDENT_SKIPPED,
        DiagnosticCode.EXECUTION_NO_OUTPUT,
        DiagnosticCode.RUNNER_WORKER_CRASHED,
        DiagnosticCode.CONNECTION_CARRIES_UNRESOLVED,
        DiagnosticCode.VALUE_UNRESOLVED,
        DiagnosticCode.ORDER_DANGLING_SOURCE,
    })

    @staticmethod
    def execution_failures(
        diagnostics: Sequence["ModelDiagnostic"],
    ) -> list["ModelDiagnostic"]:
        """The subset that actually stopped a model from producing a result.

        This distinction is the whole point of carrying ``origin`` on every
        diagnostic.  The Zielinski model reports five *error*-severity findings
        about its own source -- contradictions between sections of the paper --
        while completing its run successfully.  Those must stay visible as
        errors, and must not be turned into "the run failed", because the run
        did not fail.
        """
        return [
            d for d in diagnostics
            if d.code in ModelDiagnostic.EXECUTION_FAILURE_CODES
        ]