"""Literature-based investigation of quantities a model could not resolve.

See :mod:`composition.evidence.candidate` for the record schema and the
compatibility rules, and :mod:`composition.evidence.catalogue` for the curated
findings. Nothing in this package writes to, imports from, or executes a model
package; it produces a proposal for a reader to accept, reject or act on.
"""

from .candidate import (  # noqa: F401
    CRITICAL_DIMENSIONS,
    TARGET_PROCESS,
    VALIDATION_CRITERIA,
    CandidateFinding,
    CompatibilityAssessment,
    ExtractionConfidence,
    ExperimentalConditions,
    Provenance,
    SourceLocation,
    UncertaintyRecord,
    ValidationCriterion,
    ValidationReport,
    Verdict,
    Match,
    assess,
    candidates_for,
    catalogue_payload,
    validate,
)
from .catalogue import (  # noqa: F401
    FINDINGS,
    SEARCH_SCOPE,
    TARGETS,
    findings_for_port,
    inventory,
    main,
)

__all__ = [
    "CandidateFinding",
    "CompatibilityAssessment",
    "CRITICAL_DIMENSIONS",
    "ExtractionConfidence",
    "ExperimentalConditions",
    "FINDINGS",
    "Match",
    "Provenance",
    "SEARCH_SCOPE",
    "SourceLocation",
    "TARGET_PROCESS",
    "TARGETS",
    "UncertaintyRecord",
    "VALIDATION_CRITERIA",
    "ValidationCriterion",
    "ValidationReport",
    "Verdict",
    "assess",
    "candidates_for",
    "catalogue_payload",
    "findings_for_port",
    "inventory",
    "main",
    "validate",
]