"""Acceptance tests GJ-13, GJ-14, GJ-17 and GJ-18, plus the solver contract.

GJ-13  numerical integration: finite outputs, reproducibility under fixed
       settings, physically valid states within the stated domain
GJ-14  missing initial conditions stay unresolved and prevent a simulation
GJ-17  invalid input or a failed integration returns structured diagnostics
       rather than a plausible-looking success
GJ-18  explicit quantity keys, units, value states and provenance, and
       refused semantic conversions
"""

from __future__ import annotations

import math

import pytest

from models.composition import (
    ALL_PORTS,
    CONTRACT_VERSION_COMPATIBLE,
    REFUSED_MAPPINGS,
    CompositionMismatch,
    PortDirection,
    check_connection,
    manifest,
    port_by_id,
)
from models.composition import assert_contract_compatibility
from models.diagnostics import DiagnosticCode, Severity
from models.fed_batch import FeedProgram
from models.initial import build_initial_conditions
from models.reference import selected_recipe
from models.simulation import MODE_BATCH, MODE_FED_BATCH, simulate
from models.solver import SOLVER_NAME, SolverConfig, SolverError, integrate
from schemas.state import State, StateError, UnresolvedInitialCondition, validate_state

#: A well-formed 7-component state and a right-hand side that does nothing, for
#: exercising the solver's own guards rather than the model's equations.
_FLAT_Y0 = (1.0, 1.0, 1.0, 50.0, 0.5, 0.5, 0.1)


def _flat_rhs(t: float, y: tuple[float, ...]) -> tuple[float, ...]:
    return (0.0,) * len(y)


class TestIntegration:
    """GJ-13."""

    def test_a_short_batch_run_is_finite_and_admissible(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH
        )
        assert result.ok, [d.message for d in result.diagnostics if d.severity.value == "error"]
        assert result.times_h[0] == 0.0
        assert result.times_h[-1] == pytest.approx(3.0)
        for state in result.states:
            for value in state.as_vector():
                assert math.isfinite(value)

    def test_the_trajectory_is_monotone_in_time(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH
        )
        assert result.times_h == sorted(result.times_h)
        assert len(result.times_h) == len(set(result.times_h))

    def test_reproducible_under_fixed_settings(self, batch_conditions) -> None:
        config = SolverConfig(rtol=1e-7, atol=1e-10)
        a = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH,
            solver=config,
        )
        b = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH,
            solver=config,
        )
        assert [s.as_vector() for s in a.states] == [s.as_vector() for s in b.states]

    def test_states_stay_inside_the_stated_domain(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=6.0, mode=MODE_BATCH
        )
        for state in result.states:
            assert state.X >= 0.0
            assert state.S1 >= 0.0
            assert state.S2 >= 0.0
            assert 0.0 <= state.DO <= 100.0
            assert state.e1 >= 0.0 and state.e2 >= 0.0
            assert state.V > 0.0

    def test_requested_output_times_are_hit_exactly(self, batch_conditions) -> None:
        wanted = [0.0, 0.5, 1.0, 2.0, 3.0]
        result = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH,
            output_times_h=wanted,
        )
        assert result.ok
        for t in wanted:
            assert any(abs(x - t) < 1e-12 for x in result.times_h), f"{t} h missing"

    def test_solver_reports_its_work(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH
        )
        report = result.result.solver_report()
        assert report["steps_taken"] > 0
        assert report["smallest_step_h"] <= report["largest_step_h"]
        assert report["reached_time_h"] == pytest.approx(3.0)

    def test_the_solver_is_named_in_the_result(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0, mode=MODE_BATCH
        )
        assert result.metadata["solver"]["name"] == SOLVER_NAME
        assert result.provenance.solver["name"] == SOLVER_NAME

    def test_default_step_limit_respects_the_reported_kla(self) -> None:
        """h_max is chosen from kLa = 133 h^-1, not picked for convenience."""
        config = SolverConfig()
        assert config.h_max * 133.0 < 2.8

    def test_simulation_is_reproducible_across_processes(self, batch_conditions) -> None:
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; sys.path.insert(0, %r)\n"
            "from models.initial import build_initial_conditions\n"
            "from models.simulation import simulate\n"
            "ic = build_initial_conditions(X=0.05, S2=5.0, DO=100.0, mode='batch')\n"
            "r = simulate(initial_conditions=ic, duration_h=3.0, mode='batch')\n"
            "print(repr(r.final_state.X), r.provenance.input_digest[:16])\n" % str(root)
        )
        outputs = set()
        for _ in range(2):
            completed = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, check=True
            )
            outputs.add(completed.stdout.strip())
        assert len(outputs) == 1

        local = simulate(
            initial_conditions=batch_conditions, duration_h=3.0, mode=MODE_BATCH
        )
        assert outputs.pop().startswith(repr(local.final_state.X))


class TestMissingInitialConditions:
    """GJ-14."""

    def test_an_incomplete_state_cannot_be_constructed(self) -> None:
        from schemas.state import InitialConditions

        with pytest.raises(UnresolvedInitialCondition) as excinfo:
            InitialConditions(
                values={"X": 0.05, "S1": 2.76},
                units={},
                provenance={},
                mode="batch",
            )
        assert set(excinfo.value.missing) >= {"S2", "DO", "V", "e1", "e2"}

    def test_the_message_names_the_missing_values(self) -> None:
        from schemas.state import InitialConditions

        with pytest.raises(UnresolvedInitialCondition) as excinfo:
            InitialConditions(values={}, units={}, provenance={}, mode="batch")
        assert "will not be defaulted" in str(excinfo.value)

    def test_nothing_is_substituted_for_a_missing_value(self) -> None:
        """There is no path from the reported OD600 to a biomass default."""
        from models.initial import MissingInitialCondition

        with pytest.raises(MissingInitialCondition) as excinfo:
            build_initial_conditions(X=None, S2=5.0, DO=100.0, mode="batch")
        assert excinfo.value.missing == ("X",)

    def test_an_unresolved_culture_cannot_reach_the_simulator(self) -> None:
        """The refusal happens while building the conditions, not mid-run."""
        with pytest.raises(Exception):
            bad = build_initial_conditions(X=None, S2=5.0, DO=100.0, mode="batch")  # noqa: F841
            simulate(initial_conditions=bad, duration_h=1.0, mode=MODE_BATCH)


class TestStructuredFailures:
    """GJ-17: no plausible-looking success out of a failed run."""

    def test_an_unknown_mode_fails_with_a_diagnostic(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0, mode="chemostat"
        )
        assert result.ok is False
        assert result.final_state is None
        codes = [d.code for d in result.diagnostics]
        assert DiagnosticCode.INPUT_INVALID in codes

    def test_a_feed_supplied_to_a_batch_run_is_refused(self, batch_conditions) -> None:
        feed = FeedProgram.from_recipe(17.5, 24.5, 0.72)
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0,
            mode=MODE_BATCH, feed=feed,
        )
        assert result.ok is False
        message = " ".join(d.message for d in result.diagnostics)
        assert "no feed" in message

    def test_fed_batch_without_a_feed_is_refused(self, fed_batch_conditions) -> None:
        result = simulate(
            initial_conditions=fed_batch_conditions, duration_h=1.0,
            mode=MODE_FED_BATCH,
        )
        assert result.ok is False
        assert DiagnosticCode.INPUT_MISSING in [d.code for d in result.diagnostics]

    def test_a_non_positive_duration_is_refused(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=0.0, mode=MODE_BATCH
        )
        assert result.ok is False
        assert DiagnosticCode.INPUT_INVALID in [d.code for d in result.diagnostics]

    def test_an_end_time_before_the_start_is_refused(self) -> None:
        result = integrate(lambda t, y: y, 5.0, (1.0,), 1.0)
        assert result.ok is False
        assert DiagnosticCode.INPUT_INVALID in [d.code for d in result.diagnostics]

    def test_an_output_time_outside_the_interval_is_refused(self) -> None:
        result = integrate(
            _flat_rhs, 0.0, _FLAT_Y0, 1.0, output_times=[5.0]
        )
        assert result.ok is False
        assert DiagnosticCode.INPUT_INVALID in [d.code for d in result.diagnostics]

    def test_step_budget_exhaustion_is_a_structured_failure(self) -> None:
        result = integrate(
            _flat_rhs, 0.0, _FLAT_Y0, 10.0,
            config=SolverConfig(max_steps=5, h_init=1e-4, h_max=1.0),
        )
        assert result.ok is False
        assert DiagnosticCode.SOLVER_FAILED in [d.code for d in result.diagnostics]

    def test_a_diverging_rhs_returns_no_trajectory(self) -> None:
        def explosive(t, y):
            return (y[0] ** 2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        result = integrate(
            explosive, 0.0, (1.0, 1.0, 1.0, 50.0, 0.5, 0.5, 0.1), 10.0,
            config=SolverConfig(rtol=1e-10, atol=1e-14, h_min=1e-12),
        )
        assert result.ok is False
        assert result.diagnostics.error()

    def test_an_inadmissible_initial_state_is_refused(self) -> None:
        """Dissolved oxygen outside 0-100 % at t=0 is refused before any step."""
        result = integrate(
            _flat_rhs, 0.0, (1.0, 1.0, 1.0, -5.0, 0.5, 0.5, 0.1), 1.0
        )
        assert result.ok is False
        assert result.states == [result.states[0]]

    def test_diagnostics_serialise(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0, mode="batch"
        )
        payload = result.to_dict()
        assert isinstance(payload["diagnostics"], list)
        for entry in payload["diagnostics"]:
            assert set(entry) >= {"code", "severity", "message", "where"}
            assert entry["severity"] in {"info", "warning", "error"}

    def test_every_run_carries_the_unresolved_transcription_warnings(
        self, batch_conditions
    ) -> None:
        """Whatever remains unresolved must be visible on every run.

        TN-04 was resolved by a rendering check and no longer appears; TN-02
        is still genuinely open and must be reported.
        """
        result = simulate(
            initial_conditions=batch_conditions, duration_h=1.0, mode=MODE_BATCH
        )
        warnings = [
            d for d in result.diagnostics if d.severity is Severity.WARNING
        ]
        notes = {d.detail.get("note_id") for d in warnings}
        assert "TN-02" in notes
        assert "TN-04" not in notes
        for d in warnings:
            assert d.remediation


class TestCompositionCompatibility:
    """GJ-18: explicit keys, units, value states, and refused conversions."""

    def test_every_port_declares_a_quantity_unit_and_direction(self) -> None:
        for port in ALL_PORTS:
            assert port.port_id
            assert port.quantity
            assert port.unit
            assert isinstance(port.direction, PortDirection)

    def test_the_declared_outputs_are_the_documented_ones(self) -> None:
        expected = {
            "biomass_concentration": ("mass_concentration", "g/L"),
            "glycerol_concentration": ("mass_concentration", "g/L"),
            "complex_substrate_concentration": ("mass_concentration", "g/L"),
            "dissolved_oxygen": ("dimensionless", "%"),
            "culture_volume": ("volume", "L"),
            "simulation_time": ("time", "h"),
        }
        for port_id, (quantity, unit) in expected.items():
            port = port_by_id(port_id)
            assert port.quantity == quantity
            assert port.unit == unit

    def test_the_enzyme_fractions_are_computed_but_withheld(self) -> None:
        """A normalised enzyme fraction is internal state, not a process quantity.

        The model integrates e1 and e2 (eq. 7) and they appear in every
        trajectory, but publishing them would make them connectable to any
        dimensionless value in the repository. That is a connection that looks
        legal and means nothing, so they are withheld and the reason recorded.
        """
        from models.composition import WITHHELD_STATES

        withheld = {w["state_key"] for w in WITHHELD_STATES}
        assert withheld == {"e1", "e2"}
        for record in WITHHELD_STATES:
            assert record["reason"]
        for port_id in ("enzyme_fraction_1", "enzyme_fraction_2"):
            with pytest.raises(KeyError):
                port_by_id(port_id)

    def test_feed_flow_is_declared_as_a_volumetric_rate(self) -> None:
        """Volume flow, in the unit the paper's Table 1 prints.

        The composition contract registers ``mL/h`` and ``mL/min`` for
        ``volume_flow`` but not ``L/h``, so a port declaring ``L/h`` would be
        published unusable and could never be connected. The model integrates
        in L/h and converts on the way in; the declared unit is mL/h.
        """
        port = port_by_id("feed_flow_rate")
        assert port.quantity == "volume_flow"
        assert port.unit == "mL/h"
        assert port.temporal_basis.value == "rate"
        assert "mL/h -> L/h" in port.inbound_conversion

    def test_the_lumped_substrate_requires_attribution(self) -> None:
        port = port_by_id("complex_substrate_concentration")
        assert port.attribution_required is True
        assert "No component identity" in port.description

    def test_outputs_expose_value_state_and_provenance(self, batch_conditions) -> None:
        result = simulate(
            initial_conditions=batch_conditions, duration_h=2.0, mode=MODE_BATCH
        )
        outputs = result.output_quantities()
        assert set(outputs) >= {
            "biomass_concentration", "glycerol_concentration",
            "complex_substrate_concentration", "dissolved_oxygen", "culture_volume",
        }
        for payload in outputs.values():
            assert payload["value_state"] in {"number", "zero"}
            assert payload["provenance"] == "computed"
            assert payload["quantity"]
            assert payload["unit"]

    def test_a_stated_zero_is_distinguished_from_a_number(self, batch_conditions) -> None:
        conditions = build_initial_conditions(X=0.0, S2=5.0, DO=100.0, mode="batch")
        result = simulate(
            initial_conditions=conditions, duration_h=0.5, mode=MODE_BATCH
        )
        state = result.output_quantities()["biomass_concentration"]
        assert state["value"] == 0.0
        assert state["value_state"] == "zero"

    def test_dissolved_oxygen_is_not_connectable_as_a_mass_fraction(self) -> None:
        with pytest.raises(CompositionMismatch, match="orders of magnitude"):
            check_connection("dissolved_oxygen", "mass_fraction")

    def test_dissolved_oxygen_is_not_connectable_as_a_mass_concentration(self) -> None:
        with pytest.raises(CompositionMismatch, match="needs C"):
            check_connection("dissolved_oxygen", "mass_concentration")

    def test_the_lumped_substrate_is_not_a_mass_fraction(self) -> None:
        with pytest.raises(CompositionMismatch, match="lumped"):
            check_connection("complex_substrate_concentration", "mass_fraction")

    def test_a_concentration_is_not_a_mass_flow(self) -> None:
        with pytest.raises(CompositionMismatch, match="not a flow"):
            check_connection("glycerol_concentration", "mass_flow")

    def test_a_concentration_is_not_a_mass(self) -> None:
        with pytest.raises(CompositionMismatch, match="g/L"):
            check_connection("biomass_concentration", "mass")

    def test_an_unrelated_quantity_is_refused_with_a_reason(self) -> None:
        with pytest.raises(CompositionMismatch, match="different physical quantity"):
            check_connection("culture_volume", "temperature")

    def test_the_matching_quantity_is_accepted(self) -> None:
        assert check_connection("biomass_concentration", "mass_concentration")
        assert check_connection("culture_volume", "volume")

    def test_every_refusal_carries_a_reason(self) -> None:
        for subject, refused, reason in REFUSED_MAPPINGS:
            assert reason and len(reason) > 40, subject
            with pytest.raises(CompositionMismatch):
                check_connection(subject, refused)

    def test_an_unknown_contract_version_is_refused(self) -> None:
        assert_contract_compatibility(CONTRACT_VERSION_COMPATIBLE)
        with pytest.raises(CompositionMismatch, match="was offered"):
            assert_contract_compatibility("9.9.9")

    def test_the_manifest_declares_the_registration_relationship(self) -> None:
        document = manifest()
        assert document["registered_in_composition_layer"] is True
        assert document["registered_model_id"] == "ganjave"
        assert "does not import the composition layer" in document["registration_note"]
        assert "composition.adapters.ganjave" in document["registration_note"]

    def test_the_contract_reports_its_validation_status(self) -> None:
        """Being composable is not the same claim as reproducing the paper."""
        claim = manifest()["validation_claim"]
        assert claim["implementation_status"] == "implemented"
        assert claim["reproduction_status"] == "not_yet_validated"
        assert claim["what_is_not_validated"]
        unresolved = {item["item_id"] for item in claim["unresolved_items"]}
        assert "TN-02" in unresolved
        assert "PAPER_REPRODUCTION" in unresolved

    def test_required_inputs_have_no_defaults(self) -> None:
        """The three unstated initial conditions are required and undefaulted."""
        from models.composition import required_input_ports

        required = {p.port_id for p in required_input_ports("fed_batch")}
        for port_id in (
            "initial_biomass_concentration",
            "initial_complex_substrate_concentration",
            "initial_dissolved_oxygen",
            "feed_glycerol_concentration",
            "feed_complex_substrate_concentration",
            "feed_flow_rate",
        ):
            assert port_id in required, port_id
            assert port_by_id(port_id).default_value is None, port_id

    def test_defaults_are_reported_not_invented(self) -> None:
        """Where a default exists, the paper stated it."""
        for port_id, value, source in (
            ("initial_glycerol_concentration", 2.76, "p. 2"),
            ("initial_culture_volume", 0.1, "p. 2"),
            ("feed_start_time", 0.0, "p. 3"),
        ):
            port = port_by_id(port_id)
            assert port.default_value == value
            assert port.default_provenance == "reported"
            assert source in port.default_source

    def test_every_port_states_its_quantity_and_unit(self) -> None:
        from models.composition import ALL_PORTS, COMPOSITION_QUANTITY

        declared = set(COMPOSITION_QUANTITY.values())
        for port in ALL_PORTS:
            assert port.quantity in declared, port.port_id
            assert port.unit
            assert port.label
            if port.direction.value == "input" and port.required:
                assert port.description, port.port_id

    def test_the_manifest_lists_the_non_capabilities(self) -> None:
        text = " ".join(manifest()["non_capabilities"]).lower()
        for phrase in ("parameter estimation", "optimisation", "protein", "scale-up"):
            assert phrase in text

    def test_no_port_carries_a_component_identity(self) -> None:
        for port in ALL_PORTS:
            assert port.to_dict()["has_component_identity"] is False


class TestSolverConfiguration:
    def test_bad_tolerances_are_refused(self) -> None:
        with pytest.raises(SolverError, match="positive"):
            SolverConfig(rtol=0.0)
        with pytest.raises(SolverError, match="positive"):
            SolverConfig(atol=-1.0)

    def test_inconsistent_step_sizes_are_refused(self) -> None:
        with pytest.raises(SolverError, match="h_min <= h_init <= h_max"):
            SolverConfig(h_init=1.0, h_max=0.1, h_min=1e-6)

    def test_configuration_is_recorded_with_the_run(self) -> None:
        config = SolverConfig(rtol=1e-5, atol=1e-8, h_max=0.02)
        recorded = config.to_dict()
        assert recorded["rtol"] == 1e-5
        assert recorded["h_max"] == 0.02
        assert recorded["name"] == SOLVER_NAME


class TestStateValidation:
    def test_a_valid_state_passes(self) -> None:
        validate_state(
            State(t=1.0, X=1.0, S1=1.0, S2=1.0, DO=50.0, e1=0.5, e2=0.5, V=0.1), t=1.0
        )

    def test_a_negative_concentration_is_refused(self) -> None:
        with pytest.raises(StateError, match="negative"):
            validate_state(
                State(t=1.0, X=1.0, S1=-0.1, S2=1.0, DO=50.0, e1=0.5, e2=0.5, V=0.1), t=1.0
            )

    def test_dissolved_oxygen_outside_its_range_is_refused(self) -> None:
        with pytest.raises(StateError, match="physical range"):
            validate_state(
                State(t=1.0, X=1.0, S1=1.0, S2=1.0, DO=140.0, e1=0.5, e2=0.5, V=0.1), t=1.0
            )

    def test_a_zero_volume_is_refused(self) -> None:
        with pytest.raises(StateError, match="strictly positive"):
            validate_state(
                State(t=1.0, X=1.0, S1=1.0, S2=1.0, DO=50.0, e1=0.5, e2=0.5, V=0.0), t=1.0
            )

    def test_states_are_not_silently_clipped(self) -> None:
        """A negative value must raise, never be floored at zero."""
        with pytest.raises(StateError):
            validate_state(
                State(t=1.0, X=-1e-12, S1=1.0, S2=1.0, DO=50.0, e1=0.5, e2=0.5, V=0.1),
                t=1.0,
            )

    def test_vector_round_trip_is_exact(self) -> None:
        state = State(t=1.0, X=1.5, S1=2.5, S2=3.5, DO=4.5, e1=0.5, e2=0.6, V=0.105)
        assert State.from_vector(1.0, state.as_vector()) == state

    def test_a_wrong_length_vector_is_refused(self) -> None:
        with pytest.raises(StateError, match="7 components"):
            State.from_vector(0.0, (1.0, 2.0))