"""Fed-batch balances: eq. (12)-(16).

Covers GJ-09 (feed dilution), GJ-10 (substrate input), GJ-11 (volume balance)
and GJ-12 (batch and fed-batch are different models, not one expression with a
switch).
"""

from __future__ import annotations

import math

import pytest

from models.batch import batch_derivative
from models.fed_batch import (
    FeedDomainError,
    FeedError,
    FeedProgram,
    dDO_dt,
    dS1_dt,
    dS2_dt,
    dV_dt,
    dX_dt,
    dilution_rate,
    fed_batch_derivative,
)
from models.simulation import expected_final_volume, simulate
from schemas.state import State

MUM1, MUM2 = 1.497, 0.834
K11, K12, K22 = 0.131, 36.154, 1.001
KO1, KO2 = 0.326, 8.944
Y11, Y12, Y22, YO1, YO2 = 0.440, 0.881, 0.254, 0.925, 1.219
KLA, C_STAR = 133.0, 0.0075

_X, _S1, _S2, _DO, _E1, _E2, _V = 2.0, 4.0, 10.0, 50.0, 0.30, 0.60, 0.1
_FLOW = 1.0e-3                      # 1 mL/h in L/h
_FEED = FeedProgram(S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=_FLOW)


def hand_terms() -> tuple[float, float, float]:
    r1 = (_S1 / (K11 + _S1)) * (_S2 / (K12 + _S2)) * (_DO / (KO1 + _DO))
    r2 = (_S2 / (K22 + _S2)) * (_DO / (KO2 + _DO))
    mu1 = MUM1 * _E1 * r1
    mu2 = MUM2 * _E2 * r2
    return mu1, mu2, mu1 + mu2


@pytest.fixture()
def fed_state() -> State:
    return State(t=0.0, X=_X, S1=_S1, S2=_S2, DO=_DO, e1=_E1, e2=_E2, V=_V)


class TestDilution:
    """GJ-09: the feed dilution contribution is negative."""

    def test_dilution_rate_is_flow_over_volume(self) -> None:
        assert dilution_rate(_FLOW, _V) == pytest.approx(_FLOW / _V)

    def test_dilution_rate_needs_a_positive_volume(self) -> None:
        with pytest.raises(FeedDomainError, match="positive volume"):
            dilution_rate(_FLOW, 0.0)

    def test_dilution_contribution_to_biomass_is_negative(self, fed_state, parameters) -> None:
        """dX/dt = (mu - F/V)*X, so the dilution part is -(F/V)*X <= 0."""
        mu1, mu2, mu = hand_terms()
        dilution_contribution = -dilution_rate(_FLOW, _V) * _X
        assert dilution_contribution < 0.0
        expected = (mu - dilution_rate(_FLOW, _V)) * _X
        assert dX_dt(fed_state, _FLOW, parameters) == pytest.approx(expected)

    def test_dilution_dominates_when_growth_is_slow(self, fed_state, parameters) -> None:
        """With a 10 h dilution time constant, F/V = 1e-2 h^-1 at V = 0.1 L."""
        assert dilution_rate(_FLOW, _V) == pytest.approx(0.01)
        assert dilution_rate(_FLOW, _V) > 0.0

    def test_zero_flow_means_no_dilution(self, fed_state, parameters) -> None:
        assert dX_dt(fed_state, 0.0, parameters) == pytest.approx(hand_terms()[2] * _X)


class TestSubstrateInput:
    """GJ-10: input from feed concentration, flow rate and culture volume."""

    def test_glycerol_input_matches_the_printed_form(self, fed_state, parameters) -> None:
        mu1, _mu2, _mu = hand_terms()
        expected = (175.0 - _S1) * dilution_rate(_FLOW, _V) - (mu1 / Y11) * _X
        assert dS1_dt(fed_state, _FEED, _FLOW, parameters) == pytest.approx(expected)

    def test_complex_substrate_input_matches_the_printed_form(
        self, fed_state, parameters
    ) -> None:
        mu1, mu2, _mu = hand_terms()
        expected = (245.0 - _S2) * dilution_rate(_FLOW, _V) - (
            mu1 / Y12 + mu2 / Y22
        ) * _X
        assert dS2_dt(fed_state, _FEED, _FLOW, parameters) == pytest.approx(expected)

    def test_input_is_zero_when_the_culture_matches_the_feed(
        self, parameters
    ) -> None:
        """When S1 equals S10 the (S10 - S1) term vanishes; only consumption is left.

        The consumption has to be evaluated at the *matched* state, because
        raising S1 to the feed concentration also raises r1 and therefore mu1.
        """
        matched = State(
            t=0.0, X=_X, S1=175.0, S2=245.0, DO=_DO, e1=_E1, e2=_E2, V=_V
        )
        r1 = (matched.S1 / (K11 + matched.S1)) * (matched.S2 / (K12 + matched.S2)) * (
            matched.DO / (KO1 + matched.DO)
        )
        mu1 = MUM1 * _E1 * r1
        expected = -(mu1 / Y11) * _X
        assert (175.0 - matched.S1) == 0.0
        assert dS1_dt(matched, _FEED, _FLOW, parameters) == pytest.approx(expected)

    def test_concentrated_feed_raises_the_substrate(self, parameters) -> None:
        """A feed more concentrated than the culture must add substrate."""
        state = State(t=0.0, X=1e-6, S1=0.0, S2=0.0, DO=_DO, e1=_E1, e2=_E2, V=_V)
        assert dS1_dt(state, _FEED, _FLOW, parameters) > 0.0
        assert dS2_dt(state, _FEED, _FLOW, parameters) > 0.0

    def test_percent_recipe_conversion_is_explicit(self) -> None:
        """1 % w/v = 10 g/L; 1 mL/h = 1e-3 L/h (TN-05)."""
        feed = FeedProgram.from_recipe(17.5, 24.5, 0.72)
        assert feed.S10_g_per_L == pytest.approx(175.0)
        assert feed.S20_g_per_L == pytest.approx(245.0)
        assert feed.flow_L_per_h == pytest.approx(0.72e-3)


class TestOxygenAndVolume:
    """GJ-11 and the oxygen dilution of eq. (15)."""

    def test_oxygen_dilution_term_is_minus_do_times_f_over_v(self, fed_state, parameters) -> None:
        mu1, mu2, _mu = hand_terms()
        expected = (
            KLA * (100.0 - _DO)
            - _DO * dilution_rate(_FLOW, _V)
            - (100.0 / C_STAR) * (mu1 / YO1 + mu2 / YO2) * _X
        )
        assert dDO_dt(fed_state, _FEED, _FLOW, parameters) == pytest.approx(expected)

    def test_oxygen_dilution_is_non_positive(self, fed_state, parameters) -> None:
        with_feed = dDO_dt(fed_state, _FEED, _FLOW, parameters)
        without_feed = dDO_dt(fed_state, _FEED, 0.0, parameters)
        assert with_feed <= without_feed

    def test_volume_derivative_is_the_flow_rate(self) -> None:
        assert dV_dt(_FEED, _FLOW) == _FLOW
        assert dV_dt(_FEED, 0.0) == 0.0

    def test_constant_feed_gives_the_analytic_volume(self) -> None:
        for duration in (6.0, 12.0, 24.0):
            expected = 0.1 + 7.2e-4 * (duration - 6.0)
            assert expected_final_volume(0.1, 7.2e-4, duration, start_time_h=6.0) == (
                pytest.approx(expected)
            )

    def test_volume_before_feeding_starts_is_unchanged(self) -> None:
        for duration in (1.0, 4.0, 6.0):
            assert expected_final_volume(
                0.1, 7.2e-4, duration, start_time_h=6.0
            ) == pytest.approx(0.1)

    def test_negative_feed_duration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            expected_final_volume(0.1, -1.0, 6.0)


class TestBatchVersusFedBatch:
    """GJ-12: the two modes are different models."""

    def test_batch_has_no_dilution_and_fed_batch_does(self, fed_state, parameters) -> None:
        batch = batch_derivative(fed_state, parameters)
        fed = fed_batch_derivative(fed_state, _FEED, parameters, t=10.0)
        assert batch[0] == pytest.approx(hand_terms()[2] * _X)
        assert fed[0] < batch[0], "feeding must dilute the biomass"

    def test_batch_volume_is_constant_and_fed_volume_grows(self, fed_state, parameters) -> None:
        batch = batch_derivative(fed_state, parameters)
        fed = fed_batch_derivative(fed_state, _FEED, parameters, t=10.0)
        assert batch[6] == 0.0
        assert fed[6] == pytest.approx(_FLOW)

    def test_substrate_terms_differ_between_modes(self, fed_state, parameters) -> None:
        batch = batch_derivative(fed_state, parameters)
        fed = fed_batch_derivative(fed_state, _FEED, parameters, t=10.0)
        assert batch[1] != pytest.approx(fed[1])
        assert batch[2] != pytest.approx(fed[2])

    def test_feed_before_its_start_time_is_inactive(self, fed_state, parameters) -> None:
        """A pump that has not started yet contributes nothing."""
        late = FeedProgram(
            S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=_FLOW, start_time_h=12.0
        )
        before = fed_batch_derivative(fed_state, late, parameters, t=1.0)
        assert before[6] == 0.0
        assert before[0] == pytest.approx(batch_derivative(fed_state, parameters)[0])

    def test_zero_flow_is_a_stopped_pump_not_a_missing_one(self) -> None:
        stopped = FeedProgram(S10_g_per_L=175.0, S20_g_per_L=245.0, flow_L_per_h=0.0)
        assert stopped.is_feeding(100.0) is False
        assert stopped.flow_at(100.0) == 0.0


class TestFeedProgramValidation:
    def test_negative_feed_concentration_is_refused(self) -> None:
        with pytest.raises(FeedError, match="non-negative"):
            FeedProgram(S10_g_per_L=-1.0, S20_g_per_L=1.0, flow_L_per_h=1e-3)

    def test_negative_flow_is_refused(self) -> None:
        with pytest.raises(FeedError, match="non-negative"):
            FeedProgram(S10_g_per_L=1.0, S20_g_per_L=1.0, flow_L_per_h=-1e-3)

    def test_negative_start_time_is_refused(self) -> None:
        with pytest.raises(FeedError, match="non-negative"):
            FeedProgram(S10_g_per_L=1.0, S20_g_per_L=1.0, flow_L_per_h=1e-3,
                        start_time_h=-1.0)

    def test_recipe_and_explicit_construction_agree(self) -> None:
        """The two routes differ only by float representation of the conversions.

        ``0.78 * 1e-3`` and the literal ``0.78e-3`` are not bit-identical, so the
        comparison is numerical. Everything a run depends on is recorded with
        the converted value, so this difference cannot make two runs disagree
        for a reason a reader cannot see.
        """
        a = FeedProgram.from_recipe(20.0, 30.0, 0.78, start_time_h=6.0)
        b = FeedProgram(S10_g_per_L=200.0, S20_g_per_L=300.0, flow_L_per_h=0.78e-3,
                        start_time_h=6.0)
        assert a.S10_g_per_L == pytest.approx(b.S10_g_per_L, rel=0.0, abs=1e-12)
        assert a.S20_g_per_L == pytest.approx(b.S20_g_per_L, rel=0.0, abs=1e-12)
        assert a.flow_L_per_h == pytest.approx(b.flow_L_per_h, rel=1e-15)
        assert a.start_time_h == b.start_time_h


class TestFedBatchSimulation:
    """An integration-level check that the balances behave as printed."""

    def test_volume_matches_the_closed_form(self, fed_batch_conditions) -> None:
        """Numerically within the solver's stated tolerance, not bit-exact.

        ``V`` has no closed-form difficulty, so any larger discrepancy than the
        integration tolerance would be an integration fault rather than an
        expected rounding.
        """
        feed = FeedProgram.from_recipe(17.5, 24.5, 0.72, start_time_h=6.0)
        result = simulate(
            initial_conditions=fed_batch_conditions, duration_h=12.0,
            mode="fed_batch", feed=feed,
        )
        assert result.ok, [d.message for d in result.diagnostics if d.severity.value == "error"]
        expected = expected_final_volume(0.1, 7.2e-4, 12.0, start_time_h=6.0)
        assert result.final_state.V == pytest.approx(expected, rel=1e-6)

    def test_tighter_tolerance_closes_on_the_closed_form(self, fed_batch_conditions) -> None:
        """Level-2 numerical validation: the error falls with the tolerance."""
        from models.solver import SolverConfig

        feed = FeedProgram.from_recipe(17.5, 24.5, 0.72, start_time_h=6.0)
        expected = expected_final_volume(0.1, 7.2e-4, 12.0, start_time_h=6.0)
        errors = {}
        for rtol in (1e-4, 1e-6, 1e-8):
            result = simulate(
                initial_conditions=fed_batch_conditions, duration_h=12.0,
                mode="fed_batch", feed=feed,
                solver=SolverConfig(rtol=rtol, atol=rtol * 1e-3),
            )
            assert result.ok, [d.message for d in result.diagnostics if d.severity.value == "error"]
            errors[rtol] = abs(result.final_state.V - expected)
        assert errors[1e-8] < errors[1e-6] < errors[1e-4]

    def test_biomass_grows_under_feeding(self, fed_batch_conditions) -> None:
        feed = FeedProgram.from_recipe(17.5, 24.5, 0.72, start_time_h=6.0)
        result = simulate(
            initial_conditions=fed_batch_conditions, duration_h=10.0,
            mode="fed_batch", feed=feed,
        )
        assert result.ok
        assert result.final_state.X > result.states[0].X
        assert all(math.isfinite(s.X) for s in result.states)