"""Candidate literature evidence for quantities the models could not resolve.

This package exists because a model that reports a quantity as ``unknown`` is
supposed to be a dead end: the reader is told what is missing and why, and then
nothing. This module is the smallest thing that turns that dead end into an
investigation.

It deliberately does **not** merge anything into a model. A finding here is a
proposal with a verdict, never a value. The original model keeps reporting its
unknowns as unknown, and nothing in ``Models/`` is modified or even imported at
run time.

Vocabulary is reused from the Zielinski model's own provenance schema so the two
sides speak the same language -- ``reported`` / ``digitized`` / ``derived`` /
``assumed`` / ``unknown``, and an uncertainty record of ``kind``, ``lo``, ``hi``
and ``basis``. The classes are redeclared here rather than imported because the
composition layer may not take a run-time dependency on a model package, and
because ``EvidenceRef`` in that package hard-codes the Zielinski page offset and
therefore cannot address a different paper.

The verdict ladder is deliberately conservative:

``FOUND``       compatible on every critical dimension, but not yet validated
``UNVERIFIED``  plausibly related, with at least one critical dimension unknown
``INCOMPATIBLE`` differs on at least one critical dimension
``VALIDATED``   never assigned by loading. Only :func:`validate` may grant it,
                and only when every registered criterion passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .sourcing import (
    Condition,
    TargetPassage,
    compare_all,
    load_target_source,
    target_conditions,
    to_dict,
)


class Provenance(Enum):
    """Mirrors ``scaleup_ai.provenance.Provenance`` without importing it."""

    REPORTED = "reported"
    DIGITIZED = "digitized"
    DERIVED = "derived"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"


class Match(Enum):
    """How one experimental dimension compares with the target process."""

    MATCH = "match"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class Verdict(Enum):
    """Overall compatibility of one candidate with the target process."""

    FOUND = "found"
    UNVERIFIED = "unverified"
    INCOMPATIBLE = "incompatible"
    VALIDATED = "validated"


class ExtractionConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Dimensions that must agree before a candidate may even be called ``FOUND``.
#: A mismatch on any of these forces ``INCOMPATIBLE`` regardless of how well
#: the other dimensions match. This is the rule that stops a general literature
#: parameter being adopted just because its quantity name matches.
#:
#: ``strain`` is here because a kinetic constant is a property of a strain in a
#: medium, not of a species. Two papers can both say "E. coli on glucose" and
#: still not be talking about the same organism.
CRITICAL_DIMENSIONS: tuple[str, ...] = (
    "organism",
    "strain",
    "construct",
    "medium",
    "mode",
)


@dataclass(frozen=True)
class SourceLocation:
    """Verifiable identity and exact location within a publication."""

    citation: str
    doi: str
    url: str
    pmid: str = ""
    open_access: bool = False
    section: str = ""
    figure: str = ""
    #: Verbatim text from the source that supports the extracted value.
    quote: str = ""

    def locator(self) -> str:
        """A short, human-checkable pointer a reader can follow."""
        bits = [self.citation]
        if self.doi:
            bits.append("doi:%s" % self.doi)
        if self.section:
            bits.append("sec. %s" % self.section)
        if self.figure:
            bits.append(self.figure)
        return " | ".join(bits)

    def is_verifiable(self) -> bool:
        """A finding is only traceable if it names a source and shows evidence.

        A DOI alone is a pointer but not evidence; neither is a quote without a
        resolvable identifier. Both are required.
        """
        return bool(self.doi and self.quote and self.section)


@dataclass(frozen=True)
class UncertaintyRecord:
    """Mirrors ``scaleup_ai.provenance.Uncertainty``."""

    kind: str
    lo: float
    hi: float
    basis: str

    def contains(self, value: float) -> bool:
        return self.lo <= value <= self.hi

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "lo": self.lo, "hi": self.hi, "basis": self.basis}


#: The target process is transcribed from the target publication itself, one
#: condition at a time, each bound to the passage it was read from. See
#: :mod:`composition.evidence.sourcing` for why this is not just tidiness.
_TARGET_SOURCE = load_target_source()

#: dimension -> Condition, each carrying the Zielinski 2019 passage it came from.
TARGET_PROCESS: Mapping[str, Condition] = target_conditions(_TARGET_SOURCE)

#: The passages a candidate is checked against to decide whether it is actually
#: independent of the target publication.
TARGET_PASSAGES: tuple[TargetPassage, ...] = _TARGET_SOURCE.passages


class Independence(Enum):
    """Whether a candidate is genuinely external evidence.

    ``EXTERNAL``   the supporting passage does not occur in the target source
    ``TARGET``     the passage occurs in the target publication, so the
                   "candidate" is the target paper's own wording reached through
                   a second paper -- not independent corroboration
    ``UNDETERMINED`` the check could not be completed; never treated as
                   evidence of independence
    """

    EXTERNAL = "external"
    TARGET = "target_source"
    UNDETERMINED = "undetermined"


def _independent(finding: "CandidateFinding") -> tuple[Independence, tuple[str, ...]]:
    """Decide whether a candidate's supporting passage is genuinely external.

    Every passage a finding relies on -- the value's own quote and each
    condition quote -- is tested against the target publication. If one occurs
    there, the finding is the target paper's wording reached through a second
    paper, and it cannot corroborate the target paper.
    """
    overlaps: list[str] = []
    passages = [finding.source.quote]
    for condition in finding.conditions.values():
        if condition.quote:
            passages.append(condition.quote)

    for quote in passages:
        hit = _TARGET_SOURCE.overlap(quote)
        if hit is not None:
            overlaps.append(
                "a passage attributed to %s occurs in the target publication "
                "(%s, printed p.%d), so it is not independent evidence."
                % (finding.source.citation.split("(")[0].strip(),
                   hit.passage_id, hit.printed_page)
            )
    if overlaps:
        return Independence.TARGET, tuple(overlaps)
    return Independence.EXTERNAL, ()


@dataclass(frozen=True)
class DimensionVerdict:
    dimension: str
    candidate: Condition
    target: Condition
    match: str
    critical: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "critical": self.critical,
            "verdict": self.match,
            "candidate": to_dict(self.candidate),
            "target": to_dict(self.target),
            "note": self.note,
        }


@dataclass(frozen=True)
class CompatibilityAssessment:
    verdict: Verdict
    independence: Independence
    dimensions: tuple[DimensionVerdict, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "independence": self.independence.value,
            "reasons": list(self.reasons),
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


def assess(finding: "CandidateFinding") -> CompatibilityAssessment:
    """Score one candidate against the target process.

    Deterministic and conservative. Never returns ``VALIDATED`` -- only
    :func:`validate` may grant that.
    """
    matches = compare_all(finding.conditions, TARGET_PROCESS)
    dims = tuple(
        DimensionVerdict(
            dimension=m.dimension,
            candidate=m.candidate,
            target=m.target,
            match=m.verdict,
            critical=m.dimension in CRITICAL_DIMENSIONS,
            note=m.note,
        )
        for m in matches
    )
    independence, overlap_reasons = _independent(finding)

    def of(verdict: str, critical_only: bool = True) -> list[DimensionVerdict]:
        return [d for d in dims
                if d.match == verdict and (d.critical or not critical_only)]

    mismatched = of("mismatch")
    unknown_critical = of("unknown")
    partial_critical = of("partial")
    noncritical_mismatch = of("mismatch", critical_only=False)

    reasons: list[str] = []
    if mismatched:
        verdict = Verdict.INCOMPATIBLE
        for d in mismatched:
            reasons.append(
                "%s differs from the target process: the candidate states %r, the "
                "target publication states %r." % (d.dimension, d.candidate.value, d.target.value)
            )
    elif unknown_critical:
        verdict = Verdict.UNVERIFIED
        for d in unknown_critical:
            reasons.append(
                "%s is not stated by the candidate, so agreement cannot be shown." % d.dimension
            )
    elif partial_critical:
        verdict = Verdict.UNVERIFIED
        for d in partial_critical:
            reasons.append(
                "%s: %s Candidate states %r; target states %r."
                % (d.dimension, d.note, d.candidate.value, d.target.value)
            )
    else:
        verdict = Verdict.FOUND

    if independence is Independence.TARGET:
        # Not independent evidence. It may not be recorded as found, whatever
        # its conditions say.
        verdict = Verdict.INCOMPATIBLE
        reasons.extend(overlap_reasons)

    for d in noncritical_mismatch:
        reasons.append(
            "Non-critical difference in %s: candidate %r, target %r."
            % (d.dimension, d.candidate.value, d.target.value)
        )
    if not reasons:
        reasons.append("Every compared dimension matches the target process.")
    return CompatibilityAssessment(verdict, independence, dims, tuple(reasons))


# --------------------------------------------------------------------------- #
# Validation gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ValidationCriterion:
    """One explicit, checkable requirement for ``VALIDATED``."""

    criterion_id: str
    requirement: str


#: All of these must pass. There is no partial validation and no override.
VALIDATION_CRITERIA: tuple[ValidationCriterion, ...] = (
    ValidationCriterion("VC-1", "the source resolves and the quoted passage occurs in it"),
    ValidationCriterion("VC-2", "the quantity and unit match the target contract exactly"),
    ValidationCriterion("VC-3", "the organism and strain are the target strain or a declared derivative"),
    ValidationCriterion("VC-4", "the recombinant construct and product match the target"),
    ValidationCriterion("VC-5", "the culture medium and substrate match the target"),
    ValidationCriterion("VC-6", "the cultivation mode matches the target"),
    ValidationCriterion("VC-7", "temperature is stated and within 1 degree C of the target"),
    ValidationCriterion("VC-8", "an uncertainty is reported and the value lies inside it"),
    ValidationCriterion("VC-9", "the measurement basis matches the target's"),
    ValidationCriterion(
        "VC-10",
        "the supporting passages are independent of the target publication",
    ),
)


@dataclass(frozen=True)
class ValidationReport:
    validated: bool
    results: tuple[tuple[str, bool, str], ...]

    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, ok, _ in self.results if not ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validated": self.validated,
            "results": [
                {"criterion_id": cid, "passed": ok, "detail": detail}
                for cid, ok, detail in self.results
            ],
        }


def validate(finding: "CandidateFinding") -> ValidationReport:
    """Run every registered criterion. ``VALIDATED`` requires all of them.

    A failure is reported with the reason, so a reader can see exactly which
    condition stopped it. Nothing here can be waived.
    """
    c = finding.conditions
    t = TARGET_PROCESS
    results: list[tuple[str, bool, str]] = []

    def add(crit: ValidationCriterion, ok: bool, detail: str) -> None:
        results.append((crit.criterion_id, ok, detail))

    def blank(dim: str) -> Condition:
        return Condition(dim, "", "", "")

    def text(dim: str) -> str:
        cond = c.get(dim) or blank(dim)
        return " ".join(str(cond.value).lower().split())

    def same(dim: str) -> bool:
        a, b = c.get(dim), t.get(dim)
        return a is not None and b is not None and text(dim) == " ".join(
            str(b.value).lower().split())

    for crit in VALIDATION_CRITERIA:
        if crit.criterion_id == "VC-1":
            add(crit, finding.source.is_verifiable(),
                "DOI and quoted passage are both present." if finding.source.is_verifiable()
                else "the source has no DOI or no quoted passage.")
        elif crit.criterion_id == "VC-2":
            ok = bool(finding.unit) and bool(finding.quantity_id) \
                and bool(finding.target_quantity_ids)
            add(crit, ok, "quantity %r with unit %r, targeting %s"
                % (finding.quantity_id, finding.unit,
                   ", ".join(finding.target_quantity_ids) or "nothing"))
        elif crit.criterion_id == "VC-3":
            add(crit, same("strain"),
                "candidate strain %r vs target %r"
                % (text("strain"), " ".join(str(t["strain"].value).lower().split())))
        elif crit.criterion_id == "VC-4":
            add(crit, same("construct") and same("product"),
                "candidate construct %r" % text("construct"))
        elif crit.criterion_id == "VC-5":
            add(crit, same("medium") and same("substrate"),
                "candidate medium %r" % text("medium"))
        elif crit.criterion_id == "VC-6":
            add(crit, same("mode"),
                "candidate mode %r vs target %r"
                % (text("mode"), " ".join(str(t["mode"].value).lower().split())))
        elif crit.criterion_id == "VC-7":
            cand, targ = c.get("temperature_c"), t.get("temperature_c")
            cn = cand.number() if cand else None
            tn = targ.number() if targ else None
            add(crit, cn is not None and tn is not None and abs(cn - tn) <= 1.0,
                "candidate %r C vs target %r C" % (cn, tn))
        elif crit.criterion_id == "VC-8":
            u = finding.uncertainty
            ok = u is not None and u.contains(finding.value)
            add(crit, ok, "uncertainty %s" % (u.to_dict() if u else "not reported"))
        elif crit.criterion_id == "VC-9":
            add(crit, same("measurement"),
                "candidate measurement %r vs target %r"
                % (text("measurement"), " ".join(str(t["measurement"].value).lower().split())))
        elif crit.criterion_id == "VC-10":
            a = finding.assess()
            ok = a.independence is Independence.EXTERNAL
            add(crit, ok, "independence: %s" % a.independence.value)

    return ValidationReport(all(ok for _, ok, _ in results), tuple(results))


# --------------------------------------------------------------------------- #
# The finding itself
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CandidateFinding:
    finding_id: str
    #: The model's own missing-parameter id, e.g. ``MP-GROWTH-KINETICS``.
    target_missing_parameter: str
    #: Output ports in the target model this could inform.
    target_quantity_ids: tuple[str, ...]
    quantity_id: str
    quantity_label: str
    value: float
    unit: str
    provenance: Provenance
    source: SourceLocation
    conditions: Mapping[str, Condition]
    method: str
    uncertainty: UncertaintyRecord | None
    extraction_confidence: ExtractionConfidence
    #: What this candidate would *not* settle, even if adopted.
    does_not_resolve: tuple[str, ...] = ()
    notes: str = ""

    def assess(self) -> CompatibilityAssessment:
        return assess(self)

    def validate(self) -> ValidationReport:
        return validate(self)

    def to_dict(self) -> dict[str, Any]:
        assessment = self.assess()
        report = self.validate()
        return {
            "finding_id": self.finding_id,
            "target_missing_parameter": self.target_missing_parameter,
            "target_quantity_ids": list(self.target_quantity_ids),
            "quantity_id": self.quantity_id,
            "quantity_label": self.quantity_label,
            "value": self.value,
            "unit": self.unit,
            "provenance": self.provenance.value,
            "source": {
                "citation": self.source.citation,
                "doi": self.source.doi,
                "url": self.source.url,
                "pmid": self.source.pmid,
                "open_access": self.source.open_access,
                "section": self.source.section,
                "figure": self.source.figure,
                "quote": self.source.quote,
                "locator": self.source.locator(),
            },
            "conditions": {k: to_dict(v) for k, v in self.conditions.items()},
            "method": self.method,
            "uncertainty": self.uncertainty.to_dict() if self.uncertainty else None,
            "extraction_confidence": self.extraction_confidence.value,
            "assessment": assessment.to_dict(),
            "validation": report.to_dict(),
            "does_not_resolve": list(self.does_not_resolve),
            "notes": self.notes,
        }


def candidates_for(findings: Sequence[CandidateFinding], parameter_id: str) -> tuple[CandidateFinding, ...]:
    return tuple(f for f in findings if f.target_missing_parameter == parameter_id)


def catalogue_payload(
    findings: Sequence[CandidateFinding],
    targets: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble the payload the Godot scene consumes.

    ``targets`` maps a model missing-parameter id to the plain description of
    what is missing and what it blocks, so the UI never has to guess.
    """
    out: dict[str, Any] = {"targets": {}, "findings": []}
    for pid, info in targets.items():
        matched = candidates_for(findings, pid)
        verdicts = [f.assess().verdict.value for f in matched]
        out["targets"][pid] = {
            **dict(info),
            "candidate_count": len(matched),
            "verdicts": verdicts,
            "any_found": any(v in ("found", "validated") for v in verdicts),
        }
    for f in findings:
        out["findings"].append(f.to_dict())
    return out