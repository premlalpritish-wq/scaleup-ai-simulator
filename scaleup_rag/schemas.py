from pydantic import BaseModel, Field
from typing import Any, Optional, Dict, List, Literal

class OperatingEnvelope(BaseModel):
    temperature_c: Optional[float] = None
    ph: Optional[float] = None
    pressure_bar: Optional[float] = None
    shear_rate_s_inv: Optional[float] = None
    substrate: Optional[str] = None
    medium_or_catalyst: Optional[str] = None
    notes: Optional[str] = None

class RequiredParameterSpec(BaseModel):
    entity_name: str = Field(..., description="Snake_case identifier, e.g., 'dynamic_viscosity' or 'alginate_extraction_yield'")
    target_system: str = Field(..., description="Organism, material, or chemical species, e.g., 'Saccharina latissima'")
    expected_unit: str = Field(..., description="Pint-compatible target unit, e.g., 'Pa * s', 'dimensionless', '1 / s'")
    aliases: List[str] = Field(default_factory=list, description="Alternative parameter names or symbols")
    envelope_constraints: OperatingEnvelope = Field(default_factory=OperatingEnvelope)

class RawExtractedCandidate(BaseModel):
    entity_name: str
    target_system: str
    raw_value: float
    raw_value_min: Optional[float] = None
    raw_value_max: Optional[float] = None
    raw_unit: str
    uncertainty: Optional[float] = None
    envelope: OperatingEnvelope = Field(default_factory=OperatingEnvelope)
    source_doi: str
    source_snippet: str = Field(..., description="Exact verbatim quote or table row from the paper where the number appears")
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)

class GroundedParameter(BaseModel):
    entity_name: str
    target_system: str
    value_normalized: float
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    unit_normalized: str
    raw_value: float
    raw_value_min: Optional[float] = None
    raw_value_max: Optional[float] = None
    raw_unit: str
    uncertainty: Optional[float] = None
    envelope: OperatingEnvelope
    source_doi: str
    source_snippet: str
    verification_tier: Literal["tier_0_internal_bench", "tier_1_quarantine", "tier_2_verified"]
    origin: Literal["database_cache_hit", "live_research_writeback"]

    @property
    def value(self) -> float:
        return self.value_normalized

    @property
    def value_nominal(self) -> float:
        return self.value_normalized

class ParameterGap(BaseModel):
    entity_name: str
    target_system: str
    expected_unit: str
    status: Literal["unverified_hypothesis"] = "unverified_hypothesis"
    reason: str
    required_evidence: str
    fallback_hypothesis_value: Optional[float] = None

class PhysicalInvariantSpec(BaseModel):
    law_id: str = Field(..., description="Unique invariant identifier, e.g., 'SECOND_LAW_PINCH'")
    domain: Literal[
        "thermodynamics",
        "kinetics_equilibrium",
        "catalysis_materials",
        "hydraulics_phase",
        "bioprocess",
    ]
    governing_equation: str = Field(..., description="Machine-readable formula description")
    threshold_parameters: Dict[str, float] = Field(default_factory=dict)
    remediation_action: str = Field(..., description="Compiler action when violated")
    doi: str
    verbatim_quote: str


class SimulationManifestPayload(BaseModel):
    prompt: str
    grounded_parameters: Dict[str, GroundedParameter]
    parameter_gaps: Dict[str, ParameterGap]
    cache_hit_count: int
    writeback_count: int
    gap_count: int


class DomainSkillSpec(BaseModel):
    domain_id: str
    governing_laws: List[str]
    rag_scope: Dict[str, Any]
    allowed_archetypes: List[str]
    few_shot_derivations: List[Dict[str, Any]]
    invariant_checks: List[str]


class ValidatedWorkedTraceSpec(BaseModel):
    trace_id: str
    domain_id: str
    prompt: str
    derivation_trace: str
    topology_manifest_json: Dict[str, Any]
    perturbation_passed: bool = True
