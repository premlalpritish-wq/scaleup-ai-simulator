"""10-Parameter Live Uncached EuropePMC Wild Extraction Audit.

Queries the live EuropePMC REST API over the network against an empty
in-memory SQLite database (sqlite:///:memory:) for 10 diverse biological and
chemical systems NOT pre-seeded in seed_knowledge.py.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from .engine import ScaleUpRAGEngine, _build_literature_query
from .llm_bridge import live_llm_extractor
from .quarantine_gate import ureg
from .research_client import search_europe_pmc
from .schemas import RequiredParameterSpec


WILD_SPECS: List[RequiredParameterSpec] = [
    RequiredParameterSpec(
        entity_name="specific_growth_rate",
        target_system="Corynebacterium glutamicum",
        expected_unit="1/h",
        aliases=["maximum specific growth rate", "specific growth rate", "mu_max", "growth rate"],
    ),
    RequiredParameterSpec(
        entity_name="specific_growth_rate",
        target_system="Yarrowia lipolytica",
        expected_unit="1/h",
        aliases=["maximum specific growth rate", "specific growth rate", "mu_max", "growth rate"],
    ),
    RequiredParameterSpec(
        entity_name="specific_growth_rate",
        target_system="Pichia pastoris",
        expected_unit="1/h",
        aliases=["specific growth rate", "mu_max", "growth rate"],
    ),
    RequiredParameterSpec(
        entity_name="specific_growth_rate",
        target_system="Chlorella vulgaris",
        expected_unit="1/d",
        aliases=["specific growth rate", "growth rate", "mu"],
    ),
    RequiredParameterSpec(
        entity_name="substrate_affinity",
        target_system="Clostridium acetobutylicum",
        expected_unit="g/L",
        aliases=["Ks", "Monod constant", "substrate saturation constant", "glucose concentration"],
    ),
    RequiredParameterSpec(
        entity_name="biomass_yield",
        target_system="Zymomonas mobilis",
        expected_unit="g/g",
        aliases=["biomass yield", "yield coefficient", "Y_X/S", "ethanol yield"],
    ),
    RequiredParameterSpec(
        entity_name="optimal_temperature",
        target_system="Aspergillus niger",
        expected_unit="degC",
        aliases=["temperature", "incubation temperature", "optimal temperature", "fermentation temperature"],
    ),
    RequiredParameterSpec(
        entity_name="optimal_ph",
        target_system="Lactobacillus plantarum",
        expected_unit="dimensionless",
        aliases=["initial pH", "optimal pH", "pH"],
    ),
    RequiredParameterSpec(
        entity_name="activation_energy",
        target_system="Water-gas shift",
        expected_unit="kJ/mol",
        aliases=["apparent activation energy", "activation energy", "Ea"],
    ),
    RequiredParameterSpec(
        entity_name="operating_pressure",
        target_system="Methanol synthesis",
        expected_unit="bar",
        aliases=["reaction pressure", "operating pressure", "pressure"],
    ),
]


def _norm_ws(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    return clean


def run_live_wild_audit() -> Dict[str, Any]:
    engine = ScaleUpRAGEngine(db_url="sqlite:///:memory:")
    fetched_by_doi: Dict[str, Dict[str, Any]] = {}
    papers_per_query: Dict[str, int] = {}

    def live_search_spy(query: str) -> List[Dict]:
        papers = search_europe_pmc(query)
        papers_per_query[query] = len(papers)
        for p in papers:
            doi = (p.get("doi") or "").strip()
            if doi:
                fetched_by_doi[doi] = p
        return papers

    results: List[Dict[str, Any]] = []
    grounded_count = 0
    abstained_count = 0
    quarantine_violations = 0

    for idx, spec in enumerate(WILD_SPECS, start=1):
        lit_query = _build_literature_query(spec)

        t0 = time.perf_counter()
        cold_manifest = engine.resolve_simulation_parameters(
            prompt=f"Live wild extraction audit #{idx}: {spec.target_system} {spec.entity_name}",
            required_specs=[spec],
            llm_extractor_fn=live_llm_extractor,
            search_fn=live_search_spy,
        )
        cold_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        t1 = time.perf_counter()
        warm_manifest = engine.resolve_simulation_parameters(
            prompt=f"Live wild warm cache check #{idx}: {spec.target_system} {spec.entity_name}",
            required_specs=[spec],
            llm_extractor_fn=live_llm_extractor,
            search_fn=lambda _q: [],
        )
        warm_ms = round((time.perf_counter() - t1) * 1000.0, 2)

        paper_count = papers_per_query.get(lit_query, 0)

        if spec.entity_name in cold_manifest.grounded_parameters:
            gp = cold_manifest.grounded_parameters[spec.entity_name]
            grounded_count += 1

            doi_in_fetched = gp.source_doi in fetched_by_doi
            quote_len_ok = len(gp.source_snippet.strip()) >= 15
            quote_in_paper = False
            if doi_in_fetched:
                p = fetched_by_doi[gp.source_doi]
                corpus = _norm_ws(f"{p.get('title', '')} {p.get('abstractText', '')} {p.get('fullTextExcerpt', '')}")
                quote_in_paper = _norm_ws(gp.source_snippet) in corpus

            try:
                q_norm = ureg.Quantity(gp.value_normalized, gp.unit_normalized)
                pint_valid = q_norm.check(ureg.Unit(spec.expected_unit).dimensionality)
            except Exception:
                pint_valid = False

            if not (doi_in_fetched and quote_len_ok and pint_valid):
                quarantine_violations += 1

            row: Dict[str, Any] = {
                "index": idx,
                "target_system": spec.target_system,
                "entity_name": spec.entity_name,
                "expected_unit": spec.expected_unit,
                "aliases": spec.aliases,
                "literature_query": lit_query,
                "papers_fetched": paper_count,
                "outcome": f"GROUNDED ({gp.verification_tier})",
                "cold_latency_ms": cold_ms,
                "warm_latency_ms": warm_ms,
                "warm_cache_hit": warm_manifest.cache_hit_count == 1,
                "value": gp.value_normalized,
                "value_min": gp.value_min,
                "value_max": gp.value_max,
                "normalized_unit": gp.unit_normalized,
                "raw_value": gp.raw_value,
                "raw_unit": gp.raw_unit,
                "envelope": {
                    "temperature_c": gp.envelope.temperature_c,
                    "ph": gp.envelope.ph,
                    "pressure_bar": gp.envelope.pressure_bar,
                },
                "source_doi": gp.source_doi,
                "verbatim_quote": gp.source_snippet,
                "checks": {
                    "doi_in_fetched_papers": doi_in_fetched,
                    "quote_len_ge_15": quote_len_ok,
                    "quote_substring_in_paper": quote_in_paper,
                    "pint_dimensionality_valid": pint_valid,
                },
            }
        else:
            gap = cold_manifest.parameter_gaps[spec.entity_name]
            abstained_count += 1
            row = {
                "index": idx,
                "target_system": spec.target_system,
                "entity_name": spec.entity_name,
                "expected_unit": spec.expected_unit,
                "aliases": spec.aliases,
                "literature_query": lit_query,
                "papers_fetched": paper_count,
                "outcome": "ABSTAINED (ParameterGap)",
                "cold_latency_ms": cold_ms,
                "warm_latency_ms": warm_ms,
                "warm_cache_hit": False,
                "gap_reason": gap.reason,
                "required_evidence": gap.required_evidence,
            }

        results.append(row)

    summary = {
        "total_queries": len(WILD_SPECS),
        "grounded_count": grounded_count,
        "abstained_count": abstained_count,
        "quarantine_violations": quarantine_violations,
        "results": results,
    }
    return summary


def main() -> None:
    summary = run_live_wild_audit()
    out_dir = Path(".artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "live_wild_10_audit.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        f"Live Wild EuropePMC Audit Complete: "
        f"{summary['grounded_count']}/{summary['total_queries']} GROUNDED, "
        f"{summary['abstained_count']}/{summary['total_queries']} ABSTAINED, "
        f"{summary['quarantine_violations']} quarantine violations."
    )
    for r in summary["results"]:
        if r["outcome"].startswith("GROUNDED"):
            print(
                f"[{r['index']:02d}] {r['target_system']} | {r['entity_name']} | "
                f"{r['outcome']} | {r['value']} {r['normalized_unit']} "
                f"(raw: {r['raw_value']} {r['raw_unit']}) | "
                f"DOI: {r['source_doi']} | "
                f"Cold: {r['cold_latency_ms']} ms | Warm: {r['warm_latency_ms']} ms"
            )
            print(f"     Quote: {r['verbatim_quote']}")
            print(f"     Env: {r['envelope']} | Checks: {r['checks']}")
        else:
            print(
                f"[{r['index']:02d}] {r['target_system']} | {r['entity_name']} | "
                f"{r['outcome']} | Papers: {r['papers_fetched']} | "
                f"Cold: {r['cold_latency_ms']} ms | Warm: {r['warm_latency_ms']} ms"
            )


if __name__ == "__main__":
    main()
