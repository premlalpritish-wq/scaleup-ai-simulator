"""Equation generation and the deterministic linear solve.

This module turns a declared `BalanceSystem` into equations, solves them, and
reports what came out -- including what did not.

Equation forms, all from Morris, Geiger & Fine (2011), Chapter 4:

  steady state (sec. 4.4/4.5)   sum(inflow of i) - sum(outflow of i) = 0
  accumulating (sec. 4.4)       same, with the retained material on the outflow
                                side; Example 4.3 states it as
                                ``input = output + accumulation``
  batch (sec. 4.18)             final - initial - added + removed = 0
  composition (sec. 4.18)       sum(mass fractions of a stream) = 1

Only the forms the declared `ProcessMode` admits are generated.  A steady-state
balance is never applied to a batch because it would be numerically valid and
physically wrong, which is the harder failure to notice.

Two design decisions worth stating up front.

**Linearity is enforced, not assumed.**  A component's flow in a stream described
by a total and a composition is ``total * fraction``, which is bilinear when both
are unknown.  Such a term cannot enter a linear system, so the balance that
needs it is not generated; it is reported as a diagnostic naming the stream and
the two unknowns involved.  Silently dropping it would produce a confident
answer that quietly omits a conservation law.

**Measurement disagreement is reported, never repaired.**  Section 4.7 is blunt:
if the measurements disagree, "we have to make a judgment call about which flow
value is the least accurate".  That judgment needs information this engine does
not have -- instrument reliability, which reading was taken when.  So an
inconsistent system reports the least-squares residuals as a diagnostic and
solves nothing.  Section 4.6.2's advice to disregard a value is left to the
engine's caller, who can see exactly which measurements disagree.

The solver is ordinary Gauss-Jordan elimination with partial pivoting, plus
modified Gram-Schmidt least squares for the inconsistent case.  No third-party
dependency, no iteration, no convergence tolerance to tune: the same system
always produces bit-identical results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from schemas.material_balance import (
    BalanceDiagnostic,
    BalanceEquation,
    BalanceResidual,
    BalanceResult,
    BalanceSystem,
    ConstantTerm,
    Direction,
    EquationKind,
    LedgerRow,
    ProcessMode,
    Provenance,
    Quantity,
    QuantityKind,
    ResidualContribution,
    Severity,
    SolvedVariable,
    Solvability,
    Stream,
    UnresolvedVariable,
    Unknown,
    base_unit,
    unit as lookup_unit,
)

# --------------------------------------------------------------------------- #
# signs: the one place the balance orientation is decided
# --------------------------------------------------------------------------- #

#: Coefficient of each stream's contribution to a component balance, per mode.
#:
#: steady state   input - output                = 0
#: accumulating   input - output - accumulated  = 0
#: batch          final - initial - added + removed = 0
DIRECTION_SIGNS: Mapping[ProcessMode, Mapping[Direction, int]] = {
    ProcessMode.STEADY_STATE: {
        Direction.INPUT: +1,
        Direction.OUTPUT: -1,
        Direction.INTERNAL: 0,
    },
    ProcessMode.ACCUMULATING: {
        Direction.INPUT: +1,
        Direction.OUTPUT: -1,
        Direction.ACCUMULATED: -1,
        Direction.INTERNAL: 0,
    },
    ProcessMode.BATCH: {
        Direction.FINAL: +1,
        Direction.INITIAL: -1,
        Direction.ADDED: -1,
        Direction.REMOVED: +1,
        Direction.INTERNAL: 0,
    },
}


class BalanceError(ValueError):
    """Raised when the engine cannot proceed with the system as declared."""


class BilinearTerm(BalanceError):
    """Raised internally when a balance would need a product of two unknowns."""

    def __init__(self, message: str, stream_id: str, component_id: str) -> None:
        super().__init__(message)
        self.stream_id = stream_id
        self.component_id = component_id


# --------------------------------------------------------------------------- #
# variable bookkeeping
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VariableSpec:
    """Metadata for one column of the coefficient matrix."""

    variable_id: str
    kind: QuantityKind
    unit: str
    stream_id: str
    component_id: str | None
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "kind": self.kind.value,
            "unit": self.unit,
            "stream_id": self.stream_id,
            "component_id": self.component_id,
            "role": self.role,
        }


@dataclass
class _Term:
    """One signed contribution to an equation, before aggregation."""

    text: str
    sign: int
    coefficient: tuple[str, float] | None = None
    constant: ConstantTerm | None = None


# --------------------------------------------------------------------------- #
# stream term construction
# --------------------------------------------------------------------------- #


def _fraction_symbol(stream_id: str, component_id: str) -> str:
    return f"w({stream_id},{component_id})"


def _total_symbol(stream_id: str) -> str:
    return f"total({stream_id})"


def _component_symbol(stream_id: str, component_id: str) -> str:
    return f"{component_id}({stream_id})"


def _component_terms(
    stream: Stream, component_id: str, sign: int
) -> tuple[_Term, ...]:
    """The signed terms a stream contributes to one component's balance.

    Three shapes are possible: the component's flow is known outright (it is a
    constant), it is a declared unknown (a variable), or it is the product of a
    stream total and a mass fraction.  The last case is linear only when one of
    the two factors is known; when both are unknown it raises `BilinearTerm`
    rather than inventing a substitution.
    """
    total = stream.amount
    if stream.mass_fractions:
        fraction = stream.mass_fractions.get(component_id)
        if fraction is None:
            # declared absent: contributes nothing, by the user's statement
            return ()

        total_known = isinstance(total, Quantity)
        fraction_known = isinstance(fraction, Quantity)

        if total_known and fraction_known:
            value = total.base_value * fraction.base_value  # type: ignore[union-attr]
            return (
                _Term(
                    text=f"{total.base_value:g} * {fraction.base_value:g}",
                    sign=sign,
                    constant=ConstantTerm(
                        quantity_id=total.quantity_id,  # type: ignore[union-attr]
                        value=value,
                        unit=base_unit(stream.kind),
                        kind=stream.kind,
                        provenance=Provenance.DERIVED,
                        source_ref=None,
                        derivation=(
                            f"{total.quantity_id} * "
                            f"{fraction.quantity_id}"  # type: ignore[union-attr]
                        ),
                        sign=sign,
                    ),
                ),
            )

        if total_known and not fraction_known:
            return (
                _Term(
                    text=(
                        f"{_total_symbol(stream.stream_id)} * "
                        f"{_fraction_symbol(stream.stream_id, component_id)}"
                    ),
                    sign=sign,
                    coefficient=(
                        fraction.variable_id,  # type: ignore[union-attr]
                        sign * total.base_value,  # type: ignore[union-attr]
                    ),
                ),
            )

        if not total_known and fraction_known:
            assert isinstance(total, Unknown)
            return (
                _Term(
                    text=(
                        f"{_total_symbol(stream.stream_id)} * "
                        f"{fraction.base_value:g}"
                    ),
                    sign=sign,
                    coefficient=(total.variable_id, sign * fraction.base_value),  # type: ignore[union-attr]
                ),
            )

        assert isinstance(total, Unknown) and isinstance(fraction, Unknown)
        raise BilinearTerm(
            f"stream {stream.stream_id!r} gives neither a total nor a fraction for "
            f"component {component_id!r} that is known, so its flow is "
            f"total({stream.stream_id}) * w({stream.stream_id},{component_id}), a "
            f"product of two unknowns that no linear balance can contain",
            stream.stream_id,
            component_id,
        )

    # component amounts given directly
    value = stream.component_amounts.get(component_id)
    if value is None:
        return ()
    if isinstance(value, Quantity):
        return (
            _Term(
                text=f"{value.base_value:g}",
                sign=sign,
                constant=ConstantTerm(
                    quantity_id=value.quantity_id,
                    value=value.base_value,
                    unit=base_unit(stream.kind),
                    kind=stream.kind,
                    provenance=value.provenance,
                    source_ref=value.source_ref,
                    sign=sign,
                ),
            ),
        )
    return (
        _Term(
            text=_component_symbol(stream.stream_id, component_id),
            sign=sign,
            coefficient=(value.variable_id, sign),
        ),
    )


def _stream_total_terms(stream: Stream, sign: int) -> tuple[_Term, ...]:
    """The signed terms a stream contributes to a total-mass balance."""
    if stream.amount is None:
        return ()
    if isinstance(stream.amount, Quantity):
        return (
            _Term(
                text=f"{stream.amount.base_value:g}",
                sign=sign,
                constant=ConstantTerm(
                    quantity_id=stream.amount.quantity_id,
                    value=stream.amount.base_value,
                    unit=base_unit(stream.kind),
                    kind=stream.kind,
                    provenance=stream.amount.provenance,
                    source_ref=stream.amount.source_ref,
                    sign=sign,
                ),
            ),
        )
    return (
        _Term(
            text=_total_symbol(stream.stream_id),
            sign=sign,
            coefficient=(stream.amount.variable_id, sign),
        ),
    )


def _collect_variable_specs(system: BalanceSystem) -> dict[str, VariableSpec]:
    """Every unknown in the system, with the unit it will be reported in."""
    specs: dict[str, VariableSpec] = {}
    for stream in system.streams:
        if isinstance(stream.amount, Unknown):
            specs[stream.amount.variable_id] = VariableSpec(
                variable_id=stream.amount.variable_id,
                kind=stream.amount.kind,
                unit=stream.amount.effective_unit,
                stream_id=stream.stream_id,
                component_id=None,
                role="stream_total",
            )
        for component_id, fraction in stream.mass_fractions.items():
            if isinstance(fraction, Unknown):
                specs[fraction.variable_id] = VariableSpec(
                    variable_id=fraction.variable_id,
                    kind=fraction.kind,
                    unit=fraction.effective_unit,
                    stream_id=stream.stream_id,
                    component_id=component_id,
                    role="mass_fraction",
                )
        for component_id, value in stream.component_amounts.items():
            if isinstance(value, Unknown):
                specs[value.variable_id] = VariableSpec(
                    variable_id=value.variable_id,
                    kind=value.kind,
                    unit=value.effective_unit,
                    stream_id=stream.stream_id,
                    component_id=component_id,
                    role="component_amount",
                )
    for constraint in system.constraints:
        for variable_id in constraint.coefficients:
            if variable_id not in specs:
                # unreachable via BalanceSystem, which rejects a constraint that
                # references an undeclared variable; kept as a guard so that a
                # future caller cannot get a silently invented quantity kind
                raise BalanceError(
                    f"constraint {constraint.equation_id!r} references {variable_id!r}, "
                    f"which no stream declares; its unit and kind are unknown"
                )
    return specs


def _assemble(terms: Iterable[_Term]) -> tuple[dict[str, float], tuple[ConstantTerm, ...]]:
    coefficients: dict[str, float] = {}
    constants: list[ConstantTerm] = []
    for term in terms:
        if term.coefficient is not None:
            variable_id, value = term.coefficient
            coefficients[variable_id] = coefficients.get(variable_id, 0.0) + value
        elif term.constant is not None:
            constants.append(term.constant)
    return coefficients, tuple(constants)


def _expression(terms: Sequence[_Term]) -> str:
    """Render the equation the way the chapter writes it, for auditing."""
    parts: list[str] = []
    for term in terms:
        magnitude = abs(float(term.sign))
        body = term.text if magnitude == 1.0 else f"{magnitude:g} * {term.text}"
        if not parts:
            parts.append(body if term.sign > 0 else f"- {body}")
        else:
            parts.append(f"+ {body}" if term.sign > 0 else f"- {body}")
    return " ".join(parts) + " = 0"


def _input_ids(terms: Sequence[_Term]) -> tuple[str, ...]:
    out: list[str] = []
    for term in terms:
        if term.coefficient is not None:
            out.append(term.coefficient[0])
        elif term.constant is not None:
            out.append(term.constant.derivation or term.constant.quantity_id)
    return tuple(dict.fromkeys(out))


# --------------------------------------------------------------------------- #
# equation generation
# --------------------------------------------------------------------------- #


@dataclass
class EquationSet:
    """Everything the generators produced, including what they refused to."""

    equations: list[BalanceEquation] = field(default_factory=list)
    diagnostics: list[BalanceDiagnostic] = field(default_factory=list)


def generate_equations(system: BalanceSystem) -> EquationSet:
    """Build every equation appropriate to the declared process mode.

    Order is deterministic: component balances in component order, then the
    optional total-mass balance, then one composition sum per stream that carries
    a mass-fraction composition, then caller-supplied constraints in the order
    given.  Stable ordering keeps regression tests meaningful.
    """
    out = EquationSet()
    signs = DIRECTION_SIGNS[system.process_mode]
    crossing = system.crossing_streams()
    mode = system.process_mode

    for stream in system.internal_streams():
        out.diagnostics.append(
            BalanceDiagnostic(
                code="stream.internal_cancels",
                severity=Severity.INFO,
                message=(
                    f"stream {stream.stream_id!r} is declared internal. It enters and "
                    f"leaves the control volume, so it cancels from every balance "
                    f"generated here and contributes no equation. Model each device "
                    f"as its own BalanceSystem to balance around it (sec. 4.9)."
                ),
                where=(system.system_id, stream.stream_id),
            )
        )

    balanced = (
        list(system.balances) if system.balances is not None else list(system.component_ids)
    )
    explicit = system.balances is not None

    for component_id in balanced:
        component = system.component(component_id)
        terms: list[_Term] = []
        skipped: BilinearTerm | None = None
        for stream in crossing:
            try:
                terms.extend(
                    _component_terms(stream, component_id, signs[stream.direction])
                )
            except BilinearTerm as exc:
                skipped = exc
                break
        if skipped is not None:
            out.diagnostics.append(
                BalanceDiagnostic(
                    code="balance.non_linear_skipped",
                    severity=Severity.ERROR if explicit else Severity.WARNING,
                    message=(
                        f"no {component.label} balance was generated: {skipped}. The "
                        f"balance is not linear in the unknowns, so it cannot enter a "
                        f"linear system. Declare this stream's component amounts "
                        f"directly, or accept that this component is unbalanced. "
                        f"No conservation law was dropped silently."
                    ),
                    where=(system.system_id, skipped.stream_id),
                )
            )
            continue
        if not terms:
            out.diagnostics.append(
                BalanceDiagnostic(
                    code="balance.empty",
                    severity=Severity.WARNING,
                    message=(
                        f"the {component.label} balance involves no stream that "
                        f"crosses the control volume, so it generates no equation"
                    ),
                    where=(system.system_id, component.component_id),
                )
            )
            continue
        coefficients, constants = _assemble(terms)
        out.equations.append(
            BalanceEquation(
                equation_id=f"balance:{mode.value}:{component.component_id}",
                kind=EquationKind.COMPONENT_BALANCE,
                label=f"{component.label} balance ({mode.value})",
                expression=_expression(terms),
                coefficients=coefficients,
                constants=constants,
                component_id=component.component_id,
                process_mode=mode,
                inputs=_input_ids(terms),
                source_ref="Morris et al. 2011, sec. 4.4 and 4.5",
                note=(
                    "Independent material balance for one process component "
                    "(sec. 4.7.1: one independent balance can be written for each "
                    "process component)."
                ),
            )
        )

    if system.total_balance:
        # A total-mass equation sums one *declared total* per crossing stream.
        # A stream given as component amounts has no declared total: its total is
        # a derived consequence of its component flows, not an independent
        # variable.  Emitting the equation over only the streams that do declare
        # a total would produce something that looks like a system-wide balance
        # but silently omits the others -- usually an equation that cannot
        # close.  It is refused instead, and said why.
        without_total = [s for s in crossing if s.amount is None]
        if without_total:
            out.diagnostics.append(
                BalanceDiagnostic(
                    code="balance.total_not_generated",
                    severity=Severity.WARNING,
                    message=(
                        f"no total mass balance was generated: "
                        f"{[s.stream_id for s in without_total]} give component "
                        f"amounts and so carry no declared total to balance. Their "
                        f"totals follow from their component flows. Declare those "
                        f"streams by total plus composition if a total balance is "
                        f"required."
                    ),
                    where=(system.system_id, *[s.stream_id for s in without_total]),
                )
            )
        else:
            terms = []
            for stream in crossing:
                terms.extend(_stream_total_terms(stream, signs[stream.direction]))
            if terms:
                coefficients, constants = _assemble(terms)
                out.equations.append(
                    BalanceEquation(
                        equation_id=f"balance:{mode.value}:total",
                        kind=EquationKind.COMPONENT_BALANCE,
                        label=f"total mass balance ({mode.value})",
                        expression=_expression(terms),
                        coefficients=coefficients,
                        constants=constants,
                        process_mode=mode,
                        inputs=_input_ids(terms),
                        source_ref="Morris et al. 2011, sec. 4.4 and 4.18",
                        note=(
                            "Section 4.7.2 allows 'the total mass plus the number of "
                            "components - 1' in place of one balance per component. "
                            "When every component already has a balance this equation "
                            "is their sum and adds no independent information."
                        ),
                    )
                )

    for stream in system.streams:
        if not stream.mass_fractions:
            continue
        terms = [
            _Term(
                text=_fraction_symbol(stream.stream_id, component_id),
                sign=+1,
                coefficient=(
                    (fraction.variable_id, 1.0)
                    if isinstance(fraction, Unknown)
                    else None
                ),
                constant=(
                    None
                    if isinstance(fraction, Unknown)
                    else ConstantTerm(
                        quantity_id=fraction.quantity_id,
                        value=fraction.base_value,  # type: ignore[union-attr]
                        unit=base_unit(QuantityKind.MASS_FRACTION),
                        kind=QuantityKind.MASS_FRACTION,
                        provenance=fraction.provenance,  # type: ignore[union-attr]
                        source_ref=fraction.source_ref,  # type: ignore[union-attr]
                        sign=+1,
                    )
                ),
            )
            for component_id, fraction in stream.mass_fractions.items()
        ]
        terms.append(
            _Term(
                text="1",
                sign=-1,
                constant=ConstantTerm(
                    quantity_id=f"{stream.stream_id}:composition_target",
                    value=1.0,
                    unit=base_unit(QuantityKind.MASS_FRACTION),
                    kind=QuantityKind.MASS_FRACTION,
                    provenance=Provenance.DERIVED,
                    source_ref=None,
                    derivation=(
                        "the mass fractions of a complete composition sum to unity "
                        "(Morris et al. 2011, sec. 4.18)"
                    ),
                    sign=-1,
                ),
            )
        )
        coefficients, constants = _assemble(terms)
        out.equations.append(
            BalanceEquation(
                equation_id=f"composition:{stream.stream_id}",
                kind=EquationKind.COMPOSITION_SUM,
                label=f"{stream.label}: mass fractions sum to 1",
                expression=_expression(terms),
                coefficients=coefficients,
                constants=constants,
                stream_id=stream.stream_id,
                process_mode=mode,
                inputs=_input_ids(terms),
                source_ref="Morris et al. 2011, sec. 4.18",
            )
        )

    for constraint in system.constraints:
        if constraint.process_mode is not mode:
            out.diagnostics.append(
                BalanceDiagnostic(
                    code="constraint.mode_mismatch",
                    severity=Severity.WARNING,
                    message=(
                        f"constraint {constraint.equation_id!r} declares mode "
                        f"{constraint.process_mode.value!r} but the system is "
                        f"{mode.value!r}. It is included as written; check that the "
                        f"relation is valid for this mode."
                    ),
                    where=(system.system_id, constraint.equation_id),
                )
            )
        out.equations.append(constraint)

    for stream, missing in system.component_amounts_gap():
        out.diagnostics.append(
            BalanceDiagnostic(
                code="stream.component_absent",
                severity=Severity.WARNING,
                message=(
                    f"stream {stream.stream_id!r} gives component amounts without "
                    f"mentioning {sorted(missing)}. Each is therefore carried as a "
                    f"zero contribution in every balance that mentions it -- a "
                    f"strong reading of an omission. If the component really is "
                    f"present in that stream, those balances will not close. List "
                    f"it in `absent_components` if the absence is deliberate."
                ),
                where=(system.system_id, stream.stream_id),
            )
        )

    return out


# --------------------------------------------------------------------------- #
# linear algebra
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LinearSolution:
    """The outcome of solving the assembled system."""

    classification: Solvability
    rank: int
    n_unknowns: int
    n_equations: int
    values: Mapping[str, float]
    free_variables: tuple[str, ...]
    equation_residuals: Mapping[str, float]
    independent_equation_ids: tuple[str, ...]
    redundant_equation_ids: tuple[str, ...]
    inconsistent_equation_ids: tuple[str, ...]
    is_authoritative: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "rank": self.rank,
            "n_unknowns": self.n_unknowns,
            "n_equations": self.n_equations,
            "free_variables": list(self.free_variables),
            "independent_equation_ids": list(self.independent_equation_ids),
            "redundant_equation_ids": list(self.redundant_equation_ids),
            "inconsistent_equation_ids": list(self.inconsistent_equation_ids),
            "is_authoritative": self.is_authoritative,
        }


def _rref(
    matrix: Sequence[Sequence[float]],
    rhs: Sequence[float],
    tol: float,
) -> tuple[list[list[float]], list[int], int, list[list[int]]]:
    """Gauss-Jordan to reduced row echelon form with partial pivoting.

    Returns the reduced system, the pivot columns, the rank, and for each row
    the set of original equations it was formed from -- the last is what lets the
    engine name which supplied equations turned out to be dependent.
    """
    n_rows = len(matrix)
    n_cols = len(matrix[0]) if n_rows else 0
    work = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    origins: list[list[int]] = [[i] for i in range(n_rows)]
    pivot_columns: list[int] = []
    row = 0
    for col in range(n_cols):
        pivot = -1
        best = tol
        for candidate in range(row, n_rows):
            magnitude = abs(work[candidate][col])
            if magnitude > best:
                best = magnitude
                pivot = candidate
        if pivot < 0:
            continue
        work[row], work[pivot] = work[pivot], work[row]
        origins[row], origins[pivot] = origins[pivot], origins[row]
        pivot_value = work[row][col]
        # Normalise the pivot row before eliminating.  Without this the row is
        # only proportional to reduced row echelon form, and reading the solution
        # straight off it returns each value scaled by its own pivot.
        for j in range(col, n_cols + 1):
            work[row][j] /= pivot_value
        for candidate in range(n_rows):
            if candidate == row:
                continue
            factor = work[candidate][col]
            if factor == 0.0:
                continue
            for j in range(col, n_cols + 1):
                work[candidate][j] -= factor * work[row][j]
            origins[candidate] = sorted(set(origins[candidate]) | set(origins[row]))
        pivot_columns.append(col)
        row += 1
        if row == n_rows:
            break
    return work, pivot_columns, row, origins


def _least_squares(
    matrix: Sequence[Sequence[float]], rhs: Sequence[float], tol: float
) -> list[float]:
    """Minimum-residual solution by modified Gram-Schmidt.

    Used only to locate an inconsistency's magnitude and distribution.  It is not
    a proposed answer: reconciling measurements needs to know which one to
    distrust, and that is not something this engine can infer.
    """
    n_rows = len(matrix)
    n_cols = len(matrix[0]) if n_rows else 0
    basis: list[list[float]] = []
    upper: list[list[float]] = []
    for col in range(n_cols):
        vector = [matrix[i][col] for i in range(n_rows)]
        for k, q in enumerate(basis):
            projection = sum(q[i] * vector[i] for i in range(n_rows))
            upper[k][col] = projection
            for i in range(n_rows):
                vector[i] -= projection * q[i]
        norm = math.sqrt(sum(x * x for x in vector))
        upper.append([0.0] * n_cols)
        if norm <= tol:
            continue
        upper[-1][col] = norm
        basis.append([x / norm for x in vector])

    rank = len(basis)
    projected = [sum(basis[k][i] * rhs[i] for i in range(n_rows)) for k in range(rank)]
    solution = [0.0] * n_cols
    for k in range(rank - 1, -1, -1):
        accumulator = projected[k] - sum(
            upper[k][j] * solution[j] for j in range(k + 1, n_cols)
        )
        solution[k] = accumulator / upper[k][k]
    return solution


def _classify(
    n_unknowns: int, n_equations: int, rank: int, consistent: bool
) -> Solvability:
    """Map the matrix's shape onto the four cases the chapter distinguishes."""
    if not consistent:
        return Solvability.INCONSISTENT
    if n_unknowns == 0:
        # Nothing to determine.  Surplus equations are checks, not
        # over-specification to resolve; the count is reported separately as
        # n_equations - rank.
        return Solvability.NO_UNKNOWNS
    if rank == n_unknowns:
        return (
            Solvability.UNIQUE if n_equations == rank else Solvability.OVERCONSTRAINED
        )
    return Solvability.UNDERDETERMINED


def solve_linear(
    equations: Sequence[BalanceEquation],
    variable_ids: Sequence[str],
    *,
    tol: float = 1.0e-10,
) -> LinearSolution:
    """Solve the assembled system deterministically.

    Each equation is ``sum(c_j x_j) + sum(constants) = 0``, so the right-hand
    side is minus the constant sum.  A consistent full-rank system is solved
    exactly by Gauss-Jordan; a consistent rank-deficient one reports its free
    variables; an inconsistent one reports where the disagreement lies and
    solves nothing.
    """
    ordered_ids = list(variable_ids)
    index = {vid: i for i, vid in enumerate(ordered_ids)}
    n_cols = len(ordered_ids)
    n_rows = len(equations)

    matrix: list[list[float]] = []
    rhs: list[float] = []
    for equation in equations:
        row = [0.0] * n_cols
        for variable_id, coefficient in equation.coefficients.items():
            if variable_id not in index:
                raise BalanceError(
                    f"equation {equation.equation_id!r} references variable "
                    f"{variable_id!r}, which is not declared by any stream"
                )
            row[index[variable_id]] += coefficient
        matrix.append(row)
        rhs.append(-equation.constant_sum)

    if n_rows == 0:
        classification = _classify(n_cols, 0, 0, True)
        return LinearSolution(
            classification=classification,
            rank=0,
            n_unknowns=n_cols,
            n_equations=0,
            values={},
            free_variables=tuple(ordered_ids),
            equation_residuals={},
            independent_equation_ids=(),
            redundant_equation_ids=(),
            inconsistent_equation_ids=(),
            is_authoritative=True,
        )

    reduced, pivot_columns, rank, origins = _rref(matrix, rhs, tol)

    consistent_rows: list[int] = []
    inconsistent_rows: list[int] = []
    for i in range(n_rows):
        if all(abs(reduced[i][j]) <= tol for j in range(n_cols)) and abs(
            reduced[i][n_cols]
        ) > tol:
            inconsistent_rows.append(i)
        else:
            consistent_rows.append(i)
    consistent = not inconsistent_rows

    pivot_set = set(pivot_columns)
    free_columns = [c for c in range(n_cols) if c not in pivot_set]
    classification = _classify(n_cols, n_rows, rank, consistent)

    pivot_rows = origins[:rank]
    independent_ids: list[str] = []
    dependent_ids: list[str] = []
    for row_indices in pivot_rows:
        independent_ids.append(equations[min(row_indices)].equation_id)
    for i in range(n_rows):
        if i in inconsistent_rows:
            continue
        if equations[i].equation_id not in independent_ids:
            dependent_ids.append(equations[i].equation_id)

    inconsistent_ids = tuple(
        equations[i].equation_id for row in inconsistent_rows for i in origins[row]
    )

    values: dict[str, float] = {}
    equation_residuals: dict[str, float] = {}

    if classification in (Solvability.UNIQUE, Solvability.OVERCONSTRAINED) and consistent:
        for row, col in enumerate(pivot_columns):
            values[ordered_ids[col]] = reduced[row][n_cols]
        for i, equation in enumerate(equations):
            total = sum(
                matrix[i][j] * values.get(ordered_ids[j], 0.0) for j in range(n_cols)
            )
            equation_residuals[equation.equation_id] = total + equation.constant_sum
        return LinearSolution(
            classification=classification,
            rank=rank,
            n_unknowns=n_cols,
            n_equations=n_rows,
            values=values,
            free_variables=(),
            equation_residuals=equation_residuals,
            independent_equation_ids=tuple(dict.fromkeys(independent_ids)),
            redundant_equation_ids=tuple(dependent_ids),
            inconsistent_equation_ids=(),
            is_authoritative=True,
        )

    # underdetermined, or inconsistent: locate the free directions / the
    # disagreement without claiming a solution
    if consistent:
        point = [0.0] * n_cols
        for row, col in enumerate(pivot_columns):
            point[col] = reduced[row][n_cols]
        # A consistent system is authoritative even when it is under-determined:
        # section 4.7.2 notes that an under-specified balance "may still give
        # useful information", and the pivot variables are exactly that.  Free
        # variables are reported as free rather than being written as zeros, so
        # the representative solution is never mistaken for a determined value.
        for row, col in enumerate(pivot_columns):
            values[ordered_ids[col]] = point[col]
    else:
        point = _least_squares(matrix, rhs, tol)

    for i, equation in enumerate(equations):
        total = sum(matrix[i][j] * point[j] for j in range(n_cols))
        equation_residuals[equation.equation_id] = total + equation.constant_sum

    # A consistent system is authoritative even when it is under-determined:
    # section 4.7.2 notes that an under-specified balance "may still give useful
    # information", and the pivot variables are exactly that information.  Only a
    # contradictory system withholds values, because producing any of them would
    # mean silently picking a side.
    return LinearSolution(
        classification=classification,
        rank=rank,
        n_unknowns=n_cols,
        n_equations=n_rows,
        values=values,
        free_variables=tuple(ordered_ids[c] for c in free_columns),
        equation_residuals=equation_residuals,
        independent_equation_ids=tuple(dict.fromkeys(independent_ids)),
        redundant_equation_ids=tuple(dependent_ids),
        inconsistent_equation_ids=tuple(dict.fromkeys(inconsistent_ids)),
        is_authoritative=consistent,
    )


# --------------------------------------------------------------------------- #
# post-solve evaluation
# --------------------------------------------------------------------------- #


@dataclass
class _Resolved:
    """A stream's numbers after the solve, wherever they are available."""

    total: float | None
    components: dict[str, float | None]
    fractions: dict[str, float | None]


def _resolve_stream(stream: Stream, values: Mapping[str, float]) -> _Resolved:
    if stream.amount is not None:
        if isinstance(stream.amount, Quantity):
            total: float | None = stream.amount.base_value
        else:
            total = values.get(stream.amount.variable_id)
    else:
        total = None

    components: dict[str, float | None] = {}
    if stream.component_amounts:
        for component_id, value in stream.component_amounts.items():
            components[component_id] = (
                value.base_value
                if isinstance(value, Quantity)
                else values.get(value.variable_id)
            )
        if total is None:
            resolved = [v for v in components.values() if v is not None]
            total = sum(resolved) if len(resolved) == len(components) else None
    elif stream.mass_fractions:
        for component_id in stream.mass_fractions:
            components[component_id] = (
                total * _fraction_value(stream, component_id, values)
                if total is not None
                else None
            )

    fractions: dict[str, float | None] = {}
    for component_id in stream.mass_fractions:
        fraction_value = _fraction_value(stream, component_id, values)
        fractions[component_id] = fraction_value
        if (
            fraction_value is None
            and total is not None
            and total != 0.0
            and components.get(component_id) is not None
        ):
            fractions[component_id] = components[component_id] / total  # type: ignore[operator]

    # A stream declared as component amounts still has a composition, and the
    # ledger of section 4.5 reports one: "wBCd = 0.942" for the vapour of
    # Example 4.1 is read off the solved component flows, not stated anywhere.
    if stream.component_amounts and total not in (None, 0.0):
        for component_id, value in components.items():
            if value is not None:
                fractions[component_id] = value / total  # type: ignore[operator]

    return _Resolved(total=total, components=components, fractions=fractions)


def _fraction_value(
    stream: Stream, component_id: str, values: Mapping[str, float]
) -> float | None:
    fraction = stream.mass_fractions.get(component_id)
    if fraction is None:
        return None
    if isinstance(fraction, Quantity):
        return fraction.base_value
    return values.get(fraction.variable_id)


def _component_residuals(
    system: BalanceSystem, resolved: Mapping[str, _Resolved]
) -> list[BalanceResidual]:
    """Recompute every component balance from the solved numbers.

    This is the chapter's step 3 of section 4.6.2 -- check the answer against a
    dependent equation -- made mechanical.  It runs for *every* component, not
    only those that got a generated equation, because a check that only covers
    the equations that were solved cannot detect a wrong solution.
    """
    signs = DIRECTION_SIGNS[system.process_mode]
    tol = system.residual_tolerance
    unit_name = system.basis_unit
    residuals: list[BalanceResidual] = []
    for component in system.components:
        total = 0.0
        contributions: list[ResidualContribution] = []
        complete = True
        mentioned = False
        for stream in system.crossing_streams():
            sign = signs[stream.direction]
            declares = component.component_id in stream.components_declared
            mentioned = mentioned or declares
            value = resolved[stream.stream_id].components.get(component.component_id)
            if value is None:
                if declares:
                    # the stream declares this component but its flow could not
                    # be determined, so the balance cannot be evaluated at all
                    complete = False
                    continue
                # the stream does not carry this component, so its contribution
                # is a known zero.  It is listed rather than dropped so that the
                # residual reads as a complete ledger of the balance -- and so
                # that a reader can see a zero was *decided*, not overlooked.
                value = 0.0
            total += sign * value
            contributions.append(
                ResidualContribution(
                    stream_id=stream.stream_id,
                    label=stream.label,
                    value=sign * value,
                    unit=unit_name,
                )
            )
        if complete and mentioned:
            residuals.append(
                BalanceResidual(
                    label=f"{component.label} balance",
                    component_id=component.component_id,
                    value=total,
                    unit=unit_name,
                    basis_unit=unit_name,
                    tolerance=tol,
                    contributions=tuple(contributions),
                )
            )
    return residuals


def _total_residual(
    system: BalanceSystem, resolved: Mapping[str, _Resolved]
) -> BalanceResidual | None:
    signs = DIRECTION_SIGNS[system.process_mode]
    total = 0.0
    contributions: list[ResidualContribution] = []
    for stream in system.crossing_streams():
        value = resolved[stream.stream_id].total
        if value is None:
            return None
        total += signs[stream.direction] * value
        contributions.append(
            ResidualContribution(
                stream_id=stream.stream_id,
                label=stream.label,
                value=signs[stream.direction] * value,
                unit=system.basis_unit,
            )
        )
    return BalanceResidual(
        label="total mass balance",
        value=total,
        unit=system.basis_unit,
        basis_unit=system.basis_unit,
        tolerance=system.residual_tolerance,
        contributions=tuple(contributions),
    )


def _ledger(system: BalanceSystem, resolved: Mapping[str, _Resolved]) -> list[LedgerRow]:
    """The ledger of section 4.5: every stream/component cell that is known."""
    rows: list[LedgerRow] = []
    for stream in system.streams:
        state = resolved[stream.stream_id]
        for component in system.components:
            value = state.components.get(component.component_id)
            if value is None:
                continue
            rows.append(
                LedgerRow(
                    stream_id=stream.stream_id,
                    label=stream.label,
                    direction=stream.direction,
                    component_id=component.component_id,
                    component_label=component.label,
                    value=value,
                    unit=system.basis_unit,
                    kind=stream.kind,
                    provenance=Provenance.DERIVED,
                    mass_fraction=state.fractions.get(component.component_id),
                )
            )
    return rows


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def solve_balance(
    system: BalanceSystem,
    *,
    dof: Any | None = None,
) -> BalanceResult:
    """Generate, solve, and report one material balance.

    `dof`, when supplied, is a `models.degrees_of_freedom.DegreeOfFreedom`.  It
    is reported alongside the matrix-derived freedom but never in place of it:
    the matrix decides what is solvable, and any disagreement is surfaced as a
    diagnostic rather than reconciled away.
    """
    from .degrees_of_freedom import (  # local import: avoids a module cycle
        IndependentDegreesOfFreedom,
        compare_freedom,
    )

    equation_set = generate_equations(system)
    diagnostics: list[BalanceDiagnostic] = list(equation_set.diagnostics)

    variable_specs = _collect_variable_specs(system)
    # Variables that only ever appear on cancelled internal streams cannot be
    # determined, so they are excluded from the matrix rather than silently
    # inflating it with columns that are identically zero.
    internal_ids = {
        vid
        for stream in system.internal_streams()
        for vid in stream.unknown_variable_ids()
    }
    solved_ids = [vid for vid in variable_specs if vid not in internal_ids]
    if internal_ids:
        for vid in sorted(internal_ids):
            spec = variable_specs[vid]
            diagnostics.append(
                BalanceDiagnostic(
                    code="variable.internal_cancels",
                    severity=Severity.INFO,
                    message=(
                        f"{vid} belongs to internal stream {spec.stream_id!r} and "
                        f"cancels from every balance around this control volume, so "
                        f"it is not solved."
                    ),
                    where=(system.system_id, spec.stream_id),
                )
            )

    solution = solve_linear(
        equation_set.equations, solved_ids, tol=system.rank_tolerance
    )

    if solution.classification is Solvability.INCONSISTENT:
        diagnostics.append(
            BalanceDiagnostic(
                code="system.inconsistent",
                severity=Severity.ERROR,
                message=(
                    f"the {system.process_mode.value} balances cannot all be "
                    f"satisfied: {len(solution.inconsistent_equation_ids)} equation(s) "
                    f"contradict the others. Residuals are reported so the conflicting "
                    f"measurements can be identified, but nothing is solved and no "
                    f"measurement is altered. Section 4.7 requires a judgement about "
                    f"which reading is least accurate; the engine has no basis for "
                    f"making it."
                ),
                where=(system.system_id, *solution.inconsistent_equation_ids),
            )
        )
    elif solution.classification is Solvability.UNDERDETERMINED:
        diagnostics.append(
            BalanceDiagnostic(
                code="system.underdetermined",
                severity=Severity.WARNING,
                message=(
                    f"{solution.n_unknowns} unknowns against a rank of "
                    f"{solution.rank}: {len(solution.free_variables)} variable(s) "
                    f"cannot be determined. The system is under-specified; a further "
                    f"measurement or a declared assumption is needed."
                ),
                where=(system.system_id, *solution.free_variables),
            )
        )
    elif solution.classification is Solvability.OVERCONSTRAINED:
        diagnostics.append(
            BalanceDiagnostic(
                code="system.overconstrained",
                severity=Severity.WARNING,
                message=(
                    f"{solution.n_equations} equations of rank {solution.rank}: "
                    f"{len(solution.redundant_equation_ids)} are dependent on the "
                    f"others. They are mutually consistent, so the balance still "
                    f"closes, but they add no independent information (sec. 4.6.2)."
                ),
                where=(system.system_id, *solution.redundant_equation_ids),
            )
        )
    elif solution.classification is Solvability.NO_UNKNOWNS:
        diagnostics.append(
            BalanceDiagnostic(
                code="system.verification_only",
                severity=Severity.INFO,
                message=(
                    "every quantity is stated, so this run verifies the stated data "
                    "against conservation rather than solving for anything."
                ),
                where=(system.system_id,),
            )
        )

    point = solution.values if solution.is_authoritative else _least_squares_point(
        equation_set.equations, solved_ids, system.rank_tolerance
    )
    resolved = {s.stream_id: _resolve_stream(s, point) for s in system.streams}

    variables: list[SolvedVariable] = []
    unresolved: list[UnresolvedVariable] = []
    if solution.is_authoritative:
        for variable_id in solved_ids:
            spec = variable_specs[variable_id]
            if variable_id in solution.free_variables:
                continue
            base_value = point[variable_id]
            try:
                reported_value = convert_between(
                    base_value, base_unit(spec.kind), spec.unit
                )
            except BalanceError:
                reported_value = base_value
            variables.append(
                SolvedVariable(
                    variable_id=variable_id,
                    value=reported_value,
                    unit=spec.unit,
                    kind=spec.kind,
                    source_unit=base_unit(spec.kind),
                    source_value=base_value,
                    method=(
                        "solved from the assembled linear balance system "
                        f"(rank {solution.rank} of {solution.n_unknowns} unknowns)"
                    ),
                    inputs=tuple(
                        e.equation_id
                        for e in equation_set.equations
                        if variable_id in e.coefficients
                    ),
                )
            )
        for variable_id in solved_ids:
            if variable_id in solution.free_variables:
                spec = variable_specs[variable_id]
                unresolved.append(
                    UnresolvedVariable(
                        variable_id=variable_id,
                        unit=spec.unit,
                        kind=spec.kind,
                        reason=(
                            f"under-determined: no independent equation constrains it "
                            f"({solution.n_unknowns} unknowns, rank {solution.rank})"
                        ),
                    )
                )
    else:
        for variable_id in solved_ids:
            spec = variable_specs[variable_id]
            unresolved.append(
                UnresolvedVariable(
                    variable_id=variable_id,
                    unit=spec.unit,
                    kind=spec.kind,
                    reason=(
                        "not solved: the equations are mutually inconsistent, so any "
                        "value would require disregarding a stated measurement "
                        "(Morris et al. 2011, sec. 4.7). See the reported residuals."
                    ),
                )
            )

    component_residuals = _component_residuals(system, resolved)
    total_residual = _total_residual(system, resolved)

    if not solution.is_authoritative:
        diagnostics.append(
            BalanceDiagnostic(
                code="residual.not_authoritative",
                severity=Severity.WARNING,
                message=(
                    "residuals are evaluated at the minimum-residual point of the "
                    "inconsistent system. That point is a device for locating which "
                    "measurements disagree; it is not a reconciliation, and no value "
                    "it implies is reported as solved."
                ),
                where=(system.system_id,),
            )
        )

    for residual in [
        *component_residuals,
        *([total_residual] if total_residual is not None else []),
    ]:
        if not residual.is_within_tolerance:
            diagnostics.append(
                BalanceDiagnostic(
                    code="residual.exceeds_tolerance",
                    severity=Severity.WARNING,
                    message=(
                        f"{residual.label} does not close: {residual.value:.6g} "
                        f"{residual.unit} against a tolerance of "
                        f"{residual.tolerance:g}. Section 4.6.3 treats a balance "
                        f"that does not close as a finding about the data."
                    ),
                    where=(system.system_id, *(c.stream_id for c in residual.contributions)),
                )
            )

    freedom = None
    if dof is not None:
        independent = IndependentDegreesOfFreedom(
            n_unknowns=solution.n_unknowns,
            n_equations=solution.n_equations,
            rank=solution.rank,
        )
        comparison = compare_freedom(dof, independent=independent)
        freedom = comparison
        diagnostics.extend(comparison.diagnostics)

    return BalanceResult(
        system_id=system.system_id,
        label=system.label,
        process_mode=system.process_mode,
        basis=system.basis.value,
        basis_unit=system.basis_unit,
        solvability=solution.classification,
        n_unknowns=solution.n_unknowns,
        n_equations=solution.n_equations,
        rank=solution.rank,
        equations=tuple(equation_set.equations),
        variables=tuple(variables),
        unresolved=tuple(unresolved),
        component_residuals=tuple(component_residuals),
        total_mass_residual=total_residual,
        ledger=tuple(_ledger(system, resolved)),
        equation_residuals=dict(solution.equation_residuals),
        independent_equation_ids=solution.independent_equation_ids,
        redundant_equation_ids=solution.redundant_equation_ids,
        inconsistent_equation_ids=solution.inconsistent_equation_ids,
        freedom=freedom,
        diagnostics=tuple(diagnostics),
        assumptions=system.assumptions,
        source_ref=system.source_ref,
        notes=system.notes,
    )


def convert_between(value: float, src: str, dst: str) -> float:
    """Convert between two registered units, surfacing any failure as BalanceError."""
    try:
        source = lookup_unit(src)
        target = lookup_unit(dst)
    except Exception as exc:  # pragma: no cover - defensive
        raise BalanceError(str(exc)) from exc
    if source.kind is not target.kind:
        raise BalanceError(
            f"cannot convert {src!r} to {dst!r}: different quantity kinds"
        )
    return (value * source.to_base) / target.to_base


def _least_squares_point(
    equations: Sequence[BalanceEquation],
    variable_ids: Sequence[str],
    tol: float,
) -> dict[str, float]:
    """The minimum-residual point, for evaluating residuals on a bad system."""
    ordered = list(variable_ids)
    index = {vid: i for i, vid in enumerate(ordered)}
    matrix: list[list[float]] = []
    rhs: list[float] = []
    for equation in equations:
        row = [0.0] * len(ordered)
        for variable_id, coefficient in equation.coefficients.items():
            if variable_id in index:
                row[index[variable_id]] += coefficient
        matrix.append(row)
        rhs.append(-equation.constant_sum)
    if not matrix:
        return {}
    point = _least_squares(matrix, rhs, tol)
    return {ordered[i]: point[i] for i in range(len(ordered))}


__all__ = [
    "DIRECTION_SIGNS",
    "BalanceError",
    "BilinearTerm",
    "EquationSet",
    "LinearSolution",
    "VariableSpec",
    "generate_equations",
    "solve_balance",
    "solve_linear",
]