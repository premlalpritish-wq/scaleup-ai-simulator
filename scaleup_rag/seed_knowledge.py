import os
import re
import json
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from .schemas import (
    RawExtractedCandidate,
    RequiredParameterSpec,
    OperatingEnvelope
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

    return {
        "total_evaluated": total_count,
        "total_candidates": total_count,
        "json_params_scanned": json_params_count,
        "passed_quarantine": passed_count,
        "rejected_by_quarantine": rejected_count,
        "newly_written_to_db": written_count,
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
