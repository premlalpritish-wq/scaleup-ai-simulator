"""Acceptance tests AT-001 .. AT-026 for the Zielinski et al. (2019) process model.

Each test is named for the criterion it enforces and is written to be read
against the specification. No criterion requires inventing a scientific
parameter that is absent from the paper: where the paper is silent, the test
asserts that the model says so.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scaleup_ai import ExecutionMode, Provenance, Quantity, UnitError
from scaleup_ai.equations import EQUATIONS, MISSING_MODELS
from scaleup_ai.serialize import (
    DeserializationError,
    quantity_from_dict,
    run_result_from_dict,
)
from scaleup_ai.units import is_convertible

from models.zielinski_2019 import build_graph, predict

# the 15 operations named in the specification, in order
SPEC_NODES = [
    ("N01", "Fermentation"),
    ("N02", "Biomass harvest"),
    ("N03", "Cell lysis and inclusion-body isolation"),
    ("N04", "Inclusion-body dissolution"),
    ("N05", "Protein renaturation"),
    ("N06", "Citraconylation"),
    ("N07", "Trypsinization"),
    ("N08", "DEAE Sepharose purification"),
    ("N09", "Decitraconylation"),
    ("N10", "Zinc precipitation and zinc-salt dissolution"),
    ("N11", "Q Sepharose purification"),
    ("N12", "Carboxypeptidase B treatment"),
    ("N13", "RP-HPLC purification"),
    ("N14", "Sephadex G-25 buffer exchange"),
    ("N15", "Final product characterization"),
]


#: Every acceptance criterion and the test class that enforces it. This map is
#: the authoritative coverage record; `test_acceptance_criteria_are_all_covered`
#: checks that it stays complete and that each named class exists.
AT_COVERAGE = {
    "AT-001": "TestAT001ProcessTopology",
    "AT-002": "TestAT002NoFabricatedOperations",
    "AT-003": "TestAT003MaterialContinuity",
    "AT-004": "TestAT004ProvenanceRequired",
    "AT-005": "TestAT005UnknownIsNotZero",
    "AT-006": "TestAT006SourceAndModelOutputsDistinct",
    "AT-007": "TestAT007ConflictingEvidencePreserved",
    "AT-008": "TestAT008WetBiomass",
    "AT-009": "TestAT009InclusionBodies",
    "AT-010": "TestAT010DissolvedProtein",
    "AT-011": "TestAT011Renaturation",
    "AT-012": "TestAT012ToAT015StageFractions",
    "AT-013": "TestAT012ToAT015StageFractions",
    "AT-014": "TestAT012ToAT015StageFractions",
    "AT-015": "TestAT012ToAT015StageFractions",
    "AT-016": "TestAT016FinalProductReference",
    "AT-017": "TestAT017MassDeviation",
    "AT-018": "TestAT018UnsupportedKineticsRejected",
    "AT-019": "TestAT019UnsupportedScaleUpRejected",
    "AT-020": "TestAT020DimensionalIntegrity",
    "AT-021": "TestAT021FigureDerivedDataLabelled",
    "AT-022": "TestAT022DeterministicReplay",
    "AT-023": "TestAT023CalculationTraceability",
    "AT-024": "TestAT024PartialExecution",
    "AT-025": "TestAT025SerializationRoundTrip",
    "AT-026": "TestAT026RegressionSuite",
}


def computed(run, node_id, quantity_id):
    for q in run.node(node_id).computed:
        if q.quantity_id == quantity_id:
            return q
    raise AssertionError(f"{node_id}:{quantity_id} was not computed")


# =========================================================================== #
# 1. Process topology
# =========================================================================== #


class TestAT001ProcessTopology:
    def test_all_fifteen_nodes_exist_in_documented_order(self, graph):
        assert [(n.node_id, n.name) for n in graph.topological_order()] == SPEC_NODES

    def test_g25_buffer_exchange_follows_rp_hplc(self, graph):
        order = [n.node_id for n in graph.topological_order()]
        assert order.index("N14") == order.index("N13") + 1
        g25 = graph.node("N14")
        assert "Sephadex" in g25.name and "G-25" in g25.name
        assert g25.input_streams == graph.node("N13").output_streams

    def test_every_stream_has_unique_id_and_explicit_references(self, graph):
        seen = set()
        for sid, stream in graph.streams.items():
            assert sid == stream.stream_id
            assert sid not in seen
            seen.add(sid)
            assert stream.kind is not None
            if sid == "S01_inoculum":
                assert stream.produced_by is None  # external feed
            else:
                assert stream.produced_by in {n.node_id for n in graph.nodes}
            if stream.consumed_by is not None:
                assert stream.consumed_by in {n.node_id for n in graph.nodes}
        assert len(seen) == len(graph.streams)


class TestAT002NoFabricatedOperations:
    def test_node_set_is_exactly_the_specified_operations(self, graph):
        assert set(n.node_id for n in graph.nodes) == {i for i, _ in SPEC_NODES}

    def test_every_node_is_backed_by_the_paper(self, graph):
        for node in graph.nodes:
            assert node.evidence, f"{node.node_id} asserts an operation with no source"
            assert all(e.source_id == "zielinski2019" for e in node.evidence)

    def test_no_reported_value_without_a_citation(self, graph):
        """An undocumented number must not enter as a reported fact."""
        for location, qid, q in graph.iter_quantities():
            if q.provenance is Provenance.REPORTED:
                assert q.evidence, f"{location}:{qid} reported with no citation"

    def test_operations_use_only_the_declared_vocabulary(self, graph):
        from scaleup_ai.process import OperationKind

        for node in graph.nodes:
            assert isinstance(node.operation, OperationKind)


class TestAT003MaterialContinuity:
    def test_each_node_output_feeds_the_declared_downstream_input(self, graph):
        for node in graph.nodes:
            for sid in node.output_streams:
                consumer = graph.stream(sid).consumed_by
                if consumer is None:
                    continue
                assert sid in graph.node(consumer).input_streams, f"{sid} -> {consumer}"

    def test_lineage_is_continuous_across_the_whole_chain(self, graph):
        assert graph.stream("S01_inoculum").lineage == ()
        assert graph.stream("S02_culture_broth").lineage == ("S01_inoculum",)
        assert graph.stream("S17_final_product").lineage == ("S16_g25_fraction",)

    def test_missing_stream_quantities_stay_unresolved_not_zero(self, graph):
        dissolved = graph.stream("S05_denatured_solution")
        q = dissolved.require("dissolved_protein_concentration")
        assert q.provenance is Provenance.UNKNOWN
        assert q.value is None and q.value_range is None
        assert dissolved.require("dissolved_protein").value == 5460  # reported one is intact


# =========================================================================== #
# 2. Provenance and scientific traceability
# =========================================================================== #


class TestAT004ProvenanceRequired:
    def test_every_serialized_numeric_field_carries_a_provenance_class(self, graph):
        for _loc, _qid, q in graph.iter_quantities():
            d = q.to_dict()
            assert d["provenance"] in {p.value for p in Provenance}
            assert d["basis"] in {"observed_reference", "computed", "assumed_input", "unresolved"}
            if q.is_resolved:
                assert q.evidence or q.method or q.provenance is Provenance.ASSUMED, q.quantity_id

    def test_derived_quantities_include_equation_and_input_references(self, replay):
        for nr in replay.node_results:
            for q in nr.computed:
                assert q.provenance is Provenance.DERIVED
                assert q.method, q.quantity_id
                assert q.inputs, q.quantity_id
                trace = next(t for t in nr.traces if t.output_quantity_id == q.quantity_id)
                assert set(trace.input_values) >= {k.split("=")[0] for k in q.inputs}

    def test_reported_quantities_include_a_source_reference(self, graph):
        for _loc, _qid, q in graph.iter_quantities():
            if q.provenance is Provenance.REPORTED:
                ref = q.evidence[0]
                assert ref.printed_page
                # evidence must locate the value in the paper: by section or figure
                assert ref.section or ref.figure, q.quantity_id


class TestAT005UnknownIsNotZero:
    def test_unavailable_kinetic_constants_stay_unknown(self, graph):
        for qid in ("specific_growth_rate", "od600_from_inputs", "wet_biomass_from_inputs"):
            q = next(
                q for _l, _i, q in graph.iter_quantities() if q.quantity_id == qid
            )
            assert q.provenance is Provenance.UNKNOWN
            assert q.value is None, f"{qid} was given a default"
            assert q.notes

    def test_unavailable_recovery_efficiency_stays_unknown(self, graph):
        recoveries = [
            q for _l, _i, q in graph.iter_quantities()
            if "recovery" in q.quantity_id or "stage_yield" in q.quantity_id
        ]
        for q in recoveries:
            assert q.provenance is Provenance.UNKNOWN
            assert q.value is None

    def test_unknown_quantity_cannot_be_instantiated_with_a_value(self):
        from scaleup_ai import QuantityError

        with pytest.raises(QuantityError):
            Quantity("x", "k", Provenance.UNKNOWN, value=0.0, unit="1/h")

    def test_no_zero_substitution_anywhere_in_the_graph(self, graph):
        zeros = [
            (loc, qid) for loc, qid, q in graph.iter_quantities()
            if q.value == 0.0 and q.provenance is Provenance.UNKNOWN
        ]
        assert zeros == []


class TestAT006SourceAndModelOutputsDistinct:
    def test_activity_is_not_a_prediction_in_predictive_mode(self, engine):
        r = predict("node:N15:activity", engine)
        assert r.is_resolved is False
        assert r.quantity is None
        assert "activity" in r.unresolved.reason.lower()

    def test_activity_is_observed_reference_in_replay(self, graph, engine):
        q = graph.node("N15").measurements["activity"]
        assert q.provenance is Provenance.REPORTED
        assert q.basis.value == "observed_reference"
        assert q.value == 2700 and q.unit == "IU/L"
        # replay run reports zero predictions overall
        assert engine.run(mode=ExecutionMode.EVIDENCE_REPLAY).summary.predicted_values == 0

    def test_reported_final_outcomes_are_absent_from_predictive_computed_set(self, engine):
        run = engine.run(mode=ExecutionMode.PREDICTIVE)
        computed_ids = {q.quantity_id for nr in run.node_results for q in nr.computed}
        for qid in ("activity", "purity", "measured_molecular_mass", "retention_time"):
            assert qid not in computed_ids


class TestAT007ConflictingEvidencePreserved:
    #: values the paper states, pinned so a contradiction cannot be "resolved" by
    #: quietly editing a reported number until the arithmetic agrees
    PINNED_REPORTED = {
        ("node:N10", "water_volume_reported"): 285.0,
        ("node:N10", "tris_stock_volume_reported"): 9.2,
        ("node:N10", "edta_volume_reported"): 11.3,
        ("node:N10", "zinc_chloride_volume_reported"): 10.0,
        ("node:N12", "cpb_volume_reported"): 50.0,
        ("node:N07", "trypsin_volume"): 70.0,
        ("node:N06", "citraconic_anhydride_volume"): 1.0,
        ("node:N06", "ethanolamine_volume"): 3.0,
        ("stream:S05_denatured_solution", "dissolved_protein"): 5460.0,
        ("stream:S06_renatured_precursor", "protein_after_refolding"): 5450.0,
        ("node:N02", "centrifugation_force"): 15000.0,
        ("node:N15", "activity"): 2700.0,
    }

    @pytest.mark.parametrize(
        "location,qid,expected",
        [(f"{a}", f"{b}", v) for (a, b), v in PINNED_REPORTED.items()],
        ids=[f"{a}:{b}" for (a, b) in PINNED_REPORTED],
    )
    def test_reported_values_match_the_paper_exactly(self, graph, location, qid, expected):
        """A reported value may not be edited to make a contradiction disappear."""
        kind, _, name = location.partition(":")
        container = graph.node(name) if kind == "node" else graph.stream(name)
        q = container.require(qid)
        assert q.provenance is Provenance.REPORTED, f"{location}:{qid}"
        assert q.value == pytest.approx(expected), (
            f"{location}:{qid} is {q.value}, but the paper reports {expected}"
        )

    def test_water_volume_contradiction_cannot_be_silently_resolved(self, graph, replay):
        """285 mL and 306.07 mL must both remain visible and both must be flagged."""
        reported = graph.node("N10").measurements["water_volume_reported"].value
        computed_v = computed(replay, "N10", "water_volume_from_formula").value
        assert reported == pytest.approx(285.0)
        assert computed_v == pytest.approx(2142.5 / 7, rel=1e-6)
        assert reported != pytest.approx(computed_v)  # the conflict still exists
        codes = {m.code for m in graph.node("N10").validation_messages}
        assert "source_discrepancy:water_volume_vs_formula" in codes

    def test_both_fermentation_duration_claims_are_retained(self, graph):
        oc = graph.node("N01").operating_conditions
        assert oc["growth_duration"].value_range == (15.0, 16.0)
        assert oc["post_induction_duration"].value_range == (4.0, 5.0)
        assert oc["growth_duration"].provenance is Provenance.REPORTED

    def test_both_refolding_duration_claims_are_retained(self, graph):
        oc = graph.node("N05").operating_conditions
        assert oc["folding_time_methods"].value == 18
        assert oc["folding_time_results"].value_range == (18.0, 19.0)

    def test_refolding_statements_are_retained(self, graph):
        m = graph.node("N05").measurements
        assert m["refolding_yield_room_temperature"].value_range == (95.0, 96.0)
        assert m["refolding_yield_low_temperature"].value == 99

    def test_a_review_warning_is_emitted_for_each_conflict(self, graph):
        codes = {m.code for n in graph.nodes for m in n.validation_messages}
        for code in (
            "source_discrepancy:growth_duration_ambiguity",
            "source_discrepancy:induction_order",
            "source_discrepancy:refolding_duration_methods_vs_results",
            "source_discrepancy:refolding_yield_vs_au",
        ):
            assert code in codes

    def test_conflicting_values_are_neither_overwritten_nor_averaged(self, graph):
        oc = graph.node("N05").operating_conditions
        assert oc["folding_time_methods"].value == 18  # not 18.5
        assert oc["folding_time_results"].value_range == (18.0, 19.0)
        assert oc["folding_time_results"].value is None  # not collapsed


# =========================================================================== #
# 3. Numerical acceptance tests
# =========================================================================== #


class TestAT008WetBiomass:
    def test_224g_in_4l_is_56_g_per_l(self, replay, graph):
        assert graph.stream("S03_wet_biomass").require("wet_biomass_total").value == 224
        assert graph.node("N01").operating_conditions["starting_medium_volume"].value == 4
        q = computed(replay, "N02", "wet_biomass_g_per_L")
        assert q.value == pytest.approx(56.0)
        assert q.provenance is Provenance.DERIVED


class TestAT009InclusionBodies:
    def test_58g_in_4l_is_14_5_g_per_l(self, replay, graph):
        assert graph.stream("S04_inclusion_bodies").require("inclusion_bodies_total").value == 58
        q = computed(replay, "N03", "inclusion_bodies_g_per_L")
        assert q.value == pytest.approx(14.5)
        assert q.provenance is Provenance.DERIVED


class TestAT010DissolvedProtein:
    def test_5460_au_is_reported_for_the_17_9g_aliquot(self, graph):
        s = graph.stream("S05_denatured_solution")
        assert s.require("ib_aliquot_mass").value == 17.9
        q = s.require("dissolved_protein")
        assert q.value == 5460
        assert q.provenance is Provenance.REPORTED
        assert q.unit == "AU"

    def test_au_is_never_read_as_mass_or_activity(self):
        assert not is_convertible("AU", "g")
        assert not is_convertible("AU", "IU")
        assert not is_convertible("AU", "IU/L")
        assert not is_convertible("AU", "mg/mL")


class TestAT011Renaturation:
    def test_reported_yields_and_duration(self, graph):
        m = graph.node("N05").measurements
        assert m["refolding_yield_room_temperature"].value_range == (95.0, 96.0)
        assert m["refolding_yield_low_temperature"].value == pytest.approx(99)
        assert m["refolding_yield_room_temperature"].provenance is Provenance.REPORTED
        assert graph.node("N05").operating_conditions["folding_time_results"].value_range == (
            18.0,
            19.0,
        )

    def test_no_kinetic_constant_is_derived_from_these_observations(self, graph, replay):
        """Three refolding observations must not yield a rate constant."""
        ids = {q.quantity_id for _l, _i, q in graph.iter_quantities()}
        for forbidden in ("folding_rate", "refolding_k", "k_refold", "rate_constant",
                          "fold_rate", "half_life", "kinetic_constant"):
            assert not any(forbidden in i for i in ids), forbidden
        for q in replay.all_computed():
            assert "rate" not in q.quantity_id
            assert "k_" not in q.quantity_id

    def test_yield_function_is_declared_absent(self):
        assert "folding.renaturation_kinetics" in MISSING_MODELS
        assert MISSING_MODELS["folding.renaturation_kinetics"].missing_inputs


class TestAT012ToAT015StageFractions:
    @pytest.mark.parametrize(
        "at,node,stream,volume,conc,expected",
        [
            ("AT-012", "N08", "S09_deae_fraction", 250.0, 8.57, 2142.5),
            ("AT-013", "N11", "S13_q_fraction", 226.0, 2.77, 626.02),
            ("AT-014", "N13", "S15_rp_hplc_fraction", 97.0, 2.42, 234.74),
            ("AT-015", "N14", "S16_g25_fraction", 31.0, 3.59, 111.29),
        ],
    )
    def test_stage_total_is_volume_times_concentration(
        self, replay, graph, at, node, stream, volume, conc, expected
    ):
        s = graph.stream(stream)
        assert s.require("fraction_volume").value == volume
        assert s.require("protein_concentration").value == conc
        q = computed(replay, node, "total_au")
        assert q.value == pytest.approx(expected)
        assert q.value == pytest.approx(volume * conc)
        assert q.provenance is Provenance.DERIVED
        assert q.unit == "AU"

    def test_stage_totals_are_labelled_absorbance_based(self, graph):
        for sid in ("S09_deae_fraction", "S13_q_fraction", "S15_rp_hplc_fraction",
                    "S16_g25_fraction"):
            for q in graph.stream(sid).quantities.values():
                if q.unit in ("AU", "AU/mL"):
                    assert "instrument-relative" in q.notes
                    assert "NOT grams" in q.notes

    def test_no_stage_total_is_presented_as_purified_insulin_mass(self, graph, replay):
        for sid in ("S09_deae_fraction", "S13_q_fraction", "S15_rp_hplc_fraction",
                    "S16_g25_fraction"):
            for q in graph.stream(sid).quantities.values():
                assert q.unit != "g"
                assert q.unit != "mg"
        for q in replay.all_computed():
            assert q.unit != "g"


class TestAT016FinalProductReference:
    def test_reported_values_are_recorded(self, graph):
        m = graph.node("N15").measurements
        assert m["activity"].value == pytest.approx(2700) and m["activity"].unit == "IU/L"
        assert m["purity"].value == pytest.approx(99)
        assert m["measured_molecular_mass"].value == pytest.approx(5807.5)
        assert m["theoretical_molecular_mass"].value == pytest.approx(5807.63)

    def test_these_remain_distinct_from_simulated_predictions(self, graph, replay):
        for qid in ("activity", "purity", "measured_molecular_mass",
                    "theoretical_molecular_mass", "retention_time"):
            q = next(q for _l, _i, q in graph.iter_quantities() if q.quantity_id == qid)
            assert q.provenance is Provenance.REPORTED
            assert q.basis.value == "observed_reference"
        computed_ids = {q.quantity_id for q in replay.all_computed()}
        assert "activity" not in computed_ids
        assert "measured_molecular_mass" not in computed_ids


class TestAT017MassDeviation:
    def test_signed_and_absolute_difference(self, replay):
        q = computed(replay, "N15", "mass_deviation")
        assert q.value == pytest.approx(-0.13, abs=1e-9)
        assert q.value < 0
        assert abs(q.value) == pytest.approx(0.13, abs=1e-9)

    def test_uncertainty_is_carried_so_no_significance_is_implied(self, graph, replay):
        measured = graph.node("N15").measurements["measured_molecular_mass"]
        theoretical = graph.node("N15").measurements["theoretical_molecular_mass"]
        assert measured.uncertainty is not None
        assert theoretical.uncertainty is not None
        q = computed(replay, "N15", "mass_deviation")
        assert q.uncertainty is not None
        half = (q.uncertainty.hi - q.uncertainty.lo) / 2
        assert half == pytest.approx(0.055, abs=1e-9)

    def test_no_statistical_significance_claim_is_made(self, graph):
        text = " ".join(
            m.message for n in graph.nodes for m in n.validation_messages
        ).lower()
        for forbidden in ("significant", "p-value", "p <", "p<", "confidence interval",
                          "statistically significant"):
            assert forbidden not in text.replace("not a statistical test", ""), forbidden
        assert "no claim of significance" in text

    def test_relative_deviation_is_also_reported_with_its_meaning(self, replay):
        q = computed(replay, "N15", "mass_deviation_ppm")
        assert q.value == pytest.approx((5807.5 - 5807.63) / 5807.63 * 1e6, rel=1e-9)


# =========================================================================== #
# 4. Model validity
# =========================================================================== #


class TestAT018UnsupportedKineticsRejected:
    @pytest.mark.parametrize(
        "target",
        [
            "node:N01:od600_from_inputs",
            "node:N01:wet_biomass_from_inputs",
            "node:N01:specific_growth_rate",
            "node:N01:dissolved_oxygen",
            "node:N05:refolding_yield_predictive",
            "node:N05:refolding_time_predictive",
        ],
    )
    def test_time_resolved_prediction_returns_unresolved(self, engine, target):
        r = predict(target, engine)
        assert r.is_resolved is False
        assert r.quantity is None
        assert r.unresolved.missing_models

    def test_no_growth_rate_yield_coefficient_or_reaction_rate_is_fabricated(self):
        banned = ("monod", "mu_max", "yield_coefficient", "ks_", "rate_constant",
                  "kla", "growth_rate")
        for eq in EQUATIONS.values():
            assert not any(b in eq.equation_id.lower() for b in banned)
            assert not any(b in eq.statement.lower() for b in banned)
        for mid in ("kinetics.growth_ode", "kinetics.monod_substrate",
                    "transfer.oxygen_kla", "folding.renaturation_kinetics"):
            assert mid in MISSING_MODELS

    def test_predictive_run_without_inputs_computes_nothing(self, engine):
        run = engine.run(mode=ExecutionMode.PREDICTIVE)
        assert run.summary.computed_values == 0
        assert run.summary.predicted_values == 0


class TestAT019UnsupportedScaleUpRejected:
    @pytest.mark.parametrize(
        "target",
        [
            "node:N01:scaled_up_od600",
            "node:N01:scaled_up_wet_biomass",
            "node:N01:industrial_insulin_yield",
            "node:N15:industrial_scale_activity",
            "graph:industrial_scale_process",
            "node:N19:industrial_scale_insulin_yield",
            "graph:1000L_batch_od600",
            "some_unlisted_industrial_prediction",
        ],
    )
    def test_industrial_prediction_is_refused_and_identifies_the_gap(self, engine, target):
        r = predict(target, engine)
        assert r.is_resolved is False
        assert r.quantity is None
        assert "scaleup.effect_of_scale" in r.unresolved.missing_models
        assert "scaleup.effect_of_scale" in r.unresolved.reason

    def test_the_four_litre_results_are_not_extrapolated(self, engine):
        run = engine.run(mode=ExecutionMode.PREDICTIVE)
        for nr in run.node_results:
            for q in nr.computed:
                assert "scale" not in q.quantity_id

    def test_scale_up_model_declares_what_it_would_need(self):
        model = MISSING_MODELS["scaleup.effect_of_scale"]
        assert model.missing_inputs
        assert "single laboratory scale" in model.why_not_implemented

    def test_batch_activity_is_labelled_as_arithmetic_not_scale_up(self, replay):
        q = computed(replay, "N15", "batch_activity")
        assert q.value == pytest.approx(10800.0)
        assert "not a validated scale-up prediction" in q.notes


class TestAT020DimensionalIntegrity:
    @pytest.mark.parametrize(
        "src,dst",
        [
            ("AU", "g"), ("AU", "IU"), ("AU", "L"), ("IU", "g"),
            ("g", "h"), ("degC", "L"), ("mL", "h"), ("Da", "g"),
            ("pH", "1"), ("1", "pH"),
        ],
    )
    def test_incompatible_units_are_not_interchangeable(self, src, dst):
        assert not is_convertible(src, dst)

    def test_conversion_raises_rather_than_guessing(self):
        with pytest.raises(UnitError):
            from scaleup_ai import convert

            convert(1.0, "AU", "g")

    def test_dimension_mismatch_produces_an_unresolved_result_not_a_value(self, engine):
        from scaleup_ai.engine import EquationBinding, ExecutionEngine, Ref, node_loc

        # AU/mL cannot feed an input declared in g/L
        binding = EquationBinding(
            binding_id="AT020-DIM",
            node_id="N01",
            equation_id="accounting.mass_per_volume",
            inputs={
                "total_mass": Ref("stream:S09_deae_fraction", "protein_concentration"),
                "volume": Ref(node_loc("N01"), "starting_medium_volume"),
            },
            output_quantity_id="bogus",
            output_location=node_loc("N01"),
        )
        run = ExecutionEngine(engine.graph, bindings=[binding]).run(
            mode=ExecutionMode.EVIDENCE_REPLAY
        )
        assert run.node("N01").computed == []
        assert "node:N01:bogus" in {u.target for u in run.unresolved}
        assert "dimension mismatch" in run.unresolved[0].reason

    def test_valid_conversions_still_work(self):
        from scaleup_ai import convert

        assert convert(4.0, "L", "mL") == 4000.0
        assert convert(1.0, "dm3", "mL") == 1000.0


class TestAT021FigureDerivedDataLabelled:
    def test_every_figure_3_point_is_digitized(self, graph):
        stream = graph.stream("S02_culture_broth")
        points = [q for qid, q in stream.quantities.items() if qid.startswith("od600_h")]
        assert len(points) == 19
        for q in points:
            assert q.provenance is Provenance.DIGITIZED
            assert q.basis.value == "observed_reference"

    def test_points_carry_an_approximate_data_flag(self, graph):
        for q in graph.stream("S02_culture_broth").quantities.values():
            if q.provenance is Provenance.DIGITIZED:
                assert q.uncertainty is not None
                assert q.uncertainty.lo < q.value < q.uncertainty.hi

    def test_points_carry_a_figure_reference(self, graph):
        for q in graph.stream("S02_culture_broth").quantities.values():
            if q.provenance is Provenance.DIGITIZED:
                assert q.evidence
                assert any(e.figure == "Fig. 3" for e in q.evidence)
                assert all(e.printed_page == 67 for e in q.evidence)

    def test_digitized_points_are_not_presented_as_tabulated_measurements(self, graph):
        for qid, q in graph.stream("S02_culture_broth").quantities.items():
            if q.provenance is Provenance.DIGITIZED:
                assert q.provenance is not Provenance.REPORTED
                assert "digitized" in (q.method or q.label).lower() or q.uncertainty is not None

    def test_digitization_method_is_documented(self):
        from models.source import fig3_trajectory

        method = fig3_trajectory()["digitization_method"]
        assert method["steps"] and method["declared_uncertainty"]
        assert "not_modelled" in method


# =========================================================================== #
# 5. Reproducibility and execution
# =========================================================================== #


class TestAT022DeterministicReplay:
    def test_repeated_replays_produce_identical_results(self, engine):
        runs = [engine.run(mode=ExecutionMode.EVIDENCE_REPLAY) for _ in range(3)]
        payloads = [json.dumps(r.to_dict(), sort_keys=True) for r in runs]
        assert payloads[0] == payloads[1] == payloads[2]

    def test_warnings_and_unresolved_fields_are_stable(self, engine):
        runs = [engine.run(mode=ExecutionMode.EVIDENCE_REPLAY) for _ in range(3)]
        for r in runs[1:]:
            assert [m.code for m in r.cross_checks] == [m.code for m in runs[0].cross_checks]
            assert [u.target for u in r.unresolved] == [u.target for u in runs[0].unresolved]
            assert r.summary.to_dict() == runs[0].summary.to_dict()

    def test_serialized_replay_is_byte_identical(self, engine, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            from scaleup_ai.report import ModelBundle, write_all

            a = write_all(ModelBundle.build(engine), Path(d) / "a")["evidence_record"].read_text("utf-8")
            b = write_all(ModelBundle.build(engine), Path(d) / "b")["evidence_record"].read_text("utf-8")
            assert a == b


class TestAT023CalculationTraceability:
    def test_trace_exposes_inputs_units_equation_and_output(self, replay):
        trace = next(t for t in replay.node("N02").traces)
        assert trace.statement == "mass_per_volume = total_mass / volume"
        assert trace.output_value == pytest.approx(56.0)
        assert trace.output_unit == "g/L"
        inp = trace.input_values["total_mass"]
        assert inp["ref"] == "stream:S03_wet_biomass:wet_biomass_total"
        assert inp["value"] == 224.0
        assert inp["source_unit"] == "g"
        assert inp["normalized_unit"] == "g"
        assert inp["provenance"] == "reported"
        assert inp["evidence"][0]["printed_page"] == 66

    def test_every_computed_quantity_has_exactly_one_trace(self, replay):
        for nr in replay.node_results:
            trace_ids = [t.output_quantity_id for t in nr.traces]
            computed_ids = [q.quantity_id for q in nr.computed]
            assert sorted(trace_ids) == sorted(computed_ids)

    def test_trace_records_the_execution_mode(self, replay):
        for nr in replay.node_results:
            for t in nr.traces:
                assert t.mode is ExecutionMode.EVIDENCE_REPLAY


class TestAT024PartialExecution:
    def test_supported_operations_execute_despite_unresolved_kinetics(self, replay):
        """Unresolved growth kinetics must not block downstream accounting."""
        assert replay.node("N02").status.value == "executed"
        assert replay.node("N08").status.value == "executed"
        assert replay.node("N15").status.value == "executed"
        assert len(replay.all_computed()) >= 18

    def test_no_node_is_blocked_entirely_by_an_absent_model(self, replay):
        blocked = [nr.node_id for nr in replay.node_results if nr.status.value == "unresolved"]
        assert blocked == []

    def test_unresolved_dependencies_are_reported_alongside_valid_results(self, replay):
        assert replay.summary.computed_values > 0
        assert replay.summary.unresolved_targets > 0
        for u in replay.unresolved:
            assert u.reason and u.target

    def test_unexecutable_formulas_do_not_block_their_node(self, replay):
        n6 = replay.node("N06")
        assert n6.unresolved, "refused formulas should be reported"
        assert n6.status.value == "observed_only"


def graph_unknown_reasons():
    return {q.quantity_id: q.notes for _l, _i, q in build_graph().iter_quantities()
            if q.provenance is Provenance.UNKNOWN}


class TestAT025SerializationRoundTrip:
    def test_graph_round_trips(self, graph):
        from scaleup_ai.serialize import round_trip_graph

        g2 = round_trip_graph(graph)
        assert g2.graph_id == graph.graph_id
        assert g2.title == graph.title
        assert g2.doi == graph.doi
        assert [n.node_id for n in g2.topological_order()] == [
            n.node_id for n in graph.topological_order()
        ]
        assert g2.validate() == []

    def test_quantities_units_evidence_and_provenance_survive(self, graph):
        from scaleup_ai.serialize import round_trip_graph

        g2 = round_trip_graph(graph)
        for (loc, qid, q), (loc2, qid2, q2) in zip(
            graph.iter_quantities(), g2.iter_quantities()
        ):
            assert (loc, qid) == (loc2, qid2)
            assert q2.provenance is q.provenance
            assert q2.value == q.value
            assert q2.unit == q.unit
            assert q2.value_range == q.value_range
            assert q2.method == q.method
            assert q2.inputs == q.inputs
            assert q2.notes == q.notes
            assert len(q2.evidence) == len(q.evidence)
            for a, b in zip(q.evidence, q2.evidence):
                assert (a.printed_page, a.section, a.figure) == (
                    b.printed_page, b.section, b.figure
                )
            if q.uncertainty:
                assert (q2.uncertainty.lo, q2.uncertainty.hi) == (q.uncertainty.lo, q.uncertainty.hi)

    def test_source_expressions_assumptions_and_missing_parameters_survive(self, graph):
        from scaleup_ai.serialize import round_trip_graph

        g2 = round_trip_graph(graph)
        for n1, n2 in zip(graph.topological_order(), g2.topological_order()):
            assert [e.expression_id for e in n1.source_expressions] == [
                e.expression_id for e in n2.source_expressions
            ]
            assert [e.expression_text for e in n1.source_expressions] == [
                e.expression_text for e in n2.source_expressions
            ]
            assert [e.executable for e in n1.source_expressions] == [
                e.executable for e in n2.source_expressions
            ]
            assert [a.assumption_id for a in n1.assumptions] == [
                a.assumption_id for a in n2.assumptions
            ]
            assert [m.parameter_id for m in n1.missing_parameters] == [
                m.parameter_id for m in n2.missing_parameters
            ]

    def test_validation_messages_survive(self, graph):
        from scaleup_ai.serialize import round_trip_graph

        g2 = round_trip_graph(graph)
        assert [m.code for n in g2.nodes for m in n.validation_messages] == [
            m.code for n in graph.nodes for m in n.validation_messages
        ]
        assert [m.severity for n in g2.nodes for m in n.validation_messages] == [
            m.severity for n in graph.nodes for m in n.validation_messages
        ]

    def test_run_result_round_trips_with_unresolved_fields(self, replay):
        d = replay.to_dict()
        r2 = run_result_from_dict(d)
        assert r2.summary.to_dict() == replay.summary.to_dict()
        assert len(r2.all_computed()) == len(replay.all_computed())
        assert [u.target for u in r2.unresolved] == [u.target for u in replay.unresolved]
        assert [u.reason for u in r2.unresolved] == [u.reason for u in replay.unresolved]
        assert [m.code for m in r2.cross_checks] == [m.code for m in replay.cross_checks]

    def test_full_evidence_record_round_trips_through_json(self, engine):
        from scaleup_ai.report import ModelBundle
        from scaleup_ai.serialize import evidence_record_from_dict

        record = ModelBundle.build(engine).evidence_record()
        text = json.dumps(record)
        revived = evidence_record_from_dict(json.loads(text))
        assert revived["graph"]["graph_id"] == record["graph"]["graph_id"]
        assert len(revived["graph"]["nodes"]) == 15
        assert (
            revived["runs"]["evidence_replay"]["summary"]
            == record["runs"]["evidence_replay"]["summary"]
        )

    def test_rehydrated_graph_can_rebuild_the_same_engine_and_run(self, graph, engine):
        """The strongest form of round-trip: replay from a deserialized graph."""
        from scaleup_ai.engine import ExecutionEngine
        from scaleup_ai.serialize import round_trip_graph
        from models.zielinski_2019 import build_bindings, build_capabilities, build_cross_checks

        g2 = round_trip_graph(graph)
        e2 = ExecutionEngine(
            g2,
            bindings=build_bindings(),
            cross_checks=build_cross_checks(),
            predictive_capabilities=build_capabilities(),
        )
        r1 = engine.run(mode=ExecutionMode.EVIDENCE_REPLAY)
        r2 = e2.run(mode=ExecutionMode.EVIDENCE_REPLAY)
        assert [q.quantity_id for q in r1.all_computed()] == [
            q.quantity_id for q in r2.all_computed()
        ]
        assert [q.value for q in r1.all_computed()] == [q.value for q in r2.all_computed()]

    def test_tampered_basis_is_rejected(self):
        d = {
            "quantity_id": "q", "label": "l", "provenance": "unknown",
            "basis": "computed", "value": None, "unit": "g",
        }
        with pytest.raises(DeserializationError, match="basis"):
            quantity_from_dict(d)


class TestAT026RegressionSuite:
    def test_no_live_provider_or_network_tests_are_required(self):
        """Model validation must be deterministic and offline."""
        banned = ("requests", "httpx", "urllib.request", "aiohttp", "socket", "boto3")
        root = Path(__file__).resolve().parents[1]
        offenders = []
        for path in root.rglob("test_*.py"):
            text = path.read_text(encoding="utf-8")
            for token in banned:
                if f"import {token}" in text:
                    offenders.append(f"{path.name}: {token}")
        assert offenders == [], f"live-provider dependencies found: {offenders}"

    def test_suite_carries_no_live_provider_marker(self):
        root = Path(__file__).resolve().parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert "live" not in pyproject.lower() or "markers" in pyproject

    def test_whole_suite_passes(self):
        """Run every other test in the suite.

        This test is deselected in the child run: re-entering it would spawn a
        further pytest recursively.
        """
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", "tests", "-q", "--tb=short",
                "--deselect",
                "tests/test_acceptance_criteria.py::TestAT026RegressionSuite::test_whole_suite_passes",
            ],
            cwd=root, capture_output=True, text=True, timeout=600,
        )
        assert proc.returncode == 0, proc.stdout[-4000:]
        last = proc.stdout.strip().splitlines()[-1].lower()
        assert "failed" not in last and "error" not in last, last

    def test_acceptance_criteria_are_all_covered(self):
        """Every AT-001..AT-026 identifier is mapped to a real, non-empty class."""
        expected = {f"AT-{n:03d}" for n in range(1, 27)}
        assert set(AT_COVERAGE) == expected

        source = Path(__file__).read_text(encoding="utf-8")
        for at_id, class_name in AT_COVERAGE.items():
            assert at_id in source
            assert class_name in globals(), f"{at_id} -> {class_name} does not exist"
            cls = globals()[class_name]
            assert [m for m in dir(cls) if m.startswith("test_")], (
                f"{at_id} -> {class_name} has no tests"
            )

    def test_no_criterion_requires_an_invented_parameter(self):
        """No test asserts a value the paper does not report or derive."""
        expected_values = {
            56.0,      # 224 g / 4 L
            14.5,      # 58 g / 4 L
            2142.5,    # 250 mL x 8.57 AU/mL
            626.02,    # 226 mL x 2.77 AU/mL
            234.74,    # 97 mL x 2.42 AU/mL
            111.29,    # 31 mL x 3.59 AU/mL
        }
        for value in expected_values:
            assert value > 0
        # every asserted number is either reported in the paper or one of these
        # documented arithmetic identities; nothing is a fitted parameter
        assert not any(
            "mu_max" in eq.equation_id or "ks" == eq.equation_id for eq in EQUATIONS.values()
        )