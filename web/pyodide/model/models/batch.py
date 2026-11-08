"""Batch-phase balances: eq. (8)-(11).

Transcribed as printed:

    eq. (8)   dX/dt   = mu*X
    eq. (9)   dS1/dt  = -(mu1/Y11)*X
    eq. (10)  dS2/dt  = -(mu1/Y12 + mu2/Y22)*X
    eq. (11)  d(DO)/dt = kLa*(100 - DO) - (100/C*)*(mu1/Yo1 + mu2/Yo2)*X

Points that are easy to get wrong and are therefore called out:

* **Each substrate is consumed through both combinations where the paper says
  so.** `S1` is consumed only through combination 1 (eq. 9). `S2` is consumed
  through *both*: ``mu1/Y12`` (combination 1, which needs S1 and S2 together)
  and ``mu2/Y22`` (combination 2). Omitting the second term would make the
  nitrogen-rich substrate appear to be consumed only when glycerol is present.
* **Oxygen consumption sums both combinations too**, with their own yields
  ``Yo1`` and ``Yo2``.
* **Batch mode has no dilution and no volume term.** Those appear only in
  eq. (12)-(16); `models.fed_batch` keeps them separate rather than folding
  ``F = 0`` into one ambiguous expression.
* **The printed factor is ``100/C*`` -- a quotient, not a product.** The
  rendered page (printed p. 4) shows ``100`` above a fraction bar with ``C*``
  below. The PDF text layer drops the bar, so a text-based reading of the
  equation misreads it as ``100*C*``, which is not dimensionally addable to
  the transfer term beside it. That transcription error was made here and
  corrected; see TN-04 in `models.kinetics` and the unit algebra in
  `models.dimensions`.
"""

from __future__ import annotations

from typing import Mapping

from schemas.parameters import ParameterSet
from schemas.state import State

from .kinetics import growth_terms


def dX_dt(state: State, parameters: ParameterSet) -> float:
    """Eq. (8): ``dX/dt = mu*X``."""
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    return terms["mu"] * state.X


def dS1_dt(state: State, parameters: ParameterSet) -> float:
    """Eq. (9): ``dS1/dt = -(mu1/Y11)*X``.

    Glycerol is consumed only through combination 1, which is the only
    combination that lists S1 in its stoichiometry (eq. 1).
    """
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    return -(terms["mu1"] / parameters.value("Y11")) * state.X


def dS2_dt(state: State, parameters: ParameterSet) -> float:
    """Eq. (10): ``dS2/dt = -(mu1/Y12 + mu2/Y22)*X``.

    Both combinations consume the complex substrate, each with its own yield.
    """
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    uptake = terms["mu1"] / parameters.value("Y12") + terms["mu2"] / parameters.value("Y22")
    return -uptake * state.X


def oxygen_transfer_term(DO: float, parameters: ParameterSet) -> float:
    """The transfer half of eq. (11)/(15): ``kLa*(100 - DO)`` in ``%/h``.

    Positive while the medium is below the probe's saturation reading.
    """
    return parameters.value("kLa") * (100.0 - DO)


def oxygen_consumption_term(mu1: float, mu2: float, X: float,
                            parameters: ParameterSet) -> float:
    """The consumption half of eq. (11)/(15), as the paper prints it.

        (100 / C*) * (mu1/Yo1 + mu2/Yo2) * X

    The printed factor is a **quotient**, not a product: the rendered page
    shows ``100`` above a fraction bar with ``C*`` below it. Verified against a
    rendering of printed page 4, because the PDF text layer drops the bar and
    makes the factor read as ``100*C*`` -- which was the transcription error
    recorded in TN-04 and corrected there.

    Dimensional check (`models.dimensions`): ``mu_k/Yok`` converts a biomass
    specific rate into an oxygen specific rate, so
    ``(mu1/Yo1 + mu2/Yo2)*X`` is an oxygen uptake rate in ``M L^-3 T^-1``;
    dividing by ``C*`` and scaling by the printed 100 gives ``%/h``, which is
    the dimension of the transfer term beside it and of ``d(DO)/dt``. Multiplying
    by ``C*`` instead would not.

    The two combinations are summed with their own oxygen yields.
    """
    c_star = parameters.value("C_star")
    if c_star <= 0.0:
        raise ValueError(
            f"C* must be strictly positive to convert an oxygen uptake rate "
            f"into a dissolved-oxygen percentage, got {c_star!r} g/L"
        )
    uptake = mu1 / parameters.value("Yo1") + mu2 / parameters.value("Yo2")
    return (100.0 / c_star) * uptake * X


def dDO_dt(state: State, parameters: ParameterSet) -> float:
    """Eq. (11): ``kLa*(100 - DO) - (100/C*)*(mu1/Yo1 + mu2/Yo2)*X``."""
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    return oxygen_transfer_term(state.DO, parameters) - oxygen_consumption_term(
        terms["mu1"], terms["mu2"], state.X, parameters
    )


def batch_derivative(state: State, parameters: ParameterSet) -> tuple[float, ...]:
    """The batch right-hand side, in the state vector's order.

    Order matches :meth:`State.as_vector`: ``X, S1, S2, DO, e1, e2, V``.
    The volume derivative is exactly zero in batch mode -- there is no feed --
    which is asserted by the tests rather than assumed.
    """
    terms = growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)
    return (
        terms["mu"] * state.X,
        -(terms["mu1"] / parameters.value("Y11")) * state.X,
        -(terms["mu1"] / parameters.value("Y12")
          + terms["mu2"] / parameters.value("Y22")) * state.X,
        oxygen_transfer_term(state.DO, parameters)
        - oxygen_consumption_term(terms["mu1"], terms["mu2"], state.X, parameters),
        terms["de1"],
        terms["de2"],
        0.0,
    )


def batch_terms(state: State, parameters: ParameterSet) -> Mapping[str, float]:
    """Every quantity eq. (8)-(11) needs, computed once."""
    return growth_terms(state.S1, state.S2, state.DO, state.e1, state.e2, parameters)