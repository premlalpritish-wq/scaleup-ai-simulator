"""The printed model, evaluated: initial values, branches, integration, units."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from lin2000 import model, parameters as params, units
from lin2000.validate import check_parameters


# --------------------------------------------------------------------------- #
# initial values and the parameter table
# --------------------------------------------------------------------------- #


def test_mu_max_is_the_printed_formula():
    p = check_parameters()
    assert p.mu_max == pytest.approx((p.qSmax - p.qm) * p.YXS_ox)


def test_rS0_and_rO0_are_the_printed_initial_values():
    p = check_parameters()
    assert p.rS0 == pytest.approx(p.cS * p.mu_max / (p.qESd + p.mu_max))
    assert p.rO0 == pytest.approx(p.cO * p.mu_max / (p.qEOd + p.mu_max))


def test_qScap_equals_qSmax_at_the_initial_state():
    p = check_parameters()
    s = model.subsidiary(p.initial_state(), p)
    assert s.qScap == pytest.approx(p.qSmax)


def test_the_paper_prints_no_value_for_the_five_required_inputs():
    for name in model.REQUIRED_RUN_INPUTS:
        assert name in params.UNVALUED_RUN_INPUTS
    with pytest.raises(model.MissingRunInput):
        model.SimulationParameters.from_culture(
            "w3110_exponential", cS=None, cO=1.0, kLa=60.0, DOT_star=100.0,
            H=14000.0,
        )


def test_the_two_cultures_carry_the_two_printed_columns():
    a = model.SimulationParameters.from_culture(
        "w3110_exponential", cS=1, cO=1, kLa=1, DOT_star=100, H=14000)
    b = model.SimulationParameters.from_culture(
        "rb791_constant", cS=1, cO=1, kLa=1, DOT_star=100, H=14000)
    assert (a.qSmax, a.V0, a.S0) == (1.86, 7.0, 0.5)
    assert (b.qSmax, b.V0, b.S0) == (1.5, 4.0, 5.0)


def test_the_constant_capacity_variant_uses_the_footnote_c_value():
    p = model.SimulationParameters.from_culture(
        "w3110_exponential", cS=1, cO=1, kLa=1, DOT_star=100, H=14000,
        variant="constant_capacity",
    )
    assert p.qESd == 0.0 and p.qEOd == 0.0 and p.YES_X == 0.0 and p.YEO_X == 0.0


def test_an_unknown_culture_or_variant_is_refused():
    with pytest.raises(model.ModelError):
        model.SimulationParameters.from_culture(
            "k12", cS=1, cO=1, kLa=1, DOT_star=100, H=14000)
    with pytest.raises(model.ModelError):
        model.SimulationParameters.from_culture(
            "w3110_exponential", cS=1, cO=1, kLa=1, DOT_star=100, H=14000,
            variant="imagined")


# --------------------------------------------------------------------------- #
# the subsidiary chain and its two printed correction branches
# --------------------------------------------------------------------------- #


def test_the_worked_initial_state_matches_a_by_hand_evaluation():
    """W3110 with cS=cO=1: the printed chain gives mu = 0.45360 1/h."""
    p = check_parameters()
    s = model.subsidiary(p.initial_state(), p)
    assert s.qScap == pytest.approx(1.86, abs=1e-9)
    assert s.qOcap == pytest.approx(0.607, abs=1e-9)
    assert s.mu == pytest.approx(0.45360, abs=5e-5)


def test_the_oxygen_capacity_branch_clamps_qOs_to_qOcap():
    p = check_parameters()
    s = model.subsidiary(p.initial_state(), p)
    assert s.oxygen_capacity_clamped
    assert s.qOs == pytest.approx(p.qOmax, abs=1e-12)
    assert s.qSoxen == pytest.approx(p.qOmax / p.YOS, abs=1e-12)


def test_the_maintenance_floor_branch_collapses_qSox_to_qmr():
    p = replace(check_parameters(), qOmax=0.01)
    s = model.subsidiary(p.initial_state(), p)
    assert s.maintenance_reduced_below_qm
    assert s.qmr == pytest.approx(s.qSox)
    assert s.qSoxen == pytest.approx(s.qSox)
    assert s.qSoxan == pytest.approx(0.0, abs=1e-12)


def test_mu_is_the_printed_sum_of_the_three_contributions():
    p = check_parameters()
    state = replace(p.initial_state(), A=0.5)
    s = model.subsidiary(state, p)
    expected = (
        (s.qSox - p.qm) * p.YXS_ox + s.qSof * p.YXS_of + s.qAc * p.YXA
    )
    assert s.mu == pytest.approx(expected)


def test_qO_is_the_printed_sum():
    p = check_parameters()
    s = model.subsidiary(replace(p.initial_state(), A=0.5), p)
    assert s.qO == pytest.approx(s.qOs + s.qAcen * p.YOA)


# --------------------------------------------------------------------------- #
# the printed differential equations
# --------------------------------------------------------------------------- #


def test_volume_derivative_is_the_feed_rate():
    p = check_parameters()
    feed = model.feed_constant(0.1)
    d = model.derivatives(p.initial_state(), p, feed, 0.0)
    assert d.V == pytest.approx(0.1)


def test_substrate_derivative_matches_the_printed_expression():
    p = check_parameters()
    feed = model.feed_constant(0.1)
    state = p.initial_state()
    s = model.subsidiary(state, p)
    d = model.derivatives(state, p, feed, 0.0)
    expected = -(0.1 / state.V) * (state.S - p.Si) - s.qS * state.X
    assert d.S == pytest.approx(expected)


def test_oxygen_derivative_matches_the_printed_expression():
    p = check_parameters()
    state = replace(p.initial_state(), DOT=50.0)
    s = model.subsidiary(state, p)
    d = model.derivatives(state, p, model.feed_constant(0.1), 0.0)
    assert d.DOT == pytest.approx(
        p.kLa * (p.DOT_star - state.DOT) - s.qO * state.X * p.H
    )


def test_enzyme_derivatives_match_the_printed_equations():
    p = check_parameters()
    state = p.initial_state()
    s = model.subsidiary(state, p)
    d = model.derivatives(state, p, model.feed_constant(0.1), 0.0)
    assert d.rS == pytest.approx(p.YES_X * s.mu - state.rS * (p.qESd + s.mu))
    assert d.rO == pytest.approx(p.YEO_X * s.mu - state.rO * (p.qEOd + s.mu))
