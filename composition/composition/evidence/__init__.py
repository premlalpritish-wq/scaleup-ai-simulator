"""Literature-based investigation of quantities a model could not resolve.

This package records evidence, scores compatibility against the target process
under declared rules, and reports what is present, absent and conflicting. It
does not merge anything into a model, settle a conflict, or decide that two
wordings mean the same thing. See ``candidate`` for the record schema and
``sourcing`` for why each condition carries a quote from its own publication.
"""

"""Literature-based investigation of quantities a model could not resolve.

This package records evidence, scores compatibility against the target process
under declared rules, and reports what is present, absent and conflicting. It
does not merge anything into a model, settle a conflict, or decide that two
wordings mean the same thing. See ``candidate`` for the record schema and
``sourcing`` for why each condition carries a quote from its own publication.
"""

from typing import Any

_CANDIDATE_EXPORTS = {
    "CRITICAL_DIMENSIONS",
    "TARGET_PASSAGES",
    "TARGET_PROCESS",
    "VALIDATION_CRITERIA",
    "CandidateFinding",
    "CompatibilityAssessment",
    "DimensionVerdict",
    "ExtractionConfidence",
    "Independence",
    "Provenance",
    "SourceLocation",
    "UncertaintyRecord",
    "ValidationCriterion",
    "ValidationReport",
    "Verdict",
    "assess",
    "candidates_for",
    "catalogue_payload",
    "validate",
}

_CATALOGUE_EXPORTS = {
    "FINDINGS",
    "REGISTERED_MODEL_ID",
    "SEARCH_SCOPE",
    "TARGETS",
    "ZIELINSKI_RECORD",
    "findings_for_port",
    "inventory",
    "main",
    "missing_information_required",
}

_CONFLICTS_EXPORTS = {
    "Conflict",
    "ConflictKind",
    "RecordExamined",
    "detect",
    "summarise",
}

_SOURCING_EXPORTS = {
    "DIMENSION_ORDER",
    "IDENTITY_DIMENSIONS",
    "NUMERIC_DIMENSIONS",
    "Condition",
    "Match",
    "TargetPassage",
    "TargetSource",
    "compare",
    "compare_all",
    "load_target_source",
    "target_conditions",
}


def __getattr__(name: str) -> Any:
    if name in _CANDIDATE_EXPORTS:
        from . import candidate
        return getattr(candidate, name)
    if name in _CATALOGUE_EXPORTS:
        from . import catalogue
        return getattr(catalogue, name)
    if name in _CONFLICTS_EXPORTS:
        from . import conflicts
        return getattr(conflicts, name)
    if name in _SOURCING_EXPORTS:
        from . import sourcing
        return getattr(sourcing, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CRITICAL_DIMENSIONS",
    "CandidateFinding",
    "CompatibilityAssessment",
    "Condition",
    "Conflict",
    "ConflictKind",
    "DIMENSION_ORDER",
    "DimensionVerdict",
    "ExtractionConfidence",
    "FINDINGS",
    "IDENTITY_DIMENSIONS",
    "Independence",
    "Match",
    "NUMERIC_DIMENSIONS",
    "Provenance",
    "REGISTERED_MODEL_ID",
    "RecordExamined",
    "SEARCH_SCOPE",
    "SourceLocation",
    "TARGET_PASSAGES",
    "TARGET_PROCESS",
    "TARGETS",
    "TargetPassage",
    "TargetSource",
    "UncertaintyRecord",
    "VALIDATION_CRITERIA",
    "ValidationCriterion",
    "ValidationReport",
    "Verdict",
    "ZIELINSKI_RECORD",
    "assess",
    "candidates_for",
    "catalogue_payload",
    "compare",
    "compare_all",
    "detect",
    "findings_for_port",
    "inventory",
    "load_target_source",
    "main",
    "missing_information_required",
    "summarise",
    "target_conditions",
    "validate",
]