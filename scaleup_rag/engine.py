from typing import List, Optional, Callable, Dict
from .schemas import (
    RequiredParameterSpec,
    RawExtractedCandidate,
    GroundedParameter,
    ParameterGap,
    SimulationManifestPayload
)
from .database import ParameterDatabase
from .research_client import search_europe_pmc, extract_candidate_from_literature
from .quarantine_gate import validate_and_normalize
from . import llm_bridge

def _build_literature_query(spec: RequiredParameterSpec) -> str:
    STOP_TOKENS = {"constant", "coefficient", "parameter", "value", "specific"}
    tokens = [t for t in spec.entity_name.lower().split("_") if t not in STOP_TOKENS]
    if not tokens:
        tokens = [spec.entity_name.replace("_", " ")]
    keyword_clause = " AND ".join(tokens)
    return f'"{spec.target_system}" AND ({keyword_clause})'

class ScaleUpRAGEngine:
    def __init__(
        self,
        db_url: Optional[str] = None,
        search_fn: Optional[Callable[[str], List[Dict]]] = None
    ):
        self.db = ParameterDatabase(db_url=db_url)
        self.default_search_fn = search_fn or search_europe_pmc

    def resolve_simulation_parameters(
        self,
        prompt: str,
        required_specs: List[RequiredParameterSpec],
        llm_extractor_fn: Optional[Callable[[RequiredParameterSpec, List[Dict]], Optional[RawExtractedCandidate]]] = None,
        search_fn: Optional[Callable[[str], List[Dict]]] = None
    ) -> SimulationManifestPayload:
        grounded_parameters: Dict[str, GroundedParameter] = {}
        parameter_gaps: Dict[str, ParameterGap] = {}
        cache_hit_count = 0
        writeback_count = 0
        gap_count = 0

        active_search_fn = search_fn or self.default_search_fn

        # 1. Fast Local Read-Through Database Cache Lookup
        missing_specs: List[RequiredParameterSpec] = []
        for spec in required_specs:
            cached = self.db.lookup_parameter(spec)
            if cached is not None:
                grounded_parameters[spec.entity_name] = cached
                cache_hit_count += 1
            else:
                missing_specs.append(spec)

        # Fast path: If all specs hit cache, return immediately (< 5ms)
        if not missing_specs:
            return SimulationManifestPayload(
                prompt=prompt,
                grounded_parameters=grounded_parameters,
                parameter_gaps=parameter_gaps,
                cache_hit_count=cache_hit_count,
                writeback_count=writeback_count,
                gap_count=gap_count
            )

        # 2. Autonomous Concurrent Literature Search for Cache Misses
        from concurrent.futures import ThreadPoolExecutor, as_completed

        paper_cache: Dict[str, List[Dict]] = {}

        def _get_papers(query: str) -> List[Dict]:
            if query not in paper_cache:
                paper_cache[query] = active_search_fn(query)
            return paper_cache[query]

        def _search_and_extract(spec: RequiredParameterSpec):
            search_query = _build_literature_query(spec)
            papers = _get_papers(search_query)
            cand = extract_candidate_from_literature(spec, papers, llm_extractor_fn=llm_extractor_fn)
            if cand is not None:
                validated = validate_and_normalize(cand, spec)
                return spec, validated
            return spec, None

        with ThreadPoolExecutor(max_workers=min(len(missing_specs), 4)) as executor:
            future_to_spec = {executor.submit(_search_and_extract, s): s for s in missing_specs}
            for future in as_completed(future_to_spec):
                spec, validated = future.result()
                if validated is not None:
                    self.db.write_back_parameter(validated)
                    grounded_parameters[spec.entity_name] = validated
                    writeback_count += 1
                else:
                    parameter_gaps[spec.entity_name] = ParameterGap(
                        entity_name=spec.entity_name,
                        target_system=spec.target_system,
                        expected_unit=spec.expected_unit,
                        reason="No dimensionally valid empirical parameter with DOI provenance found in DB or literature.",
                        required_evidence=f"Experimental measurement of {spec.entity_name} ({spec.expected_unit}) for {spec.target_system}."
                    )
                    gap_count += 1

        return SimulationManifestPayload(
            prompt=prompt,
            grounded_parameters=grounded_parameters,
            parameter_gaps=parameter_gaps,
            cache_hit_count=cache_hit_count,
            writeback_count=writeback_count,
            gap_count=gap_count
        )

    def run_from_prompt(
        self,
        prompt: str,
        search_fn: Optional[Callable[[str], List[Dict]]] = None,
        llm_extractor_fn: Optional[Callable[[RequiredParameterSpec, List[Dict]], Optional[RawExtractedCandidate]]] = None,
        decomposer_fn: Optional[Callable[[str], List[RequiredParameterSpec]]] = None
    ) -> SimulationManifestPayload:
        decomposer = decomposer_fn or llm_bridge.decompose_prompt_to_specs
        specs = decomposer(prompt)
        extractor = llm_extractor_fn or llm_bridge.live_llm_extractor
        return self.resolve_simulation_parameters(
            prompt=prompt,
            required_specs=specs,
            llm_extractor_fn=extractor,
            search_fn=search_fn
        )
