"""Acceptance tests: the completion criterion from the handoff.

    "A reviewer must be able to trace every reported number to the paper,
     every derived number to an explicit calculation, and every unavailable
     prediction to an explicit unresolved dependency."
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scaleup_ai import Provenance
from scaleup_ai.report import ModelBundle, write_all


# --------------------------------------------------------------------------- #
# criterion 1: every reported number traces to the paper
# --------------------------------------------------------------------------- #


def test_every_reported_quantity_cites_page_and_source_text(graph):
    for location, qid, q in graph.iter_quantities():
        if q.provenance is not Provenance.REPORTED:
            continue
        assert q.evidence, qid
        page = q.evidence[0].printed_page
        assert 63 <= page <= 69, f"{location}:{qid} cites p.{page}"


def test_page_numbers_are_consistent_across_the_whole_graph(graph):
    pages = set()
    for _loc, _qid, q in graph.iter_quantities():
        for e in q.evidence:
            pages.add(e.printed_page)
    assert pages <= set(range(63, 70))
    assert {63, 64, 65, 66, 67, 68, 69} & pages


# --------------------------------------------------------------------------- #
# criterion 2: every derived number traces to an explicit calculation
# --------------------------------------------------------------------------- #


def test_every_derived_quantity_names_its_equation_and_inputs(replay):
    for nr in replay.node_results:
        for q in nr.computed:
            assert q.method
            assert q.inputs
            assert any(t.output_quantity_id == q.quantity_id for t in nr.traces)


def test_every_trace_expands_to_reproducible_arithmetic(replay):
    for nr in replay.node_results:
        for t in nr.traces:
            assert t.input_values
            for spec, entry in t.input_values.items():
                assert entry["ref"]
                assert entry["value"] is not None
                assert entry["source_unit"]
                assert entry["normalized_unit"]
                assert entry["provenance"]


# --------------------------------------------------------------------------- #
# criterion 3: every unavailable prediction has an explicit dependency
# --------------------------------------------------------------------------- #


def test_every_unknown_quantity_states_why_it_is_unknown(graph):
    unknown_qs = [
        q for _l, _i, q in graph.iter_quantities()
        if q.provenance is Provenance.UNKNOWN
    ]
    assert unknown_qs
    for q in unknown_qs:
        assert q.notes, f"{q.quantity_id} is unknown without a reason"


def test_unresolved_targets_are_all_explained(replay):
    for u in replay.unresolved:
        assert u.reason
        assert u.target


# --------------------------------------------------------------------------- #
# observed vs computed separation
# --------------------------------------------------------------------------- #


def test_run_distinguishes_observed_reference_from_computed(replay):
    s = replay.summary.to_dict()
    assert s["observed_reference_values"] > 100
    assert s["digitized_values"] > 0
    assert s["computed_values"] > 0
    assert s["predicted_values"] == 0
    assert s["graph_is_predictive"] is False


def test_computed_values_are_all_derived_never_reported(graph):
    computed_ids = {q.quantity_id for _l, _i, q in graph.iter_quantities()
                    if q.provenance is Provenance.DERIVED}
    replay_ids = set()
    for nr in graph.nodes:
        replay_ids |= set(nr.calculated)
    assert replay_ids <= computed_ids


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def artifacts(engine):
    """Write artifacts to a private temp dir.

    Uses tempfile.mkdtemp rather than pytest's tmp_path_factory, which cannot
    enumerate the shared temp root in this environment.
    """
    import shutil
    import tempfile

    out = Path(tempfile.mkdtemp(prefix="zielinski_artifacts_"))
    bundle = ModelBundle.build(engine)
    written = write_all(bundle, out)
    yield bundle, written, out
    shutil.rmtree(out, ignore_errors=True)


def test_all_artifacts_are_written(artifacts):
    _bundle, written, _out = artifacts
    for name in ("graph", "evidence_record", "quantities", "computed", "summary_md"):
        path = written[name]
        assert path.exists() and path.stat().st_size > 0, name


def test_evidence_record_is_valid_json_and_complete(artifacts):
    _bundle, written, _out = artifacts
    data = json.loads(written["evidence_record"].read_text(encoding="utf-8"))
    assert data["record_type"] == "scaleup_ai_evidence_record"
    assert len(data["graph"]["nodes"]) == 15
    assert data["equation_registry"]
    assert data["declared_missing_models"]
    assert data["runs"]["evidence_replay"]["summary"]["graph_is_predictive"] is False
    assert data["runs"]["predictive"]["summary"]["predicted_values"] == 0
    assert data["interpretation"]["evidence_replay_is_predictive"] is False


def _read_csv(path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_quantities_csv_is_fully_populated(artifacts):
    _bundle, written, _out = artifacts
    rows = _read_csv(written["quantities"])
    assert len(rows) > 150
    for row in rows:
        assert row["provenance"]
        assert row["location"] and row["quantity_id"]
        if row["provenance"] == "reported":
            assert row["source_id"] and row["printed_page"]
        if row["provenance"] == "unknown":
            assert row["value"] == "" and row["value_low"] == ""


def test_computed_csv_records_equation_and_inputs(artifacts):
    _bundle, written, _out = artifacts
    rows = _read_csv(written["computed"])
    assert len(rows) == 20
    for row in rows:
        assert row["equation_id"] and row["statement"] and row["inputs"]


def test_generated_summary_states_the_predictive_boundary(artifacts):
    _bundle, written, _out = artifacts
    text = written["summary_md"].read_text(encoding="utf-8")
    assert "graph_is_predictive" in text
    assert "Cross-checks" in text
    assert "Unresolved targets" in text
    assert "Provenance census" in text


# --------------------------------------------------------------------------- #
# scope exclusions are actually respected
# --------------------------------------------------------------------------- #


def test_no_monod_or_biomass_differential_equation(graph):
    from scaleup_ai.equations import EQUATIONS

    for eq in EQUATIONS.values():
        assert "monod" not in eq.equation_id.lower()
        assert "kinetic" not in eq.equation_id.lower()
        assert "ode" not in eq.equation_id.lower()


def test_no_purification_recovery_efficiencies(graph):
    for _loc, _qid, q in graph.iter_quantities():
        if "recovery" in q.quantity_id and q.value is not None:
            pytest.fail(f"invented recovery: {q.quantity_id}")


def test_no_au_to_mass_or_au_to_iu_conversion_exists():
    from scaleup_ai.units import is_convertible

    assert not is_convertible("AU", "g")
    assert not is_convertible("AU", "IU")
    assert not is_convertible("AU/mL", "mg/mL")


def test_contradictions_are_not_silently_resolved(graph):
    """Every known source contradiction must still be reported as a message."""
    codes = {m.code for n in graph.nodes for m in n.validation_messages}
    for expected in (
        "source_discrepancy:water_volume_vs_formula",
        "source_discrepancy:cpb_dose_vs_au",
        "source_discrepancy:refolding_yield_vs_au",
        "source_discrepancy:induction_order",
        "source_discrepancy:digitized_vs_reported_od600",
    ):
        assert expected in codes


def test_repeated_runs_are_byte_identical(engine):
    import shutil
    import tempfile

    out = Path(tempfile.mkdtemp(prefix="zielinski_determinism_"))
    try:
        a = ModelBundle.build(engine)
        b = ModelBundle.build(engine)
        pa = write_all(a, out / "a")["evidence_record"].read_text(encoding="utf-8")
        pb = write_all(b, out / "b")["evidence_record"].read_text(encoding="utf-8")
        assert pa == pb
    finally:
        shutil.rmtree(out, ignore_errors=True)