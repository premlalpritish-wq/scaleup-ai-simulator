import pytest
from scaleup_rag import (
    ScaleUpRAGEngine,
    RequiredParameterSpec,
    RawExtractedCandidate,
    OperatingEnvelope,
    seed_database
)
from scaleup_rag.research_client import _strip_xml_tags

FAST_MOCK_PAPERS = [{"doi": "10.1016/mock", "title": "Mock", "abstractText": "Mock"}]
mock_search_fn = lambda q: FAST_MOCK_PAPERS

@pytest.fixture
def rag_engine(tmp_path):
    db_file = tmp_path / "test_scaleup.db"
    return ScaleUpRAGEngine(db_url=f"sqlite:///{db_file}", search_fn=mock_search_fn)

def test_path_1_and_2_writeback_then_cache_hit(rag_engine):
    spec = RequiredParameterSpec(
        entity_name="dynamic_viscosity",
        target_system="Saccharina latissima",
        expected_unit="Pa * s",
        envelope_constraints=OperatingEnvelope(temperature_c=65.0)
    )

    def mock_valid_extractor(s, papers):
        return RawExtractedCandidate(
            entity_name=s.entity_name,
            target_system=s.target_system,
            raw_value=45.0,
            raw_unit="mPa * s",
            envelope=OperatingEnvelope(temperature_c=65.0),
            source_doi="10.1016/j.algal.2023.102931",
            source_snippet="The apparent dynamic viscosity of the Saccharina latissima extract was 45.0 mPa*s at 65 C.",
            extraction_confidence=0.95
        )

    # Run 1: Cache Miss -> Research Extraction -> Pint Conversion (45 mPa*s -> 0.045 Pa*s) -> DB Write-Back
    res1 = rag_engine.resolve_simulation_parameters(
        prompt="Simulate kelp extraction viscosity",
        required_specs=[spec],
        llm_extractor_fn=mock_valid_extractor
    )
    assert res1.writeback_count == 1
    assert res1.cache_hit_count == 0
    assert res1.gap_count == 0
    assert pytest.approx(res1.grounded_parameters["dynamic_viscosity"].value_normalized, 1e-6) == 0.045
    assert res1.grounded_parameters["dynamic_viscosity"].origin == "live_research_writeback"

    # Run 2: Subsequent Query -> Instant Read-Through Cache Hit (extractor not needed)
    res2 = rag_engine.resolve_simulation_parameters(
        prompt="Simulate kelp extraction viscosity again",
        required_specs=[spec],
        llm_extractor_fn=None
    )
    assert res2.cache_hit_count == 1
    assert res2.writeback_count == 0
    assert res2.gap_count == 0
    assert pytest.approx(res2.grounded_parameters["dynamic_viscosity"].value_normalized, 1e-6) == 0.045
    assert res2.grounded_parameters["dynamic_viscosity"].origin == "database_cache_hit"

def test_path_3_quarantine_rejects_wrong_dimensionality(rag_engine):
    spec = RequiredParameterSpec(
        entity_name="dynamic_viscosity",
        target_system="E. coli",
        expected_unit="Pa * s"
    )

    def mock_bad_unit_extractor(s, papers):
        return RawExtractedCandidate(
            entity_name=s.entity_name,
            target_system=s.target_system,
            raw_value=37.0,
            raw_unit="kelvin",  # Wrong physical dimension for viscosity
            source_doi="10.1016/j.biotech.2022.01.005",
            source_snippet="The fermentation broth was maintained at 37.0 K difference during lysis.",
            extraction_confidence=0.80
        )

    res = rag_engine.resolve_simulation_parameters(
        prompt="Simulate E. coli viscosity",
        required_specs=[spec],
        llm_extractor_fn=mock_bad_unit_extractor
    )
    assert res.writeback_count == 0
    assert res.cache_hit_count == 0
    assert res.gap_count == 1
    assert "dynamic_viscosity" in res.parameter_gaps
    assert res.parameter_gaps["dynamic_viscosity"].status == "unverified_hypothesis"

def test_path_4_literature_miss_logs_explicit_gap(rag_engine):
    spec = RequiredParameterSpec(
        entity_name="mass_transfer_kla",
        target_system="Novel synthetic strain X",
        expected_unit="1 / s"
    )

    res = rag_engine.resolve_simulation_parameters(
        prompt="Simulate novel strain kLa",
        required_specs=[spec],
        llm_extractor_fn=lambda s, p: None
    )
    assert res.writeback_count == 0
    assert res.gap_count == 1
    assert res.parameter_gaps["mass_transfer_kla"].status == "unverified_hypothesis"

def test_fulltext_xml_extraction():
    sample_xml = """
    <article>
        <body>
            <sec sec-type="materials|methods">
                <p>The solution was stirred at 300 rpm.</p>
                <table-wrap id="t1">
                    <caption>Table 1: Viscosity results</caption>
                    <table><tr><td>Viscosity: 0.05 Pa s</td></tr></table>
                </table-wrap>
            </sec>
        </body>
    </article>
    """
    extracted = _strip_xml_tags(sample_xml)
    assert "Table 1: Viscosity results" in extracted
    assert "The solution was stirred at 300 rpm." in extracted
    assert "<table-wrap" not in extracted
    assert "<body>" not in extracted

def test_run_from_prompt_with_mocks(rag_engine, monkeypatch):
    def mock_decompose(prompt):
        return [
            RequiredParameterSpec(
                entity_name="growth_rate_mu_max",
                target_system="E. coli",
                expected_unit="1 / hr"
            )
        ]

    def mock_extractor(spec, papers):
        return RawExtractedCandidate(
            entity_name=spec.entity_name,
            target_system=spec.target_system,
            raw_value=0.65,
            raw_unit="1 / hr",
            source_doi="10.1000/ecoli.growth",
            source_snippet="The maximum specific growth rate mu_max was determined to be 0.65 1/hr under aerobic conditions.",
            extraction_confidence=0.98
        )

    manifest = rag_engine.run_from_prompt(
        "Simulate E. coli growth in bioreactor",
        llm_extractor_fn=mock_extractor,
        decomposer_fn=mock_decompose
    )
    assert manifest.writeback_count == 1
    assert "growth_rate_mu_max" in manifest.grounded_parameters
    assert manifest.grounded_parameters["growth_rate_mu_max"].value_normalized == 0.65

def test_seed_knowledge_idempotent(tmp_path):
    db_file = tmp_path / "test_seeding.db"
    db_url = f"sqlite:///{db_file}"

    # First seeding run: 66 valid items should pass (57 Tier 1 + 9 Tier 0), 65 unique newly written, 2 rejected
    rep1 = seed_database(db_url=db_url)
    assert rep1["total_evaluated"] == 68
    assert rep1["passed_quarantine"] == 66
    assert rep1["tier_counts"]["tier_1_quarantine"] == 57
    assert rep1["tier_counts"]["tier_0_internal_bench"] == 9
    assert rep1["rejected_by_quarantine"] == 2
    assert rep1["newly_written_to_db"] == 65

    # Second seeding run: idempotent, newly written should be 0
    rep2 = seed_database(db_url=db_url)
    assert rep2["total_evaluated"] == 68
    assert rep2["passed_quarantine"] == 66
    assert rep2["rejected_by_quarantine"] == 2
    assert rep2["newly_written_to_db"] == 0

    # Verify lookups from seeded database
    engine = ScaleUpRAGEngine(db_url=db_url, search_fn=mock_search_fn)
    spec = RequiredParameterSpec(
        entity_name="alginate_extraction_yield",
        target_system="Saccharina latissima",
        expected_unit="dimensionless"
    )
    res = engine.resolve_simulation_parameters(
        prompt="Lookup seeded alginate yield",
        required_specs=[spec],
        llm_extractor_fn=None
    )
    assert res.cache_hit_count == 1
    assert res.grounded_parameters["alginate_extraction_yield"].value_normalized == 0.33
    assert res.grounded_parameters["alginate_extraction_yield"].source_doi == "10.1016/j.algal.2020.101956"

def test_solver_bridge_end_to_end(tmp_path):
    from scaleup_rag.solver_bridge import run_grounded_simulation

    db_file = tmp_path / "test_sim.db"
    db_url = f"sqlite:///{db_file}"
    seed_database(db_url=db_url)

    engine = ScaleUpRAGEngine(db_url=db_url, search_fn=mock_search_fn)
    out_file = tmp_path / "rag_simulation_run.json"

    result = run_grounded_simulation(
        prompt="Simulate E. coli fed-batch fermentation with 500 g/L glucose feed at 37 C",
        system_type="ecoli_fed_batch",
        output_artifact_path=str(out_file),
        engine=engine,
    )

    assert result["status"] == "COMPLETED"
    assert out_file.exists()

    # Trajectory validation
    trajectories = result["trajectories"]
    assert "time_hours" in trajectories
    assert "biomass_g_per_L" in trajectories
    assert "glucose_g_per_L" in trajectories
    assert "volume_L" in trajectories
    assert len(trajectories["time_hours"]) == 41
    assert trajectories["time_hours"][0] == 0.0
    assert trajectories["time_hours"][-1] == 20.0
    assert trajectories["biomass_g_per_L"][-1] > trajectories["biomass_g_per_L"][0]

    # Epistemic audit validation
    audit = result["_epistemic_audit"]
    assert "grounded_parameters" in audit
    assert "user_design_setpoints" in audit
    assert "unverified_assumptions" in audit
    assert "feed_glucose_concentration" in audit["user_design_setpoints"]
    assert audit["user_design_setpoints"]["feed_glucose_concentration"]["user_override_value"] == 500.0
    assert audit["user_design_setpoints"]["temperature_c"]["user_override_value"] == 37.0
    assert len(audit["grounded_parameters"]) >= 5

    # 3D Scene Assembly validation
    assert "scene_assembly" in result
    scene = result["scene_assembly"]
    assert "components" in scene
    comps = scene["components"]
    for expected_c in [
        "bioreactor_vessel",
        "rushton_impeller_assembly",
        "ring_sparger_and_bubbles",
        "glucose_feed_pump_and_inlet",
        "thermal_jacket_and_probes"
    ]:
        assert expected_c in comps
        assert "governing_equations" in comps[expected_c]
        assert "epistemic_payload" in comps[expected_c]

def test_server_and_workbench_endpoints():
    import httpx
    from scaleup_rag.server import start_server

    # Start server in background thread
    server = start_server(port=8123, open_browser=False, block=False)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with httpx.Client(timeout=5.0) as client:
            # 1. Health check
            r_health = client.get(f"{base_url}/api/health")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "ok"

            # 2. HTML workbench
            r_wb = client.get(f"{base_url}/rag_workbench.html")
            assert r_wb.status_code == 200
            assert "ScaleUp AI" in r_wb.text
            assert "bioreactor_vessel" in r_wb.text
    finally:
        server.shutdown()
        server.server_close()


def test_range_regex_extraction_and_envelope():
    from scaleup_rag.llm_bridge import _extract_via_regex
    from scaleup_rag.quarantine_gate import validate_and_convert_candidate

    spec = RequiredParameterSpec(
        entity_name="specific_growth_rate_mu_max",
        target_system="Escherichia coli",
        expected_unit="1 / hour",
    )
    papers = [
        {
            "doi": "10.1016/j.biotech.2024.001",
            "title": "E. coli growth envelope",
            "abstractText": "The specific growth rate ranged from 0.42 to 0.58 h-1 at 37 \u00b0C and pH 7.0 in minimal medium.",
        }
    ]
    cand = _extract_via_regex(spec, papers)
    assert cand is not None
    assert pytest.approx(cand.raw_value_min, 1e-6) == 0.42
    assert pytest.approx(cand.raw_value_max, 1e-6) == 0.58
    assert pytest.approx(cand.raw_value, 1e-6) == 0.50
    assert cand.envelope.temperature_c == 37.0
    assert cand.envelope.ph == 7.0

    grounded = validate_and_convert_candidate(cand, spec)
    assert grounded is not None
    assert pytest.approx(grounded.value_min, 1e-6) == 0.42
    assert pytest.approx(grounded.value_max, 1e-6) == 0.58
    assert pytest.approx(grounded.value, 1e-6) == 0.50
    assert grounded.envelope.temperature_c == 37.0
    assert grounded.envelope.ph == 7.0


def test_plus_minus_extraction_and_envelope():
    from scaleup_rag.llm_bridge import _extract_via_regex
    from scaleup_rag.quarantine_gate import validate_and_convert_candidate

    spec = RequiredParameterSpec(
        entity_name="specific_growth_rate_mu_max",
        target_system="Escherichia coli",
        expected_unit="1 / hour",
    )
    papers = [
        {
            "doi": "10.1016/j.biotech.2024.002",
            "title": "E. coli growth uncertainty",
            "abstractText": "Maximum specific growth rate was 0.50 \u00b1 0.08 1/h at 30 \u00b0C during exponential phase.",
        }
    ]
    cand = _extract_via_regex(spec, papers)
    assert cand is not None
    assert pytest.approx(cand.raw_value_min, 1e-6) == 0.42
    assert pytest.approx(cand.raw_value_max, 1e-6) == 0.58
    assert pytest.approx(cand.raw_value, 1e-6) == 0.50
    assert cand.envelope.temperature_c == 30.0

    grounded = validate_and_convert_candidate(cand, spec)
    assert grounded is not None
    assert pytest.approx(grounded.value_min, 1e-6) == 0.42
    assert pytest.approx(grounded.value_max, 1e-6) == 0.58
    assert pytest.approx(grounded.value, 1e-6) == 0.50
    assert grounded.envelope.temperature_c == 30.0


def test_sqlite_range_and_envelope_roundtrip(tmp_path):
    from scaleup_rag.database import ParameterDatabase
    from scaleup_rag.quarantine_gate import validate_and_convert_candidate

    db_file = tmp_path / "test_range_roundtrip.db"
    db = ParameterDatabase(db_url=f"sqlite:///{db_file}")

    spec = RequiredParameterSpec(
        entity_name="smr_operating_pressure",
        target_system="SMR Hydrogen Plant",
        expected_unit="bar",
    )
    cand = RawExtractedCandidate(
        entity_name="smr_operating_pressure",
        target_system="SMR Hydrogen Plant",
        raw_value=28.0,
        raw_value_min=20.0,
        raw_value_max=35.0,
        raw_unit="bar",
        envelope=OperatingEnvelope(temperature_c=850.0, ph=None, pressure_bar=28.0),
        source_doi="10.1016/j.ijhydene.2024.101",
        source_snippet="Industrial SMR reformers operate at 28.0 bar (range 20.0-35.0 bar) and 850 °C.",
        extraction_confidence=0.96,
    )
    grounded = validate_and_convert_candidate(cand, spec)
    assert grounded is not None
    db.store_grounded_parameter(grounded)

    loaded = db.lookup_parameter(spec)
    assert loaded is not None
    assert pytest.approx(loaded.value, 1e-6) == 28.0
    assert pytest.approx(loaded.value_min, 1e-6) == 20.0
    assert pytest.approx(loaded.value_max, 1e-6) == 35.0
    assert loaded.envelope.temperature_c == 850.0
    assert loaded.envelope.pressure_bar == 28.0


def test_blind_50_parameter_audit_gate():
    from scaleup_rag.benchmark_blind_audit import run_blind_50_audit

    res = run_blind_50_audit(write_artifacts=False)
    s = res["summary"]
    assert s["total_cases"] == 50
    assert s["quarantine_precision"] == 1.0
    assert s["adversarial_block_rate"] == 1.0
    assert s["extraction_conversion_recall"] >= 0.95
    assert s["range_bound_accuracy"] >= 0.95
    assert s["operating_envelope_completeness"] >= 0.95

