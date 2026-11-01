"""Adapter for the Morris, Geiger & Fine (2011) material balance engine.

The adapter is a translator, not a solver.  It turns a JSON control-volume
declaration into a `BalanceSystem`, calls `solve_balance`, and turns the
`BalanceResult` back into port values.  Every number it publishes came out of
the engine; the only arithmetic it performs itself is the stream total, which is
the sum of the engine's own ledger rows and is labelled as such.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import (
    ModelInput,
    ModelManifest,
    ModelOutput,
    PortDefinition,
    PortDirection,
    PortRef,
    ProvenanceRecord,
    ProvenanceRequirement,
    ResidualReport,
    TemporalBasis,
    ValueProvenance,
    ValueState,
    ModelValue,
)
from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from ..dimensions import QUANTITY_TO_MORRIS_KIND
from ..quantities import Quantity, REGISTRY
from .base import AdapterRun, JsonWorker, ModelAdapter

MODEL_ID = "morris2011.material_balance"
MODEL_VERSION = "0.1.0"


class MorrisAdapter(ModelAdapter):
    model_id = MODEL_ID
    model_version = MODEL_VERSION
    parameters_key = "system"

    def __init__(self, worker: JsonWorker) -> None:
        super().__init__(worker)

    # -- manifest ------------------------------------------------------------

    def manifest(
        self, parameters: Mapping[str, Any]
    ) -> tuple[ModelManifest | None, list[ModelDiagnostic]]:
        spec = parameters.get(self.parameters_key)
        if not spec:
            return None, [
                ModelDiagnostic(
                    code=DiagnosticCode.MANIFEST_INVALID,
                    severity=Severity.ERROR,
                    message=(
                        f"instance parameters must contain a 'system' declaration "
                        f"for {MODEL_ID}; got keys {sorted(parameters)}"
                    ),
                    where=("manifest", MODEL_ID),
                    origin=Origin.MANIFEST,
                    remediation=(
                        "Add a 'system' block with system_id, process_mode, basis, "
                        "components and streams."
                    ),
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                )
            ]
        response = self.worker.call({"op": "manifest", "system": spec})
        if not response.ok:
            return None, [response.error_diagnostic(MODEL_ID, MODEL_ID, MODEL_VERSION)]
        return self._to_manifest(response.payload["manifest"]), []

    @staticmethod
    def _to_manifest(payload: Mapping[str, Any]) -> ModelManifest:
        ports: list[PortDefinition] = []
        for item in payload.get("ports", ()):
            quantity = Quantity(item["quantity"])
            ports.append(
                PortDefinition(
                    port_id=item["port_id"],
                    direction=PortDirection(item["direction"]),
                    quantity=quantity,
                    unit=item.get("unit", ""),
                    label=item.get("label", ""),
                    component=item.get("component"),
                    components=tuple(item.get("components", ()) or ()),
                    temporal_basis=TemporalBasis(item.get("temporal_basis",
                                                           "not_applicable")),
                    required=bool(item.get("required", False)),
                    provenance_requirement=ProvenanceRequirement(
                        item.get("provenance_requirement", "explained")
                    ),
                    attribution_required=bool(
                        item.get("attribution_required", False)
                    ),
                    solvable=bool(item.get("solvable", False)),
                    unavailable_reason=item.get("unavailable_reason", ""),
                    description=item.get("description", ""),
                    metadata=dict(item.get("metadata", {})),
                )
            )
        return ModelManifest(
            model_id=payload["model_id"],
            model_version=payload["model_version"],
            title=payload.get("title", ""),
            summary=payload.get("summary", ""),
            adapter=payload.get("adapter", ""),
            contract_version=payload.get("contract_version", "0.1.0"),
            source_ref=payload.get("source_ref", ""),
            ports=tuple(ports),
            parameters=dict(payload.get("parameters", {})),
            parameter_sections=dict(payload.get("parameter_sections", {})),
            capabilities=tuple(payload.get("capabilities", ())),
            unsupported_capabilities=dict(payload.get("unsupported_capabilities", {})),
            reaction_terms=tuple(payload.get("reaction_terms", ())),
            conversion_models=tuple(payload.get("conversion_models", ())),
            non_reacting_only=bool(payload.get("non_reacting_only", False)),
            assumptions=tuple(payload.get("assumptions", ())),
            missing_information=tuple(payload.get("missing_information", ())),
        )

    # -- run -----------------------------------------------------------------

    def run(
        self,
        instance_id: str,
        parameters: Mapping[str, Any],
        inputs: Mapping[str, ModelOutput],
        literal_inputs: Mapping[str, ModelInput],
    ) -> AdapterRun:
        spec = dict(parameters.get(self.parameters_key) or {})

        #: port id -> the Morris slot it fills, e.g. ``in:A:Cu`` -> ``A:component:Cu``
        slot_map = self._slot_map(spec)

        injected: dict[str, Any] = {}
        transfer_chain: dict[str, tuple[ProvenanceRecord, ...]] = {}
        diagnostics: list[ModelDiagnostic] = []

        #: port_id -> (connected output, None, None) or (None, literal, None)
        supplied: dict[str, tuple[ModelOutput | None, ModelInput | None, None]] = {
            port_id: (output, None, None) for port_id, output in inputs.items()
        }
        for port_id, model_input in literal_inputs.items():
            supplied[port_id] = (None, model_input, None)

        for port_id, (output, literal, _c) in sorted(supplied.items()):
            slot = slot_map.get(port_id)
            if slot is None:
                continue
            if output is not None:
                value = output.value
                if not value.is_resolved:
                    reason = value.reason or "no reason recorded"
                    diagnostics.append(
                        ModelDiagnostic(
                            code=DiagnosticCode.CONNECTION_CARRIES_UNRESOLVED,
                            severity=Severity.ERROR,
                            message=(
                                f"{output.ref.key} carries a value in state "
                                f"{value.state.value!r} ({reason}), so it was not "
                                f"injected into {instance_id}. An unresolved value "
                                f"is never coerced to make a system solvable."
                            ),
                            where=("instance", instance_id, "port", port_id),
                            origin=Origin.EXECUTION,
                            remediation=(
                                "Resolve the upstream port, or remove the "
                                "connection."
                            ),
                            model_id=MODEL_ID,
                            model_version=MODEL_VERSION,
                        )
                    )
                    continue
                record = {
                    "quantity_id": f"{slot}:{port_id}",
                    "value": float(value.value),
                    "unit": value.unit,
                    "kind": QUANTITY_TO_MORRIS_KIND[value.quantity],
                    "provenance": "derived",
                    "source_ref": (
                        f"supplied by the composition layer from "
                        f"{output.ref.key}"
                    ),
                    "derivation": (
                        "composition input; see the composition provenance index"
                    ),
                }
                transfer_chain[port_id] = output.provenance_chain
                diagnostics.extend(self._provenance_notes(output, port_id,
                                                          instance_id))
            else:
                assert literal is not None
                value = literal.value
                if not value.is_resolved:
                    reason = value.reason or "no reason recorded"
                    diagnostics.append(
                        ModelDiagnostic(
                            code=DiagnosticCode.VALUE_UNRESOLVED,
                            severity=Severity.ERROR,
                            message=(
                                f"the literal input {literal.ref.key} is in state "
                                f"{value.state.value!r} ({reason}), so nothing was "
                                f"injected into {instance_id}."
                            ),
                            where=("instance", instance_id, "port", port_id),
                            origin=Origin.EXECUTION,
                            model_id=MODEL_ID,
                            model_version=MODEL_VERSION,
                        )
                    )
                    continue
                record = {
                    "quantity_id": f"{slot}:{port_id}",
                    "value": float(value.value),
                    "unit": value.unit,
                    "kind": QUANTITY_TO_MORRIS_KIND[value.quantity],
                    "provenance": "derived",
                    "source_ref": literal.ref.key,
                    "derivation": "literal input declared on the composition graph",
                }

            try:
                self._check_injection_unit(value)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_UNIT_MISMATCH,
                        severity=Severity.ERROR,
                        message=str(exc),
                        where=("instance", instance_id, "port", port_id),
                        origin=Origin.EXECUTION,
                        model_id=MODEL_ID,
                        model_version=MODEL_VERSION,
                    )
                )
                continue
            injected[slot] = record

        response = self.worker.call(
            {"op": "run", "system": spec, "inputs": injected}
        )
        if not response.ok:
            return AdapterRun(
                outputs=(),
                diagnostics=(
                    tuple(diagnostics)
                    + (response.error_diagnostic(instance_id, MODEL_ID,
                                                 MODEL_VERSION),)
                ),
                summary=response.payload.get("summary", {}),
            )

        payload = response.payload
        summary = payload.get("summary", {})
        manifest_payload = payload.get("manifest", {})

        if not response.ok:
            # The engine ran and reported that it solved nothing (an
            # inconsistent system), or it raised. Either way there are outputs
            # to publish -- all unresolved -- and the diagnostics that say why.
            diagnostics.extend(
                _morris_diagnostic(raw, instance_id)
                for raw in payload.get("diagnostics", ())
            )
            published = tuple(
                ModelOutput(
                    ref=PortRef(instance_id, item["port_id"]),
                    value=self._to_value(item),
                    provenance_chain=(
                        ProvenanceRecord(
                            kind="gap",
                            producer_model=MODEL_ID,
                            producer_version=MODEL_VERSION,
                            where=f"instance:{instance_id}",
                            detail=(
                                "the balance solved nothing, so this port carries "
                                "no value"
                            ),
                        ),
                    ),
                )
                for item in payload.get("outputs", ())
            )
            return AdapterRun(
                outputs=published,
                diagnostics=tuple(diagnostics),
                unresolved=tuple(summary.get("unresolved", ())),
                summary=summary,
            )

        origin = ProvenanceRecord(
            kind="source",
            producer_model=MODEL_ID,
            producer_version=MODEL_VERSION,
            where=f"instance:{instance_id}",
            detail=(
                f"solve_balance on {summary.get('system_id')} "
                f"({summary.get('process_mode')}, basis {summary.get('basis')})"
            ),
            method=(
                "Morris, Geiger & Fine (2011), Chapter 4: conservation equations "
                "generated for the declared process mode, solved by Gauss-Jordan "
                "with partial pivoting"
            ),
        )

        outputs: list[ModelOutput] = []
        residuals: list[ResidualReport] = []
        seen: set[str] = set()
        for item in payload.get("outputs", ()):
            port_id = item["port_id"]
            if port_id in seen:
                continue
            seen.add(port_id)
            # A value that arrived at this instance through a connection keeps
            # the record of where it came from. The match is the *same declared
            # variable on the same stream* -- `in:A:w:Cu` -> `out:A:w:Cu` -- and
            # nothing else. Where an output has no injected counterpart the
            # chain is left alone rather than assuming a dependency that was
            # never computed: a solved total is not credited to whatever
            # happened to be fed in, because this engine does not publish a
            # dependency map and inventing one would assert a provenance it
            # cannot show.
            carried = _carried_chains(spec, transfer_chain, port_id)
            chain = carried + (origin,) if carried else (origin,)
            extra = item.get("extra") or {}
            if "within_tolerance" in extra and port_id.startswith("out:residual:"):
                residuals.append(
                    ResidualReport(
                        label=port_id.split(":", 2)[2].replace("_", " "),
                        value=float(item["value"]),
                        unit=item.get("unit", ""),
                        tolerance=float(extra.get("tolerance", 0.0)),
                        within_tolerance=bool(extra["within_tolerance"]),
                        quantity=_quantity_from_morris_kind(item.get("kind", "mass")),
                        component=(item.get("components") or [None])[0],
                        contributions=tuple(extra.get("contributions", ())),
                    )
                )
            outputs.append(
                ModelOutput(
                    ref=PortRef(instance_id, port_id),
                    value=self._to_value(item),
                    provenance_chain=chain,
                )
            )

        for raw in payload.get("diagnostics", ()):
            diagnostics.append(_morris_diagnostic(raw, instance_id))

        # CG-07: a slot the declaration left unknown and the balance could not
        # determine stays unknown. It is never written as a zero, and the fact
        # that it is still missing after a *successful* solve is worth saying.
        for item in summary.get("unresolved", ()):
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.EXECUTION_UNDERDETERMINED,
                    severity=Severity.WARNING,
                    message=(
                        f"{item.get('variable_id')} was left unknown by the "
                        f"declaration and is still not determined: "
                        f"{item.get('reason')}"
                    ),
                    where=("instance", instance_id),
                    origin=Origin.MORRIS,
                    remediation=(
                        "Supply the measurement, or declare an assumption that "
                        "closes the gap. Morris et al. 2011 sec. 4.7.2 requires the "
                        "degrees of freedom to be accounted for explicitly; a free "
                        "variable is never reported as a solved zero."
                    ),
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                    detail={"variable_id": item.get("variable_id")},
                )
            )

        for residual in residuals:
            if not residual.within_tolerance:
                diagnostics.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.EXECUTION_RESIDUAL_OUT_OF_TOLERANCE,
                        severity=Severity.WARNING,
                        message=(
                            f"the {residual.label} residual is {residual.value:g} "
                            f"{residual.unit}, outside its tolerance of "
                            f"{residual.tolerance:g} {residual.unit}."
                        ),
                        where=("instance", instance_id),
                        origin=Origin.MORRIS,
                        remediation=(
                            "Inspect the per-equation residuals in the results "
                            "panel. Morris et al. 2011 sec. 4.6.2 treats a "
                            "non-closing check as a finding."
                        ),
                        model_id=MODEL_ID,
                        model_version=MODEL_VERSION,
                    )
                )

        return AdapterRun(
            outputs=tuple(outputs),
            diagnostics=tuple(diagnostics),
            residuals=tuple(residuals),
            unresolved=tuple(summary.get("unresolved", ())),
            summary={
                **summary,
                "equations": [
                    {
                        "equation_id": e["equation_id"],
                        "label": e["label"],
                        "expression": e["expression"],
                        "source_ref": e.get("source_ref"),
                        "process_mode": e.get("process_mode"),
                    }
                    for e in summary.get("equations", ())
                ],
            },
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _slot_map(spec: Mapping[str, Any]) -> dict[str, str]:
        """Composition port id -> Morris slot key (``<stream>:<slot>``)."""
        out: dict[str, str] = {}
        for stream in spec.get("streams", ()):
            sid = stream["stream_id"]
            if stream.get("amount"):
                out[f"in:{sid}:total"] = f"{sid}:total"
            for cid in (stream.get("mass_fractions") or {}):
                out[f"in:{sid}:w:{cid}"] = f"{sid}:fraction:{cid}"
            for cid in (stream.get("component_amounts") or {}):
                out[f"in:{sid}:{cid}"] = f"{sid}:component:{cid}"
        return out

    @staticmethod
    def _check_injection_unit(value: ModelValue) -> None:
        if value.quantity in (Quantity.MASS, Quantity.MASS_FLOW, Quantity.AMOUNT,
                              Quantity.AMOUNT_FLOW, Quantity.MASS_FRACTION):
            REGISTRY.resolve(value.unit, value.quantity)

    @staticmethod
    def _to_value(item: Mapping[str, Any]) -> ModelValue:
        kind = item.get("kind") or ""
        quantity = (
            _quantity_from_morris_kind(kind) if kind else Quantity.DIMENSIONLESS
        )
        state = item.get("state", "unresolved")
        components = tuple(item.get("components", ()) or ())
        source_ref = item.get("source_ref")
        method = item.get("method")
        extra = dict(item.get("extra", {}) or {})

        if state == "number":
            provenance = (
                ValueProvenance.DERIVED
                if "solved" in (method or "")
                else ValueProvenance.REPORTED
                if source_ref and "declared" in (method or "")
                else ValueProvenance.DERIVED
            )
            return ModelValue.number(
                float(item["value"]),
                quantity=quantity,
                unit=item.get("unit", ""),
                provenance=provenance,
                components=components,
                source_ref=source_ref,
                method=method,
                extra=extra,
            )
        if state == "range":
            return ModelValue.unavailable(
                ValueState.RANGE,
                quantity=quantity,
                reason=item.get("reason", ""),
                unit=item.get("unit", ""),
                components=components,
                extra=extra,
            )
        if state == "not_reported":
            return ModelValue.unavailable(
                ValueState.NOT_REPORTED,
                quantity=quantity,
                reason=item.get("reason", "the model does not report this"),
                unit=item.get("unit", ""),
                components=components,
                extra=extra,
            )
        return ModelValue.unavailable(
            ValueState.UNRESOLVED,
            quantity=quantity,
            reason=item.get("reason", "the balance did not determine this value"),
            unit=item.get("unit", ""),
            components=components,
            extra=extra,
        )

    @staticmethod
    def _provenance_notes(
        output: ModelOutput, port_id: str, instance_id: str
    ) -> list[ModelDiagnostic]:
        notes: list[ModelDiagnostic] = []
        upstream = output.value.provenance
        if upstream is ValueProvenance.UNKNOWN:
            notes.append(
                ModelDiagnostic(
                    code=DiagnosticCode.VALUE_UNKNOWN,
                    severity=Severity.WARNING,
                    message=(
                        f"{output.ref.key} supplied {instance_id}/{port_id} with a "
                        f"quantity the source model declares unknown."
                    ),
                    where=("instance", instance_id, "port", port_id),
                    origin=Origin.EXECUTION,
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                )
            )
        return notes


def _carried_chains(
    spec: Mapping[str, Any],
    transfer_chain: Mapping[str, tuple[ProvenanceRecord, ...]],
    port_id: str,
) -> tuple[ProvenanceRecord, ...]:
    """The chain an output inherits, when it is literally the value that came in.

    Morris publishes ``out:<stream>:<component>`` and ``out:<stream>:w:<component>``
    and accepts ``in:<stream>:<component>`` and ``in:<stream>:w:<component>``.
    For those, the output *is* the injected value re-published, so the upstream
    record travels with it.

    A stream **total** is deliberately excluded. ``out:<stream>:total`` is the
    sum the balance computes, and crediting it to an upstream total would assert
    that the sum equals what was fed in -- which is the thing a material balance
    exists to test, not to assume. A balance that did not close would still
    carry the upstream chain, and the evidence for closure would be gone.

    Nothing else gets a chain either: where an output has no injected
    counterpart, the record names only this instance, because this adapter
    computes no dependency map and inventing one would assert a provenance it
    cannot show.
    """
    if not port_id.startswith("out:"):
        return ()
    parts = port_id.split(":")
    # out:<stream>:<component> -> 3 parts; out:<stream>:w:<component> -> 4.
    if len(parts) == 3 and parts[2] != "total":
        pass                                            # a component amount
    elif len(parts) == 4 and parts[2] == "w":
        pass                                            # a mass fraction
    else:
        return ()                                       # the stream total, or something else
    mirror = "in:" + port_id[len("out:"):]
    if mirror not in transfer_chain:
        return ()
    if MorrisAdapter._slot_map(spec).get(mirror) is None:
        return ()
    return tuple(transfer_chain[mirror])


def _quantity_from_morris_kind(kind: str) -> Quantity:
    from ..dimensions import MORRIS_KIND_TO_QUANTITY

    return MORRIS_KIND_TO_QUANTITY.get(kind, Quantity.DIMENSIONLESS)


def _morris_diagnostic(
    raw: Mapping[str, Any], instance_id: str
) -> ModelDiagnostic:
    severity = Severity(raw.get("severity", "info"))
    return ModelDiagnostic(
        code=_morris_code(raw.get("code", "execution.model_failed")),
        severity=severity,
        message=raw.get("message", ""),
        where=("instance", instance_id, *(raw.get("where", ()) or ())),
        origin=Origin.MORRIS,
        remediation=_MORRIS_REMEDIATION.get(raw.get("code", ""), ""),
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        detail={"morris_code": raw.get("code", "")},
    )


_MORRIS_REMEDIATION = {
    "system.inconsistent": (
        "The declared measurements contradict each other. Section 4.7 requires a "
        "judgement about which reading is least accurate; nothing is solved until "
        "that judgement is made and the data are corrected at source."
    ),
    "system.underdetermined": (
        "Supply one more measurement or declare one more assumption. A free "
        "variable is never reported as a solved zero."
    ),
    "system.overconstrained": (
        "Some equations are dependent on the others. They are consistent, so the "
        "balance still closes, but they add no independent information "
        "(sec. 4.6.2). Remove one of the dependent equations to reduce the count."
    ),
    "balance.non_linear_skipped": (
        "Declare this stream's component amounts directly, or accept that the "
        "component is unbalanced. No conservation law was dropped silently."
    ),
    "balance.total_not_generated": (
        "Streams given as component amounts carry no declared total. Declare them "
        "by total plus composition if a total balance is required."
    ),
    "stream.component_absent": (
        "List the component in `absent_components` if its absence is deliberate."
    ),
}

#: Morris diagnostic codes mapped onto contract codes. Unknown codes keep their
#: text but are attributed to the Morris layer, never to composition.
_MORRIS_CODE_MAP = {
    "system.inconsistent": DiagnosticCode.EXECUTION_INCONSISTENT,
    "system.underdetermined": DiagnosticCode.EXECUTION_UNDERDETERMINED,
    "system.overconstrained": DiagnosticCode.EXECUTION_OVERCONSTRAINED,
    "balance.non_linear_skipped": DiagnosticCode.CAPABILITY_UNSUPPORTED,
    "balance.total_not_generated": DiagnosticCode.CAPABILITY_UNSUPPORTED,
    "stream.internal_cancels": DiagnosticCode.CAPABILITY_UNSUPPORTED,
    "variable.internal_cancels": DiagnosticCode.CAPABILITY_UNSUPPORTED,
}


def _morris_code(code: str) -> DiagnosticCode:
    return _MORRIS_CODE_MAP.get(code, DiagnosticCode.EXECUTION_MODEL_FAILED)