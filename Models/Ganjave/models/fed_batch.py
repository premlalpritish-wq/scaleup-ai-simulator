"""Fed-batch balances: eq. (12)-(16).

Transcribed as printed:

    eq. (12)  dX/dt    = (mu - F/V)*X
    eq. (13)  dS1/dt   = (S10 - S1)*F/V - (mu1/Y11)*X
    eq. (14)  dS2/dt   = (S20 - S2)*F/V - (mu1/Y12 + mu2/Y22)*X
    eq. (15)  d(DO)/dt = kLa*(100 - DO) - (DO)*F/V - (100/C*)*(mu1/Yo1 + mu2/Yo2)*X
    eq. (16)  dV/dt    = F

What fed-batch adds to the batch balances, and why each term is there:

* **Dilution.** Feed adds volume, so the concentration derivative gains the
  feed-in term ``(S_feed - S)*F/V``. For biomass the same dilution appears as
  ``-F/V*X``: a positive feed always *removes* concentration, whatever the
  growth term is doing. The paper applies the dilution to biomass and dissolved
  oxygen but **not** to the substrate concentrations in a dilution-only form --
  the substrate terms carry the feed input and the consumption together.
* **Oxygen dilution.** Eq. (15) adds ``-(DO)*F/V``. Note it dilutes the
  *reading*, not the transfer coefficient: the ``kLa*(100 - DO)`` term is
  unchanged from batch.
* **Volume.** ``dV/dt = F``, so a constant feed rate raises the volume
  linearly. ``F`` and ``V`` must be in the same volume unit for ``F/V`` to be
  a rate; the API takes both in litres and converts at the boundary.

The feed concentrations ``S10`` and ``S20`` are the *feed* concentrations in
g/L, not the culture values at t=0 (TN-05). The paper prints the recipes in
percent weight/volume and eq. (13)/(14) require g/L.

Fed-batch is kept separate from batch rather than folded in with ``F = 0``.
``models.batch`` and this module can therefore disagree, and the tests assert
that they do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from schemas.parameters import ParameterSet
from schemas.state import State

from .batch import oxygen_consumption_term, oxygen_transfer_term
from .kinetics import growth_terms


class FeedError(ValueError):
    """The feed program is not usable."""


class FeedDomainError(ArithmeticError):
    """A fed-batch balance was evaluated outside the model's domain.

    Raised when the culture volume is not positive, which makes ``F/V``
    undefined. During integration this normally means a trial step was too long
    rather than that the feed is wrong; the solver shortens the step and
    retries. Outside integration it means the caller's state is invalid.
    """


@dataclass(frozen=True)
class FeedProgram:
    """Feed concentration and volumetric flow for a fed-batch run.

    ``S10_g_per_L`` and ``S20_g_per_L`` are the feed concentrations as
    eq. (13)/(14) require them, in g/L. ``flow_L_per_h`` is the volumetric feed
    rate; the paper reports it in mL/h and the conversion is explicit at the
    boundary.
    """

    S10_g_per_L: float
    S20_g_per_L: float
    flow_L_per_h: float
    start_time_h: float = 0.0
    """Feeding begins at this time. The paper starts feeding at 6 h (p. 3)."""

    def __post_init__(self) -> None:
        if self.S10_g_per_L < 0.0 or self.S20_g_per_L < 0.0:
            raise FeedError(
                f"feed concentrations must be non-negative, got "
                f"S10={self.S10_g_per_L!r} g/L, S20={self.S20_g_per_L!r} g/L"
            )
        if self.flow_L_per_h < 0.0:
            raise FeedError(
                f"feed flow rate must be non-negative, got {self.flow_L_per_h!r} L/h"
            )
        if self.start_time_h < 0.0:
            raise FeedError(
                f"feed start time must be non-negative, got {self.start_time_h!r} h"
            )

    def is_feeding(self, t: float) -> bool:
        """Whether the pump is running at time ``t``.

        A zero flow rate is a stopped pump, not a missing one: the volume
        balance still holds and the dilution terms vanish.
        """
        return t >= self.start_time_h and self.flow_L_per_h > 0.0

    def flow_at(self, t: float) -> float:
        """Volumetric flow at time ``t``, in L/h."""
        return self.flow_L_per_h if t >= self.start_time_h else 0.0

    @classmethod
    def from_recipe(
        cls,
        glycerol_percent_wv: float,
        yeast_extract_percent_wv: float,
        flow_mL_per_h: float,
        *,
        start_time_h: float = 0.0,
    ) -> "FeedProgram":
        """Build from the paper's Table 1 units: % w/v and mL/h.

        The two conversions are explicit and tested: 1 % w/v = 10 g/L, and
        1 mL/h = 1e-3 L/h. This is the only place a percent recipe enters the
        model.
        """
        from schemas.units import percent_wv_to_g_per_l

        return cls(
            S10_g_per_L=percent_wv_to_g_per_l(glycerol_percent_wv),
            S20_g_per_L=percent_wv_to_g_per_l(yeast_extract_percent_wv),
            flow_L_per_h=flow_mL_per_h * 1.0e-3,
            start_time_h=start_time_h,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "S10_g_per_L": self.S10_g_per_L,
            "S20_g_per_L": self.S20_g_per_L,
            "flow_L_per_h": self.flow_L_per_h,
            "start_time_h": self.start_time_h,
        }


def dilution_rate(flow_L_per_h: float, volume_L: float) -> float:
    """``F/V`` in h^-1.

    Eq. (12), (13), (14) and (15) all carry this factor. It is exposed because
    the acceptance tests check the dilution contribution directly, and because
    a caller computing an expected value by hand needs the same expression.
    """
    if volume_L <= 0.0:
        raise FeedDomainError(
            f"dilution rate F/V needs a positive volume, got V={volume_L!r} L"
        )
    return flow_L_per_h / volume_L


def dX_dt(state: State, flow_L_per_h: float, parameters: ParameterSet) -> float:
    """Eq. (12): ``dX/dt = (mu - F/V)*X``.

    The dilution contribution ``-(F/V)*X`` is non-positive whenever the feed is
    non-negative, which is what makes it a dilution.
    """
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    return (terms["mu"] - dilution_rate(flow_L_per_h, state.V)) * state.X


def dS1_dt(state: State, feed: FeedProgram, flow_L_per_h: float,
           parameters: ParameterSet) -> float:
    """Eq. (13): ``dS1/dt = (S10 - S1)*F/V - (mu1/Y11)*X``."""
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    feed_in = (feed.S10_g_per_L - state.S1) * dilution_rate(flow_L_per_h, state.V)
    consumption = -(terms["mu1"] / parameters.value("Y11")) * state.X
    return feed_in + consumption


def dS2_dt(state: State, feed: FeedProgram, flow_L_per_h: float,
           parameters: ParameterSet) -> float:
    """Eq. (14): ``dS2/dt = (S20 - S2)*F/V - (mu1/Y12 + mu2/Y22)*X``."""
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    feed_in = (feed.S20_g_per_L - state.S2) * dilution_rate(flow_L_per_h, state.V)
    uptake = terms["mu1"] / parameters.value("Y12") + terms["mu2"] / parameters.value("Y22")
    return feed_in - uptake * state.X


def dDO_dt(state: State, feed: FeedProgram, flow_L_per_h: float,
           parameters: ParameterSet) -> float:
    """Eq. (15): transfer, minus dilution of the reading, minus consumption.

        kLa*(100 - DO) - (DO)*F/V - (100/C*)*(mu1/Yo1 + mu2/Yo2)*X

    The printed factor is a quotient, ``100/C*``, as eq. (11); see TN-04.
    """
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    dilution = -state.DO * dilution_rate(flow_L_per_h, state.V)
    return (
        oxygen_transfer_term(state.DO, parameters)
        + dilution
        - oxygen_consumption_term(terms["mu1"], terms["mu2"], state.X, parameters)
    )


def dV_dt(feed: FeedProgram, flow_L_per_h: float) -> float:
    """Eq. (16): ``dV/dt = F``."""
    return flow_L_per_h


def fed_batch_derivative(
    state: State, feed: FeedProgram, parameters: ParameterSet, *, t: float
) -> tuple[float, ...]:
    """The fed-batch right-hand side, in the state vector's order.

    Order matches :meth:`State.as_vector`: ``X, S1, S2, DO, e1, e2, V``.
    ``feed.flow_at(t)`` decides whether the pump is running, so the batch
    interval before feeding starts is integrated with zero feed.
    """
    flow = feed.flow_at(t)
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    return (
        (terms["mu"] - dilution_rate(flow, state.V)) * state.X,
        (feed.S10_g_per_L - state.S1) * dilution_rate(flow, state.V)
        - (terms["mu1"] / parameters.value("Y11")) * state.X,
        (feed.S20_g_per_L - state.S2) * dilution_rate(flow, state.V)
        - (terms["mu1"] / parameters.value("Y12")
           + terms["mu2"] / parameters.value("Y22")) * state.X,
        oxygen_transfer_term(state.DO, parameters)
        - state.DO * dilution_rate(flow, state.V)
        - oxygen_consumption_term(terms["mu1"], terms["mu2"], state.X, parameters),
        terms["de1"],
        terms["de2"],
        dV_dt(feed, flow),
    )


def fed_batch_terms(state: State, parameters: ParameterSet) -> Mapping[str, float]:
    """The kinetic quantities eq. (12)-(16) share."""
    return growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)