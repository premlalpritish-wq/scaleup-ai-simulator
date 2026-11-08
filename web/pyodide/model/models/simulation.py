"""Simulation orchestration: run a batch or fed-batch trajectory, with provenance.

This module owns three things and nothing else:

* choosing the right-hand side for the operating mode, so batch and fed-batch
  are never one ambiguous expression;
* collecting the full state trajectory and the solver's own report;
* producing the provenance record -- parameters, initial conditions, feed
  program, solver configuration, equations version and an input digest.

It refuses to run without resolved initial conditions
(:class:`UnresolvedInitialCondition`) and refuses to hand back a trajectory
whose states are invalid. Both refusals are structured, not exceptions with a
``print`` somewhere.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from schemas.parameters import EQUATIONS_VERSION, ParameterSet, table2_parameter_set
from schemas.provenance import SimulationProvenance
from schemas.state import InitialConditions, State, validate_state
from schemas.units import percent_wv_to_g_per_l

from .batch import batch_derivative
from .diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticList,
    Severity,
    unresolved_transcription_diagnostics,
)
from .fed_batch import FeedProgram, fed_batch_derivative
from .kinetics import TRANSCRIPTION_NOTES
from .solver import IntegrationResult, SolverConfig, integrate

MODEL_ID = "ganjave2022.cybernetic-growth"
MODEL_VERSION = "0.1.0"

MODE_BATCH = "batch"
MODE_FED_BATCH = "fed_batch"
MODES = (MODE_BATCH, MODE_FED_BATCH)


@dataclass(frozen=True)
class SimulationResult:
    """One run: the trajectory, the diagnostics, and where it came from."""

    mode: str
    result: IntegrationResult
    provenance: SimulationProvenance
    diagnostics: DiagnosticList = field(default_factory=DiagnosticList)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.diagnostics.error() and self.result.ok

    @property
    def times_h(self) -> list[float]:
        return list(self.result.times)

    @property
    def states(self) -> list[State]:
        return list(self.result.states)

    @property
    def final_state(self) -> State | None:
        return self.result.final_state

    def series(self, key: str) -> list[float]:
        """One state variable over the trajectory, for the composition layer."""
        return [getattr(s, key) for s in self.result.states]

    def output_quantities(self) -> dict[str, dict[str, Any]]:
        """Final-value outputs with explicit keys, units and value states.

        Shapes the composition engine needs: a stable key, a quantity, a unit,
        whether the number is a number at all, and how it came to exist. The
        simulation's outputs are COMPUTED, always -- nothing here is reported.
        """
        final = self.final_state
        if final is None:
            return {}
        from schemas.state import value_state_of

        from .composition import OUTPUT_PORTS

        out: dict[str, dict[str, Any]] = {}
        for port in OUTPUT_PORTS:
            if port.state_key is None:
                continue
            value = getattr(final, port.state_key)
            out[port.port_id] = {
                "value": value,
                "unit": port.unit,
                "quantity": port.quantity,
                "value_state": value_state_of(value).value,
                "provenance": "computed",
                "basis": "computed",
                "temporal_basis": port.temporal_basis.value,
                "label": port.label,
            }
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.provenance.model_id,
            "model_version": self.provenance.model_version,
            "mode": self.mode,
            "ok": self.ok,
            "times_h": self.times_h,
            "states": [s.to_dict() for s in self.result.states],
            "solver_report": self.result.solver_report(),
            "diagnostics": self.diagnostics.to_list(),
            "provenance": self.provenance.to_dict(),
            "outputs": self.output_quantities(),
            "metadata": dict(self.metadata),
        }


def _digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical JSON of the run inputs."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def simulate(
    *,
    initial_conditions: InitialConditions,
    duration_h: float,
    mode: str = MODE_BATCH,
    feed: FeedProgram | None = None,
    parameters: ParameterSet | None = None,
    solver: SolverConfig | None = None,
    output_times_h: Sequence[float] | None = None,
) -> SimulationResult:
    """Integrate the printed balances and return the trajectory with provenance.

    ``initial_conditions`` must already be resolved: constructing it is what
    refuses a missing value, so this function cannot be handed a half-populated
    culture.

    ``feed`` is required for ``fed_batch`` and rejected for ``batch``. That is
    the point of keeping the two modes separate -- a batch run cannot quietly
    apply a dilution term because a feed object happened to be passed.
    """
    parameters = parameters or table2_parameter_set()
    solver = solver or SolverConfig()

    diagnostics = DiagnosticList()
    diagnostics.extend(unresolved_transcription_diagnostics(TRANSCRIPTION_NOTES))

    if mode not in MODES:
        diagnostics.append(
            Diagnostic(
                code=DiagnosticCode.INPUT_INVALID,
                severity=Severity.ERROR,
                message=f"mode must be one of {list(MODES)}, got {mode!r}",
                where="simulate",
            )
        )
        return _failed(mode, initial_conditions, feed, parameters, solver, diagnostics)

    if mode == MODE_BATCH and feed is not None:
        diagnostics.append(
            Diagnostic(
                code=DiagnosticCode.INPUT_INVALID,
                severity=Severity.ERROR,
                message=(
                    "a feed program was supplied for a batch run. Batch mode has "
                    "no feed: eq. (8)-(11) carry neither the dilution nor the "
                    "volume term. Use mode='fed_batch', or drop the feed."
                ),
                where="simulate",
                remediation="Operating mode is explicit; it is never inferred.",
            )
        )
        return _failed(mode, initial_conditions, feed, parameters, solver, diagnostics)

    if mode == MODE_FED_BATCH and feed is None:
        diagnostics.append(
            Diagnostic(
                code=DiagnosticCode.INPUT_MISSING,
                severity=Severity.ERROR,
                message=(
                    "fed_batch mode needs a FeedProgram: eq. (13)-(16) read S10, "
                    "S20 and F, and the paper prints no single feed program that "
                    "applies to every run"
                ),
                where="simulate",
                remediation=(
                    "FeedProgram.from_recipe(glycerol_percent_wv=17.5, "
                    "yeast_extract_percent_wv=24.5, flow_mL_per_h=0.72, "
                    "start_time_h=6.0) is the recipe the paper reports as its "
                    "selected optimum (p. 7)."
                ),
            )
        )
        return _failed(mode, initial_conditions, feed, parameters, solver, diagnostics)

    if duration_h <= 0.0:
        diagnostics.append(
            Diagnostic(
                code=DiagnosticCode.INPUT_INVALID,
                severity=Severity.ERROR,
                message=f"duration_h must be positive, got {duration_h!r}",
                where="simulate",
            )
        )
        return _failed(mode, initial_conditions, feed, parameters, solver, diagnostics)

    start = initial_conditions.initial_state(t=0.0)

    def rhs(t: float, y: tuple[float, ...]) -> tuple[float, ...]:
        state = State.from_vector(t, y)
        if mode == MODE_BATCH:
            return batch_derivative(state, parameters)
        assert feed is not None
        return fed_batch_derivative(state, feed, parameters, t=t)

    integration = integrate(
        rhs,
        0.0,
        start.as_vector(),
        float(duration_h),
        config=solver,
        output_times=list(output_times_h) if output_times_h else None,
    )
    diagnostics.extend(integration.diagnostics)

    provenance = _provenance(
        mode, initial_conditions, feed, parameters, solver, output_times_h
    )

    metadata: dict[str, Any] = {
        "solver": solver.to_dict(),
        "equations_version": EQUATIONS_VERSION,
        "parameter_set_id": parameters.parameter_set_id,
        "parameter_set_version": parameters.version,
        "transcription_notes": [n.to_dict() for n in TRANSCRIPTION_NOTES],
        "mode_is_explicit": True,
    }
    if feed is not None:
        metadata["feed"] = feed.to_dict()
        metadata["feed_recipe_percent_wv"] = {
            "glycerol": feed.S10_g_per_L / 10.0,
            "yeast_extract": feed.S20_g_per_L / 10.0,
            "note": "S10/S20 stored in g/L; percent w/v = g/L / 10",
        }

    return SimulationResult(
        mode=mode,
        result=integration,
        provenance=provenance,
        diagnostics=diagnostics,
        metadata=metadata,
    )


def _provenance(
    mode: str,
    initial: InitialConditions,
    feed: FeedProgram | None,
    parameters: ParameterSet,
    solver: SolverConfig,
    output_times: Sequence[float] | None,
) -> SimulationProvenance:
    payload = {
        "parameters": parameters.to_dict(),
        "initial_conditions": initial.to_dict(),
        "feed": feed.to_dict() if feed else None,
        "solver": solver.to_dict(),
        "mode": mode,
        "output_times_h": list(output_times) if output_times else None,
        "equations_version": EQUATIONS_VERSION,
    }
    return SimulationProvenance(
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        equations_version=EQUATIONS_VERSION,
        source_id="ganjave2022",
        parameters=parameters.to_dict(),
        initial_conditions=initial.to_dict(),
        feed=feed.to_dict() if feed else {},
        solver=solver.to_dict(),
        initial_condition_provenance=initial.provenance_summary(),
        input_digest=_digest(payload),
    )


def _failed(
    mode: str,
    initial: InitialConditions,
    feed: FeedProgram | None,
    parameters: ParameterSet,
    solver: SolverConfig,
    diagnostics: DiagnosticList,
) -> SimulationResult:
    return SimulationResult(
        mode=mode,
        result=IntegrationResult(),
        provenance=_provenance(mode, initial, feed, parameters, solver, None),
        diagnostics=diagnostics,
        metadata={"solver": solver.to_dict()},
    )


def expected_final_volume(initial_volume_L: float, flow_L_per_h: float,
                          duration_h: float, start_time_h: float = 0.0) -> float:
    """Analytic value of eq. (16) for a constant feed rate.

    Reported by the solver so the integration and the closed form can be
    compared; a fed-batch volume is the one quantity in this model with an exact
    solution, so a disagreement between the two is unambiguous evidence of an
    integration fault.
    """
    if flow_L_per_h < 0.0:
        raise ValueError("feed flow rate must be non-negative")
    feeding_time = max(0.0, duration_h - start_time_h)
    return initial_volume_L + flow_L_per_h * feeding_time