"""Subprocess worker for the Zielinski et al. (2019) recombinant insulin model.

Run with ``python -m composition._workers.zielinski_worker --model-root <path>``
and a JSON request on stdin.  One JSON response on stdout.

Same isolation rationale as ``morris_worker``: the two models both ship a
top-level ``models`` package, so they cannot share an interpreter.

The ``Dimension`` a quantity carries is emitted verbatim and the *composition*
side maps it to a contract quantity.  That mapping is declared as data in
``composition.dimensions`` rather than imported here, which keeps the
dependency arrow pointing one way: this worker knows about Zielinski's
vocabulary and nothing about the composition contract.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "zielinski2019.rhi_process"
MODEL_VERSION = "1.0.0"


def _model():
    import models.zielinski_2019 as z

    return z


def _core():
    import scaleup_ai as core

    return core


# --------------------------------------------------------------------------- #
# ports
# --------------------------------------------------------------------------- #


def _location_port(location: str, quantity) -> str:
    """`node:N01` + `starting_medium_volume` -> `node:N01#starting_medium_volume`."""
    return f"{location}#{quantity.quantity_id}"


def _safe_dimension(quantity) -> str:
    """The model's own dimension for a unit, or "" if it does not register one.

    The model carries at least one quantity whose unit is not in its own
    registry (the specific growth rate is declared ``1/h``, which
    ``scaleup_ai.units`` does not define).  Raising there would hide the whole
    model behind one gap, so the gap is reported instead: the port is published
    with no dimension, and the composition side marks it unusable.
    """
    try:
        dimension = quantity.dimension
    except Exception:  # noqa: BLE001 - UnitError and anything else it raises
        return ""
    return dimension.value if dimension is not None else ""


def _describe_quantity(location: str, quantity, engine, run) -> dict[str, Any]:
    """One port payload for one Zielinski quantity."""
    core = _core()
    provenance = quantity.provenance.value
    dimension = _safe_dimension(quantity)

    extra: dict[str, Any] = {}
    if quantity.evidence:
        ev = quantity.evidence[0]
        extra["evidence"] = {
            "source_id": ev.source_id,
            "printed_page": ev.printed_page,
            "pdf_page": ev.pdf_page,
            "section": ev.section,
            "figure": ev.figure,
            "quote": ev.quote,
            "citation": ev.citation,
        }
    if quantity.original_text:
        extra["original_text"] = quantity.original_text
    if quantity.original_unit:
        extra["original_unit"] = quantity.original_unit
    if quantity.uncertainty:
        extra["uncertainty"] = quantity.uncertainty.to_dict()

    payload: dict[str, Any] = {
        "port_id": _location_port(location, quantity),
        "location": location,
        "quantity_id": quantity.quantity_id,
        "label": quantity.label,
        "unit": quantity.unit,
        "dimension": dimension,
        "provenance": provenance,
        "basis": quantity.basis.value,
        "value": quantity.value,
        "value_range": list(quantity.value_range) if quantity.value_range else None,
        "method": quantity.method,
        "inputs": list(quantity.inputs),
        "notes": quantity.notes,
        "extra": extra,
    }

    if quantity.provenance is core.Provenance.UNKNOWN:
        payload["state"] = "unknown"
        payload["reason"] = (
            quantity.notes
            or "the paper does not report this quantity and no model is "
               "implemented that would determine it"
        )
    elif quantity.value_range is not None:
        payload["state"] = "range"
        payload["reason"] = (
            "reported as an interval; collapsing it to a point value would be an "
            "undeclared assumption"
        )
    else:
        payload["state"] = "number"
    return payload


def build_manifest(engine, run) -> dict[str, Any]:
    """Derive the port surface from the model's own graph.

    Every quantity the model declares becomes a port.  Nothing is curated away:
    an unknown quantity with an unregistered unit still gets a port, marked
    unusable, so the gap is visible and countable rather than invisible.
    """
    graph = engine.graph
    core = _core()

    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    for node in graph.nodes:
        location = f"node:{node.node_id}"
        for qid, quantity in node.operating_conditions.items():
            payload = _describe_quantity(location, quantity, engine, run)
            payload["direction"] = "input"
            payload["role"] = "operating_condition"
            inputs.append(payload)
        for qid, quantity in node.measurements.items():
            payload = _describe_quantity(location, quantity, engine, run)
            payload["direction"] = "input"
            payload["role"] = "measurement"
            inputs.append(payload)
        for qid, quantity in node.calculated.items():
            payload = _describe_quantity(location, quantity, engine, run)
            payload["direction"] = "output"
            payload["role"] = "calculated"
            outputs.append(payload)

    for sid, stream in graph.streams.items():
        location = f"stream:{sid}"
        for qid, quantity in stream.quantities.items():
            payload = _describe_quantity(location, quantity, engine, run)
            payload["direction"] = "output"
            payload["role"] = "stream_quantity"
            payload["stream_kind"] = stream.kind.value
            payload["stream_name"] = stream.name
            outputs.append(payload)

    # quantities the engine computed during this run, if any
    for node_result in run.node_results:
        for quantity in node_result.computed:
            location = None
            for stream_id, states in node_result.output_states.items():
                if quantity.quantity_id in states:
                    location = f"stream:{stream_id}"
                    break
            if location is None:
                location = f"node:{node_result.node_id}"
            payload = _describe_quantity(location, quantity, engine, run)
            payload["direction"] = "output"
            payload["role"] = "computed"
            payload["node_id"] = node_result.node_id
            outputs.append(payload)

    def port_record(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "port_id": payload["port_id"],
            "direction": payload["direction"],
            "label": payload["label"],
            "unit": payload["unit"],
            "dimension": payload["dimension"],
            "provenance": payload["provenance"],
            "basis": payload["basis"],
            "state": payload["state"],
            "role": payload.get("role", ""),
            "location": payload["location"],
            "notes": payload["notes"],
            "reason": payload.get("reason", ""),
            "extra": payload.get("extra", {}),
        }

    missing_models = {
        mid: m.to_dict() for mid, m in core.MISSING_MODELS.items()
    }

    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "title": graph.title,
        "summary": (
            f"{len(graph.nodes)} operations, {len(graph.streams)} material "
            f"streams, {len(engine.bindings)} declared equation bindings. Evidence "
            f"replay restates the paper's reported numbers and applies only the "
            f"accounting identities the paper supports; predictive mode starts from "
            f"declared inputs and fails closed."
        ),
        "adapter": "composition.adapters.zielinski.ZielinskiAdapter",
        "source_ref": graph.description or graph.source_id,
        "ports": [port_record(p) for p in inputs] + [port_record(p) for p in outputs],
        "parameters": {
            "graph_id": graph.graph_id,
            "source_id": graph.source_id,
            "nodes": [n.node_id for n in graph.nodes],
            "streams": list(graph.streams),
            "operations": sorted({n.operation.value for n in graph.nodes}),
            "bindings": [b.binding_id for b in engine.bindings],
            "cross_checks": [c.check_id for c in engine.cross_checks],
            "doi": graph.doi,
        },
        "parameter_sections": {
            "process graph": {
                "nodes": len(graph.nodes),
                "streams": len(graph.streams),
                "operations": sorted({n.operation.value for n in graph.nodes}),
            },
            "assumptions": [
                {
                    "assumption_id": a.assumption_id,
                    "statement": a.statement,
                    "rationale": a.rationale,
                    "affects": list(a.affects),
                }
                for a in graph.assumptions
            ],
            "declared missing models": list(missing_models.values()),
        },
        "capabilities": [
            "evidence_replay",
            "fail_closed_prediction",
            "accounting_identities",
            "verbatim_source_formulas",
            "digitized_trajectory",
            "declared_cross_checks",
            "calculation_traces",
        ],
        "unsupported_capabilities": {
            "growth_kinetics": missing_models["kinetics.growth_ode"][
                "why_not_implemented"],
            "oxygen_transfer": missing_models["transfer.oxygen_kla"][
                "why_not_implemented"],
            "renaturation_kinetics": missing_models["folding.renaturation_kinetics"][
                "why_not_implemented"],
            "au_to_mass_calibration": missing_models["calibration.au_to_mass"][
                "why_not_implemented"],
            "stage_recovery": missing_models["recovery.stage_yield"][
                "why_not_implemented"],
            "iu_from_au": missing_models["activity.iu_from_au"][
                "why_not_implemented"],
            "scale_up": missing_models["scaleup.effect_of_scale"][
                "why_not_implemented"],
            "component_identity": (
                "StreamKind is a process-role vocabulary (wet_biomass, "
                "inclusion_bodies, chromatographic_fraction, ...), not a set of "
                "conserved chemical entities. No stream carries a component amount "
                "or a mass fraction, so nothing here can be placed in a "
                "component-declared control volume."
            ),
        },
        "reaction_terms": [],
        "conversion_models": [],
        "non_reacting_only": False,
        "assumptions": [a.to_dict() for a in graph.assumptions],
        "missing_information": [m.to_dict() for m in graph.missing_parameters],
    }


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def _run(
    execution_mode,
    engine,
    inputs: Mapping[str, Any],
    manifest: Mapping[str, Any],
    replay=None,
) -> dict[str, Any]:
    core = _core()
    quantities: dict[str, Any] = {}
    for key, payload in inputs.items():
        cls = core.Provenance(payload.get("provenance", "assumed"))
        quantities[key] = core.Quantity(
            quantity_id=payload.get("quantity_id", key),
            label=payload.get("label", key),
            provenance=cls,
            value=payload.get("value"),
            unit=payload.get("unit"),
            method=payload.get("method"),
            inputs=tuple(payload.get("inputs", ()) or ()),
        )

    if replay is not None and execution_mode is core.ExecutionMode.EVIDENCE_REPLAY \
            and not quantities:
        # Evidence replay with no declared inputs is exactly the run the
        # manifest was built from; reuse it rather than repeating the walk.
        run = replay
    else:
        run = engine.run(mode=execution_mode, inputs=quantities)

    outputs: list[dict[str, Any]] = []

    # declared graph quantities: the observed/derived/unknown inventory
    for location, qid, quantity in engine.graph.iter_quantities():
        payload = _describe_quantity(location, quantity, engine, run)
        payload["direction"] = "output"
        payload["role"] = "declared"
        outputs.append(payload)

    # quantities the engine computed during this run
    for node_result in run.node_results:
        for trace in node_result.traces:
            outputs.append({
                "port_id": f"node:{node_result.node_id}#{trace.output_quantity_id}",
                "location": f"node:{node_result.node_id}",
                "quantity_id": trace.output_quantity_id,
                "label": node_result.name,
                "unit": trace.output_unit,
                "dimension": "",
                "provenance": "derived",
                "basis": "computed",
                "state": "number",
                "value": trace.output_value,
                "value_range": None,
                "method": trace.statement,
                "inputs": list(trace.input_values),
                "notes": "",
                "extra": {
                    "calculation_trace": trace.to_dict(),
                    "binding_id": trace.binding_id,
                    "equation_id": trace.equation_id,
                },
            })

    # deduplicate: a computed quantity wins over the declared one
    seen: dict[str, dict[str, Any]] = {}
    for payload in outputs:
        seen[payload["port_id"]] = payload
    deduped = list(seen.values())

    diagnostics = [m.to_dict() for m in run.cross_checks]
    for node_result in run.node_results:
        diagnostics.extend(m.to_dict() for m in node_result.warnings)

    return {
        "ok": True,
        "outputs": deduped,
        "diagnostics": diagnostics,
        "unresolved": [u.to_dict() for u in run.unresolved],
        "summary": {
            **run.summary.to_dict(),
            "graph_id": run.graph_id,
            "nodes": [
                {
                    "node_id": nr.node_id,
                    "index": nr.index,
                    "name": nr.name,
                    "operation": nr.operation,
                    "status": nr.status.value,
                    "validation": nr.validation.value,
                }
                for nr in run.node_results
            ],
        },
        "raw": run.to_dict(),
    }


def handle(request: Mapping[str, Any]) -> dict[str, Any]:
    op = request.get("op", "run")
    try:
        model = _model()
        engine = model.build_engine()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"could not build the Zielinski model: {type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }

    if op == "manifest":
        core = _core()
        run = engine.run(mode=core.ExecutionMode.EVIDENCE_REPLAY)
        try:
            return {"ok": True, "manifest": build_manifest(engine, run)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()}

    if op == "run":
        mode = request.get("mode", "evidence_replay")
        core = _core()
        try:
            # The manifest is derived from the model's own graph plus a replay,
            # so compute it once and reuse it rather than replaying twice.
            replay = engine.run(mode=core.ExecutionMode.EVIDENCE_REPLAY)
            manifest = build_manifest(engine, replay)
            execution_mode = (
                core.ExecutionMode.PREDICTIVE if mode == "predictive"
                else core.ExecutionMode.EVIDENCE_REPLAY
            )
            response = _run(
                execution_mode, engine, request.get("inputs") or {},
                manifest,
                replay if execution_mode is core.ExecutionMode.EVIDENCE_REPLAY
                else None,
            )
        except Exception as exc:  # noqa: BLE001 - a model failure is a result
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "outputs": [],
                "summary": {},
                "diagnostics": [{
                    "code": "execution.model_failed",
                    "severity": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "where": ["zielinski2019"],
                }],
            }
        response["manifest"] = manifest
        return response

    return {"ok": False, "error": f"unknown op {op!r}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", required=True,
                        help="path to the Zielinski package root")
    args = parser.parse_args(argv)

    root = str(Path(args.model_root).resolve())
    sys.path.insert(0, root)

    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        json.dump({"ok": False, "error": f"malformed request: {exc}"}, sys.stdout)
        return 2

    response = handle(request)
    json.dump(response, sys.stdout, default=str)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())