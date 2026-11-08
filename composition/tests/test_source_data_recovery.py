"""Data identity, provenance and processing integrity for the source-data recovery.

The recovery of Ganjave et al. (2022) source data returned nothing for its stated
target: the numerical time courses behind Figures 3a and 3b are not published. That is
a negative result, and negative results rot quietly -- a later reader has no way to tell
"we looked and it is not there" from "nobody looked".

These tests fix that. They assert four things:

1. **The absence is documented and evidenced.** The search log names its sources; the
   recovered record states the target was not recovered and why.
2. **Recovered data is never confused with digitised data.** The distinction is the
   whole point of the recovery, and it is asserted structurally, not by convention.
3. **The recovered files are the ones that were examined.** Hashes pin them, so a later
   substitution cannot pass unnoticed.
4. **The frozen evaluation is untouched.** The recovery was not allowed to change the
   failure it was conducted against, and that is checked rather than assumed.

No test asserts that any scientific conclusion holds, and none encodes a model
expectation.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "composition"))
sys.path.insert(0, str(ROOT / "composition" / "tools"))

SOURCE = ROOT / "data" / "ganjave2022" / "source_data"
RESULTS = ROOT / "data" / "ganjave2022" / "results" / "evaluation_results.json"
OBSERVATIONS = ROOT / "data" / "ganjave2022" / "observations.json"
PROTOCOL = ROOT / "data" / "ganjave2022" / "evaluation_protocol.json"
CONFIG = ROOT / "data" / "ganjave2022" / "frozen_configuration.json"

RECOVERY_REPORT = ROOT / "reports" / "GANJAVE_SOURCE_DATA_RECOVERY.md"
REQUEST = ROOT / "reports" / "GANJAVE_AUTHOR_DATA_REQUEST.md"

#: SHA-256 of the files retrieved from Europe PMC on the recovery date. These pin the
#: exact artefacts that were inspected; a different file under the same name would
#: change the search's meaning.
EXPECTED_HASHES = {
    "PMC8718739_supplementary.zip":
        "f50c75b00f2dbcfeb55290f2534c854aae9580917baac71ce11615d020374e57",
    "mmc1_supplementary.docx":
        "2b24a4fd43bf4e94e7a8f30da4c59ae298fc3d512b3b919e51a9de2049b29ee1",
    "gr3_maintext_fig3.jpg":
        "ff45d6279d75ea4ec7cf6dcdf030b31afdbedcfd7d9e4a4c85c2ff9040302ed8",
    "chart1.xml":
        "e0b6a21f3b95c0ee75eb3deed268ec23959c57ea7d4306852e38ccd5c7aa5460",
    "chart2.xml":
        "420751868610b2c30e2d86027538962a361e7e242c2424038b86d2d112e75b7a",
}

FROZEN = {
    "frozen_configuration.json": CONFIG,
    "observations.json": OBSERVATIONS,
    "evaluation_protocol.json": PROTOCOL,
    "figure_reference_data.json":
        ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json",
    "reference_parameters.json":
        ROOT / "Models" / "Ganjave" / "data" / "reference_parameters.json",
}


def _load(path: Path) -> dict:
    assert path.exists(), f"{path.relative_to(ROOT)} is missing"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def recovered() -> dict:
    return _load(SOURCE / "recovered_numerical_data.json")


@pytest.fixture(scope="module")
def search_log() -> dict:
    return _load(SOURCE / "search_log.json")


@pytest.fixture(scope="module")
def inventory() -> dict:
    return _load(SOURCE / "supplementary_inventory.json")


@pytest.fixture(scope="module")
def charts() -> dict:
    return _load(SOURCE / "supplementary_charts.json")


@pytest.fixture(scope="module")
def config() -> dict:
    return _load(CONFIG)


# --------------------------------------------------------------------------- #
# integrity
# --------------------------------------------------------------------------- #


class TestTheRecoveredFilesAreTheOnesExamined:
    @pytest.mark.parametrize("name,expected", sorted(EXPECTED_HASHES.items()))
    def test_the_hash_still_matches(self, name: str, expected: str) -> None:
        path = SOURCE / name
        assert path.exists(), f"{name} was recovered but is not present"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, (
            f"{name} changed since the search. The recorded findings describe the "
            f"previous contents, and the search must be repeated."
        )

    def test_the_normalised_record_carries_the_provenance_of_its_inputs(
        self, recovered: dict
    ) -> None:
        provenance = recovered["provenance"]
        assert provenance["package_sha256"] == \
            EXPECTED_HASHES["PMC8718739_supplementary.zip"]
        assert provenance["docx_sha256"] == \
            EXPECTED_HASHES["mmc1_supplementary.docx"]

    def test_the_supplementary_contains_no_data_file(self, inventory: dict) -> None:
        """The negative result, asserted so it cannot be quietly forgotten."""
        assert inventory["spreadsheet_or_data_parts"] == [], (
            "the supplementary now contains a spreadsheet or data file. The recovery "
            "conclusion that no time course is published is no longer established."
        )

    def test_the_native_charts_carry_no_data(self, charts: dict) -> None:
        """They were the most promising lead, and they are empty."""
        for chart in charts["charts"]:
            for series in chart["series"]:
                assert series["n_points"] == 0, (
                    f"{chart['chart_part']} now carries cached values. If so, the "
                    f"authors' plotted numbers may be recoverable and the search "
                    f"conclusion must be revisited."
                )


# --------------------------------------------------------------------------- #
# identity: measured is not digitised
# --------------------------------------------------------------------------- #


class TestRecoveredDataIsNeverConfusedWithDigitisedData:
    def test_every_recovered_record_is_author_reported(self, recovered: dict) -> None:
        records = [
            record
            for table in recovered["recovered_tables"]
            for record in table["records"]
        ]
        assert records
        for record in records:
            assert record["data_class"] == "author_reported_measurement"
            assert record["digitized"] is False
            assert record["reading_uncertainty"] is None, (
                "an author-reported number carries no reading uncertainty. Setting "
                "one would invent a measurement precision nobody reported."
            )

    def test_no_digitised_value_leaked_into_the_recovered_record(
        self, recovered: dict
    ) -> None:
        """The frozen dataset's values must not appear here as recovered data."""
        blob = json.dumps(recovered)
        observations = _load(OBSERVATIONS)
        leaked = [
            point["observation_id"]
            for observation_set in observations["observation_sets"]
            for point in observation_set["points"]
            if f'"{point["value"]}"' in blob
        ]
        assert not leaked, (
            f"digitised observations appear in the recovered record: {leaked[:5]}. "
            f"Figure readings must never be relabelled as author-reported data."
        )

    def test_the_frozen_dataset_still_declares_itself_digitised(self) -> None:
        observations = _load(OBSERVATIONS)
        points = [
            point
            for observation_set in observations["observation_sets"]
            for point in observation_set["points"]
        ]
        assert points
        for point in points:
            assert point["digitized"] is True
            assert point["kind"] == "experimental_observation"
            assert point["combined_uncertainty"] > 0

    def test_the_recovered_record_states_it_is_not_a_time_course(
        self, recovered: dict
    ) -> None:
        for table in recovered["recovered_tables"]:
            assert table["is_time_course"] is False


# --------------------------------------------------------------------------- #
# processing integrity
# --------------------------------------------------------------------------- #


class TestTheTransformationsAreRecorded:
    def test_every_kla_record_declares_its_forward_fill_state(
        self, recovered: dict
    ) -> None:
        records = recovered["recovered_tables"][0]["records"]
        assert records
        for record in records:
            assert "volume_forward_filled" in record
            assert "rpm_forward_filled" in record
            assert isinstance(record["volume_forward_filled"], bool)

    def test_at_least_one_value_was_forward_filled(self, recovered: dict) -> None:
        """If nothing was, the merge handling is doing nothing and should be removed
        rather than left in place implying work it did not do."""
        records = recovered["recovered_tables"][0]["records"]
        filled = [r for r in records
                  if r["volume_forward_filled"] or r["rpm_forward_filled"]]
        assert filled, "no merged cell was forward-filled; the handling is inert"

    def test_the_transformation_list_matches_what_was_applied(
        self, recovered: dict
    ) -> None:
        ids = {t["id"] for t in recovered["transformations"]}
        assert "merged_cell_forward_fill" in ids
        assert "column_group_assignment" in ids
        for transformation in recovered["transformations"]:
            assert transformation["description"].strip()
            assert transformation["applies_to"]
            assert transformation["affects"]

    def test_the_immutable_operations_are_declared(self, recovered: dict) -> None:
        declared = " ".join(recovered["transformations_not_applied"]).lower()
        for forbidden in ("smoothing", "conversion", "imputation", "averaging"):
            assert forbidden in declared

    def test_the_transformation_is_idempotent(self, recovered: dict) -> None:
        """Re-running the normaliser must reproduce the record exactly."""
        import normalise_recovered_data as normaliser

        inventory = _load(SOURCE / "supplementary_inventory.json")
        rebuilt = normaliser.normalise_kla_table(inventory["tables"][2])
        assert rebuilt == recovered["recovered_tables"][0]["records"]

    def test_the_model_input_is_confirmed_by_the_recovered_data(
        self, recovered: dict, config: dict
    ) -> None:
        """The one thing the recovery bears on: an independent, author-reported
        confirmation of a parameter the frozen configuration uses."""
        records = recovered["recovered_tables"][0]["records"]
        match = [
            r for r in records
            if r["medium_volume_ml"] == 100 and r["shaking_speed_rpm"] == 200
            and r["pitch_cm"] == 5.0
        ]
        assert match, "the 100 mL / 200 rpm / 5 cm pitch measurement is missing"
        assert match[0]["kla_h_per_h"] == 133.0
        solver_note = config["model"]["solver"]["h_max_reason"]
        assert "133" in solver_note, (
            "the frozen configuration's solver justification cites a kLa the "
            "recovered table does not confirm"
        )


# --------------------------------------------------------------------------- #
# the negative result is on the record
# --------------------------------------------------------------------------- #


class TestTheAbsenceIsDocumented:
    def test_the_search_log_names_its_target_and_outcome(self, search_log: dict) -> None:
        assert "Figure 3a" in search_log["target"]["what"]
        assert "Figure 3b" in search_log["target"]["what"]
        assert search_log["outcome"].startswith("NOT PUBLISHED")

    def test_every_search_step_records_a_source_and_an_outcome(
        self, search_log: dict
    ) -> None:
        assert len(search_log["steps"]) >= 8
        for step in search_log["steps"]:
            assert step["action"].strip()
            assert step["source"].strip()
            assert step["result"].strip()

    def test_the_search_covers_every_source_class_the_task_names(
        self, search_log: dict
    ) -> None:
        blob = json.dumps(search_log).lower()
        for expected in ("data-availability", "supplementary", "repository",
                         "europe pmc", "authors"):
            assert expected in blob, f"the search never mentions {expected}"

    def test_the_access_failure_is_recorded_as_a_limitation_not_evidence(
        self, search_log: dict
    ) -> None:
        """A network failure is not evidence of absence, and must not be recorded as
        if it were."""
        step = next(
            s for s in search_log["steps"]
            if "sciencedirect" in s["source"].lower()
        )
        assert "limitation" in step["result"].lower()
        assert "not as evidence" in step["result"].lower() or \
            "not evidence" in step["result"].lower()

    def test_the_record_states_fabrication_was_not_done(self, search_log: dict) -> None:
        for entry in search_log["explicitly_not_done"]:
            assert entry.strip()
        blob = json.dumps(search_log["explicitly_not_done"]).lower()
        assert "fabricated" in blob

    def test_the_recovered_record_states_what_was_not_found_and_why(
        self, recovered: dict
    ) -> None:
        target = recovered["target_not_recovered"]
        assert target["status"] == "NOT PUBLISHED"
        assert len(target["evidence"]) >= 4
        for item in target["evidence"]:
            assert item.strip()

    def test_the_report_says_no_open_question_was_resolved(self) -> None:
        text = RECOVERY_REPORT.read_text(encoding="utf-8")
        assert "Zero of the six open questions were resolved" in text
        assert "No comparison changed its" in text or \
            "no new data existed to compare" in text


# --------------------------------------------------------------------------- #
# the frozen evaluation is untouched
# --------------------------------------------------------------------------- #


class TestTheFrozenEvaluationIsUnchanged:
    def test_all_five_frozen_inputs_still_match_their_digests(self) -> None:
        results = _load(RESULTS)
        recorded = results["input_digests"]
        for name, path in FROZEN.items():
            assert path.exists(), f"{name} is missing"
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == recorded[name], (
                f"{name} changed. The recovery was not permitted to alter the "
                f"evaluation it was investigating."
            )

    def test_the_primary_result_is_unchanged(self) -> None:
        results = _load(RESULTS)
        primary = next(s for s in results["scenarios"]
                       if s["scenario_id"] == "heldout_fig3")
        assert primary["decision"]["outcome"] == "fail"
        metrics = next(
            c for c in primary["observation_sets"].values()
            if c["quantity"] == "biomass_concentration")["metrics"]
        assert metrics["rmse_g_per_L"] == pytest.approx(2.52037, abs=1e-4)

    def test_no_recovered_file_sits_inside_the_frozen_dataset(
        self,
    ) -> None:
        """Recovered material lives in its own directory; the frozen dataset was not
        extended with it."""
        observations_blob = OBSERVATIONS.read_text(encoding="utf-8")
        for marker in ("source_data", "mmc1", "supplementary", "author_reported"):
            assert marker not in observations_blob, (
                f"the frozen dataset now mentions {marker!r}"
            )

    def test_no_validation_status_was_upgraded(self) -> None:
        source = (ROOT / "Models" / "Ganjave" / "models" / "composition.py").read_text(
            encoding="utf-8")
        assert '"not_yet_validated"' in source


# --------------------------------------------------------------------------- #
# the author request
# --------------------------------------------------------------------------- #


class TestTheAuthorRequestIsReady:
    def test_it_exists_and_addresses_the_corresponding_author(self) -> None:
        text = REQUEST.read_text(encoding="utf-8")
        assert "wangikar@iitb.ac.in" in text
        assert "10.1016/j.btre.2021.e00694" in text

    def test_it_asks_for_the_specific_series_and_the_open_questions(self) -> None:
        text = REQUEST.read_text(encoding="utf-8").lower()
        for expected in ("dissolved oxygen", "glycerol", "biomass",
                         "s2", "enzyme ratio", "26 h"):
            assert expected in text, f"the request never asks about {expected!r}"

    def test_it_states_a_licensing_intention(self) -> None:
        assert "cc by" in REQUEST.read_text(encoding="utf-8").lower()

    def test_it_does_not_ask_for_a_change_to_the_paper(self) -> None:
        """The request must not put the authors on the spot about their results."""
        text = REQUEST.read_text(encoding="utf-8").lower()
        assert "not asking you to re-check" in text or \
            "not asking for a change to the paper" in text
