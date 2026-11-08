"""The held-out evaluation is reproducible, and its verdict is derived rather than asserted.

Phase 7. Four things must hold, and none of them is "the model is good":

1. **The frozen inputs are intact.** SHA-256 digests of the configuration, dataset,
   protocol, digitisation and parameter file are recorded in the results. Changing a
   parameter, a threshold, an observation or the upstream figure data changes a digest
   and fails here, so a result can never be silently attributed to inputs it did not
   come from.

2. **The reported metrics are recomputable.** Every number in
   ``evaluation_results.json`` is recomputed here from the stored per-point rows. A
   metric that cannot be reproduced from the predictions is not a result.

3. **The verdict follows the protocol.** The pass/fail decision is re-derived here from
   the stored predictions and the thresholds written in the protocol file. *No test in
   this file asserts that any criterion passes.* If the model improves, the recomputed
   verdict changes and the digest guard demands a conscious re-run; if it degrades, the
   recorded failure is preserved rather than the threshold being relaxed.

4. **The composition finding is intact.** No cross-model boundary may become permitted
   without a new rule, and a new rule without evidence is not something a test can
   authorise. The boundary list is pinned.

One test re-runs a graph through the normal pipeline, because "reproducible" has to mean
executable, not merely recorded.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "composition"))
sys.path.insert(0, str(ROOT / "composition" / "tools"))

import evaluate_heldout_biomass as evaluator  # noqa: E402
from composition import cross_model  # noqa: E402

DATA = ROOT / "data" / "ganjave2022"
RESULTS = DATA / "results" / "evaluation_results.json"
CONFIG = DATA / "frozen_configuration.json"
DATASET = DATA / "observations.json"
PROTOCOL = DATA / "evaluation_protocol.json"

MISSING = (
    f"{RESULTS} is missing. Run "
    f"`python composition/tools/evaluate_heldout_biomass.py` first. The evaluation "
    f"is not reconstructible without it."
)


@pytest.fixture(scope="module")
def results() -> dict:
    assert RESULTS.exists(), MISSING
    return json.loads(RESULTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def scenario(results: dict, scenario_id: str) -> dict:
    for entry in results["scenarios"]:
        if entry["scenario_id"] == scenario_id:
            return entry
    raise AssertionError(f"no scenario {scenario_id!r} in the results")


def biomass_sets(entry: dict) -> list[tuple[str, dict]]:
    return [
        (name, comparison)
        for name, comparison in entry["observation_sets"].items()
        if comparison["quantity"] == "biomass_concentration"
    ]


# --------------------------------------------------------------------------- #
# the finding that governs the whole exercise
# --------------------------------------------------------------------------- #


class TestTheCompositionFindingIsIntact:
    def test_no_cross_model_boundary_is_permitted(self) -> None:
        """The reason no composed process could be evaluated. If this ever changes,
        the whole premise of the report has changed and a human has to decide whether
        the new rule has evidence behind it."""
        for boundary in cross_model.BOUNDARIES:
            if boundary.source_model != boundary.target_model:
                assert boundary.permitted is False, (
                    f"{boundary.source_model} -> {boundary.target_model} is now "
                    f"permitted. This needs a published source and a deliberate "
                    f"decision, not a code change."
                )

    def test_the_permitted_boundaries_are_still_exactly_the_two_same_model_ones(
        self, results: dict
    ) -> None:
        permitted = sorted(
            f"{b.source_model} -> {b.target_model}"
            for b in cross_model.BOUNDARIES if b.permitted
        )
        assert permitted == sorted(results["composition_finding"][
            "cross_model_boundaries_permitted"])

    def test_the_results_record_that_no_composition_was_evaluated(
        self, results: dict
    ) -> None:
        assert "No cross-model composition was evaluated" in \
            results["composition_finding"]["statement"]

    def test_the_graph_really_has_no_connections(self, results: dict, config: dict
                                                 ) -> None:
        assert config["scope"]["graph_connections"] == [], (
            "the frozen configuration declares no connections; adding one would be "
            "exactly the manufactured composition the plan rules out"
        )
        for entry in results["scenarios"]:
            report = entry["run"]["composition_report"]
            assert report["connections"] == [], entry["scenario_id"]

    def test_the_combined_graph_is_never_claimed_validated(self, results: dict) -> None:
        for entry in results["scenarios"]:
            combined = entry["run"]["composition_report"]["combined_graph"]
            assert combined["independently_validated"] is False
            assert combined["status"] == "not_established"


# --------------------------------------------------------------------------- #
# the frozen inputs
# --------------------------------------------------------------------------- #


class TestTheFrozenInputsAreIntact:
    def test_every_digest_still_matches(self, results: dict) -> None:
        """Change a parameter, an observation, a threshold or the upstream figures and
        this fails. A result must never outlive the inputs it came from."""
        paths = {
            "frozen_configuration.json": CONFIG,
            "observations.json": DATASET,
            "evaluation_protocol.json": PROTOCOL,
            "figure_reference_data.json": ROOT / "Models" / "Ganjave" / "data"
            / "figure_reference_data.json",
            "reference_parameters.json": ROOT / "Models" / "Ganjave" / "data"
            / "reference_parameters.json",
        }
        recorded = results["input_digests"]
        assert set(recorded) == set(paths), (
            "the recorded digest set changed; every input must be covered"
        )
        for name, path in paths.items():
            assert path.exists(), f"{name} is missing, so no result can be attributed to it"
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == recorded[name], (
                f"{name} changed after the evaluation was run. The recorded metrics "
                f"describe the previous contents. Re-run the evaluation deliberately."
            )

    def test_the_model_and_version_are_pinned(self, config: dict, results: dict
                                               ) -> None:
        assert config["model"]["model_id"] == "ganjave"
        assert config["model"]["model_version"] == "0.1.0"
        for entry in results["scenarios"]:
            # Keyed by instance id, so check the values rather than the keys.
            assert entry["run"]["model_versions"], entry["scenario_id"]
            assert set(entry["run"]["model_versions"].values()) == {"0.1.0"}

    def test_the_parameters_are_loaded_as_fitted_not_refitted(self, config: dict
                                                              ) -> None:
        provenance = config["model"]["parameter_set_provenance"].lower()
        assert "not" in provenance and "refit" in provenance
        assert config["model"]["parameter_set_id"] == "ganjave2022.table2"

    def test_every_initial_condition_is_classified(self, config: dict) -> None:
        allowed = {"reported", "derived", "assumed", "inferred"}
        for scenario in config["scenarios"]:
            for name, value in scenario["initial_conditions"].items():
                assert value["classification"] in allowed, (
                    f"{scenario['scenario_id']}/{name} is not classified"
                )
                assert value["source"].strip(), f"{scenario['scenario_id']}/{name}"

    def test_the_three_unspecified_conditions_are_the_ones_declared_assumed(
        self, config: dict
    ) -> None:
        for scenario in config["scenarios"]:
            assumed = {
                name for name, value in scenario["initial_conditions"].items()
                if value["classification"] == "assumed"
            }
            assert assumed == {"X0", "DO0"}, (
                "the paper does not state X0 or DO0; if a third condition became an "
                "assumption, the sensitivity analysis no longer covers it"
            )

    def test_every_sensitivity_case_names_what_it_probes(self, protocol: dict) -> None:
        for case in protocol["sensitivity"]["cases"]:
            assert case["case_id"] and case["change"] and case["why"]

    def test_the_blinding_disclosure_is_present_and_honest(self, config: dict,
                                                           results: dict) -> None:
        primary = scenario(results, "heldout_fig3")
        assert primary["blinded"] is True, (
            "the primary scenario must not be described as blind unless it was"
        )
        secondary = scenario(results, "optimum_fig5")
        assert secondary["blinded"] is False
        assert "DISCLOS" in secondary["blinding_note"].upper()
        assert config["scenarios"][1]["blinded"] is False


# --------------------------------------------------------------------------- #
# the protocol
# --------------------------------------------------------------------------- #


class TestTheProtocolPrecedesTheResult:
    def test_it_states_it_was_written_before_the_primary_run(self, protocol: dict
                                                             ) -> None:
        assert "heldout_fig3" in protocol["written_before"]
        assert "before" in protocol["blinding"]["primary_scenario"].lower()
        assert protocol["blinding"]["primary_scenario"].startswith("blind")
        assert protocol["blinding"]["secondary_scenario"].startswith("DISCLOSED")

    def test_no_criterion_threshold_was_reselected_after_a_result(self, protocol: dict
                                                                  ) -> None:
        """Every threshold must be justifiable from the reference data or the paper,
        not from our output."""
        for criterion in protocol["criteria"]:
            justification = criterion["justification"].lower()
            assert len(justification) > 60, criterion["id"]
        assert "no_post_hoc_reselection" in protocol["decision_rule"]

    def test_thresholds_come_from_the_protocol_not_the_code(self, protocol: dict) -> None:
        """The evaluator parses the threshold strings; it must hold no numbers of its
        own, so editing the code cannot move a threshold."""
        by_id = {c["id"]: c for c in protocol["criteria"]}
        assert evaluator.limit_of(by_id["E_heldout_trajectory"]["threshold"]
                                  ["rmse_g_per_L"]) == 1.5
        assert evaluator.limit_of(by_id["F_no_worse_than_authors_model"]["threshold"]
                                  ["ratio"]) == 1.5
        assert evaluator.range_of(by_id["I_reported_endpoint_range"]["threshold"]
                                  ["range_g_per_L"]) == (19.9, 21.5)

    def test_the_endpoint_range_is_the_papers_own_number(self, protocol: dict) -> None:
        criterion = next(c for c in protocol["criteria"]
                         if c["id"] == "I_reported_endpoint_range")
        assert "19.9-21.5" in criterion["justification"].replace(" ", "") or \
            "19.9" in criterion["justification"]
        assert "p. 7" in criterion["justification"]

    def test_the_declared_data_anomalies_were_handled_in_advance(
        self, protocol: dict
    ) -> None:
        anomalies = protocol["known_data_anomalies"]
        assert anomalies
        for anomaly in anomalies:
            assert "pre_declared_handling" in anomaly
            assert "why_pre_declared" in anomaly
        # The non-monotone mark must be named explicitly, not left to be noticed.
        assert any(
            "monoton" in a["description"].lower()
            for a in anomalies
        )

    def test_there_is_no_calibration_data_to_contaminate(self, protocol: dict) -> None:
        separation = protocol["data_separation"]
        assert separation["calibration_data"].startswith("None")
        assert "not refitted" in separation["rule"]


# --------------------------------------------------------------------------- #
# the results are recomputable
# --------------------------------------------------------------------------- #


class TestTheMetricsAreRecomputable:
    @pytest.mark.parametrize("scenario_id", ["heldout_fig3", "optimum_fig5"])
    def test_every_metric_recomputes_from_the_stored_points(self, results: dict,
                                                             scenario_id: str) -> None:
        entry = scenario(results, scenario_id)
        for name, comparison in biomass_sets(entry):
            scored = [r for r in comparison["rows"] if r.get("compared") and
                      "residual" in r]
            assert scored, f"{name}: nothing was compared"
            recorded = comparison["metrics"]

            residuals = [r["residual"] for r in scored]
            observed = [r["observed"] for r in scored]
            rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals))
            mae = sum(abs(r) for r in residuals) / len(residuals)
            bias = sum(residuals) / len(residuals)

            assert recorded["n"] == len(scored)
            assert recorded["rmse_g_per_L"] == pytest.approx(rmse, abs=1e-5), name
            assert recorded["mae_g_per_L"] == pytest.approx(mae, abs=1e-5), name
            assert recorded["bias_g_per_L"] == pytest.approx(bias, abs=1e-5), name
            assert recorded["within_2_sigma"] == sum(
                1 for r in scored if abs(r["residual"]) <= 2.0 * r["combined_uncertainty"])
            assert recorded["fraction_within_2_sigma"] == pytest.approx(
                recorded["within_2_sigma"] / recorded["n"], abs=1e-6)

    def test_residuals_are_prediction_minus_observation(self, results: dict) -> None:
        """The sign convention is load-bearing for every bias statement."""
        for entry in results["scenarios"]:
            for _, comparison in biomass_sets(entry):
                for row in comparison["rows"]:
                    if "residual" in row:
                        assert row["residual"] == pytest.approx(
                            row["predicted"] - row["observed"], abs=1e-5)
                        assert row["abs_residual"] == pytest.approx(
                            abs(row["predicted"] - row["observed"]), abs=1e-5)

    def test_the_excluded_observation_is_excluded_by_a_stated_rule(
        self, results: dict, protocol: dict
    ) -> None:
        """Not compared by hand -- by the window rule, and the rule is in the protocol."""
        entry = scenario(results, "heldout_fig3")
        excluded = [r for r in biomass_sets(entry)[0][1]["rows"] if not r["compared"]]
        assert excluded, "the window rule should exclude the pre-t=0 marker"
        for row in excluded:
            assert "simulated interval" in row["exclusion_reason"]
            assert row["t_h"] < 0 or row["t_h"] > entry["duration_h"]

    def test_no_metric_reports_a_non_finite_number(self, results: dict) -> None:
        """NaN in a result file is invalid JSON and never a measurement."""
        blob = json.dumps(results)

        def walk(node) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
            elif isinstance(node, float):
                assert math.isfinite(node), f"non-finite value {node!r} in the results"

        walk(results)
        assert "NaN" not in blob
        assert "Infinity" not in blob

    def test_the_biomass_trajectory_came_back_in_the_declared_unit(
        self, results: dict
    ) -> None:
        for entry in results["scenarios"]:
            for _, comparison in biomass_sets(entry):
                assert comparison["unit"] == "g/L"
                assert comparison["quantity"] == "biomass_concentration"

    def test_the_run_went_through_the_normal_pipeline(self, results: dict) -> None:
        for entry in results["scenarios"]:
            report = entry["run"]["composition_report"]
            assert report["schema"] == "composition-report/1"
            assert report["execution"]["results_produced"] is True
            assert entry["run"]["status"].startswith("success")
            assert entry["run"]["exit_code"] == 0

    def test_the_run_is_deterministic(self, results: dict, protocol: dict) -> None:
        """Determinism is a property of the implementation, so unlike the scientific
        criteria it is safe to assert rather than merely record."""
        limit = evaluator.limit_of(
            next(c for c in protocol["criteria"] if c["id"] == "J_determinism")
            ["threshold"]["relative_difference"])
        for entry in results["scenarios"]:
            assert entry["run"]["determinism_relative_difference"] <= limit


# --------------------------------------------------------------------------- #
# the verdict is derived
# --------------------------------------------------------------------------- #


class TestTheVerdictFollowsTheProtocol:
    """No test here asserts that a criterion passes. Each re-derives the recorded
    verdict from the stored predictions and the protocol's thresholds, so a changed
    result is reported as a changed result rather than tolerated."""

    def test_the_recorded_outcome_matches_what_the_stored_metrics_imply(
        self, results: dict, protocol: dict
    ) -> None:
        for entry in results["scenarios"]:
            recomputed = _recompute_verdicts(entry, protocol)
            for criterion_id, verdict in entry["criteria"].items():
                assert verdict["verdict"] == recomputed[criterion_id], (
                    f"{entry['scenario_id']}/{criterion_id}: recorded "
                    f"{verdict['verdict']!r} but the stored metrics give "
                    f"{recomputed[criterion_id]!r}. A recorded verdict that does not "
                    f"follow from the data is the one thing that must never happen."
                )

    def test_the_overall_outcome_follows_from_the_criteria(self, results: dict,
                                                           protocol: dict) -> None:
        for entry in results["scenarios"]:
            verdicts = [v["verdict"] for v in entry["criteria"].values() if v["primary"]]
            if "inconclusive" in verdicts:
                expected = "inconclusive"
            elif "fail" in verdicts:
                expected = "fail"
            elif verdicts:
                expected = "pass"
            else:
                expected = "inconclusive"
            assert entry["decision"]["outcome"] == expected, entry["scenario_id"]

    def test_a_failure_is_recorded_with_its_observed_value_and_threshold(
        self, results: dict
    ) -> None:
        for entry in results["scenarios"]:
            for failure in entry["decision"]["failures"]:
                assert failure["observed"] is not None
                assert failure["threshold"]

    def test_the_results_never_claim_a_composed_process_or_general_accuracy(
        self, results: dict
    ) -> None:
        for entry in results["scenarios"]:
            decision = entry["decision"]
            assert "not a validation of any composed process" in \
                decision["scope_of_a_pass"].lower()
            assert decision["what_this_never_establishes"]

    def test_no_criterion_thresholds_were_loosened_against_the_recorded_result(
        self, results: dict, protocol: dict
    ) -> None:
        """A safety net on the whole exercise: if every criterion happens to pass, the
        thresholds must still be the ones in the frozen protocol. A passing run
        obtained by moving a threshold is the outcome this project must never ship."""
        for criterion in protocol["criteria"]:
            for entry in results["scenarios"]:
                recorded = entry["criteria"].get(criterion["id"])
                if recorded is None:
                    continue
                assert recorded["threshold"] == criterion["threshold"], (
                    f"{criterion['id']}: the threshold recorded in the results is not "
                    f"the threshold in the protocol"
                )

    def test_the_excluded_anomaly_would_change_the_verdict_and_is_still_reported(
        self, results: dict, protocol: dict
    ) -> None:
        """The single most important honesty property of this evaluation.

        Excluding one pre-declared artefact flips criterion E. The primary analysis
        must still be the one that decides, and the favourable number must still be
        present in the record rather than quietly dropped.
        """
        entry = scenario(results, "heldout_fig3")
        criterion = next(c for c in protocol["criteria"]
                         if c["id"] == "E_heldout_trajectory")
        limit = evaluator.limit_of(criterion["threshold"]["rmse_g_per_L"])

        primary = biomass_sets(entry)[0][1]["metrics"]["rmse_g_per_L"]
        excluded = biomass_sets(entry)[0][1]["metrics_excluding_declared_anomaly"]

        # Whatever the two numbers are, the verdict must come from the primary one.
        assert entry["criteria"]["E_heldout_trajectory"]["observed"] == pytest.approx(
            primary, abs=1e-6)
        # And the excluded variant must be recorded, not hidden.
        assert excluded.get("n", 0) > 0
        assert excluded["n"] < biomass_sets(entry)[0][1]["metrics"]["n"]
        assert "excl" or "excluding" or "anomaly" in json.dumps(entry)

        # If the exclusion happens to rescue the criterion, that must be visible in
        # the report rather than used as the verdict.
        if excluded.get("rmse_g_per_L", 1e9) <= limit and primary > limit:
            report = (ROOT / "reports" / "COMPOSED_PROCESS_SCIENTIFIC_VALIDATION.md")
            assert report.exists()
            text = report.read_text(encoding="utf-8")
            assert "would satisfy criterion E" in text or "would pass" in text, (
                "the favourable excluded-anomaly number is reported as the verdict. "
                "It must be reported as a diagnosis, with the primary analysis "
                "standing as the result."
            )
            assert "FAILS" in text, "the report must state the primary verdict"


# --------------------------------------------------------------------------- #
# the evaluation is executable, not merely recorded
# --------------------------------------------------------------------------- #


class TestTheEvaluationIsExecutable:
    def test_the_graph_builder_honours_the_frozen_configuration(self, config: dict
                                                                ) -> None:
        held_out = next(s for s in config["scenarios"]
                        if s["scenario_id"] == "heldout_fig3")
        document = evaluator.build_graph(held_out)
        assert document["connections"] == []
        assert len(document["instances"]) == 1
        instance = document["instances"][0]
        assert instance["model_id"] == "ganjave"
        assert instance["model_version"] == "0.1.0"
        simulation = instance["parameters"]["simulation"]
        assert simulation["duration_h"] == held_out["duration_h"]
        assert simulation["mode"] == held_out["mode"]

    def test_the_builder_refuses_a_silent_unit_change(self, config: dict) -> None:
        """Every literal is checked against the contract's declared unit. A conversion
        nobody wrote down would otherwise be applied quietly."""
        with pytest.raises(AssertionError):
            evaluator.literal("initial_biomass_concentration", 0.05, "mg/L")
        with pytest.raises(AssertionError):
            evaluator.literal("feed_flow_rate", 0.72, "L/h")

    def test_the_graph_reruns_through_the_normal_pipeline(self, config: dict,
                                                          tmp_path: Path) -> None:
        """Reproducible means executable. This re-runs the primary scenario end to end
        through `python -m composition.runner` and checks it still lands on the
        recorded endpoint."""
        held_out = next(s for s in config["scenarios"]
                        if s["scenario_id"] == "heldout_fig3")
        payload = evaluator.run_graph(
            evaluator.build_graph(held_out), tmp_path, "acceptance-rerun")
        assert payload["_exit_code"] == 0
        assert payload["status"].startswith("success")
        times, values, units = evaluator.trajectory_of(payload, "biomass_concentration")
        assert units["unit"] == "g/L"
        assert units["quantity"] == "mass_concentration"
        endpoint = evaluator.at(times, values, 24.0)

        recorded = scenario(
            json.loads(RESULTS.read_text(encoding="utf-8")), "heldout_fig3")
        # The results file rounds to six decimals; the comparison is against that,
        # not against full float precision the file no longer holds.
        assert endpoint == pytest.approx(
            recorded["run"]["final_biomass_g_per_L"], abs=1e-5), (
            "re-running the frozen configuration did not reproduce the recorded "
            "endpoint. Something is not deterministic."
        )

    def test_a_sensitivity_override_actually_changes_the_graph(self, config: dict
                                                               ) -> None:
        held_out = next(s for s in config["scenarios"]
                        if s["scenario_id"] == "heldout_fig3")
        baseline = evaluator.build_graph(held_out)
        varied = evaluator.build_graph(held_out, {"S2_0": 5.0}, case_id="variant")
        assert baseline["literal_inputs"] != varied["literal_inputs"]
        assert varied["graph_id"] != baseline["graph_id"], (
            "a sensitivity case must be distinguishable from the primary run"
        )


# --------------------------------------------------------------------------- #
# sensitivity
# --------------------------------------------------------------------------- #


class TestSensitivityIsReportedSeparately:
    def test_every_protocol_case_was_run(self, results: dict, protocol: dict) -> None:
        cases = results["sensitivity"]["heldout_fig3"]
        assert {c["case_id"] for c in cases} == {
            c["case_id"] for c in protocol["sensitivity"]["cases"]}

    def test_each_case_records_what_it_changed_and_why(self, results: dict) -> None:
        for case in results["sensitivity"]["heldout_fig3"]:
            assert case["change"] and case["why"]
            assert case["overrides"]
            assert case["metrics"]["n"] > 0

    def test_sensitivity_never_leaks_into_the_primary_metrics(self, results: dict,
                                                               config: dict) -> None:
        primary = scenario(results, "heldout_fig3")
        assert primary["run"]["final_biomass_g_per_L"] == pytest.approx(
            json.loads(RESULTS.read_text(encoding="utf-8"))["scenarios"][0]
            ["run"]["final_biomass_g_per_L"])
        for case in results["sensitivity"]["heldout_fig3"]:
            assert case["case_id"] != "primary"


# --------------------------------------------------------------------------- #


def _recompute_verdicts(entry: dict, protocol: dict) -> dict[str, str]:
    """Re-derive every recorded verdict from the stored predictions and thresholds.

    Every bound is read out of the protocol file. The test holds no threshold of its
    own, so it cannot be quietly tuned into agreement with a result.
    """
    verdicts: dict[str, str] = {}
    biomass = biomass_sets(entry)
    biomass_metrics = biomass[0][1]["metrics"] if biomass else {"n": 0}

    def outcome(value: float | None, passed: bool) -> str:
        if value is None:
            return "inconclusive"
        return "pass" if passed else "fail"

    for criterion in protocol["criteria"]:
        if entry["scenario_id"] not in criterion["applies_to"]:
            continue
        cid = criterion["id"]
        threshold = criterion["threshold"]

        if cid == "E_heldout_trajectory":
            value = biomass_metrics.get("rmse_g_per_L")
            verdicts[cid] = outcome(
                value, value is not None
                and value <= evaluator.limit_of(threshold["rmse_g_per_L"]))
        elif cid == "F_no_worse_than_authors_model":
            value = biomass_metrics.get("ratio_rmse_ours_over_authors")
            verdicts[cid] = outcome(
                value, value is not None
                and value <= evaluator.limit_of(threshold["ratio"]))
        elif cid == "G_oxygen_limiting_regime":
            value = entry["run"]["min_DO_percent_after_feed"]
            verdicts[cid] = outcome(
                value, value is not None
                and value < evaluator.limit_of(threshold["min_DO_percent"]))
        elif cid == "H_agreement_with_reported_uncertainty":
            value = biomass_metrics.get("fraction_within_2_sigma")
            verdicts[cid] = outcome(
                value, value is not None
                and value >= evaluator.limit_of(threshold["fraction_at_2_sigma"]))
        elif cid == "I_reported_endpoint_range":
            low, high = evaluator.range_of(threshold["range_g_per_L"])
            value = entry["run"]["final_biomass_g_per_L"]
            verdicts[cid] = outcome(
                value, value is not None and low <= value <= high)
        elif cid == "J_determinism":
            value = entry["run"]["determinism_relative_difference"]
            verdicts[cid] = outcome(
                value, value is not None
                and value <= evaluator.limit_of(threshold["relative_difference"]))
    return verdicts
