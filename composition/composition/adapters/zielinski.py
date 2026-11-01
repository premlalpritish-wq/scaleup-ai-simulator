"""Adapter for the Zielinski et al. (2019) recombinant insulin process model.

The model is a complete process graph with its own execution engine, so the
adapter's job is to expose its quantities as ports and to pass its execution
modes through unchanged:

* ``evidence_replay`` restates the paper's reported numbers and applies the
  accounting identities the paper supports.  It is a transcription, not a
  simulation, and the results panel says so.
* ``predictive`` starts from declared inputs and **fails closed**.  With no
  inputs it resolves 0 of 23 targets, which is the designed outcome and is
  reported as such rather than as an empty result.

The model has no component identity anywhere (see ``COMPOSITION_AUDIT.md``
section 4.1), so every port here publishes ``components=()`` and the engine
refuses to attach one to a component-declared control volume.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import (
    ModelInput,
    ModelManifest,
    ModelOutput,
    PortDefinition,
    PortDirection,
    PortRef,
    ProvenanceRecord,
    TemporalBasis,
    ValueProvenance,
    ValueState,
    ModelValue,
)
from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from ..dimensions import quantity_for_zielinski_dimension
from ..quantities import Quantity, REGISTRY
from .base import AdapterRun, JsonWorker, ModelAdapter

MODEL_ID = "zielinski2019.rhi_process"
MODEL_VERSION = "1.0.0"


class ZielinskiAdapter(ModelAdapter):
    model_id = MODEL_ID
    model_version = MODEL_VERSION
    parameters_key = "execution"

    def __init__(self, worker: JsonWorker) -> None:
        super().__init__(worker)

    # -- manifest ------------------------------------------------------------

    def manifest(
        self, parameters: Mapping[str, Any]
    ) -> tuple[ModelManifest | None, list[ModelDiagnostic]]:
        response = self.worker.call({"op": "manifest"})
        if not response.ok:
            return None, [response.error_diagnostic(MODEL_ID, MODEL_ID, MODEL_VERSION)]
        return self._to_manifest(response.payload["manifest"]), []

    @staticmethod
    def _to_manifest(payload: Mapping[str, Any]) -> ModelManifest:
        ports: list[PortDefinition] = []
        for item in payload.get("ports", ()):
            unit = item.get("unit", "")
            dimension = item.get("dimension", "")
            quantity = quantity_for_zielinski_dimension(dimension, unit)
            unavailable = ""
            if quantity is None:
                unavailable = (
                    f"the model declares dimension {dimension or '(none)'!r} for "
                    f"unit {unit!r}, which this contract does not define. The port "
                    f"is published so the gap is visible, and it cannot be connected."
                )
            else:
                try:
                    REGISTRY.resolve(unit, quantity)
                except Exception as exc:  # noqa: BLE001
                    unavailable = (
                        f"unit {unit!r} is not registered for quantity "
                        f"{quantity.value!r} in this contract: {exc}"
                    )
            if item.get("state") == "unknown" and not unavailable:
                unavailable = ""
            ports.append(
                PortDefinition(
                    port_id=item["port_id"],
                    direction=PortDirection(item["direction"]),
                    quantity=quantity or Quantity.DIMENSIONLESS,
                    unit=unit,
                    label=item.get("label", ""),
                    component=None,
                    components=(),
                    temporal_basis=_temporal_basis(item, dimension),
                    required=False,
                    provenance_requirement=ModelAdapter._requirements_from_provenance(
                        item.get("provenance", "unknown")
                    ),
                    attribution_required=False,
                    solvable=False,
                    unavailable_reason=unavailable,
                    description=item.get("reason", "") or item.get("notes", ""),
                    metadata={
                        "role": item.get("role", ""),
                        "location": item.get("location", ""),
                        "provenance": item.get("provenance", ""),
                        "basis": item.get("basis", ""),
                        "state": item.get("state", ""),
                        "extra": item.get("extra", {}),
                        "stream_kind": item.get("stream_kind", ""),
                        "stream_name": item.get("stream_name", ""),
                    },
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
        execution = dict(parameters.get(self.parameters_key) or {})
        mode = execution.get("mode", "evidence_replay")

        payload_inputs: dict[str, Any] = {}
        transfer_chain: dict[str, tuple[ProvenanceRecord, ...]] = {}
        diagnostics: list[ModelDiagnostic] = []

        for port_id, output in sorted(inputs.items()):
            if not output.value.is_resolved:
                diagnostics.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_CARRIES_UNRESOLVED,
                        severity=Severity.ERROR,
                        message=(
                            f"{output.ref.key} is in state "
                            f"{output.value.state.value!r} and was not injected into "
                            f"{instance_id}. An unresolved value never becomes a "
                            f"number on its way into a model."
                        ),
                        where=("instance", instance_id, "port", port_id),
                        origin=Origin.EXECUTION,
                        model_id=MODEL_ID,
                        model_version=MODEL_VERSION,
                    )
                )
                continue
            location = output.ref.port_id.split("#", 1)[0]
            payload_inputs[f"{location}:{port_id}"] = {
                "quantity_id": port_id,
                "label": output.ref.port_id,
                "value": float(output.value.value),
                "unit": output.value.unit,
                "provenance": "assumed",
                "method": (
                    f"supplied by the composition layer from {output.ref.key}"
                ),
                "inputs": [output.ref.key],
            }
            transfer_chain[port_id] = output.provenance_chain

        for port_id, literal in sorted(literal_inputs.items()):
            if not literal.value.is_resolved:
                diagnostics.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.VALUE_UNRESOLVED,
                        severity=Severity.ERROR,
                        message=(
                            f"the literal input {literal.ref.key} is in state "
                            f"{literal.value.state.value!r} and was not injected."
                        ),
                        where=("instance", instance_id, "port", port_id),
                        origin=Origin.EXECUTION,
                        model_id=MODEL_ID,
                        model_version=MODEL_VERSION,
                    )
                )
                continue
            location = port_id.split("#", 1)[0]
            quantity_id = port_id.rsplit("#", 1)[-1]
            payload_inputs[f"{location}:{quantity_id}"] = {
                # The worker keys the model's ProcessState by the quantity id,
                # not by the full graph port id. Passing `node:N01#x` here made
                # the literal land under a different key and silently do nothing.
                "quantity_id": quantity_id,
                "label": port_id,
                "value": float(literal.value.value),
                "unit": literal.value.unit,
                "provenance": "assumed",
                "method": "literal input declared on the composition graph",
                "inputs": [port_id],
            }

        response = self.worker.call(
            {"op": "run", "mode": mode, "inputs": payload_inputs}
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
        origin = ProvenanceRecord(
            kind="source",
            producer_model=MODEL_ID,
            producer_version=MODEL_VERSION,
            where=f"instance:{instance_id}",
            detail=(
                f"{mode}: {summary.get('observed_reference_values', 0)} reported, "
                f"{summary.get('digitized_values', 0)} digitized, "
                f"{summary.get('computed_values', 0)} computed, "
                f"{summary.get('unknown_values', 0)} unknown, "
                f"{summary.get('unresolved_targets', 0)} unresolved targets"
            ),
            method=(
                "Zielinski et al. (2019) process graph; "
                + ("reported conditions and observations restated, supported "
                   "accounting identities applied"
                   if mode == "evidence_replay"
                   else "declared inputs only; fails closed where the paper "
                        "supplies no model")
            ),
            source_ref=(
                "Zielinski et al. 2019, Protein Expression and Purification 157 "
                "(2019) 63-69, doi:10.1016/j.pep.2019.02.002"
            ),
        )

        outputs: list[ModelOutput] = []
        for item in payload.get("outputs", ()):
            port_id = item["port_id"]
            chain = transfer_chain.get(port_id, ())
            if port_id in transfer_chain:
                chain = chain + (
                    ProvenanceRecord(
                        kind="transfer",
                        producer_model=MODEL_ID,
                        producer_version=MODEL_VERSION,
                        where=f"instance:{instance_id}",
                        detail=(
                            "a composition-supplied value entered this model as a "
                            "declared input; the model does not treat it as a "
                            "reported observation"
                        ),
                    ),
                )
            outputs.append(
                ModelOutput(
                    ref=PortRef(instance_id, port_id),
                    value=self._to_value(item),
                    provenance_chain=chain + (origin,),
                )
            )

        for raw in payload.get("diagnostics", ()):
            diagnostics.append(self._to_diagnostic(raw, instance_id))

        for unresolved in payload.get("unresolved", ()):
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MODEL_FINDING,
                    severity=Severity.INFO,
                    message=(
                        f"unresolved target {unresolved.get('target')}: "
                        f"{unresolved.get('reason')}"
                    ),
                    where=("instance", instance_id),
                    origin=Origin.ZIELINSKI,
                    remediation=(
                        "This is the model's designed fail-closed answer. The paper "
                        "supplies no model that would close the gap, so the value "
                        "stays absent."
                    ),
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                    detail={
                        "missing_models": unresolved.get("missing_models", []),
                        "missing_inputs": unresolved.get("missing_inputs", []),
                        "model_severity": "info",
                    },
                )
            )

        if mode == "predictive" and summary.get("predicted_values", 0) == 0:
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MODEL_FINDING,
                    severity=Severity.INFO,
                    message=(
                        f"predictive execution resolved "
                        f"{summary.get('unresolved_targets', 0)} target(s) and "
                        f"predicted 0 values. That is the model's fail-closed "
                        f"behaviour, not an empty result: the paper reports no "
                        f"kinetics, no oxygen-transfer data, no AU calibration and "
                        f"no purification model."
                    ),
                    where=("instance", instance_id),
                    origin=Origin.ZIELINSKI,
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                    detail={"model_severity": "info"},
                )
            )

        return AdapterRun(
            outputs=tuple(outputs),
            diagnostics=tuple(diagnostics),
            unresolved=tuple(payload.get("unresolved", ())),
            summary=summary,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _to_value(item: Mapping[str, Any]) -> ModelValue:
        unit = item.get("unit", "")
        dimension = item.get("dimension", "")
        quantity = quantity_for_zielinski_dimension(dimension, unit)
        if quantity is None:
            quantity = Quantity.DIMENSIONLESS
        try:
            REGISTRY.resolve(unit, quantity) if unit else None
        except Exception:  # noqa: BLE001 - reported through the port
            pass

        provenance_name = item.get("provenance", "unknown")
        provenance = {
            "reported": ValueProvenance.REPORTED,
            "digitized": ValueProvenance.DIGITIZED,
            "derived": ValueProvenance.DERIVED,
            "assumed": ValueProvenance.ASSUMED,
        }.get(provenance_name, ValueProvenance.UNKNOWN)

        state = item.get("state", "unresolved")
        evidence = (item.get("extra") or {}).get("evidence") or {}
        source_ref = None
        if evidence:
            source_ref = evidence.get("citation") or (
                f"p.{evidence.get('printed_page')}"
                + (f", {evidence['section']}" if evidence.get("section") else "")
                + (f", {evidence['figure']}" if evidence.get("figure") else "")
            )

        if state == "number" and item.get("value") is not None:
            return ModelValue.number(
                float(item["value"]),
                quantity=quantity,
                unit=unit,
                provenance=provenance,
                components=(),
                source_ref=source_ref,
                method=item.get("method"),
                reason=item.get("notes", ""),
            )
        if state == "range":
            rng = item.get("value_range") or (0.0, 0.0)
            return ModelValue.unavailable(
                ValueState.RANGE,
                quantity=quantity,
                unit=unit,
                value_range=(float(rng[0]), float(rng[1])),
                reason=item.get("notes")
                or "reported as a range; not collapsed to a point value",
                source_ref=source_ref,
            )
        if state == "unknown":
            return ModelValue.unavailable(
                ValueState.UNKNOWN,
                quantity=quantity,
                unit=unit,
                reason=item.get("reason") or item.get("notes")
                or "not reported by the source",
                source_ref=source_ref,
            )
        return ModelValue.unavailable(
            ValueState.UNRESOLVED,
            quantity=quantity,
            unit=unit,
            reason=item.get("reason") or "not determined",
            source_ref=source_ref,
        )

    @staticmethod
    def _to_diagnostic(raw: Mapping[str, Any], instance_id: str) -> ModelDiagnostic:
        """One of the model's own messages, carried through unchanged in weight.

        Every diagnostic the model raises is a *finding about its source* -- a
        contradiction between two sections of the paper, a cross-check that did
        not reproduce, a quantity the paper leaves undetermined.  The model's
        severity is preserved exactly, so five error-severity findings still
        read as five errors.  What is not preserved is the implication that the
        run failed: it did not, and the composition layer says so.
        """
        code = str(raw.get("code", ""))
        severity = Severity(raw.get("severity", "info"))
        message = raw.get("message", "")
        if code.startswith("crosscheck:fail"):
            remediation = (
                "A value the model computed disagrees with a value the paper "
                "states. The model reports the contradiction rather than choosing "
                "a side; this is a finding from the source, not a composition "
                "error."
            )
        elif code.startswith("crosscheck"):
            remediation = "Cross-check passed; recorded for the audit trail."
        elif "discrepancy" in code or "contradiction" in code or "ambiguity" in code:
            remediation = (
                "Documented contradiction in the source. Both readings are stored; "
                "neither is adjusted."
            )
        elif code.startswith("crosscheck_skipped"):
            remediation = (
                "Not evaluated because one side of the comparison is unresolved. "
                "It is reported as skipped rather than as a pass."
            )
        else:
            remediation = "Reported by the model; review it in the inspector."
        return ModelDiagnostic(
            code=DiagnosticCode.MODEL_FINDING,
            severity=severity,
            message=message,
            where=("instance", instance_id, *(raw.get("where", ()) or ())),
            origin=Origin.ZIELINSKI,
            remediation=remediation,
            model_id=MODEL_ID,
            model_version=MODEL_VERSION,
            detail={"zielinski_code": code, "model_severity": severity.value},
        )


def _temporal_basis(item: Mapping[str, Any], dimension: str) -> TemporalBasis:
    provenance = item.get("provenance", "")
    qid = item.get("port_id", "").rsplit("#", 1)[-1]
    if dimension == "time":
        return TemporalBasis.DURATION
    if dimension in ("volume_rate",):
        return TemporalBasis.RATE
    if dimension == "mass":
        return TemporalBasis.INVENTORY
    if provenance == "digitized" or qid.startswith("od600_h"):
        return TemporalBasis.TRAJECTORY_POINT
    return TemporalBasis.NOT_APPLICABLE