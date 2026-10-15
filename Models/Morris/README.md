# Morris, Geiger & Fine (2011) â€” material balance engine

A deterministic, testable conservation engine based on Chapter 4,
"Fundamentals of Material Balances with Applications to Non-Reacting Systems",
of Morris, Geiger & Fine, *Introduction to Chemical Engineering: Materials,
Energy, and Balance*, 4th ed. (2011).

**Read [`MODEL_REPORT.md`](MODEL_REPORT.md) first.** It states exactly what the
engine computes and does not compute, and documents three internal
inconsistencies found in the source text.

## Quick start

```bash
python -m pytest tests -q    # 186 tests, no third-party runtime dependencies
```

## What it is

A typed model of one **control volume**, its **components**, and its **streams**,
which generates the conservation equations the declaration implies and solves
them with a pure-Python linear solver.

```python
from schemas.material_balance import (
    BalanceBasis, BalanceSystem, Component, Direction, ProcessMode,
    QuantityKind, Stream, reported, unknown, stream_component_id,
    stream_fraction_id,
)
from models.material_balance import solve_balance

system = BalanceSystem(
    system_id="cd-zn",
    label="Distillation of a Cd-Zn alloy",
    process_mode=ProcessMode.STEADY_STATE,
    basis=BalanceBasis.MASS,
    components=(
        Component("Cd", "cadmium", formula="Cd", molar_mass_kg_per_mol=0.112414),
        Component("Zn", "zinc",     formula="Zn", molar_mass_kg_per_mol=0.065388),
    ),
    streams=(
        Stream("A", "original alloy", Direction.INPUT,
               amount=reported("A:total", 1000.0, "kg/h", source_ref="Example 4.1"),
               mass_fractions={"Cd": reported("A:w_Cd", 0.50, "1", source_ref="Example 4.1"),
                               "Zn": unknown(stream_fraction_id("A","Zn"), QuantityKind.MASS_FRACTION)}),
        Stream("B", "vapour", Direction.OUTPUT, component_amounts={
            "Cd": reported(stream_component_id("B","Cd"), 454.0, "kg/h", source_ref="Example 4.1"),
            "Zn": unknown(stream_component_id("B","Zn"), QuantityKind.MASS_FLOW)}),
        Stream("C", "Zn-rich alloy", Direction.OUTPUT, component_amounts={
            "Zn": reported(stream_component_id("C","Zn"), 472.0, "kg/h", source_ref="Example 4.1"),
            "Cd": unknown(stream_component_id("C","Cd"), QuantityKind.MASS_FLOW)}),
    ),
)

result = solve_balance(system)
result.solvability            # Solvability.UNIQUE
result.rank                   # 3
{s.stream_id for s in result.ledger}   # {'A','B','C'}
```

This reproduces Example 4.1 exactly: 28 kg/h of zinc in the vapour, 46 kg/h of
cadmium in the liquid, stream totals of 482 and 518 kg/h, and the book's
`wB_Cd = 0.942` and `wC_Zn = 0.911`.

## Equation forms

| Mode | Equation | Source |
|---|---|---|
| `STEADY_STATE` | `Î£(inflow of i) âˆ’ Î£(outflow of i) = 0` | §4.4, §4.5 |
| `ACCUMULATING` | `Î£(inflow of i) âˆ’ Î£(outflow of i) âˆ’ accumulation = 0` | §4.4, Example 4.3 |
| `BATCH` | `final âˆ’ initial âˆ’ added + removed = 0` | §4.18 |
| composition | `Î£(mass fractions of a stream) = 1` | §4.18 |

Only the forms the declared mode admits are generated. `BalanceSystem` rejects a
stream whose direction the mode does not allow, so a steady-state balance is
never quietly applied to a batch.

## The data contract

Every number is a `Quantity` carrying a value, a unit, a **semantic kind**, and a
**provenance**:

| Provenance | Must carry |
|---|---|
| `reported` | a `source_ref` pointing at the place the value was stated |
| `derived` | a `derivation` describing the calculation |
| `assumed` | an `assumption_id` and rationale, in `source_ref` |

The kind is one of `MASS`, `MASS_FLOW`, `MASS_FRACTION`, `AMOUNT`, `AMOUNT_FLOW`.
Units are bound to a kind, so `convert(1.0, "kg", "mol")` raises rather than
guessing a molar mass. There is no `TIME` kind: a time basis is carried by a
flow's unit (`"kg/min"`), and is recorded on the stream.

**Unknowns are explicit.** A quantity the source does not supply is an
`Unknown`, which names the variable, its kind, and the gap â€” never a value.
`Unknown` is a separate type from `Quantity` precisely so that "unknown" cannot
be written as "zero".

**Composition completeness is declared.** A stream that gives mass fractions
must list the components it omits in `absent_components`. Otherwise an omission
would silently act like a zero fraction once `Î£w = 1` is generated.

## Solvability

| Result | Meaning |
|---|---|
| `UNIQUE` | every unknown determined |
| `UNDERDETERMINED` | fewer independent equations than unknowns; free variables named |
| `INCONSISTENT` | the measurements contradict each other |
| `OVERCONSTRAINED` | more equations than unknowns, but mutually consistent |
| `NO_UNKNOWNS` | nothing to solve; the run verifies stated data |

An inconsistent system reports residuals and solves **nothing**. Section 4.7
requires "a judgment call about which flow value is the least accurate", and the
engine has no basis for making it. Least squares is used only to locate *which*
equations disagree; its values are never presented as solved.

A dependent equation is not an error. Section 4.6.2 calls it a check, and it is
reported as one.

## Degrees of freedom

Section 4.7.2's bookkeeping is implemented as
`DOF = SV âˆ’ IB âˆ’ IC âˆ’ F âˆ’ SR`, with all five terms supplied explicitly. `dof` is
`None` unless all five are present â€” a partially known count is an unknown
count, not a small one.

It is reported **alongside**, never in place of, `n_unknowns âˆ’ rank(A)`. The
chapter is explicit about why this matters: writing the equations and checking
that `N_equations = N_unknowns` "is easy to inadvertently write one or more
non-independent equations, which creates the impression that a sufficient number
of independent equations have been written". Where the two counts disagree, the
matrix wins and the disagreement is emitted as a diagnostic.

`process_dof()` implements the multi-device rule of §4.9: balances add, but a
connecting stream's stream variables and compositions are subtracted so they are
not counted twice.

## What it does not do

No reaction kinetics. No stoichiometry. No empirical fitting. No reconciliation of
inconsistent measurements by editing source data. No claim of predictive
validation â€” these are conservation-law tests, and passing them shows only that a
declared set of numbers is internally consistent with conservation of mass.

## Layout

| Path | Contents |
|---|---|
| `schemas/material_balance.py` | units, quantity kinds, provenance, `Component`, `Stream`, `BalanceSystem`, `BalanceEquation`, `BalanceResult`, `BalanceDiagnostic` |
| `models/material_balance.py` | equation generation, the linear solver, residuals, the ledger |
| `models/degrees_of_freedom.py` | the §4.7.2 bookkeeping, matrix rank, and their comparison |
| `tests/test_material_balance.py` | 108 unit, integration, solvability and regression tests |
| `tests/test_acceptance_criteria.py` | 78 tests implementing MB-01 … MB-12, one class per criterion |

## The tests are checked against deliberate breakage

Mutating the engine to break it is how the suite was validated. All **24**
mutations tried are caught. They include, from the core suite: dropping the
pivot-row normalisation in the solver, flipping an output sign, swapping the
batch `ADDED`/`REMOVED` signs, trusting least-squares values on inconsistent
data, reporting a free variable as a solved zero, deleting the composition-sum
equation, allowing a bilinear balance through, defaulting an incomplete DOF to
zero, and letting the bookkeeping override the rank.

From the MB-01…MB-12 acceptance suite: silently renormalizing a composition that
sums to 0.98, emitting a total balance over only some streams, returning a
solved value in the wrong unit, dropping the equations a solved variable came
from, counting a redundant equation toward rank, and letting `kg` convert
silently to `kg/h`.

Four mutations exposed real gaps in the implementation or the suite, now fixed
and covered:

* nothing pinned that a **free variable is never reported as a solved zero** —
  the exact fabrication the engine exists to prevent;
* nothing pinned that an **underdetermined system still reports the variables it
  can determine**, which §4.7.2 explicitly says is possible;
* a component **absent from a stream** was being treated as unknown, which
  silently suppressed that component's residual entirely rather than
  contributing a declared zero;
* a **total balance** requested over streams given as component amounts produced
  an equation that looked system-wide while omitting most streams. It is now
  refused with a reason.

## Serialization

`solve_balance(...).to_dict()` returns equations (with their constants and each
constant's provenance), solved variables, unresolved variables with reasons,
rank and equation counts, per-equation and per-component residuals, the ledger,
diagnostics and assumptions.
