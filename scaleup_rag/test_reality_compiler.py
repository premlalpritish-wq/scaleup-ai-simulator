"""Adversarial & End-to-End Tests for the First-Principles Reality Compiler."""

from __future__ import annotations

import pytest

from composition.composition.workflow.reality_compiler import (
    PhysicsCompilationError,
    RealityCompiler,
)
from composition.composition.workflow.skill_research_bridge import (
    _solve_smr_plant_trajectories,
    extract_dynamic_stages_from_prompt,
    synthesize_heat_integration_network,
)
from scaleup_rag.database import ParameterDatabase
from scaleup_rag.seed_knowledge import SEED_MECHANISTIC_LAWS, seed_database


def test_seed_mechanistic_laws_into_sqlite():
    report = seed_database(db_url="sqlite:///:memory:", include_workspace_json=False)
    assert report["mechanistic_laws_total"] == len(SEED_MECHANISTIC_LAWS)
    assert report["mechanistic_laws_newly_written"] == len(SEED_MECHANISTIC_LAWS)

    db = ParameterDatabase(db_url="sqlite:///:memory:")
    for law in SEED_MECHANISTIC_LAWS:
        db.upsert_mechanistic_law(law)
    laws = db.list_mechanistic_laws()
    law_ids = {l.law_id for l in laws}
    assert "SECOND_LAW_PINCH" in law_ids
    assert "POLYTROPIC_COMPRESSION_DISCHARGE" in law_ids
    assert "PASSIVE_PRESSURE_DROP_MONOTONICITY" in law_ids


def test_lumped_smr_cooler_bug_raises():
    payload = {
        "stages": [
            {"stage_id": "s1", "tag": "B-101/R-103", "archetype": "furnace_reformer", "temperature_c": 900.0, "pressure_bar": 38.0},
            {"stage_id": "s2", "tag": "E-LUMP", "archetype": "shell_tube_hx", "temperature_c": 40.0, "pressure_bar": 36.0, "t_hot_in_c": 900.0, "t_hot_out_c": 40.0},
        ],
        "composition_graph": {"edges": [{"from": "s1", "to": "s2", "stream_type": "process"}]},
    }
    with pytest.raises(PhysicsCompilationError) as exc_info:
        RealityCompiler().verify_strict(payload)
    assert any(v["law_id"] == "SINGLE_SHELL_THERMAL_SHOCK" for v in exc_info.value.violations)


def test_backwards_convection_coil_pinch_bug_raises():
    payload = {
        "stages": [
            {
                "stage_id": "s1",
                "tag": "B-101/R-103",
                "archetype": "furnace_reformer",
                "temperature_c": 900.0,
                "pressure_bar": 38.0,
                "convection_banks": [
                    {
                        "tag": "E-104",
                        "duty_mw": 9.0,
                        "t_hot_in_c": 270.0,
                        "t_hot_out_c": 130.0,
                        "t_cold_in_c": 25.0,
                        "t_cold_out_c": 220.0,
                    },
                    {
                        "tag": "E-109",
                        "duty_mw": 10.0,
                        "t_hot_in_c": 130.0,
                        "t_hot_out_c": 90.0,
                        "t_cold_in_c": 25.0,
                        "t_cold_out_c": 400.0,
                    },
                ],
            }
        ],
        "composition_graph": {"edges": []},
    }
    with pytest.raises(PhysicsCompilationError) as exc_info:
        RealityCompiler().verify_strict(payload)
    assert any(v["law_id"] == "SECOND_LAW_TEMPERATURE_CROSS" for v in exc_info.value.violations)


def test_single_bed_adiabatic_exothermic_shift_bug_raises():
    payload = {
        "stages": [
            {
                "stage_id": "s1",
                "tag": "R-104",
                "archetype": "packed_bed_reactor",
                "title": "Single-Bed WGS (12% CO to 0.3% CO)",
                "description": "Adiabatic WGS converting 12% CO to 0.3% CO in one bed.",
                "temperature_c": 380.0,
                "pressure_bar": 35.0,
                "co_in_pct": 12.0,
                "co_out_pct": 0.3,
            }
        ],
        "composition_graph": {"edges": []},
    }
    with pytest.raises(PhysicsCompilationError) as exc_info:
        RealityCompiler().verify_strict(payload)
    assert any(v["law_id"] == "VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM" for v in exc_info.value.violations)


def test_unintercooled_compressor_bug_raises():
    payload = {
        "stages": [
            {"stage_id": "s1", "tag": "V-101", "archetype": "psa_skid", "temperature_c": 27.0, "pressure_bar": 33.1},
            {"stage_id": "s0", "tag": "S-101", "archetype": "knockout_cooler", "temperature_c": 27.0, "pressure_bar": 33.2},
            {"stage_id": "s2", "tag": "C-101", "archetype": "high_pressure_compressor", "temperature_c": 50.0, "pressure_bar": 400.0, "p_in_bar": 33.1},
        ],
        "composition_graph": {"edges": []},
    }
    # Put S-101 before V-101 so only POLYTROPIC_COMPRESSION_DISCHARGE triggers
    payload["stages"] = [payload["stages"][1], payload["stages"][0], payload["stages"][2]]
    with pytest.raises(PhysicsCompilationError) as exc_info:
        RealityCompiler().verify_strict(payload)
    assert any(v["law_id"] == "POLYTROPIC_COMPRESSION_DISCHARGE" for v in exc_info.value.violations)


def test_wet_gas_into_psa_bug_raises():
    payload = {
        "stages": [
            {"stage_id": "s1", "tag": "R-105", "archetype": "packed_bed_reactor", "temperature_c": 210.0, "pressure_bar": 34.5},
            {"stage_id": "s2", "tag": "V-101", "archetype": "psa_skid", "temperature_c": 27.0, "pressure_bar": 33.1},
        ],
        "composition_graph": {"edges": [{"from": "s1", "to": "s2", "stream_type": "process"}]},
    }
    with pytest.raises(PhysicsCompilationError) as exc_info:
        RealityCompiler().verify_strict(payload)
    assert any(v["law_id"] == "WET_GAS_PSA_KNOCKOUT" for v in exc_info.value.violations)


def test_pressure_backflow_bug_raises():
    payload = {
        "stages": [
            {"stage_id": "s1", "tag": "E-105", "archetype": "shell_tube_hx", "temperature_c": 350.0, "pressure_bar": 25.0},
            {"stage_id": "s2", "tag": "R-104", "archetype": "packed_bed_reactor", "temperature_c": 380.0, "pressure_bar": 38.0},
        ],
        "composition_graph": {"edges": [{"from": "s1", "to": "s2", "stream_type": "process"}]},
    }
    with pytest.raises(PhysicsCompilationError) as exc_info:
        RealityCompiler().verify_strict(payload)
    assert any(v["law_id"] == "PASSIVE_PRESSURE_DROP_MONOTONICITY" for v in exc_info.value.violations)


def test_validated_smr_and_methanol_flows_pass_all_6_gates():
    for prompt in (
        "Design a 120,000 Nm3/h SMR hydrogen production plant with HDS R-101, Pre-Reformer R-102, 1010 C flue gas convection recovery, dual-stage WGS, PSA V-101, and 400 bar H2 compression",
        "(1) Fired Reformer Syngas Heater at 820 C, 30 bar, (2) Multi-bed Methanol Synthesis Converter at 260 C and 220 C, (3) Flash Knockout Separator at 40 C, (4) Recycle Syngas Compressor to 180 bar",
    ):
        stages = extract_dynamic_stages_from_prompt(prompt)
        _solve_smr_plant_trajectories(prompt, stages, None)
        units, _, conns, _ = synthesize_heat_integration_network(stages)
        payload = {"stages": units, "composition_graph": {"edges": conns}}
        audit = RealityCompiler().compile_and_verify(payload, strict=True)
        assert audit["status"] == "PASSED"
        assert audit["laws_checked"] == 6
        assert audit["violations"] == []
