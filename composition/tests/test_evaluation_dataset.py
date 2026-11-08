"""The evaluation dataset is present, correctly structured, and honestly labelled.

Phase 2 of the held-out validation. Three properties are load-bearing and are asserted
here rather than assumed:

1. **Observations and predictions are in different files sections, and never mix.**
   A reference set that can accidentally supply its own prediction as its target is not
   a reference set. ``Model_predicted.marks`` are curve pixels with reading
   uncertainties above 2 g/L; reading them as measurements would invent data.

2. **Every observation is traceable to the paper's own figure numbering.** The upstream
   digitisation keys the held-out experiment as ``"5"`` and the selected optimum as
   ``"6"``; in the paper they are Fig. 3 and Fig. 5. That mismatch is corrected here,
   and asserted, so a citation can be checked against the PDF.

3. **Every point carries its own uncertainty.** A comparison that drops the reference
   data's error bar reports agreement the source cannot support.

Nothing here checks whether the model agrees with the data. That is
``test_heldout_validation.py``'s job, and it is not allowed to pass or fail on the
strength of a value asserted here.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "composition"))

DATA = ROOT / "data" / "ganjave2022"
OBSERVATIONS = DATA / "observations.json"
DIGITISATION = ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json"


def load() -> dict:
    assert OBSERVATIONS.exists(), (
        f"{OBSERVATIONS} is missing. Rebuild it with "
        f"`python composition/tools/build_evaluation_dataset.py`."
    )
    return json.loads(OBSERVATIONS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dataset() -> dict:
    return load()


@pytest.fixture(scope="module")
def digitisation() -> dict:
    return json.loads(DIGITISATION.read_text(encoding="utf-8"))


def sets_by_id(dataset: dict) -> dict[str, dict]:
    return {s["observation_set_id"]: s for s in dataset["observation_sets"]}


class TestTheDatasetIsPresentAndStructured:
    def test_it_declares_its_identity_and_source(self, dataset: dict) -> None:
        assert dataset["dataset_id"].startswith("ganjave2022")
        assert dataset["version"]
        source = dataset["source"]
        assert "Ganjave" in source["citation"]
        assert source["doi"] == "10.1016/j.btre.2021.e00694"

    def test_the_cited_paper_is_not_required_to_be_present(self, dataset: dict) -> None:
        """The reference PDFs are deliberately not distributed -- .gitignore says so,
        and they are other authors' publications. A test that demanded one would fail
        on every clone. The citation is checked against the extracted captions and
        quotes that *are* committed."""
        assert (ROOT / dataset["source"]["pdf"]).name.endswith(".pdf")
        # The facts that make the citation checkable all live in committed files.
        assert (ROOT / "Models" / "Ganjave" / "data"
                / "figure_reference_data.json").exists()
        assert (ROOT / "Models" / "Ganjave" / "data"
                / "validation_fig5.json").exists()

    def test_it_records_how_to_regenerate_itself(self, dataset: dict) -> None:
        derivation = dataset["source"]["derivation"]
        assert "build_evaluation_dataset.py" in derivation

    def test_it_states_what_counts_as_an_observation(self, dataset: dict) -> None:
        policy = dataset["observation_policy"]
        for key in ("what_counts_as_an_observation", "what_does_not", "no_interpolation"):
            assert policy[key].strip(), f"the observation policy is silent about {key}"

    def test_it_records_the_excluded_fitting_experiment(self, dataset: dict) -> None:
        """Fig. 2 must be excluded *on the record*, so its absence is a decision."""
        excluded = dataset["excluded"]["fitting_experiment"]
        assert excluded["paper_figure"] == 2
        assert "circular" in excluded["reason"]
        assert excluded["feed"]["glycerol_percent_wv"] == 30.0

    def test_every_set_is_complete(self, dataset: dict) -> None:
        for observation_set in dataset["observation_sets"]:
            name = observation_set["observation_set_id"]
            assert observation_set["n_observations"] == len(observation_set["points"]), name
            assert observation_set["n_observations"] > 0, name
            assert observation_set["quantity"].endswith("concentration"), name
            assert observation_set["unit"] == "g/L", name
            assert observation_set["paper_page"] > 0, name
            assert observation_set["independent_of_parameter_fitting"] is True, name


class TestObservationsAreNeverModelOutput:
    def test_every_point_is_tagged_as_an_experimental_observation(
        self, dataset: dict
    ) -> None:
        for observation_set in dataset["observation_sets"]:
            for point in observation_set["points"]:
                assert point["kind"] == "experimental_observation", point
                assert point["digitized"] is True
                assert point["tabulated"] is False

    def test_the_authors_model_curve_is_not_in_any_point_list(self, dataset: dict) -> None:
        """The contamination guard. A prediction that can be read as a target is not
        a target, so it must be structurally unable to appear in one."""
        blob = json.dumps(dataset["observation_sets"])
        assert "Model_predicted" not in blob, (
            "a model-predicted series leaked into the observation sets"
        )
        for observation_set in dataset["observation_sets"]:
            for point in observation_set["points"]:
                assert point["culture"] != "Model_predicted"

    def test_the_model_curve_is_carried_separately_and_labelled(
        self, dataset: dict
    ) -> None:
        assert dataset["model_predictions"], "the authors' curve should be recorded"
        for prediction in dataset["model_predictions"]:
            assert prediction["kind"] == "model_prediction"
            assert prediction["is_measurement"] is False
            assert prediction["n_samples"] > 0
            # The curve pixels are not points, and saying so is what stops them
            # being read as measurements later.
            assert "marks" in prediction["note"].lower() or \
                "'marks'" in prediction["note"]

    def test_the_curve_pixels_would_be_absurd_as_measurements(
        self, digitisation: dict
    ) -> None:
        """Why the split exists: the Model_predicted 'marks' carry reading
        uncertainties larger than the entire trajectory they sit on. If a future
        digitisation ever fixed that, this test should be revisited, not deleted."""
        marks = (
            digitisation["figures"]["5"]["panels"]["b"]["series"]["Model_predicted"]
            .get("marks", [])
        )
        assert marks, "the digitisation's Model_predicted marks changed shape"
        for mark in marks:
            assert mark["reading_uncertainty"] > 2.0, (
                "Model_predicted marks are now precise enough to be mistaken for "
                "measurements; revisit the observation/prediction split"
            )


class TestEveryObservationIsTraceable:
    def test_the_figure_mapping_is_corrected_to_the_paper(
        self, dataset: dict, digitisation: dict
    ) -> None:
        """The upstream keys do not match the paper. Asserting the correction is what
        makes the citation checkable."""
        mapping = dataset["figure_numbering"]["map"]
        assert mapping == {"5": 3, "6": 5}
        for observation_set in dataset["observation_sets"]:
            key = observation_set["dataset_figure_key"]
            assert mapping[key] == observation_set["paper_figure"]
            # The figure's own feed must be the one the paper's caption prints.
            assert observation_set["feed"] == digitisation["figures"][key]["feed"]

    def test_the_held_out_set_is_the_papers_designated_validation_experiment(
        self, dataset: dict
    ) -> None:
        held_out = next(
            s for s in dataset["observation_sets"]
            if s["evaluation_role"] == "primary"
        )
        assert held_out["paper_figure"] == 3
        # The entire independence claim rests on this sentence in the caption.
        assert "not used for estimation" in held_out["paper_caption"]
        assert held_out["feed"]["glycerol_percent_wv"] == 20.0
        assert held_out["feed"]["yeast_extract_percent_wv"] == 30.0
        assert held_out["feed"]["flow_mL_per_h"] == 0.78

    def test_the_held_out_feed_differs_from_the_fitting_experiment(
        self, dataset: dict
    ) -> None:
        """If they matched, 'held out' would mean nothing."""
        held_out = next(
            s for s in dataset["observation_sets"]
            if s["evaluation_role"] == "primary"
        )
        fitting = dataset["excluded"]["fitting_experiment"]["feed"]
        assert held_out["feed"]["glycerol_percent_wv"] != fitting["glycerol_percent_wv"]
        assert held_out["feed"]["flow_mL_per_h"] != fitting["flow_mL_per_h"]

    def test_every_point_carries_its_own_uncertainty(self, dataset: dict) -> None:
        for observation_set in dataset["observation_sets"]:
            for point in observation_set["points"]:
                assert point["combined_uncertainty"] > 0, point
                assert point["reading_uncertainty"] > 0, point
                assert point["calibration_uncertainty"] > 0, point
                expected = round(
                    point["reading_uncertainty"] + point["calibration_uncertainty"], 6)
                assert point["combined_uncertainty"] == pytest.approx(expected, abs=1e-6)

    def test_the_calibration_uncertainty_is_recorded_per_panel(
        self, dataset: dict
    ) -> None:
        for observation_set in dataset["observation_sets"]:
            calibration = observation_set["axis_calibration"]
            for key in ("px_per_y_unit", "px_per_x_unit",
                        "y_calibration_uncertainty", "x_calibration_uncertainty"):
                assert calibration[key] > 0, f"{observation_set['observation_set_id']}: {key}"

    def test_observation_ids_are_unique(self, dataset: dict) -> None:
        identifiers = [
            point["observation_id"]
            for observation_set in dataset["observation_sets"]
            for point in observation_set["points"]
        ]
        assert len(identifiers) == len(set(identifiers))

    def test_times_and_values_are_finite(self, dataset: dict) -> None:
        for observation_set in dataset["observation_sets"]:
            for point in observation_set["points"]:
                assert math.isfinite(point["t_h"]), point
                assert math.isfinite(point["value"]), point


class TestNothingWasInvented:
    def test_no_observation_was_interpolated_onto_a_grid(self, dataset: dict) -> None:
        """Real sampling times are irregular. A uniform grid would mean invented
        measurements, so every gap within a culture must not be the same.

        Times are compared *within* a culture: the five Fig. 5c cultures were sampled
        at shared nominal times, so a tie across cultures is a property of the
        experiment and not a duplicated reading.
        """
        for observation_set in dataset["observation_sets"]:
            by_culture: dict[str, list[float]] = {}
            for point in observation_set["points"]:
                by_culture.setdefault(point["culture"], []).append(point["t_h"])
            for culture, times in by_culture.items():
                times = sorted(times)
                for earlier, later in zip(times, times[1:]):
                    assert later > earlier, (
                        f"{observation_set['observation_set_id']}/{culture}: "
                        f"duplicate time {earlier}"
                    )
                if len(times) >= 4:
                    gaps = [round(b - a, 2) for a, b in zip(times, times[1:])]
                    # A synthesised grid has exactly one gap value. Digitised marks
                    # sampled when someone happened to take a reading do not.
                    assert len(set(gaps)) > 1, (
                        f"{observation_set['observation_set_id']}/{culture} has a "
                        f"constant {gaps[0]} h spacing, which is a generated grid"
                    )

    def test_the_held_out_times_are_not_whole_hours_either(self, dataset: dict) -> None:
        """The digitisation recovers marker centres, so times sit near but not on
        whole hours. Values snapped to the hour would mean they were guessed."""
        held_out = next(
            s for s in dataset["observation_sets"] if s["evaluation_role"] == "primary"
        )
        offsets = [
            abs(point["t_h"] - round(point["t_h"]))
            for point in held_out["points"]
        ]
        assert max(offsets) > 0.01, (
            "every observation time is a whole hour, which no raster reading produces"
        )

    def test_point_counts_match_the_source_digitisation(
        self, dataset: dict, digitisation: dict
    ) -> None:
        """Re-derive the counts from the upstream file. If the dataset ever grows a
        point that the source does not have, this fails."""
        for observation_set in dataset["observation_sets"]:
            key = observation_set["dataset_figure_key"]
            panel = digitisation["figures"][key]["panels"][observation_set["panel"]]
            expected = sum(
                len(panel["series"].get(name, {}).get("marks", []))
                for name in {
                    p["culture"] for p in observation_set["points"]
                }
            )
            assert observation_set["n_observations"] == expected, (
                observation_set["observation_set_id"]
            )

    def test_the_dataset_does_not_claim_to_be_tabulated(self, dataset: dict) -> None:
        """The paper publishes no numerical time courses. Saying 'tabulated' would
        imply a precision the source does not have."""
        for observation_set in dataset["observation_sets"]:
            for point in observation_set["points"]:
                assert point["tabulated"] is False
                assert point["digitized"] is True


class TestTheBuilderReproducesTheDataset:
    def test_rebuilding_reproduces_the_committed_file(self) -> None:
        """Byte-for-byte. A dataset that cannot be regenerated is not a dataset, it is
        an assertion."""
        sys.path.insert(0, str(ROOT / "composition" / "tools"))
        import build_evaluation_dataset as builder

        rebuilt = builder.build()
        assert rebuilt == json.loads(OBSERVATIONS.read_text(encoding="utf-8"))

    def test_the_builder_would_refuse_a_broken_figure_mapping(self) -> None:
        """The mapping is asserted against the printed caption and feed recipe, so a
        change in the source cannot silently invalidate a citation."""
        sys.path.insert(0, str(ROOT / "composition" / "tools"))
        import build_evaluation_dataset as builder

        with pytest.raises(SystemExit):
            builder.check_mapping("9", {"caption": "", "feed": {}})
        with pytest.raises(SystemExit):
            builder.check_mapping(
                "5", {"caption": "something else entirely", "feed": {
                    "glycerol_percent_wv": 20.0, "yeast_extract_percent_wv": 30.0,
                    "flow_mL_per_h": 0.78}})
