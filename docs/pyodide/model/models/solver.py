"""The ODE solver: explicit Runge-Kutta with step-size control.

**Method.** Classical fourth-order Runge-Kutta (RK4) with an embedded
third-order estimate for local error, i.e. the classical step-doubling
controller. The step is accepted when

    err = |y_full - y_half| <= atol + rtol * max(|y_full|, |y_half|)

with ``y_full`` the single-step result and ``y_half`` two half-steps, and the
next step size is scaled by a bounded factor derived from ``err``. On
rejection the step is halved and retried. Standard library only: the repository
carries no third-party runtime dependency, and a solver whose behaviour cannot
be reproduced exactly would defeat the point of recording a run's provenance.

**Determinism.** The solver has no randomness and no wall-clock or
environment input. The same configuration, the same initial state and the same
right-hand side give bit-identical trajectories, which is what makes the run
digest meaningful.

**What it does not do.** It does not clip states. A negative concentration or a
non-finite value is a failure and is reported as one; silently flooring it at
zero would hide the step that produced it. `schemas.state.validate_state`
raises, and :func:`integrate` converts that into a structured diagnostic with
no result.

**Why the step-size defaults are what they are.** This model is mildly stiff,
and not because of a modelling choice: the reported transfer coefficient is
``kLa = 133 h^-1`` (Table S2, quoted on p. 3), so the dissolved-oxygen state
relaxes with a time constant of ``1/kLa = 7.5e-3 h`` while the biomass dynamics
run at ``mu ~ 0.6-1.5 h^-1``. The stiffness ratio is therefore of order
``10^3``. Explicit RK4 is stable only while ``h * kLa`` stays below about 2.8,
so the default ``h_max`` is **0.01 h** (``h * kLa = 1.33``) rather than
something that would look more convenient. The cost is a few thousand steps
over a 24 h horizon, which is cheap and keeps the answer inspectable by hand.

A candidate state that leaves the physical range is treated as a **rejected
step**, not an immediate failure and not a clipped value: the step is halved
and retried, up to a bounded number of consecutive rejections. A non-finite
value is an immediate failure, because no step size resolves it. A model that
genuinely diverges therefore still fails -- it just does not fail on the first
overshoot a smaller step would have avoided.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from schemas.state import State, StateError, validate_state

from .diagnostics import Diagnostic, DiagnosticCode, DiagnosticList, Severity


class FeedDomainError(ArithmeticError):
    """A right-hand side was evaluated outside the model's domain.

    Distinct from a failure of the model: it is what a trial Runge-Kutta stage
    can legitimately hit when the step was too long, and the solver responds by
    shortening the step. ``models.fed_batch.FeedError`` is re-raised as this so
    the solver can tell a domain excursion from a genuine defect.
    """

#: (t, y) -> dy/dt
RightHandSide = Callable[[float, tuple[float, ...]], tuple[float, ...]]

SOLVER_NAME = "runge-kutta-4(3) step-doubling"
SOLVER_VERSION = "1.0.0"


class SolverError(RuntimeError):
    """The integration could not be completed."""


@dataclass(frozen=True)
class SolverConfig:
    """Integration settings, recorded with every result."""

    rtol: float = 1.0e-6
    atol: float = 1.0e-9
    h_init: float = 1.0e-4
    """First trial step, in hours."""
    h_max: float = 1.0e-2
    """Largest step the controller may take, in hours.

    Chosen from the reported kLa: h_max * kLa = 1.33, inside the explicit RK4
    stability limit. See the module docstring.
    """
    h_min: float = 1.0e-9
    """Smallest step before the run is declared failed."""
    max_steps: int = 200_000
    safety: float = 0.9
    min_factor: float = 0.2
    max_factor: float = 5.0
    max_range_rejections: int = 60
    """Consecutive physical-range rejections before the run is declared failed."""

    def __post_init__(self) -> None:
        if self.rtol <= 0.0 or self.atol <= 0.0:
            raise SolverError("rtol and atol must be positive")
        if self.h_init <= 0.0 or self.h_max <= 0.0 or self.h_min <= 0.0:
            raise SolverError("step sizes must be positive")
        if self.h_min > self.h_init or self.h_init > self.h_max:
            raise SolverError(
                f"step sizes must satisfy h_min <= h_init <= h_max, got "
                f"{self.h_min:g}, {self.h_init:g}, {self.h_max:g}"
            )
        if self.max_steps < 1:
            raise SolverError("max_steps must be at least 1")

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "name": SOLVER_NAME,
            "version": SOLVER_VERSION,
            "rtol": self.rtol,
            "atol": self.atol,
            "h_init": self.h_init,
            "h_max": self.h_max,
            "h_min": self.h_min,
            "max_steps": self.max_steps,
            "max_range_rejections": self.max_range_rejections,
        }


@dataclass
class IntegrationResult:
    """A trajectory, or the reason there is not one."""

    times: list[float] = field(default_factory=list)
    states: list[State] = field(default_factory=list)
    diagnostics: DiagnosticList = field(default_factory=DiagnosticList)
    steps_taken: int = 0
    steps_rejected: int = 0
    smallest_step: float | None = None
    largest_step: float | None = None
    reached_time_h: float | None = None

    @property
    def ok(self) -> bool:
        return not self.diagnostics.error() and bool(self.states)

    @property
    def final_state(self) -> State | None:
        return self.states[-1] if self.states else None

    def solver_report(self) -> dict[str, float | int | None]:
        return {
            "steps_taken": self.steps_taken,
            "steps_rejected": self.steps_rejected,
            "smallest_step_h": self.smallest_step,
            "largest_step_h": self.largest_step,
            "reached_time_h": self.reached_time_h,
        }


def _rk4_step(rhs: RightHandSide, t: float, y: tuple[float, ...], h: float) -> tuple[float, ...]:
    """One classical fourth-order Runge-Kutta step."""
    k1 = rhs(t, y)
    k2 = rhs(t + 0.5 * h, tuple(yi + 0.5 * h * ki for yi, ki in zip(y, k1)))
    k3 = rhs(t + 0.5 * h, tuple(yi + 0.5 * h * ki for yi, ki in zip(y, k2)))
    k4 = rhs(t + h, tuple(yi + h * ki for yi, ki in zip(y, k3)))
    return tuple(
        yi + (h / 6.0) * (a + 2.0 * b + 2.0 * c + d)
        for yi, a, b, c, d in zip(y, k1, k2, k3, k4)
    )


def _error_norm(
    full: tuple[float, ...], half: tuple[float, ...], config: SolverConfig
) -> float:
    """Scaled difference between the full step and two half steps."""
    total = 0.0
    for f, hf in zip(full, half):
        scale = config.atol + config.rtol * max(abs(f), abs(hf))
        total += ((f - hf) / scale) ** 2
    return math.sqrt(total / len(full)) if full else 0.0


def integrate(
    rhs: RightHandSide,
    t0: float,
    y0: tuple[float, ...],
    t_end: float,
    *,
    config: SolverConfig | None = None,
    output_times: list[float] | None = None,
    validate: bool = True,
) -> IntegrationResult:
    """Integrate from ``t0`` to ``t_end``, reporting the whole trajectory.

    ``output_times`` are hit exactly: the solver steps to each one in turn, so a
    requested time point is never approximated by a neighbouring step. Without
    it, every accepted step is recorded.

    A failure -- a non-finite or physically invalid state, or a step that has to
    shrink below ``h_min`` -- returns the partial trajectory with an ERROR
    diagnostic and ``ok == False``. The caller decides what to do; the solver
    never invents a value.
    """
    config = config or SolverConfig()
    result = IntegrationResult()
    if t_end < t0:
        result.diagnostics.append(
            Diagnostic(
                code=DiagnosticCode.INPUT_INVALID,
                severity=Severity.ERROR,
                message=f"integration end time {t_end:g} h precedes the start {t0:g} h",
                where="solver",
            )
        )
        return result

    y = tuple(float(v) for v in y0)
    t = float(t0)
    result.times.append(t)
    result.states.append(State.from_vector(t, y))
    result.reached_time_h = t

    if validate:
        try:
            validate_state(result.states[0], t=t)
        except StateError as exc:
            result.diagnostics.append(
                Diagnostic(
                    code=DiagnosticCode.STATE_NEGATIVE,
                    severity=Severity.ERROR,
                    message=f"the initial state is not admissible: {exc}",
                    where="solver",
                )
            )
            return result

    targets = sorted(float(x) for x in (output_times or []))
    for target in targets:
        if not t0 <= target <= t_end:
            result.diagnostics.append(
                Diagnostic(
                    code=DiagnosticCode.INPUT_INVALID,
                    severity=Severity.ERROR,
                    message=(
                        f"requested output time {target:g} h lies outside the "
                        f"integration interval [{t0:g}, {t_end:g}] h"
                    ),
                    where="solver",
                )
            )
            return result

    target_index = 0
    h = min(config.h_init, config.h_max)
    range_rejections = 0

    def fail(code: DiagnosticCode, message: str, *, detail: dict | None = None,
             remediation: str = "") -> IntegrationResult:
        result.diagnostics.append(
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                message=message,
                where="solver",
                detail=detail or {},
                remediation=remediation,
            )
        )
        return result

    while t < t_end:
        if result.steps_taken >= config.max_steps:
            return fail(
                DiagnosticCode.SOLVER_FAILED,
                f"integration stopped after {result.steps_taken} steps at "
                f"t={t:g} h without reaching {t_end:g} h",
                detail={"config": config.to_dict()},
                remediation="Raise max_steps or loosen rtol/atol deliberately.",
            )

        limit = t_end
        while target_index < len(targets) and targets[target_index] <= t:
            target_index += 1
        if target_index < len(targets):
            limit = targets[target_index]
        h = min(h, limit - t, config.h_max)

        # Trial evaluations. An exception raised by the right-hand side on a
        # trial stage (a stage that walks outside the model's domain) is a
        # step that was too long, not a failure of the model: it is retried with
        # a smaller step. Nothing is substituted for the value that could not be
        # computed.
        try:
            full = _rk4_step(rhs, t, y, h)
            two_half = _rk4_step(
                rhs, t + 0.5 * h, _rk4_step(rhs, t, y, 0.5 * h), 0.5 * h
            )
            err = _error_norm(full, two_half, config)
        except (FeedDomainError, ArithmeticError, ValueError) as exc:
            range_rejections += 1
            result.steps_rejected += 1
            if range_rejections > config.max_range_rejections:
                return fail(
                    DiagnosticCode.SOLVER_FAILED,
                    f"the right-hand side could not be evaluated at t={t:g} h "
                    f"within {config.max_range_rejections} smaller steps: "
                    f"{type(exc).__name__}: {exc}",
                    detail={"t_h": t, "step_h": h},
                    remediation=(
                        "The step was not shortened far enough to stay inside the "
                        "model's domain. Check the inputs against the stated "
                        "ranges rather than loosening the solver."
                    ),
                )
            h = max(h * 0.5, config.h_min)
            if h <= config.h_min:
                return fail(
                    DiagnosticCode.SOLVER_FAILED,
                    f"the step at t={t:g} h would have to fall below h_min to "
                    f"stay inside the model's domain: {exc}",
                    detail={"t_h": t},
                )
            continue

        if not math.isfinite(err):
            return fail(
                DiagnosticCode.STATE_NON_FINITE,
                f"the right-hand side produced a non-finite value at "
                f"t={t:g} h; the integration has failed",
                detail={"state": list(y)},
                remediation="No trajectory is returned for a failed step.",
            )

        if err > 1.0:
            result.steps_rejected += 1
            factor = max(config.min_factor, config.safety * err ** -0.25)
            new_h = h * factor
            if new_h < config.h_min:
                return fail(
                    DiagnosticCode.SOLVER_FAILED,
                    f"the step at t={t:g} h would have to shrink below "
                    f"h_min={config.h_min:g} h to meet rtol={config.rtol:g}; "
                    f"the trajectory is not being continued",
                    detail={"local_error": err, "step_h": h},
                    remediation=(
                        "Loosen rtol/atol deliberately, or check whether the model "
                        "is being driven outside its domain."
                    ),
                )
            h = new_h
            continue

        # Candidate state, checked before anything is committed.
        t_next = t + h
        if abs((t + h) - limit) < 1e-15:
            t_next = limit
        candidate = State.from_vector(t_next, full)

        if validate:
            try:
                validate_state(candidate, t=t_next)
            except StateError as exc:
                if "non-finite" in str(exc):
                    return fail(
                        DiagnosticCode.STATE_NON_FINITE,
                        str(exc),
                        detail={"t_h": t_next, "state": candidate.to_dict()},
                        remediation=(
                            "No trajectory is returned for a failed step; no value "
                            "is substituted."
                        ),
                    )
                range_rejections += 1
                result.steps_rejected += 1
                if range_rejections > config.max_range_rejections:
                    return fail(
                        DiagnosticCode.SOLVER_FAILED,
                        f"the state left the physically admissible range at "
                        f"t={t_next:g} h and did not recover within "
                        f"{config.max_range_rejections} smaller steps: {exc}",
                        detail={"t_h": t_next, "state": candidate.to_dict()},
                        remediation=(
                            "The state is reported as invalid rather than clipped. "
                            "If the model is being driven outside its stated "
                            "domain, that is the finding."
                        ),
                    )
                h = max(h * 0.5, config.h_min)
                if h <= config.h_min:
                    return fail(
                        DiagnosticCode.SOLVER_FAILED,
                        f"the step at t={t:g} h would have to fall below h_min to "
                        f"keep the state admissible: {exc}",
                        detail={"t_h": t},
                    )
                continue
        range_rejections = 0

        # Committed: nothing above this line has changed t or y.
        t, y = t_next, full
        result.steps_taken += 1
        result.smallest_step = h if result.smallest_step is None else min(result.smallest_step, h)
        result.largest_step = h if result.largest_step is None else max(result.largest_step, h)
        result.reached_time_h = t
        result.times.append(t)
        result.states.append(candidate)

        factor = (
            config.max_factor
            if err == 0.0
            else min(config.max_factor, config.safety * err ** -0.2)
        )
        h = min(config.h_max, h * factor)

    return result