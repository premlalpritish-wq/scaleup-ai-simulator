"""Adapter for the Ganjave et al. (2022) cybernetic growth model.

The model is a dynamic biological cultivation model: it integrates eq. (1)-(16)
of the paper over a stated interval and returns a state trajectory.  It has no
component identity anywhere, so every port publishes ``components=()`` and the
engine refuses to attach one to a component-declared control volume.

This adapter is deliberately mechanical.  It:

* publishes the manifest the model itself declares
  (``Models/Ganjave/models/composition.py``), translated into the contract's
  vocabulary through ``composition.dimensions``;
* translates composition inputs into the model's own API and calls it;
* turns the returned trajectory into ``ModelOutput`` values, carrying the full
  time series in ``extra`` because the contract has no time-series value type;
* preserves the model's diagnostics at their own severity, and never converts a
  model finding into "the run failed".

It contains no kinetic equation, no balance and no solver.  Those live in the
model package and are reached only through ``models.simulation.simulate``.

Two things this adapter refuses to do, because doing either would be a
scientific claim this package has not earned:

* **it does not label a result a reproduction.**  Every output carries the
  model's declared validation claim: implementation ``implemented``, reproduction
  ``not_yet_validated``;
* **it does not default an initial condition.**  Three are not stated in the
  paper; the model refuses them and the adapter turns that refusal into a
  structured diagnostic naming the missing ports.
"""

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
    TemporalBasis,
    ValueProvenance,
    ValueState,
)
from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from ..dimensions import quantity_for_ganjave_kind
from ..quantities import Quantity, REGISTRY
from .base import AdapterRun, JsonWorker, ModelAdapter
from .ganjave_contract import ConnectionRefused, check_input_connection

MODEL_ID = "ganjave"
MODEL_VERSION = "0.1.0"

#: Where the instance's run configuration lives.
PARAMETERS_KEY = "simulation"

#: Composition ``TemporalBasis`` <- the model's own vocabulary.
_TEMPORAL_BASIS = {
    "instant": TemporalBasis.INSTANT,
    "rate": TemporalBasis.RATE,
    "trajectory_point": TemporalBasis.TRAJECTORY_POINT,
    "inventory": TemporalBasis.INVENTORY,
    "duration": TemporalBasis.DURATION,
    "not_applicable": TemporalBasis.NOT_APPLICABLE,
}


class GanjaveAdapter(ModelAdapter):
    model_id = MODEL_ID
    model_version = MODEL_VERSION
    parameters_key = PARAMETERS_KEY

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
            kind = item.get("contract_kind", "")
            quantity = quantity_for_ganjave_kind(kind, unit)
            unavailable = ""
            if quantity is None:
                unavailable = (
                    f"the model declares quantity kind {kind or '(none)'!r} for "
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
            ports.append(
                PortDefinition(
                    port_id=item["port_id"],
                    direction=PortDirection(item["direction"]),
                    quantity=quantity or Quantity.DIMENSIONLESS,
                    unit=unit,
                    label=item.get("label", ""),
                    component=None,
                    components=(),
                    temporal_basis=_TEMPORAL_BASIS.get(
                        item.get("temporal_basis", "not_applicable"),
                        TemporalBasis.NOT_APPLICABLE,
                    ),
                    required=bool(item.get("required", False)),
                    provenance_requirement=_requirement(item),
                    attribution_required=bool(
                        item.get("attribution_required", False)
                    ),
                    solvable=False,
                    unavailable_reason=unavailable,
                    description=item.get("description", ""),
                    metadata={
                        "model_kind": kind,
                        "contract_quantity": item.get("quantity", ""),
                        "model_symbol": item.get("model_symbol", ""),
                        "state_key": item.get("state_key"),
                        "source_equation": item.get("source_equation", ""),
                        "required_when": list(item.get("required_when", ())),
                        "default_value": item.get("default_value"),
                        "default_provenance": item.get("default_provenance", ""),
                        "default_source": item.get("default_source", ""),
                        "inbound_conversion": item.get("inbound_conversion", ""),
                        "upstream": item.get("upstream"),
                    },
                )
            )

        validation = payload.get("validation_claim", {})
        return ModelManifest(
            model_id=payload["model_id"],
            model_version=payload["model_version"],
            title="Ganjave et al. (2022) cybernetic growth and fed-batch model",
            summary=payload.get("summary", ""),
            adapter=payload.get("adapter", "composition.adapters.ganjave.GanjaveAdapter"),
            contract_version=payload.get("composition_contract_version", "0.1.0"),
            source_ref=(
                "Ganjave et al. 2022, Biotechnology Reports 33:e00694, "
                "doi:10.1016/j.btre.2021.e00694"
            ),
            ports=tuple(ports),
            parameters={
                "parameter_set_id": payload.get("parameter_set", {}).get("id", ""),
                "parameter_set_version": payload.get("parameter_set", {}).get(
                    "version", ""
                ),
                "equations_version": payload.get("parameter_set", {}).get(
                    "equations_version", ""
                ),
                "implementation_status": validation.get("implementation_status", ""),
                "reproduction_status": validation.get("reproduction_status", ""),
                "solver": payload.get("solver", {}),
                "modes": sorted(payload.get("modes", {})),
            },
            parameter_sections={
                "run configuration": {
                    "mode": ["batch", "fed_batch"],
                    "duration_h": (
                        "integration interval in hours; required, and never "
                        "chosen by the adapter"
                    ),
                    "output_times_h": (
                        "times, in hours, at which the trajectory is recorded "
                        "exactly; optional"
                    ),
                    "solver": payload.get("solver", {}),
                },
                "parameter set": payload.get("parameter_set", {}),
                "validation status": {
                    "implementation_status": validation.get(
                        "implementation_status", ""
                    ),
                    "reproduction_status": validation.get("reproduction_status", ""),
                    "what_is_not_validated": validation.get(
                        "what_is_not_validated", []
                    ),
                    "unresolved_items": validation.get("unresolved_items", []),
                },
            },
            capabilities=tuple(payload.get("capabilities", ())),
            unsupported_capabilities={
                **_unsupported_capabilities(payload),
                "component_identity": (
                    "S2 is a lumped mixture of amino acids and peptides with a "
                    "single fitted yield and no component identity, and X is a "
                    "total dry-cell weight. No port carries components, so nothing "
                    "from this model can enter a component-declared control volume."
                ),
                "paper_reproduction": (
                    "The published time courses are figures, three initial "
                    "conditions are not stated by the source, and one "
                    "transcription item (TN-02) is unresolved. Outputs are "
                    "computed under the printed equations; they are not a validated "
                    "reproduction of the paper."
                ),
            },
            reaction_terms=(),
            conversion_models=("mL/h -> L/h within volume_flow",),
            non_reacting_only=False,
            assumptions=tuple(
                {"item_id": item["item_id"], "summary": item["summary"],
                 "status": item["status"]}
                for item in validation.get("unresolved_items", ())
            ),
            missing_information=tuple(
                {"item": entry["item"], "reason": entry["reason"],
                 "consequence": entry["consequence"]}
                for entry in payload.get("missing_information", ())
            ),
        )

    # -- run -----------------------------------------------------------------

    def run(
        self,
        instance_id: str,
        parameters: Mapping[str, Any],
        inputs: Mapping[str, ModelOutput],
        literal_inputs: Mapping[str, ModelInput],
    ) -> AdapterRun:
        run_config = dict(parameters.get(PARAMETERS_KEY) or parameters or {})
        mode = str(run_config.get("mode", "batch"))

        # One manifest lookup for the whole run, so every input is checked
        # against the same port table rather than against a fresh copy.
        manifest, manifest_diagnostics = self.manifest(parameters)
        if manifest is None:
            return AdapterRun(
                outputs=(), diagnostics=tuple(manifest_diagnostics)
            )

        payload_inputs: dict[str, Any] = {}
        transfer_chain: dict[str, tuple[ProvenanceRecord, ...]] = {}
        assumptions: list[str] = []
        diagnostics: list[ModelDiagnostic] = list(manifest_diagnostics)

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
            refusal = _semantic_check(
                manifest, port_id, output.value.quantity.value, instance_id,
                via="connection",
            )
            if refusal is not None:
                diagnostics.append(refusal)
                continue
            rule = _rule_or_none(port_id, output.value.quantity.value)
            if rule is not None and rule.assumption:
                assumptions.append(f"{port_id}: {rule.assumption}")
            payload_inputs[port_id] = {
                "value": float(output.value.value),
                "unit": output.value.unit,
                "quantity": output.value.quantity.value,
                "via": "connection",
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
            refusal = _semantic_check(
                manifest, port_id, literal.value.quantity.value, instance_id,
                via="literal",
            )
            if refusal is not None:
                diagnostics.append(refusal)
                continue
            rule = _rule_or_none(port_id, literal.value.quantity.value)
            if rule is not None and rule.assumption:
                assumptions.append(f"{port_id}: {rule.assumption}")
            payload_inputs[port_id] = {
                "value": float(literal.value.value),
                "unit": literal.value.unit,
                "quantity": literal.value.quantity.value,
                "via": "literal",
            }

        if diagnostics:
            # A refused input is a failure, not a partial run.
            return AdapterRun(outputs=(), diagnostics=tuple(diagnostics))

        request = {
            "op": "run",
            "parameters": {
                "mode": mode,
                "duration_h": run_config.get("duration_h"),
                "output_times_h": run_config.get("output_times_h"),
                "solver": run_config.get("solver") or {},
            },
            "inputs": payload_inputs,
        }

        response = self.worker.call(request)
        if not response.ok:
            missing = response.payload.get("missing") or []
            detail: dict[str, Any] = {
                "exit_code": response.exit_code,
                "stderr": response.stderr[-4000:],
                "traceback": response.payload.get("traceback", ""),
            }
            if missing:
                detail["missing_inputs"] = missing
            failure = response.error_diagnostic(
                instance_id, MODEL_ID, MODEL_VERSION
            )
            diagnostics.append(
                ModelDiagnostic(
                    code=failure.code,
                    severity=failure.severity,
                    message=(
                        f"{failure.message} Ganjave requires "
                        f"{missing} to be declared, because the paper does not "
                        f"state the value and this adapter will not invent one."
                        if missing else failure.message
                    ),
                    where=failure.where,
                    origin=Origin.EXECUTION,
                    remediation=failure.remediation,
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                    detail=detail,
                )
            )
            return AdapterRun(
                outputs=(), diagnostics=tuple(diagnostics),
                summary=response.payload.get("summary", {}),
            )

        payload = response.payload
        summary = payload.get("summary", {})
        origin_record = ProvenanceRecord(
            kind="source",
            producer_model=MODEL_ID,
            producer_version=MODEL_VERSION,
            where=f"instance:{instance_id}",
            detail=(
                f"{summary.get('mode', mode)} over {summary.get('duration_h')} h; "
                f"equations {summary.get('equations_version')}; parameter set "
                f"{summary.get('parameter_set_id')}@{summary.get('parameter_set_version')}; "
                f"digest {str(summary.get('input_digest'))[:16]}; reproduction "
                f"status {summary.get('reproduction_status')}"
            ),
            method=(
                "Ganjave et al. (2022) cybernetic growth model, eq. (1)-(16), "
                "integrated by the model's own RK4(3) step-doubling solver"
            ),
            source_ref=(
                "Ganjave et al. 2022, Biotechnology Reports 33:e00694, "
                "doi:10.1016/j.btre.2021.e00694"
            ),
        )

        outputs: list[ModelOutput] = []
        # Every input that entered this run contributed to every output: the
        # model integrated one trajectory from all of them, so a value whose
        # provenance chain omits its inputs would be unreadable. Connected
        # inputs bring their upstream chain with them; literals bring an
        # assumption record, because that is what they are.
        input_records: tuple[ProvenanceRecord, ...] = ()
        for port_id, chain in sorted(transfer_chain.items()):
            input_records += chain + (
                ProvenanceRecord(
                    kind="transfer",
                    producer_model=MODEL_ID,
                    producer_version=MODEL_VERSION,
                    where=f"instance:{instance_id}",
                    detail=(
                        f"a composition-supplied value entered this run on port "
                        f"{port_id!r}; it is an input, not an observation"
                    ),
                    source_port=port_id,
                    target_port=port_id,
                    method="injected into the model's initial conditions",
                ),
            )
        for port_id in sorted(payload_inputs):
            if port_id in transfer_chain:
                continue
            input_records += (
                ProvenanceRecord(
                    kind="assumption",
                    producer_model="composition",
                    producer_version=MODEL_VERSION,
                    where=f"instance:{instance_id}",
                    detail=(
                        f"port {port_id!r} was declared on the graph as a literal "
                        f"input; the model does not treat it as a reported "
                        f"observation"
                    ),
                    target_port=port_id,
                    method="literal input declared on the composition graph",
                ),
            )

        for item in payload.get("outputs", ()):
            port_id = item["port_id"]
            outputs.append(
                ModelOutput(
                    ref=PortRef(instance_id, port_id),
                    value=self._to_value(item),
                    provenance_chain=input_records + (origin_record,),
                )
            )

        for raw in payload.get("diagnostics", ()):
            diagnostics.append(self._to_diagnostic(raw, instance_id))

        if assumptions:
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MODEL_FINDING,
                    severity=Severity.INFO,
                    message=(
                        f"{instance_id} accepted {len(assumptions)} upstream or "
                        f"literal input(s) whose physical premise is the operator's "
                        f"to confirm: " + "; ".join(sorted(assumptions))
                    ),
                    where=("instance", instance_id),
                    origin=Origin.GANJAVE,
                    remediation=(
                        "A matching quantity is not a matching meaning. Check the "
                        "declared assumption for each accepted input."
                    ),
                    model_id=MODEL_ID,
                    model_version=MODEL_VERSION,
                    detail={"assumptions": sorted(assumptions)},
                )
            )

        diagnostics.append(
            ModelDiagnostic(
                code=DiagnosticCode.MODEL_FINDING,
                severity=Severity.INFO,
                message=(
                    f"{instance_id} computed a trajectory from the printed "
                    f"equations. Implementation status "
                    f"{summary.get('implementation_status')}; reproduction status "
                    f"{summary.get('reproduction_status')}. The published time "
                    f"courses are figures and no figure was digitised, so this "
                    f"result is a simulation of the printed model, not a validated "
                    f"reproduction of the paper."
                ),
                where=("instance", instance_id),
                origin=Origin.GANJAVE,
                remediation=(
                    "Do not quote these values as the paper's results. See "
                    "Models/Ganjave/OXYGEN_BALANCE_REPORT.md."
                ),
                model_id=MODEL_ID,
                model_version=MODEL_VERSION,
                detail={
                    "implementation_status": summary.get("implementation_status"),
                    "reproduction_status": summary.get("reproduction_status"),
                    "unresolved_transcription_notes": [
                        note for note in summary.get("transcription_notes", ())
                        if note.get("unresolved")
                    ],
                },
            )
        )

        return AdapterRun(
            outputs=tuple(outputs),
            diagnostics=tuple(diagnostics),
            summary=summary,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _to_value(item: Mapping[str, Any]) -> ModelValue:
        unit = item.get("unit", "")
        kind = item.get("contract_kind", "")
        quantity = quantity_for_ganjave_kind(kind, unit) or Quantity.DIMENSIONLESS
        state = item.get("state", "unresolved")
        if state == "number" and item.get("value") is not None:
            return ModelValue.number(
                float(item["value"]),
                quantity=quantity,
                unit=unit,
                provenance=ValueProvenance.DERIVED,
                components=(),
                method=item.get("method"),
                reason=item.get("reason", ""),
                extra=dict(item.get("extra", {})),
            )
        return ModelValue.unavailable(
            ValueState.UNRESOLVED,
            quantity=quantity,
            unit=unit,
            reason=item.get("reason") or "the model produced no value on this port",
            extra=dict(item.get("extra", {})),
        )

    @staticmethod
    def _to_diagnostic(raw: Mapping[str, Any], instance_id: str) -> ModelDiagnostic:
        """One of the model's own messages, carried through at its own weight.

        The model's severity is preserved exactly. What is *not* carried is the
        implication that the run failed: a transcription note about the paper is
        a finding about the source, not a failure to execute.
        """
        code = str(raw.get("code", ""))
        severity = Severity(raw.get("severity", "info"))
        if code.startswith("transcription"):
            remediation = (
                "An open question about the source, recorded so a reader is not "
                "left believing the reading is settled. It does not affect this "
                "run's execution."
            )
        elif code.startswith("input"):
            remediation = "The model refused an input; supply it or leave it unresolved."
        else:
            remediation = "Reported by the model; review it in the inspector."
        return ModelDiagnostic(
            code=DiagnosticCode.MODEL_FINDING,
            severity=severity,
            message=raw.get("message", ""),
            where=("instance", instance_id, *(raw.get("where", ()) or ())),
            origin=Origin.GANJAVE,
            remediation=remediation,
            model_id=MODEL_ID,
            model_version=MODEL_VERSION,
            detail={"ganjave_code": code, "model_severity": severity.value},
        )


def _slug(text: str, words: int = 4) -> str:
    """A readable key from the leading clause of a declared limitation.

    ``capability.unsupported`` diagnostics are keyed by capability name and
    shown in the inspector, so ``capability_0`` would be an unreadable label for
    a fact the model states precisely. The clause ends at the first parenthesis,
    because the parenthetical is an explanation rather than part of the name.
    """
    head = text.split("(", 1)[0]
    slug = "".join(
        ch if ch.isalnum() else "_" for ch in " ".join(head.split()[:words]).lower()
    ).strip("_")
    return slug or "unspecified"


def _unsupported_capabilities(payload: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for text in payload.get("non_capabilities", ()):
        key = _slug(text)
        extra = 2
        while key in out:          # two clauses can share their first words
            key = _slug(text, words=4 + extra)
            extra += 1
        out[key] = text
    return out


def _port_or_none(manifest: ModelManifest, port_id: str):
    """The manifest's port for `port_id`, or None if the model does not have it."""
    try:
        return manifest.port(port_id)
    except KeyError:
        return None


def _rule_or_none(port_id: str, quantity: str):
    """The connection rule for an input port, or None when the port is unknown.

    A port id that is not a Ganjave input reaches here only if the caller named
    something this adapter does not publish; it is caught by the manifest lookup
    in the engine, and is not silently accepted.
    """
    try:
        return check_input_connection(port_id, quantity)
    except (ConnectionRefused, KeyError):
        return None


def _semantic_check(
    manifest: ModelManifest, port_id: str, quantity: str, instance_id: str,
    via: str,
):
    """The diagnostic for a refused input, or None when the connection is legal.

    ``via`` matters. ``upstream_supplyable = False`` means *no upstream model may
    drive this port* -- it does not mean the value is unobtainable. A literal on
    the graph is the sanctioned route for exactly those ports, so the supplyable
    check applies only to values arriving through a connection, while the
    quantity check applies to both.
    """
    if _port_or_none(manifest, port_id) is None:
        return None
    try:
        check_input_connection(port_id, quantity, via=via)
    except ConnectionRefused as exc:
        return ModelDiagnostic(
            # EXECUTION_MODEL_FAILED, not CONNECTION_QUANTITY_MISMATCH: the
            # contract layer classifies only a handful of codes as "the model
            # did not produce its result". A refused input is exactly that --
            # without this code the engine scores the node as
            # success-with-warnings and the graph exits 0.
            code=DiagnosticCode.EXECUTION_MODEL_FAILED,
            severity=Severity.ERROR,
            message=(
                f"{instance_id} refuses to run: {exc} No output was produced and "
                f"no value was substituted."
            ),
            where=("instance", instance_id, "port", port_id),
            origin=Origin.EXECUTION,
            remediation=exc.what_would_help,
            model_id=MODEL_ID,
            model_version=MODEL_VERSION,
            detail={
                "proposed_quantity": exc.proposed,
                "via": via,
                "refused_contract": "composition.adapters.ganjave_contract",
            },
        )
    except KeyError:
        return None
    return None


def _requirement(item: Mapping[str, Any]):
    """How far a value on this port must be traceable.

    An initial condition the paper does not state has to be *explained*; a
    reported one has to be *cited*. Anything the model computes needs nothing
    from the caller.
    """
    from ..contracts import ProvenanceRequirement

    if item.get("direction") != "input":
        return ProvenanceRequirement.NONE
    if item.get("default_provenance") == "reported":
        return ProvenanceRequirement.CITED
    if item.get("required"):
        return ProvenanceRequirement.EXPLAINED
    return ProvenanceRequirement.NONE


__all__ = ["GanjaveAdapter", "MODEL_ID", "MODEL_VERSION", "PARAMETERS_KEY"]