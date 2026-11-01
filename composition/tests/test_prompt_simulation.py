"""Prompt-to-Zielinski tests: mapping, clarification and real runner execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from composition import prompt
from composition.runner import run_prompt

ROOT = Path(__file__).resolve().parents[2]

SUPPORTED = (
    "Simulate the Zielinski insulin production process for 19 hours and show "
    "OD600, wet biomass, inclusion bodies and insulin activity."
)


@pytest.fixture(scope="module")
def manifest():
    data, diagnostics = prompt.load_manifest()
    assert data is not None, diagnostics
    return data


def _ports(manifest) -> dict[str, dict]:
    return {port.port_id: port.to_dict() for port in manifest.ports}


def test_supported_prompt_selects_zielinski_and_maps_real_ports(manifest):
    result = prompt.interpret(SUPPORTED, manifest=manifest)
    assert result["ok"] is True
    assert result["selected_model"]["model_id"] == "zielinski2019.rhi_process"
    assert result["selected_model"]["model_version"] == "1.0.0"
    assert result["target_process"]["supported"] is True
    keys = {output["key"] for output in result["requested_outputs"]}
    assert {"od600", "wet_biomass", "inclusion_bodies", "activity"} <= keys
    known = _ports(manifest)
    for output in result["requested_outputs"]:
        assert output["port_ids"], output["key"]
        for port_id in output["port_ids"]:
            assert port_id in known, port_id
    od = next(output for output in result["requested_outputs"] if output["key"] == "od600")
    assert od["kind"] == "trajectory"
    assert len([p for p in od["port_ids"] if "#od600_h" in p]) == 19


def test_supported_parameter_change_maps_to_a_real_input(manifest):
    result = prompt.interpret(
        "Increase the starting medium volume to 8 L and show wet biomass and insulin activity.",
        manifest=manifest,
    )
    assert result["ok"] is True
    changes = result["requested_parameters"]
    assert len(changes) == 1
    change = changes[0]
    assert change["port_id"] == "node:N01#starting_medium_volume"
    assert change["quantity"] == "volume"
    assert change["unit"] == "L"
    assert change["value"] == pytest.approx(8.0)
    key = "zielinski_replay/node:N01#starting_medium_volume"
    assert key in result["configuration"]["literal_inputs"]
    assert result["configuration"]["literal_inputs"][key]["value"] == pytest.approx(8.0)
    assert result["validation"]["ok"] is True


def test_unit_conversion_uses_the_port_unit(manifest):
    result = prompt.interpret(
        "Set the Zielinski starting medium volume to 500 mL and show growth.",
        manifest=manifest,
    )
    assert result["ok"] is True
    change = result["requested_parameters"][0]
    assert change["requested_value"] == pytest.approx(500.0)
    assert change["requested_unit"] == "mL"
    assert change["value"] == pytest.approx(0.5)
    assert change["unit"] == "L"


def test_missing_duration_is_a_clarification_not_an_extrapolation(manifest):
    result = prompt.interpret("Simulate 48 hours of the insulin process.", manifest=manifest)
    assert result["ok"] is False
    assert result["status"] == "needs_clarification"
    codes = [item["code"] for item in result["clarification"]]
    assert "duration_not_available" in codes
    assert result["duration"]["requested_hours"] == pytest.approx(48.0)
    assert result["duration"]["published_max_hours"] == pytest.approx(19.0)


def test_unsupported_process_is_rejected(manifest):
    result = prompt.interpret(
        "Simulate CHO cell insulin production for 48 hours.", manifest=manifest
    )
    assert result["ok"] is False
    assert result["status"] == "rejected"
    assert result["target_process"]["supported"] is False
    assert result["clarification"][0]["code"] == "process_not_supported"


def test_a_bare_ambiguous_parameter_asks_which_port(manifest):
    result = prompt.interpret(
        "Simulate the Zielinski insulin process and change the temperature to 37 C.",
        manifest=manifest,
    )
    assert result["ok"] is False
    assert result["status"] == "needs_clarification"
    assert result["requested_parameters"] == []
    codes = [item["code"] for item in result["clarification"]]
    assert "parameter_ambiguous" in codes
    options = next(
        item["options"] for item in result["clarification"]
        if item["code"] == "parameter_ambiguous"
    )
    assert any("fermenter_temperature" in option for option in options)


def test_a_parameter_without_a_value_asks_for_it(manifest):
    result = prompt.interpret(
        "Change the Zielinski starting medium volume and show growth.",
        manifest=manifest,
    )
    assert result["ok"] is False
    assert result["status"] == "needs_clarification"
    codes = [item["code"] for item in result["clarification"]]
    assert "parameter_value_missing" in codes


def test_incompatible_parameter_unit_is_not_coerced(manifest):
    result = prompt.interpret(
        "Set the starting medium volume to 5 kg and show growth.",
        manifest=manifest,
    )
    assert result["ok"] is False
    assert result["requested_parameters"] == []
    codes = [item["code"] for item in result["clarification"]]
    assert any(
        code in {"parameter_unit_incompatible", "parameter_unit_unrecognised"}
        for code in codes
    )


def test_unavailable_requested_output_is_explained_not_invented(manifest):
    result = prompt.interpret(
        "Simulate the insulin process and show dissolved oxygen.", manifest=manifest
    )
    assert result["ok"] is True
    oxygen = next(
        output for output in result["requested_outputs"]
        if output["key"] == "dissolved_oxygen"
    )
    assert oxygen["available"] is False
    assert oxygen["reason"]
    assert any(
        item["code"] == "output_unavailable"
        for item in result["missing_information"]
    )


def test_build_graph_only_adds_literal_inputs_and_does_not_touch_the_source(manifest):
    source = ROOT / "composition/replay/zielinski_replay.json"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    interpretation = prompt.interpret(
        "Set the starting medium volume to 5 L and show growth.", manifest=manifest
    )
    graph = prompt.build_graph(interpretation)
    validation = prompt.validate_graph(graph, manifest)
    assert validation["ok"] is True
    assert graph["literal_inputs"]
    assert graph["instances"][0]["model_id"] == "zielinski2019.rhi_process"
    assert graph["instances"][0]["parameters"]["execution"]["mode"] == "evidence_replay"
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    assert before == after


def test_the_existing_runner_executes_and_reports_unchanged_baseline():
    payload, code = run_prompt(SUPPORTED)
    assert code == 0
    assert payload["status"] in {"success", "success_with_warnings"}
    assert payload["prompt_interpretation"]["selected_model"]["model_id"] == "zielinski2019.rhi_process"
    effect = payload["prompt_effect"]
    assert effect["identical"] is True
    assert effect["published_outputs_changed"] is False
    assert effect["parameter_change_count"] == 0
    assert payload["results"]

    # The original replay's published values must be numerically unchanged.
    stored = json.loads((ROOT / "assets/zielinski_replay_result.json").read_text(encoding="utf-8"))
    expected = prompt._output_map(stored)
    actual = prompt._output_map(payload)
    assert set(expected) == set(actual)
    assert [
        port for port in expected
        if prompt._signature(expected[port]) != prompt._signature(actual[port])
    ] == []


def test_parameter_change_executes_through_the_existing_runner():
    payload, code = run_prompt(
        "Increase the starting medium volume to 8 L and show wet biomass and insulin activity."
    )
    assert code == 0
    interpretation = payload["prompt_interpretation"]
    assert interpretation["configuration"]["literal_inputs"]
    effect = payload["prompt_effect"]
    assert effect["parameter_change_count"] == 1
    assert effect["identical"] is False
    assert effect["published_outputs_changed"] is True
    assert "node:N02#wet_biomass_g_per_L" in effect["requested_differences"]
    assert "node:N15#batch_activity" in effect["requested_differences"]
    json.dumps(payload)


def test_runner_refuses_a_clarification_without_executing():
    payload, code = run_prompt("Simulate 48 hours of the insulin process.")
    assert code == 3
    assert payload["status"] == "invalid"
    assert payload["results"] == []
    assert payload["prompt_interpretation"]["clarification"][0]["code"] == "duration_not_available"


def test_prompt_payload_has_the_godot_fields():
    payload = prompt.interpret(SUPPORTED)
    for key in (
        "ok", "status", "target_process", "selected_model", "duration",
        "requested_variables", "requested_outputs", "requested_parameters",
        "configuration", "validation", "missing_information", "clarification",
        "assumptions", "warnings",
    ):
        assert key in payload, key
    assert payload["llm_used"] is False
    assert payload["interpretation_method"] == "local_rules"
