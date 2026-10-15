"""Structural tests for the graph document and the contract types.

These pin the JSON boundary: the document the canvas edits and the runner
consumes. A change that breaks a graph file's round trip is a change to the
public interface, not an internal refactor.
"""

from __future__ import annotations

import pytest

from composition.contracts import (
    CONTRACT_VERSION,
    CompositionGraph,
    Connection,
    ModelInstance,
    PortDirection,
    PortRef,
    ValueState,
    load_graph,
)
from composition.quantities import Quantity


class TestContractVersion:
    def test_the_version_is_pinned(self):
        assert CONTRACT_VERSION == "0.1.0"

    def test_every_document_carries_the_version(self, brass_graph):
        assert brass_graph.contract_version == CONTRACT_VERSION

    def test_a_graph_under_another_version_is_refused(self, brass_graph):
        # Copy rather than mutate: the fixture is session-scoped and shared.
        doc = brass_graph.to_dict()
        doc["contract_version"] = "9.9.9"
        with pytest.raises(Exception) as excinfo:
            load_graph(doc)
        assert "9.9.9" in str(excinfo.value)


class TestGraphDocument:
    def test_a_graph_round_trips_through_the_contract(self, brass_graph):
        restored = load_graph(brass_graph.to_dict())
        assert restored.graph_id == brass_graph.graph_id
        assert [i.instance_id for i in restored.instances] == [
            i.instance_id for i in brass_graph.instances
        ]
        assert len(restored.connections) == len(brass_graph.connections)
        assert restored.to_dict() == brass_graph.to_dict()

    def test_duplicate_instance_ids_are_refused(self, brass_graph):
        doc = brass_graph.to_dict()
        doc["instances"].append(doc["instances"][0])
        with pytest.raises(Exception):
            load_graph(doc)

    def test_duplicate_connection_ids_are_refused(self, brass_graph):
        doc = brass_graph.to_dict()
        doc["connections"].append(doc["connections"][0])
        with pytest.raises(Exception):
            load_graph(doc)

    def test_an_unknown_instance_on_a_connection_is_refused(self, brass_graph):
        doc = brass_graph.to_dict()
        doc["connections"][0]["source"]["instance_id"] = "nope"
        with pytest.raises(Exception):
            load_graph(doc)

    def test_a_self_loop_is_recorded_not_silently_dropped(self, brass_graph):
        """The canvas refuses a self-loop before it reaches the document, but if
        one ever arrives the graph still carries it so the runner can name it."""
        loop = Connection(
            connection_id="self",
            source=PortRef("brass_charge", "out:D:total"),
            target=PortRef("brass_charge", "in:C:total"),
        )
        graph = CompositionGraph(
            graph_id="g", title="t", instances=brass_graph.instances,
            connections=(*brass_graph.connections, loop),
        )
        assert any(c.source.instance_id == c.target.instance_id
                   for c in graph.connections)


class TestPortRefs:
    def test_a_port_ref_is_addressable_by_instance_and_port(self):
        ref = PortRef("brass_charge", "out:D:total")
        assert ref.key == "brass_charge/out:D:total"

    def test_an_incomplete_port_ref_is_refused(self):
        with pytest.raises(Exception):
            PortRef("", "out:D:total")
        with pytest.raises(Exception):
            PortRef("brass_charge", "")


class TestInstances:
    def test_an_instance_without_an_id_is_refused(self):
        with pytest.raises(Exception):
            ModelInstance(instance_id="", model_id="m", model_version="1")

    def test_its_ports_come_from_the_manifest_not_the_instance(self):
        """A graph document stores parameters, not ports. Ports are derived
        from the model's manifest, so the canvas cannot offer a port the model
        does not declare."""
        inst = ModelInstance(instance_id="x", model_id="m", model_version="1")
        assert inst.parameters == {}


class TestValueStateBoundaries:
    def test_a_value_cannot_be_both_number_and_range(self):
        from composition.contracts import ModelValue, ContractError

        with pytest.raises(ContractError):
            ModelValue(
                state=ValueState.NUMBER, quantity=Quantity.MASS, unit="kg",
                value=1.0, value_range=(0.0, 2.0),
            )

    def test_a_range_carrying_no_interval_is_refused(self):
        from composition.contracts import ModelValue, ContractError

        with pytest.raises(ContractError):
            ModelValue(
                state=ValueState.RANGE, quantity=Quantity.MASS, unit="kg",
            )

    def test_the_zielinski_range_survives_a_round_trip(self):
        """`15-16 h` must come back as an interval, not as 16."""
        from composition.contracts import ModelValue, ValueProvenance

        original = ModelValue.unavailable(
            ValueState.RANGE, quantity=Quantity.TIME, unit="h",
            value_range=(15.0, 16.0), reason="reported as '15-16 h'",
        )
        restored = ModelValue.from_dict(original.to_dict())
        assert restored.value is None
        assert restored.value_range == (15.0, 16.0)
        assert restored.display == "15-16 h"
        assert restored.provenance is ValueProvenance.UNKNOWN
