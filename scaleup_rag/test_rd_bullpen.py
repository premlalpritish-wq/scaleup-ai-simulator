import json
from pathlib import Path

import pytest

from scaleup_rag.database import ParameterDatabase
from scaleup_rag.rd_bullpen import run_bullpen_review, sanitize_for_public_export
from scaleup_rag.seed_knowledge import SEED_AGENT_PROFILES, SEED_DOMAIN_SKILLS, SEED_MECHANISTIC_LAWS
from scaleup_rag.test_ai_university import _valid_smr_payload


def _seed_memory_db(tmp_path: Path) -> str:
    db_url = f"sqlite:///{tmp_path / 'bullpen_test.db'}"
    db = ParameterDatabase(db_url=db_url)
    for law in SEED_MECHANISTIC_LAWS:
        db.upsert_mechanistic_law(law)
    for sk in SEED_DOMAIN_SKILLS:
        db.upsert_domain_skill(sk)
    for prof in SEED_AGENT_PROFILES:
        db.upsert_agent_profile(prof)
    return db_url


def test_four_personas_load_and_link_to_domain_skills(tmp_path):
    db_url = _seed_memory_db(tmp_path)
    db = ParameterDatabase(db_url=db_url)
    profiles = db.list_agent_profiles()
    assert len(profiles) == 4
    by_id = {p.persona_id: p for p in profiles}
    assert set(by_id.keys()) == {"elmer_gaden", "octave_levenspiel", "nikola_tesla", "richard_feynman"}
    assert by_id["richard_feynman"].is_proctor is True
    assert by_id["octave_levenspiel"].public_engine_alias == "ScaleUp Thermochemical Process Engine"

    for p in profiles:
        assert Path(p.lens_markdown_path).exists(), f"Missing lens file: {p.lens_markdown_path}"
        linked_skill = db.get_domain_skill(p.linked_domain_skill_id)
        assert linked_skill is not None


def test_bullpen_round_2_hard_stop_reclassifies_ungrounded_params(tmp_path):
    db_url = _seed_memory_db(tmp_path)
    payload = _valid_smr_payload()
    payload["grounded_parameters"] = {
        "smr_reaction_enthalpy": {
            "value": 206.0,
            "unit": "kJ/mol",
            "source_doi": "10.1016/j.ijhydene.2010.04.093",
            "verbatim_quote": "Steam methane reforming enthalpy is 206 kJ/mol.",
        },
        "guessed_catalyst_pore_tortuosity": {
            "value": 3.4,
            "unit": "dimensionless",
            "source_doi": "",  # missing DOI -> Richard Feynman proctor must flag
        },
    }

    bundle = run_bullpen_review(payload, primary_persona_id="octave_levenspiel", db_url=db_url)
    trace = bundle["bullpen_trace"]
    assert trace["rounds_executed"] == 2
    assert trace["hard_stop_enforced"] is True
    assert any(c["target_field"] == "guessed_catalyst_pore_tortuosity" and c["resolved"] for c in trace["critiques"])

    locked = bundle["manifest_payload"]
    assert "guessed_catalyst_pore_tortuosity" not in locked["grounded_parameters"]
    assert "guessed_catalyst_pore_tortuosity" in locked["epistemic_audit"]["unverified_assumptions"]
    assert bundle["peer_review_audit"]["status"] == "PASSED"


def test_sanitize_for_public_export_strips_personas_and_preserves_dois(tmp_path):
    db_url = _seed_memory_db(tmp_path)
    payload = _valid_smr_payload()
    payload["grounded_parameters"] = {
        "smr_reaction_enthalpy": {
            "value": 206.0,
            "unit": "kJ/mol",
            "source_doi": "10.1016/j.ijhydene.2010.04.093",
            "verbatim_quote": "Cited by Octave Levenspiel in classic chemical reaction engineering.",
        }
    }
    bundle = run_bullpen_review(payload, primary_persona_id="octave_levenspiel", db_url=db_url)
    public_doc = sanitize_for_public_export(bundle)

    assert "bullpen_trace" not in public_doc
    assert "critiques" not in public_doc
    assert public_doc["engine_attribution"] == "ScaleUp Thermochemical Process Engine"
    assert public_doc["grounded_parameters"]["smr_reaction_enthalpy"]["source_doi"] == "10.1016/j.ijhydene.2010.04.093"

    serialized = json.dumps(public_doc)
    assert "richard_feynman" not in serialized
    assert "octave_levenspiel" not in serialized

    # Verify leakage guard rejects accidental persona name in non-quote field
    leaky_bundle = {"manifest_payload": {"prompt": "Audited by Richard Feynman"}, "public_engine_alias": "ScaleUp Engine"}
    with pytest.raises(ValueError, match="Persona leakage"):
        sanitize_for_public_export(leaky_bundle)


def test_anti_gaming_elo_updates_reflect_physics_and_grounding(tmp_path):
    db_url = _seed_memory_db(tmp_path)
    db = ParameterDatabase(db_url=db_url)

    # 1. Physics pass + 100% grounding ratio -> Elo increases
    elo_up = db.update_persona_elo("octave_levenspiel", physics_passed=True, grounding_ratio=1.0, perturbation_responsive=True)
    assert elo_up > 1200.0

    # 2. Physics failure -> Elo drops sharply
    elo_down = db.update_persona_elo("elmer_gaden", physics_passed=False, grounding_ratio=0.5, perturbation_responsive=True)
    assert elo_down < 1200.0

    # 3. Lazy over-abstention penalty reduces reward
    elo_lazy = db.update_persona_elo(
        "nikola_tesla",
        physics_passed=True,
        grounding_ratio=0.2,
        perturbation_responsive=True,
        lazy_abstention_count=3,
    )
    assert elo_lazy < 1200.0


def test_pioneer_toolkits_and_feynman_fermi_flux():
    from scaleup_rag.personas.toolkits import (
        FeynmanProctorToolkit,
        GadenToolkit,
        LevenspielToolkit,
        TeslaToolkit,
    )

    lev = LevenspielToolkit().diagnose_manifest({
        "stages": [
            {"tag": "R-104", "archetype": "packed_bed_reactor", "temperature_c": 370.0, "sizing": {"u_superficial_m_s": 0.4}},
        ],
        "hen_summary": {"pinch_min_approach_c": 12.0},
    })
    assert lev["toolkit"] == "LevenspielToolkit"
    assert "adiabatic_equilibrium" in lev
    assert "catalyst_diffusion" in lev
    assert "pinch_composite" in lev

    gad = GadenToolkit().diagnose_manifest({
        "stages": [
            {"tag": "BIO-1", "archetype": "stirred_tank_bioreactor", "temperature_c": 37.0, "sizing": {"volume_m3": 10.0, "power_kw": 25.0}},
        ],
    })
    assert gad["toolkit"] == "GadenToolkit"
    assert "scaleup_audit" in gad

    tes = TeslaToolkit().diagnose_manifest({
        "stages": [
            {"tag": "C-101", "archetype": "high_pressure_compressor", "temperature_c": 140.0, "sizing": {"power_kw": 500.0}},
        ],
    })
    assert tes["toolkit"] == "TeslaToolkit"
    assert "electromechanical_transients" in tes

    # FeynmanProctorToolkit catches Fermi heat-flux anomaly q'' > 150 kW/m2
    feyn = FeynmanProctorToolkit().run_asymptotic_and_flux_audit({
        "stages": [
            {
                "tag": "E-999",
                "archetype": "shell_tube_hx",
                "temperature_c": 300.0,
                "pressure_bar": 30.0,
                "thermal_duty_mw": 10.0,  # 10,000 kW / 20 m2 = 500 kW/m2 > 150
                "sizing": {"area_req_m2": 20.0},
            }
        ]
    })
    assert feyn["passed"] is False
    assert any(a["code"] == "FERMI_HEAT_FLUX_EXCEEDED" and a["unit_tag"] == "E-999" for a in feyn["anomalies"])


def test_bullpen_persists_and_reloads_episodic_memory(tmp_path):
    from scaleup_rag.database import ParameterDatabase
    from scaleup_rag.seed_knowledge import seed_database

    db_url = f"sqlite:///{tmp_path / 'bullpen_mem.db'}"
    seed_database(db_url=db_url, include_workspace_json=False)

    manifest = {
        "prompt": "Simulate SMR syngas cooling.",
        "stages": [
            {
                "tag": "E-999",
                "archetype": "shell_tube_hx",
                "temperature_c": 350.0,
                "pressure_bar": 35.0,
                "thermal_duty_mw": 10.0,
                "sizing": {"area_req_m2": 20.0},
            }
        ],
        "grounded_parameters": {
            "bogus_param": {"value": 1.0, "unit": "dimensionless"}  # missing source_doi -> triggers critique
        },
        "trajectories": {"t": [0.0, 1.0], "y": [1.0, 2.0]},
    }

    res1 = run_bullpen_review(manifest, primary_persona_id="octave_levenspiel", db_url=db_url)
    learned = res1["bullpen_trace"]["episodic_memories_learned"]
    assert len(learned) >= 1
    assert res1["bullpen_trace"]["toolkit_diagnostics"]["toolkit"] == "LevenspielToolkit"
    assert res1["bullpen_trace"]["feynman_proctor_audit"]["passed"] is False

    # Verify DB persistence directly and reload on second wake-up
    db = ParameterDatabase(db_url=db_url)
    mems = db.list_episodic_memories(persona_id="octave_levenspiel")
    assert any(m.memory_id in learned for m in mems)

    res2 = run_bullpen_review(manifest, primary_persona_id="octave_levenspiel", db_url=db_url)
    loaded = res2["bullpen_trace"]["episodic_memories_loaded"]
    assert any(mid in loaded for mid in learned)
    # Public export must still strip all internal persona & episodic traces
    pub = sanitize_for_public_export(res2)
    assert "bullpen_trace" not in pub
