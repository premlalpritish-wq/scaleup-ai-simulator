"""Adapter for Lin et al. (2000/2001) uptake capacities."""
from __future__ import annotations

from typing import Any, Mapping

from ..contracts import (
    ModelInput,
    ModelManifest,
    ModelOutput,
    ModelValue,
    PortDefinition,
    PortDirection,
    PortRef,
    ProvenanceRecord,
    ProvenanceRequirement,
    TemporalBasis,
    ValueProvenance,
    ValueState,
)
from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from ..quantities import Quantity
from .base import AdapterRun, JsonWorker, ModelAdapter

MODEL_ID = "lin2000.uptake_capacities"
MODEL_VERSION = "0.1.0"


class LinAdapter(ModelAdapter):
    model_id = MODEL_ID
    model_version = MODEL_VERSION
    parameters_key = "simulation"

    def manifest(
        self, parameters: Mapping[str, Any]
    ) -> tuple[ModelManifest | None, list[ModelDiagnostic]]:
        response = self.worker.call({"op": "manifest", "parameters": dict(parameters)})
        if not response.ok:
            return None, [response.error_diagnostic(MODEL_ID, MODEL_ID, MODEL_VERSION)]
        raw = response.payload.get("manifest", {})
        ports: list[PortDefinition] = []
        for p in raw.get("ports", []):
            try:
                qty = Quantity(p.get("quantity", "unspecified"))
            except Exception:
                qty = Quantity.DIMENSIONLESS
            ports.append(
                PortDefinition(
                    port_id=p["port_id"],
                    direction=PortDirection(p["direction"]),
                    quantity=qty,
                    unit=p.get("unit", ""),
                    label=p.get("label", p["port_id"]),
                    temporal_basis=TemporalBasis.NOT_APPLICABLE,
                    provenance_requirement=ProvenanceRequirement.EXPLAINED,
                )
            )
        manifest_obj = ModelManifest(
            model_id=MODEL_ID,
            model_version=MODEL_VERSION,
            ports=tuple(ports),
            parameters=(),
            provenance_requirements=(),
            disclaimer=raw.get("disclaimer", ""),
        )
        return manifest_obj, []

    def run(
        self,
        instance_id: str,
        parameters: Mapping[str, Any],
        inputs: Mapping[str, ModelOutput],
        literal_inputs: Mapping[str, ModelInput],
    ) -> tuple[AdapterRun | None, list[ModelDiagnostic]]:
        worker_inputs = {}
        for k, v in inputs.items():
            worker_inputs[k] = {"value": v.value.magnitude, "unit": v.value.unit}
        for k, inp in literal_inputs.items():
            worker_inputs[k] = {"value": inp.value.magnitude, "unit": inp.value.unit}

        response = self.worker.call({
            "op": "run",
            "instance_id": instance_id,
            "inputs": worker_inputs,
            "parameters": dict(parameters),
        })
        if not response.ok:
            return None, [response.error_diagnostic(instance_id, MODEL_ID, MODEL_VERSION)]

        outputs: list[ModelOutput] = []
        for item in response.payload.get("outputs", []):
            try:
                qty = Quantity(item.get("quantity", "unspecified"))
            except Exception:
                qty = Quantity.DIMENSIONLESS
            outputs.append(
                ModelOutput(
                    ref=PortRef(instance_id, item["port_id"]),
                    value=ModelValue(
                        state=ValueState.RESOLVED,
                        magnitude=item.get("value"),
                        unit=item.get("unit", ""),
                        quantity=qty,
                        provenance=ValueProvenance(
                            records=(
                                ProvenanceRecord(
                                    rule="lin2000_run",
                                    basis="Lin et al. 2001 reported uptake capacities",
                                    sources=("lin2000",),
                                ),
                            )
                        ),
                    ),
                )
            )
        return AdapterRun(outputs=tuple(outputs)), []
