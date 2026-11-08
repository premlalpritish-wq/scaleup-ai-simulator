"""Cybernetic growth kinetics: eq. (1)-(7).

Every function here is a direct transcription of one printed equation. The
paper's own symbols are kept in the docstrings so a reader can check the code
against the page, and nothing is rearranged, substituted or "improved".

Transcription notes, all recorded in :data:`TRANSCRIPTION_NOTES`:

**TN-01 -- eq. (1)/(2) are stoichiometries, not balances.** ``X - S1/Y11 -
S2/Y12 - DO/Yo1 = 0`` defines the yields used by the growth model. It is *not*
integrated: integrating it would assert a conserved quantity the paper never
proposes, and it mixes an oxygen *percentage* with concentrations. The
stoichiometric form is exposed by :func:`stoichiometric_residual_1` /
:func:`stoichiometric_residual_2` so the relation is checkable, and the
balances in `models.batch` are what the model actually integrates.

**TN-02 -- the enzyme state is a normalised fraction.** Eq. (5) multiplies
``mum_k`` by ``(e_k/e_mk)`` and eq. (7) differentiates that ratio directly, so
the state is the fraction ``e_k/e_mk``; ``e_mk`` is never needed as a number.
Table 2 prints the second initial ratio as "e20/em1", which cannot be right
(the denominator of combination 2 must be ``em2``); it is read as ``e20/em2``
and the print is preserved in the parameter's quote.

**TN-03 -- dissolved oxygen is a percentage.** ``Ko,1``/``Ko,2`` are percentages
and the response functions use ``DO/(Ko,k + DO)``. No concentration appears.
"""

from __future__ import annotations

from typing import Mapping

from schemas.parameters import ParameterSet
from schemas.provenance import SourceRef, TranscriptionNote

#: The two growth combinations, in the paper's own words (p. 4):
#: "(1) S1, S2, and dissolved oxygen (DO), and (2) S2 and DO".
COMBINATIONS = ("1", "2")

_PARAM_SOURCE = SourceRef(
    section="3.2 Model formulation and parameter estimation",
    locator="Table 2",
    printed_page=4,
)
_EQ_SOURCE = SourceRef(
    section="3.2 Model formulation and parameter estimation",
    locator="eq. (1)-(16)",
    printed_page=4,
)
_NOTATION_SOURCE = SourceRef(section="Notations", locator="notation table", printed_page=2)

TRANSCRIPTION_NOTES: tuple[TranscriptionNote, ...] = (
    TranscriptionNote(
        note_id="TN-01",
        statement=(
            "Eq. (1) and (2) are printed as equations equal to zero, which reads "
            "like a mass balance. They are the stoichiometries of the two "
            "substrate combinations and define the yield coefficients."
        ),
        decision=(
            "Implemented as a checkable residual (stoichiometric_residual_1/2), "
            "not as an integrated equation. The integrated balances are eq. "
            "(8)-(16) in models.batch and models.fed_batch."
        ),
        affected_equations=("eq. (1)", "eq. (2)"),
        source=_EQ_SOURCE,
    ),
    TranscriptionNote(
        note_id="TN-02",
        statement=(
            "Table 2 prints the initial enzyme ratio for combination 2 as "
            "'e20/em1'. The denominator of combination 2 must be e_m2; e_m1 is "
            "the maximum of combination 1."
        ),
        decision=(
            "Read as e2(0)/e_m2 = 0.874. The printed string is preserved in the "
            "parameter's source quote so the reading is auditable."
        ),
        affected_equations=("eq. (5)", "eq. (7)", "Table 2"),
        source=_PARAM_SOURCE,
        unresolved=True,
        review_question=(
            "Confirm with the authors that the second initial enzyme ratio is "
            "e2(0)/e_m2 and not a typo that changes the value."
        ),
    ),
    TranscriptionNote(
        note_id="TN-03",
        statement=(
            "Dissolved oxygen enters eq. (3), (4), (11) and (15) as a percentage "
            "of the probe's saturation reading; Ko,1 and Ko,2 are percentages."
        ),
        decision=(
            "DO is carried as a percentage throughout. Conversion to a "
            "dissolved-oxygen concentration needs the reported C* = 0.0075 g/L "
            "and is available only through an explicit, tested conversion."
        ),
        affected_equations=("eq. (3)", "eq. (4)", "eq. (11)", "eq. (15)"),
        source=_NOTATION_SOURCE,
    ),
    TranscriptionNote(
        note_id="TN-04",
        statement=(
            "Eq. (11) and (15) print the oxygen-consumption term as "
            "'(100/C*)(mu1/Yo1 + mu2/Yo2) X' -- a quotient, with 100 above a "
            "fraction bar and C* below it. This package originally transcribed "
            "that factor as the product (100*C*), because the PDF text layer "
            "drops the fraction bar and renders it as '100C*'."
        ),
        decision=(
            "Corrected to the printed quotient (100/C*). The correction was "
            "made from three independent pieces of evidence, not from the fact "
            "that the correction improves the simulation. (1) The rendered "
            "page, at 9x, shows the fraction bar. (2) Unit algebra: "
            "(mu1/Yo1 + mu2/Yo2)*X is an oxygen uptake rate in g O2/(L.h), so "
            "dividing by C* and scaling by 100 gives %/h -- the dimension of "
            "d(DO)/dt and of the kLa*(100 - DO) transfer term beside it -- "
            "whereas multiplying by C* would give M^2 L^-6 T^-1, which cannot "
            "be added to it; see models.dimensions. (3) The paper's reported "
            "behaviour is only reachable under the quotient reading. The "
            "parameter values themselves were not touched."
        ),
        affected_equations=("eq. (11)", "eq. (15)"),
        source=_EQ_SOURCE,
        unresolved=False,
        review_question=(
            "None outstanding for the transcription. Worth showing the authors "
            "that the text layer of their own equation reads as a product, in "
            "case downstream users have made the same mistake."
        ),
    ),
    TranscriptionNote(
        note_id="TN-05",
        statement=(
            "Eq. (13) and (14) require S10 and S20 as concentrations, but the feed "
            "recipes are printed as percent weight/volume (Table 1)."
        ),
        decision=(
            "S10 and S20 are taken in g/L. Percent w/v is converted explicitly "
            "by percent_wv_to_g_per_l (1 % w/v = 10 g/L) at the API boundary; the "
            "balances never see a percentage."
        ),
        affected_equations=("eq. (13)", "eq. (14)"),
        source=SourceRef(
            section="3. Results", locator="Table 1", printed_page=4,
            quote="Glycerol Conc. (% w/v)",
        ),
    ),
)


# --------------------------------------------------------------------------- #
# eq. (1)-(2): stoichiometries
# --------------------------------------------------------------------------- #


def stoichiometric_residual_1(X: float, S1: float, S2: float, DO: float,
                               parameters: ParameterSet) -> float:
    """Left-hand side of eq. (1): ``X - S1/Y11 - S2/Y12 - DO/Yo1``.

    Provided so the stoichiometric relation is checkable, not because the model
    integrates it (TN-01). DO enters as the percentage the paper uses
    throughout; this residual mixes units by construction and is a relation
    check, not a balance.
    """
    return (
        X
        - S1 / parameters.value("Y11")
        - S2 / parameters.value("Y12")
        - DO / parameters.value("Yo1")
    )


def stoichiometric_residual_2(X: float, S2: float, DO: float,
                              parameters: ParameterSet) -> float:
    """Left-hand side of eq. (2): ``X - S2/Y22 - DO/Yo2`` (TN-01)."""
    return X - S2 / parameters.value("Y22") - DO / parameters.value("Yo2")


# --------------------------------------------------------------------------- #
# eq. (3)-(4): substrate response
# --------------------------------------------------------------------------- #


def response_r1(S1: float, S2: float, DO: float, parameters: ParameterSet) -> float:
    """Eq. (3): ``r1 = (S1/(K11+S1)) * (S2/(K12+S2)) * (DO/(Ko,1+DO))``.

    Three multiplicative limitation terms. A zero value of any substrate gives
    exactly zero, with no division by the substrate and so no singularity.
    """
    s1_term = S1 / (parameters.value("K11") + S1)
    s2_term = S2 / (parameters.value("K12") + S2)
    do_term = DO / (parameters.value("Ko1") + DO)
    return s1_term * s2_term * do_term


def response_r2(S2: float, DO: float, parameters: ParameterSet) -> float:
    """Eq. (4): ``r2 = (S2/(K22+S2)) * (DO/(Ko,2+DO))``."""
    s2_term = S2 / (parameters.value("K22") + S2)
    do_term = DO / (parameters.value("Ko2") + DO)
    return s2_term * do_term


# --------------------------------------------------------------------------- #
# eq. (5)-(6): growth rates
# --------------------------------------------------------------------------- #


def specific_growth_1(r1: float, e1: float, parameters: ParameterSet) -> float:
    """Eq. (5) for k = 1: ``mu1 = mum1 * (e1/e_m1) * r1``."""
    return parameters.value("mum1") * e1 * r1


def specific_growth_2(r2: float, e2: float, parameters: ParameterSet) -> float:
    """Eq. (5) for k = 2: ``mu2 = mum2 * (e2/e_m2) * r2``."""
    return parameters.value("mum2") * e2 * r2


def specific_growth_rates(
    S1: float, S2: float, DO: float, e1: float, e2: float,
    parameters: ParameterSet,
) -> tuple[float, float, float]:
    """Eq. (5)-(6) together: ``(r1, r2, mu)`` with ``mu = mu1 + mu2``.

    Returns the two responses as well, because every balance needs them and
    recomputing them would invite two different answers to the same question.
    """
    r1 = response_r1(S1, S2, DO, parameters)
    r2 = response_r2(S2, DO, parameters)
    mu1 = specific_growth_1(r1, e1, parameters)
    mu2 = specific_growth_2(r2, e2, parameters)
    return r1, r2, mu1 + mu2


# --------------------------------------------------------------------------- #
# eq. (7): enzyme dynamics
# --------------------------------------------------------------------------- #


def enzyme_fraction_derivative(
    index: int, r_k: float, e_k: float, mu: float, parameters: ParameterSet
) -> float:
    """Eq. (7) for combination ``index`` (1 or 2).

        d(e_k/e_mk)/dt = (mum_k + beta_k)*r_k - (mu + beta_k)*(e_k/e_mk)

    ``index`` is 1-based and selects ``mum_k``, ``beta_k`` and ``r_k``. The
    state is the normalised fraction (TN-02); no ``e_mk`` value appears.
    """
    if index not in (1, 2):
        raise ValueError(f"combination index must be 1 or 2, got {index!r}")
    mum_k = parameters.value(f"mum{index}")
    beta_k = parameters.value(f"beta{index}")
    return (mum_k + beta_k) * r_k - (mu + beta_k) * e_k


def growth_terms(
    S1: float, S2: float, DO: float, e1: float, e2: float,
    parameters: ParameterSet,
) -> Mapping[str, float]:
    """Every kinetic quantity of one state, computed once.

    Returning them as a mapping keeps eq. (5), (6) and (7) consistent with one
    another: the growth rates that divide a substrate are the same numbers the
    substrate derivative uses.
    """
    r1 = response_r1(S1, S2, DO, parameters)
    r2 = response_r2(S2, DO, parameters)
    mu1 = specific_growth_1(r1, e1, parameters)
    mu2 = specific_growth_2(r2, e2, parameters)
    mu = mu1 + mu2
    return {
        "r1": r1,
        "r2": r2,
        "mu1": mu1,
        "mu2": mu2,
        "mu": mu,
        "de1": enzyme_fraction_derivative(1, r1, e1, mu, parameters),
        "de2": enzyme_fraction_derivative(2, r2, e2, mu, parameters),
    }