"""The complete simulation model printed in Lin et al. (2001), Appendix.

The paper's appendix is titled "THE COMPLETE SIMULATION MODEL" and prints, in
full, the seven ordinary differential equations (printed p. 356) and the chain
of subsidiary-variable calculations (printed pp. 356-357) that make up the
model of Xu et al. (1999) as extended by equations (6) and (7). That is what
this module implements, and it is the reason this package exists: the paper
supplies a closed model, so a faithful standalone implementation is possible.

Every function here is the printed equation, in the printed order. Nothing is
re-ordered, no branch is dropped, and no constant is filled in: the five
constants the Appendix and Table I leave unvalued (`cS`, `cO`, `kLa`,
`DOT_star`, `H`) are arguments a caller must supply for a run.

**On the printed page.** The differential system is on printed p. 356 and the
second half of the subsidiary chain is on p. 357. Equation numbers below are the
paper's own.

**On equation (2).** The appendix prints the biomass balance in dilution form;
the extracted text renders its symbols in the order ``mD``. The arithmetic is
unambiguous because the notation defines F (feed flow rate, L h-1) and V
(fermenter volume, L), so the dilution rate it uses is F/V, which is what
`derivatives` computes. That one symbol is therefore not quoted as a fidelity
check, because the extraction garbles it; the values it implies are asserted
numerically instead.

**What is not here.** This module does not couple to any other model, does not
declare ports, and does not register anything with the composition layer. It is
a standalone executable model of one paper's own experiment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Callable, Mapping, Sequence

from . import parameters as params

#: Printed page carrying the differential equation system (equations 1-7).
DIFFERENTIAL_SYSTEM_PAGE = 356
#: Printed page carrying the second half of the subsidiary chain.
SUBSIDIARY_CHAIN_PAGE = 357
#: Printed page carrying the pulse method, equation (1).
PULSE_METHOD_PAGE = 351


class ModelError(ValueError):
    """Raised when the model is asked for something it cannot do."""


class MissingRunInput(ModelError):
    """Raised when a run omits a constant the paper does not value."""


#: Every constant the Appendix requires and the paper does not value.
REQUIRED_RUN_INPUTS: tuple[str, ...] = ("cS", "cO", "kLa", "DOT_star", "H")


@dataclass(frozen=True)
class State:
    """One point of the model's state vector, in the paper's own units.

    V [L], X [g/L], S [g/L], DOT [%], A [g/L], rS [-], rO [-].
    """

    V: float
    X: float
    S: float
    DOT: float
    A: float
    rS: float
    rO: float

    def to_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class SimulationParameters:
    """One Table I culture plus the five unvalued constants, for one run."""

    #: Which Table I culture column this run uses.
    culture: str
    # Table I
    KS: float
    KA: float
    qm: float
    qSmax: float
    qOmax: float
    qAc_max: float
    YXS_ox: float
    CS: float
    CA: float
    CX: float
    YOS: float
    YXS_of: float
    YAS: float
    YOA: float
    YXA: float
    Si: float
    X0: float
    S0: float
    V0: float
    # The four protocol-dependent rows the Appendix's equations (6) and (7) use.
    YES_X: float
    YEO_X: float
    qESd: float
    qEOd: float
    # Required run inputs the paper does not value.
    cS: float
    cO: float
    kLa: float
    DOT_star: float
    H: float

    @classmethod
    def from_culture(
        cls,
        culture: str,
        *,
        cS: float,
        cO: float,
        kLa: float,
        DOT_star: float,
        H: float,
        variant: str = "growth_dependent",
    ) -> "SimulationParameters":
        """Build the parameter set Table I prints for `culture`.

        `variant` selects which printed value the four protocol-dependent rows
        take: ``"growth_dependent"`` uses Table I's footnote-d values, which are
        the ones the Appendix's equations (6) and (7) describe;
        ``"constant_capacity"`` uses the footnote-c value 0, the paper's own "no
        change in qOcap and qScap is considered".
        """
        if culture not in params.CULTURES:
            raise ModelError(
                f"unknown culture {culture!r}; Table I prints "
                f"{sorted(params.CULTURES)}"
            )
        if variant not in ("growth_dependent", "constant_capacity"):
            raise ModelError(
                f"unknown variant {variant!r}; expected 'growth_dependent' or "
                f"'constant_capacity'"
            )
        get = params.parameter

        def val(name: str) -> float:
            value = get(name).value_for(culture)
            if value is None:
                raise ModelError(f"Table I prints no value for {name} at {culture}")
            return float(value)

        growth = {v.name: v.value for v in params.PROTOCOL_VARIANTS}
        if variant == "growth_dependent":
            yes_x, yeo_x = growth["YES/X"], growth["YEO/X"]
            qesd, qeod = growth["qESd"], growth["qEOd"]
        else:
            yes_x, yeo_x = 0.0, 0.0
            qesd = params.NO_CHANGE_VALUES["qESd"]
            qeod = params.NO_CHANGE_VALUES["qEOd"]

        for name, value in (
            ("cS", cS), ("cO", cO), ("kLa", kLa),
            ("DOT_star", DOT_star), ("H", H),
        ):
            if value is None:
                raise MissingRunInput(
                    f"{name} is required for a run: "
                    f"{params.UNVALUED_RUN_INPUTS[name]}"
                )

        return cls(
            culture=culture,
            KS=val("KS"), KA=val("KA"), qm=val("qm"),
            qSmax=val("qSmax"), qOmax=val("qOmax"), qAc_max=val("qAc,max"),
            YXS_ox=val("YX/S,ox"), CS=val("CS"), CA=val("CA"), CX=val("CX"),
            YOS=val("YO/S"), YXS_of=val("YX/S,of"), YAS=val("YA/S"),
            YOA=val("YO/A"), YXA=val("YX/A"), Si=val("Si"), X0=val("X0"),
            S0=val("S0"), V0=val("V0"),
            YES_X=yes_x, YEO_X=yeo_x, qESd=qesd, qEOd=qeod,
            cS=cS, cO=cO, kLa=kLa, DOT_star=DOT_star, H=H,
        )

    # -- derived initial values, printed in the Appendix ---------------------

    @property
    def mu_max(self) -> float:
        """``mu_max = (qSmax - qm) * YX/S,ox`` (printed p. 356)."""
        return (self.qSmax - self.qm) * self.YXS_ox

    @property
    def rS0(self) -> float:
        """``rS0 = cS * mu_max / (qESd + mu_max)`` (printed p. 356)."""
        return self.cS * self.mu_max / (self.qESd + self.mu_max)

    @property
    def rO0(self) -> float:
        """``rO0 = cO * mu_max / (qEOd + mu_max)`` (printed p. 356)."""
        return self.cO * self.mu_max / (self.qEOd + self.mu_max)

    def initial_state(self, *, DOT: float = 0.0, A: float = 0.0) -> State:
        """The state Table I's initial values define, with rS0 and rO0."""
        return State(
            V=self.V0, X=self.X0, S=self.S0, DOT=DOT, A=A,
            rS=self.rS0, rO=self.rO0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class Subsidiary:
    """The Appendix's subsidiary variables at one state, in printed units."""

    qScap: float
    qOcap: float
    qS: float
    qSox: float
    qmr: float
    qSoxan: float
    qSoxen: float
    qOs: float
    qSof: float
    qAc: float
    qSofan: float
    qSofen: float
    qAcan: float
    qAcen: float
    qAp: float
    qO: float
    mu: float
    #: Which of the Appendix's two correction branches fired, for transparency.
    oxygen_capacity_clamped: bool
    maintenance_reduced_below_qm: bool

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def subsidiary(state: State, p: SimulationParameters) -> Subsidiary:
    """The printed subsidiary chain, pp. 356-357, evaluated at `state`.

    The order is the paper's, and the two correction branches are the paper's
    own: the oxygen-capacity clamp ("If the calculated value of qOs is larger
    then qOcap we set qOs ... and correct the values of qSoxan, qSoxen, qSox,
    and qmr") and the maintenance floor ("If now qSox < qmr then we must set
    qmr ... and therefore we obtain qmr = qSox = qSoxen and qSoxan ... 0").
    """
    qScap = p.qSmax * state.rS / p.rS0
    qOcap = p.qOmax * state.rO / p.rO0
    qS = qScap * state.S / (state.S + p.KS)
    qSox = qS
    qmr = min(p.qm, qSox)
    qSoxan = (qSox - qmr) * p.YXS_ox * p.CS
    qSoxen = qSox - qSoxan
    qOs = qSoxen * p.YOS

    oxygen_clamped = False
    maintenance_reduced = False

    if qOs > qOcap:
        oxygen_clamped = True
        qOs = qOcap
        qSoxen = qOcap / p.YOS
        qSox = (qmr * p.CS * p.YXS_ox - qSoxen) / (p.CS * p.YXS_ox - 1.0)
        qSoxan = qSox - qSoxen

    if qSox < qmr:
        maintenance_reduced = True
        qmr = qSox
        qSoxen = qSox
        qSoxan = 0.0

    qSof = qS - qSox
    qAc = p.qAc_max * state.A / (state.A + p.KA)
    qSofan = qSof * p.YXS_of * p.CS
    qSofen = qSof - qSofan
    qAcan = qAc * p.YXA * p.CA
    qAcen = qAc - qAcan

    if qAcen > qOcap - qOs / p.YOA:
        qAcen = qOcap - qOs / p.YOA
        qAc = qAcen / (1.0 - p.YXA * p.CA)
        qAcan = qAc - qAcen

    qAp = qSofen * p.YAS
    qO = qOs + qAcen * p.YOA
    mu = (
        (qSox - p.qm) * p.YXS_ox
        + qSof * p.YXS_of
        + qAc * p.YXA
    )
    return Subsidiary(
        qScap=qScap, qOcap=qOcap, qS=qS, qSox=qSox, qmr=qmr, qSoxan=qSoxan,
        qSoxen=qSoxen, qOs=qOs, qSof=qSof, qAc=qAc, qSofan=qSofan,
        qSofen=qSofen, qAcan=qAcan, qAcen=qAcen, qAp=qAp, qO=qO, mu=mu,
        oxygen_capacity_clamped=oxygen_clamped,
        maintenance_reduced_below_qm=maintenance_reduced,
    )


#: A feed protocol: volumetric feed rate F [L/h] as a function of time [h].
FeedProtocol = Callable[[float], float]


def feed_exponential(
    initial_rate_L_per_h: float, rate_constant_per_h: float
) -> FeedProtocol:
    """``F(t) = F0 * exp(k t)``, the paper's protocol-1 feed (printed p. 349)."""
    def protocol(t: float) -> float:
        return initial_rate_L_per_h * math.exp(rate_constant_per_h * t)
    return protocol


def feed_constant(rate_L_per_h: float) -> FeedProtocol:
    """``F(t) = F``, the paper's protocol-2 feed (printed p. 349)."""
    def protocol(t: float) -> float:
        return rate_L_per_h
    return protocol


def derivatives(
    state: State, p: SimulationParameters, feed: FeedProtocol, t: float
) -> State:
    """The seven printed differential equations, at ``(state, t)``.

    (1) V. = F;  (2) X. = (mu - F/V) X;  (3) S. = -(F/V)(S - Si) - qS X;
    (4) DOT. = kLa(DOT* - DOT) - qO X H;  (5) A. = -(F/V) A + (qAp - qAc) X;
    (6) rS. = YES/X mu - rS(qESd + mu);  (7) rO. = YEO/X mu - rO(qEOd + mu).
    """
    s = subsidiary(state, p)
    F = feed(t)
    D = F / state.V
    return State(
        V=F,
        X=(s.mu - D) * state.X,
        S=-D * (state.S - p.Si) - s.qS * state.X,
        DOT=p.kLa * (p.DOT_star - state.DOT) - s.qO * state.X * p.H,
        A=-D * state.A + (s.qAp - s.qAc) * state.X,
        rS=p.YES_X * s.mu - state.rS * (p.qESd + s.mu),
        rO=p.YEO_X * s.mu - state.rO * (p.qEOd + s.mu),
    )


def _step(state: State, deriv: State, h: float) -> State:
    return State(**{
        name: getattr(state, name) + h * getattr(deriv, name)
        for name in state.to_dict()
    })


@dataclass(frozen=True)
class SimulationSample:
    t: float
    state: State
    subsidiary: Subsidiary

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "state": self.state.to_dict(),
            "subsidiary": self.subsidiary.to_dict(),
        }


@dataclass(frozen=True)
class SimulationResult:
    """A trajectory: one sample per step, plus the parameters behind it."""

    parameters: SimulationParameters
    feed: FeedProtocol
    samples: tuple[SimulationSample, ...]

    @property
    def times(self) -> tuple[float, ...]:
        return tuple(s.t for s in self.samples)

    def final(self) -> SimulationSample:
        if not self.samples:
            raise ModelError("the simulation produced no samples")
        return self.samples[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": self.parameters.to_dict(),
            "times": list(self.times),
            "samples": [s.to_dict() for s in self.samples],
        }


def simulate(
    p: SimulationParameters,
    feed: FeedProtocol,
    *,
    t_end: float,
    dt: float = 0.01,
    initial: State | None = None,
    record_every: int = 1,
) -> SimulationResult:
    """Integrate the printed differential system with classical RK4.

    The integration scheme is not the paper's (it prints equations, not a
    solver), so the result is a reproducible evaluation of the printed model
    rather than the authors' own curves. `dt`, the scheme and `record_every` are
    declared here so a run is reproducible. Nothing is fitted.
    """
    if t_end <= 0:
        raise ModelError("t_end must be positive")
    if dt <= 0:
        raise ModelError("dt must be positive")
    if record_every < 1:
        raise ModelError("record_every must be at least 1")

    state = initial if initial is not None else p.initial_state()
    steps = int(round(t_end / dt))
    samples: list[SimulationSample] = [
        SimulationSample(t=0.0, state=state, subsidiary=subsidiary(state, p))
    ]
    t = 0.0
    for i in range(steps):
        k1 = derivatives(state, p, feed, t)
        k2 = derivatives(_step(state, k1, dt / 2), p, feed, t + dt / 2)
        k3 = derivatives(_step(state, k2, dt / 2), p, feed, t + dt / 2)
        k4 = derivatives(_step(state, k3, dt), p, feed, t + dt)
        state = State(**{
            name: getattr(state, name)
            + (dt / 6.0) * (
                getattr(k1, name)
                + 2 * getattr(k2, name)
                + 2 * getattr(k3, name)
                + getattr(k4, name)
            )
            for name in state.to_dict()
        })
        t = (i + 1) * dt
        if i % record_every == 0 or i == steps - 1:
            samples.append(
                SimulationSample(t=t, state=state, subsidiary=subsidiary(state, p))
            )
    return SimulationResult(parameters=p, feed=feed, samples=tuple(samples))


def qScap_from_pulse(
    *,
    delta_S_g: float,
    integral_F_Si_g: float,
    V_L: float,
    X_g_per_L: float,
    tP_h: float,
    tR_h: float,
) -> float:
    """Equation (1), printed p. 351: the pulse-based glucose uptake capacity.

    ``qScap = (delta_S + INTEGRAL(F*Si)) / (V X (tR - tP))``.

    **Unit note.** The printed denominator ``V X (tR - tP)`` is a biomass mass
    times time, so the numerator must be a glucose *mass* for the result to be
    g g-1 h-1. The paper describes the pulse as a concentration ("pulses of 0.5
    to 1.0 g L-1 glucose"), so a caller holding a concentration multiplies by V
    before calling. The model does not perform that multiplication itself,
    because the paper does not print it.
    """
    if tR_h <= tP_h:
        raise ModelError("tR must be later than tP")
    if V_L <= 0 or X_g_per_L <= 0:
        raise ModelError("V and X must be positive")
    return (delta_S_g + integral_F_Si_g) / (V_L * X_g_per_L * (tR_h - tP_h))

