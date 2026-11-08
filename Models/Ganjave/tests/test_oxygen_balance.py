"""Oxygen-balance tests: GJ-O2-01 through GJ-O2-08.

The question these tests exist to answer is whether eq. (11) and eq. (15)
correctly represent the paper's dissolved-oxygen balance. The answer was no:
the package transcribed the printed factor ``100/C*`` as the product
``100*C*``, because the PDF's text layer drops the fraction bar. These tests
are the evidence, and they are written so that a future change cannot quietly
reintroduce the error.

Every expected value below is arithmetic on the paper's own printed numbers.
Nothing in this module takes an expected result from the implementation it is
checking, and where a test compares against a recorded value, that value is
either written out from Table 2 or is a measurement of the PDF's glyph
geometry.

GJ-O2-01  source transcription
GJ-O2-02  dimensional consistency
GJ-O2-03  oxygen transfer
GJ-O2-04  oxygen consumption, per combination
GJ-O2-05  the percentage/concentration relationship via C*
GJ-O2-06  batch and fed-batch use the same conventions
GJ-O2-07  regression: nothing else moved
GJ-O2-08  uncertainty preservation
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from models.batch import (
    batch_derivative,
    dDO_dt,
    oxygen_consumption_term,
    oxygen_transfer_term,
)
from models.dimensions import (
    GAS_PER_LITRE,
    PERCENT,
    PERCENT_PER_TIME,
    QUANTITIES,
    Dimension,
    oxygen_balance_dimensions,
    oxygen_balance_report,
)
from models.fed_batch import FeedProgram, dDO_dt as fed_dDO_dt, dilution_rate, fed_batch_derivative
from models.kinetics import TRANSCRIPTION_NOTES, growth_terms
from models.simulation import simulate
from schemas.parameters import EQUATION_CHANGES, EQUATIONS_VERSION, table2_parameter_set
from schemas.state import State
from schemas.units import do_concentration_to_percentage, do_percentage_to_concentration

# ---------------------------------------------------------------------------
# The paper's printed numbers, restated so the arithmetic below is readable.
# Table 2 (printed p. 4), the Notations table (printed p. 2), p. 3.
# ---------------------------------------------------------------------------
KLA = 133.0          # h^-1, measured for the 500 mL baffled flask at 200 rpm
C_STAR = 0.0075      # g/L, maximum solubility of oxygen in the medium
YO1, YO2 = 0.925, 1.219       # g biomass / g oxygen
MUM1, MUM2 = 1.497, 0.834     # h^-1
K11, K12, K22 = 0.131, 36.154, 1.001
KO1, KO2 = 0.326, 8.944       # % of the dissolved-oxygen reading

#: The fixed state every hand calculation starts from.
_X, _S1, _S2, _DO, _E1, _E2, _V = 2.0, 4.0, 10.0, 50.0, 0.30, 0.60, 0.1

#: The factor exactly as printed: a quotient.
PRINTED_FACTOR = 100.0 / C_STAR
#: The reading this package originally implemented, kept only so a test can
#: show it is a different number.
TRANSPOSED_FACTOR = 100.0 * C_STAR


def hand_r1() -> float:
    return (_S1 / (K11 + _S1)) * (_S2 / (K12 + _S2)) * (_DO / (KO1 + _DO))


def hand_r2() -> float:
    return (_S2 / (K22 + _S2)) * (_DO / (KO2 + _DO))


def hand_mu() -> tuple[float, float, float]:
    """(mu1, mu2, mu) written out on the printed values."""
    mu1 = MUM1 * _E1 * hand_r1()
    mu2 = MUM2 * _E2 * hand_r2()
    return mu1, mu2, mu1 + mu2


def hand_uptake_rate() -> float:
    """Oxygen uptake rate OUR = (mu1/Yo1 + mu2/Yo2)*X, in g O2/(L.h)."""
    mu1, mu2, _mu = hand_mu()
    return (mu1 / YO1 + mu2 / YO2) * _X


@pytest.fixture()
def state() -> State:
    return State(t=0.0, X=_X, S1=_S1, S2=_S2, DO=_DO, e1=_E1, e2=_E2, V=_V)


# --------------------------------------------------------------------------- #
# GJ-O2-01  Source transcription
# --------------------------------------------------------------------------- #


class TestSourceTranscription:
    """GJ-O2-01: the transcription matches what the paper prints."""

    def test_the_printed_factor_is_a_quotient(self, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        assert oxygen_consumption_term(mu1, mu2, _X, parameters) == pytest.approx(
            (100.0 / C_STAR) * hand_uptake_rate()
        )

    def test_the_transposed_factor_is_not_what_is_implemented(self, parameters) -> None:
        """The two readings differ by 1/C*^2, so no test can accept both."""
        mu1, mu2, _mu = hand_mu()
        got = oxygen_consumption_term(mu1, mu2, _X, parameters)
        transposed = TRANSPOSED_FACTOR * hand_uptake_rate()
        assert got / transposed == pytest.approx(1.0 / (C_STAR * C_STAR))
        assert got != pytest.approx(transposed)

    def test_the_transcription_note_records_both_readings(self) -> None:
        note = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-04")
        assert "(100/C*)" in note.statement
        assert "(100*C*)" in note.statement
        assert note.unresolved is False
        assert set(note.affected_equations) == {"eq. (11)", "eq. (15)"}

    def test_equations_version_records_the_correction(self) -> None:
        assert EQUATIONS_VERSION == "1.1.0"
        change = EQUATION_CHANGES["1.1.0"]
        assert "100/C*" in change
        assert "No parameter value changed" in change

    def test_docstrings_quote_the_printed_equations(self) -> None:
        """The transcription is also written down where it is implemented."""
        import models.batch as batch_module
        import models.fed_batch as fed_module

        # The module docstrings carry the printed equation listings.
        assert "(100/C*)*(mu1/Yo1 + mu2/Yo2)*X" in batch_module.__doc__
        assert "(100/C*)*(mu1/Yo1 + mu2/Yo2)*X" in fed_module.__doc__
        # and the two balance functions quote their own equation.
        assert "(100/C*)*(mu1/Yo1 + mu2/Yo2)*X" in (inspect.getdoc(dDO_dt) or "")
        assert "(100/C*)*(mu1/Yo1 + mu2/Yo2)*X" in (inspect.getdoc(fed_dDO_dt) or "")


class TestPrintedPageEvidence:
    """The same claim, measured from the article PDF rather than asserted.

    These tests need the PDF and PyMuPDF. Where they cannot run they say so
    loudly; they never pass by doing nothing quietly.
    """

    @staticmethod
    def _pdf():
        from models.paper_equations import PaperNotAvailable, resolve_source_pdf

        try:
            return resolve_source_pdf()
        except PaperNotAvailable as exc:
            pytest.skip(f"article PDF unavailable: {exc}")

    def test_the_numerator_is_stacked_above_the_denominator_in_eq_11(self) -> None:
        """A fraction prints 100 above C*, not beside it."""
        from models.paper_equations import fraction_numerator_above

        pdf = self._pdf()
        measurement = fraction_numerator_above(pdf, 3, "(11)", "left", "100", "C*")
        assert measurement["vertical_offset_pt"] > 5.0, measurement
        assert measurement["stacked"] is True

    def test_the_numerator_is_stacked_above_the_denominator_in_eq_15(self) -> None:
        from models.paper_equations import fraction_numerator_above

        pdf = self._pdf()
        measurement = fraction_numerator_above(pdf, 3, "(15)", "right", "100", "C*")
        assert measurement["vertical_offset_pt"] > 5.0, measurement

    def test_same_line_tokens_agree_where_the_fraction_does_not(self) -> None:
        """Calibrates the offset: a control pair on one line must not be stacked.

        Without this, "different baselines" could be an artefact of how words
        are boxed. Here two denominators printed side by side in eq. (11) agree
        to under a point, while 100 and C* differ by more than five.
        """
        from models.paper_equations import fraction_numerator_above

        pdf = self._pdf()
        control = fraction_numerator_above(pdf, 3, "(11)", "left", "Yo1", "Yo2")
        factor = fraction_numerator_above(pdf, 3, "(11)", "left", "100", "C*")
        assert control["vertical_offset_pt"] < 1.0, control
        assert factor["vertical_offset_pt"] > 5.0, factor

    def test_the_text_layer_is_the_trap_it_was(self) -> None:
        """Documents why a text-only transcription gets this wrong.

        The text layer of eq. (11) contains no '/' between the 100 and the C*,
        so a reader who trusts it concludes a product. The geometry above is
        what settles the question.
        """
        from models.paper_equations import page_words

        pdf = self._pdf()
        tokens = [
            t.text for t in page_words(pdf, 3)
            if 515 <= t.y0 <= 555 and t.x0 < 300
        ]
        joined = " ".join(tokens)
        assert "C*" in joined
        assert "/" not in joined, (
            "if the text layer ever carries a solidus here, the trap is gone "
            "and this test should be revisited"
        )

    def test_the_notation_value_of_c_star_is_present(self) -> None:
        from models.paper_equations import page_words

        pdf = self._pdf()
        text = " ".join(t.text for t in page_words(pdf, 1))
        assert "0.0075" in text


# --------------------------------------------------------------------------- #
# GJ-O2-02  Dimensional consistency
# --------------------------------------------------------------------------- #


class TestDimensionalConsistency:
    """GJ-O2-02: the terms of the balance can be added together."""

    def test_transfer_has_the_dimension_of_d_do_dt(self) -> None:
        dims = oxygen_balance_dimensions()
        assert dims["transfer_kLa_x_100_minus_DO"] == PERCENT_PER_TIME
        assert dims["d_DO_dt_required"] == PERCENT_PER_TIME

    def test_consumption_has_the_dimension_of_d_do_dt(self) -> None:
        dims = oxygen_balance_dimensions()
        assert dims["consumption_as_printed"] == PERCENT_PER_TIME

    def test_the_transposed_reading_does_not(self) -> None:
        """The dimensional reason the product reading cannot be right."""
        dims = oxygen_balance_dimensions()
        assert dims["consumption_if_product_reading"] != PERCENT_PER_TIME
        assert dims["consumption_if_product_reading"] == (
            Dimension(mass=2, length=-6, time=-1)
        )

    def test_the_batch_terms_are_addable_as_printed(self) -> None:
        report = oxygen_balance_report()
        assert report["batch_terms_addable"] is True
        assert report["batch_terms_addable_under_product_reading"] is False

    def test_adding_the_terms_of_different_dimensions_is_refused(self) -> None:
        """The algebra itself refuses an impossible sum."""
        with pytest.raises(TypeError, match="different dimensions"):
            PERCENT * GAS_PER_LITRE + PERCENT  # noqa: B018

    def test_dissolved_oxygen_is_carried_as_a_percentage(self) -> None:
        assert QUANTITIES["DO"] == PERCENT
        assert QUANTITIES["kLa"] == QUANTITIES["mum1"] == Dimension(time=-1)

    def test_the_yields_are_mass_ratios_and_therefore_dimensionless(self) -> None:
        """Declared, because it is why the equation reduces correctly."""
        assert QUANTITIES["Yo1"] == Dimension()
        assert QUANTITIES["Yo2"] == Dimension()

    def test_the_uptake_rate_is_a_concentration_per_time(self) -> None:
        dims = oxygen_balance_dimensions()
        assert dims["uptake_rate_mu_over_Y_times_X"] == Dimension(
            mass=1, length=-3, time=-1
        )

    def test_the_fed_batch_dilution_term_matches_too(self) -> None:
        """eq. (15)'s (DO)*F/V is in the same units as the other two terms."""
        dims = oxygen_balance_dimensions()
        assert dims["fed_batch_dilution_DO_x_F_over_V"] == PERCENT_PER_TIME

    def test_the_report_names_its_sources(self) -> None:
        report = oxygen_balance_report()
        assert "fraction bar" in report["source"]["eq_11"]
        assert "rendering" in report["source"]["eq_15"]


# --------------------------------------------------------------------------- #
# GJ-O2-03  Oxygen transfer
# --------------------------------------------------------------------------- #


class TestOxygenTransfer:
    """GJ-O2-03: the transfer term, calculated from the printed definition."""

    @pytest.mark.parametrize("do_percent", [0.0, 10.0, 25.0, 50.0, 75.0, 99.0])
    def test_transfer_is_kla_times_the_gap_to_saturation(self, parameters, do_percent) -> None:
        assert oxygen_transfer_term(do_percent, parameters) == pytest.approx(
            KLA * (100.0 - do_percent)
        )

    def test_transfer_vanishes_exactly_at_saturation(self, parameters) -> None:
        assert oxygen_transfer_term(100.0, parameters) == 0.0

    def test_transfer_is_maximal_at_zero_reading(self, parameters) -> None:
        assert oxygen_transfer_term(0.0, parameters) == pytest.approx(KLA * 100.0)

    def test_transfer_is_linear_in_the_gap(self, parameters) -> None:
        assert oxygen_transfer_term(80.0, parameters) == pytest.approx(
            2.0 * oxygen_transfer_term(90.0, parameters)
        )

    def test_transfer_carries_no_biomass_dependence(self, parameters) -> None:
        """It is a property of the vessel and the medium, not the culture."""
        assert oxygen_transfer_term(50.0, parameters) == pytest.approx(6650.0)


# --------------------------------------------------------------------------- #
# GJ-O2-04  Oxygen consumption
# --------------------------------------------------------------------------- #


class TestOxygenConsumption:
    """GJ-O2-04: each biological contribution, computed independently."""

    def test_total_consumption_from_the_printed_expression(self, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        expected = (100.0 / C_STAR) * (mu1 / YO1 + mu2 / YO2) * _X
        assert oxygen_consumption_term(mu1, mu2, _X, parameters) == pytest.approx(expected)

    def test_combination_1_contribution(self, parameters) -> None:
        mu1, _mu2, _mu = hand_mu()
        expected = (100.0 / C_STAR) * (mu1 / YO1) * _X
        assert expected > 0.0
        assert oxygen_consumption_term(mu1, 0.0, _X, parameters) == pytest.approx(expected)

    def test_combination_2_contribution(self, parameters) -> None:
        _mu1, mu2, _mu = hand_mu()
        expected = (100.0 / C_STAR) * (mu2 / YO2) * _X
        assert expected > 0.0
        assert oxygen_consumption_term(0.0, mu2, _X, parameters) == pytest.approx(expected)

    def test_the_two_contributions_sum_to_the_total(self, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        via_1 = oxygen_consumption_term(mu1, 0.0, _X, parameters)
        via_2 = oxygen_consumption_term(0.0, mu2, _X, parameters)
        assert via_1 + via_2 == pytest.approx(
            oxygen_consumption_term(mu1, mu2, _X, parameters)
        )

    def test_consumption_is_proportional_to_biomass(self, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        assert oxygen_consumption_term(mu1, mu2, 2 * _X, parameters) == pytest.approx(
            2.0 * oxygen_consumption_term(mu1, mu2, _X, parameters)
        )

    def test_consumption_vanishes_without_growth(self, parameters) -> None:
        assert oxygen_consumption_term(0.0, 0.0, _X, parameters) == 0.0

    def test_consumption_is_the_same_order_as_transfer_here(self, parameters) -> None:
        """Both terms are %/h, so they are comparable magnitudes by construction."""
        mu1, mu2, _mu = hand_mu()
        transfer = oxygen_transfer_term(_DO, parameters)
        consumption = oxygen_consumption_term(mu1, mu2, _X, parameters)
        assert 1.0e-3 < consumption / transfer < 1.0e3

    def test_derivative_is_the_printed_balance(self, state, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        expected = (
            KLA * (100.0 - _DO) - (100.0 / C_STAR) * (mu1 / YO1 + mu2 / YO2) * _X
        )
        assert dDO_dt(state, parameters) == pytest.approx(expected)

    def test_derivative_becomes_negative_when_uptake_exceeds_transfer(self, parameters) -> None:
        """At this state the culture is oxygen-limited, so DO must fall."""
        state = State(t=0.0, X=_X, S1=_S1, S2=_S2, DO=_DO, e1=_E1, e2=_E2, V=_V)
        assert dDO_dt(state, parameters) < 0.0

    def test_zero_c_star_is_refused(self, parameters) -> None:
        degenerate = parameters.with_overrides({"C_star": 0.0}, reason="degenerate case")
        with pytest.raises(ValueError, match="strictly positive"):
            oxygen_consumption_term(0.1, 0.1, 1.0, degenerate)


# --------------------------------------------------------------------------- #
# GJ-O2-05  Percentage / concentration
# --------------------------------------------------------------------------- #


class TestPercentageConversion:
    """GJ-O2-05: the DO reading relates to C* in exactly one way."""

    def test_full_scale_is_c_star(self) -> None:
        assert do_percentage_to_concentration(100.0, C_STAR) == pytest.approx(C_STAR)

    def test_half_scale_is_half_c_star(self) -> None:
        assert do_percentage_to_concentration(50.0, C_STAR) == pytest.approx(
            C_STAR / 2.0
        )

    def test_zero_reading_is_zero_concentration(self) -> None:
        assert do_percentage_to_concentration(0.0, C_STAR) == 0.0

    def test_the_conversion_round_trips(self) -> None:
        for do_percent in (0.0, 12.5, 50.0, 67.0, 100.0):
            conc = do_percentage_to_concentration(do_percent, C_STAR)
            assert do_concentration_to_percentage(conc, C_STAR) == pytest.approx(do_percent)

    def test_the_balance_in_percentage_is_the_balance_in_concentration(
        self, parameters
    ) -> None:
        """The decisive consistency check between the two printed terms.

        The paper's transfer term is ``kLa*(100 - DO)``. Written in g/L the same
        balance is ``kLa*(C* - DO_conc) - OUR``. Multiplying the second by
        ``100/C*`` reproduces the first term exactly -- so the consumption term
        printed beside it must carry that same ``100/C*``. This is why the two
        terms share a conversion factor, and it is arithmetic on the printed
        equations rather than on any simulation result.
        """
        do_percent = 50.0
        do_conc = do_percentage_to_concentration(do_percent, C_STAR)  # g O2/L
        our = hand_uptake_rate()                                     # g O2/(L.h)

        concentration_form = KLA * (C_STAR - do_conc) - our           # g/(L.h)
        converted = (100.0 / C_STAR) * concentration_form             # %/h

        mu1, mu2, _mu = hand_mu()
        as_implemented = (
            oxygen_transfer_term(do_percent, parameters)
            - oxygen_consumption_term(mu1, mu2, _X, parameters)
        )
        assert converted == pytest.approx(as_implemented)

    def test_the_transfer_term_alone_survives_the_same_conversion(self) -> None:
        do_percent = 30.0
        do_conc = do_percentage_to_concentration(do_percent, C_STAR)
        in_conc = KLA * (C_STAR - do_conc)
        assert (100.0 / C_STAR) * in_conc == pytest.approx(
            KLA * (100.0 - do_percent)
        )

    def test_a_percentage_is_not_a_mass_fraction(self) -> None:
        """100 % is 0.0075 g/L, not 1.0 -- the reason the two cannot be joined."""
        assert do_percentage_to_concentration(100.0, C_STAR) != pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# GJ-O2-06  Batch and fed-batch consistency
# --------------------------------------------------------------------------- #


class TestBatchFedBatchConsistency:
    """GJ-O2-06: both modes use one set of oxygen conventions."""

    def test_the_same_consumption_term_serves_both_modes(self) -> None:
        mu1, mu2, _mu = hand_mu()
        feed = FeedProgram(S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=1e-3)
        flow = 1e-3
        batch_derivative(State(0.0, _X, _S1, _S2, _DO, _E1, _E2, _V), table2_parameter_set())
        from models.batch import dDO_dt as batch_dDO_dt

        batch = batch_dDO_dt(
            State(0.0, _X, _S1, _S2, _DO, _E1, _E2, _V), table2_parameter_set()
        )
        fed = fed_dDO_dt(
            State(0.0, _X, _S1, _S2, _DO, _E1, _E2, _V), feed, flow, table2_parameter_set()
        )
        assert fed == pytest.approx(batch - _DO * dilution_rate(flow, _V))

    def test_the_only_difference_is_the_dilution_term(self, state, parameters) -> None:
        feed = FeedProgram(S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=1e-3)
        batch = dDO_dt(state, parameters)
        fed = fed_dDO_dt(state, feed, 1e-3, parameters)
        assert fed - batch == pytest.approx(-_DO * 0.01)

    def test_a_stopped_pump_reduces_fed_batch_to_batch(self, state, parameters) -> None:
        feed = FeedProgram(S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=1e-3)
        assert fed_dDO_dt(state, feed, 0.0, parameters) == pytest.approx(
            dDO_dt(state, parameters)
        )

    def test_the_fed_batch_vector_keeps_the_printed_order(self, state, parameters) -> None:
        feed = FeedProgram(S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=1e-3)
        vector = fed_batch_derivative(state, feed, parameters, t=10.0)
        assert len(vector) == 7
        assert vector[3] == pytest.approx(
            fed_dDO_dt(state, feed, 1e-3, parameters)
        )

    def test_both_modes_reject_a_non_positive_c_star(self, parameters) -> None:
        from models.fed_batch import FeedError  # noqa: F401  (import surface check)

        degenerate = parameters.with_overrides({"C_star": -1.0}, reason="degenerate case")
        state = State(0.0, _X, _S1, _S2, _DO, _E1, _E2, _V)
        with pytest.raises(ValueError):
            dDO_dt(state, degenerate)


# --------------------------------------------------------------------------- #
# GJ-O2-07  Regression
# --------------------------------------------------------------------------- #


#: Values recorded from this package *before* the oxygen correction, at the
#: fixed state. Nothing here may move: the correction is confined to the oxygen
#: term of eq. (11) and eq. (15).
PRE_CORRECTION_GROWTH_TERMS = {
    "r1": 0.20843614948555444,
    "r2": 0.7710778637140973,
    "mu1": 0.0936086747339625,
    "mu2": 0.38584736300253425,
    "mu": 0.47945603773649675,
    "de1": 0.16810054060841156,
    "de2": 0.3601954958796538,
}

PRE_CORRECTION_BATCH_DERIVATIVE = (
    0.9589120754729935,
    -0.42549397606346595,
    -3.2506737171222677,
    6649.373410480086,          # the oxygen term: the one that was wrong
    0.16810054060841156,
    0.3601954958796538,
    0.0,
)


class TestRegression:
    """GJ-O2-07: the investigation touched nothing else."""

    def test_response_functions_are_bit_identical(self) -> None:
        terms = growth_terms(_S1, _S2, _DO, _E1, _E2, table2_parameter_set())
        for key, before in PRE_CORRECTION_GROWTH_TERMS.items():
            assert repr(terms[key]) == repr(before), key

    def test_biomass_substrate_and_enzyme_terms_are_bit_identical(self, state) -> None:
        vector = batch_derivative(state, table2_parameter_set())
        for index in (0, 1, 2, 4, 5, 6):
            assert repr(vector[index]) == repr(PRE_CORRECTION_BATCH_DERIVATIVE[index]), index

    def test_only_the_oxygen_term_moved(self, state) -> None:
        """The oxygen term is the only one that differs from the old build.

        The expected value is arithmetic on the printed numbers, not the
        implementation: 6650 %/h of transfer minus (100/0.0075) times the
        uptake rate of this state.
        """
        vector = batch_derivative(state, table2_parameter_set())
        before = PRE_CORRECTION_BATCH_DERIVATIVE[3]
        assert repr(vector[3]) != repr(before)

        transfer = KLA * (100.0 - _DO)
        consumption = (100.0 / C_STAR) * hand_uptake_rate()
        assert vector[3] == pytest.approx(transfer - consumption)
        assert vector[3] < 0.0, "the uptake must exceed transfer at this state"

    def test_the_parameter_set_is_untouched(self, parameters) -> None:
        assert parameters.version == "1.0.0"
        assert parameters.value("kLa") == KLA
        assert parameters.value("C_star") == C_STAR
        assert parameters.value("Yo1") == YO1
        assert parameters.value("Yo2") == YO2
        assert parameters.value("mum1") == MUM1
        assert parameters.value("Ko1") == KO1
        assert parameters.value("Ko2") == KO2

    def test_no_parameter_was_overridden_to_compensate(self, parameters) -> None:
        """A correction to an equation must not come with a tuned value."""
        for symbol in parameters:
            record = parameters.parameter(symbol)
            assert record.provenance.value in ("fitted", "reported"), symbol
            assert "overridden by the caller" not in record.note

    def test_the_solver_configuration_is_untouched(self) -> None:
        from models.solver import SOLVER_NAME, SOLVER_VERSION, SolverConfig

        config = SolverConfig()
        assert SOLVER_NAME == "runge-kutta-4(3) step-doubling"
        assert SOLVER_VERSION == "1.0.0"
        assert config.rtol == 1.0e-6
        assert config.h_max == 1.0e-2

    def test_provenance_still_records_everything_a_run_needs(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0, mode="batch"
        )
        provenance = result.provenance
        assert provenance.equations_version == "1.1.0"
        assert len(provenance.input_digest) == 64
        assert provenance.parameters["version"] == "1.0.0"

    def test_the_batch_run_still_completes(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=6.0, mode="batch"
        )
        assert result.ok, [d.message for d in result.diagnostics]
        assert result.final_state.t == pytest.approx(6.0)


# --------------------------------------------------------------------------- #
# GJ-O2-08  Uncertainty preservation
# --------------------------------------------------------------------------- #


class TestUncertaintyPreservation:
    """GJ-O2-08: what is still unknown stays visible."""

    def test_the_enzyme_ratio_typo_is_still_unresolved(self) -> None:
        note = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-02")
        assert note.unresolved is True
        assert "e20/em1" in note.statement
        assert note.review_question

    def test_exactly_one_note_remains_unresolved(self) -> None:
        unresolved = [n.note_id for n in TRANSCRIPTION_NOTES if n.unresolved]
        assert unresolved == ["TN-02"]

    def test_every_run_reports_the_remaining_ambiguity(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0, mode="batch"
        )
        notes = {
            d.detail.get("note_id")
            for d in result.diagnostics
            if d.code.value == "transcription.unresolved"
        }
        assert notes == {"TN-02"}

    def test_the_correction_is_recorded_rather_than_quietly_applied(self) -> None:
        """A corrected equation must leave its history in the package."""
        note = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-04")
        assert "transcribed" in note.statement
        assert "fraction bar" in note.statement
        assert "1.1.0" in EQUATION_CHANGES or "quotient" in EQUATION_CHANGES["1.1.0"]

    def test_the_superseded_reading_is_not_implemented_in_production_code(self) -> None:
        """No production path may silently multiply by C*."""
        root = Path(__file__).resolve().parents[1] / "models"
        offenders = []
        for path in sorted(root.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("*"):
                    continue  # prose and docstrings may name the old reading
                if "100.0 * c_star" in stripped or "100 * C_star" in stripped:
                    offenders.append(f"{path.name}: {stripped}")
        assert offenders == []

    def test_the_rejected_reading_is_still_available_for_audit(self) -> None:
        """It must be documented and computable, just not the default."""
        from models.dimensions import oxygen_balance_dimensions

        dims = oxygen_balance_dimensions()
        assert dims["product_reading_factor_100_times_C"] == GAS_PER_LITRE
        assert dims["consumption_if_product_reading"] != PERCENT_PER_TIME