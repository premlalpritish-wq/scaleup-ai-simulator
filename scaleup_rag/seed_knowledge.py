import os
import re
import json
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from .schemas import (
    DomainSkillSpec,
    InternalPersonaProfile,
    RawExtractedCandidate,
    RequiredParameterSpec,
    OperatingEnvelope,
    PhysicalInvariantSpec,
)
from .quarantine_gate import validate_and_normalize, ureg
from .database import ParameterDatabase
from .research_client import extract_operating_envelope

SEED_CANDIDATES: List[Tuple[RawExtractedCandidate, RequiredParameterSpec]] = [
    # Kelp Alginate Extraction Yield (Peteiro et al. 2020)
    (
        RawExtractedCandidate(
            entity_name="alginate_extraction_yield",
            target_system="Saccharina latissima",
            raw_value=0.33,
            raw_unit="dimensionless",
            envelope=OperatingEnvelope(temperature_c=20.0, ph=7.0),
            source_doi="10.1016/j.algal.2020.101956",
            source_snippet="The total alginate extraction yield from Saccharina latissima was 0.33 g/g dry seaweed biomass.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="alginate_extraction_yield",
            target_system="Saccharina latissima",
            expected_unit="dimensionless",
            envelope_constraints=OperatingEnvelope(temperature_c=20.0, ph=7.0)
        )
    ),
    # Kelp Dynamic Viscosity (Algal Research 2023)
    (
        RawExtractedCandidate(
            entity_name="dynamic_viscosity",
            target_system="Saccharina latissima",
            raw_value=45.0,
            raw_unit="mPa * s",
            envelope=OperatingEnvelope(temperature_c=65.0),
            source_doi="10.1016/j.algal.2023.102931",
            source_snippet="The apparent dynamic viscosity of the Saccharina latissima extract was 45.0 mPa*s at 65 C.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="dynamic_viscosity",
            target_system="Saccharina latissima",
            expected_unit="Pa * s",
            envelope_constraints=OperatingEnvelope(temperature_c=65.0)
        )
    ),
    # Snippet too short candidate (Intentionally rejected by Quarantine Gate)
    (
        RawExtractedCandidate(
            entity_name="short_snippet_candidate",
            target_system="Saccharina latissima",
            raw_value=12.0,
            raw_unit="Pa * s",
            envelope=OperatingEnvelope(),
            source_doi="10.1016/j.algal.2023.102931",
            source_snippet="short",
            extraction_confidence=0.50
        ),
        RequiredParameterSpec(
            entity_name="short_snippet_candidate",
            target_system="Saccharina latissima",
            expected_unit="Pa * s"
        )
    ),
    # Unknown URI candidate (Intentionally rejected by Quarantine Gate)
    (
        RawExtractedCandidate(
            entity_name="unknown_uri_candidate",
            target_system="Saccharina latissima",
            raw_value=1.23,
            raw_unit="dimensionless",
            envelope=OperatingEnvelope(),
            source_doi="unverified_wiki_source",
            source_snippet="unverified wiki constant for kelp ratio",
            extraction_confidence=0.10
        ),
        RequiredParameterSpec(
            entity_name="unknown_uri_candidate",
            target_system="Saccharina latissima",
            expected_unit="dimensionless"
        )
    ),
    # Steam Methane Reforming (SMR) & Hydrogen Plant Literature Constants
    (
        RawExtractedCandidate(
            entity_name="smr_reaction_enthalpy",
            target_system="SMR Hydrogen Plant",
            raw_value=206.0,
            raw_unit="kJ / mol",
            envelope=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0),
            source_doi="10.1016/j.ijhydene.2010.04.093",
            source_snippet="Endothermic steam methane reforming reaction CH4 + H2O <-> CO + 3H2 has standard enthalpy dH_298 = 206 kJ/mol.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="smr_reaction_enthalpy",
            target_system="SMR Hydrogen Plant",
            expected_unit="kJ / mol",
            envelope_constraints=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0)
        )
    ),
    (
        RawExtractedCandidate(
            entity_name="wgs_reaction_enthalpy",
            target_system="SMR Hydrogen Plant",
            raw_value=-41.0,
            raw_unit="kJ / mol",
            envelope=OperatingEnvelope(temperature_c=350.0, pressure_bar=26.0),
            source_doi="10.1016/j.ijhydene.2010.04.093",
            source_snippet="Exothermic water-gas shift reaction CO + H2O <-> CO2 + H2 has standard enthalpy dH_298 = -41 kJ/mol.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="wgs_reaction_enthalpy",
            target_system="SMR Hydrogen Plant",
            expected_unit="kJ / mol",
            envelope_constraints=OperatingEnvelope(temperature_c=350.0, pressure_bar=26.0)
        )
    ),
    (
        RawExtractedCandidate(
            entity_name="smr_steam_to_carbon_ratio",
            target_system="SMR Hydrogen Plant",
            raw_value=3.0,
            raw_unit="dimensionless",
            envelope=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0),
            source_doi="10.1016/j.ijhydene.2013.08.055",
            source_snippet="Industrial SMR primary reformers typically operate at a steam-to-carbon molar ratio S/C = 3.0 to prevent coking.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="smr_steam_to_carbon_ratio",
            target_system="SMR Hydrogen Plant",
            expected_unit="dimensionless",
            envelope_constraints=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0)
        )
    ),
    (
        RawExtractedCandidate(
            entity_name="smr_reformer_outlet_temperature",
            target_system="SMR Hydrogen Plant",
            raw_value=850.0,
            raw_unit="degC",
            envelope=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0),
            source_doi="10.1016/j.ijhydene.2013.08.055",
            source_snippet="Primary reformer syngas outlet temperature is maintained between 850 and 900 C at equilibrium.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="smr_reformer_outlet_temperature",
            target_system="SMR Hydrogen Plant",
            expected_unit="degC",
            envelope_constraints=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0)
        )
    ),
    (
        RawExtractedCandidate(
            entity_name="smr_operating_pressure",
            target_system="SMR Hydrogen Plant",
            raw_value=28.0,
            raw_unit="bar",
            envelope=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0),
            source_doi="10.1016/j.ijhydene.2013.08.055",
            source_snippet="Modern industrial steam methane reforming plants operate at 25-30 bar pressure in the primary reformer.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="smr_operating_pressure",
            target_system="SMR Hydrogen Plant",
            expected_unit="bar",
            envelope_constraints=OperatingEnvelope(temperature_c=850.0, pressure_bar=28.0)
        )
    ),
    (
        RawExtractedCandidate(
            entity_name="psa_hydrogen_recovery",
            target_system="SMR Hydrogen Plant",
            raw_value=88.0,
            raw_unit="percent",
            envelope=OperatingEnvelope(temperature_c=40.0, pressure_bar=24.0),
            source_doi="10.1016/j.seppur.2018.03.058",
            source_snippet="Pressure swing adsorption (PSA) achieves 85-90% H2 recovery at 99%+ product purity with tail gas recycle.",
            extraction_confidence=0.95
        ),
        RequiredParameterSpec(
            entity_name="psa_hydrogen_recovery",
            target_system="SMR Hydrogen Plant",
            expected_unit="percent",
            envelope_constraints=OperatingEnvelope(temperature_c=40.0, pressure_bar=24.0)
        )
    )
]

def normalize_unit_str(u: Optional[str]) -> str:
    if not u or u.strip() in ["-", "1", "dimensionless"]:
        return "dimensionless"
    u = u.strip()
    replacements = {
        "g/L": "g / L",
        "1/h": "1 / hour",
        "g/g": "dimensionless",
        "wt%": "percent",
        "% w/v": "g / (100 * mL)",
        "%": "percent",
        "g/(g h)": "1 / hour",
        "mmol/(g h)": "mmol / (g * hour)",
        "g/mol": "g / mol",
        "mmol/L": "mmol / L",
        "% L/g": "L / g",
        "MPa": "MPa",
        "kDa": "kDa",
        "L": "L",
        "mPa * s": "mPa * s",
        "Pa * s": "Pa * s"
    }
    return replacements.get(u, u)

def diagnose_rejection(candidate: RawExtractedCandidate, spec: RequiredParameterSpec) -> str:
    doi_clean = candidate.source_doi.strip()
    snippet_clean = candidate.source_snippet.strip()
    if not (doi_clean.startswith("10.") or doi_clean.startswith(("dissertation://", "bench://"))):
        return f"unrecognized_uri_scheme ('{doi_clean[:32]}')"
    if len(snippet_clean) < 15:
        return f"short_snippet (len={len(snippet_clean)} < 15)"
    try:
        raw_qty = ureg.Quantity(candidate.raw_value, candidate.raw_unit)
        target_unit = ureg.Unit(spec.expected_unit)
        if not raw_qty.check(target_unit.dimensionality):
            return f"pint_dimensionality_mismatch ({candidate.raw_unit} -> {spec.expected_unit})"
    except Exception as e:
        return f"pint_unit_error ({str(e)})"
    return "unknown_quarantine_rejection"

def _enrich_candidate_from_quote(
    cand: RawExtractedCandidate,
    extra_ctx: str = "",
    raw_meta: Optional[Dict[str, Any]] = None,
) -> RawExtractedCandidate:
    """Populate OperatingEnvelope and verbatim-grounded (raw_value_min, raw_value_max) without fabricating bounds."""
    meta = raw_meta or {}
    env_extracted = extract_operating_envelope(cand.source_snippet or "", extra_ctx)
    if cand.envelope.temperature_c is None:
        cand.envelope.temperature_c = meta.get("temperature_c") if meta.get("temperature_c") is not None else env_extracted.temperature_c
    if cand.envelope.ph is None:
        cand.envelope.ph = meta.get("ph") if meta.get("ph") is not None else env_extracted.ph
    if cand.envelope.pressure_bar is None:
        cand.envelope.pressure_bar = meta.get("pressure_bar") if meta.get("pressure_bar") is not None else env_extracted.pressure_bar
    if cand.envelope.substrate is None and meta.get("substrate"):
        cand.envelope.substrate = str(meta["substrate"])
    if cand.envelope.medium_or_catalyst is None:
        med = meta.get("medium_or_catalyst") or meta.get("medium") or meta.get("catalyst")
        if med:
            cand.envelope.medium_or_catalyst = str(med)

    # Explicit JSON range metadata if present
    if cand.raw_value_min is None and meta.get("value_min") is not None and meta.get("value_max") is not None:
        cand.raw_value_min = float(meta["value_min"])
        cand.raw_value_max = float(meta["value_max"])
        return cand

    snippet = cand.source_snippet or ""
    if cand.raw_value_min is None and cand.raw_value_max is None and snippet:
        val = cand.raw_value
        # 1. Plus-minus pattern: e.g. "0.50 ± 0.08"
        for m in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*(?:\u00b1|\+/-|\ufffd)\s*([0-9]+(?:\.[0-9]+)?)", snippet):
            v_c = float(m.group(1))
            err = float(m.group(2))
            if err > 0.0 and abs(v_c - val) <= max(1e-6, 0.25 * max(abs(val), 1.0)):
                cand.raw_value_min = round(min(val, v_c - err), 10)
                cand.raw_value_max = round(max(val, v_c + err), 10)
                if cand.uncertainty is None:
                    cand.uncertainty = err
                return cand

        # 2. Range pattern: "between X and Y", "X - Y", "X–Y", "X to Y"
        for m in re.finditer(
            r"(?:between\s+)?([0-9]+(?:\.[0-9]+)?)\s*(?:-|–|—|\bto\b|\band\b)\s*([0-9]+(?:\.[0-9]+)?)",
            snippet,
            flags=re.IGNORECASE,
        ):
            v1 = float(m.group(1))
            v2 = float(m.group(2))
            v_min, v_max = min(v1, v2), max(v1, v2)
            if v_min < v_max and (v_min - 1e-9 <= val <= v_max + 1e-9):
                cand.raw_value_min = v_min
                cand.raw_value_max = v_max
                return cand

    return cand


def ingest_workspace_json_files(base_path: Optional[Path] = None) -> List[Tuple[RawExtractedCandidate, RequiredParameterSpec, str]]:
    project_root = base_path or Path(__file__).resolve().parent.parent
    entries: List[Tuple[RawExtractedCandidate, RequiredParameterSpec, str]] = []

    # 1. composition/data/central_library.json
    cl_path = project_root / "composition" / "data" / "central_library.json"
    if cl_path.exists():
        try:
            with open(cl_path, "r", encoding="utf-8") as f:
                cl_data = json.load(f)
            papers = cl_data.get("papers", {})
            for pid, p in cl_data.get("parameters", {}).items():
                paper = papers.get(p.get("paper_id"), {})
                doi = paper.get("doi", "")
                quote = p.get("verbatim_quote", "")
                val = float(p.get("value", 0.0))
                unit = normalize_unit_str(p.get("unit", ""))
                bio_ctx = p.get("biological_context", {})
                organism = bio_ctx.get("organism", "Escherichia coli")
                temp_c = bio_ctx.get("temperature_c")
                ph = bio_ctx.get("ph")

                cand = _enrich_candidate_from_quote(
                    RawExtractedCandidate(
                        entity_name=pid.replace(".", "_").lower(),
                        target_system=organism,
                        raw_value=val,
                        raw_unit=unit,
                        envelope=OperatingEnvelope(temperature_c=temp_c, ph=ph),
                        source_doi=doi,
                        source_snippet=quote,
                        extraction_confidence=0.95
                    ),
                    extra_ctx=paper.get("title", ""),
                    raw_meta={**bio_ctx, **p},
                )
                spec = RequiredParameterSpec(
                    entity_name=cand.entity_name,
                    target_system=cand.target_system,
                    expected_unit=unit,
                    envelope_constraints=cand.envelope
                )
                entries.append((cand, spec, "composition/data/central_library.json"))
        except Exception:
            pass

    # 2. web/pyodide/model/data/reference_parameters.json
    rp_path = project_root / "web" / "pyodide" / "model" / "data" / "reference_parameters.json"
    if rp_path.exists():
        try:
            with open(rp_path, "r", encoding="utf-8") as f:
                rp_data = json.load(f)
            doi = rp_data.get("source", {}).get("doi", "")
            for p in rp_data.get("parameters", []):
                quote = p.get("source", {}).get("quote", "") or rp_data.get("source", {}).get("fitting_statement", "")
                val = float(p.get("value", 0.0))
                unit = normalize_unit_str(p.get("unit", ""))
                sym = p.get("symbol", "")

                cand = _enrich_candidate_from_quote(
                    RawExtractedCandidate(
                        entity_name=f"ganjave_{sym.lower()}",
                        target_system="Escherichia coli",
                        raw_value=val,
                        raw_unit=unit,
                        envelope=OperatingEnvelope(temperature_c=37.0, ph=7.0),
                        source_doi=doi,
                        source_snippet=quote,
                        extraction_confidence=0.92
                    ),
                    raw_meta=p,
                )
                spec = RequiredParameterSpec(
                    entity_name=cand.entity_name,
                    target_system=cand.target_system,
                    expected_unit=unit,
                    envelope_constraints=OperatingEnvelope(temperature_c=37.0, ph=7.0)
                )
                entries.append((cand, spec, "web/pyodide/model/data/reference_parameters.json"))
        except Exception:
            pass

    return entries

SEED_MECHANISTIC_LAWS: List[PhysicalInvariantSpec] = [
    PhysicalInvariantSpec(
        law_id="SECOND_LAW_PINCH",
        domain="thermodynamics",
        governing_equation="T_hot_in - T_cold_out >= dT_min and T_hot_out - T_cold_in >= dT_min and |Q_hot - Q_cold|/Q_hot <= 0.02",
        threshold_parameters={"dT_min_c": 10.0, "first_law_rel_tol": 0.02},
        remediation_action="reorder_convection_pinch",
        doi="10.1016/0009-2509(83)80134-1",
        verbatim_quote="Pinch design method enforces minimum approach temperature dT_min >= 10 C across all heat exchanger hot/cold stream matches.",
    ),
    PhysicalInvariantSpec(
        law_id="SINGLE_SHELL_THERMAL_SHOCK",
        domain="thermodynamics",
        governing_equation="delta_T_hx <= max_single_hx_dt_c",
        threshold_parameters={"max_single_hx_dt_c": 350.0},
        remediation_action="split_into_series_heat_exchangers",
        doi="10.1016/B978-0-08-096659-5.00019-5",
        verbatim_quote="Large process cooling duties exceeding 350 C temperature drop must be staged across WHB, intercooler, economizer, and trim exchangers.",
    ),
    PhysicalInvariantSpec(
        law_id="VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM",
        domain="kinetics_equilibrium",
        governing_equation="X_exit <= X_eq(T_out, P) and delta_T_ad <= max_adiabatic_rise_c",
        threshold_parameters={"max_adiabatic_rise_c": 220.0, "min_intercooled_conversion_jump": 0.05},
        remediation_action="insert_intercooled_reactor_stage",
        doi="10.1016/j.ijhydene.2010.04.093",
        verbatim_quote="Exothermic reversible reactions such as WGS require high-temperature conversion followed by interstage cooling to overcome equilibrium limitation.",
    ),
    PhysicalInvariantSpec(
        law_id="POLYTROPIC_COMPRESSION_DISCHARGE",
        domain="thermodynamics",
        governing_equation="T_out = T_in * (P_out / P_in)**((gamma - 1) / (gamma * eta_p)) <= T_max_mech",
        threshold_parameters={"max_compressor_discharge_c": 155.0, "max_stage_ratio": 2.5, "gamma": 1.38, "eta_p": 0.80},
        remediation_action="insert_multistage_compressor_intercoolers",
        doi="10.1016/B978-0-12-809644-4.00003-2",
        verbatim_quote="Reciprocating hydrogen compressors are limited to stage discharge temperatures <= 155 C via interstage cooling with stage ratio <= 2.5.",
    ),
    PhysicalInvariantSpec(
        law_id="NICKEL_SULFUR_POISONING",
        domain="catalysis_materials",
        governing_equation="y_H2S <= max_ni_h2s_ppm",
        threshold_parameters={"max_ni_h2s_ppm": 0.1},
        remediation_action="insert_upstream_hds_and_prereformer",
        doi="10.1016/j.ijhydene.2013.08.055",
        verbatim_quote="Nickel steam reforming catalysts suffer irreversible sulfur poisoning above 0.1 ppmv H2S and require upstream HDS ZnO guard beds.",
    ),
    PhysicalInvariantSpec(
        law_id="BOUDOUARD_CARBON_COKING",
        domain="catalysis_materials",
        governing_equation="S_to_C >= min_sc_ratio_ni",
        threshold_parameters={"min_sc_ratio_ni": 2.0},
        remediation_action="enforce_minimum_steam_to_carbon_ratio",
        doi="10.1016/j.ijhydene.2013.08.055",
        verbatim_quote="Industrial SMR reformers operate at S/C >= 2.0-3.0 to prevent Boudouard carbon whisker deposition on nickel catalyst tubes.",
    ),
    PhysicalInvariantSpec(
        law_id="WET_GAS_PSA_KNOCKOUT",
        domain="hydraulics_phase",
        governing_equation="T_psa_in <= max_psa_inlet_temp_c and has_knockout_separator == 1",
        threshold_parameters={"max_psa_inlet_temp_c": 45.0},
        remediation_action="insert_condensate_knockout_drum",
        doi="10.1016/j.seppur.2018.03.058",
        verbatim_quote="PSA adsorbent beds require cooled gas <= 45 C and upstream condensate knockout separation to prevent water condensation in molecular sieves.",
    ),
    PhysicalInvariantSpec(
        law_id="PASSIVE_PRESSURE_DROP_MONOTONICITY",
        domain="hydraulics_phase",
        governing_equation="P_out <= P_in for passive units; delta_P > 0 only across P-xxx/C-xxx",
        threshold_parameters={"max_passive_pressure_rise_bar": 0.01},
        remediation_action="insert_compressor_or_pump",
        doi="10.1016/B978-0-08-096659-5.00005-5",
        verbatim_quote="Passive reactors, heat exchangers, and piping cannot increase fluid static pressure without mechanical work from a pump or compressor.",
    ),
    PhysicalInvariantSpec(
        law_id="AEROBIC_OXYGEN_TRANSFER_LIMIT",
        domain="bioprocess",
        governing_equation="OTR = kLa * (C_star - C_L) >= OUR",
        threshold_parameters={"min_dissolved_oxygen_frac": 0.15},
        remediation_action="increase_kla_or_aeration",
        doi="10.1016/j.bej.2017.09.005",
        verbatim_quote="Aerobic fermentation oxygen transfer rate OTR = kLa*(C* - C_L) must exceed oxygen uptake rate to avoid anoxic metabolic shift.",
    ),
    PhysicalInvariantSpec(
        law_id="UK_INDUSTRIAL_SPACING_AND_THERMAL_LENGTH",
        domain="hydraulics_phase",
        governing_equation="clearance_fired >= 10.0 m and cooling_axial_run >= 36.0 m (BS EN 13480 / IChemE)",
        threshold_parameters={"min_fired_heater_clearance_m": 10.0, "min_cooling_train_axial_m": 36.0},
        remediation_action="expand_plot_spacing_and_thermal_runs",
        doi="10.1016/B978-0-08-096659-5.00005-5",
        verbatim_quote="Fired heaters must maintain >= 10 m clear separation from adjacent process units and high-temperature cooling trains require adequate axial run length for thermal expansion.",
    ),
]


SEED_DOMAIN_SKILLS: List[DomainSkillSpec] = [
    DomainSkillSpec(
        domain_id="thermochemical_plant",
        governing_laws=[
            "SECOND_LAW_PINCH",
            "SINGLE_SHELL_THERMAL_SHOCK",
            "VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM",
            "POLYTROPIC_COMPRESSION_DISCHARGE",
            "NICKEL_SULFUR_POISONING",
            "BOUDOUARD_CARBON_COKING",
            "WET_GAS_PSA_KNOCKOUT",
            "PASSIVE_PRESSURE_DROP_MONOTONICITY",
            "UK_INDUSTRIAL_SPACING_AND_THERMAL_LENGTH",
        ],
        rag_scope={
            "target_systems": ["Steam Methane Reforming", "Methanol Synthesis", "Ammonia Synthesis", "Chemical Process"],
            "domains": ["thermodynamics", "kinetics_equilibrium", "catalysis_materials", "hydraulics_phase"],
        },
        allowed_archetypes=[
            "pre_reformer",
            "furnace_reformer",
            "shell_tube_hx",
            "packed_bed_reactor",
            "knockout_cooler",
            "co2_absorber",
            "psa_skid",
            "high_pressure_compressor",
            "separator_unit",
        ],
        few_shot_derivations=[
            {
                "name": "12_unit_smr_hydrogen_plant",
                "prompt": "Design and simulate an industrial Steam Methane Reforming (SMR) plant for hydrogen production with pre-reformer, primary reformer, two-stage WGS, CO2 absorption, PSA, and syngas compression.",
                "derivation_trace": (
                    "1. Desulfurize natural gas in R-101 (ZnO guard bed, 400 C, 44.5 bar) to <= 0.1 ppmv H2S (NICKEL_SULFUR_POISONING).\n"
                    "2. Adiabatically pre-reform C2+ hydrocarbons in R-102 (504 C, 38.9 bar) with S/C=3.0 >= 2.0 (BOUDOUARD_CARBON_COKING).\n"
                    "3. Reform CH4 in primary radiant furnace B-101/R-103 (900 C, 38.0 bar) with Pinch-ordered convection banks E-103 -> E-102 -> E-109 -> E-101 -> E-104 -> T-102.\n"
                    "4. Stage syngas cooling & dual-bed exothermic WGS: E-105 WHB -> R-104 HT-Shift -> E-106 Intercooler -> R-105 LT-Shift -> E-107 Economizer -> E-108 Trim Condenser -> S-101 KO Drum (<= 45 C) -> V-101 4-bed PSA -> 3-stage intercooled compression C-101..103 to 400 bar."
                ),
                "topology_manifest": {
                    "unit_tags": ["R-101", "R-102", "B-101/R-103", "E-105", "R-104", "E-106", "R-105", "E-107", "E-108", "S-101", "V-101", "C-101..103"],
                    "convection_banks": ["E-103", "E-102", "E-109", "E-101", "E-104"],
                },
            }
        ],
        invariant_checks=[
            "mass_conservation_non_negative",
            "second_law_pinch_approach_ge_10c",
            "single_shell_hx_dt_bounds",
            "exothermic_shift_intercooling",
            "polytropic_discharge_le_155c",
            "passive_pressure_drop_monotonicity",
            "uk_industrial_spacing_bs_en_13480",
        ],
    ),
    DomainSkillSpec(
        domain_id="bioprocess_kinetics",
        governing_laws=["AEROBIC_OXYGEN_TRANSFER_LIMIT", "SECOND_LAW_PINCH"],
        rag_scope={
            "target_systems": ["Escherichia coli", "Saccharina latissima", "Corynebacterium glutamicum", "Yarrowia lipolytica"],
            "domains": ["bioprocess", "thermodynamics"],
        },
        allowed_archetypes=[
            "hopper_mill",
            "stirred_tank_bioreactor",
            "centrifuge_separator",
            "membrane_filter",
            "wet_spinning_bath",
            "shake_flask",
        ],
        few_shot_derivations=[
            {
                "name": "saccharina_alginate_extraction",
                "prompt": "Simulate 6-stage Saccharina latissima alginate extraction and wet-spinning.",
                "derivation_trace": (
                    "1. Dry milling of Laminaria/Saccharina frond biomass.\n"
                    "2. Acid wash & alkaline Na2CO3 dissolution.\n"
                    "3. Centrifugal clarification, cryo/ethanol precipitation, and CaCl2 wet-spinning."
                ),
                "topology_manifest": {"unit_tags": ["MILL-1", "ACID-2", "ALK-3", "CENT-4", "PREC-5", "SPIN-6"]},
            },
            {
                "name": "ecoli_fed_batch_fermentation",
                "prompt": "Simulate aerobic fed-batch Escherichia coli fermentation in a 10 L bioreactor.",
                "derivation_trace": (
                    "1. Solve Monod growth kinetics (mu_max, Ks, Y_xs, m) coupled with oxygen transfer OTR = kLa * (C* - C_L) >= OUR."
                ),
                "topology_manifest": {"unit_tags": ["SEED-1", "FERM-2", "HARV-3"]},
            },
        ],
        invariant_checks=["mass_conservation_non_negative", "aerobic_otr_ge_our"],
    ),
    DomainSkillSpec(
        domain_id="electromechanics",
        governing_laws=["POLYTROPIC_COMPRESSION_DISCHARGE", "PASSIVE_PRESSURE_DROP_MONOTONICITY"],
        rag_scope={
            "target_systems": ["Electromechanical", "Reciprocating Compressor", "Doorbell Solenoid"],
            "domains": ["thermodynamics", "hydraulics_phase"],
        },
        allowed_archetypes=["high_pressure_compressor", "solenoid_actuator", "circuit_oscillator"],
        few_shot_derivations=[
            {
                "name": "multistage_h2_compression",
                "prompt": "Compress purified H2 from 33.1 bar to 400 bar in intercooled reciprocating stages.",
                "derivation_trace": "1. Compute N = ceil(ln(P_out/P_in)/ln(2.2)) stages with interstage cooling to <= 40 C keeping discharge <= 155 C.",
                "topology_manifest": {"unit_tags": ["E-110", "C-101", "E-111", "C-102", "E-112", "C-103", "E-113"]},
            }
        ],
        invariant_checks=["polytropic_discharge_le_155c", "passive_pressure_drop_monotonicity"],
    ),
]


SEED_AGENT_PROFILES: List[InternalPersonaProfile] = [
    InternalPersonaProfile(
        persona_id="elmer_gaden",
        internal_display_name="Elmer Gaden",
        public_engine_alias="ScaleUp Bioprocess Kinetics Engine",
        domain_scope="bioprocess",
        linked_domain_skill_id="bioprocess_kinetics",
        lens_markdown_path="scaleup_rag/personas/elmer_gaden.md",
        elo_trust_score=1200.0,
        is_proctor=False,
    ),
    InternalPersonaProfile(
        persona_id="octave_levenspiel",
        internal_display_name="Octave Levenspiel",
        public_engine_alias="ScaleUp Thermochemical Process Engine",
        domain_scope="thermochemical",
        linked_domain_skill_id="thermochemical_plant",
        lens_markdown_path="scaleup_rag/personas/octave_levenspiel.md",
        elo_trust_score=1200.0,
        is_proctor=False,
    ),
    InternalPersonaProfile(
        persona_id="nikola_tesla",
        internal_display_name="Nikola Tesla",
        public_engine_alias="ScaleUp Electromechanical & Coupled Physics Engine",
        domain_scope="electromechanical",
        linked_domain_skill_id="electromechanics",
        lens_markdown_path="scaleup_rag/personas/nikola_tesla.md",
        elo_trust_score=1200.0,
        is_proctor=False,
    ),
    InternalPersonaProfile(
        persona_id="richard_feynman",
        internal_display_name="Richard Feynman",
        public_engine_alias="ScaleUp Adversarial Verification Proctor",
        domain_scope="adversarial_proctor",
        linked_domain_skill_id="thermochemical_plant",
        lens_markdown_path="scaleup_rag/personas/richard_feynman.md",
        elo_trust_score=1200.0,
        is_proctor=True,
    ),
]


def seed_database(db_url: Optional[str] = None, include_workspace_json: bool = True) -> Dict[str, Any]:
    db = ParameterDatabase(db_url=db_url)
    
    candidates_to_process: List[Tuple[RawExtractedCandidate, RequiredParameterSpec, str]] = [
        (c, s, "seed_candidates") for c, s in SEED_CANDIDATES
    ]

    json_params_count = 0
    if include_workspace_json:
        workspace_entries = ingest_workspace_json_files()
        json_params_count = len(workspace_entries)
        candidates_to_process.extend(workspace_entries)

    total_count = len(candidates_to_process)
    passed_count = 0
    rejected_count = 0
    written_count = 0
    tier_counts = {"tier_0_internal_bench": 0, "tier_1_quarantine": 0}
    rejections: List[Dict[str, str]] = []

    for candidate, spec, src in candidates_to_process:
        candidate = _enrich_candidate_from_quote(candidate)
        grounded = validate_and_normalize(candidate, spec)
        if grounded is not None:
            passed_count += 1
            if grounded.verification_tier in tier_counts:
                tier_counts[grounded.verification_tier] += 1
            existing = db.lookup_parameter(spec)
            db.write_back_parameter(grounded)
            if existing is None:
                written_count += 1
        else:
            rejected_count += 1
            reason = diagnose_rejection(candidate, spec)
            rejections.append({
                "entity_name": candidate.entity_name,
                "target_system": candidate.target_system,
                "source": src,
                "reason": reason
            })

    laws_newly_written = 0
    for law in SEED_MECHANISTIC_LAWS:
        if db.upsert_mechanistic_law(law):
            laws_newly_written += 1

    skills_newly_written = 0
    for skill in SEED_DOMAIN_SKILLS:
        if db.upsert_domain_skill(skill):
            skills_newly_written += 1

    profiles_newly_written = 0
    for profile in SEED_AGENT_PROFILES:
        if db.upsert_agent_profile(profile):
            profiles_newly_written += 1

    return {
        "total_evaluated": total_count,
        "total_candidates": total_count,
        "json_params_scanned": json_params_count,
        "passed_quarantine": passed_count,
        "rejected_by_quarantine": rejected_count,
        "newly_written_to_db": written_count,
        "mechanistic_laws_total": len(SEED_MECHANISTIC_LAWS),
        "mechanistic_laws_newly_written": laws_newly_written,
        "domain_skills_total": len(SEED_DOMAIN_SKILLS),
        "domain_skills_newly_written": skills_newly_written,
        "agent_profiles_total": len(SEED_AGENT_PROFILES),
        "agent_profiles_newly_written": profiles_newly_written,
        "tier_counts": tier_counts,
        "rejection_details": rejections
    }

def main():
    report = seed_database()
    print("==========================================================================================")
    print("                 ScaleUp Knowledge Base Ingestion & Seeding Report                        ")
    print("==========================================================================================")
    print(f"Total Candidates Evaluated (Seed + JSONs) : {report['total_evaluated']}")
    print(f"Total Workspace JSON Parameters Scanned   : {report['json_params_scanned']}")
    print(f"Passed Quarantine Gate & Validated        : {report['passed_quarantine']}")
    print(f"  -> Tier 1 (Peer-Reviewed Quarantine)    : {report['tier_counts']['tier_1_quarantine']}")
    print(f"  -> Tier 0 (Internal Bench / Thesis)     : {report['tier_counts']['tier_0_internal_bench']}")
    print(f"Rejected by Epistemic Quarantine Gate     : {report['rejected_by_quarantine']}")
    print(f"Newly Written to Database                 : {report['newly_written_to_db']}")
    print("------------------------------------------------------------------------------------------")
    print("REJECTION AUDIT LOG (Filtered out by Epistemic Guardrail):")
    print("------------------------------------------------------------------------------------------")
    for r in report["rejection_details"]:
        print(f" - [{r['entity_name']:<35}] from {r['source']:<42} -> {r['reason']}")
    print("==========================================================================================")

if __name__ == "__main__":
    main()
