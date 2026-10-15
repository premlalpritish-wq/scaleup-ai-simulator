"""ScaleUp AI core: the deterministic execution engine.

Two modes, with a hard wall between them:

  EVIDENCE_REPLAY  Loads the paper's reported conditions and observations, then
                    evaluates only those equations whose inputs are actually
                    available. Everything else is reported as unresolved. No
                    observed value is ever re-emitted as a prediction.

  PREDICTIVE       Starts from caller-supplied inputs and declared assumptions.
                    Reported values are NOT visible in this mode, so the engine
                    cannot dress a replayed result up as a simulation. Anything
                    that would need a model this package does not implement
                    fails closed with a structured reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .equations import EQUATIONS, MISSING_MODELS, AmbiguousEquation
from .process import ProcessGraph, ProcessNode
from .provenance import (
    EvidenceRef,
    Provenance,
    Quantity,
    Uncertainty,
    Severity,
    ValidationMessage,
    ValidationStatus,
    derived,
)
from .units import UnitError, convert


class ExecutionMode(Enum):
    EVIDENCE_REPLAY = "evidence_replay"
    PREDICTIVE = "predictive"


class Location(str):
    """`node:<id>` or `stream:<id>`."""

    __slots__ = ()


def node_loc(node_id: str) -> str:
    return f"node:{node_id}"


def stream_loc(stream_id: str) -> str:
    return f"stream:{stream_id}"


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #


class ProcessState:
    """Resolved quantities, keyed by `location:quantity_id`.

    Evidence replay seeds this from observed values. Predictive mode seeds it
    only from declared inputs, which is what keeps the two modes honest.
    """

    def __init__(self, mode: ExecutionMode) -> None:
        self.mode = mode
        self._values: dict[str, Quantity] = {}

    @staticmethod
    def key(location: str, quantity_id: str) -> str:
        return f"{location}:{quantity_id}"

    def put(self, location: str, quantity: Quantity) -> None:
        self._values[self.key(location, quantity.quantity_id)] = quantity

    def get(self, location: str, quantity_id: str) -> Quantity | None:
        return self._values.get(self.key(location, quantity_id))

    def contains(self, location: str, quantity_id: str) -> bool:
        return self.key(location, quantity_id) in self._values

    def as_mapping(self) -> dict[str, Quantity]:
        return dict(self._values)

    def __len__(self) -> int:
        return len(self._values)


# --------------------------------------------------------------------------- #
# bindings and cross-checks (declared by the model, evaluated by the engine)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Ref:
    location: str
    quantity_id: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.location}:{self.quantity_id}"


@dataclass(frozen=True)
class EquationBinding:
    """One node's use of one registered equation, with concrete input wiring."""

    binding_id: str
    node_id: str
    equation_id: str
    inputs: Mapping[str, Ref]
    output_quantity_id: str
    output_location: str
    notes: str = ""


@dataclass(frozen=True)
class CrossCheck:
    """A declared comparison of a computed value against a reported value."""

    check_id: str
    node_id: str
    description: str
    computed: Ref
    reported: Ref
    tolerance_rel: float
    evidence: tuple[EvidenceRef, ...] = ()
    on_failure: str = "error"


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #


@dataclass
class MissingInput:
    quantity_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"quantity_id": self.quantity_id, "reason": self.reason}


@dataclass
class UnresolvedResult:
    """A target that could not be produced, and precisely why."""

    target: str
    reason: str
    missing_equations: tuple[str, ...] = ()
    missing_inputs: tuple[MissingInput, ...] = ()
    missing_models: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "reason": self.reason,
            "missing_equations": list(self.missing_equations),
            "missing_inputs": [m.to_dict() for m in self.missing_inputs],
            "missing_models": list(self.missing_models),
            "blocked_by": list(self.blocked_by),
        }


@dataclass
class Resolution:
    target: str
    quantity: Quantity | None = None
    unresolved: UnresolvedResult | None = None

    @property
    def is_resolved(self) -> bool:
        return self.quantity is not None and self.quantity.is_resolved

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "resolved": self.is_resolved,
            "quantity": self.quantity.to_dict() if self.quantity else None,
            "unresolved": self.unresolved.to_dict() if self.unresolved else None,
        }


@dataclass
class CalculationTrace:
    """A fully expanded, auditable record of one equation evaluation."""

    binding_id: str
    node_id: str
    equation_id: str
    statement: str
    input_values: dict[str, dict[str, Any]]
    output_quantity_id: str
    output_value: float
    output_unit: str
    mode: ExecutionMode

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "node_id": self.node_id,
            "equation_id": self.equation_id,
            "statement": self.statement,
            "input_values": self.input_values,
            "output_quantity_id": self.output_quantity_id,
            "output_value": self.output_value,
            "output_unit": self.output_unit,
            "mode": self.mode.value,
        }


class NodeStatus(Enum):
    EXECUTED = "executed"
    PARTIAL = "partial"
    OBSERVED_ONLY = "observed_only"
    UNRESOLVED = "unresolved"


@dataclass
class NodeResult:
    node_id: str
    index: int
    name: str
    operation: str
    status: NodeStatus
    input_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    output_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    computed: list[Quantity] = field(default_factory=list)
    traces: list[CalculationTrace] = field(default_factory=list)
    unresolved: list[UnresolvedResult] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)
    validation: ValidationStatus = ValidationStatus.NOT_EVALUATED

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "index": self.index,
            "name": self.name,
            "operation": self.operation,
            "status": self.status.value,
            "validation": self.validation.value,
            "input_states": self.input_states,
            "output_states": self.output_states,
            "computed": [q.to_dict() for q in self.computed],
            "traces": [t.to_dict() for t in self.traces],
            "unresolved": [u.to_dict() for u in self.unresolved],
            "warnings": [w.to_dict() for w in self.warnings],
        }


@dataclass
class RunSummary:
    mode: ExecutionMode
    nodes_executed: int = 0
    nodes_partial: int = 0
    nodes_observed_only: int = 0
    nodes_unresolved: int = 0
    observed_reference_values: int = 0
    digitized_values: int = 0
    computed_values: int = 0
    predicted_values: int = 0
    assumed_values: int = 0
    unknown_values: int = 0
    unresolved_targets: int = 0
    validation_errors: int = 0
    validation_warnings: int = 0
    cross_check_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "nodes_executed": self.nodes_executed,
            "nodes_partial": self.nodes_partial,
            "nodes_observed_only": self.nodes_observed_only,
            "nodes_unresolved": self.nodes_unresolved,
            "observed_reference_values": self.observed_reference_values,
            "digitized_values": self.digitized_values,
            "computed_values": self.computed_values,
            "predicted_values": self.predicted_values,
            "assumed_values": self.assumed_values,
            "unknown_values": self.unknown_values,
            "unresolved_targets": self.unresolved_targets,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "cross_check_errors": self.cross_check_errors,
            "graph_is_predictive": self.predicted_values > 0,
        }


@dataclass
class RunResult:
    mode: ExecutionMode
    graph_id: str
    node_results: list[NodeResult]
    summary: RunSummary
    cross_checks: list[ValidationMessage] = field(default_factory=list)
    unresolved: list[UnresolvedResult] = field(default_factory=list)

    def node(self, node_id: str) -> NodeResult:
        for nr in self.node_results:
            if nr.node_id == node_id:
                return nr
        raise KeyError(node_id)

    def all_computed(self) -> list[Quantity]:
        return [q for nr in self.node_results for q in nr.computed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "graph_id": self.graph_id,
            "summary": self.summary.to_dict(),
            "nodes": [nr.to_dict() for nr in self.node_results],
            "cross_checks": [m.to_dict() for m in self.cross_checks],
            "unresolved": [u.to_dict() for u in self.unresolved],
        }


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #


def _is_finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


#: A prediction target that names a working volume ("1000L", "2 l", "_volume_")
#: is a request about a scale other than the reference batch, so scale-up is
#: always part of the fail-closed answer.
SCALE_REQUEST = re.compile(r"(?:\d+\s*l(?![a-z])|_vol|scale|industrial|extrapolat)")


class ExecutionEngine:
    """Deterministic evaluator for a ProcessGraph.

    The engine is deterministic by construction: it walks nodes in topological
    order, evaluates declared bindings whose inputs resolve, and records an
    explicit unresolved result for everything else. There is no fallback path
    that substitutes a plausible number.
    """

    def __init__(
        self,
        graph: ProcessGraph,
        bindings: Sequence[EquationBinding],
        cross_checks: Sequence[CrossCheck] = (),
        *,
        predictive_capabilities: Mapping[str, Sequence[str]] | None = None,
        keyword_models: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.graph = graph
        self.bindings = list(bindings)
        self.cross_checks = list(cross_checks)
        #: target ref -> MissingModel ids, used to explain fail-closed answers
        self.predictive_capabilities = {
            k: tuple(v) for k, v in (predictive_capabilities or {}).items()
        }
        #: substring -> MissingModel ids, for targets not named explicitly
        #: (e.g. an industrial-scale query about a target nobody enumerated)
        self.keyword_models = {k: tuple(v) for k, v in (keyword_models or {}).items()}
        self._validate_bindings()

    def _models_for(self, target: str) -> tuple[str, ...]:
        """Models a target would need: exact match, then keyword, then scale hint."""
        exact = self.predictive_capabilities.get(target)
        if exact:
            return exact
        lowered = target.lower()
        hits: list[str] = []
        for keyword, models in self.keyword_models.items():
            if keyword in lowered:
                hits.extend(m for m in models if m not in hits)
        # An explicit volume in a prediction request means "at this scale", so the
        # absence of scale-up correlation is always part of the answer.
        if SCALE_REQUEST.search(lowered) and "scaleup.effect_of_scale" not in hits:
            hits.append("scaleup.effect_of_scale")
        return tuple(hits)

    # -- setup checks --------------------------------------------------------
    def _validate_bindings(self) -> None:
        node_ids = {n.node_id for n in self.graph.nodes}
        stream_ids = set(self.graph.streams)
        locations = ("node", "stream")

        def check_location(raw: str, where: str) -> str:
            loc = raw.partition(":")[0]
            if loc not in locations:
                raise ValueError(f"{where} has bad location {raw!r}")
            if loc == "node" and raw.partition(":")[2] not in node_ids:
                raise ValueError(f"{where} references unknown node in {raw!r}")
            if loc == "stream" and raw.partition(":")[2] not in stream_ids:
                raise ValueError(f"{where} references unknown stream in {raw!r}")
            return loc

        for b in self.bindings:
            where = f"binding {b.binding_id!r}"
            if b.node_id not in node_ids:
                raise ValueError(f"{where} targets unknown node {b.node_id!r}")
            if b.equation_id not in EQUATIONS:
                raise ValueError(
                    f"{where} references unregistered equation {b.equation_id!r}"
                )
            check_location(b.output_location, where)
            for key, ref in b.inputs.items():
                check_location(ref.location, f"{where} input {key!r}")
                if not ref.quantity_id:
                    raise ValueError(f"{where} input {key!r} has no quantity id")

    # -- seeding -------------------------------------------------------------
    def _seed_state(self, mode: ExecutionMode, inputs: Mapping[str, Quantity]) -> ProcessState:
        state = ProcessState(mode)
        if mode is ExecutionMode.EVIDENCE_REPLAY:
            # seed observed + declared-assumption values only; unknowns stay absent
            for location, qid, q in self.graph.iter_quantities():
                if q.provenance in (
                    Provenance.REPORTED,
                    Provenance.DIGITIZED,
                    Provenance.ASSUMED,
                ):
                    state.put(location, q)
        for key, q in inputs.items():
            loc, _, qid = key.rpartition(":")
            if not qid:
                loc, qid = key, q.quantity_id
            state.put(loc, q)
        return state

    # -- input resolution ----------------------------------------------------
    def _gather_inputs(
        self, binding: EquationBinding, state: ProcessState
    ) -> tuple[dict[str, float], dict[str, dict[str, Any]], list[MissingInput]]:
        eq = EQUATIONS[binding.equation_id]
        values: dict[str, float] = {}
        trace: dict[str, dict[str, Any]] = {}
        missing: list[MissingInput] = []

        for spec in eq.inputs:
            ref = binding.inputs.get(spec.key)
            if ref is None:
                missing.append(MissingInput(spec.key, "binding does not wire this input"))
                continue
            q = state.get(ref.location, ref.quantity_id)
            if q is None:
                missing.append(
                    MissingInput(
                        str(ref),
                        "no value available in the current execution mode",
                    )
                )
                continue
            if not q.is_resolved:
                missing.append(MissingInput(str(ref), "quantity is unknown in the source"))
                continue
            if q.value_range is not None:
                missing.append(
                    MissingInput(
                        str(ref),
                        f"reported as range {q.value_range}; no declared representative value",
                    )
                )
                continue
            assert q.value is not None and q.unit is not None
            try:
                v = convert(q.value, q.unit, spec.unit)
            except UnitError as exc:
                missing.append(MissingInput(str(ref), str(exc)))
                continue
            values[spec.key] = v
            half = None
            if q.uncertainty is not None and q.value is not None:
                raw_half = (q.uncertainty.hi - q.uncertainty.lo) / 2.0
                half = raw_half * abs(convert(1.0, q.unit, spec.unit))
            trace[spec.key] = {
                "ref": str(ref),
                "value": q.value,
                "source_unit": q.unit,
                "normalized_unit": spec.unit,
                "value_used": v,
                "provenance": q.provenance.value,
                "evidence": [e.to_dict() for e in q.evidence],
                "uncertainty_halfwidth": half,
                "uncertainty_basis": q.uncertainty.basis if q.uncertainty else None,
            }
        return values, trace, missing

    # -- run -----------------------------------------------------------------
    def run(
        self,
        mode: ExecutionMode = ExecutionMode.EVIDENCE_REPLAY,
        inputs: Mapping[str, Quantity] | None = None,
    ) -> RunResult:
        inputs = inputs or {}
        state = self._seed_state(mode, inputs)
        results: list[NodeResult] = []
        all_unresolved: list[UnresolvedResult] = []
        summary = RunSummary(mode=mode)

        for node in self.graph.topological_order():
            results.append(
                self._run_node(node, state, mode, summary, all_unresolved)
            )

        cross_messages = self._run_cross_checks(state)
        for nr in results:
            summary.validation_errors += sum(
                1 for w in nr.warnings if w.severity is Severity.ERROR
            )
            summary.validation_warnings += sum(
                1 for w in nr.warnings if w.severity is Severity.WARNING
            )
        summary.cross_check_errors = sum(
            1 for m in cross_messages if m.severity is Severity.ERROR
        )
        summary.validation_errors += summary.cross_check_errors
        summary.unresolved_targets = len(all_unresolved)
        summary.observed_reference_values = sum(
            1
            for _, _, q in self.graph.iter_quantities()
            if q.provenance is Provenance.REPORTED
        )
        summary.digitized_values = sum(
            1
            for _, _, q in self.graph.iter_quantities()
            if q.provenance is Provenance.DIGITIZED
        )
        summary.unknown_values = sum(
            1
            for _, _, q in self.graph.iter_quantities()
            if q.provenance is Provenance.UNKNOWN
        )
        summary.computed_values = sum(len(nr.computed) for nr in results)
        summary.predicted_values = (
            summary.computed_values if mode is ExecutionMode.PREDICTIVE else 0
        )
        summary.assumed_values = sum(
            1
            for _, _, q in self.graph.iter_quantities()
            if q.provenance is Provenance.ASSUMED
        )
        summary.nodes_executed = sum(1 for r in results if r.status is NodeStatus.EXECUTED)
        summary.nodes_partial = sum(1 for r in results if r.status is NodeStatus.PARTIAL)
        summary.nodes_observed_only = sum(
            1 for r in results if r.status is NodeStatus.OBSERVED_ONLY
        )
        summary.nodes_unresolved = sum(1 for r in results if r.status is NodeStatus.UNRESOLVED)

        return RunResult(
            mode=mode,
            graph_id=self.graph.graph_id,
            node_results=results,
            summary=summary,
            cross_checks=cross_messages,
            unresolved=all_unresolved,
        )

    def _run_node(
        self,
        node: ProcessNode,
        state: ProcessState,
        mode: ExecutionMode,
        summary: RunSummary,
        sink: list[UnresolvedResult],
    ) -> NodeResult:
        nr = NodeResult(
            node_id=node.node_id,
            index=node.index,
            name=node.name,
            operation=node.operation.value,
            status=NodeStatus.UNRESOLVED,
        )

        # input / output stream snapshots
        for sid in node.input_streams:
            stream = self.graph.stream(sid)
            nr.input_states[sid] = {
                qid: q.to_dict()
                for qid, q in stream.quantities.items()
                if state.contains(stream_loc(sid), qid)
            }
        for sid in node.output_streams:
            stream = self.graph.stream(sid)
            nr.output_states[sid] = {
                qid: q.to_dict()
                for qid, q in stream.quantities.items()
                if state.contains(stream_loc(sid), qid)
            }

        produced = 0
        attempted = 0
        for binding in (b for b in self.bindings if b.node_id == node.node_id):
            attempted += 1
            outcome = self._evaluate_binding(binding, state, mode)
            if isinstance(outcome, CalculationTrace):
                nr.traces.append(outcome)
                eq = EQUATIONS[binding.equation_id]
                derived_q = derived(
                    quantity_id=binding.output_quantity_id,
                    label=eq.output_key,
                    value=outcome.output_value,
                    unit=outcome.output_unit,
                    method=eq.statement,
                    inputs={f"{k}={v['ref']}" for k, v in outcome.input_values.items()},
                    notes=binding.notes,
                )
                propagated = self._propagate_uncertainty(eq, outcome)
                if propagated is not None:
                    derived_q.uncertainty = propagated
                nr.computed.append(derived_q)
                state.put(binding.output_location, derived_q)
                produced += 1
            else:
                nr.unresolved.append(outcome)
                sink.append(outcome)

        if attempted == 0:
            # No equation is declared for this node. That is not a failure: the
            # node may be fully described by reported observations alone.
            nr.status = NodeStatus.OBSERVED_ONLY
        elif produced == attempted:
            nr.status = NodeStatus.EXECUTED
        elif produced > 0:
            nr.status = NodeStatus.PARTIAL
        else:
            nr.status = NodeStatus.UNRESOLVED

        # declared-but-unimplemented equations are always surfaced
        for eq_id in node.refused_equations:
            eq = EQUATIONS[eq_id]
            nr.unresolved.append(
                UnresolvedResult(
                    target=f"{node.node_id}:{eq.output_key}",
                    reason=(
                        "the paper prints this formula but its dimensional "
                        "interpretation is unresolved, so it is not executed"
                    ),
                    missing_equations=(eq_id,),
                )
            )
            sink.append(nr.unresolved[-1])

        # carry the node's declared operating conditions into the snapshot
        nr.input_states.setdefault("__conditions__", {}).update(
            {k: v.to_dict() for k, v in node.operating_conditions.items()}
        )

        nr.validation = node.validation
        for msg in node.validation_messages:
            nr.warnings.append(msg)
        return nr

    @staticmethod
    def _propagate_uncertainty(eq, trace: CalculationTrace) -> Uncertainty | None:
        """Carry input uncertainties onto the derived output, when declared.

        Only applied when *every* input declares an uncertainty; a partial
        interval would understate the output and imply a confidence it does not
        have. When this returns None the derived quantity simply has no
        uncertainty, which is why no significance claim can be attached to it.
        """
        halfwidths: dict[str, float] = {}
        for spec in eq.inputs:
            entry = trace.input_values.get(spec.key)
            if entry is None or entry.get("uncertainty_halfwidth") is None:
                return None
            halfwidths[spec.key] = float(entry["uncertainty_halfwidth"])
        try:
            half = eq.propagate(
                {k: float(v["value_used"]) for k, v in trace.input_values.items()},
                halfwidths,
            )
        except (ZeroDivisionError, KeyError):
            return None
        if half is None or half < 0 or not _is_finite(half):
            return None
        return Uncertainty(
            kind="first_order_propagation",
            lo=trace.output_value - half,
            hi=trace.output_value + half,
            basis=(
                "linear combination of the declared input uncertainties "
                f"({', '.join(f'{k}+/-{halfwidths[k]:g}' for k in sorted(halfwidths))}); "
                "a reporting-precision interval, not an assay uncertainty"
            ),
        )

    def _evaluate_binding(
        self, binding: EquationBinding, state: ProcessState, mode: ExecutionMode
    ) -> CalculationTrace | UnresolvedResult:
        eq = EQUATIONS[binding.equation_id]

        if not eq.executable:
            return UnresolvedResult(
                target=f"{binding.output_location}:{binding.output_quantity_id}",
                reason=eq.ambiguity or "equation is not executable",
                missing_equations=(eq.equation_id,),
            )
        if mode is ExecutionMode.PREDICTIVE and not eq.predictive_capable:
            return UnresolvedResult(
                target=f"{binding.output_location}:{binding.output_quantity_id}",
                reason="equation is not declared predictive-capable",
                missing_equations=(eq.equation_id,),
            )

        values, trace, missing = self._gather_inputs(binding, state)
        if missing:
            models = tuple(
                m
                for m in self.predictive_capabilities.get(
                    f"{binding.output_location}:{binding.output_quantity_id}", ()
                )
            )
            return UnresolvedResult(
                target=f"{binding.output_location}:{binding.output_quantity_id}",
                reason=(
                    f"not all inputs resolved in {mode.value} mode; "
                    + "; ".join(f"{m.quantity_id}: {m.reason}" for m in missing)
                    + ". The paper supplies no model that would close the gap."
                ),
                missing_equations=(eq.equation_id,),
                missing_inputs=tuple(missing),
                missing_models=models,
            )

        try:
            out = eq.evaluate(values)
        except AmbiguousEquation as exc:
            return UnresolvedResult(
                target=f"{binding.output_location}:{binding.output_quantity_id}",
                reason=str(exc),
                missing_equations=(eq.equation_id,),
            )

        trace = CalculationTrace(
            binding_id=binding.binding_id,
            node_id=binding.node_id,
            equation_id=eq.equation_id,
            statement=eq.statement,
            input_values=trace,
            output_quantity_id=binding.output_quantity_id,
            output_value=out,
            output_unit=eq.output_unit,
            mode=mode,
        )
        return trace

    # -- cross checks --------------------------------------------------------
    def _run_cross_checks(self, state: ProcessState) -> list[ValidationMessage]:
        msgs: list[ValidationMessage] = []
        for check in self.cross_checks:
            computed = state.get(check.computed.location, check.computed.quantity_id)
            reported_q = state.get(check.reported.location, check.reported.quantity_id)
            if computed is None or not computed.is_resolved or computed.value is None:
                msgs.append(
                    ValidationMessage(
                        severity=Severity.INFO,
                        code=f"crosscheck_skipped:{check.check_id}",
                        message=(
                            f"{check.description}: not evaluated because "
                            f"{check.computed} is unresolved"
                        ),
                        where=check.check_id,
                        evidence=check.evidence,
                    )
                )
                continue
            if reported_q is None or reported_q.value is None:
                msgs.append(
                    ValidationMessage(
                        severity=Severity.INFO,
                        code=f"crosscheck_skipped:{check.check_id}",
                        message=(
                            f"{check.description}: not evaluated because "
                            f"{check.reported} is unresolved"
                        ),
                        where=check.check_id,
                        evidence=check.evidence,
                    )
                )
                continue
            rel = abs(computed.value - reported_q.value) / abs(reported_q.value)
            ok = rel <= check.tolerance_rel
            severity = Severity.INFO if ok else (
                Severity.WARNING if check.on_failure == "warning" else Severity.ERROR
            )
            msgs.append(
                ValidationMessage(
                    severity=severity,
                    code=f"crosscheck:{'pass' if ok else 'fail'}:{check.check_id}",
                    message=(
                        f"{check.description}: computed {computed.value:.4g} "
                        f"{computed.unit} vs reported {reported_q.value:.4g} "
                        f"{reported_q.unit} (relative difference {rel * 100:.2f}%, "
                        f"tolerance {check.tolerance_rel * 100:.2f}%)"
                    ),
                    where=check.check_id,
                    evidence=check.evidence,
                )
            )
        return msgs

    # -- fail-closed queries -------------------------------------------------
    def request(
        self,
        target: str,
        mode: ExecutionMode = ExecutionMode.PREDICTIVE,
        inputs: Mapping[str, Quantity] | None = None,
    ) -> Resolution:
        """Try to produce `target` ("location:quantity_id"). Fails closed."""
        run = self.run(mode=mode, inputs=inputs)
        loc, _, qid = target.rpartition(":")
        for nr in run.node_results:
            for q in nr.computed:
                if q.quantity_id == qid and self._loc_matches(nr, loc, q):
                    return Resolution(target=target, quantity=q)
        # fall back to a declared observed quantity when in replay mode
        if mode is ExecutionMode.EVIDENCE_REPLAY:
            for location, q_id, q in self.graph.iter_quantities():
                if q_id == qid and location == loc:
                    return Resolution(target=target, quantity=q)
        for u in run.unresolved:
            if u.target == target:
                return Resolution(target=target, unresolved=u)
        models = self._models_for(target)
        reason = (
            "no registered equation produces this target in "
            f"{mode.value} mode"
        )
        if models:
            details = "; ".join(
                f"{m} [{MISSING_MODELS[m].label}] requires "
                f"{', '.join(MISSING_MODELS[m].missing_inputs)}"
                for m in models
                if m in MISSING_MODELS
            )
            reason += f" -- would require unimplemented model(s): {details}"
        return Resolution(
            target=target,
            unresolved=UnresolvedResult(
                target=target, reason=reason, missing_models=models
            ),
        )

    @staticmethod
    def _loc_matches(nr: NodeResult, loc: str, q: Quantity) -> bool:
        if not loc:
            return True
        return any(
            q.quantity_id in nr.output_states.get(sid, {})
            for sid in nr.output_states
            if loc == f"stream:{sid}"
        ) or loc == f"node:{nr.node_id}"