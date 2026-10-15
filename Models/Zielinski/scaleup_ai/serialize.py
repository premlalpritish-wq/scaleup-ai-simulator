"""ScaleUp AI core: lossless (de)serialization of graphs, quantities and runs.

`to_dict()` on the dataclasses produces JSON-ready payloads. This module is the
inverse: it reconstructs live objects from those payloads so a record written to
disk can be reloaded, re-executed and compared against a fresh run (AT-025).

Round-trip fidelity is deliberate rather than best-effort. Rehydrated objects must
be equal in behaviour to the originals, so every field that affects execution or
interpretation is restored, including evidence, provenance, uncertainty, source
expressions, assumptions, missing parameters and validation messages.
"""

from __future__ import annotations

from typing import Any, Mapping

from .engine import (
    CalculationTrace,
    ExecutionMode,
    NodeResult,
    NodeStatus,
    Resolution,
    RunResult,
    RunSummary,
    UnresolvedResult,
)
from .process import MaterialStream, OperationKind, ProcessGraph, ProcessNode, StreamKind
from .provenance import (
    Assumption,
    EvidenceRef,
    MissingParameter,
    Provenance,
    Quantity,
    Severity,
    SourceExpression,
    Uncertainty,
    ValidationMessage,
    ValidationStatus,
)
from .units import unit as lookup_unit


class DeserializationError(ValueError):
    """Raised when a payload cannot be turned back into a live object."""


def _require(payload: Mapping[str, Any], key: str, ctx: str) -> Any:
    if key not in payload:
        raise DeserializationError(f"{ctx}: missing required key {key!r}")
    return payload[key]


# --------------------------------------------------------------------------- #
# leaf types
# --------------------------------------------------------------------------- #


def evidence_from_dict(d: Mapping[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        source_id=_require(d, "source_id", "EvidenceRef"),
        pdf_page=int(_require(d, "pdf_page", "EvidenceRef")),
        printed_page=int(_require(d, "printed_page", "EvidenceRef")),
        section=d.get("section"),
        figure=d.get("figure"),
        quote=d.get("quote"),
    )


def evidence_to_list(d: Mapping[str, Any] | None) -> tuple[EvidenceRef, ...]:
    return tuple(evidence_from_dict(e) for e in (d or ()))


def uncertainty_from_dict(d: Mapping[str, Any] | None) -> Uncertainty | None:
    if not d:
        return None
    return Uncertainty(
        kind=_require(d, "kind", "Uncertainty"),
        lo=float(_require(d, "lo", "Uncertainty")),
        hi=float(_require(d, "hi", "Uncertainty")),
        basis=_require(d, "basis", "Uncertainty"),
    )


def assumption_from_dict(d: Mapping[str, Any]) -> Assumption:
    return Assumption(
        assumption_id=_require(d, "assumption_id", "Assumption"),
        statement=_require(d, "statement", "Assumption"),
        rationale=_require(d, "rationale", "Assumption"),
        affects=tuple(d.get("affects", ())),
        evidence=evidence_to_list(d.get("evidence")),
    )


def missing_parameter_from_dict(d: Mapping[str, Any]) -> MissingParameter:
    return MissingParameter(
        parameter_id=_require(d, "parameter_id", "MissingParameter"),
        description=_require(d, "description", "MissingParameter"),
        reason=_require(d, "reason", "MissingParameter"),
        blocks=tuple(d.get("blocks", ())),
        evidence=evidence_to_list(d.get("evidence")),
    )


def source_expression_from_dict(d: Mapping[str, Any]) -> SourceExpression:
    return SourceExpression(
        expression_id=_require(d, "expression_id", "SourceExpression"),
        label=_require(d, "label", "SourceExpression"),
        expression_text=_require(d, "expression_text", "SourceExpression"),
        variable_definitions=dict(d.get("variable_definitions", {})),
        source_unit=_require(d, "source_unit", "SourceExpression"),
        expected_output_unit=_require(d, "expected_output_unit", "SourceExpression"),
        executable=bool(d.get("executable", False)),
        ambiguity=d.get("ambiguity"),
        evidence=evidence_to_list(d.get("evidence")),
    )


def validation_message_from_dict(d: Mapping[str, Any]) -> ValidationMessage:
    return ValidationMessage(
        severity=Severity(d.get("severity", "info")),
        code=_require(d, "code", "ValidationMessage"),
        message=_require(d, "message", "ValidationMessage"),
        where=_require(d, "where", "ValidationMessage"),
        evidence=evidence_to_list(d.get("evidence")),
    )


def quantity_from_dict(d: Mapping[str, Any]) -> Quantity:
    provenance = Provenance(_require(d, "provenance", "Quantity"))
    value_range = d.get("value_range")
    q = Quantity(
        quantity_id=_require(d, "quantity_id", "Quantity"),
        label=d.get("label", ""),
        provenance=provenance,
        value=None if d.get("value") is None else float(d["value"]),
        unit=d.get("unit"),
        value_range=None if not value_range else (float(value_range[0]), float(value_range[1])),
        original_unit=d.get("original_unit"),
        original_text=d.get("original_text"),
        evidence=evidence_to_list(d.get("evidence")),
        method=d.get("method"),
        inputs=tuple(d.get("inputs", ())),
        uncertainty=uncertainty_from_dict(d.get("uncertainty")),
        notes=d.get("notes", ""),
    )
    declared_basis = d.get("basis")
    if declared_basis is not None and declared_basis != q.basis.value:
        raise DeserializationError(
            f"quantity {q.quantity_id!r}: serialized basis {declared_basis!r} does not "
            f"match provenance {provenance.value!r} (implies {q.basis.value!r})"
        )
    return q


def _quantity_map(d: Mapping[str, Any] | None) -> dict[str, Quantity]:
    return {k: quantity_from_dict(v) for k, v in (d or {}).items()}


# --------------------------------------------------------------------------- #
# graph
# --------------------------------------------------------------------------- #


def stream_from_dict(d: Mapping[str, Any]) -> MaterialStream:
    return MaterialStream(
        stream_id=_require(d, "stream_id", "MaterialStream"),
        name=d.get("name", ""),
        kind=StreamKind(_require(d, "kind", "MaterialStream")),
        produced_by=d.get("produced_by"),
        consumed_by=d.get("consumed_by"),
        lineage=tuple(d.get("lineage", ())),
        description=d.get("description", ""),
        quantities=_quantity_map(d.get("quantities")),
        evidence=evidence_to_list(d.get("evidence")),
    )


def node_from_dict(d: Mapping[str, Any]) -> ProcessNode:
    return ProcessNode(
        node_id=_require(d, "node_id", "ProcessNode"),
        index=int(_require(d, "index", "ProcessNode")),
        name=d.get("name", ""),
        operation=OperationKind(_require(d, "operation", "ProcessNode")),
        input_streams=tuple(d.get("input_streams", ())),
        output_streams=tuple(d.get("output_streams", ())),
        description=d.get("description", ""),
        operating_conditions=_quantity_map(d.get("operating_conditions")),
        condition_notes=dict(d.get("condition_notes", {})),
        measurements=_quantity_map(d.get("measurements")),
        calculated=_quantity_map(d.get("calculated")),
        source_expressions=tuple(
            source_expression_from_dict(e) for e in d.get("source_expressions", ())
        ),
        assumptions=tuple(assumption_from_dict(a) for a in d.get("assumptions", ())),
        missing_parameters=tuple(
            missing_parameter_from_dict(m) for m in d.get("missing_parameters", ())
        ),
        evidence=evidence_to_list(d.get("evidence")),
        supported_equations=tuple(d.get("supported_equations", ())),
        refused_equations=tuple(d.get("refused_equations", ())),
        validation=ValidationStatus(d.get("validation", "not_evaluated")),
        validation_messages=[
            validation_message_from_dict(m) for m in d.get("validation_messages", ())
        ],
        figure1_label=d.get("figure1_label"),
    )


def graph_from_dict(d: Mapping[str, Any]) -> ProcessGraph:
    """Rebuild a ProcessGraph from `ProcessGraph.to_dict()` output."""
    graph = ProcessGraph(
        graph_id=_require(d, "graph_id", "ProcessGraph"),
        title=d.get("title", ""),
        source_id=_require(d, "source_id", "ProcessGraph"),
        assumptions=tuple(assumption_from_dict(a) for a in d.get("assumptions", ())),
        missing_parameters=tuple(
            missing_parameter_from_dict(m) for m in d.get("missing_parameters", ())
        ),
        description=d.get("description", ""),
        doi=d.get("doi", ""),
    )
    for payload in d.get("streams", {}).values():
        graph.add_stream(stream_from_dict(payload))
    for payload in d.get("nodes", ()):
        graph.add_node(node_from_dict(payload))
    return graph


# --------------------------------------------------------------------------- #
# run results
# --------------------------------------------------------------------------- #


def missing_input_from_dict(d: Mapping[str, Any]) -> Any:
    from .engine import MissingInput

    return MissingInput(
        quantity_id=_require(d, "quantity_id", "MissingInput"),
        reason=_require(d, "reason", "MissingInput"),
    )


def unresolved_from_dict(d: Mapping[str, Any]) -> UnresolvedResult:
    return UnresolvedResult(
        target=_require(d, "target", "UnresolvedResult"),
        reason=_require(d, "reason", "UnresolvedResult"),
        missing_equations=tuple(d.get("missing_equations", ())),
        missing_inputs=tuple(missing_input_from_dict(m) for m in d.get("missing_inputs", ())),
        missing_models=tuple(d.get("missing_models", ())),
        blocked_by=tuple(d.get("blocked_by", ())),
    )


def trace_from_dict(d: Mapping[str, Any]) -> CalculationTrace:
    return CalculationTrace(
        binding_id=_require(d, "binding_id", "CalculationTrace"),
        node_id=_require(d, "node_id", "CalculationTrace"),
        equation_id=_require(d, "equation_id", "CalculationTrace"),
        statement=_require(d, "statement", "CalculationTrace"),
        input_values={k: dict(v) for k, v in d.get("input_values", {}).items()},
        output_quantity_id=_require(d, "output_quantity_id", "CalculationTrace"),
        output_value=float(_require(d, "output_value", "CalculationTrace")),
        output_unit=_require(d, "output_unit", "CalculationTrace"),
        mode=ExecutionMode(d.get("mode", "evidence_replay")),
    )


def node_result_from_dict(d: Mapping[str, Any]) -> NodeResult:
    return NodeResult(
        node_id=_require(d, "node_id", "NodeResult"),
        index=int(d.get("index", 0)),
        name=d.get("name", ""),
        operation=d.get("operation", ""),
        status=NodeStatus(_require(d, "status", "NodeResult")),
        input_states=dict(d.get("input_states", {})),
        output_states=dict(d.get("output_states", {})),
        computed=[quantity_from_dict(q) for q in d.get("computed", ())],
        traces=[trace_from_dict(t) for t in d.get("traces", ())],
        unresolved=[unresolved_from_dict(u) for u in d.get("unresolved", ())],
        warnings=[validation_message_from_dict(w) for w in d.get("warnings", ())],
        validation=ValidationStatus(d.get("validation", "not_evaluated")),
    )


def summary_from_dict(d: Mapping[str, Any]) -> RunSummary:
    return RunSummary(
        mode=ExecutionMode(_require(d, "mode", "RunSummary")),
        nodes_executed=int(d.get("nodes_executed", 0)),
        nodes_partial=int(d.get("nodes_partial", 0)),
        nodes_observed_only=int(d.get("nodes_observed_only", 0)),
        nodes_unresolved=int(d.get("nodes_unresolved", 0)),
        observed_reference_values=int(d.get("observed_reference_values", 0)),
        digitized_values=int(d.get("digitized_values", 0)),
        computed_values=int(d.get("computed_values", 0)),
        predicted_values=int(d.get("predicted_values", 0)),
        assumed_values=int(d.get("assumed_values", 0)),
        unknown_values=int(d.get("unknown_values", 0)),
        unresolved_targets=int(d.get("unresolved_targets", 0)),
        validation_errors=int(d.get("validation_errors", 0)),
        validation_warnings=int(d.get("validation_warnings", 0)),
        cross_check_errors=int(d.get("cross_check_errors", 0)),
    )


def run_result_from_dict(d: Mapping[str, Any]) -> RunResult:
    return RunResult(
        mode=ExecutionMode(_require(d, "mode", "RunResult")),
        graph_id=_require(d, "graph_id", "RunResult"),
        node_results=[node_result_from_dict(n) for n in d.get("nodes", ())],
        summary=summary_from_dict(_require(d, "summary", "RunResult")),
        cross_checks=[
            validation_message_from_dict(m) for m in d.get("cross_checks", ())
        ],
        unresolved=[unresolved_from_dict(u) for u in d.get("unresolved", ())],
    )


def resolution_from_dict(d: Mapping[str, Any]) -> Resolution:
    return Resolution(
        target=_require(d, "target", "Resolution"),
        quantity=quantity_from_dict(d["quantity"]) if d.get("quantity") else None,
        unresolved=unresolved_from_dict(d["unresolved"]) if d.get("unresolved") else None,
    )


# --------------------------------------------------------------------------- #
# whole records
# --------------------------------------------------------------------------- #


def evidence_record_from_dict(d: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and rehydrate a whole evidence record, returning a fresh payload.

    The declared equation registry and missing models are rebuilt from the live
    registries rather than trusted from the file, so a tampered record cannot
    claim an equation exists when it does not.
    """
    from .equations import EQUATIONS, MISSING_MODELS

    record = dict(d)
    record["graph"] = graph_from_dict(_require(d, "graph", "evidence_record")).to_dict()

    declared_eq = d.get("equation_registry", {})
    for eq_id in declared_eq:
        if eq_id not in EQUATIONS:
            raise DeserializationError(
                f"record declares equation {eq_id!r}, which is not registered"
            )
    record["equation_registry"] = {k: v.to_dict() for k, v in EQUATIONS.items()}

    for model_id in d.get("declared_missing_models", {}):
        if model_id not in MISSING_MODELS:
            raise DeserializationError(
                f"record declares missing model {model_id!r}, which is unknown"
            )
    record["declared_missing_models"] = {k: v.to_dict() for k, v in MISSING_MODELS.items()}

    runs = _require(d, "runs", "evidence_record")
    record["runs"] = {
        "evidence_replay": run_result_from_dict(runs["evidence_replay"]).to_dict(),
        "predictive": run_result_from_dict(runs["predictive"]).to_dict(),
    }
    return record


# --------------------------------------------------------------------------- #
# convenience
# --------------------------------------------------------------------------- #


def round_trip_graph(graph: ProcessGraph) -> ProcessGraph:
    return graph_from_dict(graph.to_dict())


def assert_units_registered(graph: ProcessGraph) -> None:
    """Every unit used anywhere in the graph must be a registered unit."""
    for _location, _qid, q in graph.iter_quantities():
        if q.unit:
            lookup_unit(q.unit)