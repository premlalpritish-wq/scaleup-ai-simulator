"""Provenance: parameters, initial conditions, derived and simulated values.

Covers GJ-01 (parameter fidelity against Table 2), GJ-15 (distinct provenance
classes with traceable sources) and GJ-16 (reference results kept as reference
records, never returned as predictions).
"""

from __future__ import annotations

import pytest

from models.composition import port_by_id
from models.initial import MissingInitialCondition, REQUIRED_BY_CALLER, build_initial_conditions
from models.reference import (
    dataset_manifest,
    feed_experiments,
    measured_outcomes,
    model_prediction,
    operating_conditions,
    reported_observations,
    selected_recipe,
    unavailable_data,
)
from models.simulation import simulate
from schemas.parameters import (
    EQUATIONS_VERSION,
    INFORMATIONAL_SYMBOLS,
    REQUIRED_SYMBOLS,
    table2_parameter_set,
)
from schemas.provenance import Parameter, ParameterError, Provenance, SourceRef
from schemas.units import QuantityKind

#: Table 2 exactly as printed, with the unit the paper prints for each.
TABLE2 = {
    "mum1": (1.497, "1/h"),
    "mum2": (0.834, "1/h"),
    "K11": (0.131, "g/L"),
    "K12": (36.154, "g/L"),
    "K22": (1.001, "g/L"),
    "Ko1": (0.326, "%"),
    "Ko2": (8.944, "%"),
    "Y11": (0.440, "g/g"),
    "Y12": (0.881, "g/g"),
    "Y22": (0.254, "g/g"),
    "Yo1": (0.925, "g/g"),
    "Yo2": (1.219, "g/g"),
    "e_ratio1_0": (0.082, "1"),
    "e_ratio2_0": (0.874, "1"),
    "beta1": (0.001, "1/h"),
    "beta2": (0.028, "1/h"),
}


class TestParameterFidelity:
    """GJ-01: every implemented Table 2 parameter against the printed value."""

    @pytest.mark.parametrize("symbol", sorted(TABLE2))
    def test_value_matches_table_2(self, parameters, symbol: str) -> None:
        expected, _unit = TABLE2[symbol]
        assert parameters.value(symbol) == expected

    @pytest.mark.parametrize("symbol", sorted(TABLE2))
    def test_unit_matches_table_2(self, parameters, symbol: str) -> None:
        _expected, unit = TABLE2[symbol]
        assert parameters.parameter(symbol).unit == unit

    @pytest.mark.parametrize("symbol", sorted(TABLE2))
    def test_every_parameter_is_fitted_with_a_source(self, parameters, symbol: str) -> None:
        parameter = parameters.parameter(symbol)
        assert parameter.provenance is Provenance.FITTED
        assert parameter.source is not None
        assert parameter.source.locator == "Table 2"
        assert parameter.fitting, "a fitted parameter must record the procedure"

    def test_reported_parameters_are_measured_not_fitted(self, parameters) -> None:
        """kLa and C* were measured/reported, not estimated by the fit."""
        assert parameters.parameter("kLa").provenance is Provenance.REPORTED
        assert parameters.parameter("C_star").provenance is Provenance.REPORTED
        assert parameters.parameter("kLa").fitting == ""
        assert parameters.value("kLa") == 133.0
        assert parameters.value("C_star") == 0.0075

    def test_every_required_symbol_is_present(self, parameters) -> None:
        for symbol in REQUIRED_SYMBOLS:
            assert symbol in parameters
            assert parameters.parameter(symbol).value is not None

    def test_informational_symbols_are_not_read_by_the_equations(self, parameters) -> None:
        for symbol in INFORMATIONAL_SYMBOLS:
            assert symbol in parameters
        assert "of_minimum" not in REQUIRED_SYMBOLS

    def test_parameter_set_is_versioned(self, parameters) -> None:
        assert parameters.parameter_set_id == "ganjave2022.table2"
        assert parameters.version == "1.0.0"
        assert parameters.equations_version == EQUATIONS_VERSION

    def test_unknown_symbol_is_refused(self, parameters) -> None:
        with pytest.raises(ParameterError, match="not in parameter set"):
            parameters.value("K33")

    def test_overriding_marks_the_parameter_assumed_and_keeps_the_original(self, parameters) -> None:
        changed = parameters.with_overrides({"mum1": 2.0}, reason="sensitivity check")
        assert changed.parameter("mum1").provenance is Provenance.ASSUMED
        assert changed.parameter("mum1").value == 2.0
        assert "prints 1.497" in changed.parameter("mum1").note
        # the original set is untouched
        assert parameters.value("mum1") == 1.497

    def test_override_without_a_reason_is_refused(self, parameters) -> None:
        with pytest.raises(ParameterError, match="state why"):
            parameters.with_overrides({"mum1": 2.0}, reason="  ")

    def test_override_of_an_unknown_parameter_is_refused(self, parameters) -> None:
        with pytest.raises(ParameterError, match="unknown parameters"):
            parameters.with_overrides({"nope": 1.0}, reason="why")


class TestParameterIntegrity:
    """The schema refuses records that cannot say where they came from."""

    def _source(self) -> SourceRef:
        return SourceRef(section="3.2", locator="Table 2", printed_page=4)

    def test_reported_parameter_without_a_source_is_refused(self) -> None:
        with pytest.raises(ParameterError, match="must cite"):
            Parameter(
                symbol="x", label="x", kind=QuantityKind.ENZYME_RATIO,
                provenance=Provenance.REPORTED, unit="1", value=1.0,
            )

    def test_fitted_parameter_without_a_procedure_is_refused(self) -> None:
        with pytest.raises(ParameterError, match="fitting procedure"):
            Parameter(
                symbol="x", label="x", kind=QuantityKind.ENZYME_RATIO,
                provenance=Provenance.FITTED, unit="1", value=1.0,
                source=self._source(),
            )

    def test_unknown_parameter_cannot_carry_a_value(self) -> None:
        with pytest.raises(ParameterError, match="refusing to fabricate"):
            Parameter(
                symbol="x", label="x", kind=QuantityKind.ENZYME_RATIO,
                provenance=Provenance.UNKNOWN, unit="1", value=0.0,
                missing_reason="not printed",
            )

    def test_unknown_parameter_needs_a_reason(self) -> None:
        with pytest.raises(ParameterError, match="say why"):
            Parameter(
                symbol="x", label="x", kind=QuantityKind.ENZYME_RATIO,
                provenance=Provenance.UNKNOWN, unit="1",
            )

    def test_a_unit_must_be_registered_for_that_quantity(self) -> None:
        with pytest.raises(ParameterError, match="not registered for"):
            Parameter(
                symbol="x", label="x", kind=QuantityKind.ENZYME_RATIO,
                provenance=Provenance.REPORTED, unit="g/L", value=1.0,
                source=self._source(),
            )


class TestInitialConditionProvenance:
    """GJ-15: what the paper states is reported; what it does not is the caller's."""

    def test_reported_and_assumed_are_distinguished(self, batch_conditions) -> None:
        summary = batch_conditions.provenance_summary()
        assert summary["S1"] == "reported"
        assert summary["V"] == "reported"
        assert summary["e1"] == "reported"
        assert summary["e2"] == "reported"
        assert summary["X"] == "assumed"
        assert summary["S2"] == "assumed"
        assert summary["DO"] == "assumed"

    def test_reported_initial_conditions_cite_the_paper(self, batch_conditions) -> None:
        for key in ("S1", "V", "e1", "e2"):
            assert batch_conditions.provenance[key].source is not None
            assert batch_conditions.provenance[key].source.printed_page in (2, 4)

    def test_assumed_initial_conditions_cite_nothing(self, batch_conditions) -> None:
        """An assumed value must not borrow a citation that does not support it."""
        for key in REQUIRED_BY_CALLER:
            assert batch_conditions.provenance[key].source is None

    def test_the_three_unstated_values_are_required(self) -> None:
        assert set(REQUIRED_BY_CALLER) == {"X", "S2", "DO"}
        with pytest.raises(MissingInitialCondition) as excinfo:
            build_initial_conditions(X=None, S2=5.0, DO=100.0, mode="batch")
        assert excinfo.value.missing == ("X",)
        assert "OD600-to-dry-cell-weight calibration" in str(excinfo.value)

    def test_reported_defaults_are_the_paper_values(self, batch_conditions) -> None:
        assert batch_conditions.values["S1"] == 2.76
        assert batch_conditions.values["V"] == pytest.approx(0.1)
        assert batch_conditions.values["e1"] == 0.082
        assert batch_conditions.values["e2"] == 0.874

    def test_units_are_converted_into_the_paper_units(self) -> None:
        conditions = build_initial_conditions(
            X=0.05, S2=5.0, DO=100.0, mode="batch", V=100.0, units={"V": "mL"}
        )
        assert conditions.values["V"] == pytest.approx(0.1)
        assert conditions.units["V"] == "L"

    def test_invalid_initial_volume_is_refused(self) -> None:
        with pytest.raises(Exception, match="strictly positive"):
            build_initial_conditions(X=0.05, S2=5.0, DO=100.0, mode="batch", V=0.0)

    def test_initial_dissolved_oxygen_outside_0_100_is_refused(self) -> None:
        with pytest.raises(Exception, match="outside"):
            build_initial_conditions(X=0.05, S2=5.0, DO=150.0, mode="batch")

    def test_negative_initial_biomass_is_refused(self) -> None:
        with pytest.raises(Exception, match="negative"):
            build_initial_conditions(X=-1.0, S2=5.0, DO=100.0, mode="batch")


class TestSimulationProvenance:
    """GJ-15: a run records its parameters, inputs, solver and digest."""

    def test_run_records_everything_needed_to_reproduce_it(self, batch_conditions) -> None:
        result = simulate(initial_conditions=batch_conditions, duration_h=2.0, mode="batch")
        provenance = result.provenance
        assert provenance.model_id == "ganjave2022.cybernetic-growth"
        assert provenance.equations_version == EQUATIONS_VERSION
        assert provenance.parameters["parameter_set_id"] == "ganjave2022.table2"
        assert set(provenance.initial_conditions["values"]) == {
            "X", "S1", "S2", "DO", "V", "e1", "e2"
        }
        assert provenance.solver["name"].startswith("runge-kutta")
        assert len(provenance.input_digest) == 64

    def test_identical_runs_share_a_digest(self, batch_conditions) -> None:
        a = simulate(initial_conditions=batch_conditions, duration_h=2.0, mode="batch")
        b = simulate(initial_conditions=batch_conditions, duration_h=2.0, mode="batch")
        assert a.provenance.input_digest == b.provenance.input_digest

    def test_a_different_input_changes_the_digest(self, batch_conditions) -> None:
        other = build_initial_conditions(X=0.06, S2=5.0, DO=100.0, mode="batch")
        a = simulate(initial_conditions=batch_conditions, duration_h=2.0, mode="batch")
        b = simulate(initial_conditions=other, duration_h=2.0, mode="batch")
        assert a.provenance.input_digest != b.provenance.input_digest

    def test_a_different_solver_changes_the_digest(self, batch_conditions) -> None:
        from models.solver import SolverConfig

        a = simulate(initial_conditions=batch_conditions, duration_h=2.0, mode="batch")
        b = simulate(
            initial_conditions=batch_conditions, duration_h=2.0, mode="batch",
            solver=SolverConfig(rtol=1e-8, atol=1e-11),
        )
        assert a.provenance.input_digest != b.provenance.input_digest

    def test_initial_condition_provenance_is_carried_per_key(self, batch_conditions) -> None:
        result = simulate(initial_conditions=batch_conditions, duration_h=1.0, mode="batch")
        assert result.provenance.initial_condition_provenance["S1"] == "reported"
        assert result.provenance.initial_condition_provenance["X"] == "assumed"

    def test_simulated_outputs_are_computed_never_reported(self, batch_conditions) -> None:
        result = simulate(initial_conditions=batch_conditions, duration_h=2.0, mode="batch")
        for port_id, value in result.output_quantities().items():
            assert value["provenance"] == "computed"
            assert value["basis"] == "computed"
            assert port_by_id(port_id).port_id == port_id


class TestReferenceRecords:
    """GJ-16: reported outcomes are reference records, not simulator output."""

    def test_measured_and_predicted_biomass_are_distinct_records(self) -> None:
        predicted = model_prediction()
        assert predicted.value == 19.44
        assert predicted.observation_id == "results.model_predicted_biomass"
        assert predicted.note.startswith("A MODEL PREDICTION")
        ids = {o.observation_id for o in reported_observations()}
        assert "abstract.optimised_process_biomass" in ids
        assert predicted.observation_id in ids

    def test_the_abstract_reports_twenty_point_seven(self) -> None:
        from models.reference import observation

        record = observation("abstract.optimised_process_biomass")
        assert record.value == 20.7
        assert record.unit == "g/L"
        assert record.provenance is Provenance.REPORTED
        assert record.source.printed_page == 1

    def test_the_reported_range_is_not_collapsed(self) -> None:
        from models.reference import observation

        record = observation("results.optimised_process_biomass_range")
        assert record.value is None
        assert record.value_range == (19.9, 21.5)

    def test_measured_outcomes_exclude_the_model_prediction(self) -> None:
        ids = {o.observation_id for o in measured_outcomes()}
        assert "results.model_predicted_biomass" not in ids
        assert "abstract.optimised_process_biomass" in ids

    def test_the_selected_recipe_is_reported_with_explicit_conversions(self) -> None:
        recipe = selected_recipe()
        assert recipe["glycerol_percent_wv"] == 17.5
        assert recipe["yeast_extract_percent_wv"] == 24.5
        assert recipe["flow_mL_per_h"] == 0.72
        assert recipe["S10_g_per_L"] == 175.0
        assert recipe["S20_g_per_L"] == 245.0
        assert "NOT implemented" in recipe["derived_by"]

    def test_conditions_cover_the_reported_setup(self) -> None:
        labels = {c["id"] for c in operating_conditions()}
        assert {
            "flask_geometry", "working_volume", "temperature", "shaking_speed",
            "initial_od600", "initial_glycerol", "online_do_measurement", "feeding_start",
        } <= labels

    def test_the_paper_gives_no_od600_to_dcw_calibration(self) -> None:
        items = {c["id"]: c for c in operating_conditions()}
        assert "no OD600-to-DCW" in items["initial_od600"]["note"]

    def test_feed_experiments_keep_missing_compositions_as_none(self) -> None:
        rows = {row["id"]: row for row in feed_experiments()}
        assert rows["exp_3"]["glycerol_percent_wv"] == 30.0
        assert rows["exp_5"]["glycerol_percent_wv"] is None
        assert rows["exp_5"]["note"]

    def test_unavailable_data_is_recorded_with_consequences(self) -> None:
        items = {item["item"]: item for item in unavailable_data()}
        assert "fed-batch time-course measurements" in items
        assert "NOT met" in items["fed-batch time-course measurements"]["consequence"]
        assert "OD600 to dry-cell-weight calibration" in items

    def test_paper_reproduction_is_declared_unmet(self) -> None:
        manifest = dataset_manifest()
        assert manifest["paper_reproduction_status"].startswith("not achievable")

    def test_simulator_never_returns_the_reference_numbers(self, fed_batch_conditions) -> None:
        """A run must not be able to 'reach' 19.44 or 20.7 by construction."""
        from models.fed_batch import FeedProgram

        feed = FeedProgram.from_recipe(17.5, 24.5, 0.72, start_time_h=6.0)
        result = simulate(
            initial_conditions=fed_batch_conditions, duration_h=6.0,
            mode="fed_batch", feed=feed,
        )
        values = {round(o.value, 6) for o in reported_observations() if o.value}
        assert result.final_state.X not in values
        assert 20.7 not in (result.final_state.X,)
        assert 19.44 not in (result.final_state.X,)
        # and the value is not even the paper's order of magnitude yet
        assert result.final_state.X < 20.7