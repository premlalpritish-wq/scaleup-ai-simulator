"""ScaleUp AI material balance engine (v0.1) -- the model layer.

`material_balance` generates the conservation equations a `BalanceSystem`
declares and solves them with a deterministic, dependency-free linear solver.
`degrees_of_freedom` implements the chapter's DOF bookkeeping and, separately,
the matrix-rank check that the bookkeeping is not entitled to stand in for.

Both modules are grounded in Morris, Geiger & Fine (2011), Chapter 4.
"""

from __future__ import annotations

from .degrees_of_freedom import (
    DISTILLATION_OVERALL,
    DISTILLATION_PROCESS,
    DISTILLATION_STILL_I,
    DISTILLATION_STILL_II,
    SALTCAKE_PROCESS,
    SPENT_GAS_SPLITTER,
    DegreeOfFreedom,
    FreedomComparison,
    FreedomKind,
    IndependentDegreesOfFreedom,
    compare_freedom,
    process_dof,
)
from .material_balance import (
    DIRECTION_SIGNS,
    BalanceError,
    BilinearTerm,
    EquationSet,
    LinearSolution,
    VariableSpec,
    generate_equations,
    solve_balance,
    solve_linear,
)

__all__ = [
    "DISTILLATION_OVERALL",
    "DISTILLATION_PROCESS",
    "DISTILLATION_STILL_I",
    "DISTILLATION_STILL_II",
    "DIRECTION_SIGNS",
    "SALTCAKE_PROCESS",
    "SPENT_GAS_SPLITTER",
    "BalanceError",
    "BilinearTerm",
    "DegreeOfFreedom",
    "EquationSet",
    "FreedomComparison",
    "FreedomKind",
    "IndependentDegreesOfFreedom",
    "LinearSolution",
    "VariableSpec",
    "compare_freedom",
    "generate_equations",
    "process_dof",
    "solve_balance",
    "solve_linear",
]