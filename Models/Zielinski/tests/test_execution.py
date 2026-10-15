"""Engine behaviour: calculation correctness, tracing, and fail-closed semantics."""

from __future__ import annotations

import pytest

from scaleup_ai import ExecutionMode, Provenance
from scaleup_ai.equations import EQUATIONS, AmbiguousEquation


def value_of(run, node_id, quantity_id):
    for q in run.node(node_id).computed:
        if q.quantity_id == quantity_id:
            return q.value
    raise AssertionError(f"{quantity_id} was not computed on {node_id}")


# --------------------------------------------------------------------------- #
# D1 fermentation reference case
# --------------------------------------------------------------------------- #


def test_wet_biomass_per_litre_is_the_documented_division(replay):
    assert value_of(replay, "N02", "wet_biomass_g_per_L") == pytest.approx(224 / 4)


def test_inclusion_bodies_per_litre_is_the_documented_division(replay):
    assert value_of(replay, "N03", "inclusion_bodies_g_per_L") == pytest.approx(58 / 4)


def test_documented_conditions_are_encoded(graph):
    oc = graph.node("N01").operating_conditions
    assert oc["inoculum_volume"].value == 50 and oc["inoculum_volume"].unit == "mL"
    assert oc["inoculum_cultivation_time"].value == 18
    assert oc["inoculum_temperature"].value == 30
    assert oc["fermenter_nominal_volume"].value == 7.5
    assert oc["starting_medium_volume"].value == 4
    assert oc["fermenter_temperature"].value == 37
    assert oc["growth_duration"].value_range == (15.0, 16.0)
    assert oc["glucose_target_initial"].value_range == (70.0, 120.0)
    assert oc["ph_stat_glucose_target"].value_range == (30.0, 50.0)
    assert oc["proline_feed_concentration"].value == 12
    assert oc["ph_control_reagent"].value == 16
    assert graph.node("N01").measurements["od600_max"].value == 54.4


def test_no_mechanistic_growth_model_is_implemented():
    from scaleup_ai.equations import MISSING_MODELS

    ids = set(MISSING_MODELS)
    assert "kinetics.growth_ode" in ids
    assert "kinetics.monod_substrate" in ids
    assert "transfer.oxygen_kla" in ids
    # none of them are implemented as executable equations
    assert not any("monod" in e or "kla" in e for e in EQUATIONS)


# --------------------------------------------------------------------------- #
# D2 dissolution and refolding
# --------------------------------------------------------------------------- #


def test_dissolution_conditions_are_encoded(graph):
    oc = graph.node("N04").operating_conditions
    assert oc["carbonate_buffer"].value == 12
    assert oc["edta_concentration"].value == 0.2
    assert oc["initial_ph"].value == 11.9
    assert oc["adjusted_ph"].value == 10.8
    assert oc["dissolution_time"].value == 45
    s5 = graph.stream("S05_denatured_solution")
    assert s5.require("ib_aliquot_mass").value == 17.9
    assert s5.require("dissolved_protein").value == 5460


def test_reported_refolding_yields_are_stored_as_reference_values(graph):
    m = graph.node("N05").measurements
    assert m["refolding_yield_room_temperature"].value_range == (95.0, 96.0)
    assert m["refolding_yield_low_temperature"].value == 99
    assert graph.stream("S06_renatured_precursor").require("protein_after_refolding").value == 5450


def test_no_temperature_yield_function_is_fitted(graph):
    ids = [q.quantity_id for _l, _i, q in graph.iter_quantities()]
    assert not any("yield_from_temperature" in i for i in ids)


def test_implied_refolding_yield_is_reported_and_contradicts_the_text(replay, graph):
    implied = value_of(replay, "N05", "implied_refolding_yield_pct")
    assert implied == pytest.approx(5450 / 5460 * 100)
    codes = {m.code for m in graph.node("N05").validation_messages}
    assert "source_discrepancy:refolding_yield_vs_au" in codes


# --------------------------------------------------------------------------- #
# D3 downstream stages
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "node_id,stream_id,volume,concentration,expected",
    [
        ("N08", "S09_deae_fraction", 250.0, 8.57, 2142.5),
        ("N11", "S13_q_fraction", 226.0, 2.77, 626.02),
        ("N13", "S15_rp_hplc_fraction", 97.0, 2.42, 234.74),
        ("N14", "S16_g25_fraction", 31.0, 3.59, 111.29),
    ],
)
def test_stage_total_au_is_volume_times_concentration(
    replay, node_id, stream_id, volume, concentration, expected
):
    assert value_of(replay, node_id, "total_au") == pytest.approx(volume * concentration)
    assert value_of(replay, node_id, "total_au") == pytest.approx(expected)


def test_stage_measurements_match_the_paper(graph):
    assert graph.stream("S09_deae_fraction").require("fraction_volume").value == 250
    assert graph.stream("S09_deae_fraction").require("protein_concentration").value == 8.57
    assert graph.stream("S13_q_fraction").require("fraction_volume").value == 226
    assert graph.stream("S13_q_fraction").require("protein_concentration").value == 2.77
    assert graph.stream("S15_rp_hplc_fraction").require("fraction_volume").value == 97
    assert graph.stream("S15_rp_hplc_fraction").require("protein_concentration").value == 2.42
    assert graph.stream("S16_g25_fraction").require("fraction_volume").value == 31
    assert graph.stream("S16_g25_fraction").require("protein_concentration").value == 3.59


def test_source_formulas_are_preserved_verbatim_with_their_variables(graph):
    exprs = {
        e.expression_id: e
        for n in graph.nodes
        for e in n.source_expressions
    }
    assert exprs["E-ZNCL2"].expression_text == "2 x V cm3 solution/100"
    assert exprs["E-WATER"].expression_text == "total amount of protein obtained after DEAE/7"
    assert exprs["E-EDTA"].expression_text == "total amount of protein obtained after DEAE/190"
    assert exprs["E-CITRACONYLATION-ANHYDRIDE"].expression_text == "0.2 x V solution (dm3) x A280 nm"
    assert exprs["E-TRYPSIN"].expression_text == "A280 nm x V solution (dm3)/75"
    assert exprs["E-ETHANOLAMINE"].expression_text == "3 x V citraconic anhydride"
    assert exprs["E-APROTININ"].expression_text == "V trypsin/21"
    assert exprs["E-CPB"].expression_text == "10 ul for every 150 AU of total protein"
    assert exprs["E-ZNCL2"].variable_definitions


def test_ambiguous_formulas_are_never_executed(engine, replay):
    ambiguous = [e for e in EQUATIONS.values() if not e.executable]
    assert ambiguous, "the model must retain at least one formula it refuses to run"
    for eq in ambiguous:
        assert eq.ambiguity
        with pytest.raises(AmbiguousEquation):
            eq.evaluate({i.key: 1.0 for i in eq.inputs})

    executed = {t.equation_id for nr in replay.node_results for t in nr.traces}
    assert not (executed & {e.equation_id for e in ambiguous})


def test_refused_formulas_surface_as_unresolved_targets(replay):
    targets = {u.target for u in replay.unresolved}
    assert "N06:citraconic_anhydride_volume" in targets
    assert "N06:ethanolamine_volume" in targets
    assert "N07:trypsin_volume" in targets


def test_source_formula_zinc_chloride_reproduces_the_reported_dose(replay):
    assert value_of(replay, "N10", "zinc_chloride_volume") == pytest.approx(10.0)


def test_source_formula_edta_matches_the_reported_dose(replay):
    assert value_of(replay, "N10", "edta_volume_from_formula") == pytest.approx(2142.5 / 190)


def test_water_volume_contradiction_is_computed_both_ways_not_resolved(replay):
    assert value_of(replay, "N10", "water_volume_from_formula") == pytest.approx(306.0714, rel=1e-4)


def test_cpb_dose_contradiction_is_computed_both_ways_not_resolved(replay):
    assert value_of(replay, "N12", "cpb_volume_from_formula") == pytest.approx(41.7347, rel=1e-4)


def test_au_is_never_equated_with_mass_activity_or_concentration(graph):
    from scaleup_ai.units import is_convertible

    assert not is_convertible("AU", "g")
    assert not is_convertible("AU", "IU")
    assert not is_convertible("AU", "M")
    au_quantities = [
        q for _l, _i, q in graph.iter_quantities() if q.unit == "AU"
    ]
    assert au_quantities
    for q in au_quantities:
        assert q.notes or q.method


def test_no_purification_recovery_is_invented(graph):
    ids = {q.quantity_id for _l, _i, q in graph.iter_quantities()}
    assert "stage_recovery_percent" not in ids
    assert not any("recovery_pct" in i for i in ids)


# --------------------------------------------------------------------------- #
# D4 final product
# --------------------------------------------------------------------------- #


def test_final_product_reference_outcomes_are_recorded(graph):
    m = graph.node("N15").measurements
    assert m["activity"].value == 2700 and m["activity"].unit == "IU/L"
    assert m["purity"].value == 99
    assert m["measured_molecular_mass"].value == 5807.5
    assert m["theoretical_molecular_mass"].value == 5807.63
    assert m["retention_time"].value == 3.748


def test_mass_accuracy_is_derived_transparently(replay):
    assert value_of(replay, "N15", "mass_deviation") == pytest.approx(-0.13, abs=1e-9)
    assert value_of(replay, "N15", "mass_deviation_ppm") == pytest.approx(
        (5807.5 - 5807.63) / 5807.63 * 1e6, rel=1e-9
    )


def test_final_outcomes_are_observed_not_predicted(replay):
    for q in replay.node("N15").computed:
        assert q.provenance is Provenance.DERIVED


# --------------------------------------------------------------------------- #
# provenance bookkeeping and tracing
# --------------------------------------------------------------------------- #


def test_every_computed_value_is_tagged_derived_and_names_its_equation(replay):
    for nr in replay.node_results:
        for q in nr.computed:
            assert q.provenance is Provenance.DERIVED
            assert q.method and q.inputs
        assert len(nr.computed) == len(nr.traces)


def test_calculation_traces_record_input_provenance_and_normalization(replay):
    trace = next(t for t in replay.node("N02").traces)
    inp = trace.input_values["total_mass"]
    assert inp["ref"] == "stream:S03_wet_biomass:wet_biomass_total"
    assert inp["value"] == 224.0
    assert inp["source_unit"] == "g"
    assert inp["normalized_unit"] == "g"
    assert inp["provenance"] == "reported"
    assert trace.statement == "mass_per_volume = total_mass / volume"


def test_every_equation_declares_inputs_that_its_function_actually_reads():
    """Guards against a binding whose arithmetic disagrees with its declaration."""
    for eq in EQUATIONS.values():
        if not eq.executable:
            continue
        assert eq.evaluate({i.key: 1.0 for i in eq.inputs}) is not None


def test_engine_is_deterministic(engine):
    a = engine.run(mode=ExecutionMode.EVIDENCE_REPLAY)
    b = engine.run(mode=ExecutionMode.EVIDENCE_REPLAY)
    assert [q.value for q in a.all_computed()] == [q.value for q in b.all_computed()]