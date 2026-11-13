import pint
from typing import Optional
from .schemas import RawExtractedCandidate, RequiredParameterSpec, GroundedParameter

ureg = pint.UnitRegistry()

def validate_and_normalize(
    candidate: RawExtractedCandidate,
    spec: RequiredParameterSpec
) -> Optional[GroundedParameter]:
    # Rule 1: Provenance & citation hygiene
    doi_clean = candidate.source_doi.strip()
    snippet_clean = candidate.source_snippet.strip()
    if doi_clean.startswith("10."):
        tier = "tier_1_quarantine"
    elif doi_clean.startswith(("dissertation://", "bench://")):
        tier = "tier_0_internal_bench"
    else:
        return None

    if len(snippet_clean) < 15:
        return None

    if not candidate.raw_unit.strip():
        return None

    # Rule 2: Physical dimensionality & SI/target unit normalization (including affine temperature & ranges)
    try:
        target_unit = ureg.Unit(spec.expected_unit)

        def _convert_val(val: float) -> float:
            q = ureg.Quantity(val, candidate.raw_unit)
            if not q.check(target_unit.dimensionality):
                raise pint.DimensionalityError(q.units, target_unit)
            return float(q.to(target_unit).magnitude)

        val_norm = _convert_val(candidate.raw_value)
        val_min_norm = _convert_val(candidate.raw_value_min) if candidate.raw_value_min is not None else None
        val_max_norm = _convert_val(candidate.raw_value_max) if candidate.raw_value_max is not None else None

        if val_min_norm is not None and val_max_norm is not None:
            if val_min_norm > val_max_norm:
                val_min_norm, val_max_norm = val_max_norm, val_min_norm
            if val_norm < val_min_norm - 1e-9 or val_norm > val_max_norm + 1e-9:
                return None
    except (pint.DimensionalityError, pint.UndefinedUnitError, Exception):
        return None

    # Rule 3: Construct verified GroundedParameter for database write-back
    return GroundedParameter(
        entity_name=spec.entity_name.lower(),
        target_system=spec.target_system,
        value_normalized=val_norm,
        value_min=val_min_norm,
        value_max=val_max_norm,
        unit_normalized=spec.expected_unit,
        raw_value=candidate.raw_value,
        raw_value_min=candidate.raw_value_min,
        raw_value_max=candidate.raw_value_max,
        raw_unit=candidate.raw_unit,
        uncertainty=candidate.uncertainty,
        envelope=candidate.envelope,
        source_doi=doi_clean,
        source_snippet=snippet_clean,
        verification_tier=tier,
        origin="live_research_writeback"
    )


validate_and_convert_candidate = validate_and_normalize
