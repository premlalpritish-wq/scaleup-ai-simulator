"""Degree-of-freedom bookkeeping for material balances (Morris et al. 2011).

Section 4.7.2 of the chapter states the counting rule for a single non-reactive
device as

    DOF = SV - IB - IC - F - SR

where

    SV  stream variables          independent stream variables in the system
    IB  independent balances      one per component (sec. 4.7.2)
    IC  independent compositions  specified compositions that are *not*
                                   obtainable by difference
    F   specified flows           specified stream flows or amounts
    SR  subsidiary relations     extra relations that yield an equation

with DOF = 0 meaning "correctly specified", DOF > 0 under-specified and
DOF < 0 over-specified.

Two things this module deliberately refuses to do.

**It refuses to guess the counts.**  The chapter itself notes that the SR item
is "difficult to get right", and its worked example (sec. 4.7.2) applies
device-specific splitter restrictions the caller must already understand.  So
every one of the five terms is an explicit optional input, and `DegreeOfFreedom.dof`
is `None` unless all five are supplied.  A partially known count is not a small
DOF, it is an unknown one.

**It refuses to stand in for a rank computation.**  This is the important
caveat, and it is the chapter's own: the alternative to DOF analysis is to write
the balance equations and check that N_equations = N_unknowns, but "the drawback
of this method is that it is easy to inadvertently write one or more
non-independent equations, which creates the impression that a sufficient number
of independent equations have been written" (sec. 4.7).  Counting terms correctly
is not the same as proving independence, and the two can disagree.

`IndependentDegreesOfFreedom` therefore computes the honest degree of freedom
from the assembled coefficient matrix -- `n_unknowns - rank(A)` -- and
`compare_freedom` puts the two side by side.  Where they disagree, the matrix
wins and the disagreement is itself reported, because a discrepancy is a finding
about the system, not a rounding detail to be smoothed over.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Sequence

from schemas.material_balance import BalanceDiagnostic, Severity

# --------------------------------------------------------------------------- #
# the chapter's five terms
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DegreeOfFreedom:
    """The chapter's bookkeeping, term by term.

    Every term is optional.  `dof` is `None` unless all five are present, and
    `missing_terms` names whatever is absent so a caller can see exactly what
    would have to be established.
    """

    label: str
    sv: int | None = None
    """Stream variables (sec. 4.7.2, step 1)."""

    ib: int | None = None
    """Independent balances (step 2): one per component in the system."""

    ic: int | None = None
    """Independent specified compositions (step 3), excluding any obtainable by
    difference.  A single-component stream contributes no independent
    composition."""

    f: int | None = None
    """Specified stream flows or amounts (step 3)."""

    sr: int | None = None
    """Subsidiary relations (step 4): split fractions, flow ratios, property
    relationships, or -- in reacting systems -- stoichiometry."""

    source_ref: str | None = None
    note: str = ""

    #: The five terms, in the chapter's order, for uniform reporting.
    TERMS: ClassVar[tuple[str, ...]] = ("sv", "ib", "ic", "f", "sr")

    @property
    def missing_terms(self) -> tuple[str, ...]:
        return tuple(t for t in self.TERMS if getattr(self, t) is None)

    @property
    def is_computable(self) -> bool:
        return not self.missing_terms

    @property
    def dof(self) -> int | None:
        """SV - IB - IC - F - SR, or None when any term is unavailable.

        Not zero-by-default and not carried over from a previous call: a DOF
        that cannot be computed stays None so that it is never mistaken for zero.
        """
        if not self.is_computable:
            return None
        return self.sv - self.ib - self.ic - self.f - self.sr  # type: ignore[operator]

    @property
    def classification(self) -> str | None:
        """`under_specified`, `correctly_specified` or `over_specified`."""
        value = self.dof
        if value is None:
            return None
        if value > 0:
            return "under_specified"
        if value == 0:
            return "correctly_specified"
        return "over_specified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "sv": self.sv,
            "ib": self.ib,
            "ic": self.ic,
            "f": self.f,
            "sr": self.sr,
            "dof": self.dof,
            "classification": self.classification,
            "missing_terms": list(self.missing_terms),
            "source_ref": self.source_ref,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# the matrix-derived count
# --------------------------------------------------------------------------- #


class FreedomKind(Enum):
    """Which of the two counts produced a value."""

    BOOKKEEPING = "bookkeeping"
    """DOF = SV - IB - IC - F - SR, from explicitly supplied counts."""

    INDEPENDENT = "independent"
    """n_unknowns - rank(A), from the assembled coefficient matrix."""


@dataclass(frozen=True)
class IndependentDegreesOfFreedom:
    """Degrees of freedom derived from the coefficient matrix itself.

    This is the count that actually governs whether a unique solution exists,
    because it is computed from the linear independence of the equations that
    were actually written -- not from a count of how many were intended.
    """

    n_unknowns: int
    n_equations: int
    rank: int

    def __post_init__(self) -> None:
        if self.n_unknowns < 0 or self.n_equations < 0:
            raise ValueError("n_unknowns and n_equations cannot be negative")
        if not 0 <= self.rank <= min(self.n_unknowns, self.n_equations):
            raise ValueError(
                f"rank {self.rank} is out of range for a {self.n_equations}x"
                f"{self.n_unknowns} matrix"
            )

    @property
    def dof(self) -> int:
        """Undetermined directions: unknowns minus independent equations."""
        return self.n_unknowns - self.rank

    @property
    def redundant_equations(self) -> int:
        """Equations that are linear combinations of the others.

        Section 4.6.2: such an equation "can be used as a check" but carries no
        new information.
        """
        return self.n_equations - self.rank

    @property
    def classification(self) -> str:
        if self.dof > 0:
            return "under_specified"
        if self.dof == 0:
            return "correctly_specified"
        return "over_specified"

    @property
    def kind(self) -> FreedomKind:
        return FreedomKind.INDEPENDENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "n_unknowns": self.n_unknowns,
            "n_equations": self.n_equations,
            "rank": self.rank,
            "dof": self.dof,
            "classification": self.classification,
            "redundant_equations": self.redundant_equations,
        }


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FreedomComparison:
    """The two counts, side by side, with the disagreement made explicit."""

    bookkeeping: DegreeOfFreedom
    independent: IndependentDegreesOfFreedom | None = None
    diagnostics: tuple[BalanceDiagnostic, ...] = ()

    @property
    def bookkeeping_dof(self) -> int | None:
        return self.bookkeeping.dof

    @property
    def independent_dof(self) -> int | None:
        return self.independent.dof if self.independent is not None else None

    @property
    def agrees(self) -> bool | None:
        """True if both counts agree, False if they differ, None if incomparable.

        `None` -- rather than a reassuring True -- whenever either side is
        unavailable, so that "we did not check" never reads as "they match".
        """
        if self.independent is None or self.bookkeeping.dof is None:
            return None
        return self.bookkeeping.dof == self.independent.dof

    @property
    def authoritative_dof(self) -> int | None:
        """The count to act on.

        The matrix-derived count whenever it is available: it reflects the
        independence of the equations actually written, which the chapter warns
        is the thing that is easy to get wrong (sec. 4.7).  The bookkeeping
        figure is retained alongside it, never in place of it.
        """
        if self.independent is not None:
            return self.independent.dof
        return self.bookkeeping.dof

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookkeeping": self.bookkeeping.to_dict(),
            "independent": self.independent.to_dict() if self.independent else None,
            "bookkeeping_dof": self.bookkeeping_dof,
            "independent_dof": self.independent_dof,
            "agrees": self.agrees,
            "authoritative_dof": self.authoritative_dof,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


def compare_freedom(
    bookkeeping: DegreeOfFreedom,
    *,
    independent: IndependentDegreesOfFreedom | None = None,
) -> FreedomComparison:
    """Compare the chapter's bookkeeping against the matrix-derived count.

    Emits a diagnostic whenever the two disagree, whenever the bookkeeping
    cannot be completed, or whenever there are redundant equations.  It never
    adjusts either number to make them match.
    """
    diagnostics: list[BalanceDiagnostic] = []

    if bookkeeping.missing_terms:
        diagnostics.append(
            BalanceDiagnostic(
                code="dof.not_computable",
                severity=Severity.INFO,
                message=(
                    f"degree-of-freedom bookkeeping for {bookkeeping.label!r} is "
                    f"incomplete: missing {list(bookkeeping.missing_terms)}. "
                    f"Section 4.7.2 counts five terms and the SR term in particular "
                    f"cannot be inferred safely, so no DOF is reported."
                ),
                where=(bookkeeping.label,),
            )
        )

    if independent is None:
        diagnostics.append(
            BalanceDiagnostic(
                code="dof.no_matrix_rank",
                severity=Severity.WARNING,
                message=(
                    "no coefficient-matrix rank was supplied, so equation "
                    "independence was not checked. The bookkeeping figure alone "
                    "does not establish it (Morris et al. 2011, sec. 4.7)."
                ),
                where=(bookkeeping.label,),
            )
        )
    else:
        if independent.redundant_equations > 0:
            diagnostics.append(
                BalanceDiagnostic(
                    code="dof.redundant_equations",
                    severity=Severity.WARNING,
                    message=(
                        f"{independent.n_equations} equations span a rank of only "
                        f"{independent.rank}, so {independent.redundant_equations} "
                        f"carry no independent information. Section 4.6.2: a "
                        f"dependent equation is still useful as a check."
                    ),
                    where=(bookkeeping.label,),
                )
            )
        if (
            bookkeeping.dof is not None
            and independent.dof != bookkeeping.dof
        ):
            diagnostics.append(
                BalanceDiagnostic(
                    code="dof.counts_disagree",
                    severity=Severity.WARNING,
                    message=(
                        f"bookkeeping gives DOF = {bookkeeping.dof} from "
                        f"SV={bookkeeping.sv}, IB={bookkeeping.ib}, "
                        f"IC={bookkeeping.ic}, F={bookkeeping.f}, SR={bookkeeping.sr}, "
                        f"but the coefficient matrix gives DOF = {independent.dof} "
                        f"from {independent.n_unknowns} unknowns of rank "
                        f"{independent.rank}. The matrix is authoritative; the "
                        f"gap means the five bookkeeping terms do not describe this "
                        f"system exactly."
                    ),
                    where=(bookkeeping.label,),
                )
            )

    return FreedomComparison(
        bookkeeping=bookkeeping,
        independent=independent,
        diagnostics=tuple(diagnostics),
    )


# --------------------------------------------------------------------------- #
# multi-device composition (sec. 4.9)
# --------------------------------------------------------------------------- #


def process_dof(
    devices: Sequence[DegreeOfFreedom],
    *,
    label: str = "process",
    connecting_stream_variables: int = 0,
    connecting_stream_compositions: int = 0,
    source_ref: str | None = None,
) -> DegreeOfFreedom:
    """Combine per-device counts into a process count.

    Section 4.9 is explicit that a connecting stream must not be counted twice:
    "we cannot simply add up all of the SV values from the two individual device
    DOF calculations, otherwise we would double-count the SV for S3.  For the
    same reason we cannot simply add up the IC values ... However, the number of
    balances is the sum of the two device balances."

    So the composition rule is:

      * IB and SR add outright;
      * SV and IC subtract the caller-supplied connecting-stream counts, which
        the caller must derive from the flowsheet because only they know which
        variables the connecting stream carries;
      * F adds outright.

    `connecting_stream_variables` and `connecting_stream_compositions` are
    therefore explicit inputs rather than a guess.  If a device count is
    incomplete the result is incomplete, and stays so.
    """
    if not devices:
        raise ValueError("process_dof needs at least one device count")

    def total(attr: str) -> int | None:
        values = [getattr(d, attr) for d in devices]
        if any(v is None for v in values):
            return None
        return sum(values)  # type: ignore[arg-type]

    sv = total("sv")
    ic = total("ic")
    if sv is not None:
        sv -= connecting_stream_variables
    if ic is not None:
        ic -= connecting_stream_compositions

    return DegreeOfFreedom(
        label=label,
        sv=sv,
        ib=total("ib"),
        ic=ic,
        f=total("f"),
        sr=total("sr"),
        source_ref=source_ref,
        note=(
            f"composed from {len(devices)} device count(s); SV reduced by "
            f"{connecting_stream_variables} and IC by "
            f"{connecting_stream_compositions} to avoid double-counting "
            f"connecting streams (sec. 4.9)"
        ),
    )


# --------------------------------------------------------------------------- #
# worked examples printed in the chapter, kept for regression tests
# --------------------------------------------------------------------------- #

#: Section 4.7.2: salt cake leaching process, four components, seven streams.
#: "The DOF for the salt cake process = 14 - 4 - 4 - 3 - 2 = +1."
SALTCAKE_PROCESS = DegreeOfFreedom(
    label="salt cake leaching process",
    sv=14,
    ib=4,
    ic=4,
    f=3,
    sr=2,
    source_ref="Morris et al. 2011, sec. 4.7.2, p.161",
    note=(
        "IB = 4 (one per component: NaCl, slag, H2O, air). IC = 4 because salt "
        "cake contributes two independent compositions (H2O follows by difference), "
        "leach solution one and ambient air one; the pure slag stream has no "
        "independent composition. SR = 2: the S6-to-S7 flow ratio and the "
        "wNaCl(S5) = 0.95 * wNaCl(S6) operating history. "
        "CAUTION: SV = 14 is reproduced here exactly as printed, but it is not "
        "derivable from the rule the section states one paragraph earlier ('the "
        "sum of the number of components over all streams', which gives 7 x 4 = 28 "
        "for this system, and which does yield 12 for the three four-component "
        "streams of Example 4.15). Treat the +1 below as the book's printed "
        "figure, not as a verified count -- which is precisely why the matrix "
        "rank is computed separately and the two are only ever compared."
    ),
)

#: Section 4.9, Table 4.6: two-stage distillation of a Cd-Hg-Zn alloy.
#: IB adds across devices (3 + 3 = 6) while SV does not (8 + 8 - 3 = 13),
#: because the connecting stream S3 belongs to both devices.
DISTILLATION_STILL_I = DegreeOfFreedom(
    label="two-stage distillation / Still I",
    sv=8,
    ib=3,
    ic=4,
    f=1,
    sr=0,
    source_ref="Morris et al. 2011, Table 4.6, p.181",
)
DISTILLATION_STILL_II = DegreeOfFreedom(
    label="two-stage distillation / Still II",
    sv=8,
    ib=3,
    ic=4,
    f=0,
    sr=0,
    source_ref="Morris et al. 2011, Table 4.6, p.181",
)
DISTILLATION_PROCESS = DegreeOfFreedom(
    label="two-stage distillation / process",
    sv=13,
    ib=6,
    ic=6,
    f=1,
    sr=0,
    source_ref="Morris et al. 2011, Table 4.6, p.181",
    note="13 = 8 + 8 - 3: the connecting stream S3 is counted once, not twice.",
)
DISTILLATION_OVERALL = DegreeOfFreedom(
    label="two-stage distillation / overall",
    sv=10,
    ib=3,
    ic=4,
    f=1,
    sr=0,
    source_ref="Morris et al. 2011, Table 4.6, p.181",
    note="Treating both stills as one unit leaves DOF = +2; the overall balance "
    "alone cannot close the system.",
)

#: Section 4.15, Example 4.15: DOF around the spent-gas splitter.
#: SR = 4: the split ratio R plus (N - 1)(S - 1) = 3 special splitter
#: restrictions. SV = 12 is three streams of four components.
SPENT_GAS_SPLITTER = DegreeOfFreedom(
    label="spent gas splitter",
    sv=12,
    ib=4,
    ic=3,
    f=1,
    sr=4,
    source_ref="Morris et al. 2011, sec. 4.15, Example 4.15, p.236",
    note="SR = 1 split ratio + (2 - 1)(4 - 1) = 3 splitter composition restrictions.",
)

__all__ = [
    "DISTILLATION_OVERALL",
    "DISTILLATION_PROCESS",
    "DISTILLATION_STILL_I",
    "DISTILLATION_STILL_II",
    "SALTCAKE_PROCESS",
    "SPENT_GAS_SPLITTER",
    "DegreeOfFreedom",
    "FreedomComparison",
    "FreedomKind",
    "IndependentDegreesOfFreedom",
    "compare_freedom",
    "process_dof",
]