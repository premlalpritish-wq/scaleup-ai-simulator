"""Subprocess worker for the Morris, Geiger & Fine (2011) material balance.

Run with ``python -m composition._workers.morris_worker --model-root <path>``
and a JSON request on stdin.  One JSON response on stdout.

**Why a subprocess at all.**  Both models ship a top-level package called
``models``.  ``Models/Morris/models`` and ``Models/Zielinski/models`` cannot
co-exist in one ``sys.modules``: whichever is imported first wins and the second
resolves to the first's modules, which would silently run the wrong engine.
A worker process gives each model its own interpreter and its own import path,
which also guarantees that composition code cannot write into ``Models/``.

This worker imports only ``schemas`` and ``models`` from the Morris package.
It never imports the composition package, so the dependency arrow points one
way: composition knows about Morris, Morris knows nothing about composition.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "morris2011.material_balance"
MODEL_VERSION = "0.1.0"

_KIND_BY_NAME = {
    "mass": "mass",
    "mass_flow": "mass_flow",
    "mass_fraction": "mass_fraction",
    "amount": "amount",
    "amount_flow": "amount_flow",
}


# --------------------------------------------------------------------------- #
# deferred imports, so the module can be imported for its constants alone
# --------------------------------------------------------------------------- #


def _schemas():
    import schemas.material_balance as mb

    return mb


def _engine():
    import models.material_balance as engine

    return engine


# --------------------------------------------------------------------------- #
# declaration -> BalanceSystem
# --------------------------------------------------------------------------- #


def _quantity(mb, spec: Mapping[str, Any], *, stream_id: str, field: str):
    """Build a `Quantity` or `Unknown` from a declaration.

    `spec["kind"]` is the schema's own `QuantityKind` value (``"mass"``,
    ``"mass_flow"``, ...).  It is validated rather than coerced: an unknown kind
    is a declaration error, and silently picking one is how a mass flow turns
    into a mass.
    """
    kind_name = spec["kind"]
    if kind_name not in _KIND_BY_NAME:
        raise ValueError(
            f"{stream_id}.{field}: {kind_name!r} is not a QuantityKind; "
            f"known kinds: {sorted(_KIND_BY_NAME)}"
        )
    kind = mb.QuantityKind(kind_name)
    if spec.get("provenance") == "unknown":
        return mb.unknown(
            variable_id=spec["variable_id"],
            kind=kind,
            unit=spec.get("unit"),
            reason=spec.get("reason", ""),
        )
    unit = spec["unit"]
    provenance = spec.get("provenance", "reported")
    source_ref = spec.get("source_ref", "declared in the composition graph")
    note = spec.get("note", "")
    value = float(spec["value"])
    if provenance == "reported":
        return mb.reported(spec["quantity_id"], value, unit,
                           source_ref=source_ref, note=note)
    if provenance == "assumed":
        return mb.assumed(spec["quantity_id"], value, unit,
                          assumption_id=spec.get("assumption_id", "COMPOSITION"),
                          rationale=source_ref, note=note)
    return mb.derived(spec["quantity_id"], value, unit,
                      derivation=spec.get("derivation", "supplied by the "
                                                        "composition graph"),
                      source_ref=source_ref, note=note)


def build_system(spec: Mapping[str, Any], inputs: Mapping[str, Any]):
    """Assemble a `BalanceSystem` from a JSON declaration plus injected inputs.

    `inputs` keys are ``<stream_id>:<slot>`` where slot is ``total``,
    ``component:<component_id>`` or ``fraction:<component_id>``.  An injected
    value replaces the declaration for that slot; a declared *unknown* left
    uninjected stays unknown and is solved for.
    """
    mb = _schemas()

    def injected(stream_id: str, slot: str) -> Mapping[str, Any] | None:
        return inputs.get(f"{stream_id}:{slot}")

    streams = []
    for raw in spec["streams"]:
        sid = raw["stream_id"]
        slot_total = injected(sid, "total")
        slot_amount = slot_total or raw.get("amount")
        amount = None
        if slot_amount is not None:
            amount = _quantity(mb, slot_amount, stream_id=sid, field="amount")

        mass_fractions: dict[str, Any] = {}
        for cid, frac in (raw.get("mass_fractions") or {}).items():
            chosen = injected(sid, f"fraction:{cid}") or frac
            mass_fractions[cid] = _quantity(mb, chosen, stream_id=sid,
                                            field="mass_fractions")

        component_amounts: dict[str, Any] = {}
        for cid, value in (raw.get("component_amounts") or {}).items():
            chosen = injected(sid, f"component:{cid}") or value
            component_amounts[cid] = _quantity(mb, chosen, stream_id=sid,
                                               field="component_amounts")

        streams.append(
            mb.Stream(
                stream_id=sid,
                label=raw.get("label", sid),
                direction=mb.Direction(raw["direction"]),
                amount=amount,
                mass_fractions=mass_fractions,
                component_amounts=component_amounts,
                absent_components=tuple(raw.get("absent_components", ()) or ()),
                time_basis=raw.get("time_basis"),
                note=raw.get("note", ""),
            )
        )

    components = tuple(
        mb.Component(
            component_id=item["component_id"],
            label=item.get("label", item["component_id"]),
            formula=item.get("formula"),
            molar_mass_kg_per_mol=item.get("molar_mass_kg_per_mol"),
            note=item.get("note", ""),
        )
        for item in spec["components"]
    )

    constraints = []
    for raw in spec.get("constraints", ()):
        constraints.append(
            mb.BalanceEquation(
                equation_id=raw["equation_id"],
                kind=mb.EquationKind(raw.get("kind", "user_constraint")),
                label=raw.get("label", raw["equation_id"]),
                expression=raw.get("expression", ""),
                coefficients=dict(raw["coefficients"]),
                component_id=raw.get("component_id"),
                stream_id=raw.get("stream_id"),
                process_mode=mb.ProcessMode(
                    raw.get("process_mode", spec["process_mode"])
                ),
                source_ref=raw.get("source_ref"),
                note=raw.get("note", ""),
            )
        )

    assumptions = tuple(
        mb.Assumption(
            assumption_id=item["assumption_id"],
            statement=item["statement"],
            rationale=item.get("rationale", ""),
            affects=tuple(item.get("affects", ()) or ()),
        )
        for item in spec.get("assumptions", ())
    )

    basis_name = spec.get("basis", "mass")
    return mb.BalanceSystem(
        system_id=spec["system_id"],
        label=spec.get("label", spec["system_id"]),
        process_mode=mb.ProcessMode(spec["process_mode"]),
        basis=mb.BalanceBasis(basis_name),
        components=components,
        streams=tuple(streams),
        constraints=tuple(constraints),
        assumptions=assumptions,
        balances=tuple(spec["balances"]) if spec.get("balances") else None,
        total_balance=bool(spec.get("total_balance", False)),
        residual_tolerance=float(spec.get("residual_tolerance", 1.0e-6)),
        rank_tolerance=float(spec.get("rank_tolerance", 1.0e-10)),
        source_ref=spec.get("source_ref"),
        notes=spec.get("notes", ""),
    )


# --------------------------------------------------------------------------- #
# ports
# --------------------------------------------------------------------------- #


def _slot_kind(spec: Mapping[str, Any], stream_id: str, kind_default: str) -> str:
    for stream in spec["streams"]:
        if stream["stream_id"] != stream_id:
            continue
        if stream.get("amount"):
            return stream["amount"].get("kind", kind_default)
        for value in (stream.get("component_amounts") or {}).values():
            return value.get("kind", kind_default)
        for value in (stream.get("mass_fractions") or {}).values():
            return value.get("kind", "mass_fraction")
    return kind_default


def _unit_for(spec: Mapping[str, Any], stream_id: str, kind: str) -> str:
    from schemas.material_balance import base_unit

    return base_unit(_schemas().QuantityKind(kind))


def build_manifest(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Ports derived from the *declared* control volume.

    The manifest describes what this control volume asks for.  It is produced
    from the declaration, not from a solution, so it is the same before and
    after a run -- which is what lets Godot draw ports before anything executes.
    """
    from schemas.material_balance import QuantityKind

    ports: list[dict[str, Any]] = []

    for stream in spec["streams"]:
        sid = stream["stream_id"]
        label = stream.get("label", sid)
        direction = stream["direction"]

        if stream.get("amount"):
            kind = _slot_kind(spec, sid, "mass")
            ports.append({
                "port_id": f"in:{sid}:total",
                "direction": "input",
                "quantity": kind,
                "unit": stream["amount"].get("unit") or _unit_for(spec, sid, kind),
                "label": f"{label}: total",
                "component": None,
                "components": [c["component_id"] for c in spec["components"]],
                "temporal_basis": (
                    "rate" if QuantityKind(kind).value.endswith("_flow")
                    else "inventory"
                ),
                # A declared quantity is its own supply: nothing has to be
                # connected for it. Only the *unresolved* slots below can be
                # filled from outside, and even then the solver may determine
                # them, so none of them is required either.
                "required": False,
                "provenance_requirement": "explained",
                "attribution_required": bool(stream.get("mass_fractions")),
                "solvable": stream["amount"].get("provenance") == "unknown",
                "description": stream.get("note", ""),
                "metadata": {"stream_id": sid, "role": "stream_total",
                             "direction": direction,
                             "declared_provenance":
                                 stream["amount"].get("provenance", "reported")},
            })
        for cid, frac in (stream.get("mass_fractions") or {}).items():
            ports.append({
                "port_id": f"in:{sid}:w:{cid}",
                "direction": "input",
                "quantity": "mass_fraction",
                "unit": frac.get("unit", "1"),
                "label": f"{label}: mass fraction of {cid}",
                "component": cid,
                "components": [cid],
                "temporal_basis": "not_applicable",
                "required": False,
                "provenance_requirement": "explained",
                "attribution_required": False,
                "solvable": frac.get("provenance") == "unknown",
                "description": "",
                "metadata": {"stream_id": sid, "role": "mass_fraction",
                             "direction": direction,
                             "declared_provenance":
                                 frac.get("provenance", "reported")},
            })
        for cid, value in (stream.get("component_amounts") or {}).items():
            kind = _slot_kind(spec, sid, "mass")
            ports.append({
                "port_id": f"in:{sid}:{cid}",
                "direction": "input",
                "quantity": kind,
                "unit": value.get("unit") or _unit_for(spec, sid, kind),
                "label": f"{label}: {cid}",
                "component": cid,
                "components": [cid],
                "temporal_basis": (
                    "rate" if QuantityKind(kind).value.endswith("_flow")
                    else "inventory"
                ),
                "required": False,
                "provenance_requirement": "explained",
                "attribution_required": False,
                "solvable": value.get("provenance") == "unknown",
                "description": value.get("note", ""),
                "metadata": {"stream_id": sid, "role": "component_amount",
                             "direction": direction,
                             "declared_provenance":
                                 value.get("provenance", "reported")},
            })

    # Output ports: declared for every stream/slot plus the residuals, so the
    # canvas is complete before a run and the diagnostics view can name a port
    # that produced nothing.
    for stream in spec["streams"]:
        sid = stream["stream_id"]
        label = stream.get("label", sid)
        kind = _slot_kind(spec, sid, "mass")
        unit = _unit_for(spec, sid, kind)
        ports.append({
            "port_id": f"out:{sid}:total",
            "direction": "output",
            "quantity": kind,
            "unit": unit,
            "label": f"{label}: total",
            "component": None,
            "components": sorted(
                {c["component_id"] for c in spec["components"]}
                | set(stream.get("absent_components", ()) or ())
                | set(stream.get("component_amounts") or {})
                | set(stream.get("mass_fractions") or {})
            ),
            "temporal_basis": "rate" if kind.endswith("_flow") else "inventory",
            "required": False,
            "provenance_requirement": "explained",
            "attribution_required": True,
            "solvable": False,
            "description": "sum of the stream's component amounts",
            "metadata": {"stream_id": sid, "role": "stream_total"},
        })
        for cid in (stream.get("component_amounts") or {}
                    or stream.get("mass_fractions") or {}):
            ports.append({
                "port_id": f"out:{sid}:{cid}",
                "direction": "output",
                "quantity": kind,
                "unit": unit,
                "label": f"{label}: {cid}",
                "component": cid,
                "components": [cid],
                "temporal_basis": "rate" if kind.endswith("_flow") else "inventory",
                "required": False,
                "provenance_requirement": "explained",
                "attribution_required": False,
                "solvable": True,
                "description": "",
                "metadata": {"stream_id": sid, "role": "component_amount"},
            })
            ports.append({
                "port_id": f"out:{sid}:w:{cid}",
                "direction": "output",
                "quantity": "mass_fraction",
                "unit": "1",
                "label": f"{label}: mass fraction of {cid}",
                "component": cid,
                "components": [cid],
                "temporal_basis": "not_applicable",
                "required": False,
                "provenance_requirement": "explained",
                "attribution_required": False,
                "solvable": True,
                "description": "",
                "metadata": {"stream_id": sid, "role": "mass_fraction"},
            })
    ports.append({
        "port_id": "out:residual:total",
        "direction": "output",
        "quantity": _slot_kind(spec, spec["streams"][0]["stream_id"], "mass"),
        "unit": _unit_for(spec, spec["streams"][0]["stream_id"],
                          _slot_kind(spec, spec["streams"][0]["stream_id"], "mass")),
        "label": "total mass balance residual",
        "component": None,
        "components": [c["component_id"] for c in spec["components"]],
        "temporal_basis": "rate" if spec["process_mode"] == "steady_state"
        else "inventory",
        "required": False,
        "provenance_requirement": "explained",
        "attribution_required": False,
        "solvable": False,
        "description": "sec. 4.6.2 check: recomputed from the solved numbers",
        "metadata": {"role": "residual"},
    })
    for comp in spec["components"]:
        ports.append({
            "port_id": f"out:residual:{comp['component_id']}",
            "direction": "output",
            "quantity": _slot_kind(spec, spec["streams"][0]["stream_id"], "mass"),
            "unit": _unit_for(spec, spec["streams"][0]["stream_id"],
                              _slot_kind(spec, spec["streams"][0]["stream_id"],
                                         "mass")),
            "label": f"{comp.get('label', comp['component_id'])} balance residual",
            "component": comp["component_id"],
            "components": [comp["component_id"]],
            "temporal_basis": "rate" if spec["process_mode"] == "steady_state"
            else "inventory",
            "required": False,
            "provenance_requirement": "explained",
            "attribution_required": False,
            "solvable": False,
            "description": "sec. 4.6.2 check: recomputed from the solved numbers",
            "metadata": {"role": "residual"},
        })

    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "title": spec.get("label", spec["system_id"]),
        "summary": (
            f"Morris, Geiger & Fine (2011) Chapter 4 {spec['process_mode']} "
            f"balance over {spec['system_id']} on a {spec.get('basis', 'mass')} "
            f"basis. Non-reacting systems only: no stoichiometry, no reaction terms."
        ),
        "adapter": "composition.adapters.morris.MorrisAdapter",
        "source_ref": spec.get("source_ref", "Morris et al. 2011, Chapter 4"),
        "ports": ports,
        "parameters": {
            "system_id": spec["system_id"],
            "process_mode": spec["process_mode"],
            "basis": spec.get("basis", "mass"),
            "components": [c["component_id"] for c in spec["components"]],
            "streams": [s["stream_id"] for s in spec["streams"]],
            "total_balance": bool(spec.get("total_balance", False)),
            "balances": spec.get("balances"),
            "residual_tolerance": spec.get("residual_tolerance", 1.0e-6),
        },
        "parameter_sections": {
            "control volume": {
                "system_id": spec["system_id"],
                "process_mode": spec["process_mode"],
                "basis": spec.get("basis", "mass"),
            },
            "assumptions": [
                {"assumption_id": a["assumption_id"], "statement": a["statement"],
                 "rationale": a.get("rationale", ""),
                 "affects": list(a.get("affects", ()))}
                for a in spec.get("assumptions", ())
            ],
        },
        "capabilities": [
            "component_balance", "total_mass_balance", "composition_sum",
            "batch_ledger", "solvability_classification", "residual_reporting",
            "degree_of_freedom_bookkeeping",
        ],
        "unsupported_capabilities": {
            "reactive_balance": (
                "Chapter 4 is titled 'Fundamentals of Material Balances with "
                "Applications to Non-Reacting Systems'. The generated equations "
                "are sum(inflow) - sum(outflow) [- accumulation] = 0 and "
                "BalanceSystem has no field in which a reaction term could be "
                "declared."
            ),
            "stoichiometry": "no reaction or conversion field exists in the schema",
            "kinetics": "no rate law is implemented or declared",
            "empirical_fitting": "no correlation fitting; over-determined data is "
                                 "checked, never fitted",
            "reconciliation": "an inconsistent system is reported with residuals "
                              "and solved for nothing",
        },
        "reaction_terms": [],
        "conversion_models": [],
        "non_reacting_only": True,
        "assumptions": spec.get("assumptions", []),
    }


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def _run(spec: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    mb = _schemas()
    engine = _engine()
    system = build_system(spec, inputs)
    result = engine.solve_balance(system)

    base = result.basis_unit
    streams = {s.stream_id: s for s in system.streams}
    component_ids = [c.component_id for c in system.components]

    #: port_id -> payload.  A later publish *replaces* an earlier one, so a
    #: solved value wins over the "still unknown" placeholder declared for it.
    published: dict[str, dict[str, Any]] = {}

    def emit(port_id, state, value, unit, components, *, reason="", kind=None,
             source_ref=None, method=None, extra=None):
        published[port_id] = {
            "port_id": port_id,
            "state": state,
            "value": value,
            "unit": unit,
            "kind": kind or "",
            "components": list(components),
            "reason": reason,
            "source_ref": source_ref,
            "method": method,
            "extra": extra or {},
        }

    def declared_components_of(stream) -> list[str]:
        """Every component this stream can account for, declared or absent."""
        return sorted(set(stream.components_declared) | set(stream.absent_components))

    # -- declared, known inputs are echoed so a downstream port can read them --
    for stream in system.streams:
        sid = stream.stream_id
        declared_components = declared_components_of(stream)
        if stream.amount is not None and isinstance(stream.amount, mb.Quantity):
            emit(f"out:{sid}:total", "number", stream.amount.base_value,
                 base, declared_components, source_ref=stream.amount.source_ref,
                 method=f"declared total of {sid}", kind=stream.kind.value)
        for cid, frac in stream.mass_fractions.items():
            if isinstance(frac, mb.Quantity):
                emit(f"out:{sid}:w:{cid}", "number", frac.base_value, "1", [cid],
                     source_ref=frac.source_ref,
                     method=f"declared mass fraction of {cid} in {sid}",
                     kind="mass_fraction")
        for cid, value in stream.component_amounts.items():
            if isinstance(value, mb.Quantity):
                emit(f"out:{sid}:{cid}", "number", value.base_value, base, [cid],
                     source_ref=value.source_ref,
                     method=f"declared {cid} flow in {sid}", kind=stream.kind.value)

    solved = {v.variable_id: v for v in result.variables}
    free = {u.variable_id: u for u in result.unresolved}

    #: Morris sec. 4.7.2: an under-specified balance "may still give useful
    #: information", and the engine reports the pivot variables as that
    #: information while naming the free ones.  A pivot value in an
    #: under-determined system is a canonical member of a one-parameter family,
    #: **not** a determined quantity, and it has to be labelled as such -- an
    #: undeclared input reported as 0.0 would be precisely the fabrication this
    #: whole project exists to prevent.
    underdetermined = result.solvability.value == "underdetermined"
    free_ids = sorted(u.variable_id for u in result.unresolved)
    family_note = (
        f" NOTE: the system is under-determined ({result.n_unknowns} unknowns, "
        f"rank {result.rank}); this is the canonical member of a "
        f"{result.n_unknowns - result.rank}-parameter family, not a determined "
        f"value. Free variables: {', '.join(free_ids) if free_ids else 'none'}."
    )

    for vid, variable in solved.items():
        parts = vid.split(":")
        if parts[0] != "stream":
            continue
        sid = parts[1]
        cid = parts[2]
        stream = streams.get(sid)
        if stream is None:
            continue
        method = f"solved: {variable.method}"
        if underdetermined:
            method += family_note
        extra = {"inputs": list(variable.inputs)}
        if underdetermined:
            extra["determination"] = "representative"
        if cid == "total":
            emit(f"out:{sid}:total", "number", variable.value, variable.unit,
                 declared_components_of(stream),
                 method=method,
                 kind=stream.kind.value,
                 extra=extra)
        elif cid.startswith("w:"):
            emit(f"out:{sid}:w:{cid[2:]}", "number", variable.value, variable.unit,
                 [cid[2:]], method=method,
                 kind="mass_fraction", extra=extra)
        else:
            emit(f"out:{sid}:{cid}", "number", variable.value, variable.unit, [cid],
                 method=method, kind=stream.kind.value, extra=extra)

    for vid, unresolved in free.items():
        parts = vid.split(":")
        if parts[0] != "stream" or len(parts) < 3:
            continue
        sid = parts[1]
        cid = parts[2]
        stream = streams.get(sid)
        if stream is None:
            continue
        if cid == "total":
            port = f"out:{sid}:total"
            components = declared_components_of(stream)
            kind = stream.kind.value
        elif cid.startswith("w:"):
            port = f"out:{sid}:w:{cid[2:]}"
            components = [cid[2:]]
            kind = "mass_fraction"
        else:
            port = f"out:{sid}:{cid}"
            components = [cid]
            kind = stream.kind.value
        if port in published:
            continue
        emit(port, "unresolved", None, unresolved.unit, components,
             reason=unresolved.reason, kind=kind)

    # -- totals and fractions derived from the ledger ------------------------
    ledger_by_stream: dict[str, list[Any]] = {}
    for row in result.ledger:
        ledger_by_stream.setdefault(row.stream_id, []).append(row)

    for sid, rows in ledger_by_stream.items():
        stream = streams.get(sid)
        if stream is None:
            continue
        have = {r.component_id for r in rows}
        # A component the stream *declares absent* contributes a known zero and
        # does not make the total indeterminate. One it merely fails to mention
        # does, because the omission is a strong reading that may be wrong.
        missing = [
            c for c in component_ids
            if c not in have and c not in stream.absent_components
        ]
        if f"out:{sid}:total" not in published:
            if missing:
                emit(f"out:{sid}:total", "unresolved", None, base, sorted(have),
                     reason=(
                         f"the total of {sid} is the sum of its component amounts, "
                         f"and {missing} could not be determined. Summing over the "
                         f"components that did resolve would understate the stream, "
                         f"so no total is reported."
                     ),
                     kind=stream.kind.value)
            else:
                total = sum(r.value for r in rows)
                emit(f"out:{sid}:total", "number", total, base,
                     declared_components_of(stream),
                     method=(
                         f"sum of the solved component amounts of {sid}: "
                         + " + ".join(f"{r.component_id}={r.value:g}" for r in rows)
                     ),
                     kind=stream.kind.value,
                     source_ref="Morris et al. 2011, sec. 4.5 (ledger)")
        for row in rows:
            if row.mass_fraction is not None and (
                f"out:{sid}:w:{row.component_id}" not in published
            ):
                emit(f"out:{sid}:w:{row.component_id}", "number",
                     row.mass_fraction, "1", [row.component_id],
                     method=f"{row.component_id} in {sid} divided by the stream total",
                     kind="mass_fraction")

    # -- residuals -----------------------------------------------------------
    for residual in result.component_residuals:
        emit(f"out:residual:{residual.component_id}", "number", residual.value,
             residual.unit, [residual.component_id] if residual.component_id else [],
             method=(
                 f"recomputed from the solved numbers after the solve "
                 f"(Morris et al. 2011, sec. 4.6.2 step 3); tolerance "
                 f"{residual.tolerance:g} {residual.basis_unit}"
             ),
             kind="mass",
             extra={
                 "within_tolerance": residual.is_within_tolerance,
                 "tolerance": residual.tolerance,
                 "contributions": [c.to_dict() for c in residual.contributions],
             })
    if result.total_mass_residual is not None:
        residual = result.total_mass_residual
        emit("out:residual:total", "number", residual.value, residual.unit, [],
             method=(
                 f"recomputed from the solved numbers after the solve "
                 f"(Morris et al. 2011, sec. 4.6.2 step 3); tolerance "
                 f"{residual.tolerance:g} {residual.basis_unit}"
             ),
             kind="mass",
             extra={
                 "within_tolerance": residual.is_within_tolerance,
                 "tolerance": residual.tolerance,
                 "contributions": [c.to_dict() for c in residual.contributions],
             })

    diagnostics = [d.to_dict() for d in result.diagnostics]
    payload = result.to_dict()

    #: published in a stable order so two runs of the same system emit the same
    #: port sequence, byte for byte
    outputs = [published[pid] for pid in sorted(published)]

    inconsistent = result.solvability.value == "inconsistent"
    error = None
    if inconsistent:
        error = (
            f"the declared readings of {result.system_id} contradict each other: "
            f"{len(result.inconsistent_equation_ids)} equation(s) cannot all be "
            f"satisfied. Nothing was solved and no measurement was altered. "
            f"Residuals are reported so the conflicting readings can be identified, "
            f"but Morris et al. 2011 sec. 4.7 requires a judgement about which "
            f"reading is least accurate, and this engine has no basis for making it."
        )
        diagnostics.append({
            "code": "execution.inconsistent",
            "severity": "error",
            "message": error,
            "where": [result.system_id, *result.inconsistent_equation_ids],
        })

    return {
        "ok": not inconsistent,
        "error": error,
        "outputs": outputs,
        "diagnostics": diagnostics,
        "residuals": [
            r.to_dict() for r in (*result.component_residuals,
                                  *((result.total_mass_residual,)
                                    if result.total_mass_residual else ()))
        ],
        "summary": {
            "system_id": result.system_id,
            "label": result.label,
            "process_mode": result.process_mode.value,
            "basis": result.basis,
            "basis_unit": result.basis_unit,
            "solvability": result.solvability.value,
            "is_consistent": result.is_consistent,
            "balances_close": result.balances_close,
            "n_unknowns": result.n_unknowns,
            "n_equations": result.n_equations,
            "rank": result.rank,
            "underdetermined": underdetermined,
            "free_variable_ids": free_ids,
            "equations": [e.to_dict() for e in result.equations],
            "unresolved": [u.to_dict() for u in result.unresolved],
            "ledger": [r.to_dict() for r in result.ledger],
            "independent_equation_ids": list(result.independent_equation_ids),
            "redundant_equation_ids": list(result.redundant_equation_ids),
            "inconsistent_equation_ids": list(result.inconsistent_equation_ids),
            "assumptions": [a.to_dict() for a in result.assumptions],
        },
        "raw": payload,
        "ok": result.solvability.value != "inconsistent",
    }


# --------------------------------------------------------------------------- #
# protocol
# --------------------------------------------------------------------------- #


def handle(request: Mapping[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    spec = request.get("parameters", {}).get("system") or request.get("system")
    if spec is None:
        return {"ok": False, "error": "no system declaration supplied"}

    if op == "manifest":
        try:
            return {"ok": True, "manifest": build_manifest(spec)}
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()}

    if op == "run":
        try:
            outcome = _run(spec, request.get("inputs") or {})
        except Exception as exc:  # noqa: BLE001 - a model failure is a result
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "diagnostics": [{
                    "code": "execution.model_failed",
                    "severity": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "where": [spec.get("system_id", "unknown")],
                }],
                "outputs": [],
                "summary": {},
            }
        outcome["manifest"] = build_manifest(spec)
        return outcome

    return {"ok": False, "error": f"unknown op {op!r}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", required=True,
                        help="path to the Morris package root")
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