"""50-Parameter Blind Extraction Benchmark & Epistemic Quarantine Audit.

Evaluates 40 grounded extraction/unit-conversion/range/envelope cases (Group A)
and 10 adversarial/abstention/quarantine-rejection cases (Group B) against an
isolated in-memory SQLite database (sqlite:///:memory:).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import ScaleUpRAGEngine
from .llm_bridge import _extract_via_regex
from .schemas import OperatingEnvelope, RawExtractedCandidate, RequiredParameterSpec


@dataclass
class BenchmarkCase:
    case_id: str
    group: str  # "A_GROUNDED" or "B_ADVERSARIAL"
    category: str
    domain: str
    doi: str
    paper_text: str
    spec: RequiredParameterSpec
    expected_value: Optional[float] = None
    expected_min: Optional[float] = None
    expected_max: Optional[float] = None
    expected_temp_c: Optional[float] = None
    expected_ph: Optional[float] = None
    expected_pressure_bar: Optional[float] = None
    adversarial_candidate: Optional[RawExtractedCandidate] = None


def _build_cases() -> List[BenchmarkCase]:
    cases: List[BenchmarkCase] = []

    # ------------------------------------------------------------------
    # Group A: 40 Grounded Extraction & Conversion Cases across 10 DOIs
    # ------------------------------------------------------------------
    raw_a = [
        # DOI 1: Bioprocess Fermentation - E. coli fed-batch (10.1016/j.biortech.2024.130101)
        ("A01", "Range+Env", "Bioprocess Fermentation", "10.1016/j.biortech.2024.130101",
         "In a 5 L bioreactor at 37 \u00b0C and pH 6.8 (OD600 = 42 after 24 h), the specific growth rate of E. coli ranged from 0.38 to 0.52 h^-1.",
         "specific_growth_rate_mu_max", "Escherichia coli", "1 / hour", 0.45, 0.38, 0.52, 37.0, 6.8, None),
        ("A02", "UnitConv+Env", "Bioprocess Fermentation", "10.1016/j.biortech.2024.130101",
         "Operating a 5 L vessel at 37 \u00b0C and pH 6.8, feed glucose concentration was maintained at 450.0 g/L over 24 h.",
         "feed_glucose_concentration", "Escherichia coli", "kg / m**3", 450.0, None, None, 37.0, 6.8, None),
        ("A03", "PlusMinus+Env", "Bioprocess Fermentation", "10.1016/j.biortech.2024.130101",
         "Oxygen mass transfer kLa in the 5 L sparged reactor at 37 \u00b0C and pH 6.8 was 180.0 \u00b1 15.0 1/h at 600 rpm.",
         "mass_transfer_kla", "Escherichia coli", "1 / hour", 180.0, 165.0, 195.0, 37.0, 6.8, None),
        ("A04", "UnitConv+Env", "Bioprocess Fermentation", "10.1016/j.biortech.2024.130101",
         "At 37 \u00b0C and pH 6.8 in a 5 L reactor, dissolved oxygen saturation c_star was 7.2 mg/L.",
         "oxygen_saturation_c_star", "Escherichia coli", "kg / m**3", 0.0072, None, None, 37.0, 6.8, None),

        # DOI 2: Yeast / Pichia Fermentation (10.1002/bit.28102)
        ("A05", "UnitConv+Env", "Bioprocess Fermentation", "10.1002/bit.28102",
         "Pichia pastoris cultivation in a 10 L fermenter at 30 \u00b0C and pH 5.5 exhibited a dilution_rate of 0.002 min^-1 over 48 h.",
         "dilution_rate", "Pichia pastoris", "1 / hour", 0.12, None, None, 30.0, 5.5, None),
        ("A06", "Range+Env", "Bioprocess Fermentation", "10.1002/bit.28102",
         "At 30 \u00b0C and pH 5.5, methanol uptake_rate ranged from 0.12 to 0.18 h^-1 in the 10 L batch.",
         "methanol_uptake_rate", "Pichia pastoris", "1 / hour", 0.15, 0.12, 0.18, 30.0, 5.5, None),
        ("A07", "Scalar+Env", "Bioprocess Fermentation", "10.1002/bit.28102",
         "Recombinant protein titer reached 4.8 g/L at 30 \u00b0C and pH 5.5 after 72 h induction.",
         "protein_titer", "Pichia pastoris", "kg / m**3", 4.8, None, None, 30.0, 5.5, None),
        ("A08", "PlusMinus+Env", "Bioprocess Fermentation", "10.1002/bit.28102",
         "Cell maintenance coefficient at 30 \u00b0C and pH 5.5 was 0.025 \u00b1 0.005 1/h across 3 runs.",
         "maintenance_coefficient", "Pichia pastoris", "1 / hour", 0.025, 0.020, 0.030, 30.0, 5.5, None),

        # DOI 3: Downstream Biopolymer Alginate Extraction (10.1016/j.algal.2023.103103)
        ("A09", "UnitConv+Env", "Downstream Biopolymer", "10.1016/j.algal.2023.103103",
         "Saccharina latissima alginate extract viscosity at 65 \u00b0C and pH 7.0 was 48.0 mPa\u00b7s at 100 rpm.",
         "dynamic_viscosity", "Saccharina latissima", "Pa * s", 0.048, None, None, 65.0, 7.0, None),
        ("A10", "Range+Env", "Downstream Biopolymer", "10.1016/j.algal.2023.103103",
         "Alkaline extraction at 65 \u00b0C and pH 12.0 achieved an alginate yield of 28.0-34.0 % on a dry kelp basis.",
         "alginate_yield", "Saccharina latissima", "percent", 31.0, 28.0, 34.0, 65.0, 12.0, None),
        ("A11", "PlusMinus+Env", "Downstream Biopolymer", "10.1016/j.algal.2023.103103",
         "Wet-spun alginate fibre tensile_strength at 25 \u00b0C and pH 7.0 was 42.5 \u00b1 2.5 MPa.",
         "tensile_strength", "Saccharina latissima", "bar", 425.0, 400.0, 450.0, 25.0, 7.0, None),
        ("A12", "UnitConv+Env", "Downstream Biopolymer", "10.1016/j.algal.2023.103103",
         "In a 2 L vessel at 25 \u00b0C and pH 7.0, slurry concentration was 15.0 mg/mL.",
         "slurry_concentration", "Saccharina latissima", "g / L", 15.0, None, None, 25.0, 7.0, None),

        # DOI 4: Protein Chromatography & Membrane Filtration (10.1016/j.chroma.2024.464104)
        ("A13", "PlusMinus+Env", "Downstream Purification", "10.1016/j.chroma.2024.464104",
         "Protein A affinity chromatography recovery at 22 \u00b0C and pH 7.2 was 82.5 \u00b1 4.5 % at 150 cm/h.",
         "chromatography_recovery", "Monoclonal Antibody", "percent", 82.5, 78.0, 87.0, 22.0, 7.2, None),
        ("A14", "UnitConv+Env", "Downstream Purification", "10.1016/j.chroma.2024.464104",
         "Transmembrane pressure during ultrafiltration at 22 \u00b0C and pH 7.2 was 0.25 MPa for 4 h.",
         "transmembrane_pressure", "Monoclonal Antibody", "bar", 2.5, None, None, 22.0, 7.2, None),
        ("A15", "UnitConv+Env", "Downstream Purification", "10.1016/j.chroma.2024.464104",
         "Eluate buffer viscosity at 22 \u00b0C and pH 3.5 was 1.35 mPa*s in a 50 mL column.",
         "eluate_viscosity", "Monoclonal Antibody", "Pa * s", 0.00135, None, None, 22.0, 3.5, None),
        ("A16", "Scalar+Env", "Downstream Purification", "10.1016/j.chroma.2024.464104",
         "Dynamic binding capacity at 22 \u00b0C and pH 7.2 reached 55.0 mg/mL resin.",
         "binding_capacity", "Monoclonal Antibody", "g / L", 55.0, None, None, 22.0, 7.2, None),

        # DOI 5: Enzymatic Kinetics - Cellulase Hydrolysis (10.1016/j.enzmictec.2023.110105)
        ("A17", "Range+Env", "Enzymatic Kinetics", "10.1016/j.enzmictec.2023.110105",
         "Cellulase catalytic turnover_rate at 50 \u00b0C and pH 4.8 ranged from 1.2 to 1.8 s^-1 in 100 mL flasks.",
         "catalytic_turnover_rate", "Trichoderma reesei cellulase", "1 / hour", 5400.0, 4320.0, 6480.0, 50.0, 4.8, None),
        ("A18", "Scalar+Env", "Enzymatic Kinetics", "10.1016/j.enzmictec.2023.110105",
         "Substrate affinity km at 50 \u00b0C and pH 4.8 was 12.5 g/L.",
         "substrate_affinity_km", "Trichoderma reesei cellulase", "kg / m**3", 12.5, None, None, 50.0, 4.8, None),
        ("A19", "Scalar+Env", "Enzymatic Kinetics", "10.1016/j.enzmictec.2023.110105",
         "Activation energy for thermal deactivation at pH 4.8 was 115.0 kJ/mol between 45 and 65 \u00b0C.",
         "activation_energy", "Trichoderma reesei cellulase", "J / mol", 115000.0, None, None, None, 4.8, None),
        ("A20", "PlusMinus+Env", "Enzymatic Kinetics", "10.1016/j.enzmictec.2023.110105",
         "Glucose conversion at 50 \u00b0C and pH 4.8 after 48 h was 76.0 \u00b1 3.0 %.",
         "glucose_conversion", "Trichoderma reesei cellulase", "percent", 76.0, 73.0, 79.0, 50.0, 4.8, None),

        # DOI 6: Steam Methane Reforming (SMR) Catalysis (10.1016/j.ijhydene.2024.20106)
        ("A21", "Range+Env", "Thermochemical SMR", "10.1016/j.ijhydene.2024.20106",
         "Primary SMR reformer pressure at 850 \u00b0C operated between 24.0 and 30.0 bar over Ni/Al2O3 catalyst.",
         "reformer_pressure", "SMR Hydrogen Plant", "bar", 27.0, 24.0, 30.0, 850.0, None, None),
        ("A22", "Scalar+Env", "Thermochemical SMR", "10.1016/j.ijhydene.2024.20106",
         "Endothermic reforming enthalpy at 850 \u00b0C and 28 bar was 206.2 kJ/mol.",
         "reforming_enthalpy", "SMR Hydrogen Plant", "J / mol", 206200.0, None, None, 850.0, None, 28.0),
        ("A23", "UnitConv+Env", "Thermochemical SMR", "10.1016/j.ijhydene.2024.20106",
         "High-pressure H2 storage compressor discharge at 40 \u00b0C reached 40.0 MPa.",
         "compressor_discharge", "SMR Hydrogen Plant", "bar", 400.0, None, None, 40.0, None, None),
        ("A24", "Range+Env", "Thermochemical SMR", "10.1016/j.ijhydene.2024.20106",
         "PSA hydrogen_recovery at 40 \u00b0C and 24 bar ranged from 86.0 to 90.0 %.",
         "psa_hydrogen_recovery", "SMR Hydrogen Plant", "percent", 88.0, 86.0, 90.0, 40.0, None, 24.0),

        # DOI 7: Water-Gas Shift & CO2 Capture (10.1016/j.cej.2023.145107)
        ("A25", "Scalar+Env", "Thermochemical WGS", "10.1016/j.cej.2023.145107",
         "Exothermic water-gas shift enthalpy at 350 \u00b0C and 25 bar was -41.2 kJ/mol.",
         "shift_enthalpy", "WGS Reactor", "J / mol", -41200.0, None, None, 350.0, None, 25.0),
        ("A26", "UnitConv+Env", "Thermochemical WGS", "10.1016/j.cej.2023.145107",
         "Syngas heat capacity at 350 \u00b0C and 25 bar was 34.5 J/(mol*K).",
         "syngas_heat_capacity", "WGS Reactor", "kJ / (mol * K)", 0.0345, None, None, 350.0, None, 25.0),
        ("A27", "PlusMinus+Env", "Thermochemical WGS", "10.1016/j.cej.2023.145107",
         "Amine CO2 capture efficiency at 42 \u00b0C and 24 bar was 94.0 \u00b1 1.5 %.",
         "co2_capture_efficiency", "WGS Reactor", "percent", 94.0, 92.5, 95.5, 42.0, None, 24.0),
        ("A28", "Scalar+Env", "Thermochemical WGS", "10.1016/j.cej.2023.145107",
         "Fe-Cr HT-shift catalyst bulk_density at 380 \u00b0C and 25 bar was 1150.0 kg/m**3.",
         "catalyst_bulk_density", "WGS Reactor", "g / L", 1150.0, None, None, 380.0, None, 25.0),

        # DOI 8: Haber-Bosch Ammonia Synthesis (10.1021/acs.iecr.2023.30108)
        ("A29", "Range+Env", "Catalytic Ammonia", "10.1021/acs.iecr.2023.30108",
         "Ammonia synthesis loop pressure at 450 \u00b0C was maintained between 240 and 280 bar.",
         "synthesis_pressure", "Haber-Bosch Loop", "bar", 260.0, 240.0, 280.0, 450.0, None, None),
        ("A30", "UnitConv+Env", "Catalytic Ammonia", "10.1021/acs.iecr.2023.30108",
         "Inlet gas pressure at 450 \u00b0C was 26.0 MPa over promoted iron catalyst.",
         "inlet_gas_pressure", "Haber-Bosch Loop", "bar", 260.0, None, None, 450.0, None, None),
        ("A31", "Scalar+Env", "Catalytic Ammonia", "10.1021/acs.iecr.2023.30108",
         "Molar entropy change at 450 \u00b0C and 260 bar was -99.4 J/(mol*K).",
         "molar_entropy", "Haber-Bosch Loop", "kJ / (mol * K)", -0.0994, None, None, 450.0, None, 260.0),
        ("A32", "Scalar+Env", "Catalytic Ammonia", "10.1021/acs.iecr.2023.30108",
         "Single-pass nitrogen conversion at 450 \u00b0C and 260 bar was 18.5 %.",
         "nitrogen_conversion", "Haber-Bosch Loop", "percent", 18.5, None, None, 450.0, None, 260.0),

        # DOI 9: PEM Electrolysis & Photobioreactor (10.1016/j.apenergy.2024.122109)
        ("A33", "UnitConv+Env", "Electrochemical / Photo", "10.1016/j.apenergy.2024.122109",
         "Solar irradiance incident on the photobioreactor at 28 \u00b0C and pH 7.4 was 45.0 mW/cm**2.",
         "solar_irradiance", "Chlorella vulgaris", "W / m**2", 450.0, None, None, 28.0, 7.4, None),
        ("A34", "Range+Env", "Electrochemical / Photo", "10.1016/j.apenergy.2024.122109",
         "Biomass productivity at 28 \u00b0C and pH 7.4 ranged from 0.10 to 0.14 g/(L*h) over 120 h.",
         "biomass_productivity", "Chlorella vulgaris", "kg / (m**3 * hour)", 0.12, 0.10, 0.14, 28.0, 7.4, None),
        ("A35", "Scalar+Env", "Electrochemical / Photo", "10.1016/j.apenergy.2024.122109",
         "PEM electrolyzer operating pressure at 60 \u00b0C reached 30.0 bar.",
         "electrolyzer_pressure", "PEM Electrolyzer", "bar", 30.0, None, None, 60.0, None, 30.0),
        ("A36", "Scalar+Env", "Electrochemical / Photo", "10.1016/j.apenergy.2024.122109",
         "Faradaic efficiency at 60 \u00b0C and 30 bar was 98.5 %.",
         "faradaic_efficiency", "PEM Electrolyzer", "percent", 98.5, None, None, 60.0, None, 30.0),

        # DOI 10: Microalgae Lipid & Fermentation Scale-Up (10.1016/j.algal.2024.103510)
        ("A37", "UnitConv+Env", "Bioprocess Scale-Up", "10.1016/j.algal.2024.103510",
         "Broth dynamic viscosity at 25 \u00b0C and pH 7.0 was 12.0 mPa*s in a 500 L pilot tank.",
         "broth_viscosity", "Schizochytrium sp.", "Pa * s", 0.012, None, None, 25.0, 7.0, None),
        ("A38", "PlusMinus+Env", "Bioprocess Scale-Up", "10.1016/j.algal.2024.103510",
         "Lipid content at 25 \u00b0C and pH 7.0 was 48.0 \u00b1 3.5 % dry cell weight.",
         "lipid_content", "Schizochytrium sp.", "percent", 48.0, 44.5, 51.5, 25.0, 7.0, None),
        ("A39", "UnitConv+Env", "Bioprocess Scale-Up", "10.1016/j.algal.2024.103510",
         "In the 500 L pilot tank at 25 \u00b0C and pH 7.0, impeller turnover was 3.0 min^-1.",
         "impeller_turnover", "Schizochytrium sp.", "1 / hour", 180.0, None, None, 25.0, 7.0, None),
        ("A40", "Scalar+Env", "Bioprocess Scale-Up", "10.1016/j.algal.2024.103510",
         "Final dry biomass titer at 25 \u00b0C and pH 7.0 reached 85.0 g/L after 96 h.",
         "biomass_titer", "Schizochytrium sp.", "kg / m**3", 85.0, None, None, 25.0, 7.0, None),
    ]

    for cid, cat, dom, doi, txt, ent, sys_name, unit, exp_v, exp_min, exp_max, tc, ph_v, pb in raw_a:
        cases.append(
            BenchmarkCase(
                case_id=cid,
                group="A_GROUNDED",
                category=cat,
                domain=dom,
                doi=doi,
                paper_text=txt,
                spec=RequiredParameterSpec(
                    entity_name=ent,
                    target_system=sys_name,
                    expected_unit=unit,
                ),
                expected_value=exp_v,
                expected_min=exp_min,
                expected_max=exp_max,
                expected_temp_c=tc,
                expected_ph=ph_v,
                expected_pressure_bar=pb,
            )
        )

    # ------------------------------------------------------------------
    # Group B: 10 Adversarial / Abstention / Quarantine Rejection Cases
    # ------------------------------------------------------------------
    # B01-B04: Missing Parameter Cases (must abstain -> ParameterGap)
    missing_specs = [
        ("B01", "MissingParam", "Bioprocess Fermentation", "10.1016/j.biortech.2024.130101",
         "E. coli was grown in a 5 L reactor at 37 \u00b0C and pH 6.8 for 24 h with 20 g/L glucose feed.",
         "saturation_constant_ks", "Escherichia coli", "g / L"),
        ("B02", "MissingParam", "Thermochemical SMR", "10.1016/j.ijhydene.2024.20106",
         "The primary reformer operated at 850 \u00b0C and 28 bar with steam-to-carbon ratio 3.0.",
         "catalyst_pore_tortuosity", "SMR Hydrogen Plant", "dimensionless"),
        ("B03", "MissingParam", "Downstream Biopolymer", "10.1016/j.algal.2023.103103",
         "Seaweed was milled for 30 min and washed at 20 \u00b0C before alkaline extraction at pH 12.0.",
         "mannuronic_guluronic_ratio", "Saccharina latissima", "dimensionless"),
        ("B04", "MissingParam", "Enzymatic Kinetics", "10.1016/j.enzmictec.2023.110105",
         "Enzymatic hydrolysis was conducted at 50 \u00b0C and pH 4.8 in 100 mL shake flasks at 200 rpm.",
         "inhibition_constant_ki", "Trichoderma reesei cellulase", "g / L"),
    ]
    for cid, cat, dom, doi, txt, ent, sys_name, unit in missing_specs:
        cases.append(
            BenchmarkCase(
                case_id=cid,
                group="B_ADVERSARIAL",
                category=cat,
                domain=dom,
                doi=doi,
                paper_text=txt,
                spec=RequiredParameterSpec(entity_name=ent, target_system=sys_name, expected_unit=unit),
            )
        )

    # B05-B07: Dimensionality Mismatch Cases (number near keyword, wrong dimension -> ParameterGap)
    dim_specs = [
        ("B05", "DimMismatch", "Bioprocess Fermentation", "10.1016/j.biortech.2024.130101",
         "The specific_growth_rate experiment used a biomass yield of 0.48 g/g and temperature 37 \u00b0C.",
         "specific_growth_rate", "Escherichia coli", "1 / hour"),
        ("B06", "DimMismatch", "Enzymatic Kinetics", "10.1016/j.enzmictec.2023.110105",
         "The activation_energy assay measured a first-order rate constant of 0.05 s^-1 at 50 \u00b0C.",
         "activation_energy", "Trichoderma reesei cellulase", "kJ / mol"),
        ("B07", "DimMismatch", "Downstream Purification", "10.1016/j.chroma.2024.464104",
         "The eluate_viscosity buffer was held at 22 \u00b0C for 4 h at 2.5 bar pressure.",
         "eluate_viscosity", "Monoclonal Antibody", "Pa * s"),
    ]
    for cid, cat, dom, doi, txt, ent, sys_name, unit in dim_specs:
        cases.append(
            BenchmarkCase(
                case_id=cid,
                group="B_ADVERSARIAL",
                category=cat,
                domain=dom,
                doi=doi,
                paper_text=txt,
                spec=RequiredParameterSpec(entity_name=ent, target_system=sys_name, expected_unit=unit),
            )
        )

    # B08-B10: Provenance / Integrity Violation Cases (invalid DOI, short snippet, inconsistent range)
    cases.append(
        BenchmarkCase(
            case_id="B08",
            group="B_ADVERSARIAL",
            category="InvalidDOI",
            domain="Bioprocess Fermentation",
            doi="http://blog.example.com/ecoli-post",
            paper_text="E. coli growth rate was 0.55 1/h.",
            spec=RequiredParameterSpec(entity_name="specific_growth_rate", target_system="Escherichia coli", expected_unit="1 / hour"),
            adversarial_candidate=RawExtractedCandidate(
                entity_name="specific_growth_rate",
                target_system="Escherichia coli",
                raw_value=0.55,
                raw_unit="1 / hour",
                source_doi="http://blog.example.com/ecoli-post",
                source_snippet="E. coli specific growth rate was measured at 0.55 1/h in shake flask.",
                extraction_confidence=0.90,
            ),
        )
    )
    cases.append(
        BenchmarkCase(
            case_id="B09",
            group="B_ADVERSARIAL",
            category="ShortSnippet",
            domain="Thermochemical SMR",
            doi="10.1016/j.ijhydene.2024.20106",
            paper_text="28 bar",
            spec=RequiredParameterSpec(entity_name="reformer_pressure", target_system="SMR Hydrogen Plant", expected_unit="bar"),
            adversarial_candidate=RawExtractedCandidate(
                entity_name="reformer_pressure",
                target_system="SMR Hydrogen Plant",
                raw_value=28.0,
                raw_unit="bar",
                source_doi="10.1016/j.ijhydene.2024.20106",
                source_snippet="28 bar",
                extraction_confidence=0.90,
            ),
        )
    )
    cases.append(
        BenchmarkCase(
            case_id="B10",
            group="B_ADVERSARIAL",
            category="InconsistentRange",
            domain="Bioprocess Fermentation",
            doi="10.1016/j.biortech.2024.130101",
            paper_text="Nominal 0.95 h^-1 outside [0.38, 0.52].",
            spec=RequiredParameterSpec(entity_name="specific_growth_rate", target_system="Escherichia coli", expected_unit="1 / hour"),
            adversarial_candidate=RawExtractedCandidate(
                entity_name="specific_growth_rate",
                target_system="Escherichia coli",
                raw_value=0.95,
                raw_value_min=0.38,
                raw_value_max=0.52,
                raw_unit="1 / hour",
                source_doi="10.1016/j.biortech.2024.130101",
                source_snippet="The specific growth rate ranged from 0.38 to 0.52 h^-1 at 37 C.",
                extraction_confidence=0.90,
            ),
        )
    )

    return cases


def _rel_close(a: Optional[float], b: Optional[float], rel_tol: float = 1e-3) -> bool:
    if a is None or b is None:
        return False
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=1e-6)


def run_blind_50_audit(write_artifacts: bool = True) -> Dict[str, Any]:
    cases = _build_cases()
    assert len(cases) == 50, f"Expected 50 cases, got {len(cases)}"

    case_by_key = {(c.spec.entity_name, c.spec.target_system): c for c in cases}

    # Isolated in-memory SQLite DB for Group A (Cold -> Warm) and fresh DB for Group B adversarial cases
    engine = ScaleUpRAGEngine(db_url="sqlite:///:memory:", search_fn=lambda _q: [])

    records: List[Dict[str, Any]] = []
    tp = 0
    fp = 0
    range_total = 0
    range_correct = 0
    env_total = 0
    env_correct = 0
    adv_blocked = 0
    cold_latencies_ms: List[float] = []
    warm_latencies_ms: List[float] = []

    # Pass 1: Cold Blind Extraction + Quarantine + Write-Back
    for c in cases:
        active_engine = engine if c.group == "A_GROUNDED" else ScaleUpRAGEngine(db_url="sqlite:///:memory:", search_fn=lambda _q: [])

        def _case_extractor(spec: RequiredParameterSpec, papers: List[Dict[str, Any]], _c: BenchmarkCase = c) -> Optional[RawExtractedCandidate]:
            if _c.adversarial_candidate is not None:
                return _c.adversarial_candidate
            return _extract_via_regex(spec, papers)

        t0 = time.perf_counter()
        manifest = active_engine.resolve_simulation_parameters(
            prompt=f"Benchmark {c.case_id}",
            required_specs=[c.spec],
            llm_extractor_fn=_case_extractor,
            search_fn=lambda _q, _c=c: [{"doi": _c.doi, "title": f"{_c.domain} ({_c.doi})", "abstractText": _c.paper_text}],
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        cold_latencies_ms.append(dt_ms)

        key = c.spec.entity_name
        grounded = manifest.grounded_parameters.get(key)
        gap = manifest.parameter_gaps.get(key)

        if c.group == "A_GROUNDED":
            val_ok = grounded is not None and _rel_close(grounded.value_normalized, c.expected_value)
            if val_ok:
                tp += 1
            elif grounded is not None:
                fp += 1

            is_range = c.expected_min is not None and c.expected_max is not None
            if is_range:
                range_total += 1
                if grounded is not None and _rel_close(grounded.value_min, c.expected_min) and _rel_close(grounded.value_max, c.expected_max):
                    range_correct += 1

            has_env = (c.expected_temp_c is not None) or (c.expected_ph is not None) or (c.expected_pressure_bar is not None)
            if has_env:
                env_total += 1
                if grounded is not None:
                    t_ok = (c.expected_temp_c is None) or _rel_close(grounded.envelope.temperature_c, c.expected_temp_c)
                    ph_ok = (c.expected_ph is None) or _rel_close(grounded.envelope.ph, c.expected_ph)
                    p_ok = (c.expected_pressure_bar is None) or _rel_close(grounded.envelope.pressure_bar, c.expected_pressure_bar)
                    if t_ok and ph_ok and p_ok:
                        env_correct += 1

            records.append({
                "case_id": c.case_id,
                "group": c.group,
                "category": c.category,
                "domain": c.domain,
                "entity_name": key,
                "doi": c.doi,
                "expected_value": c.expected_value,
                "expected_min": c.expected_min,
                "expected_max": c.expected_max,
                "expected_unit": c.spec.expected_unit,
                "extracted_value": grounded.value_normalized if grounded else None,
                "extracted_min": grounded.value_min if grounded else None,
                "extracted_max": grounded.value_max if grounded else None,
                "envelope": grounded.envelope.model_dump() if grounded else None,
                "snippet": grounded.source_snippet if grounded else None,
                "passed": bool(val_ok),
                "cold_ms": round(dt_ms, 3),
            })
        else:
            blocked = grounded is None and gap is not None
            if blocked:
                adv_blocked += 1
            else:
                fp += 1
            records.append({
                "case_id": c.case_id,
                "group": c.group,
                "category": c.category,
                "domain": c.domain,
                "entity_name": key,
                "doi": c.doi,
                "expected_value": "ABSTAIN / REJECT",
                "extracted_value": grounded.value_normalized if grounded else "ParameterGap",
                "passed": bool(blocked),
                "cold_ms": round(dt_ms, 3),
            })

    # Pass 2: Warm SQLite Read-Through Cache Latency on Group A
    for c in cases:
        if c.group != "A_GROUNDED":
            continue
        t0 = time.perf_counter()
        m_warm = engine.resolve_simulation_parameters(
            prompt=f"Warm {c.case_id}",
            required_specs=[c.spec],
            llm_extractor_fn=None,
        )
        if m_warm.cache_hit_count == 1:
            warm_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / 40.0
    range_acc = range_correct / range_total if range_total > 0 else 0.0
    env_comp = env_correct / env_total if env_total > 0 else 0.0
    adv_rate = adv_blocked / 10.0
    cold_avg_ms = sum(cold_latencies_ms) / len(cold_latencies_ms)
    warm_avg_ms = sum(warm_latencies_ms) / len(warm_latencies_ms)

    summary = {
        "total_cases": len(cases),
        "group_a_grounded": 40,
        "group_b_adversarial": 10,
        "true_positives": tp,
        "false_positives": fp,
        "quarantine_precision": round(precision, 4),
        "extraction_conversion_recall": round(recall, 4),
        "range_cases_total": range_total,
        "range_cases_correct": range_correct,
        "range_bound_accuracy": round(range_acc, 4),
        "envelope_cases_total": env_total,
        "envelope_cases_correct": env_correct,
        "operating_envelope_completeness": round(env_comp, 4),
        "adversarial_blocked": adv_blocked,
        "adversarial_block_rate": round(adv_rate, 4),
        "cold_avg_latency_ms": round(cold_avg_ms, 3),
        "warm_avg_latency_ms": round(warm_avg_ms, 3),
    }

    payload = {"summary": summary, "cases": records}

    if write_artifacts:
        art_dir = Path(__file__).resolve().parent.parent / ".artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        with open(art_dir / "blind_50_param_audit.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        md_lines = [
            "# 50-Parameter Blind Extraction & Epistemic Quarantine Audit",
            "",
            "## Executive Summary (Isolated `sqlite:///:memory:` Cold Run)",
            "",
            "| Metric | Result | Target |",
            "|---|---|---|",
            f"| Quarantine Precision | **{precision * 100:.1f}%** ({tp}/{tp + fp}) | 100.0% |",
            f"| Extraction & Conversion Recall (Group A) | **{recall * 100:.1f}%** ({tp}/40) | >= 95.0% |",
            f"| Range / ± Bound Accuracy | **{range_acc * 100:.1f}%** ({range_correct}/{range_total}) | >= 95.0% |",
            f"| Operating Envelope Completeness | **{env_comp * 100:.1f}%** ({env_correct}/{env_total}) | >= 95.0% |",
            f"| Adversarial Abstention / Quarantine Block Rate (Group B) | **{adv_rate * 100:.1f}%** ({adv_blocked}/10) | 100.0% |",
            f"| Cold-Miss Avg Latency | **{cold_avg_ms:.2f} ms** | — |",
            f"| Warm SQLite Read-Through Avg Latency | **{warm_avg_ms:.2f} ms** | — |",
            "",
            "## All 50 Audit Cases",
            "",
            "| ID | Group | Category | Entity | Expected | Extracted | Status |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in records:
            exp_s = f"{r['expected_value']} [{r.get('expected_min')}, {r.get('expected_max')}]" if r.get("expected_min") is not None else str(r["expected_value"])
            ext_s = f"{r['extracted_value']} [{r.get('extracted_min')}, {r.get('extracted_max')}]" if r.get("extracted_min") is not None else str(r["extracted_value"])
            st = "PASS" if r["passed"] else "FAIL"
            md_lines.append(f"| {r['case_id']} | {r['group']} | {r['category']} | `{r['entity_name']}` | {exp_s} | {ext_s} | {st} |")

        with open(art_dir / "BLIND_50_PARAM_AUDIT_REPORT.md", "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")

    return payload


def main() -> None:
    res = run_blind_50_audit(write_artifacts=True)
    s = res["summary"]
    print("=== 50-Parameter Blind Extraction & Epistemic Quarantine Audit ===")
    print(f"Quarantine Precision           : {s['quarantine_precision'] * 100:.1f}% ({s['true_positives']}/{s['true_positives'] + s['false_positives']})")
    print(f"Extraction & Conversion Recall : {s['extraction_conversion_recall'] * 100:.1f}% ({s['true_positives']}/40)")
    print(f"Range Bound Accuracy           : {s['range_bound_accuracy'] * 100:.1f}% ({s['range_cases_correct']}/{s['range_cases_total']})")
    print(f"Operating Envelope Completeness: {s['operating_envelope_completeness'] * 100:.1f}% ({s['envelope_cases_correct']}/{s['envelope_cases_total']})")
    print(f"Adversarial Block Rate         : {s['adversarial_block_rate'] * 100:.1f}% ({s['adversarial_blocked']}/10)")
    print(f"Cold vs Warm Latency           : {s['cold_avg_latency_ms']:.2f} ms -> {s['warm_avg_latency_ms']:.2f} ms")


if __name__ == "__main__":
    main()
