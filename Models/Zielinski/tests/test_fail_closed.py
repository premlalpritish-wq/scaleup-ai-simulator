"""Fail-closed behaviour and the observed/predicted boundary.

These are the tests that stop the model from looking more capable than it is.
"""

from __future__ import annotations

import pytest

from scaleup_ai import ExecutionMode, Provenance, Quantity

from models.zielinski_2019 import predict


# --------------------------------------------------------------------------- #
# evidence replay must not look predictive
# --------------------------------------------------------------------------- #


def test_evidence_replay_produces_no_predictions(replay):
    assert replay.summary.predicted_values == 0
    assert replay.summary.to_dict()["graph_is_predictive"] is False


def test_evidence_replay_never_marks_a_reported_value_as_computed(replay, graph):
    """A replayed number is tagged observed_reference, never re-emitted as computed."""
    for nr in replay.node_results:
        for q in nr.computed:
            assert q.provenance is Provenance.DERIVED, q.quantity_id
            assert q.basis.value == "computed"
    # and the same quantity id is never simultaneously reported and computed
    computed_ids = {
        (nr.node_id, q.quantity_id)
        for nr in replay.node_results
        for q in nr.computed
    }
    for location, qid, q in graph.iter_quantities():
        if q.provenance is Provenance.REPORTED and (location.split(":")[1], qid) in computed_ids:
            pytest.fail(f"{location}:{qid} is reported but was re-emitted as computed")


def test_reported_values_keep_observed_basis_in_replay(graph):
    from scaleup_ai import Provenance as P

    for _loc, _qid, q in graph.iter_quantities():
        if q.provenance is P.REPORTED:
            assert q.basis.value == "observed_reference"


def test_predictive_mode_without_inputs_computes_nothing(engine):
    run = engine.run(mode=ExecutionMode.PREDICTIVE)
    assert run.summary.computed_values == 0
    assert run.summary.predicted_values == 0
    assert run.summary.unresolved_targets > 0


# --------------------------------------------------------------------------- #
# predictive mode with declared inputs
# --------------------------------------------------------------------------- #


def test_predictive_mode_computes_only_from_declared_inputs(engine):
    inputs = {
        "stream:S03_wet_biomass:wet_biomass_total": Quantity(
            "wet_biomass_total", "wet biomass", Provenance.ASSUMED, 560.0, "g"
        ),
        "node:N01:starting_medium_volume": Quantity(
            "starting_medium_volume", "volume", Provenance.ASSUMED, 10.0, "L"
        ),
    }
    run = engine.run(mode=ExecutionMode.PREDICTIVE, inputs=inputs)
    assert run.summary.predicted_values == 1
    assert run.summary.to_dict()["graph_is_predictive"] is True
    computed = run.node("N02").computed
    assert computed[0].quantity_id == "wet_biomass_g_per_L"
    assert computed[0].value == pytest.approx(56.0)
    # the paper's own 4 L volume must not have leaked into the prediction
    assert run.node("N02").traces[0].input_values["volume"]["value"] == 10.0


def test_predictive_mode_does_not_see_reported_values(engine):
    run = engine.run(mode=ExecutionMode.PREDICTIVE)
    for nr in run.node_results:
        for q in nr.computed:
            assert q.provenance is Provenance.DERIVED


# --------------------------------------------------------------------------- #
# fail-closed queries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "target,expected_models",
    [
        ("node:N01:od600_from_inputs", "kinetics.growth_ode"),
        ("node:N01:wet_biomass_from_inputs", "kinetics.growth_ode"),
        ("node:N01:specific_growth_rate", "kinetics.growth_ode"),
        ("node:N01:dissolved_oxygen", "transfer.oxygen_kla"),
        ("node:N05:refolding_yield_predictive", "folding.renaturation_kinetics"),
        ("node:N05:refolding_time_predictive", "folding.renaturation_kinetics"),
        ("node:N15:au_to_protein_mass_factor", "calibration.au_to_mass"),
        ("node:N15:insulin_mass_from_au", "calibration.au_to_mass"),
        ("node:N15:final_activity_from_au", "activity.iu_from_au"),
        ("stream:S16_g25_fraction:insulin_mass", "calibration.au_to_mass"),
    ],
)
def test_unsupported_predictions_fail_closed_with_a_stated_dependency(engine, target, expected_models):
    r = predict(target, engine)
    assert r.is_resolved is False
    assert r.quantity is None
    assert r.unresolved is not None
    assert r.unresolved.target == target
    assert expected_models in r.unresolved.missing_models
    assert r.unresolved.reason


def test_fail_closed_result_names_the_missing_inputs(engine):
    r = predict("node:N01:od600_from_inputs", engine)
    from scaleup_ai.equations import MISSING_MODELS

    detail = MISSING_MODELS["kinetics.growth_ode"]
    assert any("specific growth rate" in i for i in detail.missing_inputs)
    assert "kinetics.growth_ode" in r.unresolved.reason
    for missing in detail.missing_inputs:
        assert missing in r.unresolved.reason


def test_fail_closed_never_returns_a_silent_zero(engine):
    for target in ("node:N15:insulin_mass_from_au", "node:N01:od600_from_inputs"):
        r = predict(target, engine)
        assert r.quantity is None
        assert r.unresolved is not None


# --------------------------------------------------------------------------- #
# range guard: an interval is not silently collapsed
# --------------------------------------------------------------------------- #


def test_equation_needing_a_point_value_refuses_a_reported_range(engine):
    """A quantity reported as an interval must not be silently collapsed.

    A purpose-built graph is used so the ranged quantity's unit (mL) is directly
    convertible to the equation's declared input unit; otherwise the run would
    fail on a unit mismatch and never reach the range guard.
    """
    from scaleup_ai.engine import EquationBinding, ExecutionEngine, Ref, node_loc
    from scaleup_ai.process import (
        MaterialStream,
        OperationKind,
        ProcessGraph,
        ProcessNode,
        StreamKind,
    )
    from models.source import ev

    g = ProcessGraph("range-guard", "range guard", "zielinski2019")
    s = MaterialStream("S", "s", StreamKind.INCLUSION_BODIES, produced_by="N1", consumed_by="N2")
    s.put(Quantity("vol", "volume", Provenance.REPORTED, None, "mL",
                   value_range=(10.0, 20.0), evidence=(ev(3, section="2.10"),)))
    g.add_stream(s)
    g.add_node(ProcessNode("N1", 1, "a", OperationKind.HARVEST, output_streams=("S",)))
    g.add_node(ProcessNode("N2", 2, "b", OperationKind.CHROMATOGRAPHY, input_streams=("S",)))

    binding = EquationBinding(
        binding_id="TEST-RANGE", node_id="N2",
        equation_id="accounting.stock_volume_for_target_concentration",
        inputs={
            "target_concentration": Ref(node_loc("N1"), "target"),
            "stock_concentration": Ref(node_loc("N1"), "stock"),
            "final_volume": Ref("stream:S", "vol"),
        },
        output_quantity_id="bogus", output_location=node_loc("N2"),
    )
    node = g.node("N1")
    node.operating_conditions["target"] = Quantity("target", "t", Provenance.REPORTED, 30.0, "mM")
    node.operating_conditions["stock"] = Quantity("stock", "s", Provenance.REPORTED, 1.0, "mM")

    run = ExecutionEngine(g, bindings=[binding]).run(mode=ExecutionMode.EVIDENCE_REPLAY)
    assert run.node("N2").computed == []
    reason = run.unresolved[0].reason
    assert "range" in reason
    assert "(10.0, 20.0)" in reason


# --------------------------------------------------------------------------- #
# deliberately absent models
# --------------------------------------------------------------------------- #


def test_missing_models_declare_why_they_are_absent():
    from scaleup_ai.equations import MISSING_MODELS

    for m in MISSING_MODELS.values():
        assert m.why_needed
        assert m.why_not_implemented
        assert m.missing_inputs


def test_folding_model_refuses_temperature_as_causal_predictor():
    from scaleup_ai.equations import MISSING_MODELS

    reason = MISSING_MODELS["folding.renaturation_kinetics"].why_not_implemented
    assert "not on the temperature" in reason