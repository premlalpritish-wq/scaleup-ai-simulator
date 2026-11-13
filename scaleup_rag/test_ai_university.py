import json
from pathlib import Path

import pytest

from scaleup_rag.ast_magic_guard import assert_no_magic_numbers, lint_solver_magic_numbers
from scaleup_rag.database import ParameterDatabase
from scaleup_rag.peer_review_gate import PeerReviewCommittee
from scaleup_rag.seed_knowledge import SEED_DOMAIN_SKILLS, SEED_MECHANISTIC_LAWS


def _valid_smr_payload() -> dict:
    return {
        "prompt": "Simulate a 12-unit SMR hydrogen plant at 900 C and 38 bar.",
        "topology_manifest": {
            "domain_id": "thermochemical_plant",
            "derivation_trace": "12-unit SMR flowsheet with Pinch-ordered HEN and intercooled WGS/compression.",
            "units": [{"stage_id": "s1", "tag": "B-101/R-103", "archetype": "furnace_reformer"}],
        },
        "stages": [
            {
                "stage_id": "pre_ref",
                "tag": "R-102",
                "archetype": "pre_reformer",
                "temperature_c": 504.0,
                "pressure_bar": 38.9,
                "flow_nm3_h": 144200.0,
                "steam_to_carbon_ratio": 3.0,
            },
            {
                "stage_id": "smr",
                "tag": "B-101/R-103",
                "archetype": "furnace_reformer",
                "temperature_c": 900.0,
                "pressure_bar": 38.0,
                "flow_nm3_h": 218880.0,
                "flue_in_temp_c": 1010.0,
                "steam_to_carbon_ratio": 3.0,
            },
            {
                "stage_id": "whb",
                "tag": "E-105",
                "archetype": "shell_tube_hx",
                "temperature_c": 340.0,
                "t_hot_in_c": 900.0,
                "t_hot_out_c": 340.0,
                "t_cold_in_c": 240.0,
                "t_cold_out_c": 280.0,
                "pressure_bar": 36.5,
                "flow_nm3_h": 218880.0,
                "thermal_duty_mw": 24.5,
            },
            {
                "stage_id": "hts",
                "tag": "R-104",
                "archetype": "packed_bed_reactor",
                "temperature_c": 420.0,
                "pressure_bar": 35.5,
                "flow_nm3_h": 218880.0,
            },
            {
                "stage_id": "ic",
                "tag": "E-106",
                "archetype": "shell_tube_hx",
                "temperature_c": 210.0,
                "t_hot_in_c": 420.0,
                "t_hot_out_c": 210.0,
                "t_cold_in_c": 110.0,
                "t_cold_out_c": 180.0,
                "pressure_bar": 34.8,
                "flow_nm3_h": 218880.0,
                "thermal_duty_mw": 10.2,
            },
            {
                "stage_id": "lts",
                "tag": "R-105",
                "archetype": "packed_bed_reactor",
                "temperature_c": 235.0,
                "pressure_bar": 34.2,
                "flow_nm3_h": 218880.0,
            },
            {
                "stage_id": "ko",
                "tag": "S-101",
                "archetype": "knockout_cooler",
                "temperature_c": 40.0,
                "pressure_bar": 33.3,
                "flow_nm3_h": 170200.0,
            },
            {
                "stage_id": "psa",
                "tag": "V-101",
                "archetype": "psa_skid",
                "temperature_c": 27.0,
                "pressure_bar": 33.1,
                "flow_nm3_h": 120000.0,
            },
        ],
        "composition_graph": {
            "edges": [
                {"from": "pre_ref", "to": "smr", "stream_type": "process"},
                {"from": "smr", "to": "whb", "stream_type": "process"},
                {"from": "whb", "to": "hts", "stream_type": "process"},
                {"from": "hts", "to": "ic", "stream_type": "process"},
                {"from": "ic", "to": "lts", "stream_type": "process"},
                {"from": "lts", "to": "ko", "stream_type": "process"},
                {"from": "ko", "to": "psa", "stream_type": "process"},
            ]
        },
    }


def test_domain_skills_seed_and_locked_layer_c():
    db = ParameterDatabase(db_url="sqlite:///:memory:")
    for law in SEED_MECHANISTIC_LAWS:
        db.upsert_mechanistic_law(law)
    for sk in SEED_DOMAIN_SKILLS:
        assert db.upsert_domain_skill(sk) is True

    skills = db.list_domain_skills()
    ids = {s.domain_id for s in skills}
    assert {"thermochemical_plant", "bioprocess_kinetics", "electromechanics"}.issubset(ids)

    smr_skill = db.get_domain_skill("thermochemical_plant")
    assert smr_skill is not None
    assert "SECOND_LAW_PINCH" in smr_skill.governing_laws
    assert "furnace_reformer" in smr_skill.allowed_archetypes
    assert len(smr_skill.few_shot_derivations) >= 1

    lock_path = Path("composition/LOCKED_LAYER_C.json")
    assert lock_path.exists()
    lock_cfg = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock_cfg["write_lock_policy"]["subagent_write_access"] == "FORBIDDEN"
    assert "scripts/replay_vessel_view.gd" in lock_cfg["locked_files"]


def test_peer_review_symptom_only_and_flat_bypass_detection():
    # 1. Symptom-only failure (S/C = 1.1 < 2.0) must NOT leak threshold '2.0'
    bad_payload = _valid_smr_payload()
    bad_payload["stages"][1]["sc_ratio"] = 1.1
    committee = PeerReviewCommittee(db_url="sqlite:///:memory:")
    res_bad = committee.evaluate(bad_payload, run_perturbations=False, archive_on_pass=False)
    assert res_bad["status"] == "FAILED"
    assert len(res_bad["symptom_reports"]) >= 1
    for msg in res_bad["symptom_reports"]:
        assert "BOUDOUARD_CARBON_COKING" in msg
        assert "2.0" not in msg

    # 2. Hardcoded flat-output bypass under 3-point perturbation
    def hardcoded_flat_solver(_perturbed: dict) -> dict:
        return _valid_smr_payload()  # ignores perturbation completely

    flat_committee = PeerReviewCommittee(db_url="sqlite:///:memory:", solver_fn=hardcoded_flat_solver)
    res_flat = flat_committee.evaluate(_valid_smr_payload(), run_perturbations=True, archive_on_pass=False)
    assert res_flat["status"] == "FAILED"
    assert res_flat["perturbation_audit"]["flag"] == "HARDCODED_BYPASS_SUSPECTED"
    assert any("HARDCODED_BYPASS_SUSPECTED" in s for s in res_flat["symptom_reports"])


def test_peer_review_passes_and_archives_trace(tmp_path):
    db_file = tmp_path / "test_ai_univ.db"
    db_url = f"sqlite:///{db_file}"
    committee = PeerReviewCommittee(db_url=db_url)
    payload = _valid_smr_payload()
    res = committee.evaluate(payload, run_perturbations=True, archive_on_pass=True)
    assert res["status"] == "PASSED"
    assert res["perturbation_audit"]["flag"] == "RESPONSIVE"
    assert res["trace_archived"] is True

    db = ParameterDatabase(db_url=db_url)
    traces = db.list_validated_traces("thermochemical_plant")
    assert len(traces) == 1
    assert traces[0].perturbation_passed is True


def test_ast_magic_guard_catches_injected_literal_and_passes_locked_compiler(tmp_path):
    bad_solver = tmp_path / "dummy_bad_solver.py"
    bad_solver.write_text(
        "def solve_flux(x):\n"
        "    return x * 42.7 + 1.0\n",
        encoding="utf-8",
    )
    violations = lint_solver_magic_numbers([bad_solver])
    assert len(violations) == 1
    assert violations[0]["value"] == 42.7
    with pytest.raises(AssertionError, match="42.7"):
        assert_no_magic_numbers([bad_solver])

    # Locked RealityCompiler check_* methods must pass with 0 magic number violations
    assert_no_magic_numbers(
        ["composition/composition/workflow/reality_compiler.py"],
        function_names=[
            "check_mass_and_elemental_balance",
            "check_second_law_and_pinch",
            "check_equilibrium_and_adiabatic_ceiling",
            "check_catalyst_and_material_invariants",
            "check_phase_and_equipment_compatibility",
            "check_hydraulic_pressure_gradient",
        ],
    )
