"""Tests for the scientific validation fixture and its comparison procedure.

These tests are about *evidence*, not about arithmetic.  The hand-calculation
tests live elsewhere; what is checked here is that the reproduction fixture is
traceable, that the comparison against the paper is computed correctly from the
stored reference data, and that nothing can quietly upgrade the model's
reproduction status.

The eight requirements each get at least one test:

1. the fixture carries traceable inputs and units          -> TestFixtureTraceability
2. reported values are distinguishable from inferred and assumed -> TestProvenanceClasses
3. the equations and parameters match the declared model version -> TestModelVersion
4. the fixture executes deterministically                    -> TestDeterminism
5. the quantitative comparisons are computed correctly       -> TestComparisonArithmetic
6. missing reference data and open ambiguities block 'validated' -> TestStatusGuards
7. reproduction thresholds are documented and paper-derived -> TestCriteria
8. the composition contracts, refusance rules and provenance survive -> TestCompositionBoundary
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPO_ROOT = ROOT.parent.parent
COMPOSITION_ROOT = REPO_ROOT / "composition"

FIXTURE = ROOT / "data" / "validation_fig5.json"
REFERENCE = ROOT / "data" / "figure_reference_data.json"
RESULTS = ROOT / "data" / "validation_results.json"
DIGITIZER = ROOT / "tools" / "digitize_figures.py"
PDF = REPO_ROOT / "papers" / "Ganjave et al 2022.pdf"

#: The only classifications this package accepts for a value's provenance.
CLASSIFICATIONS = {"reported", "derived", "assumed", "unavailable"}


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reference() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def results() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def primary_run(fixture) -> dict:
    """The primary case, run once, for the tests that need a trajectory."""
    case = next(c for c in fixture["cases"] if c["case_id"] == "primary")
    cmd = [
        sys.executable, "-m", "models", "simulate",
        "--mode", "fed_batch", "--duration", "24",
        "--X", str(case["X0_g_per_L"]), "--S2", str(case["S2_0_g_per_L"]),
        "--DO", str(case["DO0_percent"]),
        "--S1", "2.76", "--V", "0.1",
        "--glycerol-percent", "17.5", "--yeast-percent", "24.5",
        "--flow-ml-h", "0.72", "--feed-start", "6",
    ]
    completed = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=600, check=True,
    )
    return json.loads(completed.stdout)


def rel_rmse(ours, ref) -> float:
    """The same metric the runner uses, restated so the test checks it."""
    a = np.asarray(ours, dtype=float)
    b = np.asarray(ref, dtype=float)
    scale = float(np.mean(np.abs(b)))
    return float(np.sqrt(np.mean((a - b) ** 2)) / scale * 100.0)


# --------------------------------------------------------------------------- #
# 1. traceable inputs and units
# --------------------------------------------------------------------------- #


class TestFixtureTraceability:
    def test_every_input_carries_a_value_unit_classification_and_source(
        self, fixture
    ) -> None:
        for key, item in fixture["configuration"]["initial_conditions"].items():
            assert isinstance(item["value"], (int, float)), key
            assert item["unit"], key
            assert item["classification"] in CLASSIFICATIONS, key
            assert item["source"], key
            assert item["note"], key

    def test_the_mode_duration_and_solver_are_explicit(self, fixture) -> None:
        config = fixture["configuration"]
        assert config["mode"] == "fed_batch"
        assert config["duration_h"] == 24.0
        assert fixture["model"]["solver"]["rtol"] == 1e-6
        assert fixture["model"]["solver"]["atol"] == 1e-9

    def test_the_feed_is_traceable_to_a_printed_sentence(self, fixture) -> None:
        feed = fixture["configuration"]["feed"]
        assert feed["glycerol_percent_wv"] == 17.5
        assert feed["yeast_extract_percent_wv"] == 24.5
        assert feed["flow_mL_per_h"] == 0.72
        # 1 % w/v = 10 g/L is the paper's own convention, applied here.
        assert feed["S10_g_per_L"] == 175.0
        assert feed["S20_g_per_L"] == 245.0
        assert "p. 7" in feed["source"]

    def test_every_case_states_why_it_exists(self, fixture) -> None:
        for case in fixture["cases"]:
            assert case["case_id"]
            assert case["why"]
            assert set(case) >= {"S2_0_g_per_L", "X0_g_per_L", "DO0_percent"}


# --------------------------------------------------------------------------- #
# 2. reported vs inferred vs assumed
# --------------------------------------------------------------------------- #


class TestProvenanceClasses:
    def test_the_classification_vocabulary_is_exactly_four_values(
        self, fixture
    ) -> None:
        used = {
            item["classification"]
            for item in fixture["configuration"]["initial_conditions"].values()
        }
        used.add(fixture["configuration"]["feed"]["classification"])
        assert used <= CLASSIFICATIONS

    def test_reported_values_are_cited_and_match_the_reference_dataset(
        self, fixture
    ) -> None:
        from models.reference import reported_observations

        reported = {o.observation_id: o for o in reported_observations()}
        config = fixture["configuration"]["initial_conditions"]

        # S1_0 is reported: the fixture, the reference dataset and the paper
        # must all say 2.76 g/L.
        assert config["S1_0"]["classification"] == "reported"
        assert config["S1_0"]["value"] == 2.76
        assert reported["optimisation.selected_recipe_flow"].value == 0.72

        # V0 is reported: 100 mL = 0.1 L.
        assert config["V0"]["classification"] == "reported"
        assert config["V0"]["value"] == 0.1

    def test_a_derived_value_is_not_labelled_reported(self, fixture) -> None:
        """S2_0 is derived from a stated recipe, which is weaker than reported."""
        s2 = fixture["configuration"]["initial_conditions"]["S2_0"]
        assert s2["classification"] == "derived"
        assert s2["value"] == 25.0
        assert "does not state" in s2["note"] or "never states" in s2["note"]

    def test_assumed_values_are_named_as_assumptions(self, fixture) -> None:
        config = fixture["configuration"]["initial_conditions"]
        for key in ("X0", "DO0"):
            assert config[key]["classification"] == "assumed", key

    def test_the_unavailable_items_are_still_listed(self) -> None:
        """What the paper does not give stays visible rather than vanishing."""
        from models.reference import unavailable_data

        items = {u["item"] for u in unavailable_data()}
        assert any("time-course" in i for i in items)
        assert any("OD600" in i for i in items)
        for entry in unavailable_data():
            assert entry["reason"]
            assert entry["consequence"]


# --------------------------------------------------------------------------- #
# 3. equations and parameters match the declared model version
# --------------------------------------------------------------------------- #


class TestModelVersion:
    def test_the_declared_equation_version_is_the_corrected_one(self, fixture) -> None:
        assert fixture["model"]["equations_version"] == "1.1.0"

    def test_the_parameter_set_is_the_printed_table_2(self, fixture) -> None:
        assert fixture["model"]["parameter_set_id"] == "ganjave2022.table2"

    def test_the_run_uses_that_parameter_set_unmodified(self, primary_run) -> None:
        assert primary_run["metadata"]["parameter_set_id"] == "ganjave2022.table2"
        assert primary_run["metadata"]["equations_version"] == "1.1.0"
        # kLa and C* are the two reported (not fitted) oxygen parameters.
        assert primary_run["metadata"]["solver"]["rtol"] == pytest.approx(1e-6)
        assert primary_run["metadata"]["solver"]["atol"] == pytest.approx(1e-9)
        assert primary_run["solver_report"]["steps_taken"] > 0

    def test_no_threshold_is_a_function_of_the_implementation_output(
        self, fixture, results
    ) -> None:
        """A threshold chosen to make a case pass is not a threshold.

        Every number in the fixture's criteria must be a paper quantity: the
        reported range, the stated behaviour, or the paper's own model-data
        scatter and digitization uncertainty.  If any threshold equals a value
        the implementation happened to produce, that would show the threshold
        was fitted to the answer, so the test checks the two sets are disjoint.
        """
        thresholds: list[float] = []
        for criterion in fixture["criteria"]:
            for value in criterion["threshold"].values():
                for number in re.findall(r"[-+]?\d*\.?\d+", value):
                    thresholds.append(float(number))

        produced = {
            round(r["final_biomass_g_per_L"], 6)
            for r in results["cases"] if r["final_biomass_g_per_L"] is not None
        }
        produced.update({
            round(r["biomass_vs_model_prediction"]["relative_rmse_percent"], 6)
            for r in results["cases"]
        })

        offenders = [t for t in thresholds if t in produced]
        assert offenders == [], (
            f"thresholds {offenders} coincide with values the implementation "
            f"produced {sorted(produced)}, which would mean they were chosen "
            f"after seeing the result"
        )

    def test_no_parameter_was_refit_against_the_reference_curves(self, fixture) -> None:
        """The fixture declares the parameter set; it never optimises anything."""
        assert fixture["model"]["parameter_set_provenance"].startswith("Table 2")
        assert "loaded as a fitted set" in fixture["model"]["parameter_set_provenance"]
        assert fixture["model"]["parameter_set_provenance"].endswith(
            "nothing here is refit"
        )
        # A calibration procedure aimed at the reference curves would have to
        # name those curves.  Nothing in the fixture names them as a target to
        # fit to.
        text = FIXTURE.read_text(encoding="utf-8").lower()
        assert "fit to the" not in text
        assert "calibrated to" not in text
        assert "calibration procedure" not in text


# --------------------------------------------------------------------------- #
# 4. determinism within a documented tolerance
# --------------------------------------------------------------------------- #


class TestDeterminism:
    def test_two_runs_of_the_primary_case_agree(self, fixture, primary_run) -> None:
        case = next(c for c in fixture["cases"] if c["case_id"] == "primary")
        again = json.loads(subprocess.run(
            [
                sys.executable, "-m", "models", "simulate",
                "--mode", "fed_batch", "--duration", "24",
                "--X", str(case["X0_g_per_L"]), "--S2", str(case["S2_0_g_per_L"]),
                "--DO", str(case["DO0_percent"]),
                "--S1", "2.76", "--V", "0.1",
                "--glycerol-percent", "17.5", "--yeast-percent", "24.5",
                "--flow-ml-h", "0.72", "--feed-start", "6",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=600, check=True,
        ).stdout)

        assert (primary_run["provenance"]["input_digest"]
                == again["provenance"]["input_digest"])

        worst = 0.0
        for a, b in zip(primary_run["states"], again["states"]):
            for key in ("biomass_concentration_g_per_L",
                        "dissolved_oxygen_percent",
                        "glycerol_concentration_g_per_L"):
                denom = max(abs(a[key]), abs(b[key]), 1e-12)
                worst = max(worst, abs(a[key] - b[key]) / denom)
        assert worst <= 1e-9

    def test_the_runner_records_the_determinism_criterion(self, results) -> None:
        det = results["D_determinism"]
        assert det["pass"] is True
        assert det["observed_worst_relative_difference"] <= 1e-9
        assert det["digests_equal"] is True

    def test_the_input_digest_changes_when_an_input_changes(self, fixture) -> None:
        """A digest that ignores its inputs is not a digest."""
        case = next(c for c in fixture["cases"] if c["case_id"] == "primary")
        other = next(c for c in fixture["cases"] if c["case_id"] == "x0_fourfold")
        assert case["X0_g_per_L"] != other["X0_g_per_L"]

        def digest(c):
            return json.loads(subprocess.run(
                [
                    sys.executable, "-m", "models", "simulate",
                    "--mode", "fed_batch", "--duration", "1",
                    "--X", str(c["X0_g_per_L"]), "--S2", str(c["S2_0_g_per_L"]),
                    "--DO", str(c["DO0_percent"]),
                    "--S1", "2.76", "--V", "0.1",
                    "--glycerol-percent", "17.5", "--yeast-percent", "24.5",
                    "--flow-ml-h", "0.72", "--feed-start", "6",
                ],
                cwd=ROOT, capture_output=True, text=True, timeout=600, check=True,
            ).stdout)["provenance"]["input_digest"]

        assert digest(case) != digest(other)


# --------------------------------------------------------------------------- #
# 5. the comparisons are computed correctly from the stored reference data
# --------------------------------------------------------------------------- #


class TestComparisonArithmetic:
    def test_the_biomass_rmse_is_recomputed_from_the_stored_reference(
        self, fixture, reference, primary_run, results
    ) -> None:
        panel = reference["figures"]["6"]["panels"]["c"]
        curve = [s for s in panel["series"]["Model_predicted"]["samples"]
                 if s.get("value") is not None and s["t_h"] <= 24.0]
        ts = np.array([s["t_h"] for s in curve])
        ref_vals = np.array([s["value"] for s in curve])

        states = primary_run["states"]
        t_all = np.array([s["t_h"] for s in states])
        ours = np.array([np.interp(t, t_all, [s["biomass_concentration_g_per_L"]
                                              for s in states]) for t in ts])

        expected = rel_rmse(ours, ref_vals)
        stored = next(r for r in results["cases"]
                      if r["case_id"] == "primary")
        assert stored["biomass_vs_model_prediction"][
            "relative_rmse_percent"] == pytest.approx(expected, abs=0.01)

    def test_the_reported_endpoint_is_compared_against_the_reported_range(
        self, fixture, primary_run, results
    ) -> None:
        """The endpoint check must use the paper's range, not a tuned point."""
        case = next(r for r in results["cases"] if r["case_id"] == "primary")
        observed = case["final_biomass_g_per_L"]
        lo, hi = 19.9, 21.5
        assert case["criteria"]["B_reported_endpoint"]["pass"] == (lo <= observed <= hi)

    def test_measured_points_are_never_used_as_the_target(self, results) -> None:
        """They are reported, and labelled, but no criterion depends on them."""
        criteria_text = json.dumps(results["criteria_definitions"])
        assert "measured" not in criteria_text.lower() or "measurements" in criteria_text
        for case in results["cases"]:
            note = case["biomass_vs_measured_points"]["note"]
            assert "never used as a target" in note

    def test_the_digitization_cross_checks_against_a_printed_number(
        self, reference
    ) -> None:
        """The strongest available check on the digitization itself.

        The paper prints the initial glycerol as 2.76 g/L (p. 2).  Figure 3c
        shows the experimental glycerol at t = 0, digitized here, and it must
        agree with the printed value within the stated digitization uncertainty.
        If it did not, every comparison built on these curves would be suspect.

        Figure 5d cannot be used for the same check: its t = 0 experimental mark
        is not separately resolvable, because the authors' own model curve starts
        at the same 2.78 g/L and is drawn on top of it.  That limit is recorded
        rather than worked around.
        """
        marks = reference["figures"]["5"]["panels"]["c"]["series"]["PDGF"]["marks"]
        at_zero = [m for m in marks if abs(m["t_h"]) <= 0.1]
        assert at_zero, "figure 3 has no t=0 glycerol mark"
        mark = at_zero[0]
        uncertainty = mark["reading_uncertainty"] + mark["calibration_uncertainty"]
        assert abs(mark["value"] - 2.76) <= uncertainty, (
            f"digitized t=0 glycerol {mark['value']} g/L is "
            f"{abs(mark['value'] - 2.76):.4f} from the printed 2.76 g/L, "
            f"against an uncertainty of {uncertainty:.4f} g/L"
        )

    def test_the_digitized_model_glycerol_start_matches_the_printed_value(
        self, reference
    ) -> None:
        """A second, independent route to the same number.

        The authors' own model curve in Figure 5d starts at the initial
        glycerol.  It digitizes to 2.78 g/L against the printed 2.76 g/L, a
        0.7 % gap that is well inside the reading uncertainty -- which is what
        makes the digitized model curve usable as a comparison target.
        """
        curve = [s for s in reference["figures"]["6"]["panels"]["d"]["series"]
                 ["Model_predicted"]["samples"] if s.get("value") is not None]
        start = min(curve, key=lambda s: s["t_h"])
        uncertainty = reference["figures"]["6"]["panels"]["d"]["calibration"][
            "y_calibration_uncertainty"
        ]
        assert abs(start["value"] - 2.76) <= uncertainty + 0.05

    def test_the_digitized_model_biomass_endpoint_matches_the_printed_prediction(
        self, reference
    ) -> None:
        """A second, independent cross-check.

        The paper prints its model-predicted biomass as 19.44 g/L (p. 7).  The
        digitized Figure 5c model curve ends at about 19.6 g/L.  These are two
        different routes to the same number -- text and figure -- and their
        agreement is what makes the digitized curve usable as a target.
        """
        curve = [s for s in
                 reference["figures"]["6"]["panels"]["c"]["series"]
                 ["Model_predicted"]["samples"] if s.get("value") is not None]
        final = max(curve, key=lambda s: s["t_h"])
        uncertainty = reference["figures"]["6"]["panels"]["c"]["calibration"][
            "y_calibration_uncertainty"
        ]
        assert abs(final["value"] - 19.44) <= uncertainty + 0.5


# --------------------------------------------------------------------------- #
# 6. missing data and open ambiguities block an unsupported status
# --------------------------------------------------------------------------- #


class TestStatusGuards:
    def test_the_status_is_not_and_cannot_become_validated(self, fixture) -> None:
        assert fixture["status"]["reproduction"] == "not_yet_validated"
        assert fixture["status"]["implementation"] == "implemented"

    def test_no_file_in_the_package_sets_the_status_to_validated(self) -> None:
        """A status upgrade has to be written down somewhere to take effect."""
        offenders = []
        for path in ROOT.rglob("*.py"):
            if ".artifacts" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if '"validated"' in line and "not_yet_validated" not in line:
                    if "partially_validated" in line:
                        continue
                    offenders.append((path.name, stripped[:70]))
        assert offenders == [], offenders

    def test_the_open_transcription_item_is_still_open(self) -> None:
        """TN-02 stays unresolved; nothing may silently resolve it."""
        from models.kinetics import TRANSCRIPTION_NOTES

        ids = {n.note_id for n in TRANSCRIPTION_NOTES}
        assert "TN-02" in ids
        tn02 = next(n for n in TRANSCRIPTION_NOTES if n.note_id == "TN-02")
        assert tn02.unresolved is True

    def test_the_run_reports_the_open_question(self, primary_run) -> None:
        notes = primary_run["metadata"]["transcription_notes"]
        assert any(n["note_id"] == "TN-02" and n["unresolved"] for n in notes)

    def test_missing_reference_data_prevents_a_conclusive_comparison(
        self, fixture
    ) -> None:
        """The fixture says which gaps block what, and a test enforces it."""
        assert fixture["experiment"]["why_this_one"]
        reference_doc = json.loads((ROOT / "data" / "reference_experiments.json")
                                   .read_text(encoding="utf-8"))
        items = {u["item"] for u in reference_doc["unavailable_data"]}
        assert any("OD600" in i for i in items), (
            "the missing OD600-to-DCW calibration must stay listed, because it is "
            "why X0 cannot be derived"
        )

    def test_digitization_ambiguity_is_recorded_not_smoothed_over(
        self, reference
    ) -> None:
        ambiguous = 0
        for figure in reference["figures"].values():
            for panel in figure["panels"].values():
                for series in panel.get("series", {}).values():
                    for sample in series.get("samples", []):
                        if sample.get("ambiguous"):
                            ambiguous += 1
        assert ambiguous > 0, (
            "if nothing is ever marked ambiguous, the digitizer is silently "
            "averaging columns it cannot resolve"
        )


# --------------------------------------------------------------------------- #
# 7. thresholds are documented and derived from the paper, not from the result
# --------------------------------------------------------------------------- #


class TestCriteria:
    def test_every_criterion_carries_a_statement_threshold_and_justification(
        self, fixture
    ) -> None:
        for criterion in fixture["criteria"]:
            assert criterion["criterion_id"]
            assert criterion["statement"]
            assert criterion["threshold"]
            assert criterion["justification"], criterion["criterion_id"]
            assert criterion["kind"]

    def test_the_endpoint_threshold_is_the_papers_own_reported_range(
        self, fixture
    ) -> None:
        criterion = next(c for c in fixture["criteria"]
                         if c["criterion_id"] == "B_reported_endpoint")
        assert criterion["threshold"]["biomass_24h_g_per_L"] == "within [19.9, 21.5]"

    def test_the_regime_threshold_separates_the_two_regimes(self, fixture) -> None:
        """The threshold must discriminate, not just describe the outcome.

        The substrate-limited reading of S2_0 keeps dissolved oxygen near 60 %;
        the paper's curves fall to a few per cent.  A threshold anywhere between
        the two separates them, and 10 % is a generous margin above the paper's
        own figures rather than a value fitted to this run.
        """
        criterion = next(c for c in fixture["criteria"]
                         if c["criterion_id"] == "A_limiting_regime")
        assert criterion["threshold"]["min_DO_percent_over_6_to_24h"] == "< 10"
        assert "60 %" in criterion["justification"]

    def test_the_shape_threshold_is_looser_than_the_papers_own_scatter(
        self, fixture
    ) -> None:
        criterion = next(c for c in fixture["criteria"]
                         if c["criterion_id"] == "C_model_curve_shape")
        assert criterion["threshold"]["relative_rmse_percent"] == "<= 25"
        justification = criterion["justification"]
        assert "1 g/L" in justification and "5 %" in justification
        assert "0.5 g/L" in justification

    def test_the_thresholds_are_not_applied_only_when_they_pass(
        self, results
    ) -> None:
        """A criterion that never fails is not a criterion."""
        by_id = {r["case_id"]: r for r in results["cases"]}
        # the narrow S2 reading fails all three
        for key in ("A_limiting_regime", "B_reported_endpoint",
                    "C_model_curve_shape"):
            assert by_id["s2_yeast_extract_only"]["criteria"][key]["pass"] is False
        # the paper-grounded reading passes the regime and shape criteria
        assert by_id["primary"]["criteria"]["A_limiting_regime"]["pass"] is True
        assert by_id["primary"]["criteria"]["C_model_curve_shape"]["pass"] is True


# --------------------------------------------------------------------------- #
# 8. the composition contracts, refusal rules and provenance survive
# --------------------------------------------------------------------------- #


class TestCompositionBoundary:
    """The composition layer is untouched; these tests guard that."""

    def test_the_connection_contract_is_unchanged_in_kind(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-c",
             "import json,sys;sys.path.insert(0, r'" + str(COMPOSITION_ROOT) + "');"
             "from composition.adapters.ganjave_contract import INPUT_CONTRACT, REFUSED, "
             "connection_contract;"
             "print(json.dumps({'inputs': [r.to_dict() for r in INPUT_CONTRACT],"
             "'refused': len(REFUSED),"
             "'notes': [n['verdict'] for n in connection_contract()['cross_model_notes']]}"
             "))"],
            capture_output=True, text=True, timeout=300,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        payload = json.loads(completed.stdout)
        assert len(payload["inputs"]) == 9
        assert payload["refused"] == 12
        # Morris is still refused outright; Zielinski is still only
        # conditionally connectable.
        assert any(v.startswith("no shared quantity") for v in payload["notes"])

    def test_the_refusal_reasons_still_cover_the_quantity_boundaries(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-c",
             "import json,sys;sys.path.insert(0, r'" + str(COMPOSITION_ROOT) + "');"
             "from composition.adapters.ganjave_contract import REFUSED;"
             "print(json.dumps(sorted({(p, q) for p, q, _r, _h in REFUSED})))"],
            capture_output=True, text=True, timeout=300,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        pairs = {tuple(item) for item in json.loads(completed.stdout)}
        expected = {
            ("initial_biomass_concentration", "mass"),
            ("initial_biomass_concentration", "mass_fraction"),
            ("initial_glycerol_concentration", "mass_flow"),
            ("initial_complex_substrate_concentration", "mass_flow"),
            ("initial_dissolved_oxygen", "mass_fraction"),
            ("initial_dissolved_oxygen", "mass_concentration"),
            ("initial_culture_volume", "mass"),
            ("feed_flow_rate", "mass_flow"),
            ("biomass_concentration", "mass"),
            ("glycerol_concentration", "mass_flow"),
            ("complex_substrate_concentration", "mass_fraction"),
            ("complex_substrate_concentration", "component_mass"),
        }
        assert pairs == expected

    def test_a_run_still_carries_its_provenance(self, primary_run) -> None:
        outputs = primary_run["outputs"]
        biomass = outputs["biomass_concentration"]
        assert biomass["provenance"] == "computed"
        assert biomass["unit"] == "g/L"
        assert biomass["quantity"] == "mass_concentration"
        assert biomass["value_state"] == "number"

        provenance = primary_run["provenance"]
        assert provenance["equations_version"] == "1.1.0"
        assert provenance["input_digest"]
        # Every initial condition is labelled with where its value came from.
        classes = set(provenance["initial_condition_provenance"].values())
        assert classes == {"reported", "assumed"}
        assert provenance["initial_condition_provenance"]["S1"] == "reported"
        assert provenance["initial_condition_provenance"]["S2"] == "assumed"
        assert provenance["initial_condition_provenance"]["DO"] == "assumed"

    def test_the_demo_example_still_runs(self) -> None:
        """The existing example graph is not broken by the fixture's arrival."""
        if not COMPOSITION_ROOT.is_dir():
            pytest.skip("composition package is not available from here")
        example = COMPOSITION_ROOT / "examples" / "ganjave_fed_batch.json"
        if not example.is_file():
            pytest.skip("example graph is missing")
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner",
             "--graph", str(example), "--result",
             str(ROOT / ".artifacts" / "composition_smoke.json")],
            cwd=str(COMPOSITION_ROOT), capture_output=True, text=True,
            timeout=900,
        )
        assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-1000:]


# --------------------------------------------------------------------------- #
# the digitization itself is reproducible
# --------------------------------------------------------------------------- #


class TestDigitizationReproducible:
    def test_the_stored_reference_data_is_what_the_tool_produces(
        self, reference, tmp_path
    ) -> None:
        """Regenerating the reference data must reproduce it byte for byte.

        A digitized dataset that cannot be regenerated is a claim, not
        evidence, so this test re-runs the extractor and compares.  It needs the
        paper's PDF, so it skips when that is absent rather than failing.
        """
        if not PDF.is_file():
            pytest.skip(f"paper PDF not found at {PDF}")
        target = tmp_path / "regenerated.json"
        completed = subprocess.run(
            [sys.executable, str(DIGITIZER), "--pdf", str(PDF),
             "--out", str(target)],
            cwd=ROOT, capture_output=True, text=True, timeout=1800,
        )
        assert completed.returncode == 0, completed.stderr[-3000:]
        regenerated = json.loads(target.read_text(encoding="utf-8"))
        assert regenerated == reference
