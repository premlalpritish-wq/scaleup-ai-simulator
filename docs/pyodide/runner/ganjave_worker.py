"""Subprocess worker for the Ganjave et al. (2022) growth model.

Run with ``python -m composition._workers.ganjave_worker --model-root <path>``
and a JSON request on stdin.  One JSON response on stdout.

Same isolation rationale as ``morris_worker`` and ``zielinski_worker``: all
three models ship a top-level ``models`` package, so none of them can be
imported into another model's interpreter without colliding.

What this file is allowed to do is narrow, and it is the same narrowness
``composition.adapters.base`` demands of an adapter:

* read the model's own contract (``models.composition``) and translate it into
  the composition contract's vocabulary;
* convert declared units where the contract says a conversion is permitted;
* call the model's own ``simulate`` entry point;
* hand the trajectory back.

It contains no kinetic equation, no balance and no solver. The equations live
in ``models/kinetics.py``, ``models/batch.py`` and ``models/fed_batch.py`` and
are reached only through ``models.simulation.simulate``, so there is exactly one
implementation of the science and this file cannot drift from it.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

#: Registered identifier. Deliberately shorter than the two sibling ids
#: (``morris2011.material_balance``, ``zielinski2019.rhi_process``); the paper's
#: citation is carried in the manifest's ``source`` block instead.
MODEL_ID = "ganjave"
MODEL_VERSION = "0.1.0"

MODE_BATCH = "batch"
MODE_FED_BATCH = "fed_batch"
MODES = (MODE_BATCH, MODE_FED_BATCH)


def _model_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Models" / "Ganjave"


def _import_model(model_root: str | None = None):
    """Import the model package, and only after the root is on the path.

    The subprocess already runs with ``cwd`` set to the model root, but relying
    on that would make the worker depend on how it was launched.
    """
    root = Path(model_root) if model_root else _model_root()
    sys.path.insert(0, str(root.resolve()))
    import models.simulation as simulation  # noqa: PLC0415
    import models.composition as contract  # noqa: PLC0415

    return simulation, contract


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #


def build_manifest(contract) -> dict[str, Any]:
    """Derive the manifest from the model's own contract declaration."""
    document = contract.manifest()

    ports: list[dict[str, Any]] = []
    for port in contract.ALL_PORTS:
        record = port.to_dict()
        record["contract_quantity"] = port.quantity
        record["contract_kind"] = port.kind.value
        record["model_symbol"] = port.model_symbol
        record["state_key"] = port.state_key
        ports.append(record)

    document["ports"] = ports
    document["model_id"] = MODEL_ID
    document["model_version"] = MODEL_VERSION
    return document


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def _require(payload: Mapping[str, Any], key: str) -> Any:
    if key not in payload or payload[key] is None:
        raise KeyError(key)
    return payload[key]


def _resolve_inputs(contract, inputs: Mapping[str, Any], mode: str) -> dict[str, Any]:
    """Check every required input is present, and name the ones that are not.

    The model itself refuses an unresolved initial condition; this function
    exists so that the *composition* layer gets a diagnostic naming the missing
    ports before a subprocess is asked to do something impossible.
    """
    required = {p.port_id for p in contract.required_input_ports(mode)}
    missing = sorted(required - set(inputs))
    if missing:
        raise KeyError(
            "these inputs are required and were not supplied: "
            + ", ".join(missing)
        )
    return dict(inputs)


def _build_initial_conditions(contract, initial, mode: str, simulation):
    """Translate composition inputs into the model's initial-condition builder.

    Every value arrives already converted to the unit its port declares, so no
    arithmetic happens here beyond reading the numbers out.
    """
    from models.initial import build_initial_conditions  # noqa: PLC0415

    values: dict[str, float] = {}
    units: dict[str, str] = {}
    provenance_notes: dict[str, str] = {}

    mapping = {
        "initial_biomass_concentration": "X",
        "initial_glycerol_concentration": "S1",
        "initial_complex_substrate_concentration": "S2",
        "initial_dissolved_oxygen": "DO",
        "initial_culture_volume": "V",
    }
    for port_id, key in mapping.items():
        if port_id in initial:
            values[key] = float(initial[port_id]["value"])
            units[key] = initial[port_id]["unit"]
            provenance_notes[key] = initial[port_id].get("via", "declared")

    return build_initial_conditions(
        X=values["X"],
        S2=values["S2"],
        DO=values["DO"],
        mode=mode,
        S1=values.get("S1"),
        V=values.get("V"),
        units=units,
        note=(
            "supplied by the ScaleUp AI composition layer; "
            + ", ".join(f"{k}={v}" for k, v in sorted(provenance_notes.items()))
        ),
    )


def _build_feed(contract, inputs: Mapping[str, Any]):
    """Translate the feed ports into the model's ``FeedProgram``.

    One conversion is performed here, and the contract declares it: the feed
    flow arrives in ``mL/h`` (the unit the paper's Table 1 prints and the only
    volume-flow unit the composition contract registers) and the model
    integrates in ``L/h``. Nothing else is converted.
    """
    from models.fed_batch import FeedProgram  # noqa: PLC0415

    flow_ml_per_h = float(_require(inputs, "feed_flow_rate")["value"])
    return FeedProgram(
        S10_g_per_L=float(_require(inputs, "feed_glycerol_concentration")["value"]),
        S20_g_per_L=float(
            _require(inputs, "feed_complex_substrate_concentration")["value"]
        ),
        flow_L_per_h=flow_ml_per_h * 1.0e-3,
        start_time_h=float(inputs.get("feed_start_time", {}).get("value", 0.0)),
    )


def _solver_config(parameters: Mapping[str, Any]):
    from models.solver import SolverConfig  # noqa: PLC0415

    declared = parameters.get("solver") or {}
    return SolverConfig(
        rtol=float(declared.get("rtol", SolverConfig.rtol)),
        atol=float(declared.get("atol", SolverConfig.atol)),
        h_max=float(declared.get("h_max", SolverConfig.h_max)),
        max_steps=int(declared.get("max_steps", SolverConfig.max_steps)),
        max_range_rejections=int(
            declared.get("max_range_rejections", SolverConfig.max_range_rejections)
        ),
    )


def _trajectory_payload(port, contract, result) -> dict[str, Any]:
    """The final value plus the whole trajectory, in the contract's structure.

    The composition contract has no time-series value type: a ``ModelValue``
    carries one number, an interval, or a reason. So the trajectory travels in
    ``extra``, which the contract carries through verbatim and the inspector
    publishes. It is declared here rather than assembled by the adapter so that
    its shape is the model's own.
    """
    final = result.final_state
    times = [state.t for state in result.states]
    if port.state_key:
        values = [getattr(state, port.state_key) for state in result.states]
    else:
        values = []

    extra: dict[str, Any] = {}
    if port.state_key:
        extra["trajectory"] = {
            "quantity": port.quantity,
            "unit": port.unit,
            "points": len(times),
            "time_axis": {"quantity": "time", "unit": "h", "values": times},
            "values": values,
            "monotonic_time": all(b > a for a, b in zip(times, times[1:])),
        }
    extra["time_axis"] = {
        "quantity": "time",
        "unit": "h",
        "first": times[0] if times else None,
        "last": times[-1] if times else None,
        "points": len(times),
    }
    extra["solver_report"] = result.result.solver_report()
    extra["solver"] = result.metadata.get("solver", {})
    extra["equations_version"] = result.provenance.equations_version
    extra["parameter_set"] = {
        "id": result.metadata.get("parameter_set_id"),
        "version": result.metadata.get("parameter_set_version"),
    }
    extra["input_digest"] = result.provenance.input_digest
    extra["mode"] = result.mode
    extra["validation_claim"] = contract.VALIDATION_CLAIM
    extra["model_reference"] = (
        "Ganjave et al. 2022, Biotechnology Reports 33:e00694, "
        "doi:10.1016/j.btre.2021.e00694"
    )
    if port.model_symbol:
        extra["model_symbol"] = port.model_symbol
    if port.source_equation:
        extra["source_equation"] = port.source_equation

    value = float(getattr(final, port.state_key)) if (port.state_key and final) else (
        float(final.t) if final else 0.0
    )
    return {
        "port_id": port.port_id,
        "quantity": port.quantity,
        "contract_kind": port.kind.value,
        "unit": port.unit,
        "value": value,
        "state": "number" if final is not None else "unresolved",
        "provenance": "derived",
        "basis": "computed",
        "temporal_basis": port.temporal_basis.value,
        "method": (
            f"computed by {MODEL_ID} from eq. "
            f"{port.source_equation or '(8)-(16)'}; reproduction status "
            f"{contract.REPRODUCTION_STATUS}"
        ),
        "reason": "" if final is not None else "the run produced no final state",
        "extra": extra,
    }


def handle_run(request: Mapping[str, Any], simulation, contract) -> dict[str, Any]:
    parameters = request.get("parameters") or {}
    mode = str(parameters.get("mode", MODE_BATCH))
    if mode not in MODES:
        raise ValueError(
            f"mode must be one of {list(MODES)}, got {mode!r}. The operating "
            f"mode is explicit and is never inferred."
        )

    raw_inputs = request.get("inputs") or {}
    resolved = _resolve_inputs(contract, raw_inputs, mode)

    duration_h = parameters.get("duration_h")
    if duration_h is None:
        raise KeyError(
            "parameters.duration_h is required: a duration is an input of the "
            "run, not something this worker may choose"
        )

    conditions = _build_initial_conditions(contract, resolved, mode, simulation)
    feed = _build_feed(contract, resolved) if mode == MODE_FED_BATCH else None
    solver = _solver_config(parameters)
    output_times = parameters.get("output_times_h") or None

    result = simulation.simulate(
        initial_conditions=conditions,
        duration_h=float(duration_h),
        mode=mode,
        feed=feed,
        solver=solver,
        output_times_h=output_times,
    )

    outputs: list[dict[str, Any]] = []
    if result.ok:
        for port in contract.OUTPUT_PORTS:
            outputs.append(_trajectory_payload(port, contract, result))

    diagnostics = [d.to_dict() for d in result.diagnostics]

    return {
        "ok": bool(result.ok),
        "outputs": outputs,
        "diagnostics": diagnostics,
        "summary": {
            "mode": result.mode,
            "ok": result.ok,
            "duration_h": result.times_h[-1] if result.times_h else None,
            "points": len(result.states),
            "equations_version": result.provenance.equations_version,
            "parameter_set_id": result.metadata.get("parameter_set_id"),
            "parameter_set_version": result.metadata.get("parameter_set_version"),
            "input_digest": result.provenance.input_digest,
            "solver": result.metadata.get("solver", {}),
            "solver_report": result.result.solver_report(),
            "implementation_status": contract.IMPLEMENTATION_STATUS,
            "reproduction_status": contract.REPRODUCTION_STATUS,
            "transcription_notes": [
                {"note_id": n.note_id, "unresolved": n.unresolved}
                for n in _transcription_notes()
            ],
        },
        "provenance": result.provenance.to_dict(),
    }


def _transcription_notes():
    from models.kinetics import TRANSCRIPTION_NOTES  # noqa: PLC0415

    return TRANSCRIPTION_NOTES


def handle(request: Mapping[str, Any]) -> dict[str, Any]:
    op = request.get("op", "run")
    try:
        simulation, contract = _import_model(request.get("model_root"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"could not import the Ganjave model: {type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }

    try:
        if op == "manifest":
            return {"ok": True, "manifest": build_manifest(contract)}
        if op == "run":
            return handle_run(request, simulation, contract)
    except KeyError as exc:
        key = exc.args[0]
        return {
            "ok": False,
            "error": (
                f"{key} is required and was not supplied: {exc.args[1] if len(exc.args) > 1 else ''}"
            ).strip(": "),
            "missing": [key],
            "traceback": traceback.format_exc(),
            "outputs": [],
            "diagnostics": [
                {
                    "code": "input.missing",
                    "severity": "error",
                    "message": (
                        f"the Ganjave model cannot run without {key}. No value was "
                        f"substituted and no output was produced."
                    ),
                    "where": ["ganjave", key],
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001 - a model failure is a result
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "outputs": [],
            "summary": {},
            "diagnostics": [
                {
                    "code": "execution.model_failed",
                    "severity": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "where": ["ganjave"],
                }
            ],
        }

    return {"ok": False, "error": f"unknown op {op!r}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", required=True, help="path to the Ganjave package root")
    args = parser.parse_args(argv)

    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        json.dump({"ok": False, "error": f"malformed request: {exc}"}, sys.stdout)
        return 2

    request.setdefault("model_root", args.model_root)
    response = handle(request)
    json.dump(response, sys.stdout, default=str)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
