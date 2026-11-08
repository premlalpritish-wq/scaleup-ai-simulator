"""Structured diagnostics.

Every failure a run can have is one of these. The rule the package follows is
that a run which cannot be trusted says so in a structured way and returns no
result -- never a plausible-looking trajectory with a warning attached at the
end.

Severity mirrors the composition layer's (``ERROR`` blocks, ``WARNING``
annotates, ``INFO`` records) so a diagnostic from this model can be surfaced
without translation if the model is ever wired into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticCode(Enum):
    INPUT_MISSING = "input.missing"
    INPUT_INVALID = "input.invalid"
    UNIT_INVALID = "unit.invalid"
    PARAMETER_UNKNOWN = "parameter.unknown"
    SOLVER_FAILED = "solver.failed"
    STATE_NON_FINITE = "state.non_finite"
    STATE_NEGATIVE = "state.negative"
    STATE_OUT_OF_RANGE = "state.out_of_range"
    TRANSCRIPTION_UNRESOLVED = "transcription.unresolved"
    REFERENCE_NOT_AVAILABLE = "reference.not_available"


@dataclass(frozen=True)
class Diagnostic:
    code: DiagnosticCode
    severity: Severity
    message: str
    where: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "where": self.where,
            "detail": dict(self.detail),
            "remediation": self.remediation,
        }

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"[{self.severity.value}] {self.code.value}: {self.message}"


class DiagnosticList(list):
    """A list of diagnostics with the few queries the caller actually needs."""

    def error(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self)

    def codes(self) -> tuple[str, ...]:
        return tuple(d.code.value for d in self)

    def extend_diagnostics(self, items: Iterable[Diagnostic]) -> None:
        self.extend(items)

    def to_list(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self]


def unresolved_transcription_diagnostics(
    notes: Iterable[Any],
) -> DiagnosticList:
    """Turn every unresolved transcription note into a run-visible warning.

    These are attached to *every* result, including successful ones. A run that
    used an equation whose printed form is ambiguous should not look identical
    to a run that did not.
    """
    out = DiagnosticList()
    for note in notes:
        if not getattr(note, "unresolved", False):
            continue
        out.append(
            Diagnostic(
                code=DiagnosticCode.TRANSCRIPTION_UNRESOLVED,
                severity=Severity.WARNING,
                message=(
                    f"{note.note_id}: {note.statement} Decision taken: "
                    f"{note.decision}"
                ),
                where=f"equations{list(note.affected_equations)}",
                detail={
                    "note_id": note.note_id,
                    "review_question": note.review_question,
                    "source": note.source.citation if note.source else "",
                },
                remediation=(
                    "Results computed with this reading are conditional on it. "
                    "Confirm with the paper's authors before treating the "
                    "affected trajectory as a reproduction of the paper."
                ),
            )
        )
    return out