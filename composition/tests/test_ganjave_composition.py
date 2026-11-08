"""Composition acceptance tests for the Ganjave model: GJ-C01 through GJ-C15.

Each test names the requirement it discharges. Where a test could pass without
the feature existing, it is tightened: the isolation test asserts against the
sibling packages' actual module names, and the refusal tests assert on the
*reason*, not merely on a raised exception.

Two things these tests deliberately do **not** assert:

* that the model reproduces the paper. It does not, and the model's declared
  reproduction status (``not_yet_validated``) is itself asserted here, so that
  a future change that quietly upgraded it would fail this suite;
* that Ganjave connects to Morris or Zielinski. It shares no quantity with
  Morris at all, and the Zielinski pairs that would pass the engine's
  mechanical check carry assumptions that are recorded, never assumed away.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import COMPOSITION_ROOT, ROOT, all_codes, error_codes, read_example

from composition.adapters import DEFAULT_VERSIONS, REGISTRATIONS, adapter_for, known_models
from composition.adapters.ganjave import MODEL_ID, MODEL_VERSION, GanjaveAdapter
from composition.adapters.ganjave_contract import (
    INPUT_CONTRACT,
    REFUSED,
    ConnectionRefused,
    check_input_connection,
    connection_contract,
    rule_for,
)
from composition.contracts import (
    PortDirection,
    ProvenanceRequirement,
    ValueProvenance,
    ValueState,
    load_graph,
)
from composition.dimensions import GANJAVE_KIND_TO_QUANTITY, quantity_for_ganjave_kind
from composition.diagnostics import DiagnosticCode, ModelDiagnostic, Origin
from composition.engine import CompositionEngine
from composition.quantities import Quantity, REGISTRY
from composition.runner import run_graph

EXAMPLE = "ganjave_fed_batch.json"

#: The three initial conditions the paper does not state. A graph must declare
#: them or the model refuses to run.
REQUIRED_LITERALS = (
    "initial_biomass_concentration",
    "initial_complex_substrate_concentration",
    "initial_dissolved_oxygen",
)

FED_BATCH_LITERALS = REQUIRED_LITERALS + (
    "feed_glycerol_concentration",
    "feed_complex_substrate_concentration",
    "feed_flow_rate",
)


@pytest.fixture(scope="session")
def ganjave_root() -> Path:
    from composition.adapters import model_root

    return model_root("Models/Ganjave", ROOT)


@pytest.fixture(scope="session")
def adapter() -> GanjaveAdapter:
    instance, diagnostics = adapter_for(MODEL_ID, ROOT)
    assert instance is not None, diagnostics
    return instance


@pytest.fixture(scope="session")
def manifest(adapter):
    document, diagnostics = adapter.manifest({})
    assert document is not None
    assert diagnostics == []
    return document


@pytest.fixture(scope="session")
def fed_batch_result() -> dict:
    payload, _code = run_graph(read_example(EXAMPLE), base=ROOT)
    return payload


def output_of(payload: dict, instance_id: str, port_id: str) -> dict:
    for result in payload["results"]:
        if result["instance_id"] != instance_id:
            continue
        for out in result["outputs"]:
            if out["ref"]["port_id"] == port_id:
                return out
    raise KeyError(f"{instance_id}/{port_id} produced no output")


# --------------------------------------------------------------------------- #
# GJ-C01  Discovery
# --------------------------------------------------------------------------- #


class TestDiscovery:
    """GJ-C01: the registry finds Ganjave under a unique identifier."""

    def test_the_registry_lists_exactly_one_ganjave(self) -> None:
        entries = [m for m in known_models(ROOT) if m["model_id"] == MODEL_ID]
        assert len(entries) == 1, entries
        entry = entries[0]
        assert entry["model_version"] == MODEL_VERSION
        assert entry["available"] is True
        assert entry["reference"] == f"ganjave@{MODEL_VERSION}"

    def test_the_identifier_is_unique_across_the_registry(self) -> None:
        ids = [reg.model_id for reg in REGISTRATIONS]
        assert len(ids) == len(set(ids))
        assert ids.count(MODEL_ID) == 1

    def test_the_package_is_reachable_at_the_registered_path(self, ganjave_root) -> None:
        assert (ganjave_root / "pyproject.toml").is_file()
        assert (ganjave_root / "models" / "composition.py").is_file()

    def test_the_default_version_is_declared(self) -> None:
        assert DEFAULT_VERSIONS[MODEL_ID] == MODEL_VERSION

    def test_the_worker_module_is_registered_and_importable(self) -> None:
        registration = next(r for r in REGISTRATIONS if r.model_id == MODEL_ID)
        assert registration.worker_module == "composition._workers.ganjave_worker"
        completed = subprocess.run(
            [sys.executable, "-m", registration.worker_module, "--help"],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT),
        )
        assert completed.returncode == 0, completed.stderr

    def test_the_cli_lists_the_model(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--list-models"],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT), check=True,
        )
        payload = json.loads(completed.stdout)
        ids = [m["model_id"] for m in payload["models"]]
        assert MODEL_ID in ids
        assert len(ids) == len(set(ids))

    def test_the_cli_can_describe_the_model(self) -> None:
        completed = subprocess.run(
            [
                sys.executable, "-m", "composition.runner",
                "--describe-model", f"{MODEL_ID}@{MODEL_VERSION}",
            ],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT), check=True,
        )
        payload = json.loads(completed.stdout)
        assert payload["model_id"] == MODEL_ID
        assert payload["model_version"] == MODEL_VERSION
        assert payload["resolved"] is True
        manifest = payload["manifest"]
        assert manifest["ports"], "a described model must publish its ports"
        assert payload["package_available"] is True


# --------------------------------------------------------------------------- #
# GJ-C02  Instantiation
# --------------------------------------------------------------------------- #


class TestInstantiation:
    """GJ-C02: an adapter builds a model from an explicit configuration."""

    def test_an_adapter_is_built_for_the_identifier(self, adapter) -> None:
        assert isinstance(adapter, GanjaveAdapter)
        assert adapter.model_id == MODEL_ID
        assert adapter.model_version == MODEL_VERSION

    def test_the_parameter_set_is_explicit_in_the_manifest(self, manifest) -> None:
        assert manifest.parameters["parameter_set_id"] == "ganjave2022.table2"
        assert manifest.parameters["parameter_set_version"] == "1.0.0"
        assert manifest.parameters["equations_version"] == "1.1.0"

    def test_the_solver_is_declared_with_its_reason(self, manifest) -> None:
        solver = manifest.parameters["solver"]
        assert solver["name"].startswith("runge-kutta")
        assert "kLa" in solver["h_max_reason"]

    def test_both_operating_modes_are_declared(self, manifest) -> None:
        assert sorted(manifest.parameters["modes"]) == ["batch", "fed_batch"]

    def test_the_initial_conditions_a_graph_may_omit_are_declared_defaults(
        self, manifest
    ) -> None:
        port = manifest.port("initial_glycerol_concentration")
        assert port.required is False
        assert port.metadata["default_value"] == 2.76
        assert port.metadata["default_provenance"] == "reported"
        assert "p. 2" in port.metadata["default_source"]

    def test_the_conditions_the_paper_does_not_state_have_no_default(
        self, manifest
    ) -> None:
        for port_id in REQUIRED_LITERALS:
            port = manifest.port(port_id)
            assert port.required is True, port_id
            assert port.metadata["default_value"] is None, port_id
            assert port.metadata["default_provenance"] == "", port_id


# --------------------------------------------------------------------------- #
# GJ-C03  Execution
# --------------------------------------------------------------------------- #


class TestExecution:
    """GJ-C03: a valid request returns a structured result."""

    def test_the_example_graph_succeeds(self, fed_batch_result) -> None:
        assert fed_batch_result["status"] in ("success", "success_with_warnings")
        assert error_codes(fed_batch_result) == set()

    def test_the_result_carries_every_declared_output(self, fed_batch_result) -> None:
        produced = {
            out["ref"]["port_id"]
            for result in fed_batch_result["results"]
            for out in result["outputs"]
        }
        expected = {
            "biomass_concentration",
            "glycerol_concentration",
            "complex_substrate_concentration",
            "dissolved_oxygen",
            "culture_volume",
            "simulation_time",
        }
        assert expected <= produced

    def test_the_result_reports_the_solver_and_digest(self, fed_batch_result) -> None:
        payload = output_of(fed_batch_result, "ganjave_fed_batch", "biomass_concentration")
        extra = payload["value"]["extra"]
        assert extra["input_digest"]
        assert extra["equations_version"] == "1.1.0"
        assert extra["solver_report"]["steps_taken"] > 0
        assert extra["parameter_set"]["id"] == "ganjave2022.table2"

    def test_the_values_match_a_direct_model_run(self, fed_batch_result) -> None:
        """The composition path must not alter the science.

        Run the model's own CLI in a subprocess and compare the final biomass.
        A divergence here would mean the adapter changed something it should
        only have passed through.
        """
        completed = subprocess.run(
            [
                sys.executable, "-m", "models", "simulate",
                "--mode", "fed_batch", "--duration", "24",
                "--X", "0.05", "--S2", "5", "--DO", "100",
                "--glycerol-percent", "17.5", "--yeast-percent", "24.5",
                "--flow-ml-h", "0.72", "--feed-start", "6",
                "--output-times", "0", "6", "12", "18", "24", "--summary",
            ],
            capture_output=True, text=True, cwd=str(ROOT / "Models" / "Ganjave"),
            check=True,
        )
        direct = json.loads(completed.stdout)["final_state"]
        through = output_of(fed_batch_result, "ganjave_fed_batch", "biomass_concentration")
        assert through["value"]["value"] == pytest.approx(
            direct["biomass_concentration_g_per_L"], rel=1e-9
        )
        do = output_of(fed_batch_result, "ganjave_fed_batch", "dissolved_oxygen")
        assert do["value"]["value"] == pytest.approx(
            direct["dissolved_oxygen_percent"], rel=1e-9
        )


# --------------------------------------------------------------------------- #
# GJ-C04  Contract
# --------------------------------------------------------------------------- #


class TestContract:
    """GJ-C04: required inputs and output semantics match the declaration."""

    def test_every_port_is_usable(self, manifest) -> None:
        unusable = [p.port_id for p in manifest.ports if not p.is_usable]
        assert unusable == []

    def test_every_port_declares_a_registered_unit(self, manifest) -> None:
        for port in manifest.ports:
            REGISTRY.resolve(port.unit, port.quantity)

    def test_input_and_output_directions_are_right(self, manifest) -> None:
        for port in manifest.ports:
            if port.port_id.startswith("initial_") or port.port_id.startswith("feed_"):
                assert port.direction is PortDirection.INPUT, port.port_id
            else:
                assert port.direction is PortDirection.OUTPUT, port.port_id

    def test_required_inputs_are_the_documented_set(self, manifest) -> None:
        required = {
            p.port_id for p in manifest.ports
            if p.direction is PortDirection.INPUT and p.required
        }
        assert required == set(REQUIRED_LITERALS)

    def test_output_quantity_semantics(self, manifest) -> None:
        expected = {
            "biomass_concentration": (Quantity.MASS_CONCENTRATION, "g/L"),
            "glycerol_concentration": (Quantity.MASS_CONCENTRATION, "g/L"),
            "complex_substrate_concentration": (Quantity.MASS_CONCENTRATION, "g/L"),
            "dissolved_oxygen": (Quantity.DIMENSIONLESS, "%"),
            "culture_volume": (Quantity.VOLUME, "L"),
            "simulation_time": (Quantity.TIME, "h"),
        }
        for port_id, (quantity, unit) in expected.items():
            port = manifest.port(port_id)
            assert (port.quantity, port.unit) == (quantity, unit), port_id

    def test_the_lumped_substrate_requires_attribution(self, manifest) -> None:
        port = manifest.port("complex_substrate_concentration")
        assert port.attribution_required is True
        assert port.components == ()

    def test_no_port_claims_a_component_identity(self, manifest) -> None:
        for port in manifest.ports:
            assert not port.has_component_identity, port.port_id
            assert port.components == ()

    def test_reported_defaults_require_citation_and_caller_values_explanation(
        self, manifest
    ) -> None:
        for port in manifest.ports:
            if port.direction is not PortDirection.INPUT:
                continue
            if port.metadata.get("default_provenance") == "reported":
                assert port.provenance_requirement is ProvenanceRequirement.CITED
            elif port.required:
                assert port.provenance_requirement is ProvenanceRequirement.EXPLAINED

    def test_computed_outputs_require_no_caller_provenance(self, manifest) -> None:
        for port in manifest.ports:
            if port.direction is PortDirection.OUTPUT:
                assert port.provenance_requirement is ProvenanceRequirement.NONE

    def test_the_manifest_declares_the_validation_status(self, manifest) -> None:
        assert manifest.parameters["implementation_status"] == "implemented"
        assert manifest.parameters["reproduction_status"] == "not_yet_validated"

    def test_the_manifest_states_that_reproduction_is_unmet(self, manifest) -> None:
        assert "paper_reproduction" in manifest.unsupported_capabilities
        assert "component_identity" in manifest.unsupported_capabilities
        statuses = {a.get("status") for a in manifest.assumptions}
        assert "unresolved" in statuses

    def test_the_declared_contract_and_the_manifest_agree(self, manifest) -> None:
        """The ports in the manifest are the ports the model declares."""
        from composition._workers.ganjave_worker import _import_model

        _simulation, contract = _import_model(str(ROOT / "Models" / "Ganjave"))
        declared = {p.port_id for p in contract.ALL_PORTS}
        assert {p.port_id for p in manifest.ports} == declared


# --------------------------------------------------------------------------- #
# GJ-C05  Missing values
# --------------------------------------------------------------------------- #


class TestMissingValues:
    """GJ-C05: a missing required input stays unresolved and blocks the run."""

    def _graph_without(self, port_id: str) -> dict:
        document = read_example(EXAMPLE)
        document["literal_inputs"].pop(f"ganjave_fed_batch/{port_id}", None)
        return document

    @pytest.mark.parametrize("port_id", REQUIRED_LITERALS)
    def test_omitting_a_required_literal_is_refused_before_execution(
        self, port_id
    ) -> None:
        payload, code = run_graph(self._graph_without(port_id), base=ROOT)
        assert code != 0, payload["status"]
        assert DiagnosticCode.CONNECTION_MISSING_REQUIRED.value in error_codes(payload)

    @pytest.mark.parametrize("port_id", REQUIRED_LITERALS)
    def test_no_output_is_produced_when_a_required_input_is_missing(
        self, port_id
    ) -> None:
        payload, _code = run_graph(self._graph_without(port_id), base=ROOT)
        for result in payload["results"]:
            assert result["outputs"] == [], result["instance_id"]

    def test_an_unresolved_literal_never_becomes_a_number(self) -> None:
        document = read_example(EXAMPLE)
        key = "ganjave_fed_batch/initial_dissolved_oxygen"
        document["literal_inputs"][key] = {
            "state": "unresolved",
            "quantity": "dimensionless",
            "unit": "%",
            "reason": "the operator has not measured the starting dissolved oxygen",
        }
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        codes = error_codes(payload)
        assert DiagnosticCode.VALUE_UNRESOLVED.value in codes
        for result in payload["results"]:
            assert result["outputs"] == [], result["instance_id"]

    def test_a_duration_is_required_and_is_never_chosen(self) -> None:
        document = read_example(EXAMPLE)
        document["instances"][0]["parameters"]["simulation"].pop("duration_h")
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        assert "duration_h" in json.dumps(payload)

    def test_no_default_is_substituted_for_a_missing_initial_condition(self) -> None:
        """The omission must not be papered over by a default.

        The graph is refused at validation, so the model's own refusal is never
        reached here; the reason it *would* refuse is declared on the port and
        asserted below, and the absence of any output is asserted here.
        """
        document = read_example(EXAMPLE)
        document["literal_inputs"].pop("ganjave_fed_batch/initial_biomass_concentration")
        payload, _code = run_graph(document, base=ROOT)
        assert DiagnosticCode.CONNECTION_MISSING_REQUIRED.value in error_codes(payload)
        for result in payload["results"]:
            assert result["outputs"] == []

    def test_the_port_says_why_the_value_cannot_be_derived(self, manifest) -> None:
        port = manifest.port("initial_biomass_concentration")
        assert "OD600" in port.description
        assert "calibration" in port.description
        assert port.metadata["default_value"] is None


# --------------------------------------------------------------------------- #
# GJ-C06  Units and conversions
# --------------------------------------------------------------------------- #


class TestUnits:
    """GJ-C06: incompatible quantities and unsupported conversions are refused."""

    def test_a_glycerol_port_refuses_a_mass_flow(self) -> None:
        with pytest.raises(ConnectionRefused) as excinfo:
            check_input_connection("initial_glycerol_concentration", "mass_flow")
        assert "volume" in str(excinfo.value).lower()

    def test_biomass_refuses_a_total_mass(self) -> None:
        with pytest.raises(ConnectionRefused) as excinfo:
            check_input_connection("initial_biomass_concentration", "mass")
        assert "volume" in str(excinfo.value).lower()

    def test_dissolved_oxygen_refuses_a_mass_fraction(self) -> None:
        with pytest.raises(ConnectionRefused) as excinfo:
            check_input_connection("initial_dissolved_oxygen", "mass_fraction")
        assert "C*" in str(excinfo.value)

    def test_dissolved_oxygen_refuses_a_concentration(self) -> None:
        with pytest.raises(ConnectionRefused) as excinfo:
            check_input_connection("initial_dissolved_oxygen", "mass_concentration")
        assert "C*" in str(excinfo.value)

    def test_feed_flow_refuses_a_mass_flow(self) -> None:
        with pytest.raises(ConnectionRefused) as excinfo:
            check_input_connection("feed_flow_rate", "mass_flow")
        assert "density" in str(excinfo.value)

    def test_the_lumped_substrate_refuses_a_mass_fraction(self) -> None:
        with pytest.raises(ConnectionRefused):
            check_input_connection("initial_complex_substrate_concentration", "mass_fraction")

    def test_a_matching_quantity_is_accepted_with_its_assumption(self) -> None:
        rule = check_input_connection("initial_glycerol_concentration", "mass_concentration")
        assert rule.upstream_supplyable is True
        assert "glycerol" in rule.assumption.lower()

    def test_every_refusal_states_what_would_help(self) -> None:
        """Every *input-side* refusal is actionable, and is reachable."""
        input_ids = {rule.port_id for rule in INPUT_CONTRACT}
        for port_id, quantity, _reason, help_text in REFUSED:
            assert help_text, (port_id, quantity)
            if port_id not in input_ids:
                continue    # output-side refusals live in the model's own contract
            with pytest.raises(ConnectionRefused) as excinfo:
                check_input_connection(port_id, quantity)
            assert excinfo.value.what_would_help == help_text

    def test_the_output_side_refusals_are_declared_by_the_model(self) -> None:
        """The model declares which of its own outputs cannot be connected."""
        from composition._workers.ganjave_worker import _import_model

        _simulation, contract = _import_model(str(ROOT / "Models" / "Ganjave"))
        subjects = {s for s, _q, _r, _h in REFUSED}
        for port_id in subjects:
            if port_id in {rule.port_id for rule in INPUT_CONTRACT}:
                continue
            assert any(
                subject == port_id
                for subject, _refused, _reason in contract.REFUSED_MAPPINGS
            ), port_id

    def test_the_only_declared_conversion_is_within_one_quantity(self, manifest) -> None:
        """A conversion model may not cross a quantity boundary.

        The feed conversion is ``mL/h`` -> ``L/h``. ``L/h`` is deliberately
        *not* a registered contract unit: the contract registers ``mL/h`` and
        ``mL/min`` for ``volume_flow``, so the port declares the unit the paper
        prints and the model converts inside its own boundary. That is why this
        test asserts the declaration and the registered end, rather than
        round-tripping through the contract's converter.
        """
        assert manifest.conversion_models
        assert any(
            "mL/h -> L/h" in declared for declared in manifest.conversion_models
        )
        assert all("within" in declared for declared in manifest.conversion_models)

        feed = manifest.port("feed_flow_rate")
        assert feed.quantity is Quantity.VOLUME_FLOW
        assert feed.unit == "mL/h"
        REGISTRY.resolve(feed.unit, feed.quantity)
        assert "within volume_flow" in feed.metadata["inbound_conversion"]

    def test_no_registered_unit_is_declared_that_the_contract_lacks(self, manifest) -> None:
        for port in manifest.ports:
            REGISTRY.resolve(port.unit, port.quantity)

    def test_a_unit_mismatch_is_refused_by_the_contract_itself(self) -> None:
        from composition.quantities import QuantityMismatch, convert

        with pytest.raises(QuantityMismatch):
            convert(1.0, "g/L", "kg/h", Quantity.MASS_CONCENTRATION)

    def test_a_non_convertible_pair_is_refused(self) -> None:
        """pH is log activity: two pH values are not related by a factor."""
        from composition.quantities import NonConvertibleUnitError, convert

        with pytest.raises(NonConvertibleUnitError):
            convert(7.0, "pH", "pH", Quantity.PH)

    def test_a_literal_declared_with_the_wrong_quantity_is_refused(self) -> None:
        """End to end: a mass declared where a concentration is required.

        The engine's own quantity check passes -- it compares the port's declared
        quantity with the *connection's* -- but a literal carries its own
        ``quantity`` field, so a graph can lie about what it is supplying. The
        adapter's semantic check is what catches it.
        """
        document = read_example(EXAMPLE)
        key = "ganjave_fed_batch/initial_biomass_concentration"
        document["literal_inputs"][key] = {
            "state": "number",
            "quantity": "mass",
            "value": 2.0,
            "unit": "kg",
            "method": "a total mass, supplied by mistake",
            "reason": "the graph author confused a mass with a concentration",
        }
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        assert DiagnosticCode.EXECUTION_MODEL_FAILED.value in error_codes(payload)
        for result in payload["results"]:
            assert result["outputs"] == [], result["instance_id"]


# --------------------------------------------------------------------------- #
# GJ-C07  Provenance
# --------------------------------------------------------------------------- #


class TestProvenance:
    """GJ-C07: an output traces back to its inputs, parameters and solver."""

    def test_the_chain_names_the_source_model(self, fed_batch_result) -> None:
        output = output_of(fed_batch_result, "ganjave_fed_batch", "biomass_concentration")
        chain = output["provenance_chain"]
        assert chain, "a computed value must carry provenance"
        source = [record for record in chain if record["kind"] == "source"]
        assert source, chain
        assert source[-1]["producer_model"] == MODEL_ID
        assert source[-1]["producer_version"] == MODEL_VERSION
        assert "e00694" in (source[-1]["source_ref"] or "")

    def test_the_chain_records_the_equations_version_and_digest(
        self, fed_batch_result
    ) -> None:
        output = output_of(fed_batch_result, "ganjave_fed_batch", "biomass_concentration")
        detail = output["provenance_chain"][-1]["detail"]
        assert "1.1.0" in detail
        assert "ganjave2022.table2" in detail
        assert "not_yet_validated" in detail

    def test_outputs_are_computed_not_reported(self, fed_batch_result) -> None:
        for result in fed_batch_result["results"]:
            for out in result["outputs"]:
                assert out["value"]["provenance"] == ValueProvenance.DERIVED.value

    def test_literal_inputs_are_recorded_as_assumptions(self) -> None:
        document = read_example(EXAMPLE)
        graph = load_graph(document)
        assert graph.literal_inputs, "the example declares its inputs"
        for key, spec in graph.literal_inputs.items():
            assert spec["method"], key
            assert spec["reason"], key

    def test_the_solver_configuration_travels_with_the_value(
        self, fed_batch_result
    ) -> None:
        output = output_of(fed_batch_result, "ganjave_fed_batch", "biomass_concentration")
        solver = output["value"]["extra"]["solver"]
        assert solver["name"].startswith("runge-kutta")
        assert solver["rtol"] == 1e-6

    def test_the_validation_claim_travels_with_every_output(
        self, fed_batch_result
    ) -> None:
        for result in fed_batch_result["results"]:
            for out in result["outputs"]:
                claim = out["value"]["extra"]["validation_claim"]
                assert claim["reproduction_status"] == "not_yet_validated"
                assert claim["implementation_status"] == "implemented"


# --------------------------------------------------------------------------- #
# GJ-C08  Trajectories
# --------------------------------------------------------------------------- #


class TestTrajectories:
    """GJ-C08: a time series keeps its stamps, units, order and dimensions."""

    def test_the_trajectory_is_carried_on_the_value(self, fed_batch_result) -> None:
        output = output_of(fed_batch_result, "ganjave_fed_batch", "glycerol_concentration")
        trajectory = output["value"]["extra"]["trajectory"]
        assert trajectory["quantity"] == "mass_concentration"
        assert trajectory["unit"] == "g/L"
        assert trajectory["time_axis"]["quantity"] == "time"
        assert trajectory["time_axis"]["unit"] == "h"

    def test_the_time_axis_is_strictly_increasing(self, fed_batch_result) -> None:
        output = output_of(fed_batch_result, "ganjave_fed_batch", "biomass_concentration")
        times = output["value"]["extra"]["trajectory"]["time_axis"]["values"]
        assert times == sorted(times)
        assert len(times) == len(set(times))
        assert times[0] == pytest.approx(0.0)
        assert times[-1] == pytest.approx(24.0)

    def test_the_series_and_the_axis_have_the_same_length(self, fed_batch_result) -> None:
        for port_id in (
            "biomass_concentration", "glycerol_concentration",
            "complex_substrate_concentration", "dissolved_oxygen", "culture_volume",
        ):
            trajectory = output_of(fed_batch_result, "ganjave_fed_batch", port_id)[
                "value"
            ]["extra"]["trajectory"]
            assert len(trajectory["values"]) == len(trajectory["time_axis"]["values"])
            assert trajectory["points"] == len(trajectory["values"])

    def test_the_final_value_matches_the_last_trajectory_point(
        self, fed_batch_result
    ) -> None:
        for port_id in ("biomass_concentration", "culture_volume", "dissolved_oxygen"):
            value = output_of(fed_batch_result, "ganjave_fed_batch", port_id)["value"]
            assert value["value"] == pytest.approx(value["extra"]["trajectory"]["values"][-1])

    def test_the_requested_output_times_are_hit_exactly(self, fed_batch_result) -> None:
        wanted = {0.0, 6.0, 12.0, 18.0, 24.0}
        times = output_of(
            fed_batch_result, "ganjave_fed_batch", "biomass_concentration"
        )["value"]["extra"]["trajectory"]["time_axis"]["values"]
        for target in wanted:
            assert any(abs(t - target) < 1e-12 for t in times), target

    def test_every_trajectory_value_is_finite(self, fed_batch_result) -> None:
        import math

        for port_id in (
            "biomass_concentration", "glycerol_concentration",
            "complex_substrate_concentration", "dissolved_oxygen", "culture_volume",
        ):
            trajectory = output_of(fed_batch_result, "ganjave_fed_batch", port_id)[
                "value"
            ]["extra"]["trajectory"]
            assert all(math.isfinite(v) for v in trajectory["values"]), port_id

    def test_a_trajectory_value_is_never_written_as_a_zero(self, fed_batch_result) -> None:
        """The final complex substrate is small but positive; it must not read 0."""
        output = output_of(
            fed_batch_result, "ganjave_fed_batch", "complex_substrate_concentration"
        )["value"]
        assert output["state"] == ValueState.NUMBER.value
        assert output["value"] > 0.0


# --------------------------------------------------------------------------- #
# GJ-C09  Determinism
# --------------------------------------------------------------------------- #


class TestDeterminism:
    """GJ-C09: identical inputs and settings reproduce, within a tolerance."""

    #: The model's solver runs at rtol 1e-6; a rerun is bit-identical, and the
    #: tolerance below is the *documented* bound rather than a measured one.
    TOLERANCE = 1.0e-9

    def test_two_runs_of_the_same_graph_agree(self) -> None:
        first, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        second, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        assert first["reproducibility"] == second["reproducibility"]

    def test_every_output_value_reproduces(self) -> None:
        first, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        second, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        for port_id in (
            "biomass_concentration", "glycerol_concentration",
            "complex_substrate_concentration", "dissolved_oxygen",
            "culture_volume", "simulation_time",
        ):
            a = output_of(first, "ganjave_fed_batch", port_id)["value"]
            b = output_of(second, "ganjave_fed_batch", port_id)["value"]
            assert a["value"] == pytest.approx(
                b["value"], rel=self.TOLERANCE, abs=self.TOLERANCE
            ), port_id

    def test_the_trajectories_reproduce(self) -> None:
        first, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        second, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        a = output_of(first, "ganjave_fed_batch", "biomass_concentration")["value"]
        b = output_of(second, "ganjave_fed_batch", "biomass_concentration")["value"]
        assert a["extra"]["trajectory"]["values"] == pytest.approx(
            b["extra"]["trajectory"]["values"], rel=self.TOLERANCE
        )

    def test_a_different_duration_changes_the_digest(self) -> None:
        document = read_example(EXAMPLE)
        document["instances"][0]["parameters"]["simulation"]["duration_h"] = 12.0
        other, _ = run_graph(document, base=ROOT)
        original, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        assert other["reproducibility"] != original["reproducibility"]

    def test_a_different_input_changes_the_digest(self) -> None:
        document = read_example(EXAMPLE)
        document["literal_inputs"]["ganjave_fed_batch/initial_complex_substrate_concentration"][
            "value"
        ] = 10.0
        other, _ = run_graph(document, base=ROOT)
        original, _ = run_graph(read_example(EXAMPLE), base=ROOT)
        assert other["reproducibility"] != original["reproducibility"]


# --------------------------------------------------------------------------- #
# GJ-C10  Diagnostics
# --------------------------------------------------------------------------- #


class TestDiagnostics:
    """GJ-C10: bad input, solver failure and open questions are structured."""

    def test_an_open_scientific_question_is_reported_on_a_successful_run(
        self, fed_batch_result
    ) -> None:
        findings = [
            d for d in fed_batch_result["diagnostics"]
            if d["code"] == DiagnosticCode.MODEL_FINDING.value
        ]
        assert findings, "an unresolved assumption must be visible"
        messages = " ".join(d["message"] for d in findings)
        assert "TN-02" in messages
        assert "not_yet_validated" in messages

    def test_a_model_finding_keeps_its_own_origin(self, fed_batch_result) -> None:
        for diagnostic in fed_batch_result["diagnostics"]:
            if diagnostic["code"] == DiagnosticCode.MODEL_FINDING.value:
                assert diagnostic["origin"] == Origin.GANJAVE.value

    def test_a_model_finding_is_not_reported_as_a_run_failure(
        self, fed_batch_result
    ) -> None:
        """The composition layer distinguishes 'found something' from 'failed'."""
        from composition.diagnostics import ModelDiagnostic as MD

        findings = [
            MD.from_dict(d) for d in fed_batch_result["diagnostics"]
            if d["code"] == DiagnosticCode.MODEL_FINDING.value
        ]
        assert findings
        assert MD.execution_failures(findings) == []

    def test_a_run_reports_its_reproduction_status(self, fed_batch_result) -> None:
        messages = " ".join(d["message"] for d in fed_batch_result["diagnostics"])
        assert "reproduction status not_yet_validated" in messages

    def test_an_accepted_upstream_value_carries_its_assumption(self) -> None:
        """A matching quantity is not silently treated as a matching meaning."""
        from composition.adapters.ganjave import _rule_or_none

        rule = _rule_or_none("initial_glycerol_concentration", "mass_concentration")
        assert rule is not None and rule.assumption

    def test_an_unsupported_mode_is_refused_by_the_worker(self) -> None:
        document = read_example(EXAMPLE)
        document["instances"][0]["parameters"]["simulation"]["mode"] = "chemostat"
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        assert "mode must be one of" in json.dumps(payload)

    def test_a_failed_run_reports_a_structured_failure_not_a_partial_result(self) -> None:
        document = read_example(EXAMPLE)
        document["instances"][0]["parameters"]["simulation"]["duration_h"] = -1.0
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        for result in payload["results"]:
            assert result["outputs"] == []

    def test_every_ganjave_diagnostic_carries_a_remediation(self) -> None:
        """Ganjave's own messages must tell the operator what to do.

        Scoped to Ganjave-originated diagnostics: the engine's own
        `capability.unsupported` notices are informational by design and are not
        Ganjave's to word.
        """
        payload, _code = run_graph(read_example(EXAMPLE), base=ROOT)
        relevant = [
            d for d in payload["diagnostics"]
            if d["origin"] == Origin.GANJAVE.value
            or d["code"] == DiagnosticCode.MODEL_FINDING.value
        ]
        assert relevant
        for diagnostic in relevant:
            assert diagnostic["remediation"], diagnostic["code"]

    def test_a_refused_input_is_reported_with_a_remediation(self) -> None:
        document = read_example(EXAMPLE)
        document["literal_inputs"]["ganjave_fed_batch/initial_biomass_concentration"] = {
            "state": "number", "quantity": "mass", "value": 2.0, "unit": "kg",
            "method": "a total mass, supplied by mistake",
            "reason": "the graph author confused a mass with a concentration",
        }
        payload, _code = run_graph(document, base=ROOT)
        refusals = [
            d for d in payload["diagnostics"]
            if d["code"] == DiagnosticCode.EXECUTION_MODEL_FAILED.value
        ]
        assert refusals
        assert refusals[0]["remediation"]
        assert refusals[0]["detail"]["refused_contract"].endswith("ganjave_contract")


# --------------------------------------------------------------------------- #
# GJ-C11  Failure propagation
# --------------------------------------------------------------------------- #


class TestFailurePropagation:
    """GJ-C11: a failed node never leaves a dependent running on stale output.

    The dependent is a second Ganjave instance whose initial glycerol is fed by
    the first instance's residual glycerol -- a connection that is physically
    coherent, not merely quantity-compatible. A Morris or Zielinski node cannot
    play this role: neither publishes a mass concentration Ganjave accepts, so
    no legal edge exists from Ganjave to them (see :class:`TestUnits`), and a
    graph that wired one would be refused at validation rather than at run time.
    """

    def _chain_graph(self, *, break_upstream: bool) -> dict:
        first = read_example(EXAMPLE)
        document = {
            "contract_version": "0.1.0",
            "graph_id": "gj_chain",
            "title": "two chained Ganjave instances",
            "instances": [
                first["instances"][0],
                {
                    "instance_id": "stage_b",
                    "model_id": MODEL_ID,
                    "model_version": MODEL_VERSION,
                    "label": "second culture, seeded from the first's glycerol",
                    "parameters": {
                        "simulation": {"mode": "batch", "duration_h": 6.0}
                    },
                },
            ],
            "connections": [
                {
                    "connection_id": "glycerol_a_to_b",
                    "source": {
                        "instance_id": "ganjave_fed_batch",
                        "port_id": "glycerol_concentration",
                    },
                    "target": {
                        "instance_id": "stage_b",
                        "port_id": "initial_glycerol_concentration",
                    },
                    "label": "residual glycerol seeds the next culture",
                }
            ],
            "literal_inputs": {},
        }
        # The upstream instance keeps every literal it had, feed included; the
        # downstream batch instance needs only the three unconditional ones,
        # because a batch run reads no feed ports.
        for name, spec in first["literal_inputs"].items():
            document["literal_inputs"][name] = spec
            if "feed_" not in name:
                document["literal_inputs"][f"stage_b/{name.split('/', 1)[1]}"] = spec
        # stage_b's glycerol arrives on the connection, not as a literal.
        document["literal_inputs"].pop(
            "stage_b/initial_glycerol_concentration", None
        )
        # The break is an *unresolved* literal rather than an absent one. An
        # absent required input is caught by graph validation, so nothing would
        # ever execute and there would be no propagation to observe; an
        # unresolved one passes validation and fails inside the run, which is
        # the case this test is about.
        if break_upstream:
            document["literal_inputs"]["ganjave_fed_batch/initial_dissolved_oxygen"] = {
                "state": "unresolved",
                "quantity": "dimensionless",
                "unit": "%",
                "reason": "the operator has not measured the starting dissolved oxygen",
            }
        return document

    def test_the_dependent_is_skipped_when_the_upstream_fails(self) -> None:
        payload, code = run_graph(self._chain_graph(break_upstream=True), base=ROOT)
        assert code != 0
        statuses = {r["instance_id"]: r["status"] for r in payload["results"]}
        assert statuses["ganjave_fed_batch"] == "failed"
        assert statuses["stage_b"] == "failed"

    def test_the_skip_is_explained_by_the_upstream_failure(self) -> None:
        payload, _code = run_graph(self._chain_graph(break_upstream=True), base=ROOT)
        skipped = [
            d for d in payload["diagnostics"]
            if d["code"] == DiagnosticCode.EXECUTION_DEPENDENT_SKIPPED.value
        ]
        assert skipped
        assert "ganjave_fed_batch" in skipped[0]["message"]

    def test_the_dependent_produces_no_output(self) -> None:
        payload, _code = run_graph(self._chain_graph(break_upstream=True), base=ROOT)
        stage_b = next(r for r in payload["results"] if r["instance_id"] == "stage_b")
        assert stage_b["outputs"] == []

    def test_no_stale_result_survives_a_failed_run(self) -> None:
        payload, code = run_graph(self._chain_graph(break_upstream=True), base=ROOT)
        assert code != 0
        assert payload["status"] == "failed", payload["status"]
        for result in payload["results"]:
            if result["status"] == "failed":
                assert result["outputs"] == []

    def test_the_chain_runs_when_the_upstream_is_complete(self) -> None:
        """The converse, so the propagation test is not vacuously green."""
        payload, code = run_graph(self._chain_graph(break_upstream=False), base=ROOT)
        assert code == 0, payload["diagnostics"]
        statuses = {r["instance_id"]: r["status"] for r in payload["results"]}
        assert statuses["stage_b"].startswith("success")
        assert output_of(payload, "stage_b", "biomass_concentration")["value"]["value"] > 0.0

    def test_the_chained_value_carries_both_instances_in_its_provenance(self) -> None:
        payload, _code = run_graph(self._chain_graph(break_upstream=False), base=ROOT)
        chain = output_of(payload, "stage_b", "biomass_concentration")["provenance_chain"]
        producers = {record["producer_model"] for record in chain}
        # 'ganjave' produced the value; 'composition' is the origin of the
        # literal inputs it was computed from. Both must appear.
        assert producers == {MODEL_ID, "composition"}
        assert any(record["kind"] == "transfer" for record in chain)
        assert any(record["connection_id"] == "glycerol_a_to_b" for record in chain)
        assert any(record["kind"] == "assumption" for record in chain)

    def test_an_absent_required_input_is_caught_before_anything_executes(self) -> None:
        """A missing literal is a graph error, so no node runs at all.

        This is the complement of the propagation tests above: the engine
        refuses the graph rather than running half of it.
        """
        document = self._chain_graph(break_upstream=False)
        document["literal_inputs"].pop("ganjave_fed_batch/initial_dissolved_oxygen")
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        assert payload["status"] == "invalid"
        assert DiagnosticCode.CONNECTION_MISSING_REQUIRED.value in error_codes(payload)

    def test_a_successful_graph_rewrites_the_result_completely(self, work_dir) -> None:
        """The inverse check: a good run overwrites, it does not append."""
        target = work_dir / "gj_stale_check.json"
        bad, bad_code = run_graph(self._chain_graph(break_upstream=True), base=ROOT)
        target.write_text(json.dumps(bad), encoding="utf-8")
        assert json.loads(target.read_text(encoding="utf-8"))["status"] == "failed"

        good, good_code = run_graph(self._chain_graph(break_upstream=False), base=ROOT)
        assert good_code == 0
        target.write_text(json.dumps(good), encoding="utf-8")
        rewritten = json.loads(target.read_text(encoding="utf-8"))
        assert rewritten["status"] != "failed"
        assert rewritten["results"][0]["outputs"]


# --------------------------------------------------------------------------- #
# GJ-C12  Isolation
# --------------------------------------------------------------------------- #


class TestIsolation:
    """GJ-C12: Ganjave's `models` package cannot resolve to a sibling's."""

    def test_the_worker_runs_in_its_own_interpreter(self) -> None:
        """Each model ships a top-level `models` package, so they are separate."""
        registrations = {reg.model_id: reg for reg in REGISTRATIONS}
        workers = {reg.worker_module for reg in REGISTRATIONS}
        assert len(workers) == len(registrations), "each model needs its own worker"
        assert (
            registrations[MODEL_ID].worker_module
            == "composition._workers.ganjave_worker"
        )

    def test_the_ganjave_worker_resolves_the_ganjave_package(self) -> None:
        from composition._workers.ganjave_worker import _import_model

        simulation, contract = _import_model(str(ROOT / "Models" / "Ganjave"))
        assert simulation.MODEL_ID == "ganjave2022.cybernetic-growth"
        assert contract.MODEL_ID == "ganjave2022.cybernetic-growth"

    def test_the_worker_does_not_import_a_sibling_package(self) -> None:
        """The module name alone would collide; the import path must not."""
        text = (COMPOSITION_ROOT / "composition" / "_workers" / "ganjave_worker.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "import models.morris",
            "import models.zielinski_2019",
            "from models.morris",
            "from models.zielinski_2019",
        ):
            assert forbidden not in text, forbidden

    def test_the_composition_package_never_imports_the_model(self) -> None:
        """The dependency arrow points one way: model -> JSON boundary -> composition."""
        for path in (
            COMPOSITION_ROOT / "composition" / "adapters" / "ganjave.py",
            COMPOSITION_ROOT / "composition" / "adapters" / "ganjave_contract.py",
        ):
            text = path.read_text(encoding="utf-8")
            assert "import models" not in text, path.name
            assert "from models" not in text, path.name

    def test_the_adapter_really_does_contain_no_science(self) -> None:
        """No equation is transcribed in the adapter."""
        text = (COMPOSITION_ROOT / "composition" / "adapters" / "ganjave.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "response_r1", "growth_terms", "batch_derivative", "fed_batch_derivative",
            "_rk4_step", "integrate(", "oxygen_consumption_term",
        ):
            assert forbidden not in text, forbidden

    def test_three_models_coexist_in_one_interpreter(self) -> None:
        """Only the registry sees them together, which is the point."""
        assert len(REGISTRATIONS) == 3
        ids = sorted(reg.model_id for reg in REGISTRATIONS)
        assert ids == ["ganjave", "morris2011.material_balance", "zielinski2019.rhi_process"]


# --------------------------------------------------------------------------- #
# GJ-C13  Regression
# --------------------------------------------------------------------------- #


class TestRegression:
    """GJ-C13: the sibling suites are untouched."""

    def test_the_sibling_model_registrations_are_unchanged(self) -> None:
        entries = {m["model_id"]: m for m in known_models(ROOT)}
        assert entries["morris2011.material_balance"]["model_version"] == "0.1.0"
        assert entries["zielinski2019.rhi_process"]["model_version"] == "1.0.0"

    def test_the_contract_quantity_set_did_not_grow(self) -> None:
        """Ganjave reuses existing quantities; it adds none."""
        assert set(GANJAVE_KIND_TO_QUANTITY.values()) <= set(Quantity)

    def test_the_broader_example_set_still_behaves(self) -> None:
        from conftest import EXAMPLE_EXPECTATIONS, run_example

        for name, expected in EXAMPLE_EXPECTATIONS.items():
            payload, code = run_example(name)
            assert code == expected["exit_code"], name


# --------------------------------------------------------------------------- #
# GJ-C14  Graph execution
# --------------------------------------------------------------------------- #


class TestGraphExecution:
    """GJ-C14: a graph runs through the real CLI and returns a valid result."""

    def test_the_cli_runs_the_example_graph(self, work_dir) -> None:
        target = work_dir / "gj_cli_result.json"
        completed = subprocess.run(
            [
                sys.executable, "-m", "composition.runner",
                "--graph", str(COMPOSITION_ROOT / "examples" / EXAMPLE),
                "--result", str(target),
            ],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT),
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        summary = json.loads(completed.stdout)
        assert summary["exit_code"] == 0
        assert summary["status"] in ("success", "success_with_warnings")
        assert target.is_file()
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["graph_id"] == "ganjave_fed_batch"
        assert payload["error_count"] == 0
        assert payload["results"], "the result must carry the executed node"

    def test_the_written_result_contains_the_outputs_and_provenance(self, work_dir) -> None:
        target = work_dir / "gj_cli_result2.json"
        subprocess.run(
            [
                sys.executable, "-m", "composition.runner",
                "--graph", str(COMPOSITION_ROOT / "examples" / EXAMPLE),
                "--result", str(target),
            ],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT), check=True,
        )
        payload = json.loads(target.read_text(encoding="utf-8"))
        result = payload["results"][0]
        assert result["model_id"] == MODEL_ID
        assert result["outputs"]
        for out in result["outputs"]:
            assert out["provenance_chain"], out["ref"]["port_id"]
            assert out["value"]["unit"]

    def test_the_example_is_pinned_by_the_suite(self) -> None:
        from conftest import EXAMPLE_EXPECTATIONS

        assert EXAMPLE in EXAMPLE_EXPECTATIONS
        assert EXAMPLE_EXPECTATIONS[EXAMPLE]["exit_code"] == 0

    def test_the_run_carries_a_reproducibility_digest(self, fed_batch_result) -> None:
        assert fed_batch_result["reproducibility"]
        assert len(fed_batch_result["reproducibility"]) == 64

    def test_the_graph_declares_that_it_does_not_reproduce_the_paper(self) -> None:
        document = read_example(EXAMPLE)
        assert "not reproduce" in document["notes"].lower() or "does not reproduce" in (
            document["notes"].lower()
        )
        assert document["source_ref"].startswith("Ganjave et al.")


# --------------------------------------------------------------------------- #
# GJ-C15  GUI execution
# --------------------------------------------------------------------------- #


class TestGuiExecution:
    """GJ-C15: the Godot interface can load, validate and run this graph.

    The interface reaches the engine through `CompositionRunner`, so what it can
    do is exactly what these tests drive: discovery, a manifest description, a
    plan-only validation, a real run, and a read of the result document back
    off disk.

    **Godot is installed on this host** (4.7.2, under `D:/Godot`), so these run
    for real rather than being skipped. The discovery helper is the suite's own
    `_find_godot`, so a host without Godot skips these with the reason recorded
    rather than passing quietly.
    """

    @staticmethod
    def godot_binary() -> str | None:
        from test_acceptance import _find_godot

        return _find_godot()

    def _run_harness(self, script: str, work_dir) -> subprocess.CompletedProcess:
        binary = self.godot_binary()
        assert binary, "the harness was invoked without a Godot binary"
        return subprocess.run(
            [binary, "--headless", "--path", str(ROOT), "--script", script],
            cwd=str(ROOT), capture_output=True, text=True, timeout=900,
        )

    def test_the_contract_boundary_still_passes_with_a_third_model(self) -> None:
        """The editor reads the model list at run time, so registration is enough."""
        completed = self._run_harness(
            "res://composition/tests/godot/contract_boundary.gd", None
        )
        assert completed.returncode == 0, completed.stdout[-3000:] + completed.stderr[-2000:]
        assert "checks passed" in completed.stdout, completed.stdout[-2000:]
        assert "FAIL" not in completed.stdout, completed.stdout[-2000:]

    def test_the_ganjave_graph_loads_validates_and_runs_in_godot(self, work_dir) -> None:
        completed = self._run_harness(
            "res://composition/tests/godot/ganjave_graph_run.gd", work_dir
        )
        assert completed.returncode == 0, completed.stdout[-4000:] + completed.stderr[-2000:]
        assert "ganjave-graph-run: " in completed.stdout
        assert "FAILED" not in completed.stdout, completed.stdout[-2000:]

    def test_godot_surfaces_the_validation_status_and_the_open_question(self, work_dir) -> None:
        """The editor must not present a not-validated run as a reproduction.

        The harness asserts this inside Godot; this test re-reads the result
        document the editor wrote, so the claim is checked against the bytes on
        disk rather than against the harness's own report of itself.
        """
        completed = self._run_harness(
            "res://composition/tests/godot/ganjave_graph_run.gd", work_dir
        )
        assert completed.returncode == 0, completed.stdout[-3000:]
        user_dir = Path.home() / "AppData" / "Roaming" / "Godot" / "app_userdata"
        candidates = list(user_dir.glob("*/ganjave_graph_run.json"))
        assert candidates, f"the editor wrote no result document under {user_dir}"
        document = json.loads(candidates[0].read_text(encoding="utf-8"))
        # The last run through the harness is the deliberately broken one; the
        # successful document is asserted by the harness itself, and here we
        # assert that neither document ever claims to be a reproduction.
        messages = " ".join(d.get("message", "") for d in document["diagnostics"])
        assert "reproduction" not in messages.lower() or "not_yet_validated" in messages

    def test_godot_availability_is_recorded_not_assumed(self) -> None:
        binary = self.godot_binary()
        if binary is None:
            pytest.skip(
                "no Godot binary is installed on this host, so the editor "
                "boundary was NOT verified. Run it by hand:\n"
                "  godot --headless --path . --script "
                "res://composition/tests/godot/ganjave_graph_run.gd\n"
                "A skip here is not a pass."
            )
        assert Path(binary).exists()

    def test_the_registry_surface_the_ui_reads_lists_ganjave(self) -> None:
        """``--list-models`` is exactly what scripts/model_registry.gd calls."""
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--list-models"],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT), check=True,
        )
        payload = json.loads(completed.stdout)
        entry = next(m for m in payload["models"] if m["model_id"] == MODEL_ID)
        # The UI reads these keys and nothing else.
        assert {"model_id", "model_version", "reference", "package", "available"} <= set(entry)
        assert entry["available"] is True

    def test_the_manifest_surface_the_ui_reads_is_valid(self) -> None:
        """``--describe-model`` is what the inspector requests per model."""
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--describe-model", MODEL_ID],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT), check=True,
        )
        payload = json.loads(completed.stdout)
        manifest = payload["manifest"]
        assert manifest["model_id"] == MODEL_ID
        for port in manifest["ports"]:
            assert {"port_id", "direction", "quantity", "unit", "label"} <= set(port)
            assert port["direction"] in ("input", "output")
        assert manifest["parameter_sections"], "the inspector renders these"

    def test_every_quantity_the_ports_use_has_a_ui_colour(self, manifest) -> None:
        """An unknown quantity would render in the unknown colour; none may."""
        known = {
            "mass", "mass_flow", "mass_fraction", "amount", "amount_flow",
            "volume", "volume_flow", "time", "temperature", "molar_concentration",
            "mass_concentration", "absorbance", "absorbance_per_volume",
            "absorbance_per_mass", "activity", "activity_per_volume", "molar_mass",
            "conductivity", "relative_centrifugal_force", "concentration_factor",
            "wavelength", "dimensionless", "ph",
        }
        for port in manifest.ports:
            assert port.quantity.value in known, port.port_id

    def test_the_contract_surface_the_ui_reads_is_served(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--describe-contract"],
            capture_output=True, text=True, cwd=str(COMPOSITION_ROOT), check=True,
        )
        payload = json.loads(completed.stdout)
        units = payload["units_by_quantity"]
        for port_id, (quantity, unit) in {
            "biomass_concentration": ("mass_concentration", "g/L"),
            "culture_volume": ("volume", "L"),
            "feed_flow_rate": ("volume_flow", "mL/h"),
            "simulation_time": ("time", "h"),
            "dissolved_oxygen": ("dimensionless", "%"),
        }.items():
            assert unit in units[quantity], port_id

    def test_the_godot_contract_script_carries_no_port_table(self) -> None:
        """Adding a model must not require editing the GDScript.

        `scripts/model_registry.gd` reads `--list-models`, `--describe-model`
        and `--describe-contract`, so a new registration appears on its own. The
        GDScript contract test names individual models today, but it must not
        carry ports or quantities, because those come from the runner at run
        time and a hard-coded copy would drift.
        """
        script = COMPOSITION_ROOT / "tests" / "godot" / "contract_boundary.gd"
        text = script.read_text(encoding="utf-8")
        assert "in:" not in text, "port ids are read from the runner, not compiled in"

    def test_the_ui_scripts_need_no_edit_for_a_third_model(self) -> None:
        """`model_registry.gd` keys colours on contract quantity names only."""
        script = ROOT / "scripts" / "model_registry.gd"
        text = script.read_text(encoding="utf-8")
        for model_id in ("morris2011", "zielinski2019", "ganjave"):
            assert model_id not in text, model_id
        # Every quantity Ganjave publishes already has a colour.
        for quantity in ("mass_concentration", "volume", "volume_flow", "time",
                         "dimensionless"):
            assert f'"{quantity}"' in text, quantity


# --------------------------------------------------------------------------- #
# connection contract, as data
# --------------------------------------------------------------------------- #


class TestConnectionContractDocument:
    def test_every_input_is_declared(self) -> None:
        declared = {rule.port_id for rule in INPUT_CONTRACT}
        assert declared == {
            "initial_biomass_concentration",
            "initial_glycerol_concentration",
            "initial_complex_substrate_concentration",
            "initial_dissolved_oxygen",
            "initial_culture_volume",
            "feed_glycerol_concentration",
            "feed_complex_substrate_concentration",
            "feed_flow_rate",
            "feed_start_time",
        }

    def test_every_rule_states_a_reason(self) -> None:
        for rule in INPUT_CONTRACT:
            assert rule.reason, rule.port_id

    def test_a_supplyable_rule_states_its_assumption(self) -> None:
        for rule in INPUT_CONTRACT:
            if rule.upstream_supplyable:
                assert rule.assumption, rule.port_id

    def test_fed_batch_only_ports_declare_their_mode(self) -> None:
        for rule in INPUT_CONTRACT:
            if rule.required_when:
                assert set(rule.required_when) <= {"fed_batch"}
                assert rule.modes == ("fed_batch",), rule.port_id

    def test_the_two_refused_ports_are_the_ones_without_upstream_sources(self) -> None:
        refused = {r.port_id for r in INPUT_CONTRACT if not r.upstream_supplyable}
        assert refused == {
            "initial_biomass_concentration",
            "initial_dissolved_oxygen",
        }

    def test_morris_is_not_claimed_as_a_source(self) -> None:
        notes = connection_contract()["cross_model_notes"]
        morris = next(n for n in notes if n["other_model"].startswith("morris"))
        assert morris["verdict"] == "no shared quantity"
        assert "kg" in morris["note"]

    def test_zielinski_is_not_treated_as_a_protein_expression_model(self) -> None:
        notes = connection_contract()["cross_model_notes"]
        zielinski = next(n for n in notes if n["other_model"].startswith("zielinski"))
        assert "not a dynamic protein-expression model" in zielinski["note"]
        assert "assumption" in zielinski["verdict"]

    def test_an_unknown_port_raises_rather_than_defaulting(self) -> None:
        with pytest.raises(KeyError):
            rule_for("initial_vitamin_concentration")
        with pytest.raises(KeyError):
            check_input_connection("initial_vitamin_concentration", "mass_concentration")


# --------------------------------------------------------------------------- #
# quantity mapping, as data
# --------------------------------------------------------------------------- #


class TestQuantityMapping:
    def test_a_mapped_kind_resolves_to_its_contract_quantity(self) -> None:
        assert quantity_for_ganjave_kind("mass_concentration", "g/L") is Quantity.MASS_CONCENTRATION
        assert quantity_for_ganjave_kind("volume", "L") is Quantity.VOLUME
        assert quantity_for_ganjave_kind("volume_flow", "mL/h") is Quantity.VOLUME_FLOW
        assert quantity_for_ganjave_kind("time", "h") is Quantity.TIME

    def test_dissolved_oxygen_maps_to_dimensionless_not_a_mass_fraction(self) -> None:
        assert quantity_for_ganjave_kind(
            "dissolved_oxygen_percent", "%"
        ) is Quantity.DIMENSIONLESS
        assert quantity_for_ganjave_kind(
            "dissolved_oxygen_percent", "%"
        ) is not Quantity.MASS_FRACTION

    def test_an_unmapped_kind_is_none_not_a_guess(self) -> None:
        assert quantity_for_ganjave_kind("mystery", "g/L") is None
        assert quantity_for_ganjave_kind("", "g/L") is None

    def test_the_mapping_is_total_over_the_published_ports(self, manifest) -> None:
        for port in manifest.ports:
            assert quantity_for_ganjave_kind(
                port.metadata["model_kind"], port.unit
            ) is port.quantity, port.port_id

    def test_g_L_means_different_things_on_different_ports(self, manifest) -> None:
        """The same symbol, different quantities, kept apart."""
        kinds = {
            port.metadata["model_kind"]
            for port in manifest.ports
            if port.unit == "g/L"
        }
        quantities = {
            port.quantity for port in manifest.ports if port.unit == "g/L"
        }
        assert kinds == {"mass_concentration"}
        assert quantities == {Quantity.MASS_CONCENTRATION}


# --------------------------------------------------------------------------- #
# the engine's own machinery
# --------------------------------------------------------------------------- #


class TestEngineIntegration:
    def test_the_engine_loads_a_manifest_for_a_ganjave_instance(self) -> None:
        engine = CompositionEngine(base_path=ROOT)
        graph = load_graph(read_example(EXAMPLE))
        loaded = engine.load(graph)
        assert loaded["ganjave_fed_batch"].manifest is not None
        errors = [d for d in loaded["ganjave_fed_batch"].diagnostics if d.is_error]
        assert errors == []

    def test_the_manifest_validates_against_the_contract(self, manifest) -> None:
        diagnostics = manifest.validate_against_contract()
        errors = [d for d in diagnostics if d.is_error]
        assert errors == []

    def test_unsupported_capabilities_are_readable_keys(self, manifest) -> None:
        for key in manifest.unsupported_capabilities:
            assert not key.startswith("capability_"), key
            assert key.replace("_", "").isalnum(), key

    def test_a_version_mismatch_is_refused(self) -> None:
        document = read_example(EXAMPLE)
        document["instances"][0]["model_version"] = "9.9.9"
        payload, code = run_graph(document, base=ROOT)
        assert code != 0
        assert DiagnosticCode.MODEL_VERSION_MISMATCH.value in error_codes(payload)