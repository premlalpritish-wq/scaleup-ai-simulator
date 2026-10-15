"""Conflicting evidence, and what each finding was checked against.

Two obligations live here.

**Conflicts.** Detecting that sources disagree is mechanical and is explicitly
within scope: given two findings for the same quantity, either their reported
intervals overlap or they do not. Nothing here decides which source is right.
A conflict is recorded as *unresolved* and left for a human, because picking a
winner is a scientific judgement.

**Records examined.** Every verdict is only meaningful next to the artefact it
was made against, so a finding records which model specification, which
publication, and which exact run result it was assessed against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence

from .candidate import CRITICAL_DIMENSIONS, CandidateFinding, Independence


# --------------------------------------------------------------------------- #
# Records examined
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RecordExamined:
    """Exactly what a comparison was made against.

    A verdict without this is not reproducible: the model changes, the run
    digest changes, and a later reader cannot tell which state produced it.
    """

    model_id: str
    model_source: str
    model_doi: str
    #: ``graph_id`` of the result document the ports were read from.
    run_id: str
    #: The result's ``reproducibility`` digest. Note precisely what this covers:
    #: it is a digest of the *graph document*, not of the numeric results. It
    #: pins which graph was executed; it does not attest to the values.
    graph_reproducibility_digest: str
    #: Version string the model package reported for this run.
    model_version: str = ""
    #: Output ports inspected for this finding.
    ports_examined: tuple[str, ...] = ()
    missing_parameters_examined: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_source": self.model_source,
            "model_doi": self.model_doi,
            "run_id": self.run_id,
            "graph_reproducibility_digest": self.graph_reproducibility_digest,
            "digest_covers": "the graph document, not the numeric results",
            "model_version": self.model_version,
            "ports_examined": list(self.ports_examined),
            "missing_parameters_examined": list(self.missing_parameters_examined),
        }


# --------------------------------------------------------------------------- #
# Conflicts
# --------------------------------------------------------------------------- #


class ConflictKind(Enum):
    VALUE = "value_disagreement"
    SOURCE_OVERLAP = "not_independent_of_target"
    CONDITION = "condition_disagreement"


@dataclass(frozen=True)
class Conflict:
    conflict_id: str
    kind: ConflictKind
    subject: str
    participants: tuple[str, ...]
    affected_records: tuple[str, ...]
    explanation: str
    #: Always false. This system reports conflicts; it does not settle them.
    resolved: bool = False
    requires: str = "explicit human direction"

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "kind": self.kind.value,
            "subject": self.subject,
            "participants": list(self.participants),
            "affected_records": list(self.affected_records),
            "explanation": self.explanation,
            "resolved": self.resolved,
            "requires": self.requires,
        }


def _overlapping(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def detect(findings: Sequence[CandidateFinding]) -> tuple[Conflict, ...]:
    """Find every disagreement we can establish without interpreting anything."""
    conflicts: list[Conflict] = []
    n = 0

    def next_id() -> str:
        nonlocal n
        n += 1
        return "CFL-%02d" % n

    # 1. Two sources giving disjoint intervals for the same quantity.
    by_quantity: dict[str, list[CandidateFinding]] = {}
    for f in findings:
        if f.uncertainty is not None:
            by_quantity.setdefault(f.quantity_id, []).append(f)

    for quantity, group in sorted(by_quantity.items()):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                assert a.uncertainty is not None and b.uncertainty is not None
                if a.unit != b.unit:
                    continue
                ia = (a.uncertainty.lo, a.uncertainty.hi)
                ib = (b.uncertainty.lo, b.uncertainty.hi)
                if _overlapping(ia, ib):
                    continue
                conflicts.append(Conflict(
                    conflict_id=next_id(),
                    kind=ConflictKind.VALUE,
                    subject=quantity,
                    participants=(a.finding_id, b.finding_id),
                    affected_records=a.target_quantity_ids + b.target_quantity_ids,
                    explanation=(
                        "%s and %s report %s %s over %g-%g and %g-%g respectively. "
                        "The reported intervals do not overlap, so the two sources "
                        "cannot both describe the same system. Which is applicable "
                        "is not decided here."
                        % (a.finding_id, b.finding_id, quantity, a.unit,
                           ia[0], ia[1], ib[0], ib[1])
                    ),
                ))

    # 2. A "candidate" that is actually the target publication's own wording.
    for f in findings:
        if f.assess().independence is Independence.TARGET:
            conflicts.append(Conflict(
                conflict_id=next_id(),
                kind=ConflictKind.SOURCE_OVERLAP,
                subject=f.finding_id,
                participants=(f.finding_id,),
                affected_records=f.target_quantity_ids,
                explanation=(
                    "%s is cited as external support, but a passage it relies on "
                    "occurs in the target publication itself. It is therefore the "
                    "target paper's own content reached through a second paper and "
                    "cannot serve as independent corroboration."
                    % f.finding_id
                ),
            ))

    # 3. Findings that describe one target's conditions incompatibly with each
    #    other -- i.e. the sources disagree about what the process was.
    by_port: dict[str, list[CandidateFinding]] = {}
    for f in findings:
        for port in f.target_quantity_ids:
            by_port.setdefault(port, []).append(f)

    for port, group in sorted(by_port.items()):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                da = {d.dimension: d.match for d in a.assess().dimensions}
                db = {d.dimension: d.match for d in b.assess().dimensions}
                opposed = sorted(
                    d for d in CRITICAL_DIMENSIONS
                    if {da.get(d), db.get(d)} == {"match", "mismatch"}
                )
                if opposed:
                    conflicts.append(Conflict(
                        conflict_id=next_id(),
                        kind=ConflictKind.CONDITION,
                        subject=port,
                        participants=(a.finding_id, b.finding_id),
                        affected_records=(port,),
                        explanation=(
                            "%s and %s disagree about the process described for "
                            "%s: on %s one matches the target and the other does not."
                            % (a.finding_id, b.finding_id, port,
                               ", ".join(opposed))
                        ),
                    ))

    return tuple(conflicts)


def summarise(conflicts: Iterable[Conflict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in conflicts:
        counts[c.kind.value] = counts.get(c.kind.value, 0) + 1
    return counts