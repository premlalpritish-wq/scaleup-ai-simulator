from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))
import app


def default_graph():
    import json
    return json.loads((ROOT / "composition/examples/ganjave_fed_batch.json").read_text(encoding="utf-8"))


def test_registry_and_contracts_are_project_backed():
    ids = {model["model_id"] for model in app.known_models()}
    assert {"ganjave", "morris2011.material_balance", "zielinski2019.rhi_process"} <= ids
    contract, code = app.describe_model("ganjave@0.1.0", base=ROOT)
    assert code == 0
    assert contract["manifest"]["model_id"] == "ganjave"
    assert contract["manifest"]["model_version"] == "0.1.0"


def test_compatibility_and_related_research_use_engine_context():
    connections = app.cross_model.describe()
    assert connections
    context, code = app.cross_paper.context_for("ganjave@0.1.0", base=ROOT)
    assert code == 0
    assert context.get("model") or context.get("focus_model") or context.get("related_models")


def test_rejects_bad_shape_and_resource_excess_before_runner():
    with pytest.raises(app.ApiError) as bad:
        app._graph_from_request({"graph": {"instances": None}})
    assert bad.value.code == "invalid_graph_shape"
    graph = default_graph()
    graph["instances"][0]["parameters"]["simulation"]["duration_h"] = 49
    with pytest.raises(app.ApiError) as large:
        app._graph_from_request({"graph": graph})
    assert large.value.code == "duration_limit"
    graph = default_graph()
    graph["instances"][0]["parameters"]["simulation"]["solver"]["max_steps"] = 200001
    with pytest.raises(app.ApiError) as too_many_steps:
        app._graph_from_request({"graph": graph})
    assert too_many_steps.value.code == "solver_limit"
    graph["instances"][0]["parameters"]["simulation"]["solver"]["max_steps"] = 1.5
    with pytest.raises(app.ApiError) as fractional_steps:
        app._graph_from_request({"graph": graph})
    assert fractional_steps.value.code == "solver_limit"
    with pytest.raises(app.ApiError) as nonfinite:
        app._graph_from_request({"graph": {"instances": [], "connections": [], "literal_inputs": {"x": {"value": float("inf")}}}})
    assert nonfinite.value.code == "non_finite_number"


def test_rejects_unknown_model_and_arbitrary_execution_fields():
    graph = default_graph()
    graph["instances"][0]["model_id"] = "evil.module:run"
    with pytest.raises(app.ApiError) as exc:
        app._graph_from_request({"graph": graph})
    assert exc.value.status == 400
    assert graph["instances"][0]["model_id"] not in {model["model_id"] for model in app.known_models()}


def test_live_run_returns_computed_quantities_provenance_and_validation():
    graph = default_graph()
    result, code = app.run_graph(graph, base=ROOT)
    payload = app._execution_payload("test-run", graph, result, code)
    assert payload["execution_status"] == "completed"
    assert payload["result_kind"] == "computed"
    assert payload["model_versions"]["ganjave_fed_batch"] == "0.1.0"
    assert payload["time_axis"]["unit"] == "h"
    assert payload["trajectories"]["ganjave_fed_batch/culture_volume"]["unit"] == "L"
    assert payload["trajectories"]["ganjave_fed_batch/biomass_concentration"]["unit"] == "g/L"
    assert payload["trajectories"]["ganjave_fed_batch/dissolved_oxygen"]["unit"] == "%"
    assert payload["provenance"]
    assert payload["composition_report"]
    assert payload["scientific_validation_status"]["execution_success"] is True
    assert payload["scientific_validation_status"]["models"]["ganjave_fed_batch"]["reproduction_status"] == "not_yet_validated"


def test_failed_run_is_not_computed_or_reused():
    graph = default_graph()
    graph["literal_inputs"].clear()
    result, code = app.run_graph(graph, base=ROOT)
    payload = app._execution_payload("failed-run", graph, result, code)
    assert payload["execution_status"] == "failed"
    assert payload["result_kind"] == "none"
    assert payload["trajectories"] == {}


def test_solver_step_budget_failure_is_returned_without_a_trajectory():
    graph = default_graph()
    graph["instances"][0]["parameters"]["simulation"]["solver"]["max_steps"] = 1
    result, code = app.run_graph(graph, base=ROOT)
    payload = app._execution_payload("budget-run", graph, result, code)
    assert payload["execution_status"] == "failed"
    assert payload["result_kind"] == "none"
    assert payload["trajectories"] == {}
    assert any(item["code"] == "execution.model_failed" for item in payload["diagnostics"])
    solver_report = payload["result"]["results"][0]["raw_summary"]["solver_report"]
    assert solver_report["steps_taken"] == 1
    requested_duration = graph["instances"][0]["parameters"]["simulation"]["duration_h"]
    assert solver_report["reached_time_h"] < requested_duration


def test_response_redacts_server_paths_and_tracebacks():
    value = {"traceback": "private", "package": str(ROOT), "message": str(ROOT / "Models")}
    public = app._public(value)
    assert "traceback" not in public and "package" not in public
    assert str(ROOT) not in public["message"]


def test_rate_limit_uses_proxy_client_ip_only_when_trusted():
    forwarded = "203.0.113.42, 10.0.0.4"
    assert app._client_key("127.0.0.1", forwarded) == "127.0.0.1"
    assert app._client_key("127.0.0.1", forwarded, trust_proxy=True) == "203.0.113.42"
