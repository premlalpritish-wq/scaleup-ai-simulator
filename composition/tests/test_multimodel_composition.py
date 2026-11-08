"""The multi-model composition run: it executes, and the baseline is unchanged.

Three properties are asserted, and the third is the one that matters:

1. the composed graph executes;
2. every instance is attributed to the paper that encodes it;
3. the insulin instance's values are **identical** to the baseline-only run. Only
   the attribution fields differ, because they name the instance.

A fourth property is asserted negatively: a graph that *does* feed one model into
the insulin process is refused by the engine, so "nothing is connected" is an
enforced result rather than a promise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from composition import compatibility
from composition.runner import run_graph

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / "composition" / "replay"
EXAMPLES = ROOT / "composition" / "examples"

BASELINE_GRAPH = "zielinski_replay.json"
COMPOSED_GRAPH = "zielinski_multimodel.json"


def _load(directory: Path, name: str) -> dict:
    return json.loads((directory / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baseline_run() -> dict:
    payload, code = run_graph(_load(REPLAY, BASELINE_GRAPH), base=ROOT)
    assert code == 0, payload.get("diagnostics")
    return payload


@pytest.fixture(scope="module")
def composed_run() -> dict:
    payload, code = run_graph(_load(REPLAY, COMPOSED_GRAPH), base=ROOT)
    assert code == 0, payload.get("diagnostics")
    return payload


def _outputs(payload: dict, instance_id: str) -> dict[str, dict]:
    for result in payload["results"]:
        if result["instance_id"] == instance_id:
            return {out["ref"]["port_id"]: out for out in result["outputs"]}
    raise AssertionError(f"no instance {instance_id!r} in the results")


def _values(outputs: dict[str, dict]) -> dict[str, tuple]:
    """The numeric content of each output, without the fields that name an instance."""
    return {
        port: (item.get("state"), item.get("value"), item.get("unit"),
               item.get("quantity"))
        for port, item in outputs.items()
    }


# --------------------------------------------------------------------------- #
# the graph
# --------------------------------------------------------------------------- #


def test_the_composed_graph_runs_two_independent_instances():
    graph = _load(REPLAY, COMPOSED_GRAPH)
    assert [i["instance_id"] for i in graph["instances"]] == [
        "zielinski_baseline", "ganjave_context"
    ]
    assert graph["connections"] == []
    assert graph["composition_scope"]["dynamic_connections_added"] == 0


def test_the_graph_names_all_seven_assessed_models():
    scope = _load(REPLAY, COMPOSED_GRAPH)["composition_scope"]
    assert set(scope["assessed_models"]) == {a.key for a in compatibility.ASSESSMENTS}


def test_the_graph_declares_the_baseline_and_says_it_is_unchanged():
    scope = _load(REPLAY, COMPOSED_GRAPH)["composition_scope"]
    assert scope["target_model_id"] == compatibility.TARGET_MODEL
    assert "unchanged" in scope["statement"].lower()


def test_no_connection_in_the_composed_graph_names_the_target():
    graph = _load(REPLAY, COMPOSED_GRAPH)
    for connection in graph["connections"]:
        assert connection["source"]["instance_id"] != "zielinski_baseline"
        assert connection["target"]["instance_id"] != "zielinski_baseline"


# --------------------------------------------------------------------------- #
# attribution
# --------------------------------------------------------------------------- #


def test_every_instance_carries_its_paper_and_role(composed_run):
    block = composed_run["composition"]
    instances = {i["instance_id"]: i for i in block["instances"]}
    assert set(instances) == {"zielinski_baseline", "ganjave_context"}

    insulin = instances["zielinski_baseline"]
    assert insulin["paper_folder"] == "Zielinski"
    assert insulin["role"] == "baseline"
    assert insulin["contributes"] is True
    assert insulin["output_count"] > 100
    assert insulin["attributed"] is True

    ganjave = instances["ganjave_context"]
    assert ganjave["paper_folder"] == "Ganjave"
    assert ganjave["role"] == "candidate"
    assert ganjave["contributes"] is False
    assert ganjave["classification"] == "contextually_relevant_not_composable"
    assert ganjave["output_count"] > 0
    assert ganjave["attributed"] is True


def test_the_composition_block_claims_no_link_to_the_target(composed_run):
    block = composed_run["composition"]
    assert block["target"]["model_id"] == compatibility.TARGET_MODEL
    assert [c for c in block["cross_model_links"] if c["touches_target"]] == []
    assert block["note"]


def test_each_instance_output_names_its_own_instance(composed_run):
    for result in composed_run["results"]:
        for out in result["outputs"]:
            assert out["ref"]["instance_id"] == result["instance_id"]


# --------------------------------------------------------------------------- #
# the baseline is numerically unchanged
# --------------------------------------------------------------------------- #


def test_the_insulin_instance_produces_the_same_ports_as_the_baseline(
    baseline_run, composed_run
):
    baseline = _outputs(baseline_run, "zielinski_replay")
    composed = _outputs(composed_run, "zielinski_baseline")
    assert set(baseline) == set(composed)
    assert len(baseline) == 196


def test_the_insulin_values_are_identical_to_the_baseline_run(
    baseline_run, composed_run
):
    baseline = _values(_outputs(baseline_run, "zielinski_replay"))
    composed = _values(_outputs(composed_run, "zielinski_baseline"))
    differing = [port for port in baseline if baseline[port] != composed.get(port)]
    assert differing == [], differing


def test_the_only_difference_between_the_runs_is_attribution(
    baseline_run, composed_run
):
    """Adding an independent instance must not change a value, only a name."""
    baseline = _outputs(baseline_run, "zielinski_replay")
    composed = _outputs(composed_run, "zielinski_baseline")
    port = sorted(baseline)[0]
    changed = {
        key
        for key in baseline[port]
        if baseline[port].get(key) != composed[port].get(key)
    }
    assert changed <= {"ref", "provenance_chain"}
    assert changed, "the instance id should appear somewhere in the attribution"


def test_the_baseline_graph_still_runs_alone(baseline_run):
    assert baseline_run["status"] in {"success", "success_with_warnings"}
    assert len(_outputs(baseline_run, "zielinski_replay")) == 196


# --------------------------------------------------------------------------- #
# a real attempt to connect is refused, so the separation is enforced
# --------------------------------------------------------------------------- #


def test_a_ganjave_to_insulin_connection_is_refused_by_the_engine():
    payload, code = run_graph(
        _load(EXAMPLES, "rejected_cross_model_insulin.json"), base=ROOT
    )
    assert code == 1, "the engine accepted a connection the policy refuses"
    assert payload["status"] == "invalid"
    codes = [
        d["code"] for d in payload["diagnostics"]
        if d.get("severity") == "error"
    ]
    assert codes.count("connection.cross_model_refused") == 3
    # Nothing was executed: an invalid graph produces no results at all.
    assert payload["results"] == []
    refused = [
        d for d in payload["diagnostics"]
        if d["code"] == "connection.cross_model_refused"
    ]
    for diagnostic in refused:
        assert "dimensionally legal" in diagnostic["message"]
        assert diagnostic["remediation"]


def test_the_refused_example_declares_its_three_connections():
    graph = _load(EXAMPLES, "rejected_cross_model_insulin.json")
    assert len(graph["connections"]) == 3
    assert {c["source"]["port_id"] for c in graph["connections"]} == {
        "biomass_concentration", "culture_volume", "simulation_time"
    }


# --------------------------------------------------------------------------- #
# the editor's introspection verb
# --------------------------------------------------------------------------- #


def test_compare_composition_reports_identical_values(capsys):
    from composition.runner import main as runner_main

    code = runner_main(["--compare-composition"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["baseline"]["exit_code"] == 0
    assert payload["composed"]["exit_code"] == 0
    comparison = payload["comparison"]
    assert comparison["identical"] is True
    assert comparison["differing_ports"] == []
    assert comparison["baseline_ports"] == comparison["composed_ports"] == 196
    assert comparison["fields_excluded_as_attribution"] == ["ref", "provenance_chain"]
    assert [i["instance_id"] for i in payload["composition"]["instances"]] == [
        "zielinski_baseline", "ganjave_context"
    ]


def test_compare_runs_detects_a_real_value_difference():
    """The comparison must be able to fail, or 'identical' proves nothing."""

    def payload(instance: str, value: float) -> dict:
        return {
            "results": [
                {
                    "instance_id": instance,
                    "outputs": [
                        {
                            "ref": {"instance_id": instance, "port_id": "p"},
                            "state": "number",
                            "value": value,
                            "unit": "g/L",
                            "quantity": "mass_concentration",
                        }
                    ],
                }
            ]
        }

    same = compatibility.compare_runs(
        payload("a", 1.0), payload("b", 1.0),
        baseline_instance="a", composed_instance="b",
    )
    assert same["identical"] is True

    changed = compatibility.compare_runs(
        payload("a", 1.0), payload("b", 1.0001),
        baseline_instance="a", composed_instance="b",
    )
    assert changed["identical"] is False
    assert changed["differing_ports"] == ["p"]


def test_compare_runs_reports_a_missing_instance_rather_than_passing_silently():
    result = compatibility.compare_runs(
        {"results": []}, {"results": []},
        baseline_instance="a", composed_instance="b",
    )
    assert result["identical"] is False
    assert result["baseline_ports"] == 0


def test_an_individual_model_still_runs_on_its_own_graph():
    """Composition must not be the only way to run a model."""
    payload, code = run_graph(
        _load(EXAMPLES, "ganjave_fed_batch.json"), base=ROOT
    )
    assert code == 0, payload.get("diagnostics")
    assert len(payload["results"]) == 1
    instance = payload["composition"]["instances"][0]
    assert instance["instance_id"] == "ganjave_fed_batch"
    assert instance["paper_folder"] == "Ganjave"
    assert instance["attributed"] is True


def test_describe_compatibility_returns_all_seven(capsys):
    from composition.runner import main as runner_main

    code = runner_main(["--describe-compatibility"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"]["model_id"] == compatibility.TARGET_MODEL
    assert len(payload["assessments"]) == 7
    assert payload["summary"]["assessed"] == 7
    assert payload["connections"]["touching_target"] == []
    assert payload["problems"] == []
    labels = {a["key"]: (a["classification_number"], a["classification_label"])
              for a in payload["assessments"]}
    assert labels["zielinski"][0] == 1
    assert labels["morris"][0] == 4
    assert labels["lin"] == (3, "contextually relevant, not composable")

