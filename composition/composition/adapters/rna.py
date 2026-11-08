"""Adapter for the generated RNA evidence-audit model.

The model is generated per research run, so it is not registered in the global
``REGISTRATIONS`` table.  The workflow injects this adapter into the existing
:class:`composition.engine.CompositionEngine` for the duration of one run.  That
keeps the shipped model list (and every test that pins it) unchanged while still
executing the constructed model through the real contract, ordering, provenance
and result boundary.

The adapter has one job: translate the worker's derived counts into the
composition contract's :class:`ModelValue` / :class:`ModelOutput` types.  It does
no science and fills no gap.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import (
    ModelManifest,
    ModelOutput,
    PortDefinition,
    PortDirection,
    PortRef,
    ProvenanceRequirement,
    ProvenanceRecord,
    ValueProvenance,
    ModelValue,
)
from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from ..quantities import Quantity
from .base import AdapterRun, JsonWorker, ModelAdapter

MODEL_ID = "pecan_rna_evidence_audit"
MODEL_VERSION = "0.1.0"


class RnaEvidenceAdapter(ModelAdapter):
    model_id = MODEL_ID
    model_version = MODEL_VERSION
    parameters_key = "model"

    def manifest(
        self, parameters: Mapping[str, Any]
    ) -> tuple[ModelManifest | None, list[ModelDiagnostic]]:
        response = self.worker.call({"op": "manifest"})
        if not response.ok:
            return None, [
                response.error_diagnostic("manifest", MODEL_ID, MODEL_VERSION)
            ]
        payload = response.payload["manifest"]
        ports = []
        for item in payload.get("ports", ()):
            ports.append(
                PortDefinition(
                    port_id=item["port_id"],
                    direction=PortDirection(item.get("direction", "output")),
                    quantity=Quantity.DIMENSIONLESS,
                    unit=item.get("unit", "1"),
                    label=item.get("label", ""),
                    component=None,
                    components=(),
                    temporal_basis=ModelAdapter._temporal_basis_for(
                        item.get("dimension", "")
                    ),
                    required=False,
                    provenance_requirement=ProvenanceRequirement.NONE,
                    attribution_required=False,
                    solvable=False,
                    description=item.get("description", ""),
                    metadata={
                        "role": item.get("role", ""),
                        "provenance": item.get("provenance", ""),
                    },
                )
            )
        return (
            ModelManifest(
                model_id=payload["model_id"],
                model_version=payload["model_version"],
                title=payload.get("title", ""),
                summary=payload.get("summary", ""),
                adapter=payload.get("adapter", "rna"),
                contract_version=payload.get("contract_version", "0.1.0"),
                source_ref=payload.get("source_ref", ""),
                ports=tuple(ports),
                parameters=dict(payload.get("parameters", {})),
                parameter_sections={},
                capabilities=tuple(payload.get("capabilities", ())),
                unsupported_capabilities=dict(
                    payload.get("unsupported_capabilities", {})
                ),
                reaction_terms=(),
                conversion_models=(),
                non_reacting_only=True,
                assumptions=tuple(payload.get("assumptions", ())),
                missing_information=tuple(payload.get("missing_information", ())),
            ),
            [],
        )

    def run(
        self,
        instance_id: str,
        parameters: Mapping[str, Any],
        inputs: Mapping[str, Any],
        literal_inputs: Mapping[str, Any],
    ) -> AdapterRun:
        model_block = parameters.get(self.parameters_key) or {}
        model_spec = (
            model_block.get("model_spec")
            if isinstance(model_block, Mapping)
            else None
        )
        if not isinstance(model_spec, Mapping):
            return AdapterRun(
                outputs=(),
                diagnostics=(
                    ModelDiagnostic(
                        code=DiagnosticCode.MANIFEST_INVALID,
                        severity=Severity.ERROR,
                        message=(
                            f"{MODEL_ID} was placed in the graph without a "
                            f"model_spec. The generated model cannot be inferred "
                            f"from an empty parameter block."
                        ),
                        where=("instance", instance_id),
                        origin=Origin.MANIFEST,
                        remediation=(
                            "Run the workflow builder and carry its model_spec in "
                            "the instance's 'model' parameters."
                        ),
                        model_id=MODEL_ID,
                        model_version=MODEL_VERSION,
                    ),
                ),
                summary={},
            )

        response = self.worker.call({"op": "run", "model_spec": model_spec})
        if not response.ok:
            return AdapterRun(
                outputs=(),
                diagnostics=(
                    response.error_diagnostic(instance_id, MODEL_ID, MODEL_VERSION),
                ),
                summary=response.payload.get("summary", {}),
            )

        payload = response.payload
        source_ref = ""
        outputs_payload = payload.get("outputs") or ()
        if outputs_payload:
            source_ref = str(outputs_payload[0].get("source_ref", ""))
        origin = ProvenanceRecord(
            kind="derivation",
            producer_model=MODEL_ID,
            producer_version=MODEL_VERSION,
            where=f"instance:{instance_id}",
            detail=(
                f"{payload.get('summary', {}).get('claim_count', 0)} verified "
                f"claims, {payload.get('summary', {}).get('step_count', 0)} steps, "
                f"{payload.get('summary', {}).get('unresolved_parameter_count', 0)} "
                f"unresolved parameters"
            ),
            method=(
                "derived from quote-verified literature claims in the generated "
                "model spec; no yield, RIN or degradation value is computed"
            ),
            source_ref=source_ref or None,
        )

        outputs = []
        for item in outputs_payload:
            value = ModelValue.number(
                float(item["value"]),
                quantity=Quantity.DIMENSIONLESS,
                unit=item.get("unit", "1"),
                provenance=ValueProvenance.DERIVED,
                source_ref=item.get("source_ref") or None,
                method=item.get("method"),
                chain=(origin,),
                extra=dict(item.get("extra", {})),
            )
            outputs.append(
                ModelOutput(
                    ref=PortRef(instance_id, item["port_id"]),
                    value=value,
                    provenance_chain=(origin,),
                )
            )

        diagnostics = []
        for raw in payload.get("diagnostics", ()):
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MODEL_FINDING,
                    severity=Severity(raw.get("severity", "info")),
                    message=str(raw.get("message", "")),
                    where=("instance", instance_id),
                    origin=Origin.EXECUTION,
                    remediation=(
                        "This is the audit's answer, not a failed run. Read the "
                        "model spec's unknowns and hypotheses for the detail."
                    ),
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                )
            )

        return AdapterRun(
            outputs=tuple(outputs),
            diagnostics=tuple(diagnostics),
            unresolved=tuple(payload.get("unresolved", ())),
            summary=dict(payload.get("summary", {})),
        )
