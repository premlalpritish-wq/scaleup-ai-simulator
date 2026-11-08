"""Invariants the failure investigation established, guarded against recurrence.

Phase 8 of the Ganjave failure investigation. None of these is a model-behaviour test:
no defect was confirmed, so there is nothing to encode as an expected value. What was
established are **invariants about the evidence**, each of which corresponds to a
specific way this failure could be dishonestly disposed of.

The most important is the first: a single observation carries 82.5 % of the squared
error, and excluding it would turn the failing criterion into a pass. The tests here
exist so that this cannot happen quietly -- not because the model failed, and not
because it should pass.

Nothing in this file asserts a scientific outcome. The recorded verdicts are re-derived
elsewhere (``test_heldout_validation.py``); here they are only checked for *drift
against the frozen baseline*, so that a changed result is noticed rather than absorbed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "composition"))
sys.path.insert(0, str(ROOT / "composition" / "tools"))

INVESTIGATION = ROOT / "data" / "ganjave2022" / "investigation"
RESULTS = ROOT / "data" / "ganjave2022" / "results" / "evaluation_results.json"
OBSERVATIONS = ROOT / "data" / "ganjave2022" / "observations.json"
BASELINE = INVESTIGATION / "baseline_primary_result.json"
RESIDUALS = INVESTIGATION / "residuals.json"
PIXEL_CHECK = INVESTIGATION / "digitisation_pixel_check.json"
SHAPE = INVESTIGATION / "trajectory_shape_comparison.json"
AUTHORS = INVESTIGATION / "comparison_with_authors_curve.json"

TOOLS = ROOT / "composition" / "tools"

#: The observation the investigation examined. Named here so the tests read as a
#: statement about a specific, known quantity rather than about "some outlier".
DISPUTED = "fig3b:PDGF:8"


def _load(path: Path) -> dict:
    assert path.exists(), (
        f"{path.relative_to(ROOT)} is missing. The investigation artefacts are "
        f"part of the evidence for the recorded failure; regenerate them with the "
        f"tools in composition/tools/."
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def results() -> dict:
    return _load(RESULTS)


@pytest.fixture(scope="module")
def dataset() -> dict:
    return _load(OBSERVATIONS)


@pytest.fixture(scope="module")
def residuals() -> dict:
    return _load(RESIDUALS)


@pytest.fixture(scope="module")
def baseline() -> dict:
    return _load(BASELINE)


def primary_observations(results: dict) -> list[dict]:
    entry = next(s for s in results["scenarios"]
                 if s["scenario_id"] == "heldout_fig3")
    comparison = next(
        c for c in entry["observation_sets"].values()
        if c["quantity"] == "biomass_concentration")
    return comparison["rows"]


# --------------------------------------------------------------------------- #
# the point that dominates the error must stay in
# --------------------------------------------------------------------------- #


class TestTheDominantObservationIsRetained:
    def test_it_is_still_in_the_frozen_dataset(self, dataset: dict) -> None:
        identifiers = {
            p["observation_id"]
            for s in dataset["observation_sets"] for p in s["points"]
        }
        assert DISPUTED in identifiers, (
            "the observation that dominates the held-out squared error has been "
            "removed from the frozen dataset. That requires independent evidence of a "
            "digitisation error; the pixel check found none."
        )

    def test_it_is_compared_in_the_primary_evaluation(self, results: dict) -> None:
        row = next(r for r in primary_observations(results)
                   if r["observation_id"] == DISPUTED)
        assert row["compared"] is True, (
            "the disputed observation is no longer compared. Excluding it drops the "
            "held-out RMSE below the acceptance threshold, which is exactly the "
            "outcome that must not be obtained this way."
        )
        assert "residual" in row and "predicted" in row

    def test_it_is_recorded_as_materially_disagreeing(self, residuals: dict) -> None:
        """The investigation established that its disagreement is real, not a reading
        artefact. That finding has to stay attached to the number."""
        entry = residuals["scenarios"]["heldout_fig3"]
        row = next(
            r for r in entry["observations"] if r["observation_id"] == DISPUTED)
        assert row["material"] is True
        assert row["share_of_sse"] > 0.5, (
            "a single observation should still dominate the squared error; if that "
            "stopped being true the comparison changed and needs re-examination"
        )

    def test_the_exclusion_variant_is_reported_but_does_not_decide(
        self, results: dict, protocol_path: Path | None = None
    ) -> None:
        """Both numbers stay on the record, and the verdict comes from the one that
        includes every observation."""
        entry = next(s for s in results["scenarios"]
                     if s["scenario_id"] == "heldout_fig3")
        comparison = next(
            c for c in entry["observation_sets"].values()
            if c["quantity"] == "biomass_concentration")
        assert "metrics_excluding_declared_anomaly" in comparison
        assert comparison["metrics_excluding_declared_anomaly"]["n"] < \
            comparison["metrics"]["n"]
        criterion = entry["criteria"]["E_heldout_trajectory"]
        assert criterion["observed"] == pytest.approx(
            comparison["metrics"]["rmse_g_per_L"], abs=1e-6), (
            "the verdict is being taken from the exclusion variant rather than from "
            "the primary analysis"
        )


# --------------------------------------------------------------------------- #
# nothing is read off a clipped plot
# --------------------------------------------------------------------------- #


class TestNothingIsInventedOffAClippedAxis:
    def test_the_paper_curve_above_the_axis_is_recorded_as_unavailable(
        self,
    ) -> None:
        report = _load(AUTHORS)
        rows = report["scenarios"]["heldout_fig3"]["sets"][
            "ganjave2022.heldout_observations.fig3b"]["rows"]
        clipped = [r for r in rows if r.get("authors_off_scale")]
        assert clipped, (
            "the paper's model curve leaves the plot through the top spine after "
            "25 h. If this stops being recorded, the clipping has been lost and a "
            "value may have been read off the axis"
        )
        for row in clipped:
            assert row["authors_curve_g_per_L"] is None, (
                "a value was read for a point where the curve is outside the plot"
            )
            assert row["authors_residual_g_per_L"] is None
            assert row["authors_residual_lower_bound_g_per_L"] > 0, (
                "even off-scale, the curve must be known to disagree with the data by "
                "at least the axis excess"
            )

    def test_the_clipped_row_is_the_disputed_one(self) -> None:
        report = _load(AUTHORS)
        rows = report["scenarios"]["heldout_fig3"]["sets"][
            "ganjave2022.heldout_observations.fig3b"]["rows"]
        clipped = {r["observation_id"] for r in rows if r.get("authors_off_scale")}
        assert clipped == {DISPUTED}

    def test_no_metric_reports_a_non_finite_number(self) -> None:
        for name in (AUTHORS, RESIDUALS, SHAPE):
            text = name.read_text(encoding="utf-8")
            assert "NaN" not in text, f"{name.name} contains NaN"
            assert "Infinity" not in text, f"{name.name} contains Infinity"


# --------------------------------------------------------------------------- #
# the digitisation refutation must survive
# --------------------------------------------------------------------------- #


class TestTheDigitisationRefutationIsRecorded:
    def test_every_mark_matched_its_assigned_series_colour(self) -> None:
        """The investigation refuted 'digitisation artefact' by showing every mark --
        including the disputed one -- sits on the PDGF colour at zero distance.

        This record is from a PDF that is not distributed, so it cannot be recomputed
        in a test. What can be guarded is that the refutation exists and says what it
        said, so nobody later re-asserts the artefact claim without contradicting it.
        """
        report = _load(PIXEL_CHECK)
        marks = report["marks"]
        assert marks
        for mark in marks:
            assert mark["matches_assigned_series"] is True, (
                f"{mark['observation_id']} was recorded as not matching its series; "
                f"the 'digitisation artefact' claim would need re-examining"
            )
            assert mark["colour_distance_to_PDGF"] == 0.0

    def test_the_disputed_mark_is_among_them_verified(self) -> None:
        report = _load(PIXEL_CHECK)
        identifiers = [m["observation_id"] for m in report["marks"]]
        assert DISPUTED in identifiers

    def test_the_reports_state_the_refutation_rather_than_the_artefact_claim(
        self,
    ) -> None:
        """Both documents must carry the corrected finding. A reader who sees only the
        pre-declaration would reach the wrong conclusion about the failure."""
        analysis = (ROOT / "reports" / "GANJAVE_RESIDUAL_ANALYSIS.md").read_text(
            encoding="utf-8")
        investigation = (ROOT / "reports" / "GANJAVE_FAILURE_INVESTIGATION.md").read_text(
            encoding="utf-8")
        for text in (analysis, investigation):
            assert "probable digitisation artefact" in text
            assert "wrong" in text.lower(), (
                "the refutation of the pre-declaration must be stated"
            )


# --------------------------------------------------------------------------- #
# diagnostics must not have perturbed the primary result
# --------------------------------------------------------------------------- #


class TestDiagnosticsAreNonIntrusive:
    #: Tools that read the frozen evaluation and write only into the investigation
    #: directory. None of them runs a simulation, so all four are fast enough to
    #: execute inside a test.
    DIAGNOSTIC_TOOLS = (
        "analyse_residuals.py",
        "compare_with_authors_curve.py",
        "compare_trajectory_shapes.py",
        "verify_digitisation.py",
    )

    def test_running_every_diagnostic_leaves_the_frozen_inputs_untouched(
        self,
    ) -> None:
        """A behavioural check, not a source scan.

        The investigation exists to explain a frozen failure. If any diagnostic
        mutated the results or the dataset it was explaining, the failure under
        investigation would no longer be the failure that was frozen. So: digest
        everything frozen, run every diagnostic, digest again.
        """
        import hashlib
        import subprocess

        watched = [
            RESULTS,
            OBSERVATIONS,
            ROOT / "data" / "ganjave2022" / "evaluation_protocol.json",
            ROOT / "data" / "ganjave2022" / "frozen_configuration.json",
            ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json",
            ROOT / "Models" / "Ganjave" / "data" / "reference_parameters.json",
        ]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched
        }

        import os

        environment = dict(os.environ)
        environment["PYTHONIOENCODING"] = "utf-8"
        for name in self.DIAGNOSTIC_TOOLS:
            tool = TOOLS / name
            assert tool.exists(), f"{name} is referenced but missing"
            completed = subprocess.run(
                [sys.executable, str(tool)],
                cwd=ROOT, capture_output=True, text=True, timeout=600,
                env=environment,
            )
            # verify_digitisation.py exits 0 with a message when the PDF is absent;
            # any other failure is a real problem and should not be swallowed.
            assert completed.returncode == 0, (
                f"{name} failed:\n{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
            )

        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched
        }
        for path in watched:
            assert after[path] == before[path], (
                f"{path.relative_to(ROOT)} changed when the diagnostics ran. The "
                f"failure under investigation must not move while being explained."
            )

    def test_every_diagnostic_wrote_its_artefact_into_the_investigation_directory(
        self,
    ) -> None:
        """The diagnostics' output is evidence and is kept in one place, beside the
        frozen baseline rather than mixed in with the result it explains.

        The figures are included: both reports cite them, and a citation to a missing
        crop is a citation a reader cannot follow.
        """
        expected = (
            RESIDUALS,
            AUTHORS,
            SHAPE,
            PIXEL_CHECK,
            INVESTIGATION / "baseline_primary_result.json",
            INVESTIGATION / "heldout_trajectory_heldout_fig3.svg",
            INVESTIGATION / "heldout_trajectory_optimum_fig5.svg",
            INVESTIGATION / "fig3b_panel.png",
            INVESTIGATION / "fig3b_disputed_region.png",
        )
        for path in expected:
            assert path.exists(), (
                f"{path.name} is missing. The investigation reports cite it, and "
                f"diagnostics regenerate it."
            )
            assert path.parent == INVESTIGATION, (
                f"{path.name} landed outside the investigation directory"
            )

    def test_the_current_results_still_match_the_frozen_baseline(
        self, results: dict, baseline: dict
    ) -> None:
        """Guards against silent drift. This does not assert that the outcome is 'fail'
        or 'pass' -- it asserts the result has not changed since the investigation
        began. If it has, the change must be deliberate and the record updated."""
        for scenario in results["scenarios"]:
            recorded = baseline["scenarios"][scenario["scenario_id"]]
            assert scenario["decision"]["outcome"] == \
                recorded["decision"]["outcome"], scenario["scenario_id"]
            assert scenario["run"]["final_biomass_g_per_L"] == pytest.approx(
                recorded["run"]["final_biomass_g_per_L"], abs=1e-5)
            assert scenario["run"]["min_DO_percent_after_feed"] == pytest.approx(
                recorded["run"]["min_DO_percent_after_feed"], abs=1e-5)

    def test_the_baseline_still_matches_the_frozen_input_digests(
        self, baseline: dict, results: dict
    ) -> None:
        assert baseline["input_digests"] == results["input_digests"], (
            "the frozen inputs changed after the baseline was taken. Every conclusion "
            "in the investigation report was drawn against the previous contents."
        )

    def test_reproduction_status_was_not_upgraded(self) -> None:
        """The investigation explains the failure. It does not make the model valid."""
        composition = ROOT / "Models" / "Ganjave" / "models" / "composition.py"
        source = composition.read_text(encoding="utf-8")
        assert '"not_yet_validated"' in source, (
            "the model's declared reproduction status changed; nothing in the "
            "investigation authorises that"
        )


# --------------------------------------------------------------------------- #
# the shape finding, as an invariant rather than a conclusion
# --------------------------------------------------------------------------- #


class TestTheShapeFindingIsRecorded:
    def test_the_offset_from_the_published_curve_is_flat_not_growing(self) -> None:
        """A flat difference is what rules out a kinetic transcription error. If a
        future change made it grow, that would be a real signal and the audit's
        conclusion would need revisiting -- so the property is pinned."""
        report = _load(SHAPE)
        held_out = report["scenarios"]["heldout_fig3"]
        late = held_out["difference_ours_minus_authors"]["after_12h"]
        assert late["sd_g_per_L"] < 0.5, (
            "the late-phase difference from the published curve is no longer "
            "near-constant; the 'scale term, not a kinetic error' reading no longer "
            "follows"
        )
        assert abs(late["mean_g_per_L"]) > 0.2, (
            "the offset from the published curve has vanished; the audit conclusion "
            "that this implementation sits above the published curve no longer holds"
        )

    def test_both_scenarios_were_compared(self) -> None:
        report = _load(SHAPE)
        assert set(report["scenarios"]) == {"heldout_fig3", "optimum_fig5"}

    def test_the_audit_records_the_table1_operating_conditions(self) -> None:
        """The held-out configuration was checked against the paper's Table 1:
        PDGF, 20 % glycerol, 30 % yeast extract, 0.78 mL/h."""
        configuration = _load(
            ROOT / "data" / "ganjave2022" / "frozen_configuration.json")
        held_out = next(s for s in configuration["scenarios"]
                        if s["scenario_id"] == "heldout_fig3")
        assert held_out["feed"]["S10_g_per_L"]["value"] == 200.0
        assert held_out["feed"]["S20_g_per_L"]["value"] == 300.0
        assert held_out["feed"]["flow_mL_per_h"]["value"] == 0.78
