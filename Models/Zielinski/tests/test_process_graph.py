"""Process graph structure: nodes, streams, ordering and identity."""

from __future__ import annotations

import pytest

from scaleup_ai import GraphError, OperationKind, StreamKind
from scaleup_ai.process import MaterialStream, ProcessGraph, ProcessNode

EXPECTED_NODES = [
    ("N01", "Fermentation", OperationKind.FERMENTATION),
    ("N02", "Biomass harvest", OperationKind.HARVEST),
    ("N03", "Cell lysis and inclusion-body isolation", OperationKind.LYSIS),
    ("N04", "Inclusion-body dissolution", OperationKind.DISSOLUTION),
    ("N05", "Protein renaturation", OperationKind.RENATURATION),
    ("N06", "Citraconylation", OperationKind.CHEMICAL_MODIFICATION),
    ("N07", "Trypsinization", OperationKind.PROTEOLYSIS),
    ("N08", "DEAE Sepharose purification", OperationKind.CHROMATOGRAPHY),
    ("N09", "Decitraconylation", OperationKind.CHEMICAL_MODIFICATION),
    ("N10", "Zinc precipitation and zinc-salt dissolution", OperationKind.PRECIPITATION),
    ("N11", "Q Sepharose purification", OperationKind.CHROMATOGRAPHY),
    ("N12", "Carboxypeptidase B treatment", OperationKind.PROTEOLYSIS),
    ("N13", "RP-HPLC purification", OperationKind.CHROMATOGRAPHY),
    ("N14", "Sephadex G-25 buffer exchange", OperationKind.CHROMATOGRAPHY),
    ("N15", "Final product characterization", OperationKind.CHARACTERIZATION),
]


def test_graph_has_the_fifteen_specified_nodes_in_order(graph):
    assert [(n.node_id, n.name, n.operation) for n in graph.topological_order()] == EXPECTED_NODES


def test_graph_structure_validates_cleanly(graph):
    assert graph.validate() == []


EXTERNAL_STREAMS = {"S01_inoculum"}          # nothing in the graph produces it
TERMINAL_STREAMS = {"S17_final_product"}    # nothing in the graph consumes it
STOWABLE_BRANCH = {"S11_insulin_precipitate"}  # stored, not fed forward within N10


def test_every_stream_has_one_producer_and_one_consumer(graph):
    for sid, stream in graph.streams.items():
        if sid in EXTERNAL_STREAMS:
            assert stream.produced_by is None, sid
        else:
            assert stream.produced_by is not None, sid
        if sid in TERMINAL_STREAMS | STOWABLE_BRANCH:
            assert stream.consumed_by is None, sid
        else:
            assert stream.consumed_by is not None, sid


def test_stream_identity_and_lineage_are_preserved(graph):
    chain = [
        "S01_inoculum", "S02_culture_broth", "S03_wet_biomass",
        "S04_inclusion_bodies", "S05_denatured_solution", "S06_renatured_precursor",
        "S07_citraconylated", "S08_digested", "S09_deae_fraction",
        "S10_citrately_blocked", "S11_insulin_precipitate", "S12_dissolved_zinc_salt",
        "S13_q_fraction", "S14_cpb_treated", "S15_rp_hplc_fraction",
        "S16_g25_fraction", "S17_final_product",
    ]
    assert graph.stream(chain[0]).lineage == ()
    for prev, sid in zip(chain, chain[1:]):
        assert graph.stream(sid).lineage == (prev,), sid


def test_each_stream_records_the_operation_responsible_for_it(graph):
    for sid, stream in graph.streams.items():
        if stream.produced_by is None:
            continue
        producer = graph.node(stream.produced_by)
        assert sid in producer.output_streams


def test_g25_is_retained_despite_the_three_step_summary(graph):
    """sec. 4.13 calls purification 'three-step'; G-25 is still a real operation."""
    g25 = graph.node("N14")
    assert g25.operation is OperationKind.CHROMATOGRAPHY
    assert "three-step purification" in g25.condition_notes["note"]


def test_zinc_node_emits_both_precipitate_and_dissolved_streams(graph):
    n10 = graph.node("N10")
    assert set(n10.output_streams) == {"S11_insulin_precipitate", "S12_dissolved_zinc_salt"}
    assert n10.input_streams == ("S10_citrately_blocked",)


def test_figure1_block_diagram_is_mapped(graph):
    mapped = {n.figure1_label for n in graph.nodes if n.figure1_label}
    assert "E. coli 20 cells culture" in mapped
    assert "Inclusion bodies isolation" in mapped
    assert "Sephadex G-25 chromatography" in mapped
    # characterization is an analytical endpoint, not a Fig.1 box
    assert graph.node("N15").figure1_label is None


def test_every_node_declares_evidence(graph):
    for node in graph.nodes:
        assert node.evidence, node.node_id


def test_source_discrepancies_are_recorded_not_resolved(graph):
    codes = {m.code for n in graph.nodes for m in n.validation_messages}
    assert "source_discrepancy:water_volume_vs_formula" in codes
    assert "source_discrepancy:cpb_dose_vs_au" in codes
    assert "source_discrepancy:refolding_yield_vs_au" in codes
    assert "source_discrepancy:induction_order" in codes


# --------------------------------------------------------------------------- #
# negative cases
# --------------------------------------------------------------------------- #


def test_duplicate_node_id_is_rejected():
    g = ProcessGraph("g", "t", "s")
    node = ProcessNode("N01", 1, "a", OperationKind.HARVEST)
    g.add_node(node)
    with pytest.raises(GraphError, match="duplicate node id"):
        g.add_node(ProcessNode("N01", 2, "b", OperationKind.HARVEST))


def test_dangling_stream_reference_is_reported():
    g = ProcessGraph("g", "t", "s")
    g.add_node(ProcessNode("N01", 1, "a", OperationKind.HARVEST,
                           input_streams=("S_nope",)))
    codes = {m.code for m in g.validate()}
    assert "dangling_stream" in codes


def test_stream_referencing_unknown_node_raises():
    g = ProcessGraph("g", "t", "s")
    g.add_stream(MaterialStream("S01", "x", StreamKind.WASTE, produced_by="N99"))
    with pytest.raises(GraphError, match="unknown node"):
        g.validate()


def test_cycle_is_detected():
    g = ProcessGraph("g", "t", "s")
    g.add_stream(MaterialStream("A", "a", StreamKind.WASTE, produced_by="N1", consumed_by="N2"))
    g.add_stream(MaterialStream("B", "b", StreamKind.WASTE, produced_by="N2", consumed_by="N1"))
    g.add_node(ProcessNode("N1", 1, "a", OperationKind.HARVEST, input_streams=("B",), output_streams=("A",)))
    g.add_node(ProcessNode("N2", 2, "b", OperationKind.HARVEST, input_streams=("A",), output_streams=("B",)))
    with pytest.raises(GraphError, match="cycle"):
        g.topological_order()