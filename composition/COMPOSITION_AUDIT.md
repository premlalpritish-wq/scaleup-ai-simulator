# Composition Audit

**Scope.** Pre-coding audit of the two existing ScaleUp AI models, performed before
any composition code was written, to establish what can be connected without
inventing scientific content.

**Method.** Every claim below was read out of the source and, where it is a
behavioural claim about running code, verified by executing it. Verbatim
verification output is quoted. No model equation, schema, fixture or test was
modified during this audit; the pre-existing suites were run first to fix a
baseline (see §7).

---

## 1. Inventory

| | Zieliński et al. (2019) | Morris, Geiger & Fine (2011) |
|---|---|---|
| Package root | `Models/Zielinski/` | `Models/Morris/` |
| Declared version | `1.0.0` (`pyproject.toml`, `scaleup_ai.__version__`) | `0.1.0` (`pyproject.toml`) |
| Entry point (programmatic) | `models.zielinski_2019.build_engine() -> ExecutionEngine` | `models.material_balance.solve_balance(BalanceSystem) -> BalanceResult` |
| Entry point (CLI) | `run_model.py` → writes `out/` artifacts | **none** — library only, no `__main__`, no CLI |
| Schema/core package | `scaleup_ai/` (`units`, `provenance`, `process`, `equations`, `engine`, `serialize`, `report`) | `schemas/material_balance.py`, plus `models/degrees_of_freedom.py` |
| Tests | `tests/` — 223 tests, AT-001…AT-026 | `tests/` — 186 tests, MB-01…MB-12 |
| Runtime dependencies | none | none |
| Python | ≥3.11 (verified on 3.14.7) | ≥3.11 (verified on 3.14.7) |

### 1.1 Entry points, precisely

**Zieliński.** There are three distinct construction steps, all pure:

```
build_graph()   -> ProcessGraph        # 15 nodes, 17 streams, 253 quantities
build_bindings()-> list[EquationBinding]        # 20 bindings
build_cross_checks() -> list[CrossCheck]        # 8 cross-checks
build_capabilities()/build_keyword_models() -> fail-closed maps
build_engine()  -> ExecutionEngine
engine.run(mode=ExecutionMode.EVIDENCE_REPLAY)  -> RunResult
engine.run(mode=ExecutionMode.PREDICTIVE)       -> RunResult   # fails closed
engine.request("node:N15:insulin_mass_from_au", mode=PREDICTIVE) -> Resolution
```

**Morris.** One function:

```
solve_balance(system: BalanceSystem, *, dof=None) -> BalanceResult
```

with the declaration `BalanceSystem(...)` carrying the control volume, its
components, its streams and its `ProcessMode`. There is no runner and no
serialisation entry point other than `BalanceResult.to_dict()`.

> **Consequence for Phase 3.** Morris has no CLI. The composition runner must
> call `solve_balance` in-process. Only the *composition runner itself* can be
> invoked as a subprocess, which is exactly the shape Phase 4 asks for.

---

## 2. What each model actually computes

### 2.1 Zieliński — a process graph with 20 executable accounting identities

The scientific content is a faithful transcription of the paper's reported
numbers plus a registry of **20 transparent identities** in
`scaleup_ai/equations.py`: mass-per-volume, mass fraction, volume sum, dilution,
AU × volume, the six formulas printed verbatim in the paper (ZnCl₂, aprotinin,
EDTA, water, CPB), stock/target dilution arithmetic, Tris molarity, implied
final volume, AU percent yield, mass deviation and ppm deviation.

Verified by execution:

```
mode = evidence_replay
nodes_executed = 12     nodes_partial = 0
nodes_observed_only = 3 nodes_unresolved = 0
observed_reference_values = 142   digitized_values = 20
computed_values = 20    predicted_values = 0
unknown_values = 11     unresolved_targets = 3
validation_errors = 5   validation_warnings = 6
cross_check_errors = 2
graph_is_predictive = False

--- predictive ---
unresolved targets: 23   predicted: 0
```

The eight registered **missing models** (`kinetics.growth_ode`,
`kinetics.monod_substrate`, `transfer.oxygen_kla`, `folding.renaturation_kinetics`,
`calibration.au_to_mass`, `recovery.stage_yield`, `activity.iu_from_au`,
`scaleup.effect_of_scale`) are declared and never implemented. Predictive mode
with no inputs resolves **0 of 23** targets — that is the designed outcome.

Note the replay summary carries **5 validation errors and 2 cross-check errors**.
These are pre-existing findings *inside* the model (the paper's own internal
contradictions, §2.5 and §4.9). A composition layer must carry them through
verbatim and must not reclassify them as its own.

### 2.2 Morris — a non-reacting conservation engine

`solve_balance` generates only the equation forms the declared `ProcessMode`
admits and solves them with Gauss-Jordan. Its own README states the scope:
**no reaction kinetics, no stoichiometry, no empirical fitting, no predictive
validation.** The chapter it implements is titled *"Fundamentals of Material
Balances with Applications to **Non-Reacting Systems**"*.

---

## 3. The two unit registries do not agree

Both models have a unit registry, a `convert()` that raises on a dimension
mismatch, and a dimension/kind taxonomy. **They are disjoint.**

| Quantity | Morris key | Morris units | Zieliński key | Zieliński units |
|---|---|---|---|---|
| Mass | `QuantityKind.MASS` | `kg g mg t lb` | `Dimension.MASS` | `g mg ug` |
| Mass flow | `QuantityKind.MASS_FLOW` | `kg/h kg/min kg/s g/h g/min lb/h lb/min` | — *(none)* | — |
| Mass fraction | `QuantityKind.MASS_FRACTION` | `1 %` | `Dimension.DIMENSIONLESS` | `1 % OD600` |
| Amount / amount flow | `AMOUNT` `AMOUNT_FLOW` | `mol kmol gmol lbmol`, `mol/h …` | — *(none)* | — |
| Volume | — *(none)* | — | `Dimension.VOLUME` | `mL L dm3 cm3 uL` |
| Volume rate | — | — | `VOLUME_RATE` | `mL/min mL/h` |
| Time | **no time dimension at all** | carried only in a flow unit | `TIME` | `h min s d` |
| Molar concentration | — | — | `MOLAR_CONCENTRATION` | `M mM uM` |
| Absorbance | — | — | `ABSORBANCE`, `ABSORBANCE_PER_VOLUME` | `AU`, `AU/mL`, `AU/uL` |
| Activity | — | — | `ACTIVITY`, `ACTIVITY_PER_VOLUME` | `IU`, `IU/L` |
| pH, molar mass, conductivity, RCF, concentration factor, wavelength | — | — | `PH`, `MOLAR_MASS`, `CONDUCTIVITY`, `RELATIVE_CENTRIFUGAL_FORCE`, `CONCENTRATION_FACTOR`, `WAVELENGTH` | `pH`, `Da`, `mS`, `xg`, `fold`, `nm` |

Verified: Morris's registry rejects `AU`, `mL`, `h`, `L`, `g/L` and `OD600`.

### 3.1 The one symbol that collides is `%` — and it means different things

```
morris    %  -> kind = mass_fraction,   to_base = 0.01
zielinski %  -> dim  = dimensionless,   to_base = 0.01
```

Identical conversion factor, **incompatible meaning**. In Morris `%` is a
component's fraction of a stream and participates in `Σw = 1`. In Zieliński it
is a generic percent used for feed concentrations (40 % glucose, 16 % NH₄OH).
Connecting them on the strength of the shared symbol would be exactly the
quantity-laundering this project forbids. The composition layer therefore keys
port compatibility on the **quantity**, never on the symbol.

### 3.2 Base units differ for the one shared quantity

Mass is the only physical quantity both registries implement, and both are
linearly convertible within it — but the **base units differ** (`kg` vs `g`).
So `kg → g` is a legitimate conversion that must be *declared by the composition
layer*, not silently inferred by either model.

---

## 4. Structural incompatibilities (blocking, and not fixable by conversion)

### 4.1 The Zieliński model has no component identity at all

Morris's central abstraction is `Component` — "a conserved entity that can carry
an independent balance" (§4.7.1). Every Morris balance is a set of component
equations.

The Zieliński model's `StreamKind` vocabulary is:

```
fermentation_medium  wet_biomass  inclusion_bodies  denatured_protein_solution
renatured_precursor  citraconylated_precursor  digested_precursor
chromatographic_fraction  insulin_fraction  citrate_blocked_fraction
insulin_zinc_precipitate  dissolved_zinc_salt  final_product  waste
```

These are **process roles, not chemical species**. `inclusion_bodies` is not a
substance; `chromatographic_fraction` is a unit-operation output label. Dumped
to JSON:

```
S03_wet_biomass  wet_biomass_total            = reported 224 g
S04_inclusion_bodies inclusion_bodies_total  = reported 58 g
S05_denatured_solution ib_aliquot_mass        = reported 17.9 g
                    dissolved_protein          = reported 5460 AU
                    dissolved_protein_concentration = unknown (AU/mL)
S09_deae_fraction fraction_volume = 250 mL,  protein_concentration = 8.57 AU/mL
...
```

**Not one Zieliński stream carries a component amount or a mass fraction.**
There is nothing to balance: the model reports process quantities (optical
density, absorbance, volumes, doses), not component flows.

> **Finding.** Mapping a `StreamKind` onto a Morris `Component` would be an
> invented scientific assumption. The composition layer must refuse to do it and
> say so. This is acceptance criterion CG-08.

### 4.2 Every Zieliński boundary is reactive; Morris is non-reacting

The Zieliński process converts matter:

* `N01` fermentation — glucose and proline are converted to biomass;
* `N06` citraconylation — Lys/Arg residues gain a citraconic amide;
* `N07` proteolysis — the precursor is *cleaved* by trypsin;
* `N09` decitraconylation — the amide is hydrolysed.

Mass is therefore **not conserved** across those boundaries. The paper supplies
no stoichiometry, no reaction extent and no reaction terms. Morris's schema has
no field in which a reaction could be declared: `ProcessMode` admits
`STEADY_STATE`, `ACCUMULATING` and `BATCH`, and the generated equations are
`Σin − Σout [− accumulation] = 0` with **no reaction term**. `BalanceSystem`
does not accept one.

> **Finding.** A Morris balance drawn around any Zieliński reactive stage would
> be numerically valid and physically wrong — the exact failure mode the Morris
> README names ("a steady-state balance is never applied to a batch because it
> would be numerically valid and physically wrong"). The composition layer must
> refuse and name the absent reaction terms. This is CG-09.

### 4.3 Time basis: batch inventories cannot enter a flow balance

Every Zieliński mass is a **batch inventory** (224 g of wet biomass from a
single 4 L batch). Morris refuses this itself, verified:

```
BalanceSystemError: stream 'A' is a mass stream, but steady_state is a flow mode
and requires mass_flow quantities. Restate the balance on a rate basis, or
declare the operating time interval and use accumulating with QuantityKind.MASS
```

and the mirror image for `BATCH` (which rejects flow streams outright).

A conversion from `g` to `kg/h` would need a duration. The paper states batch
durations as **ranges** (`15–16 h`, `4–5 h`) which the Zieliński model
deliberately refuses to collapse to a point value, and which in any case would
only produce a batch-average rate, not a steady-state one.

> **Finding.** Mass ↔ mass-flow is a *quantity* change, not a unit change. No
> conversion model can bridge it here. This is CG-03 and CG-02.

### 4.4 Morris's implicit reaction restriction is not parameterised

Morris's `ProcessMode` and `DIRECTION_SIGNS` hard-code non-reacting behaviour;
there is no flag, capability or metadata that a composition layer could query
to ask "does this control volume contain reaction?". The composition layer has
to declare that restriction itself, from the citation, and enforce it. This is
recorded as an explicit assumption in `COMPOSITION_SPEC.md` §A-3.

---

## 5. Interfaces, provenance and diagnostics conventions

### 5.1 Provenance — the two vocabularies do not match

| Zieliński `Provenance` | Morris `Provenance` | shared? |
|---|---|---|
| `REPORTED` | `REPORTED` | yes |
| `DERIVED` | `DERIVED` | yes |
| `DIGITIZED` | — | **no** |
| `ASSUMED` | `ASSUMED` | yes |
| `UNKNOWN` | — (replaced by the separate `Unknown` type) | **conceptually, not syntactically** |

Both enforce the same structural rule — a value cannot be absent and present,
and the class dictates what must accompany it:

* Zieliński: `provenance is UNKNOWN ⇒ value must be None`, enforced in
  `Quantity.__post_init__`, which raises `QuantityError`.
* Morris: `Unknown` is a *different class* from `Quantity`, so "unknown" cannot
  be written as "zero" even by accident.

Zieliński additionally carries `Basis` (`observed_reference / assumed_input /
computed / unresolved`), `EvidenceRef` (page-level citation), `Uncertainty`,
`MissingParameter` and `Assumption`. Morris carries a `source_ref` string and
`Assumption`. Zieliński's evidence is strictly richer; Morris's `source_ref` is
a free-text string.

### 5.2 Diagnostics

Both use `(code, severity, message, where)` with severities `info / warning /
error`. Zieliński: `ValidationMessage` in `scaleup_ai/provenance.py`.
Morris: `BalanceDiagnostic` in `schemas/material_balance.py`. The shapes are
close enough to share one composition-level diagnostic type without loss.

### 5.3 Serialisation

Zieliński has `to_dict()` throughout plus `scaleup_ai/serialize.py` with a
round-trip test. Morris has `to_dict()` on every schema object including
`BalanceResult`, but **no loader** — `graph_from_dict()` does not exist for
Morris. The composition layer therefore receives Morris systems as Python
declarations in the adapter, not as JSON.

### 5.4 Identifier namespaces do not collide

* Zieliński locations: `node:N01` … `node:N15`, `stream:S01_inoculum` …
  `stream:S17_final_product`, quantity ids like `wet_biomass_total`.
* Morris variable ids: `stream:A:Cd`, `stream:A:w:Cd`, `stream:A:total`.

They are structurally different but not disjoint in principle, so every port in
a composition graph is keyed by `(instance_id, port_id)` and provenance entries
carry the owning instance. Verified no collision in practice, but the namespacing
is required for correctness, not just tidiness.

---

## 6. What can actually be connected — the honest answer

### 6.1 Legal

| Edge | Why it is legal |
|---|---|
| Morris `kg`/`g` mass ↔ Morris `kg` mass | Same `QuantityKind.MASS`; `g` is registered in Morris (`to_base = 1e-3`). A declared within-kind conversion. |
| Morris mass fraction `1` ↔ Morris mass fraction `1` | Same kind. |
| Morris mass flow `kg/h` ↔ Morris mass flow `g/h` | Same kind. |
| **Zieliński `g` ↔ Morris `kg`/`g`** | Same *physical quantity* (mass), linearly convertible. Requires a declared `MASS → MASS` unit conversion in the composition layer, because the two registries disagree on the base unit. |
| Morris → Morris between any two balance systems sharing a `QuantityKind` | Same basis; provenance passes through untouched. |

### 6.2 Illegal, with the reason

| Attempted edge | Rejected because | Criterion |
|---|---|---|
| `g` ↔ `kg/h` | mass vs mass **flow** — a quantity change, not a unit change | CG-03 |
| `kg` ↔ `kg/h` | same, with identical-looking symbols | CG-03 |
| `AU` ↔ anything in Morris | absorbance has no counterpart; the paper calibrated the spectrophotometer with water, so no `AU → g/mol/IU` conversion exists | CG-09 |
| `mL`/`L` ↔ anything in Morris | Morris has no volume dimension; volume is not a balance quantity in Chapter 4 | CG-02 |
| `M`/`mM` ↔ Morris `mol`/`mol/h` | molarity is a *concentration*; an amount needs a volume that Morris does not carry | CG-02 |
| Morris mass fraction `1` ↔ Zieliński dimensionless `1`/`OD600` | same symbol, incompatible semantic quantity (`%` collision of §3.1 generalises to all of `1`) | CG-02 |
| Zieliński stream kind ↔ Morris `Component` | no component identity exists in the Zieliński model | CG-08 |
| Any Morris balance across a Zieliński stage | reaction terms absent; Morris is non-reacting by construction | CG-09 |
| Zieliński `induction_time` (unknown) → any required input | unknown must not become zero or a fabricated number | CG-07 |

### 6.3 The headline finding

> **Of the 20 Zieliński equation bindings, not one output can legally enter a
> Morris control volume.** Every candidate is blocked by one of exactly three
> independent causes: no component identity (§4.1), a reactive boundary
> (§4.2), or a mass-vs-mass-flow quantity change (§4.3).

This is not a defect in either model. It is the correct scientific reading, and
it is the finding that has to drive the example graph: **the runnable example
must not pretend the two models fuse.** It runs both, it demonstrates the
downstream data transfer with two instances of the material-balance engine (the
only place where a lawful cross-boundary transfer exists), and it ships the
tempting cross-model edges as *rejected*, each with its named reason.

---

## 7. Baseline test results (captured before any composition code)

```
Models/Zielinski:  223 passed in 1.81s
Models/Morris:     186 passed in 0.22s
                   ---
existing total:    409
```

These figures are the reference for CG-15. They must be identical after the
composition layer is added, because **no file under `Models/` is modified by
this work**. The composition package is import-only: it adds `Models/Zielinski`
and `Models/Morris` to `sys.path` and imports them; it never writes to them.

---

## 8. Missing information the audit could not resolve

Recorded so they are not silently guessed later.

1. **Inclusion-body composition.** The paper reports 58 g of inclusion bodies
   and 224 g of wet biomass but never states what fraction of either is water,
   protein, lipid or nucleic acid. Without it, `wet_biomass → inclusion bodies`
   is a separation with an unreported yield and an unreported liquid phase, so
   the balance has neither a closed component set nor a closed total.
2. **Dissolution buffer volume** (`MP_DISSOLUTION_VOLUME`): 17.9 g of inclusion
   bodies dissolve in an unstated volume; the paper reports 5460 AU with no
   concentration. So even the AU-per-mL is an unknown in the source model.
3. **Lysis supernatant.** `N03`/`N04` produce an inclusion-body pellet *and* an
   aqueous fraction. The aqueous stream is not modelled at all, so material
   leaving the control volume is unaccounted for by construction.
4. **Per-stage recoveries.** Deliberately not modelled (`recovery.stage_yield`);
   an AU ratio across stages is not a recovery because the AU basis differs
   between stages (total protein at 280 nm vs the insulin-containing fraction).
5. **Batch duration as a point value.** Only ranges are available, and
   Zieliński refuses to collapse them. Even if collapsed, a batch-average rate
   would not be a steady-state one.

## 9. Assumptions this audit makes about the existing models

| id | Assumption | Basis |
|---|---|---|
| AUD-1 | Both models are importable without side effects and without network/filesystem access. | verified by execution (§2.1, §3) |
| AUD-2 | Both are deterministic: same inputs → bit-identical outputs. | Morris README ("no convergence tolerance to tune: the same system always produces bit-identical results"); Zieliński engine walks a fixed topological order with pure functions |
| AUD-3 | The 223 / 186 counts are the complete suites. | `pytest tests` from each package root |
| AUD-4 | Neither model will be modified. | task constraint; enforced by re-running both suites unchanged |

## 10. Environment

* Python 3.14.7, pytest 9.1.1
* Godot 4.7.2-stable (Windows x64), found at
  `D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe`
* Godot project root is the repository root (`project.godot`, `config/features = "4.7"`)

---

*Next: [`COMPOSITION_SPEC.md`](COMPOSITION_SPEC.md) — the versioned contracts and the
rules this audit forces.*