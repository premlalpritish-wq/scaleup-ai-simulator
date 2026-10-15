"""A deterministic, read-only registry of model specifications.

What registration means
-----------------------
Registration records that a specification artefact **exists**, is identified by
a stable id and version, and can be located and hashed. It establishes nothing
else. A registered model may be wrong. See
:data:`composition.registry.schema.SCIENTIFIC_STATUS`.

What registration refuses to do
-------------------------------
It does not infer a missing field. A model that declares no DOI gets an
explicitly unknown DOI with the reason attached, not a guess from the author
name. It does not touch a model package: files are read and hashed, never
written. It does not compose, revise or validate anything.

Unknown is a value
------------------
Every field is a :class:`TrackedField` carrying its origin. ``UNKNOWN`` means
the artefact does not state it. That is the honest answer and it is visible,
which is what makes the registry auditable rather than merely plausible.
"""

from .builder import (
    DIGEST_COVERAGE,
    FILE_COVERAGE,
    audit_references,
    build_registry,
    check_references,
    digest_file,
    digest_package,
    register_one,
)
from .schema import (
    SCIENTIFIC_STATUS,
    ArtefactDigest,
    DeclaredCondition,
    IssueKind,
    Origin,
    PortDependence,
    PortRecord,
    RegisteredModel,
    RegistrationIssue,
    TrackedField,
    collect_unknowns,
    declared,
    derived,
    summarise_variables,
    unknown,
)

__all__ = [
    "ArtefactDigest",
    "DIGEST_COVERAGE",
    "DeclaredCondition",
    "FILE_COVERAGE",
    "IssueKind",
    "Origin",
    "PortDependence",
    "PortRecord",
    "RegisteredModel",
    "RegistrationIssue",
    "SCIENTIFIC_STATUS",
    "TrackedField",
    "audit_references",
    "build_registry",
    "check_references",
    "collect_unknowns",
    "declared",
    "derived",
    "digest_file",
    "digest_package",
    "register_one",
    "summarise_variables",
    "unknown",
]