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


#: The Zielinski 2019 fermenter, exactly as the source publication states it.
#: Every comparison is against this, and every one of its fields is visible to
#: the reader so a verdict can be checked by hand rather than taken on trust.
TARGET_PROCESS: Mapping[str, str] = {
    "organism": "Escherichia coli",
    "strain": "E. coli 20 (CSH50R derivative)",
    "construct": "pIBAINS (SOD-INS fusion, TetR, deoP1P2 promoter)",
    "product": "recombinant human insulin, inclusion bodies",
    "medium": "GMS minimal medium",
    "substrate": "glucose, 40% w/v feed",
    "mode": "batch with pH-stat glucose feeding",
    "temperature_c": "37",
    "ph": "controlled with 16% NH4OH, dead band 0.01",
    "oxygen_transfer": "not reported",
    "measurement": "population OD600",
    "scale": "4 L working volume in a 7.5 L fermenter",
}


@dataclass(frozen=True)
class ExperimentalConditions:
    """The experimental context a value was measured under.

    Every field is a string so that a missing condition is recorded as an
    explicit ``"not stated"`` rather than silently omitted. An omitted field
    would read as agreement.
    """

    organism: str
    strain: str
    construct: str
    product: str
    medium: str
    substrate: str
    mode: str
    temperature_c: str
    ph: str
    oxygen_transfer: str
    measurement: str
    scale: str

    def dimensions(self) -> dict[str, str]:
        return {
            "organism": self.organism,
            "strain": self.strain,
            "construct": self.construct,
            "product": self.product,
            "medium": self.medium,
            "substrate": self.substrate,
            "mode": self.mode,
            "temperature_c": self.temperature_c,
            "ph": self.ph,
            "oxygen_transfer": self.oxygen_transfer,
            "measurement": self.measurement,
            "scale": self.scale,
        }


#: Dimensions compared literally against :data:`TARGET_PROCESS`.
#: Anything not listed is compared by hand in :func:`_compare`.
_KEYWORD_MATCHES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # dimension: (terms indicating agreement, terms indicating disagreement)
    "organism": (("escherichia coli", "e. coli"), ("coli bacillus", "yeast")),
    "temperature_c": (("37",), ("30", "25", "22")),
    "mode": (
        ("batch", "pH-stat", "fed"),
        ("chemostat", "microfluidic", "picoliter", "continuous perfusion"),
    ),
    "measurement": (("od600", "population", "biomass"), ("single cell", "single-cell")),
}


def _normalise(text: str) -> str:
    return " ".join(str(text).lower().replace("‑", "-").split())


def _compare(dimension: str, candidate: str, target: str) -> Match:
    """Compare one dimension conservatively.

    ``"not stated"`` is ``UNKNOWN``, never a match. That distinction is the whole
    point: an unreported condition must not be scored as agreement.
    """
    c, t = _normalise(candidate), _normalise(target)
    if c in ("", "not stated", "not reported", "unknown", "n/a"):
        return Match.UNKNOWN

    rules = _KEYWORD_MATCHES.get(dimension)
    if rules is not None:
        agree, disagree = rules
        if any(k in c for k in disagree):
            return Match.MISMATCH
        if any(k in c for k in agree) and any(k in t for k in agree):
            return Match.MATCH

    # Strain: exact match, or one naming the other as a derivative/parent.
    if dimension == "strain":
        if c == t:
            return Match.MATCH
        if c in t or t in c:
            return Match.PARTIAL
        return Match.MISMATCH

    # Everything else: normalised equality, else partial.
    return Match.MATCH if c == t else Match.PARTIAL


@dataclass(frozen=True)
class DimensionVerdict:
    dimension: str
    candidate: str
    target: str
    match: Match
    critical: bool


@dataclass(frozen=True)
class CompatibilityAssessment:
    verdict: Verdict
    dimensions: tuple[DimensionVerdict, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "candidate": d.candidate,
                    "target": d.target,
                    "match": d.match.value,
                    "critical": d.critical,
                }
                for d in self.dimensions
            ],
        }


def assess(finding: "CandidateFinding") -> CompatibilityAssessment:
    """Score one candidate against the target process.

    Deterministic and conservative. Never returns ``VALIDATED`` -- only
    :func:`validate` may grant that.
    """
    target = dict(TARGET_PROCESS)
    dims: list[DimensionVerdict] = []
    for name, value in finding.conditions.dimensions().items():
        dims.append(
            DimensionVerdict(
                dimension=name,
                candidate=value,
                target=target[name],
                match=_compare(name, value, target[name]),
                critical=name in CRITICAL_DIMENSIONS,
            )
        )

    mismatched = [d for d in dims if d.critical and d.match is Match.MISMATCH]
    unknown_critical = [d for d in dims if d.critical and d.match is Match.UNKNOWN]
    partial_critical = [d for d in dims if d.critical and d.match is Match.PARTIAL]
    noncritical_mismatch = [d for d in dims if not d.critical and d.match is Match.MISMATCH]

    reasons: list[str] = []
    if mismatched:
        verdict = Verdict.INCOMPATIBLE
        for d in mismatched:
            reasons.append(
                "%s differs from the target process: candidate %r, target %r."
                % (d.dimension, d.candidate, d.target)
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
                "%s only partially matches: candidate %r, target %r."
                % (d.dimension, d.candidate, d.target)
            )
    else:
        verdict = Verdict.FOUND

    for d in noncritical_mismatch:
        reasons.append(
            "Non-critical difference in %s: candidate %r, target %r."
            % (d.dimension, d.candidate, d.target)
        )
    if not reasons:
        reasons.append("Every compared dimension matches the target process.")
    return CompatibilityAssessment(verdict, tuple(dims), tuple(reasons))


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
    t = dict(TARGET_PROCESS)
    results: list[tuple[str, bool, str]] = []

    def add(crit: ValidationCriterion, ok: bool, detail: str) -> None:
        results.append((crit.criterion_id, ok, detail))

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
            ok = _normalise(c.strain) == _normalise(t["strain"])
            add(crit, ok, "candidate strain %r vs target %r" % (c.strain, t["strain"]))
        elif crit.criterion_id == "VC-4":
            ok = _normalise(c.construct) == _normalise(t["construct"]) and \
                _normalise(c.product) == _normalise(t["product"])
            add(crit, ok, "candidate construct %r" % c.construct)
        elif crit.criterion_id == "VC-5":
            ok = _normalise(c.medium) == _normalise(t["medium"]) and \
                _normalise(c.substrate) == _normalise(t["substrate"])
            add(crit, ok, "candidate medium %r" % c.medium)
        elif crit.criterion_id == "VC-6":
            ok = _normalise(c.mode) == _normalise(t["mode"])
            add(crit, ok, "candidate mode %r vs target %r" % (c.mode, t["mode"]))
        elif crit.criterion_id == "VC-7":
            ok = _normalise(c.temperature_c) == _normalise(t["temperature_c"])
            add(crit, ok, "candidate %r C vs target %r C" % (c.temperature_c, t["temperature_c"]))
        elif crit.criterion_id == "VC-8":
            u = finding.uncertainty
            ok = u is not None and u.contains(finding.value)
            add(crit, ok, "uncertainty %s" % (u.to_dict() if u else "not reported"))
        elif crit.criterion_id == "VC-9":
            ok = _normalise(c.measurement) == _normalise(t["measurement"])
            add(crit, ok, "candidate measurement %r vs target %r" % (c.measurement, t["measurement"]))

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
    conditions: ExperimentalConditions
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
            "conditions": self.conditions.dimensions(),
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