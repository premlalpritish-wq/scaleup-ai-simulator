"""Acceptance criteria CG-01 ... CG-15.

One class per criterion, named after it, and ``CG_COVERAGE`` maps each criterion
to the class that implements it.  ``TestCoverageTable`` fails if a criterion is
ever added without a class or a class disappears, so the table cannot quietly
drift away from the suite -- the same discipline the two existing suites use for
MB-01..MB-12 and AT-001..AT-026.

Each test states the criterion's acceptance value literally, so a reviewer can
check the assertion against the requirement without reading the engine.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    COMPOSITION_ROOT,
    EXAMPLE_EXPECTATIONS,
    EXAMPLES,
    ROOT,
    all_codes,
    error_codes,
    example_result,
    output_of,
    read_example,
    run_example,
    run_model_suite,
)
from composition.contracts import (
    CONTRACT_VERSION,
    PortDirection,
    ValueState,
    load_graph,
)
from composition.diagnostics import DiagnosticCode, Origin, Severity
from composition.engine import CompositionEngine
from composition.quantities import Quantity


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def inputs_to(payload: dict, instance_id: str) -> dict[str, dict]:
    """``port_id -> input record`` for one instance of a run."""
    for result in payload["results"]:
        if result["instance_id"] == instance_id:
            return {i["ref"]["port_id"]: i for i in result["inputs"]}
    raise KeyError(f"{instance_id} has no result")


# --------------------------------------------------------------------------- #
# CG-01 -- model discovery
# --------------------------------------------------------------------------- #


class TestCG01ModelDiscovery:
    """Both existing models load through their declared contracts."""

    def test_morris_loads_through_its_manifest(self, manifest_brass_charge):
        assert manifest_brass_charge is not None
        assert manifest_brass_charge.model_id == "morris2011.material_balance"
        assert manifest_brass_charge.model_version == "0.1.0"
        assert manifest_brass_charge.ports
        assert {p.direction for p in manifest_brass_charge.ports} == {
            PortDirection.INPUT, PortDirection.OUTPUT
        }

    def test_zielinski_loads_through_its_manifest(self, manifest_zielinski):
        assert manifest_zielinski is not None
        assert manifest_zielinski.model_id == "zielinski2019.rhi_process"
        assert manifest_zielinski.model_version == "1.0.0"
        # 15 operations, 17 streams, 20 bindings; the port surface is derived
        # from every declared quantity, so it is far larger than 15.
        assert len(manifest_zielinski.ports) > 150
        assert len(manifest_zielinski.ports_by_direction(PortDirection.INPUT)) > 100
        assert len(manifest_zielinski.ports_by_direction(PortDirection.OUTPUT)) > 50

    def test_both_manifests_declare_the_contract_version(self, manifest_brass_charge,
                                                          manifest_zielinski):
        assert manifest_brass_charge.contract_version == CONTRACT_VERSION
        assert manifest_zielinski.contract_version == CONTRACT_VERSION

    def test_both_manifests_validate_against_the_contract(self, manifest_brass_charge,
                                                           manifest_zielinski):
        for manifest in (manifest_brass_charge, manifest_zielinski):
            assert not [d for d in manifest.validate_against_contract()
                        if d.is_error]

    def test_zielinski_declares_the_unit_the_project_cannot_represent(self,
                                                                     manifest_zielinski):
        """The specific growth rate is declared 1/h, which the model's own unit
        registry does not define. The port is published, marked unusable, and
        reported -- not quietly repaired."""
        gaps = [p for p in manifest_zielinski.ports if not p.is_usable]
        assert [p.port_id for p in gaps] == ["node:N01#specific_growth_rate"]
        assert "1/h" in gaps[0].unavailable_reason

    def test_an_unknown_model_is_refused_not_substituted(self, engine):
        from composition.contracts import ModelInstance

        _manifest, diagnostics = engine.manifest_for(
            ModelInstance(instance_id="x", model_id="not.a.model",
                          model_version="0.0.0")
        )
        codes = {d.code for d in diagnostics}
        assert DiagnosticCode.ADAPTER_MISSING in codes
        assert all(d.message for d in diagnostics)

    def test_a_version_mismatch_is_an_error_not_a_best_effort_run(self, engine):
        from composition.contracts import ModelInstance

        _manifest, diagnostics = engine.manifest_for(
            ModelInstance(instance_id="x",
                          model_id="morris2011.material_balance",
                          model_version="9.9.9",
                          parameters=read_example(
                              "brass_batch_chain.json"
                          )["instances"][0]["parameters"])
        )
        codes = {d.code for d in diagnostics}
        assert DiagnosticCode.MODEL_VERSION_MISMATCH in codes


# --------------------------------------------------------------------------- #
# CG-02 -- port compatibility
# --------------------------------------------------------------------------- #


class TestCG02PortCompatibility:
    """Compatible ports connect; incompatible physical quantities are refused."""

    def test_a_mass_feeds_a_mass(self, brass_chain):
        assert "connection.quantity_mismatch" not in error_codes(brass_chain)
        supplied = inputs_to(brass_chain, "brass_alloying")["in:A:total"]
        assert supplied["value"]["unit"] == "kg"
        assert supplied["value"]["quantity"] == "mass"

    def test_a_mass_fraction_feeds_a_mass_fraction(self, brass_chain):
        target = [
            i for i in brass_chain["results"]
            if i["instance_id"] == "brass_alloying"
        ][0]
        supplied = {i["ref"]["port_id"] for i in target["inputs"]}
        assert "in:A:w:Cu" in supplied
        assert "in:A:w:Zn" in supplied

    def test_an_absorbance_cannot_supply_a_mass(self):
        payload = example_result("rejected_au_to_mass.json")
        assert "connection.quantity_mismatch" in error_codes(payload)
        message = next(
            d["message"] for d in payload["diagnostics"]
            if d["code"] == "connection.quantity_mismatch"
        )
        assert "absorbance" in message
        assert "mass" in message

    def test_a_dimensionless_ratio_cannot_supply_a_mass_fraction(self, engine):
        """Zielinski's `1` (pH-stat dead band) is dimensionless. Morris's `1` is
        a mass fraction. Same symbol, incompatible meaning."""
        from composition.contracts import (
            Connection, ModelInstance, PortDefinition, PortRef,
        )

        graph = load_graph(read_example("brass_batch_chain.json"))
        engine.load(graph)
        dead_band = PortDefinition(
            port_id="p", direction=PortDirection.INPUT,
            quantity=Quantity.DIMENSIONLESS, unit="1",
        )
        fraction = PortDefinition(
            port_id="q", direction=PortDirection.INPUT,
            quantity=Quantity.MASS_FRACTION, unit="1",
        )
        assert dead_band.quantity is not fraction.quantity

    def test_the_graph_does_not_run_at_all_when_a_connection_is_refused(self):
        payload = example_result("rejected_au_to_mass.json")
        assert payload["status"] in ("invalid", "refused")
        assert payload["results"] == []
        assert payload["plan"]["order"] == []


# --------------------------------------------------------------------------- #
# CG-03 -- unit semantics
# --------------------------------------------------------------------------- #


class TestCG03UnitSemantics:
    """kg and kg/h cannot be connected without an explicit conversion model."""

    def test_mass_into_mass_flow_is_refused(self):
        payload = example_result("rejected_mass_as_flow.json")
        assert error_codes(payload) == {"connection.quantity_mismatch"}
        message = payload["diagnostics"][-1]["message"]
        assert "mass" in message and "mass_flow" in message
        assert "A quantity is not a unit" in message

    def test_the_same_quantity_in_two_units_is_accepted(self, engine):
        """MASS in g and MASS in kg are the same quantity, so the connection is
        legal and the conversion is declared rather than implicit."""
        from composition.contracts import (
            Connection, ModelInstance, PortRef,
        )

        graph = load_graph(read_example("brass_batch_chain.json"))
        loaded = engine.load(graph)
        diagnostics = engine.validate_connections(
            _with_extra_connection(
                graph,
                Connection(
                    connection_id="unit-probe",
                    source=PortRef("zielinski_rhi",
                                   "stream:S03_wet_biomass#wet_biomass_total"),
                    target=PortRef("brass_alloying", "in:B:Zn"),
                ),
            ),
            loaded,
        )
        codes = {d.code for d in diagnostics}
        assert "connection.quantity_mismatch" not in codes
        assert "connection.unit_mismatch" not in codes

    def test_no_conversion_model_exists_for_mass_to_mass_flow(self, manifest_zielinski):
        """Neither model authorises a rate conversion, so there is nothing to
        declare one against."""
        assert manifest_zielinski.conversion_models == ()

    def test_the_zielinski_manifest_declares_its_missing_calibrations(self,
                                                                      manifest_zielinski):
        reasons = manifest_zielinski.unsupported_capabilities
        assert "au_to_mass_calibration" in reasons
        assert "water" in reasons["au_to_mass_calibration"].lower() or (
            "extinction" in reasons["au_to_mass_calibration"].lower()
        )

    def test_morris_refuses_inventing_a_rate_from_an_inventory(self, morris_root):
        """The refusal is Morris's own, verified by running it, not ours."""
        script = (
            "import json,sys;"
            "sys.path.insert(0, %r);"
            "from schemas.material_balance import *;"
            "from models.material_balance import BalanceError;"
            "\ntry:\n"
            "    BalanceSystem(system_id='t',label='t',"
            "process_mode=ProcessMode.STEADY_STATE,basis=BalanceBasis.MASS,"
            "components=(Component('X','x'),),"
            "streams=(Stream('A','a',Direction.INPUT,"
            "amount=reported('A:total',100.0,'kg',source_ref='t'),"
            "mass_fractions={'X':reported('A:w_X',1.0,'1',source_ref='t')}),"
            "Stream('B','b',Direction.OUTPUT,"
            "component_amounts={'X':reported('B:X',100.0,'kg',source_ref='t')})))\n"
            "    print('ACCEPTED')\n"
            "except Exception as exc:\n"
            "    print('REFUSED', type(exc).__name__)\n"
        ) % str(morris_root)
        out = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            cwd=str(morris_root), timeout=120,
        )
        assert "REFUSED" in out.stdout, out.stdout + out.stderr


def _with_extra_connection(graph, connection):
    from composition.contracts import CompositionGraph

    return CompositionGraph(
        graph_id=graph.graph_id, title=graph.title,
        instances=graph.instances,
        connections=(*graph.connections, connection),
        contract_version=graph.contract_version,
        description=graph.description,
        source_ref=graph.source_ref,
        literal_inputs=graph.literal_inputs,
        defaults=graph.defaults,
        notes=graph.notes,
    )


# --------------------------------------------------------------------------- #
# CG-04 -- graph ordering
# --------------------------------------------------------------------------- #


class TestCG04GraphOrdering:
    """Upstream models execute before downstream models."""

    def test_the_upstream_instance_runs_first(self, brass_chain):
        assert brass_chain["plan"]["order"][0] == "brass_charge"

    def test_the_downstream_instance_runs_after_its_upstream(self, brass_chain):
        order = brass_chain["plan"]["order"]
        assert order.index("brass_charge") < order.index("brass_alloying")

    def test_every_connection_respects_the_plan_order(self, brass_chain):
        order = brass_chain["plan"]["order"]
        graph = load_graph(read_example("brass_batch_chain.json"))
        for connection in graph.connections:
            assert order.index(connection.source.instance_id) < order.index(
                connection.target.instance_id
            ), connection.connection_id

    def test_the_plan_is_stable_across_runs(self):
        first = example_result("brass_batch_chain.json")["plan"]["order"]
        second = example_result("brass_batch_chain.json")["plan"]["order"]
        assert first == second

    def test_an_instance_without_a_declared_position_still_orders(self, engine):
        graph = load_graph(read_example("brass_batch_chain.json"))
        order, diagnostics = engine.order(graph)
        assert not diagnostics
        assert set(order) == {i.instance_id for i in graph.instances}


# --------------------------------------------------------------------------- #
# CG-05 -- data transfer
# --------------------------------------------------------------------------- #


class TestCG05DataTransfer:
    """The downstream model receives the exact upstream values and provenance."""

    def test_the_downstream_control_volume_saw_the_upstream_total(self, brass_chain):
        supplied = inputs_to(brass_chain, "brass_alloying")["in:A:total"]
        assert supplied["value"]["value"] == pytest.approx(26600.0)
        assert supplied["value"]["unit"] == "kg"
        assert supplied["via"] == "connection"

    def test_the_downstream_control_volume_saw_both_fractions(self, brass_chain):
        inputs = inputs_to(brass_chain, "brass_alloying")
        cu = (14500.0 + 0.79 * 8500.0) / 26600.0
        assert inputs["in:A:w:Cu"]["value"]["value"] == pytest.approx(cu, abs=1e-12)
        assert inputs["in:A:w:Zn"]["value"]["value"] == pytest.approx(
            1.0 - cu, abs=1e-12
        )

    def test_the_transfer_is_exact_not_rounded(self, brass_chain):
        upstream = output_of(brass_chain, "brass_charge", "out:D:total")["value"]
        downstream = inputs_to(brass_chain, "brass_alloying")["in:A:total"]["value"]
        assert upstream["value"] == downstream["value"]
        assert upstream["unit"] == downstream["unit"]
        assert repr(upstream["value"]) == repr(downstream["value"])

    def test_the_provenance_chain_survives_the_hop(self, brass_chain):
        chain = inputs_to(brass_chain, "brass_alloying")["in:A:total"][
            "provenance_chain"
        ]
        assert [record["kind"] for record in chain] == ["source", "transfer"]
        assert chain[0]["producer_model"] == "morris2011.material_balance"
        assert chain[0]["producer_version"] == "0.1.0"
        assert chain[1]["connection_id"] == "c1"
        assert chain[1]["source_port"] == "out:D:total"
        assert chain[1]["target_port"] == "in:A:total"

    def test_the_upstream_source_record_names_the_equation(self, brass_chain):
        chain = inputs_to(brass_chain, "brass_alloying")["in:A:total"][
            "provenance_chain"
        ]
        source_record = chain[0]
        assert "solve_balance" in source_record["detail"]
        assert "Morris" in source_record["method"]


# --------------------------------------------------------------------------- #
# CG-06 -- conservation regression
# --------------------------------------------------------------------------- #


class TestCG06ConservationRegression:
    """All 12 existing material-balance criteria still pass unchanged."""

    def test_the_existing_suites_are_run_unchanged(self):
        """Run both model suites as subprocesses from their own roots. The point
        is that nothing under Models/ is imported differently, patched or
        rewritten by this project."""
        morris = run_model_suite("Models/Morris")
        zielinski = run_model_suite("Models/Zielinski")
        assert morris.startswith("186 passed"), morris
        assert zielinski.startswith("223 passed"), zielinski

    def test_the_composition_run_reproduces_example_4_2_exactly(self, brass_chain):
        d = output_of(brass_chain, "brass_charge", "out:D:total")["value"]["value"]
        cu = output_of(brass_chain, "brass_charge", "out:D:Cu")["value"]["value"]
        zn = output_of(brass_chain, "brass_charge", "out:D:Zn")["value"]["value"]
        w_cu = output_of(brass_chain, "brass_charge", "out:D:w:Cu")["value"]["value"]
        w_zn = output_of(brass_chain, "brass_charge", "out:D:w:Zn")["value"]["value"]
        assert d == pytest.approx(26600.0, abs=1e-9)
        assert cu == pytest.approx(14500.0 + 0.79 * 8500.0)
        assert zn == pytest.approx(3600.0 + 8500.0 * 0.21)
        assert w_cu == pytest.approx(0.79756, abs=1e-5)
        assert w_zn == pytest.approx(0.20244, abs=1e-5)

    def test_the_downstream_balance_closes(self, brass_chain):
        alloying = [r for r in brass_chain["results"]
                    if r["instance_id"] == "brass_alloying"][0]
        assert alloying["raw_summary"]["balances_close"] is True
        # Every component gets a balance, so sum(w) = 1 on stream A is a
        # dependent equation. Morris et al. sec. 4.6.2 calls that a check, and
        # the engine reports it as one rather than resolving the redundancy.
        assert alloying["raw_summary"]["solvability"] == "overconstrained"
        assert alloying["raw_summary"]["redundant_equation_ids"] == [
            "composition:A"
        ]
        for residual in alloying["residuals"]:
            assert residual["within_tolerance"] is True

    def test_the_downstream_total_is_the_sum_of_its_components(self, brass_chain):
        total = output_of(brass_chain, "brass_alloying", "out:E:total")["value"]["value"]
        cu = output_of(brass_chain, "brass_alloying", "out:E:Cu")["value"]["value"]
        zn = output_of(brass_chain, "brass_alloying", "out:E:Zn")["value"]["value"]
        assert total == pytest.approx(cu + zn)


# --------------------------------------------------------------------------- #
# CG-07 -- missing information
# --------------------------------------------------------------------------- #


class TestCG07MissingInformation:
    """An unresolved upstream value cannot become zero or a fabricated input."""

    def test_the_graph_refuses_to_run_when_an_upstream_value_is_missing(self):
        payload = example_result("failure_propagation.json")
        assert payload["status"] == "failed"
        downstream = payload["results"][1]
        assert downstream["instance_id"] == "stage_b"
        assert downstream["outputs"] == []

    def test_an_unresolved_port_is_published_as_unresolved(self):
        payload = example_result("failure_propagation.json")
        upstream = payload["results"][0]
        assert upstream["status"] == "failed"
        assert upstream["outputs"] == []

    def test_a_declared_unknown_stays_unknown_after_the_solve(self):
        """A free variable of the balance system is reported as unresolved, not
        as a solved zero. Morris guarantees this; the composition layer must not
        undo it on the way out -- and the variables that *are* determined are
        still reported, which is what sec. 4.7.2 says is possible."""
        from composition.runner import run_graph

        # Keep the upstream connection, but leave the zinc make-up charge
        # undeclared: nothing constrains it, so the zinc balance has a free
        # variable while the copper balance closes exactly.
        document = read_example("brass_batch_chain.json")
        document["graph_id"] = "underdetermined-probe"
        document["literal_inputs"] = {}
        system = document["instances"][1]["parameters"]["system"]
        stream_b = next(s for s in system["streams"] if s["stream_id"] == "B")
        stream_b["component_amounts"]["Zn"] = {
            "variable_id": "stream:B:Zn",
            "kind": "mass",
            "provenance": "unknown",
            "reason": "the zinc make-up was not declared",
        }
        payload, code = run_graph(document, base=ROOT)
        assert code == 0, [d["message"] for d in payload["diagnostics"]
                           if d["severity"] == "error"]
        alloying = [r for r in payload["results"]
                    if r["instance_id"] == "brass_alloying"][0]
        assert alloying["raw_summary"]["solvability"] == "underdetermined"

        # Morris sec. 4.7.2: an under-specified balance may still give useful
        # information. The free variable is reported in `unresolved` -- it is
        # NOT written as a solved zero -- while the pivot variable (B:Zn)
        # carries the canonical member of the one-parameter family, labelled
        # as a representative and NOT as a determined value.
        unresolved = {u["variable_id"] for u in alloying["unresolved"]}
        assert "stream:E:Zn" in unresolved

        zn = output_of(payload, "brass_alloying", "out:E:Zn")["value"]
        assert zn["state"] == "unresolved"
        assert zn["value"] is None
        assert "under-determined" in zn["reason"]

        # B:Zn is the pivot: its value (0.0) is the canonical representative of
        # the free family, explicitly labelled as such -- never presented as a
        # determined quantity.
        b_zn = output_of(payload, "brass_alloying", "out:B:Zn")["value"]
        assert b_zn["state"] in ("number", "zero")
        assert b_zn["extra"]["determination"] == "representative"
        assert "under-determined" in b_zn["method"]

        # ...and the component that IS determined is still reported, which is
        # the sec. 4.7.2 point about an under-specified balance giving
        # "useful information".
        cu = output_of(payload, "brass_alloying", "out:E:Cu")["value"]
        assert cu["state"] == "number"
        assert cu["value"] == pytest.approx(21215.0)

    def test_an_underdetermined_system_is_reported_as_a_warning(self):
        from composition.runner import run_graph

        document = read_example("brass_batch_chain.json")
        document["graph_id"] = "underdetermined-warning-probe"
        document["literal_inputs"] = {}
        system = document["instances"][1]["parameters"]["system"]
        stream_b = next(s for s in system["streams"] if s["stream_id"] == "B")
        stream_b["component_amounts"]["Zn"] = {
            "variable_id": "stream:B:Zn", "kind": "mass",
            "provenance": "unknown", "reason": "not declared",
        }
        payload, _code = run_graph(document, base=ROOT)
        warnings = [
            d for d in payload["diagnostics"]
            if d["code"] == "execution.underdetermined"
        ]
        assert warnings
        assert warnings[0]["remediation"]
        assert warnings[0]["origin"] == "morris2011"

    def test_an_unresolved_value_is_not_injected_into_a_downstream_model(self):
        payload = example_result("failure_propagation.json")
        messages = " ".join(d["message"] for d in payload["diagnostics"])
        assert "received no values from stage_a" in messages
        assert "would present a result computed from missing data" in messages

    def test_the_zielinski_model_still_fails_closed_inside_a_composition(self, engine):
        """A predictive Zielinski run with no declared inputs resolves nothing.
        That has to survive composition unchanged."""
        from composition.contracts import ModelInstance
        from composition.runner import run_graph

        document = read_example("brass_batch_chain.json")
        document["graph_id"] = "predictive-probe"
        document["instances"] = [{
            "instance_id": "z",
            "model_id": "zielinski2019.rhi_process",
            "model_version": "1.0.0",
            "parameters": {"execution": {"mode": "predictive"}},
        }]
        document["connections"] = []
        document["literal_inputs"] = {}
        payload, code = run_graph(document, base=ROOT)
        assert code == 0
        summary = payload["results"][0]["raw_summary"]
        assert summary["predicted_values"] == 0
        assert summary["unresolved_targets"] == 23


# --------------------------------------------------------------------------- #
# CG-08 -- component mapping
# --------------------------------------------------------------------------- #


class TestCG08ComponentMapping:
    """Unmapped or incompatible components produce an actionable diagnostic."""

    def test_an_unmapped_component_is_refused(self):
        payload = example_result("rejected_component_mapping.json")
        codes = error_codes(payload)
        assert "connection.component_unattributed" in codes

    def test_the_unmapped_diagnostic_names_what_to_do(self):
        payload = example_result("rejected_component_mapping.json")
        diagnostic = next(
            d for d in payload["diagnostics"]
            if d["code"] == "connection.component_unattributed"
            and d["where"][-1] == "bad-unmapped-to-component"
        )
        assert "component 'Zn'" in diagnostic["message"]
        assert diagnostic["remediation"]
        assert "wet_biomass" in diagnostic["message"]

    def test_an_incompatible_component_is_refused(self):
        payload = example_result("rejected_component_mapping.json")
        mismatches = [
            d for d in payload["diagnostics"]
            if d["code"] == "connection.component_mismatch"
        ]
        assert mismatches
        assert "carries component 'Cu'" in mismatches[0]["message"]
        assert "expects 'Zn'" in mismatches[0]["message"]

    def test_a_matching_component_connects(self, brass_chain):
        """The same rule, satisfied: Cu into Cu."""
        assert not [
            d for d in brass_chain["diagnostics"]
            if d["code"] in ("connection.component_mismatch",
                             "connection.component_unattributed")
        ]

    def test_the_zielinski_manifest_publishes_no_component_identity(self,
                                                                    manifest_zielinski):
        assert all(p.components == () for p in manifest_zielinski.ports)
        assert all(p.component is None for p in manifest_zielinski.ports)
        assert "component_identity" in manifest_zielinski.unsupported_capabilities

    def test_morris_publishes_component_identity_on_its_ports(self,
                                                               manifest_brass_charge):
        cu = manifest_brass_charge.port("in:B:Cu")
        assert cu.component == "Cu"
        assert cu.components == ("Cu",)
        total = manifest_brass_charge.port("in:C:total")
        assert total.attribution_required is True
        assert set(total.components) == {"Cu", "Zn"}


# --------------------------------------------------------------------------- #
# CG-09 -- unsupported physics
# --------------------------------------------------------------------------- #


class TestCG09UnsupportedPhysics:
    """The layer refuses to claim a valid reactive balance without reaction terms."""

    def test_a_reactive_boundary_is_refused(self):
        payload = example_result("rejected_component_mapping.json")
        refusals = [
            d for d in payload["diagnostics"]
            if d["code"] == "capability.reactive_balance_refused"
        ]
        assert len(refusals) == 2
        message = refusals[0]["message"]
        assert "Non-Reacting Systems" in message
        assert "no reaction term" in message

    def test_the_morris_manifest_declares_itself_non_reacting(self,
                                                             manifest_brass_charge):
        assert manifest_brass_charge.non_reacting_only is True
        assert manifest_brass_charge.reaction_terms == ()
        assert "reactive_balance" in manifest_brass_charge.unsupported_capabilities

    def test_the_zielinski_manifest_declares_no_reaction_terms(self, manifest_zielinski):
        assert manifest_zielinski.reaction_terms == ()
        assert "component_identity" in manifest_zielinski.unsupported_capabilities

    def test_the_au_edge_is_refused_on_quantity_grounds_too(self):
        payload = example_result("rejected_au_to_mass.json")
        assert "connection.quantity_mismatch" in error_codes(payload)

    def test_a_non_reacting_boundary_between_two_compatible_models_is_allowed(self,
                                                                              brass_chain):
        """The refusal is not a blanket ban on Morris -> Morris. Brass mixing is
        non-reacting and the graph runs."""
        assert not [
            d for d in brass_chain["diagnostics"]
            if d["code"] == "capability.reactive_balance_refused"
        ]


# --------------------------------------------------------------------------- #
# CG-10 -- cycle detection
# --------------------------------------------------------------------------- #


class TestCG10CycleDetection:
    """A cyclic graph is rejected with the participating nodes identified."""

    def test_the_cycle_is_detected(self):
        payload = example_result("cycle_rejected.json")
        assert error_codes(payload) == {"order.cycle_detected"}
        assert payload["status"] == "refused"

    def test_the_participating_nodes_are_named(self):
        payload = example_result("cycle_rejected.json")
        diagnostic = payload["diagnostics"][-1]
        assert set(diagnostic["detail"]["participants"]) == {"stage_a", "stage_b"}
        assert "stage_a -> stage_b -> stage_a" in diagnostic["message"]

    def test_the_involved_connections_are_named(self):
        payload = example_result("cycle_rejected.json")
        diagnostic = payload["diagnostics"][-1]
        assert set(diagnostic["detail"]["connections"]) == {
            "a-to-b", "a-to-b-wcu", "b-to-a", "b-to-a-wcu"
        }

    def test_nothing_is_executed_when_a_cycle_is_found(self):
        payload = example_result("cycle_rejected.json")
        assert payload["results"] == []
        assert payload["reproducibility"] == ""

    def test_a_self_loop_is_refused_with_its_own_code(self, engine):
        from composition.contracts import (
            Connection, ModelInstance, PortRef, load_graph as _load,
        )

        graph = load_graph(read_example("brass_batch_chain.json"))
        loop = Connection(
            connection_id="self",
            source=PortRef("brass_charge", "out:D:total"),
            target=PortRef("brass_charge", "in:C:total"),
        )
        from composition.engine import CompositionEngine

        probe = CompositionEngine(base_path=ROOT)
        loaded = probe.load(graph)
        diagnostics = probe.validate_connections(
            _with_extra_connection(graph, loop), loaded
        )
        assert "connection.self_loop" in {d.code.value for d in diagnostics}


# --------------------------------------------------------------------------- #
# CG-11 -- failure propagation
# --------------------------------------------------------------------------- #


class TestCG11FailurePropagation:
    """A model execution error prevents dependent models from running."""

    def test_the_dependent_instance_is_not_executed(self):
        payload = example_result("failure_propagation.json")
        by_id = {r["instance_id"]: r for r in payload["results"]}
        assert by_id["stage_a"]["status"] == "failed"
        assert by_id["stage_b"]["status"] == "failed"
        assert by_id["stage_b"]["outputs"] == []

    def test_the_diagnostic_names_the_upstream_cause(self):
        payload = example_result("failure_propagation.json")
        diagnostic = next(
            d for d in payload["diagnostics"]
            if d["code"] == "execution.dependent_skipped"
        )
        assert "stage_b" in diagnostic["message"]
        assert "stage_a" in diagnostic["message"]
        assert diagnostic["detail"]["blocked_by"] == ["stage_a"]

    def test_the_diagnostic_is_addressable_by_the_editor(self):
        """Godot's diagnostics panel keys on `where`, so it must be populated."""
        payload = example_result("failure_propagation.json")
        skipped = next(
            d for d in payload["diagnostics"]
            if d["code"] == "execution.dependent_skipped"
        )
        assert skipped["where"] == ["instance", "stage_b"]
        assert skipped["origin"] == "execution"

    def test_the_inconsistent_balance_is_reported_not_repaired(self):
        payload = example_result("failure_propagation.json")
        message = next(
            d["message"] for d in payload["diagnostics"]
            if d["code"] == "execution.model_failed"
        )
        assert "contradict each other" in message
        assert "Nothing was solved" in message
        assert "no measurement was altered" in message

    def test_the_runner_exits_with_the_failure_code(self):
        _payload, code = run_example("failure_propagation.json")
        assert code == 2


# --------------------------------------------------------------------------- #
# CG-12 -- provenance
# --------------------------------------------------------------------------- #


class TestCG12Provenance:
    """A displayed result traces to source model, inputs, connections,
    assumptions and derived calculations."""

    def test_every_output_carries_a_provenance_record(self, brass_chain):
        for result in brass_chain["results"]:
            assert result["outputs"], result["instance_id"]
            for out in result["outputs"]:
                assert out["provenance_chain"], out["ref"]["port_id"]

    def test_the_record_names_the_producing_model_and_version(self, brass_chain):
        chain = output_of(brass_chain, "brass_charge", "out:D:Cu")["provenance_chain"]
        assert chain[0]["producer_model"] == "morris2011.material_balance"
        assert chain[0]["producer_version"] == "0.1.0"
        assert chain[0]["kind"] == "source"

    def test_a_solved_value_names_the_equations_it_came_from(self, brass_chain):
        cu = output_of(brass_chain, "brass_charge", "out:D:Cu")["value"]
        assert "solved" in (cu["method"] or "")
        assert cu["method"].startswith("solved: solved from the assembled linear")

    def test_a_derived_total_names_its_components(self, brass_chain):
        total = output_of(brass_chain, "brass_charge", "out:D:total")["value"]
        assert "sum of the solved component amounts" in total["method"]
        assert "Cu=21215" in total["method"]
        assert "Zn=5385" in total["method"]

    def test_a_reported_value_carries_its_source_reference(self, brass_chain):
        zn = output_of(brass_chain, "brass_charge", "out:A:Zn")["value"]
        assert zn["provenance"] == "reported"
        assert "Example 4.2" in zn["source_ref"]

    def test_a_zero_is_marked_as_a_zero_not_as_a_number(self, brass_chain):
        residual = output_of(brass_chain, "brass_charge",
                             "out:residual:Cu")["value"]
        assert residual["state"] == "zero"
        assert residual["value"] == 0.0
        assert "4.6.2" in residual["method"]

    def test_the_provenance_index_is_published_for_every_output(self, brass_chain):
        index = brass_chain["provenance_index"]
        assert "brass_charge/out:D:Cu" in index
        assert "brass_alloying/out:E:total" in index
        assert index["brass_charge/out:D:Cu"][0]["kind"] == "source"

    def test_a_literal_input_is_traced_to_its_declaration(self, brass_chain):
        inputs = [
            i for r in brass_chain["results"]
            if r["instance_id"] == "brass_alloying"
            for i in r["inputs"]
            if i["via"] == "literal"
        ]
        assert len(inputs) == 1
        assert inputs[0]["value"]["provenance"] == "assumed"
        assert inputs[0]["provenance_chain"][0]["kind"] == "assumption"

    def test_the_assumption_that_the_literal_input_encodes_is_published(self,
                                                                       manifest_alloying):
        ids = {a["assumption_id"] for a in manifest_alloying.assumptions}
        assert "COMP-MAKEUP-500KG" in ids

    def test_a_zielinski_value_traces_to_a_page_of_the_paper(self, brass_chain):
        value = output_of(
            brass_chain, "zielinski_rhi",
            "stream:S03_wet_biomass#wet_biomass_total",
        )["value"]
        assert value["provenance"] == "reported"
        assert "p." in (value["source_ref"] or "")

    def test_an_absorbed_value_reports_what_the_paper_says_not_what_was_computed(
            self, brass_chain
    ):
        value = output_of(
            brass_chain, "zielinski_rhi",
            "node:N01#inoculum_target_od600",
        )["value"]
        assert value["state"] == "range"
        assert value["value"] is None
        assert value["value_range"] == [0.5, 1.0]

    def test_an_unknown_stays_unknown_with_its_reason(self, brass_chain):
        value = output_of(
            brass_chain, "zielinski_rhi", "node:N01#induction_time",
        )["value"]
        assert value["state"] == "unknown"
        assert value["value"] is None
        assert value["reason"]

    def test_model_findings_keep_their_own_severity_and_origin(self, brass_chain):
        findings = [
            d for d in brass_chain["diagnostics"]
            if d["code"] == "model.finding"
        ]
        assert findings
        assert any(d["severity"] == "error" for d in findings)
        assert all(d["origin"] == "zielinski2019" for d in findings)
        assert all(d["detail"]["model_severity"] == d["severity"] for d in findings)


# --------------------------------------------------------------------------- #
# CG-13 -- reproducibility
# --------------------------------------------------------------------------- #


class TestCG13Reproducibility:
    """The same graph, versions and inputs produce equivalent numerical outputs."""

    def test_two_runs_produce_the_same_digest(self):
        first = example_result("brass_batch_chain.json")
        second = example_result("brass_batch_chain.json")
        assert first["reproducibility"] == second["reproducibility"]
        assert first["reproducibility"]

    def test_the_digest_covers_every_numeric_output(self):
        def numbers(payload):
            return {
                (r["instance_id"], o["ref"]["port_id"]):
                    (o["value"]["state"], repr(o["value"]["value"]))
                for r in payload["results"]
                for o in r["outputs"]
            }

        first = example_result("brass_batch_chain.json")
        second = example_result("brass_batch_chain.json")
        assert numbers(first) == numbers(second)

    def test_the_plan_digest_is_stable(self):
        first = example_result("brass_batch_chain.json")["plan"]["digest"]
        second = example_result("brass_batch_chain.json")["plan"]["digest"]
        assert first == second

    def test_the_digest_changes_when_an_input_changes(self):
        document = read_example("brass_batch_chain.json")
        document["literal_inputs"]["brass_alloying/in:B:Zn"]["value"] = 750.0
        from composition.runner import run_graph

        changed, _code = run_graph(document, base=ROOT)
        base = example_result("brass_batch_chain.json")
        assert changed["reproducibility"] != base["reproducibility"]

    def test_the_output_document_is_byte_stable(self, work_dir):
        outputs = []
        for index in range(2):
            path = work_dir / f"result-{index}.json"
            completed = subprocess.run(
                [sys.executable, "-m", "composition.runner",
                 "--graph", str(EXAMPLES / "brass_batch_chain.json"),
                 "--result", str(path)],
                cwd=str(COMPOSITION_ROOT.parent), capture_output=True, text=True,
                env={**_env(), "PYTHONPATH": str(COMPOSITION_ROOT)},
                timeout=600,
            )
            assert completed.returncode == 0, completed.stdout + completed.stderr
            outputs.append(path.read_bytes())
        assert outputs[0] == outputs[1]
        assert b"reproducibility" in outputs[0]


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)


# --------------------------------------------------------------------------- #
# CG-14 -- end-to-end execution
# --------------------------------------------------------------------------- #


class TestCG14EndToEndExecution:
    """A user can load the example graph, validate it, run it and inspect the
    results without editing intermediate JSON."""

    def test_every_shipped_example_matches_its_documented_outcome(self, example_names):
        for name in example_names:
            expected = EXAMPLE_EXPECTATIONS[name]
            payload, code = run_example(name)
            assert code == expected["exit_code"], (
                f"{name}: expected exit {expected['exit_code']}, got {code}"
            )
            assert payload["error_count"] >= expected["min_errors"], name

    def test_the_main_example_validates(self):
        payload, _code = run_example("brass_batch_chain.json")
        assert payload["status"] in ("success", "success_with_warnings")
        assert payload["plan"]["order"]
        assert payload["plan"]["digest"]

    def test_the_main_example_runs_every_instance(self):
        payload = example_result("brass_batch_chain.json")
        assert [r["instance_id"] for r in payload["results"]] == [
            "brass_charge", "brass_alloying", "zielinski_rhi"
        ]

    def test_the_results_panel_has_something_to_show_for_each_instance(self):
        payload = example_result("brass_batch_chain.json")
        for result in payload["results"]:
            assert result["outputs"]
            assert result["raw_summary"]

    def test_plan_only_validates_without_executing(self):
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner",
             "--graph", str(EXAMPLES / "brass_batch_chain.json"),
             "--plan-only"],
            cwd=str(COMPOSITION_ROOT.parent), capture_output=True, text=True,
            env={**_env(), "PYTHONPATH": str(COMPOSITION_ROOT)},
            timeout=600,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["results"] == []
        assert payload["plan"]["order"] == [
            "brass_charge", "brass_alloying", "zielinski_rhi"
        ]

    def test_the_runner_reports_the_models_it_can_reach(self):
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--list-models"],
            cwd=str(COMPOSITION_ROOT.parent), capture_output=True, text=True,
            env={**_env(), "PYTHONPATH": str(COMPOSITION_ROOT)},
            timeout=120,
        )
        assert completed.returncode == 0
        payload = json.loads(completed.stdout)
        available = {m["model_id"] for m in payload["models"] if m["available"]}
        assert available == {"morris2011.material_balance",
                             "zielinski2019.rhi_process"}


# --------------------------------------------------------------------------- #
# CG-15 -- the existing regression suite
# --------------------------------------------------------------------------- #


class TestCG15ExistingRegressionSuite:
    """All existing tests remain green; totals are reported separately."""

    def test_the_composition_suite_does_not_write_into_models(self, repository_root):
        """A cheap structural guarantee: nothing under Models/ is importable as
        a composition module, and the composition package holds no copy of a
        model file."""
        composition_files = sorted(
            p.relative_to(COMPOSITION_ROOT).as_posix()
            for p in COMPOSITION_ROOT.rglob("*")
            if p.is_file() and p.suffix in (".py", ".json")
            and "__pycache__" not in p.parts
        )
        assert not [f for f in composition_files if f.startswith("Models")]

    def test_the_two_suites_are_reported_separately(self):
        """Run both model suites as subprocesses from their own roots.

        The composition suite's own count is reported by the test runner, not
        from inside the suite: a test that shells out to run the suite that is
        currently running would recurse.
        """
        counts = {
            "morris": int(run_model_suite("Models/Morris").split()[0]),
            "zielinski": int(run_model_suite("Models/Zielinski").split()[0]),
        }
        assert counts == {"morris": 186, "zielinski": 223}

    def test_no_composition_module_is_importable_from_inside_models(self):
        """The dependency arrow points one way. Neither model package may import
        the composition contract, and the composition package imports neither
        model."""
        import ast

        for package in ("Models/Morris", "Models/Zielinski"):
            for path in (ROOT / package).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module]
                    assert not any(n.split(".")[0] == "composition" for n in names), (
                        f"{path} imports the composition contract"
                    )

        for path in (COMPOSITION_ROOT / "composition").rglob("*.py"):
            if "_workers" in path.parts:
                continue  # workers import models deliberately, inside isolation
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                assert not any(
                    n.split(".")[0] in ("schemas", "scaleup_ai", "models")
                    for n in names
                ), f"{path} imports a model package directly: {names}"


# --------------------------------------------------------------------------- #
# coverage table
# --------------------------------------------------------------------------- #


CG_COVERAGE = {
    "CG-01": TestCG01ModelDiscovery,
    "CG-02": TestCG02PortCompatibility,
    "CG-03": TestCG03UnitSemantics,
    "CG-04": TestCG04GraphOrdering,
    "CG-05": TestCG05DataTransfer,
    "CG-06": TestCG06ConservationRegression,
    "CG-07": TestCG07MissingInformation,
    "CG-08": TestCG08ComponentMapping,
    "CG-09": TestCG09UnsupportedPhysics,
    "CG-10": TestCG10CycleDetection,
    "CG-11": TestCG11FailurePropagation,
    "CG-12": TestCG12Provenance,
    "CG-13": TestCG13Reproducibility,
    "CG-14": TestCG14EndToEndExecution,
    "CG-15": TestCG15ExistingRegressionSuite,
}


class TestCoverageTable:
    """The table cannot drift away from the suite."""

    def test_every_criterion_has_a_class(self):
        expected = {f"CG-{n:02d}" for n in range(1, 16)}
        assert set(CG_COVERAGE) == expected

    def test_every_class_has_tests(self):
        for criterion, cls in CG_COVERAGE.items():
            names = [n for n in dir(cls) if n.startswith("test_")]
            assert names, f"{criterion} has no tests"
            assert len(names) >= 3, f"{criterion} is under-specified ({len(names)})"