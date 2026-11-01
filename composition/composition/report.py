"""The evidence-backed composition report.

Every graph this runner is asked about -- one that ran, one that was refused, one
that failed to parse -- leaves a report behind saying what was attempted, what
each connection's standing is and why, what evidence backs that, what remains
unresolved, and what the scientific validation status of the whole thing is.

## The distinction this file exists to keep

Four different things are routinely collapsed into one word, and only one of them
is about whether the software worked:

1. **Mechanically invalid** -- a contract, direction, unit, component or
   ordering rule failed. The engine already refused it and said why.
2. **Scientifically refused** -- a declared compatibility rule in
   :mod:`composition.cross_model` rejects it, with cited evidence.
3. **Permitted, conditionally** -- a source supports it, under stated
   assumptions an operator has to accept.
4. **Unresolved** -- nobody has written down whether it is allowed, and the
   policy fails closed. This is an *absence of a judgement*, and the report says
   so; it is never presented as a finding of physical incompatibility.

On top of all four sits a fifth question that none of them answers: **did it
work?** A graph that executes is not thereby scientifically justified, and a
refused graph is not thereby scientifically refuted. The report states both and
never lets one stand in for the other.

## What this file does not do

It re-decides nothing. Every disposition is *derived from diagnostics the engine
already emitted* and from :func:`composition.cross_model.check`, so a second
compatibility system cannot grow up beside the first. It invents no evidence, no
confidence score, no conversion factor and no scientific conclusion: a field
with no support behind it is reported as ``"not_documented"`` rather than filled
in, and the combined graph's validation status is always ``not_established``.

## Provenance

The report *describes* the existing provenance rather than restating it, and it
is careful about one thing in particular: a value that arrived at an instance
through a connection and was re-published is **carried**, and its chain says so;
a value the instance computed is **computed**, and its chain names only that
instance. Nothing here may imply a balance closed. Whether it closed is
established by the balance's own residuals, which live in
``result.results[].residuals`` and are referenced, not recomputed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import cross_model
from .contracts import Connection, ModelDiagnostic, ModelManifest, PortDefinition
from .diagnostics import DiagnosticCode, Severity

#: Bumped when the shape changes incompatibly. Consumers should refuse a schema
#: they do not recognise rather than guess.
REPORT_SCHEMA = "composition-report/1"

#: The value used wherever a field has no support behind it. Distinct from an
#: empty string, which means "stated, and it was nothing".
NOT_DOCUMENTED = "not_documented"

#: Dispositions, in the order a reader wants them.
DISPOSITIONS = (
    "mechanically_invalid",
    "scientifically_refused",
    "permitted_conditionally",
    "permitted",
    "unresolved",
)

#: Why a rule reached the position it did. Re-exported from
#: :mod:`composition.cross_model` rather than restated, so a consumer reading
#: the report and a caller reading the policy see the same three words.
EVIDENCE_BASES = (
    "documented_incompatibility",
    "evidence_limited",
    "permitted",
)


# --------------------------------------------------------------------------- #
# per-connection assessment
# --------------------------------------------------------------------------- #


def _port_block(
    instance_id: str,
    manifest: ModelManifest | None,
    port: PortDefinition | None,
) -> dict[str, Any]:
    """One endpoint: which model, which port, and what that port *is*.

    Every field the manifest publishes is carried; a field the manifest does not
    publish is ``not_documented``, never invented.
    """
    if manifest is None or port is None:
        return {
            "instance_id": instance_id,
            "model_id": NOT_DOCUMENTED,
            "model_version": NOT_DOCUMENTED,
            "port_id": NOT_DOCUMENTED,
            "quantity": NOT_DOCUMENTED,
            "unit": NOT_DOCUMENTED,
            "label": NOT_DOCUMENTED,
            "direction": NOT_DOCUMENTED,
            "temporal_basis": NOT_DOCUMENTED,
            "has_component_identity": None,
            "provenance_requirement": NOT_DOCUMENTED,
            "required": None,
            "usable": None,
            "description": NOT_DOCUMENTED,
        }
    return {
        "instance_id": instance_id,
        "model_id": manifest.model_id,
        "model_version": manifest.model_version,
        "port_id": port.port_id,
        "quantity": port.quantity.value,
        "unit": port.unit,
        "label": port.label,
        "direction": port.direction.value,
        "temporal_basis": port.temporal_basis.value,
        "has_component_identity": port.has_component_identity,
        "provenance_requirement": port.provenance_requirement.value,
        "required": port.required,
        "usable": port.is_usable,
        "description": port.description or NOT_DOCUMENTED,
    }


def _diagnostic_block(diagnostic: Mapping[str, Any] | None) -> dict[str, Any]:
    if diagnostic is None:
        return {
            "code": NOT_DOCUMENTED, "severity": NOT_DOCUMENTED,
            "message": NOT_DOCUMENTED, "remediation": NOT_DOCUMENTED,
            "origin": NOT_DOCUMENTED,
        }
    return {
        "code": str(diagnostic.get("code", NOT_DOCUMENTED)),
        "severity": str(diagnostic.get("severity", NOT_DOCUMENTED)),
        "message": str(diagnostic.get("message", NOT_DOCUMENTED)),
        "remediation": str(diagnostic.get("remediation", "") or NOT_DOCUMENTED),
        "origin": str(diagnostic.get("origin", NOT_DOCUMENTED)),
    }


def _diagnostics_for(
    diagnostics: Sequence[ModelDiagnostic], connection_id: str
) -> list[ModelDiagnostic]:
    """Every diagnostic that bears on one connection.

    Two ways a diagnostic can: it can name the connection in its ``where``, or
    it can name it in ``detail.connections``. The second is how an ordering
    diagnostic attributes a cycle -- its ``where`` holds the participating
    instances, and the connection ids live in the detail. A connection inside a
    cycle must not read as ``permitted`` merely because nothing complained
    about *it*.
    """
    mine: list[ModelDiagnostic] = []
    for d in diagnostics:
        if "connection" in d.where and connection_id in d.where:
            mine.append(d)
            continue
        detail = d.detail or {}
        involved = detail.get("connections") if isinstance(detail, Mapping) else None
        if isinstance(involved, (list, tuple)) and connection_id in involved:
            mine.append(d)
    return mine


def _most_specific(diagnostics: Sequence[ModelDiagnostic]) -> ModelDiagnostic | None:
    """The diagnostic that explains the refusal best.

    A mechanical failure always beats a semantic one: the engine only reaches
    the semantic rule when nothing mechanical fired, but an ordering diagnostic
    can arrive afterwards and describe a different objection. Preferring a
    mechanical code here is what keeps a vague cross-model refusal from
    covering a precise unit mismatch.
    """
    errors = [d for d in diagnostics if d.is_error]
    if not errors:
        return None
    for code in (
        DiagnosticCode.GRAPH_UNKNOWN_PORT,
        DiagnosticCode.GRAPH_UNKNOWN_INSTANCE,
        DiagnosticCode.CONNECTION_DIRECTION,
        DiagnosticCode.CONNECTION_SELF_LOOP,
        DiagnosticCode.VALUE_UNIT_UNREGISTERED,
        DiagnosticCode.CONNECTION_NON_CONVERTIBLE,
        DiagnosticCode.CONNECTION_UNIT_MISMATCH,
        DiagnosticCode.CONNECTION_QUANTITY_MISMATCH,
        DiagnosticCode.CONNECTION_COMPONENT_MISMATCH,
        DiagnosticCode.CONNECTION_COMPONENT_UNATTRIBUTED,
        DiagnosticCode.CAPABILITY_REACTIVE_BALANCE_REFUSED,
        DiagnosticCode.ORDER_CYCLE_DETECTED,
        DiagnosticCode.CONNECTION_CROSS_MODEL_REFUSED,
    ):
        for d in errors:
            if d.code.value == code:
                return d
    return errors[0]


def _dimensional(assessment_source: str) -> dict[str, Any]:
    """Dimensional compatibility, read off the mechanical outcome.

    ``assessment_source`` is the code that decided it, or "" when nothing
    mechanical fired. A semantic refusal does **not** make a connection
    dimensionally invalid: that is the whole point of the distinction.
    """
    if assessment_source in (
        DiagnosticCode.CONNECTION_QUANTITY_MISMATCH.value,
        DiagnosticCode.CONNECTION_UNIT_MISMATCH.value,
        DiagnosticCode.CONNECTION_NON_CONVERTIBLE.value,
        DiagnosticCode.VALUE_UNIT_UNREGISTERED.value,
        DiagnosticCode.CONNECTION_COMPONENT_MISMATCH.value,
        DiagnosticCode.CONNECTION_COMPONENT_UNATTRIBUTED.value,
    ):
        return {
            "result": "incompatible",
            "decided_by": assessment_source,
            "note": (
                "The engine's mechanical rules refused this before any "
                "compatibility policy was consulted."
            ),
        }
    if assessment_source in (
        DiagnosticCode.GRAPH_UNKNOWN_PORT.value,
        DiagnosticCode.GRAPH_UNKNOWN_INSTANCE.value,
        DiagnosticCode.CONNECTION_DIRECTION.value,
        DiagnosticCode.CONNECTION_SELF_LOOP.value,
        DiagnosticCode.ORDER_CYCLE_DETECTED.value,
        DiagnosticCode.CONNECTION_MISSING_REQUIRED.value,
    ):
        return {
            "result": "unknown",
            "decided_by": assessment_source,
            "note": (
                "The connection was refused on structure rather than on "
                "dimensions; no dimensional verdict is claimed here."
            ),
        }
    if not assessment_source or assessment_source in (
        DiagnosticCode.CONNECTION_CROSS_MODEL_REFUSED.value,
    ):
        return {
            "result": "compatible",
            "decided_by": (
                "composition.cross_model" if assessment_source
                else "engine.mechanical_checks"
            ),
            "note": (
                "Quantity, unit, direction and component identity all passed. "
                "This says the numbers can be written on the same axis; it says "
                "nothing about whether they mean the same thing."
                if not assessment_source else
                "The mechanical checks all passed -- which is why this connection "
                "is the dangerous kind. Quantity, unit, direction and component "
                "identity are satisfied; a compatibility rule rejects it anyway, "
                "on meaning."
            ),
        }
    return {"result": "unknown", "decided_by": assessment_source, "note": ""}


def _semantic(verdict: cross_model.Verdict | None) -> dict[str, Any]:
    if verdict is None:
        return {
            "result": "not_applicable",
            "rule": NOT_DOCUMENTED,
            "stance": NOT_DOCUMENTED,
            "reason": (
                "No cross-model compatibility rule is declared for this pair, or "
                "the engine's own rules already own it. That is not a scientific "
                "judgement in either direction."
            ),
            "evidence_basis": NOT_DOCUMENTED,
            "quantity_pair": None,
            "assumptions": [],
            "evidence": [],
            "unresolved": [],
            "remediation": NOT_DOCUMENTED,
        }
    return {
        "result": "permitted" if verdict.permitted else "refused",
        "rule": "composition.cross_model",
        "stance": verdict.stance,
        "reason": verdict.reason,
        "evidence_basis": verdict.evidence_basis,
        "quantity_pair": list(verdict.quantity_pair) if verdict.quantity_pair else None,
        "assumptions": list(verdict.assumptions),
        "evidence": list(verdict.evidence),
        "unresolved": list(verdict.unresolved),
        "remediation": verdict.remediation or NOT_DOCUMENTED,
    }


def disposition_for(
    blocking: ModelDiagnostic | None,
    verdict: cross_model.Verdict | None,
) -> str:
    """The one word, chosen so it cannot be mistaken for another.

    Public because it is part of the report's contract rather than an internal
    detail: the Godot panel keys its colours off these five, and a consumer
    deciding how to present a connection needs the mapping itself, not the
    sentence that produced it.
    """
    if blocking is None:
        # Nothing refused it. Either a rule permitted it, or no rule was asked
        # (a single-model graph, or a boundary the engine owns). A permitted
        # verdict carrying assumptions is the conditional case.
        if verdict is not None and verdict.permitted:
            return "permitted_conditionally" if verdict.assumptions else "permitted"
        if verdict is not None:
            return "unresolved" if verdict.evidence_basis == "evidence_limited" \
                else "scientifically_refused"
        return "permitted"

    if blocking.code is DiagnosticCode.CONNECTION_CROSS_MODEL_REFUSED:
        # The rule that fired carries its own basis, and an absence of a rule is
        # not a finding of incompatibility.
        if verdict is not None and verdict.evidence_basis == "evidence_limited":
            return "unresolved"
        return "scientifically_refused"

    return "mechanically_invalid"


def assess_connection(
    connection: Connection,
    source_manifest: ModelManifest | None,
    source_port: PortDefinition | None,
    target_manifest: ModelManifest | None,
    target_port: PortDefinition | None,
    diagnostics: Sequence[ModelDiagnostic],
) -> dict[str, Any]:
    """One connection's standing, described from what the engine already decided."""
    mine = _diagnostics_for(diagnostics, connection.connection_id)
    blocking = _most_specific(mine)

    verdict: cross_model.Verdict | None = None
    if source_manifest is not None and target_manifest is not None \
            and source_port is not None and target_port is not None:
        verdict = cross_model.check(
            source_model=source_manifest.model_id,
            source_port_id=source_port.port_id,
            source_quantity=source_port.quantity.value,
            target_model=target_manifest.model_id,
            target_port_id=target_port.port_id,
            target_quantity=target_port.quantity.value,
        )

    disposition = disposition_for(blocking, verdict)
    semantic = _semantic(verdict)
    blocking_code = str(blocking.code.value) if blocking is not None else ""

    return {
        "connection_id": connection.connection_id,
        "source": _port_block(
            connection.source.instance_id, source_manifest, source_port
        ),
        "destination": _port_block(
            connection.target.instance_id, target_manifest, target_port
        ),
        "dimensional": _dimensional(blocking_code),
        "semantic": semantic,
        "disposition": disposition,
        "disposition_explanation": _explain(disposition, blocking, semantic),
        "diagnostic": _diagnostic_block(blocking.to_dict() if blocking is not None else None),
        "evidence": semantic["evidence"],
        "assumptions": semantic["assumptions"],
        "unresolved": semantic["unresolved"],
        "remediation": semantic["remediation"],
        "other_diagnostics": [d.to_dict() for d in mine if d is not blocking],
    }


def _explain(
    disposition: str,
    blocking: ModelDiagnostic | None,
    semantic: Mapping[str, Any],
) -> str:
    """One sentence a reader can act on, chosen by disposition."""
    if disposition == "mechanically_invalid":
        return (
            "The engine's own contract rules refused this connection. That is a "
            "statement about shapes, units and identifiers -- not about whether "
            "the two models could scientifically be connected."
        )
    if disposition == "scientifically_refused":
        return (
            "Nothing mechanical objected. A declared compatibility rule rejects "
            "it, with cited evidence: the quantities match and the connection "
            "still would not mean anything."
        )
    if disposition == "unresolved":
        if str(semantic.get("evidence_basis")) == "evidence_limited":
            return (
                "Nothing mechanical objected, and no rule classifies this pair. "
                "The policy refuses it because it fails closed. This is an "
                "absence of a documented judgement, NOT a finding that the two "
                "quantities are physically incompatible."
            )
        return (
            "No rule reached a verdict and nothing mechanical objected. The "
            "available evidence does not support either a confident acceptance "
            "or a definitive incompatibility claim."
        )
    if disposition == "permitted_conditionally":
        return (
            "Permitted under the assumptions listed below. Those assumptions "
            "are the load-bearing part of this connection; a matching unit does "
            "not discharge them."
        )
    return (
        "No rule objected and no mechanical constraint failed. That is a "
        "statement about the connection's form, not about the science."
    )


# --------------------------------------------------------------------------- #
# scientific limitations
# --------------------------------------------------------------------------- #


def _validation_status(instance_id: str, result: Any) -> dict[str, Any]:
    """What the model itself says about its own scientific standing.

    Only Ganjave publishes a claim through the composition boundary. For every
    other model this returns ``not_documented``, which is the honest answer: an
    absent claim is not an absence of validation, and it is not a presence of
    it either.
    """
    claimed: dict[str, Any] = {}
    for output in getattr(result, "outputs", ()) if result is not None else ():
        extra = output.value.extra or {}
        claim = extra.get("validation_claim")
        if isinstance(claim, Mapping) and claim:
            claimed = dict(claim)
            break

    implementation = str(claimed.get("implementation_status", "") or NOT_DOCUMENTED)
    reproduction = str(claimed.get("reproduction_status", "") or NOT_DOCUMENTED)
    return {
        "instance_id": instance_id,
        "model_id": NOT_DOCUMENTED if result is None else result.model_id,
        "model_version": NOT_DOCUMENTED if result is None else result.model_version,
        "implementation_status": implementation,
        "reproduction_status": reproduction,
        "source": (
            "the model's own validation_claim, carried through the boundary"
            if claimed else NOT_DOCUMENTED
        ),
        "basis": (
            "A model that publishes no validation claim through this boundary "
            "is reported as not documented. This is neither a validated model "
            "nor an unvalidated one."
            if not claimed else ""
        ),
    }


def _limitations(manifest: ModelManifest | None) -> dict[str, Any]:
    if manifest is None:
        return {
            "declared_unsupported_capabilities": [],
            "declared_missing_information": [],
            "declared_missing_models": [],
            "assumptions": [],
            "source": NOT_DOCUMENTED,
        }
    return {
        "declared_unsupported_capabilities": sorted(
            manifest.unsupported_capabilities.keys()
        ),
        "declared_missing_information": [
            dict(item) for item in manifest.missing_information
        ],
        "declared_missing_models": [
            dict(item) for item in manifest.parameter_sections.get(
                "declared missing models", ()
            )
        ],
        "assumptions": [
            dict(item) for item in manifest.assumptions
        ],
        "source": "the model's own manifest, as published through --describe-model",
    }


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #


def build_report(
    graph: Any,
    loaded: Mapping[str, Any],
    diagnostics: Sequence[ModelDiagnostic],
    result: Any = None,
    *,
    execution_attempted: bool | None = None,
    plan_only: bool = False,
    previous_results_invalidated: bool = False,
) -> dict[str, Any]:
    """Assemble the whole report.

    A pure description of what happened. ``graph`` is the ``CompositionGraph``
    the runner was handed, ``loaded`` maps instance id to
    ``ValidatedInstance``, and ``result`` is the ``CompositionResult`` when one
    was produced and ``None`` when the graph never got that far.
    """
    graph_id = str(getattr(graph, "graph_id", "") or "unnamed")
    title = str(getattr(graph, "title", "") or "")
    notes = str(getattr(graph, "notes", "") or "")
    instances = list(getattr(graph, "instances", ()) or ())
    connections = list(getattr(graph, "connections", ()) or ())

    assessments: list[dict[str, Any]] = []
    for connection in connections:
        source_entry = loaded.get(connection.source.instance_id)
        target_entry = loaded.get(connection.target.instance_id)
        source_manifest = getattr(source_entry, "manifest", None)
        target_manifest = getattr(target_entry, "manifest", None)
        source_port = _port_of(source_manifest, connection.source.port_id)
        target_port = _port_of(target_manifest, connection.target.port_id)
        assessments.append(
            assess_connection(
                connection, source_manifest, source_port,
                target_manifest, target_port, diagnostics,
            )
        )

    attempted = (
        bool(result is not None and getattr(result, "results", ()))
        if execution_attempted is None
        else execution_attempted
    )

    by_instance: dict[str, Any] = {}
    for instance in instances:
        by_instance[_field(instance, "instance_id", "")] = None
    if result is not None:
        for entry in result.results:
            by_instance[entry.instance_id] = entry

    science_rows: list[dict[str, Any]] = []
    for instance in instances:
        instance_id = _field(instance, "instance_id", "")
        entry = loaded.get(instance_id)
        manifest = getattr(entry, "manifest", None)
        row = _validation_status(instance_id, by_instance.get(instance_id))
        row["model_id"] = _field(instance, "model_id", NOT_DOCUMENTED)
        row["model_version"] = _field(instance, "model_version", NOT_DOCUMENTED)
        row["limitations"] = _limitations(manifest)
        science_rows.append(row)

    return {
        "schema": REPORT_SCHEMA,
        "reading_guide": {
            "dispositions": list(DISPOSITIONS),
            "note": (
                "Mechanical validity, semantic compatibility, execution success "
                "and scientific validation are four different questions. None of "
                "them answers any of the others, and the report never lets one "
                "stand in for another."
            ),
            "not_documented": NOT_DOCUMENTED,
        },
        "graph": {
            "graph_id": graph_id,
            "title": title or NOT_DOCUMENTED,
            "notes": notes or NOT_DOCUMENTED,
            "instances": [
                {
                    "instance_id": _field(i, "instance_id", ""),
                    "model_id": _field(i, "model_id", NOT_DOCUMENTED),
                    "model_version": _field(i, "model_version", NOT_DOCUMENTED),
                    "label": _field(i, "label", "") or NOT_DOCUMENTED,
                }
                for i in instances
            ],
            "connection_count": len(connections),
        },
        "execution": _execution_block(
            result, attempted, previous_results_invalidated, plan_only
        ),
        "connections": assessments,
        "science": {
            "models": science_rows,
            "combined_graph": _combined_graph_block(result, diagnostics),
        },
    }


def _execution_block(
    result: Any, attempted: bool, invalidated: bool, plan_only: bool
) -> dict[str, Any]:
    if result is None:
        return {
            "attempted": False,
            "status": NOT_DOCUMENTED,
            "results_produced": False,
            "result_count": 0,
            "run_id": NOT_DOCUMENTED,
            "reproducibility": NOT_DOCUMENTED,
            "error_count": 0,
            "warning_count": 0,
            "results_invalidated": invalidated,
            "plan_only": plan_only,
            "note": (
                "No execution was attempted, so this report describes the graph "
                "and its connections only. It says nothing about whether the "
                "graph would have run."
            ),
        }
    errors = [d for d in result.diagnostics if d.severity is Severity.ERROR]
    warnings = [d for d in result.diagnostics if d.severity is Severity.WARNING]
    note = ""
    if plan_only:
        # Validated and ordered, then deliberately stopped. Every connection's
        # standing below is real; only the run is missing, and the report has
        # to say which of the two is missing so "no results" is not read as
        # "nothing permitted".
        note = (
            "This was a plan-only run: the graph validated and was ordered, but "
            "nothing was executed. Every connection below was assessed; no "
            "result here comes from a model."
        )
    elif not result.results:
        # "No results" has three quite different causes and the reader needs to
        # know which. Saying "refused" to a graph that was simply empty would be
        # a claim nobody made.
        if errors:
            note = (
                "No model executed. The graph was refused before execution, which "
                "is a statement about the graph and not about the models "
                "themselves."
            )
        elif not attempted:
            note = (
                "Nothing was executed, so this run says nothing about whether the "
                "graph would execute."
            )
        else:
            note = (
                "The graph is valid and was run, but it contains no instance, so "
                "there is nothing to execute and nothing to report."
            )
    elif warnings:
        note = (
            "Every instance ran. The warnings are findings about the sources or "
            "the models, not failures of the composition."
        )
    return {
        "attempted": attempted,
        "status": result.status.value,
        "results_produced": bool(result.results),
        "result_count": len(result.results),
        "run_id": result.run_id,
        "reproducibility": result.reproducibility or NOT_DOCUMENTED,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "results_invalidated": invalidated,
        "plan_only": plan_only,
        "note": note or NOT_DOCUMENTED,
    }


def _combined_graph_block(
    result: Any, diagnostics: Sequence[ModelDiagnostic]
) -> dict[str, Any]:
    """The status of the *combination*, which never inherits its parts' status.

    Composing two models produces a system no source has evaluated. A
    ``success`` here means the arithmetic ran; it is not a scientific claim
    about the combined process, and this block refuses to become one.
    """
    return {
        "independently_validated": False,
        "status": "not_established",
        "basis": (
            "Composing these models produces a system that no published source "
            "has evaluated. Validation evidence for an individual model is a "
            "statement about that model and does not transfer to the "
            "composition, so the combined graph starts from 'not established' "
            "and can only be changed by an independent evaluation."
        ),
        "execution_is_not_validation": (
            "A successful execution is evidence that the pipeline works. It is "
            "not evidence that the numbers are right, and nothing in this report "
            "upgrades a model's reproduction_status because a test passed."
        ),
        "resolved_by_diagnostics": sorted({
            d.code.value for d in diagnostics
            if d.severity is Severity.ERROR
        }),
    }


def empty_report(
    graph_id: str, reason: str, diagnostics: Sequence[ModelDiagnostic] = ()
) -> dict[str, Any]:
    """The report for a graph that never reached the engine.

    Produced when the document could not be parsed or did not satisfy the
    contract. There is nothing to assess, and saying so is better than emitting
    a report full of empty rows that would read as a clean run.
    """
    return {
        "schema": REPORT_SCHEMA,
        "reading_guide": {
            "dispositions": list(DISPOSITIONS),
            "note": "No connection was assessed: the graph never reached the engine.",
            "not_documented": NOT_DOCUMENTED,
        },
        "graph": {
            "graph_id": graph_id,
            "title": NOT_DOCUMENTED,
            "notes": reason,
            "instances": [],
            "connection_count": 0,
        },
        "execution": {
            "attempted": False,
            "status": NOT_DOCUMENTED,
            "results_produced": False,
            "result_count": 0,
            "run_id": NOT_DOCUMENTED,
            "reproducibility": NOT_DOCUMENTED,
            "error_count": len([d for d in diagnostics if d.severity is Severity.ERROR]),
            "warning_count": len([d for d in diagnostics if d.severity is Severity.WARNING]),
            "results_invalidated": False,
            "plan_only": False,
            "note": reason,
        },
        "connections": [],
        "science": {
            "models": [],
            "combined_graph": _combined_graph_block(None, diagnostics),
        },
    }


def _field(instance: Any, name: str, default: Any = NOT_DOCUMENTED) -> Any:
    """One field of an instance, whatever shape it arrives in.

    ``CompositionGraph.instances`` holds ``ModelInstance`` dataclasses, but a
    caller reconstructing a graph from a document may hand over mappings. Both
    are read the same way so neither has to be special-cased by the caller.
    """
    if isinstance(instance, Mapping):
        value = instance.get(name, None)
    else:
        value = getattr(instance, name, None)
    return default if value is None else str(value)


def _port_of(manifest: ModelManifest | None, port_id: str) -> PortDefinition | None:
    if manifest is None:
        return None
    try:
        return manifest.port(port_id)
    except KeyError:
        return None