"""The composition engine.

Four phases, in order, and no phase may skip a check that a later one assumes:

1. **load**   -- build every instance's manifest and validate it against the
   contract it claims (Phase 3 operations 1, 5).
2. **connect**-- validate every connection's ports, quantities, units,
   components and capabilities (operations 3, 4, 5, 9).
3. **plan**   -- topologically order the instances and reject cycles with the
   participating nodes named (operation 6, 7).
4. **execute**-- run each instance in order, pass values down through declared
   mappings, and collect structured results (operations 8, 10, 11, 12).

The engine never silently repairs a graph.  Every refusal is a
:class:`ModelDiagnostic` with a code, a location and a remediation string, and a
graph with any error diagnostic does not execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .adapters import DEFAULT_VERSIONS, adapter_for
from . import cross_model
from . import report
from .contracts import (
    CONTRACT_VERSION,
    CompositionGraph,
    CompositionResult,
    Connection,
    ExecutionPlan,
    ExecutionStep,
    ModelInput,
    ModelInstance,
    ModelManifest,
    ModelOutput,
    ModelRunResult,
    ModelValue,
    PortDefinition,
    PortRef,
    ProvenanceRecord,
    ResidualReport,
    RunStatus,
    ValueProvenance,
    ValueState,
    convert_value,
)
from .diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from .quantities import Quantity, QuantityError, convert


class CompositionError(RuntimeError):
    """The engine cannot proceed. Always carries the diagnostics that explain."""


@dataclass
class ValidatedInstance:
    """One instance with its manifest resolved."""

    instance: ModelInstance
    manifest: ModelManifest | None
    diagnostics: list[ModelDiagnostic] = field(default_factory=list)

    @property
    def ports(self) -> Mapping[str, PortDefinition]:
        if self.manifest is None:
            return {}
        return {p.port_id: p for p in self.manifest.ports}

    def port(self, port_id: str) -> PortDefinition | None:
        return self.ports.get(port_id)


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #


class CompositionEngine:
    """Builds, validates, orders and runs a :class:`CompositionGraph`."""

    def __init__(self, base_path=None, adapters=None) -> None:
        self._base = base_path
        #: Optional per-run adapters, keyed by model id. This is how a model
        #: generated for one research run is executed without adding it to the
        #: global ``REGISTRATIONS`` list. The default is empty: every ordinary
        #: graph resolves exactly as before.
        self._adapters: dict[str, Any] = dict(adapters or {})
        self._adapter_cache: dict[str, tuple[Any, list[ModelDiagnostic]]] = {}
        self._manifest_cache: dict[str, tuple[ModelManifest | None,
                                              list[ModelDiagnostic]]] = {}

    def _adapter_for(
        self, model_id: str
    ) -> tuple[Any, list[ModelDiagnostic]]:
        """Resolve one model id, honouring a per-run injected adapter.

        The engine resolves an adapter twice for an instance: once to read its
        manifest and once to execute it.  Both calls must see the same injected
        adapter, so the resolution is cached here.  Registered models keep their
        existing resolution path and diagnostics.
        """
        if model_id in self._adapter_cache:
            return self._adapter_cache[model_id]
        injected = self._adapters.get(model_id)
        if injected is not None:
            adapter = injected() if callable(injected) else injected
            resolved = (adapter, [])
        else:
            resolved = adapter_for(model_id, self._base)
        self._adapter_cache[model_id] = resolved
        return resolved

    # -- phase 1: load manifests --------------------------------------------

    def manifest_for(
        self, instance: ModelInstance
    ) -> tuple[ModelManifest | None, list[ModelDiagnostic]]:
        """Build (and cache) an instance's manifest."""
        diagnostics: list[ModelDiagnostic] = []
        expected = DEFAULT_VERSIONS.get(instance.model_id)
        declared = instance.model_version
        if (declared not in ("", "unversioned")
                and expected is not None and declared != expected):
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MODEL_VERSION_MISMATCH,
                    severity=Severity.ERROR,
                    message=(
                        f"the graph declares {instance.model_id} version "
                        f"{declared!r} but the installed model is {expected!r}. "
                        f"Running it anyway would make the result's provenance "
                        f"unverifiable, because a reader could not tell which "
                        f"version produced the numbers."
                    ),
                    where=("instance", instance.instance_id),
                    origin=Origin.MANIFEST,
                    remediation=(
                        f"Set model_version to {expected!r}, or install the "
                        f"declared version."
                    ),
                    model_id=instance.model_id,
                    model_version=declared,
                )
            )

        adapter, load_diagnostics = self._adapter_for(instance.model_id)
        if adapter is None:
            return None, diagnostics + load_diagnostics
        key = f"{instance.model_id}|{_canonical(instance.parameters)}"
        if key in self._manifest_cache:
            cached_manifest, cached_diagnostics = self._manifest_cache[key]
            return cached_manifest, diagnostics + list(cached_diagnostics)
        manifest, load_diagnostics = adapter.manifest(instance.parameters)
        diagnostics.extend(load_diagnostics)
        if manifest is not None:
            diagnostics.extend(manifest.validate_against_contract())
        self._manifest_cache[key] = (manifest, list(diagnostics))
        return manifest, diagnostics

    def load(self, graph: CompositionGraph) -> dict[str, ValidatedInstance]:
        out: dict[str, ValidatedInstance] = {}
        for instance in graph.instances:
            manifest, diagnostics = self.manifest_for(instance)
            out[instance.instance_id] = ValidatedInstance(
                instance=instance, manifest=manifest, diagnostics=diagnostics
            )
        return out

    # -- phase 2: connections ------------------------------------------------

    def validate_connections(
        self,
        graph: CompositionGraph,
        loaded: Mapping[str, ValidatedInstance],
    ) -> list[ModelDiagnostic]:
        """Check every connection, and refuse the ones that cannot be made."""
        diagnostics: list[ModelDiagnostic] = []

        for connection in graph.connections:
            diagnostics.extend(
                self._validate_connection(graph, loaded, connection)
            )

        # one value per input port, at most
        targets: dict[str, list[str]] = {}
        for connection in graph.connections:
            targets.setdefault(connection.target.key, []).append(
                connection.connection_id
            )
        for key, ids in sorted(targets.items()):
            if len(ids) > 1:
                diagnostics.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_MISSING_REQUIRED,
                        severity=Severity.ERROR,
                        message=(
                            f"{len(ids)} connections feed {key} ({', '.join(ids)}). "
                            f"An input port takes one value; adding several would "
                            f"mean silently picking one."
                        ),
                        where=("connection", *ids),
                        origin=Origin.CONNECTION,
                        remediation="Keep one connection per input port.",
                    )
                )
        return diagnostics

    def _validate_connection(
        self,
        graph: CompositionGraph,
        loaded: Mapping[str, ValidatedInstance],
        connection: Connection,
    ) -> list[ModelDiagnostic]:
        out: list[ModelDiagnostic] = []
        where = ("connection", connection.connection_id)

        if connection.source.instance_id == connection.target.instance_id:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CONNECTION_SELF_LOOP,
                    severity=Severity.ERROR,
                    message=(
                        f"connection {connection.connection_id!r} links "
                        f"{connection.source.instance_id} to itself. v0.1 has no "
                        f"iterative solve, so a self-loop could never be ordered."
                    ),
                    where=where,
                    origin=Origin.CONNECTION,
                    remediation="Remove the connection.",
                )
            )
            return out

        for side, ref in (("source", connection.source), ("target", connection.target)):
            if ref.instance_id not in loaded:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.GRAPH_UNKNOWN_INSTANCE,
                        severity=Severity.ERROR,
                        message=(
                            f"the {side} of connection "
                            f"{connection.connection_id!r} names instance "
                            f"{ref.instance_id!r}, which the graph does not contain."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        remediation=(
                            f"Known instances: "
                            f"{[i.instance_id for i in graph.instances]}"
                        ),
                    )
                )
                return out

        source_entry = loaded[connection.source.instance_id]
        target_entry = loaded[connection.target.instance_id]
        if source_entry.manifest is None or target_entry.manifest is None:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.MANIFEST_INVALID,
                    severity=Severity.ERROR,
                    message=(
                        f"connection {connection.connection_id!r} cannot be checked "
                        f"because one of its endpoints has no manifest."
                    ),
                    where=where,
                    origin=Origin.CONNECTION,
                )
            )
            return out

        source_manifest = source_entry.manifest
        target_manifest = target_entry.manifest

        try:
            source_port = source_manifest.port(connection.source.port_id)
        except KeyError as exc:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.GRAPH_UNKNOWN_PORT,
                    severity=Severity.ERROR,
                    message=str(exc),
                    where=where,
                    origin=Origin.CONNECTION,
                    remediation="Check the port id in the inspector.",
                    model_id=source_manifest.model_id,
                    model_version=source_manifest.model_version,
                )
            )
            return out
        try:
            target_port = target_manifest.port(connection.target.port_id)
        except KeyError as exc:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.GRAPH_UNKNOWN_PORT,
                    severity=Severity.ERROR,
                    message=str(exc),
                    where=where,
                    origin=Origin.CONNECTION,
                    remediation="Check the port id in the inspector.",
                    model_id=target_manifest.model_id,
                    model_version=target_manifest.model_version,
                )
            )
            return out

        # -- direction ------------------------------------------------------
        if source_port.direction.value != "output":
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CONNECTION_DIRECTION,
                    severity=Severity.ERROR,
                    message=(
                        f"{connection.source.key} is an input port, so it cannot "
                        f"drive a connection. Connections run output -> input."
                    ),
                    where=where,
                    origin=Origin.CONNECTION,
                )
            )
        if target_port.direction.value != "input":
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CONNECTION_DIRECTION,
                    severity=Severity.ERROR,
                    message=(
                        f"{connection.target.key} is an output port, so it cannot "
                        f"receive a connection."
                    ),
                    where=where,
                    origin=Origin.CONNECTION,
                )
            )
        if out:
            return out

        # -- unusable ports -------------------------------------------------
        for port, manifest, side in (
            (source_port, source_manifest, "source"),
            (target_port, target_manifest, "target"),
        ):
            if not port.is_usable:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.VALUE_UNIT_UNREGISTERED,
                        severity=Severity.ERROR,
                        message=(
                            f"the {side} port {port.port_id!r} is unusable: "
                            f"{port.unavailable_reason}"
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        remediation=(
                            "Resolve the declaration gap at source, or map the port "
                            "onto a registered unit explicitly."
                        ),
                        model_id=manifest.model_id,
                        model_version=manifest.model_version,
                    )
                )
        if out:
            return out

        # -- quantity (CG-02, CG-03) ---------------------------------------
        if source_port.quantity is not target_port.quantity:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CONNECTION_QUANTITY_MISMATCH,
                    severity=Severity.ERROR,
                    message=(
                        f"{connection.source.key} carries "
                        f"{source_port.quantity.value} ({source_port.unit}) but "
                        f"{connection.target.key} requires "
                        f"{target_port.quantity.value} ({target_port.unit}). A "
                        f"quantity is not a unit: converting "
                        f"{source_port.unit} to {target_port.unit} would change "
                        f"what the number is, not how it is written."
                    ),
                    where=where,
                    origin=Origin.CONNECTION,
                    remediation=(
                        "Declare a conversion model on the source manifest that "
                        "expresses this relationship, or do not connect the ports."
                    ),
                    model_id=source_manifest.model_id,
                    model_version=source_manifest.model_version,
                    detail={
                        "source_quantity": source_port.quantity.value,
                        "target_quantity": target_port.quantity.value,
                        "source_unit": source_port.unit,
                        "target_unit": target_port.unit,
                    },
                )
            )
            return out

        # -- unit -----------------------------------------------------------
        try:
            convert(1.0, source_port.unit, target_port.unit, source_port.quantity)
        except QuantityError as exc:
            out.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CONNECTION_NON_CONVERTIBLE,
                    severity=Severity.ERROR,
                    message=(
                        f"{connection.source.key} ({source_port.unit}) cannot be "
                        f"expressed as {connection.target.key} ({target_port.unit}): "
                        f"{exc}"
                    ),
                    where=where,
                    origin=Origin.CONNECTION,
                    remediation=(
                        "Supply the missing calibration, or leave the ports "
                        "unconnected and the value unresolved."
                    ),
                    model_id=source_manifest.model_id,
                    model_version=source_manifest.model_version,
                )
            )
            return out

        # -- components (CG-08) ---------------------------------------------
        out.extend(
            self._validate_components(connection, source_port, target_port,
                                      source_manifest, target_manifest)
        )

        # -- temporal basis -------------------------------------------------
        if source_port.temporal_basis is not target_port.temporal_basis:
            source_basis = source_port.temporal_basis.value
            target_basis = target_port.temporal_basis.value
            if {source_basis, target_basis} == {"inventory", "rate"}:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_QUANTITY_MISMATCH,
                        severity=Severity.ERROR,
                        message=(
                            f"{connection.source.key} is an inventory and "
                            f"{connection.target.key} is a rate. Turning one into "
                            f"the other needs an operating interval, which this "
                            f"connection does not declare and the models do not "
                            f"supply: a batch-average rate is not a steady-state one."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        remediation=(
                            "Restate the downstream model on an inventory basis, or "
                            "declare the interval as a conversion model."
                        ),
                        model_id=source_manifest.model_id,
                        model_version=source_manifest.model_version,
                    )
                )
            else:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_QUANTITY_MISMATCH,
                        severity=Severity.WARNING,
                        message=(
                            f"{connection.source.key} has temporal basis "
                            f"{source_basis!r} and {connection.target.key} has "
                            f"{target_basis!r}. The connection is legal; the "
                            f"temporal basis is carried through so the results "
                            f"panel can show it."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                    )
                )

        # -- capabilities (CG-03, CG-09) -----------------------------------
        out.extend(
            self._validate_capabilities(connection, source_port, target_port,
                                        source_manifest, target_manifest)
        )

        # -- cross-model standing (XM-01) -----------------------------------
        # Last, and only when nothing above has already refused the connection.
        # The mechanical rules are more specific about *what* is wrong, and a
        # second diagnostic saying "this boundary is not supported" on top of
        # "the quantities differ" would be noise. What reaches this point has
        # passed quantity, unit, component, direction and capability -- which is
        # exactly the set of connections whose soundness turns on whether the
        # two models mean the same thing, and the set the engine cannot judge.
        if not any(d.is_error for d in out):
            out.extend(
                self._validate_cross_model(connection, source_port, target_port,
                                          source_manifest, target_manifest)
            )
        return out

    @staticmethod
    def _validate_components(
        connection: Connection,
        source_port: PortDefinition,
        target_port: PortDefinition,
        source_manifest: ModelManifest,
        target_manifest: ModelManifest,
    ) -> list[ModelDiagnostic]:
        where = ("connection", connection.connection_id)
        out: list[ModelDiagnostic] = []

        def unattributed(reason: str) -> ModelDiagnostic:
            return ModelDiagnostic(
                code=DiagnosticCode.CONNECTION_COMPONENT_UNATTRIBUTED,
                severity=Severity.ERROR,
                message=(
                    f"{connection.source.key} cannot supply "
                    f"{connection.target.key}: {reason} "
                    f"{source_manifest.model_id} publishes process roles "
                    f"(wet_biomass, inclusion_bodies, chromatographic_fraction, "
                    f"...), which are not conserved chemical entities; no stream of "
                    f"its own carries a component amount or a mass fraction. "
                    f"Assigning it to a component would be an invented scientific "
                    f"assumption, and the assumption would silently determine the "
                    f"answer."
                ),
                where=where,
                origin=Origin.CONNECTION,
                remediation=(
                    "Declare the component mapping explicitly, with a justification "
                    "and a component definition, or do not connect the ports."
                ),
                model_id=source_manifest.model_id,
                model_version=source_manifest.model_version,
            )

        if source_port.component and target_port.component:
            if source_port.component != target_port.component:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_COMPONENT_MISMATCH,
                        severity=Severity.ERROR,
                        message=(
                            f"{connection.source.key} carries component "
                            f"{source_port.component!r} but "
                            f"{connection.target.key} expects "
                            f"{target_port.component!r}. Connecting them would "
                            f"relabel the substance, which is how a copper charge "
                            f"quietly becomes an inclusion-body charge."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        remediation=(
                            "Connect ports that name the same component, or "
                            "declare the equivalence explicitly."
                        ),
                        model_id=source_manifest.model_id,
                        model_version=source_manifest.model_version,
                    )
                )
            return out

        if target_port.component and not source_port.has_component_identity:
            out.append(
                unattributed(
                    f"the target names component {target_port.component!r} and the "
                    f"source names none."
                )
            )
            return out

        if target_port.component and source_port.components:
            if target_port.component not in source_port.components:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_COMPONENT_MISMATCH,
                        severity=Severity.ERROR,
                        message=(
                            f"{connection.source.key} carries components "
                            f"{sorted(source_port.components)}, which does not "
                            f"include {target_port.component!r}."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        model_id=source_manifest.model_id,
                        model_version=source_manifest.model_version,
                    )
                )
            return out

        if target_port.attribution_required and not source_port.has_component_identity:
            out.append(
                unattributed(
                    f"the target is a control-volume total, so every unit entering "
                    f"it must be attributable to a declared component "
                    f"({', '.join(target_port.components)}), and"
                )
            )
            return out

        if source_port.has_component_identity and target_port.component is None:
            source_components = set(source_port.components)
            target_components = set(target_port.components)
            if source_components and not source_components <= target_components:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_COMPONENT_MISMATCH,
                        severity=Severity.ERROR,
                        message=(
                            f"{connection.source.key} carries components "
                            f"{sorted(source_components)} but "
                            f"{connection.target.key} declares "
                            f"{sorted(target_components)}."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                    )
                )
        return out

    @staticmethod
    def _validate_cross_model(
        connection: Connection,
        source_port: PortDefinition,
        target_port: PortDefinition,
        source_manifest: ModelManifest,
        target_manifest: ModelManifest,
    ) -> list[ModelDiagnostic]:
        """Does this connection mean anything between *these two* models?

        Everything above is mechanical. This is the semantic half, and it is
        data rather than inference: :mod:`composition.cross_model` states the
        position between every registered pair and says why. A boundary the
        engine already refuses elsewhere contributes nothing here.
        """
        verdict = cross_model.check(
            source_model=source_manifest.model_id,
            source_port_id=source_port.port_id,
            source_quantity=source_port.quantity.value,
            target_model=target_manifest.model_id,
            target_port_id=target_port.port_id,
            target_quantity=target_port.quantity.value,
        )
        if verdict is None or verdict.permitted:
            return []
        return [
            ModelDiagnostic(
                code=DiagnosticCode.CONNECTION_CROSS_MODEL_REFUSED,
                severity=Severity.ERROR,
                message=(
                    f"{connection.source.key} -> {connection.target.key} is "
                    f"dimensionally legal and scientifically unsupported. "
                    f"{verdict.reason}"
                ),
                where=("connection", connection.connection_id),
                origin=Origin.CONNECTION,
                remediation=verdict.remediation,
                model_id=source_manifest.model_id,
                model_version=source_manifest.model_version,
                detail={
                    "stance": verdict.stance,
                    "quantity_pair": list(verdict.quantity_pair)
                    if verdict.quantity_pair else None,
                    "evidence": list(verdict.evidence),
                    "unresolved": list(verdict.unresolved),
                },
            )
        ]

    @staticmethod
    def _validate_capabilities(
        connection: Connection,
        source_port: PortDefinition,
        target_port: PortDefinition,
        source_manifest: ModelManifest,
        target_manifest: ModelManifest,
    ) -> list[ModelDiagnostic]:
        where = ("connection", connection.connection_id)
        out: list[ModelDiagnostic] = []

        # CG-09: a non-reacting balance may not be drawn across a boundary the
        # source model says is reactive, or across any boundary at all when the
        # source model publishes no component identity or reaction terms.
        if target_manifest.non_reacting_only and not target_manifest.reaction_terms:
            feeds_balance = target_manifest.model_id == "morris2011.material_balance"
            if not feeds_balance:
                return out
            source_has_components = any(
                p.has_component_identity for p in source_manifest.ports
            )
            if not source_has_components:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CAPABILITY_REACTIVE_BALANCE_REFUSED,
                        severity=Severity.ERROR,
                        message=(
                            f"{connection.source.key} -> {connection.target.key} "
                            f"would balance material across a boundary of "
                            f"{source_manifest.model_id}, which represents no "
                            f"component identity and no reaction terms. "
                            f"{target_manifest.model_id} is Chapter 4 "
                            f"'Fundamentals of Material Balances with Applications "
                            f"to Non-Reacting Systems': its equations are "
                            f"sum(inflow) - sum(outflow) [- accumulation] = 0 with "
                            f"no reaction term, and BalanceSystem has nowhere to "
                            f"declare one. Applying it here would be numerically "
                            f"valid and physically wrong."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        remediation=(
                            "Provide a non-reactive boundary (a pure transport "
                            "step) with a declared component set, or supply a "
                            "reaction-aware engine and declare its reaction terms on "
                            "the manifest."
                        ),
                        model_id=target_manifest.model_id,
                        model_version=target_manifest.model_version,
                        detail={
                            "source_model": source_manifest.model_id,
                            "target_model": target_manifest.model_id,
                            "source_reaction_terms":
                                list(source_manifest.reaction_terms),
                        },
                    )
                )
            if source_manifest.missing_information:
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CAPABILITY_UNSUPPORTED,
                        severity=Severity.INFO,
                        message=(
                            f"{source_manifest.model_id} declares "
                            f"{len(source_manifest.missing_information)} missing "
                            f"information item(s) that would have to be closed "
                            f"before any balance around it could be trusted."
                        ),
                        where=where,
                        origin=Origin.CONNECTION,
                        model_id=source_manifest.model_id,
                        model_version=source_manifest.model_version,
                    )
                )
        return out

    # -- phase 3: ordering (CG-04, CG-10) -----------------------------------

    def order(
        self, graph: CompositionGraph
    ) -> tuple[list[str], list[ModelDiagnostic]]:
        """Kahn's algorithm with the participating nodes named on failure."""
        diagnostics: list[ModelDiagnostic] = []
        known = {i.instance_id for i in graph.instances}

        deps: dict[str, set[str]] = {i.instance_id: set() for i in graph.instances}
        for connection in graph.connections:
            src = connection.source.instance_id
            dst = connection.target.instance_id
            if src not in known or dst not in known:
                continue
            deps[dst].add(src)

        declared = [i.instance_id for i in graph.instances]
        loaded_position = {
            i.instance_id: dict(i.position) for i in graph.instances
        }

        emitted: set[str] = set()
        order: list[str] = []
        # Determinism: among the instances that are ready at the same moment,
        # the leftmost-and-highest on the canvas goes first, and an instance
        # with no declared position falls back to its declaration order. This
        # only chooses between orderings that are already valid, but it makes
        # the plan stable and it matches what the user sees on the canvas.
        declaration_rank = {i.instance_id: n
                            for n, i in enumerate(graph.instances)}

        def layout_key(instance_id: str) -> tuple[float, float, int]:
            position = loaded_position.get(instance_id) or {}
            x = float(position.get("x", 1.0e9))
            y = float(position.get("y", 0.0))
            return (y, x, declaration_rank.get(instance_id, 0))

        while len(order) < len(declared):
            ready = [
                iid for iid in declared
                if iid not in emitted and deps[iid] <= emitted
            ]
            if not ready:
                cycle = self._find_cycle(deps, declared, emitted)
                if cycle:
                    participants = cycle
                else:
                    participants = [
                        iid for iid in declared if iid not in emitted
                    ]
                chain = " -> ".join(
                    [
                        *participants,
                        participants[0] if participants else "",
                    ]
                )
                out_edges = sorted(
                    c.connection_id
                    for c in graph.connections
                    if c.source.instance_id in participants
                    and c.target.instance_id in participants
                )
                diagnostics.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.ORDER_CYCLE_DETECTED,
                        severity=Severity.ERROR,
                        message=(
                            f"the graph is cyclic and v0.1 has no iterative solve. "
                            f"Participating instances: {participants}. Cycle: {chain}. "
                            f"Connections involved: {out_edges}."
                        ),
                        where=("order", *participants),
                        origin=Origin.ORDERING,
                        remediation=(
                            "Break the cycle: v0.1 executes each instance exactly "
                            "once, in dependency order. A recycle loop needs an "
                            "iteration contract, which is not part of this version."
                        ),
                        detail={
                            "participants": participants,
                            "connections": out_edges,
                        },
                    )
                )
                return [], diagnostics
            # Emit one instance per round and re-evaluate.  Emitting a whole
            # ready set at once is also a valid topological order, but it would
            # place every currently-unblocked instance ahead of a downstream
            # one that is nearly ready, which reads oddly against a canvas
            # laid out left to right.
            ready.sort(key=layout_key)
            order.append(ready[0])
            emitted.add(ready[0])

        return order, diagnostics

    @staticmethod
    def _find_cycle(
        deps: Mapping[str, set[str]], declared: Sequence[str], emitted: set[str]
    ) -> list[str]:
        """Depth-first search for one concrete cycle, so the message can name it."""
        colour: dict[str, int] = {iid: 0 for iid in declared}
        stack: list[str] = []

        def walk(node: str) -> list[str]:
            colour[node] = 1
            stack.append(node)
            for dependency in sorted(deps.get(node, ())):
                if colour.get(dependency, 0) == 0:
                    found = walk(dependency)
                    if found:
                        return found
                elif colour.get(dependency) == 1:
                    return stack[stack.index(dependency):]
            stack.pop()
            colour[node] = 2
            return []

        for node in declared:
            if node in emitted:
                continue
            if colour.get(node, 0) == 0:
                found = walk(node)
                if found:
                    return found
        return []

    # -- phase 4: execute ----------------------------------------------------

    def execute(
        self,
        graph: CompositionGraph,
        *,
        plan_only: bool = False,
    ) -> CompositionResult:
        loaded = self.load(graph)
        diagnostics: list[ModelDiagnostic] = []
        # A model's declared *limitations* are properties of the model, not of
        # the placement. Report them once per model so a graph with five Morris
        # instances does not repeat the same five INFO lines five times; the
        # manifest still carries the full list for the inspector.
        reported_limitations: set[tuple[str, str]] = set()
        for entry in loaded.values():
            for diagnostic in entry.diagnostics:
                if diagnostic.origin is Origin.MANIFEST and not diagnostic.is_error:
                    key = (diagnostic.model_id or "", diagnostic.code.value)
                    if key in reported_limitations:
                        continue
                    reported_limitations.add(key)
                diagnostics.append(diagnostic)

        diagnostics.extend(self.validate_connections(graph, loaded))

        order, order_diagnostics = self.order(graph)
        diagnostics.extend(order_diagnostics)

        required_missing = self._check_required_inputs(graph, loaded, order)

        has_error = any(d.is_error for d in diagnostics) or bool(required_missing)

        if has_error:
            diagnostics.extend(required_missing)
            status = RunStatus.INVALID if not order_diagnostics else RunStatus.REFUSED
            plan = ExecutionPlan(
                plan_id=f"{graph.graph_id}::invalid",
                graph_id=graph.graph_id,
                contract_version=CONTRACT_VERSION,
                steps=(),
                diagnostics=tuple(diagnostics),
                digest="",
            )
            return CompositionResult(
                run_id=f"{graph.graph_id}::invalid",
                graph_id=graph.graph_id,
                contract_version=CONTRACT_VERSION,
                status=status,
                plan=plan,
                diagnostics=tuple(diagnostics),
                composition_report=report.build_report(
                    graph, loaded, diagnostics, None, execution_attempted=False
                ),
                notes=(
                    "The graph was not executed. Every diagnostic above names what "
                    "to change; nothing was silently repaired or partially run."
                ),
            )

        steps: list[ExecutionStep] = []
        for index, instance_id in enumerate(order, start=1):
            entry = loaded[instance_id]
            steps.append(
                ExecutionStep(
                    index=index,
                    instance_id=instance_id,
                    model_id=entry.instance.model_id,
                    model_version=entry.instance.model_version,
                    status=RunStatus.SUCCESS,
                )
            )

        model_versions = {
            instance_id: loaded[instance_id].instance.model_version
            for instance_id in loaded
        }
        plan = ExecutionPlan(
            plan_id=f"{graph.graph_id}::{len(steps)}",
            graph_id=graph.graph_id,
            contract_version=CONTRACT_VERSION,
            steps=tuple(steps),
        )
        plan_digest = plan.compute_digest(
            graph,
            {
                e.instance.model_id: e.manifest.model_version
                for e in loaded.values()
                if e.manifest is not None
            },
        )
        plan = ExecutionPlan(
            plan_id=plan.plan_id,
            graph_id=plan.graph_id,
            contract_version=plan.contract_version,
            steps=plan.steps,
            diagnostics=plan.diagnostics,
            digest=plan_digest,
        )

        if plan_only:
            planned = CompositionResult(
                run_id=f"{graph.graph_id}::plan",
                graph_id=graph.graph_id,
                contract_version=CONTRACT_VERSION,
                status=RunStatus.SUCCESS,
                plan=plan,
                diagnostics=tuple(diagnostics),
                model_versions=model_versions,
                notes="Validation and ordering only; nothing was executed.",
            )
            # Validation and ordering decide every connection's standing, so a
            # plan-only run has just as much to report as a full one. It simply
            # has nothing to say about execution, and the report says that
            # rather than presenting the absence as a refusal.
            return CompositionResult(
                run_id=planned.run_id,
                graph_id=planned.graph_id,
                contract_version=planned.contract_version,
                status=planned.status,
                plan=planned.plan,
                diagnostics=planned.diagnostics,
                model_versions=planned.model_versions,
                notes=planned.notes,
                composition_report=report.build_report(
                    graph, loaded, planned.diagnostics, planned,
                    execution_attempted=False, plan_only=True,
                ),
            )

        results, provenance_index = self._execute_steps(
            graph, loaded, order, diagnostics
        )

        overall = RunStatus.SUCCESS
        for result in results:
            if result.status is RunStatus.FAILED:
                overall = RunStatus.FAILED
                break
            if result.status is RunStatus.SUCCESS_WITH_WARNINGS:
                overall = RunStatus.SUCCESS_WITH_WARNINGS

        result = CompositionResult(
            run_id=f"{graph.graph_id}::{plan_digest[:12]}",
            graph_id=graph.graph_id,
            contract_version=CONTRACT_VERSION,
            status=overall,
            plan=plan,
            results=tuple(results),
            diagnostics=tuple(diagnostics),
            provenance_index=provenance_index,
            model_versions=model_versions,
        )
        digest = result.compute_digest()
        return CompositionResult(
            run_id=result.run_id,
            graph_id=result.graph_id,
            contract_version=result.contract_version,
            status=result.status,
            plan=result.plan,
            results=result.results,
            diagnostics=result.diagnostics,
            provenance_index=result.provenance_index,
            reproducibility=digest,
            model_versions=result.model_versions,
            notes=result.notes,
            # Built after the digest on purpose: the report is a description of
            # the run, and folding it into the reproducibility digest would make
            # the digest change when only the wording of an explanation changed.
            composition_report=report.build_report(
                graph, loaded, result.diagnostics, result,
                execution_attempted=not plan_only,
            ),
        )

    # -- execution internals -------------------------------------------------

    def _check_required_inputs(
        self,
        graph: CompositionGraph,
        loaded: Mapping[str, ValidatedInstance],
        order: Sequence[str],
    ) -> list[ModelDiagnostic]:
        out: list[ModelDiagnostic] = []
        connected = {c.target.key for c in graph.connections}
        literal = set(graph.literal_inputs)
        for instance_id in order:
            entry = loaded[instance_id]
            if entry.manifest is None:
                continue
            for port in entry.manifest.ports_by_direction(_input_direction()):
                if not port.required:
                    continue
                key = PortRef(instance_id, port.port_id).key
                if key in connected or key in literal:
                    continue
                out.append(
                    ModelDiagnostic(
                        code=DiagnosticCode.CONNECTION_MISSING_REQUIRED,
                        severity=Severity.ERROR,
                        message=(
                            f"{key} is a required input of "
                            f"{entry.manifest.model_id} and nothing supplies it. "
                            f"Supplying a default would be an invented value."
                        ),
                        where=("instance", instance_id, "port", port.port_id),
                        origin=Origin.CONNECTION,
                        remediation=(
                            "Connect an upstream port, or declare it under "
                            "literal_inputs."
                        ),
                        model_id=entry.manifest.model_id,
                        model_version=entry.manifest.model_version,
                    )
                )
        return out

    def _execute_steps(
        self,
        graph: CompositionGraph,
        loaded: Mapping[str, ValidatedInstance],
        order: Sequence[str],
        diagnostics: list[ModelDiagnostic],
    ) -> tuple[list[ModelRunResult], dict[str, tuple[ProvenanceRecord, ...]]]:
        results: list[ModelRunResult] = []
        provenance_index: dict[str, tuple[ProvenanceRecord, ...]] = {}
        #: instance_id -> port_id -> output, published as each step completes
        published: dict[str, dict[str, ModelOutput]] = {}
        failed: dict[str, ModelDiagnostic] = {}

        literals = self._build_literals(graph)

        for instance_id in order:
            entry = loaded[instance_id]
            instance = entry.instance
            manifest = entry.manifest
            assert manifest is not None

            # failure propagation: a downstream instance whose upstream failed
            blocked_by = [
                other for other in order
                if other in failed
                and any(
                    c.source.instance_id == other
                    and c.target.instance_id == instance_id
                    for c in graph.connections
                )
            ]
            if blocked_by:
                for other in blocked_by:
                    diagnostics.append(
                        ModelDiagnostic(
                            code=DiagnosticCode.EXECUTION_DEPENDENT_SKIPPED,
                            severity=Severity.ERROR,
                            message=(
                                f"{instance_id} was not executed because "
                                f"{other} failed. It received no values from "
                                f"{other}, and running it anyway would present a "
                                f"result computed from missing data."
                            ),
                            where=("instance", instance_id),
                            origin=Origin.EXECUTION,
                            remediation=(
                                f"Fix {other} first: "
                                f"{failed[other].message}"
                            ),
                            model_id=manifest.model_id,
                            model_version=manifest.model_version,
                            detail={"blocked_by": blocked_by},
                        )
                    )
                results.append(
                    ModelRunResult(
                        instance_id=instance_id,
                        model_id=manifest.model_id,
                        model_version=manifest.model_version,
                        status=RunStatus.FAILED,
                        diagnostics=(),
                    )
                )
                failed[instance_id] = ModelDiagnostic(
                    code=DiagnosticCode.EXECUTION_DEPENDENT_SKIPPED,
                    severity=Severity.ERROR,
                    message=f"{instance_id} skipped: upstream {blocked_by} failed",
                    where=("instance", instance_id),
                    origin=Origin.EXECUTION,
                    model_id=manifest.model_id,
                    model_version=manifest.model_version,
                )
                continue

            # gather connected inputs
            connected_inputs: dict[str, ModelOutput] = {}
            instance_literals: dict[str, ModelInput] = {}

            for connection in graph.connections:
                if connection.target.instance_id != instance_id:
                    continue
                source_outputs = published.get(connection.source.instance_id, {})
                output = source_outputs.get(connection.source.port_id)
                if output is None:
                    diagnostics.append(
                        ModelDiagnostic(
                            code=DiagnosticCode.EXECUTION_NO_OUTPUT,
                            severity=Severity.ERROR,
                            message=(
                                f"connection {connection.connection_id!r} expected "
                                f"{connection.source.key} to carry a value, but the "
                                f"upstream instance published nothing on that port."
                            ),
                            where=("connection", connection.connection_id),
                            origin=Origin.EXECUTION,
                            model_id=manifest.model_id,
                            model_version=manifest.model_version,
                        )
                    )
                    failed[instance_id] = ModelDiagnostic(
                        code=DiagnosticCode.EXECUTION_NO_OUTPUT,
                        severity=Severity.ERROR,
                        message=(
                            f"{connection.source.key} published no value on port "
                            f"{connection.target.port_id}"
                        ),
                        where=("connection", connection.connection_id),
                        origin=Origin.EXECUTION,
                    )
                    continue
                mapped = self._map_value(
                    connection, output, entry, graph, diagnostics
                )
                if mapped is None:
                    continue
                connected_inputs[connection.target.port_id] = mapped

            for key, model_input in literals.items():
                if model_input.ref.instance_id == instance_id:
                    instance_literals[key.split("/", 1)[1]] = model_input

            adapter, _ = self._adapter_for(instance.model_id)
            assert adapter is not None
            adapter_run = adapter.run(
                instance_id, instance.parameters, connected_inputs, instance_literals
            )

            step_diagnostics = list(adapter_run.diagnostics)
            diagnostics.extend(step_diagnostics)

            outputs = adapter_run.outputs
            published[instance_id] = {o.ref.port_id: o for o in outputs}
            for output in outputs:
                provenance_index[output.ref.key] = output.provenance_chain

            step_inputs = [
                ModelInput(
                    ref=PortRef(instance_id, port_id),
                    value=out.value,
                    via="connection",
                    provenance_chain=out.provenance_chain,
                )
                for port_id, out in sorted(connected_inputs.items())
            ]
            step_inputs.extend(
                ModelInput(
                    ref=model_input.ref,
                    value=model_input.value,
                    via=model_input.via,
                    provenance_chain=model_input.provenance_chain,
                )
                for _, model_input in sorted(instance_literals.items())
            )

            step_index: dict[str, tuple[ProvenanceRecord, ...]] = {}
            for output in outputs:
                step_index[f"{instance_id}/{output.ref.port_id}"] = (
                    output.provenance_chain
                )

            failed_here = ModelDiagnostic.execution_failures(step_diagnostics)
            if failed_here:
                status = RunStatus.FAILED
                failed[instance_id] = failed_here[0]
            elif step_diagnostics:
                status = RunStatus.SUCCESS_WITH_WARNINGS
            else:
                status = RunStatus.SUCCESS

            results.append(
                ModelRunResult(
                    instance_id=instance_id,
                    model_id=manifest.model_id,
                    model_version=manifest.model_version,
                    status=status,
                    inputs=tuple(step_inputs),
                    outputs=outputs,
                    residuals=adapter_run.residuals,
                    unresolved=adapter_run.unresolved,
                    diagnostics=tuple(step_diagnostics),
                    raw_summary=dict(adapter_run.summary),
                    provenance_index=step_index,
                )
            )

        return results, provenance_index

    def _map_value(
        self,
        connection: Connection,
        output: ModelOutput,
        entry: ValidatedInstance,
        graph: CompositionGraph,
        diagnostics: list[ModelDiagnostic],
    ) -> ModelOutput | None:
        """Apply a connection's declared transfer to one value (CG-05).

        The value is passed through, carrying its upstream provenance chain.  A
        unit conversion is performed **only** within one quantity, and only when
        the source model does not authorise the conversion explicitly -- which
        it must do through ``conversion_models``.
        """
        manifest = entry.manifest
        assert manifest is not None
        source_port_id = connection.source.port_id
        target_port_id = connection.target.port_id
        target_port = manifest.port(target_port_id)
        source_value = output.value

        chain = output.provenance_chain + (
            ProvenanceRecord(
                kind="transfer",
                producer_model=output.provenance_chain[-1].producer_model
                if output.provenance_chain else "unknown",
                producer_version=output.provenance_chain[-1].producer_version
                if output.provenance_chain else "unknown",
                where=connection.target.key,
                detail=(
                    f"passed through connection {connection.connection_id!r} "
                    f"from {connection.source.key}"
                ),
                connection_id=connection.connection_id,
                source_port=source_port_id,
                target_port=target_port_id,
                method="identity transfer; no value was recomputed",
            ),
        )

        # A non-numeric value is carried through *as non-numeric*. It never
        # becomes a number here (CG-07); the adapter will refuse to inject it.
        if not source_value.is_resolved:
            return ModelOutput(
                ref=connection.target,
                value=source_value,
                provenance_chain=chain,
            )

        if source_value.unit == target_port.unit:
            carried = ModelValue(
                state=source_value.state,
                quantity=source_value.quantity,
                unit=target_port.unit,
                value=source_value.value,
                value_range=source_value.value_range,
                provenance=source_value.provenance,
                components=source_value.components,
                reason=source_value.reason,
                source_ref=source_value.source_ref,
                method=source_value.method,
                chain=source_value.chain,
            )
            return ModelOutput(
                ref=connection.target,
                value=carried,
                provenance_chain=chain,
            )

        try:
            converted, conversion = convert_value(
                source_value, target_port.unit, target_port.quantity
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(
                ModelDiagnostic(
                    code=DiagnosticCode.CONNECTION_NON_CONVERTIBLE,
                    severity=Severity.ERROR,
                    message=(
                        f"connection {connection.connection_id!r} cannot move "
                        f"{connection.source.key} into {connection.target.key}: {exc}"
                    ),
                    where=("connection", connection.connection_id),
                    origin=Origin.CONNECTION,
                    model_id=manifest.model_id,
                    model_version=manifest.model_version,
                )
            )
            return None

        chain = chain + (
            ProvenanceRecord(
                kind="derivation",
                producer_model=manifest.model_id,
                producer_version=manifest.model_version,
                where=connection.target.key,
                detail=(
                    f"unit conversion within the quantity "
                    f"{source_value.quantity.value}: "
                    f"{conversion['from_unit']} -> {conversion['to_unit']}, "
                    f"factor {conversion['factor']:g}"
                ),
                connection_id=connection.connection_id,
                source_port=source_port_id,
                target_port=target_port_id,
                method="same-quantity linear unit conversion",
                conversion=conversion,
            ),
        )
        return ModelOutput(
            ref=connection.target,
            value=converted,
            provenance_chain=chain,
        )

    def _build_literals(
        self, graph: CompositionGraph
    ) -> dict[str, ModelInput]:
        out: dict[str, ModelInput] = {}
        for key, spec in sorted(graph.literal_inputs.items()):
            if "/" not in key:
                continue
            instance_id, port_id = key.split("/", 1)
            ref = PortRef(instance_id, port_id)
            from .quantities import Quantity as _Q

            quantity = _Q(spec["quantity"])
            state = ValueState(spec.get("state", "number"))
            if state.has_number:
                value = ModelValue.number(
                    float(spec["value"]),
                    quantity=quantity,
                    unit=spec["unit"],
                    provenance=ValueProvenance.ASSUMED,
                    source_ref=spec.get("source_ref", key),
                    method=spec.get(
                        "method", "literal input declared on the composition graph"
                    ),
                    reason=spec.get("reason", ""),
                )
            else:
                value = ModelValue.unavailable(
                    state,
                    quantity=quantity,
                    unit=spec.get("unit", ""),
                    reason=spec.get("reason", ""),
                )
            out[f"{instance_id}/{port_id}"] = ModelInput(
                ref=ref,
                value=value,
                via="literal",
                provenance_chain=(
                    ProvenanceRecord(
                        kind="assumption",
                        producer_model="composition",
                        producer_version=CONTRACT_VERSION,
                        where=key,
                        detail=spec.get(
                            "reason", "literal input declared on the graph"
                        ),
                        method=value.method or "",
                        source_ref=value.source_ref,
                    ),
                ),
            )
        return out


def _input_direction():
    from .contracts import PortDirection

    return PortDirection.INPUT


def _canonical(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)