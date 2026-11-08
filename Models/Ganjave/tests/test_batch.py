"""Batch balances: eq. (8)-(11).

Covers GJ-06 (biomass balance), GJ-07 (substrate balances, including the
separate contribution of each combination) and GJ-08 (the oxygen balance, its
two halves, and the percentage semantics).

Expected values are written out as arithmetic on the printed Table 2 numbers,
not produced by the implementation.
"""

from __future__ import annotations

import math

import pytest

from schemas.state import State
from models.batch import (
    batch_derivative,
    dDO_dt,
    dS1_dt,
    dS2_dt,
    dX_dt,
    oxygen_consumption_term,
    oxygen_transfer_term,
)
from models.kinetics import growth_terms

MUM1, MUM2 = 1.497, 0.834
K11, K12, K22 = 0.131, 36.154, 1.001
KO1, KO2 = 0.326, 8.944
Y11, Y12, Y22, YO1, YO2 = 0.440, 0.881, 0.254, 0.925, 1.219
KLA, C_STAR = 133.0, 0.0075

#: The fixed hand-calculation state: X=2, S1=4, S2=10, DO=50, e1=0.3, e2=0.6.
_X, _S1, _S2, _DO, _E1, _E2 = 2.0, 4.0, 10.0, 50.0, 0.30, 0.60


def hand_r1() -> float:
    return (_S1 / (K11 + _S1)) * (_S2 / (K12 + _S2)) * (_DO / (KO1 + _DO))


def hand_r2() -> float:
    return (_S2 / (K22 + _S2)) * (_DO / (KO2 + _DO))


def hand_mu() -> tuple[float, float, float]:
    r1, r2 = hand_r1(), hand_r2()
    mu1 = MUM1 * _E1 * r1
    mu2 = MUM2 * _E2 * r2
    return mu1, mu2, mu1 + mu2


class TestBiomassBalance:
    """GJ-06: dX/dt = mu*X."""

    def test_matches_hand_calculation(self, fixed_state, parameters) -> None:
        mu1, mu2, mu = hand_mu()
        assert dX_dt(fixed_state, parameters) == pytest.approx(mu * _X)
        assert mu == pytest.approx(mu1 + mu2)

    def test_is_proportional_to_biomass(self, fixed_state, parameters) -> None:
        base = dX_dt(fixed_state, parameters)
        doubled = dX_dt(
            State(t=0.0, X=2 * _X, S1=_S1, S2=_S2, DO=_DO, e1=_E1, e2=_E2, V=0.1),
            parameters,
        )
        assert doubled == pytest.approx(2 * base)

    def test_is_zero_without_growth(self, parameters) -> None:
        no_growth = State(t=0.0, X=_X, S1=0.0, S2=0.0, DO=_DO, e1=_E1, e2=_E2, V=0.1)
        assert dX_dt(no_growth, parameters) == 0.0


class TestSubstrateBalances:
    """GJ-07: each substrate derivative, with both consumption routes for S2."""

    def test_glycerol_is_consumed_only_through_combination_1(self, fixed_state, parameters) -> None:
        mu1, _mu2, _mu = hand_mu()
        expected = -(mu1 / Y11) * _X
        assert dS1_dt(fixed_state, parameters) == pytest.approx(expected)
        # and it is strictly negative while there is glycerol and growth
        assert dS1_dt(fixed_state, parameters) < 0.0

    def test_glycerol_derivative_has_no_combination_2_term(self, fixed_state, parameters) -> None:
        """eq. (9) prints only mu1; a Y22 term would be a transcription error."""
        mu1, mu2, _mu = hand_mu()
        got = dS1_dt(fixed_state, parameters)
        with_bogus_combination_2 = -(mu1 / Y11 + mu2 / Y22) * _X
        assert got != pytest.approx(with_bogus_combination_2)

    def test_complex_substrate_sums_both_combinations(self, fixed_state, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        expected = -(mu1 / Y12 + mu2 / Y22) * _X
        assert dS2_dt(fixed_state, parameters) == pytest.approx(expected)

    def test_complex_substrate_contributions_are_separately_recoverable(
        self, fixed_state, parameters
    ) -> None:
        """Splitting the printed sum must give exactly the total."""
        mu1, mu2, _mu = hand_mu()
        via_combination_1 = -(mu1 / Y12) * _X
        via_combination_2 = -(mu2 / Y22) * _X
        total = via_combination_1 + via_combination_2
        assert total == pytest.approx(dS2_dt(fixed_state, parameters))
        assert via_combination_2 != 0.0, "combination 2 must contribute"

    def test_both_substrates_are_non_increasing_in_batch(self, fixed_state, parameters) -> None:
        assert dS1_dt(fixed_state, parameters) <= 0.0
        assert dS2_dt(fixed_state, parameters) <= 0.0

    def test_substrate_is_not_consumed_without_substrate(self, parameters) -> None:
        """No growth, no consumption: a zero substrate stays at zero."""
        state = State(t=0.0, X=_X, S1=0.0, S2=0.0, DO=_DO, e1=_E1, e2=_E2, V=0.1)
        assert dS1_dt(state, parameters) == 0.0
        assert dS2_dt(state, parameters) == 0.0


class TestOxygenBalance:
    """GJ-08: transfer and consumption checked independently."""

    def test_transfer_term_is_kla_times_the_gap_to_saturation(self, parameters) -> None:
        assert oxygen_transfer_term(50.0, parameters) == pytest.approx(KLA * (100.0 - 50.0))
        assert oxygen_transfer_term(100.0, parameters) == 0.0
        assert oxygen_transfer_term(0.0, parameters) == pytest.approx(KLA * 100.0)

    def test_transfer_is_positive_below_saturation_and_negative_above(self, parameters) -> None:
        assert oxygen_transfer_term(10.0, parameters) > 0.0
        assert oxygen_transfer_term(100.0, parameters) == 0.0
        # above saturation the printed term goes negative, as eq. (11) writes it
        assert oxygen_transfer_term(120.0, parameters) < 0.0

    def test_consumption_term_is_the_printed_quotient_100_over_c_star(self, parameters) -> None:
        """eq. (11) prints ``(100/C*)*(mu1/Yo1 + mu2/Yo2)*X`` -- a quotient.

        The arithmetic is written out on the printed C* = 0.0075 g/L, so the
        expected value is derived from the paper and not from the code.
        """
        mu1, mu2, _mu = hand_mu()
        uptake = mu1 / YO1 + mu2 / YO2          # g O2 / (g biomass.h)
        our = uptake * _X                      # g O2 / (L.h)
        expected = (100.0 / C_STAR) * our      # %/h
        assert oxygen_consumption_term(mu1, mu2, _X, parameters) == pytest.approx(expected)

    def test_consumption_is_not_the_product_reading(self, parameters) -> None:
        """The transposed factor is a different number, by construction.

        Pins the distinction that TN-04 records: the two readings differ by
        (C*)^-2, so a test cannot pass by accepting either.
        """
        mu1, mu2, _mu = hand_mu()
        quotient = oxygen_consumption_term(mu1, mu2, _X, parameters)
        product = (100.0 * C_STAR) * (mu1 / YO1 + mu2 / YO2) * _X
        assert quotient != pytest.approx(product)
        assert quotient / product == pytest.approx(1.0 / (C_STAR * C_STAR))

    def test_consumption_sums_both_oxygen_yields(self, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        via_1 = (100.0 / C_STAR) * (mu1 / YO1) * _X
        via_2 = (100.0 / C_STAR) * (mu2 / YO2) * _X
        assert via_1 + via_2 == pytest.approx(
            oxygen_consumption_term(mu1, mu2, _X, parameters)
        )

    def test_derivative_is_transfer_minus_consumption(self, fixed_state, parameters) -> None:
        mu1, mu2, _mu = hand_mu()
        expected = (
            KLA * (100.0 - _DO)
            - (100.0 / C_STAR) * (mu1 / YO1 + mu2 / YO2) * _X
        )
        assert dDO_dt(fixed_state, parameters) == pytest.approx(expected)

    def test_dissolved_oxygen_is_a_percentage_not_a_concentration(self, parameters) -> None:
        """100 % is the saturation reading, i.e. C* = 0.0075 g/L."""
        from schemas.units import do_percentage_to_concentration

        assert do_percentage_to_concentration(100.0, C_STAR) == pytest.approx(C_STAR)
        assert do_percentage_to_concentration(50.0, C_STAR) == pytest.approx(0.00375)

    def test_consumption_can_exceed_transfer_at_a_growing_culture(self, parameters) -> None:
        """At this state the uptake term is the larger one.

        Under the printed quotient the oxygen balance is genuinely
        consumption-limited at this biomass, which is what lets dissolved
        oxygen fall below saturation. Under the product reading it never could.
        """
        transfer = oxygen_transfer_term(50.0, parameters)
        mu1, mu2, _mu = hand_mu()
        consumption = oxygen_consumption_term(mu1, mu2, _X, parameters)
        assert consumption > transfer

    def test_non_positive_c_star_is_refused(self, parameters) -> None:
        """The conversion to a percentage is undefined for C* <= 0."""
        broken = parameters.with_overrides({"C_star": 0.0}, reason="degenerate case test")
        with pytest.raises(ValueError, match="strictly positive"):
            oxygen_consumption_term(0.1, 0.1, 1.0, broken)


class TestBatchDerivativeVector:
    """The assembled right-hand side, in the state-vector order."""

    def test_matches_the_component_functions(self, fixed_state, parameters) -> None:
        d = batch_derivative(fixed_state, parameters)
        assert len(d) == 7
        assert d[0] == pytest.approx(dX_dt(fixed_state, parameters))
        assert d[1] == pytest.approx(dS1_dt(fixed_state, parameters))
        assert d[2] == pytest.approx(dS2_dt(fixed_state, parameters))
        assert d[3] == pytest.approx(dDO_dt(fixed_state, parameters))

    def test_enzyme_terms_are_positions_four_and_five(self, fixed_state, parameters) -> None:
        d = batch_derivative(fixed_state, parameters)
        terms = growth_terms(_S1, _S2, _DO, _E1, _E2, parameters)
        assert d[4] == pytest.approx(terms["de1"])
        assert d[5] == pytest.approx(terms["de2"])

    def test_volume_derivative_is_exactly_zero_in_batch(self, fixed_state, parameters) -> None:
        """Batch mode has no feed: there is nothing to add volume."""
        assert batch_derivative(fixed_state, parameters)[6] == 0.0

    def test_every_component_is_finite(self, fixed_state, parameters) -> None:
        for value in batch_derivative(fixed_state, parameters):
            assert math.isfinite(value)

    def test_vector_order_matches_the_state_order(self, fixed_state, parameters) -> None:
        """Guards the round trip: a derivative tuple must land on its own state."""
        d = batch_derivative(fixed_state, parameters)
        moved = type(fixed_state).from_vector(0.0, d)
        assert moved.X == pytest.approx(d[0])
        assert moved.S1 == pytest.approx(d[1])
        assert moved.S2 == pytest.approx(d[2])
        assert moved.DO == pytest.approx(d[3])
        assert moved.e1 == pytest.approx(d[4])
        assert moved.e2 == pytest.approx(d[5])
        assert moved.V == pytest.approx(d[6])