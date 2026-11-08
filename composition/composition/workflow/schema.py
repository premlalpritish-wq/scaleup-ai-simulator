"""Data models for the research-to-simulation workflow.

Every field that can be absent has an explicit state.  The three states are the
same ones the registry already uses:

``reported``
    The source states it, and the claim carries a verbatim quote.
``derived``
    Computed from reported values by a rule stated on the field.
``unknown``
    The source does not state it.  Never inferred, never defaulted to zero.

The workflow is deliberately not a yield model.  A numeric parameter may enter
:class:`ProtocolStep` only when the quote it rests on contains that value; the
builder refuses untraceable numbers instead of accepting a plausible one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

STATE_REPORTED = "reported"
STATE_DERIVED = "derived"
STATE_UNKNOWN = "unknown"
STATES = (STATE_REPORTED, STATE_DERIVED, STATE_UNKNOWN)

#: How far a claim travels from the requested organism.
SPECIFICITY_TARGET = "target_organism"
SPECIFICITY_ANALOGUE = "analogous_species"
SPECIFICITY_METHOD = "method_review"
SPECIFICITIES = (SPECIFICITY_TARGET, SPECIFICITY_ANALOGUE, SPECIFICITY_METHOD)

#: Claim kinds.  A hypothesis is not a finding, and an unresolved question is not
#: a negative finding.
CLAIM_KINDS = (
    "protocol_step",
    "reagent",
    "condition",
    "measurement",
    "quality_criterion",
    "result",
    "limitation",
    "hypothesis",
    "unresolved_question",
)


@dataclass(frozen=True)
class TrackedValue:
    """A value plus how the workflow knows it."""

    value: Any
    state: str
    unit: str = ""
    basis: str = ""
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"unknown value state {self.state!r}")
        if self.state == STATE_UNKNOWN and self.value is not None:
            raise ValueError("an unknown value must not carry a value")
        if self.state == STATE_REPORTED and not self.source_refs:
            raise ValueError("a reported value must name its source")

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "state": self.state,
            "unit": self.unit,
            "basis": self.basis,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class ProblemSpec:
    problem_id: str
    question: str
    organism: TrackedValue
    tissue: TrackedValue
    molecule: TrackedValue
    downstream: tuple[str, ...]
    constraints: tuple[str, ...]
    requested_outputs: tuple[str, ...]
    source_text: str
    extraction_method: str = "local_rules"
    unknowns: tuple[str, ...] = ()
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "question": self.question,
            "organism": self.organism.to_dict(),
            "tissue": self.tissue.to_dict(),
            "molecule": self.molecule.to_dict(),
            "downstream": list(self.downstream),
            "constraints": list(self.constraints),
            "requested_outputs": list(self.requested_outputs),
            "source_text": self.source_text,
            "extraction_method": self.extraction_method,
            "unknowns": list(self.unknowns),
            "blocked": self.blocked,
        }


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    authors: tuple[str, ...]
    year: str
    doi: str
    journal: str
    license: str
    url: str
    file: str
    role: str
    relevance_terms: tuple[str, ...]
    retrieved_via: str
    abstract: str = ""
    pmcid: str = ""
    pmid: str = ""
    content_sha256: str = ""
    text_path: str = ""
    section_count: int = 0
    extraction_method: str = ""
    acquisition_status: str = "not_acquired"
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "doi": self.doi,
            "journal": self.journal,
            "license": self.license,
            "url": self.url,
            "file": self.file,
            "role": self.role,
            "relevance_terms": list(self.relevance_terms),
            "retrieved_via": self.retrieved_via,
            "abstract": self.abstract,
            "pmcid": self.pmcid,
            "pmid": self.pmid,
            "content_sha256": self.content_sha256,
            "text_path": self.text_path,
            "section_count": self.section_count,
            "extraction_method": self.extraction_method,
            "acquisition_status": self.acquisition_status,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class TextSection:
    title: str
    path: str
    text: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "path": self.path,
            "start": self.start,
            "end": self.end,
            "characters": len(self.text),
        }


@dataclass(frozen=True)
class SourceText:
    source_id: str
    title: str
    text: str
    sections: tuple[TextSection, ...]
    extraction_method: str
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "characters": len(self.text),
            "extraction_method": self.extraction_method,
            "sections": [s.to_dict() for s in self.sections],
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    source_id: str
    quote: str
    section: str
    locator: Mapping[str, int]
    claim_type: str
    subject: str
    relation: str
    obj: str
    organism: str
    tissue: str
    specificity: str
    hypothesis: bool
    uncertainty: str
    supports_step: str
    value: float | None = None
    unit: str = ""

    def __post_init__(self) -> None:
        if self.claim_type not in CLAIM_KINDS:
            raise ValueError(f"unknown claim type {self.claim_type!r}")
        if self.specificity not in SPECIFICITIES:
            raise ValueError(f"unknown specificity {self.specificity!r}")
        if self.hypothesis and self.specificity == SPECIFICITY_TARGET:
            raise ValueError(
                "a direct target-organism claim is evidence, not a hypothesis"
            )
        if self.value is not None and not self.unit:
            raise ValueError("a numeric claim must carry a unit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "source_id": self.source_id,
            "quote": self.quote,
            "section": self.section,
            "locator": dict(self.locator),
            "claim_type": self.claim_type,
            "subject": self.subject,
            "relation": self.relation,
            "object": self.obj,
            "organism": self.organism,
            "tissue": self.tissue,
            "specificity": self.specificity,
            "hypothesis": self.hypothesis,
            "uncertainty": self.uncertainty,
            "supports_step": self.supports_step,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class StepParameter:
    parameter_id: str
    name: str
    value: float | None
    unit: str
    state: str
    basis: str
    source_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "state": self.state,
            "basis": self.basis,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class ProtocolStep:
    step_id: str
    order: int
    label: str
    action: str
    evidence_status: str
    claim_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    parameters: tuple[StepParameter, ...] = ()
    unknowns: tuple[str, ...] = ()
    notes: str = ""
    hypothesis: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "order": self.order,
            "label": self.label,
            "action": self.action,
            "evidence_status": self.evidence_status,
            "claim_ids": list(self.claim_ids),
            "source_ids": list(self.source_ids),
            "parameters": [p.to_dict() for p in self.parameters],
            "unknowns": list(self.unknowns),
            "notes": self.notes,
            "hypothesis": self.hypothesis,
        }


@dataclass(frozen=True)
class EncodedResearch:
    problem_id: str
    claims: tuple[EvidenceClaim, ...]
    steps: tuple[ProtocolStep, ...]
    tensions: tuple[Mapping[str, Any], ...]
    source_ids: tuple[str, ...]
    verification: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "claims": [c.to_dict() for c in self.claims],
            "steps": [s.to_dict() for s in self.steps],
            "tensions": [dict(t) for t in self.tensions],
            "source_ids": list(self.source_ids),
            "verification": dict(self.verification),
        }


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    model_version: str
    title: str
    model_kind: str
    problem: Mapping[str, Any]
    steps: tuple[ProtocolStep, ...]
    parameters: tuple[StepParameter, ...]
    unknowns: tuple[str, ...]
    hypotheses: tuple[str, ...]
    assumptions: tuple[str, ...]
    readiness: Mapping[str, Any]
    sources: tuple[Mapping[str, Any], ...]
    claims: tuple[EvidenceClaim, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "title": self.title,
            "model_kind": self.model_kind,
            "problem": dict(self.problem),
            "steps": [s.to_dict() for s in self.steps],
            "parameters": [p.to_dict() for p in self.parameters],
            "unknowns": list(self.unknowns),
            "hypotheses": list(self.hypotheses),
            "assumptions": list(self.assumptions),
            "readiness": dict(self.readiness),
            "sources": [dict(s) for s in self.sources],
            "claims": [c.to_dict() for c in self.claims],
        }


@dataclass(frozen=True)
class WorkflowDiagnostic:
    code: str
    severity: str
    message: str
    where: tuple[str, ...] = ()
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "where": list(self.where),
            "remediation": self.remediation,
        }


@dataclass
class WorkflowRun:
    problem: ProblemSpec
    sources: list[SourceRecord]
    encoded: EncodedResearch | None
    model: ModelSpec | None
    graph: Mapping[str, Any] | None
    execution: Mapping[str, Any] | None
    diagnostics: list[WorkflowDiagnostic] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    status: str = "failed"
    exit_code: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "problem": self.problem.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "encoded": self.encoded.to_dict() if self.encoded else None,
            "model": self.model.to_dict() if self.model else None,
            "graph": dict(self.graph) if self.graph else None,
            "execution": dict(self.execution) if self.execution else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "artifacts": dict(self.artifacts),
        }


def unknown_value(reason: str) -> TrackedValue:
    return TrackedValue(None, STATE_UNKNOWN, basis=reason)


def reported_value(
    value: Any, unit: str, basis: str, source_refs: Sequence[str]
) -> TrackedValue:
    return TrackedValue(value, STATE_REPORTED, unit=unit, basis=basis,
                        source_refs=tuple(source_refs))
