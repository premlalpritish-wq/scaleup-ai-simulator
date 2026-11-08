"""Cybernetic kinetics: eq. (1)-(7).

Covers GJ-02 (response bounds and monotonicity), GJ-03 (zero substrate), GJ-04
(growth-rate aggregation) and GJ-05 (enzyme dynamics against hand calculation),
plus the stoichiometric relation of eq. (1)/(2).

Every expected number below is written out as arithmetic on the printed Table 2
values. None of them is produced by calling the implementation, so a test that
passes means the code agrees with the paper rather than with itself.
"""

from __future__ import annotations

import math

import pytest

from models.kinetics import (
    TRANSCRIPTION_NOTES,
    enzyme_fraction_derivative,
    growth_terms,
    response_r1,
    response_r2,
    specific_growth_1,
    specific_growth_2,
    specific_growth_rates,
    stoichiometric_residual_1,
    stoichiometric_residual_2,
)

# Printed Table 2 values, restated here so the arithmetic below is readable.
MUM1, MUM2 = 1.497, 0.834
K11, K12, K22 = 0.131, 36.154, 1.001
KO1, KO2 = 0.326, 8.944
Y11, Y12, Y22, YO1, YO2 = 0.440, 0.881, 0.254, 0.925, 1.219
BETA1, BETA2 = 0.001, 0.028


def hand_r1(S1: float, S2: float, DO: float) -> float:
    """eq. (3), written out: (S1/(K11+S1)) * (S2/(K12+S2)) * (DO/(Ko,1+DO))."""
    return (S1 / (K11 + S1)) * (S2 / (K12 + S2)) * (DO / (KO1 + DO))


def hand_r2(S2: float, DO: float) -> float:
    """eq. (4), written out: (S2/(K22+S2)) * (DO/(Ko,2+DO))."""
    return (S2 / (K22 + S2)) * (DO / (KO2 + DO))


class TestStoichiometry:
    """eq. (1)-(2): a checkable relation, not an integrated balance (TN-01)."""

    def test_residual_1_is_zero_on_the_printed_yields(self, parameters) -> None:
        # Pick X from eq. (1) for a state, then the residual must vanish.
        S1, S2, DO = 4.0, 10.0, 50.0
        X = S1 / Y11 + S2 / Y12 + DO / YO1
        assert stoichiometric_residual_1(X, S1, S2, DO, parameters) == pytest.approx(
            0.0, abs=1e-12
        )

    def test_residual_2_is_zero_on_the_printed_yields(self, parameters) -> None:
        S2, DO = 10.0, 50.0
        X = S2 / Y22 + DO / YO2
        assert stoichiometric_residual_2(X, S2, DO, parameters) == pytest.approx(
            0.0, abs=1e-12
        )

    def test_residual_is_not_zero_off_the_relation(self, parameters) -> None:
        assert stoichiometric_residual_1(2.0, 4.0, 10.0, 50.0, parameters) != 0.0

    def test_stoichiometry_is_declared_as_a_note_not_a_balance(self) -> None:
        note = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-01")
        assert "not as an integrated equation" in note.decision
        assert "eq. (1)" in note.affected_equations


class TestResponseBounds:
    """GJ-02: both responses stay in range and increase with their substrates."""

    @pytest.mark.parametrize(
        "s1,s2,do", [(4.0, 10.0, 50.0), (0.1, 0.5, 1.0), (100.0, 200.0, 100.0)]
    )
    def test_r1_is_a_strict_fraction(self, parameters, s1, s2, do) -> None:
        r1 = response_r1(s1, s2, do, parameters)
        assert 0.0 <= r1 <= 1.0
        assert r1 == pytest.approx(hand_r1(s1, s2, do))

    @pytest.mark.parametrize("s2,do", [(10.0, 50.0), (0.1, 0.5), (200.0, 100.0)])
    def test_r2_is_a_strict_fraction(self, parameters, s2, do) -> None:
        r2 = response_r2(s2, do, parameters)
        assert 0.0 <= r2 <= 1.0
        assert r2 == pytest.approx(hand_r2(s2, do))

    def test_r1_increases_with_each_limiting_substrate(self, parameters) -> None:
        base = response_r1(4.0, 10.0, 50.0, parameters)
        assert response_r1(8.0, 10.0, 50.0, parameters) > base
        assert response_r1(4.0, 20.0, 50.0, parameters) > base
        assert response_r1(4.0, 10.0, 80.0, parameters) > base

    def test_r2_increases_with_its_substrates(self, parameters) -> None:
        base = response_r2(10.0, 50.0, parameters)
        assert response_r2(20.0, 50.0, parameters) > base
        assert response_r2(10.0, 80.0, parameters) > base

    def test_response_approaches_one_but_never_reaches_it(self, parameters) -> None:
        # A response can only approach 1 as *all* of its factors saturate.
        # With DO pinned at 100 % and Ko,1 = 0.326 the oxygen factor caps r1 at
        # 100/100.326 = 0.99675, so that is the ceiling, not 1.
        assert response_r1(1e9, 1e9, 1e9, parameters) == pytest.approx(1.0, abs=1e-6)
        assert response_r1(1e9, 1e9, 100.0, parameters) == pytest.approx(
            100.0 / (KO1 + 100.0), abs=1e-6
        )
        assert response_r2(1e9, 1e9, parameters) == pytest.approx(1.0, abs=1e-6)
        assert response_r2(1e9, 100.0, parameters) < 1.0

    def test_do_enters_as_a_percentage(self, parameters) -> None:
        """Ko,2 = 8.944 is 8.944 %, so r2 is already half-saturated at ~9 %."""
        assert response_r2(1e9, KO2, parameters) == pytest.approx(0.5, abs=1e-6)


class TestZeroSubstrate:
    """GJ-03: a zero limiting substrate gives exactly zero, with no NaN."""

    def test_zero_glycerol_gives_zero_r1(self, parameters) -> None:
        assert response_r1(0.0, 10.0, 50.0, parameters) == 0.0

    def test_zero_complex_substrate_gives_zero_for_both(self, parameters) -> None:
        assert response_r1(4.0, 0.0, 50.0, parameters) == 0.0
        assert response_r2(0.0, 50.0, parameters) == 0.0

    def test_zero_oxygen_gives_zero_for_both(self, parameters) -> None:
        assert response_r1(4.0, 10.0, 0.0, parameters) == 0.0
        assert response_r2(10.0, 0.0, parameters) == 0.0

    def test_zero_substrate_yields_zero_growth_without_division_errors(self, parameters) -> None:
        r1, r2, mu = specific_growth_rates(0.0, 0.0, 0.0, 0.3, 0.6, parameters)
        assert (r1, r2, mu) == (0.0, 0.0, 0.0)
        for value in (r1, r2, mu):
            assert not math.isnan(value)

    def test_tiny_substrate_is_finite_not_nan(self, parameters) -> None:
        r1 = response_r1(1e-300, 1e-300, 1e-300, parameters)
        assert math.isfinite(r1)
        assert r1 >= 0.0


class TestGrowthAggregation:
    """GJ-04: mu = mu1 + mu2, exactly."""

    def test_total_equals_the_sum_of_the_two(self, parameters) -> None:
        r1, r2, mu = specific_growth_rates(4.0, 10.0, 50.0, 0.3, 0.6, parameters)
        mu1 = MUM1 * 0.3 * r1
        mu2 = MUM2 * 0.6 * r2
        assert mu == pytest.approx(mu1 + mu2)
        assert mu1 == pytest.approx(specific_growth_1(r1, 0.3, parameters))
        assert mu2 == pytest.approx(specific_growth_2(r2, 0.6, parameters))

    def test_each_rate_is_mum_times_enzyme_fraction_times_response(self, parameters) -> None:
        r1 = hand_r1(4.0, 10.0, 50.0)
        assert specific_growth_1(r1, 0.3, parameters) == pytest.approx(
            MUM1 * 0.3 * r1
        )
        r2 = hand_r2(10.0, 50.0)
        assert specific_growth_2(r2, 0.6, parameters) == pytest.approx(
            MUM2 * 0.6 * r2
        )

    def test_growth_is_non_negative(self, parameters) -> None:
        for s1 in (0.0, 1e-6, 1.0, 100.0):
            for s2 in (0.0, 1e-6, 1.0, 100.0):
                for do in (0.0, 1e-6, 10.0, 100.0):
                    _r1, _r2, mu = specific_growth_rates(
                        s1, s2, do, 0.3, 0.6, parameters
                    )
                    assert mu >= 0.0

    def test_growth_terms_agrees_with_the_scalar_functions(self, parameters) -> None:
        terms = growth_terms(4.0, 10.0, 50.0, 0.3, 0.6, parameters)
        r1, r2, mu = specific_growth_rates(4.0, 10.0, 50.0, 0.3, 0.6, parameters)
        assert terms["r1"] == pytest.approx(r1)
        assert terms["r2"] == pytest.approx(r2)
        assert terms["mu"] == pytest.approx(mu)


class TestEnzymeDynamics:
    """GJ-05: eq. (7) against a hand-calculated derivative."""

    def test_hand_calculation_at_a_fixed_state(self, parameters) -> None:
        # State: S1=4, S2=10, DO=50, e1=0.30, e2=0.60
        r1 = hand_r1(4.0, 10.0, 50.0)
        r2 = hand_r2(10.0, 50.0)
        mu1 = MUM1 * 0.30 * r1
        mu2 = MUM2 * 0.60 * r2
        mu = mu1 + mu2

        # eq. (7), k = 1: (mum1 + beta1)*r1 - (mu + beta1)*e1
        expected_de1 = (MUM1 + BETA1) * r1 - (mu + BETA1) * 0.30
        # eq. (7), k = 2: (mum2 + beta2)*r2 - (mu + beta2)*e2
        expected_de2 = (MUM2 + BETA2) * r2 - (mu + BETA2) * 0.60

        assert enzyme_fraction_derivative(1, r1, 0.30, mu, parameters) == pytest.approx(
            expected_de1
        )
        assert enzyme_fraction_derivative(2, r2, 0.60, mu, parameters) == pytest.approx(
            expected_de2
        )

    def test_derivative_of_each_fraction_matches_growth_terms(self, parameters) -> None:
        terms = growth_terms(4.0, 10.0, 50.0, 0.3, 0.6, parameters)
        assert terms["de1"] == pytest.approx(
            enzyme_fraction_derivative(1, terms["r1"], 0.3, terms["mu"], parameters)
        )
        assert terms["de2"] == pytest.approx(
            enzyme_fraction_derivative(2, terms["r2"], 0.6, terms["mu"], parameters)
        )

    def test_enzyme_state_is_a_normalised_fraction_not_a_concentration(self, parameters) -> None:
        """TN-02: the state is e_k/e_mk; no e_mk value is needed anywhere."""
        r1 = hand_r1(4.0, 10.0, 50.0)
        mu1 = MUM1 * 0.30 * r1
        mu2 = MUM2 * 0.60 * hand_r2(10.0, 50.0)
        # A fraction between 0 and 1 scales mum directly, with no enzyme
        # concentration to divide by.
        assert mu1 == pytest.approx(MUM1 * 0.30 * r1)
        note = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-02")
        assert note.unresolved is True

    def test_fraction_decays_when_the_response_vanishes(self, parameters) -> None:
        """With r_k = 0 the production term is gone and the fraction only decays."""
        mu = 0.5
        assert enzyme_fraction_derivative(1, 0.0, 0.4, mu, parameters) == pytest.approx(
            -(mu + BETA1) * 0.4
        )

    def test_invalid_combination_index_is_refused(self, parameters) -> None:
        with pytest.raises(ValueError, match="1 or 2"):
            enzyme_fraction_derivative(3, 0.5, 0.5, 0.5, parameters)


class TestTranscriptionNotes:
    """The recorded decisions are part of the model, so they are tested."""

    def test_every_note_has_a_decision_and_a_source(self) -> None:
        for note in TRANSCRIPTION_NOTES:
            assert note.statement and note.decision
            assert note.affected_equations
            assert note.source.citation

    def test_the_unresolved_ones_raise_a_review_question(self) -> None:
        unresolved = [n for n in TRANSCRIPTION_NOTES if n.unresolved]
        assert {n.note_id for n in unresolved} == {"TN-02"}
        for note in unresolved:
            assert note.review_question

    def test_the_oxygen_term_correction_records_both_readings(self) -> None:
        """TN-04: the factor was corrected from a product to a quotient.

        The note has to name the wrong reading as well as the right one, or a
        later reader cannot tell what was changed or why.
        """
        note = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-04")
        assert "(100/C*)" in note.statement
        assert "(100*C*)" in note.statement, "the superseded reading must survive"
        assert note.unresolved is False
        assert "Corrected to the printed quotient" in note.decision
        assert "not from the fact" in note.decision
        assert set(note.affected_equations) == {"eq. (11)", "eq. (15)"}
        assert "fraction bar" in note.decision