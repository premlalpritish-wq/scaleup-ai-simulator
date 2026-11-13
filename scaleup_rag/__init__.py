from .engine import ScaleUpRAGEngine
from .schemas import (
    OperatingEnvelope,
    RequiredParameterSpec,
    RawExtractedCandidate,
    GroundedParameter,
    ParameterGap,
    SimulationManifestPayload
)
from .llm_bridge import decompose_prompt_to_specs, live_llm_extractor

def seed_database(*args, **kwargs):
    from .seed_knowledge import seed_database as _seed
    return _seed(*args, **kwargs)
