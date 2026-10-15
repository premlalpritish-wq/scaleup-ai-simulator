# Composition Specification

**Contract version:** `0.1.0`
**Status:** implemented and tested
**Authoritative companion to:** [`COMPOSITION_AUDIT.md`](COMPOSITION_AUDIT.md)

This document is the specification of the composition layer. Where the audit
records *what is true about the two models*, this document states *what the
composition layer does about it*. Every rule here is enforced in code and pinned
by a test in `tests/test_acceptance.py`.

---

## 1. Scope

The composition layer is the only thing that may connect two scientific models.
It is not a scientific model and it does not contain a scientific equation.

It provides:

1. a typed description of what a model offers and asks for;
2. a directed acyclic graph of model instances;
3. a connection check that refuses incompatible links *before* anything runs;
4. a deterministic topological execution order;
5. a value-passing mechanism that preserves provenance across every hop;
6. a structured result that reports residuals, warnings and errors.

It explicitly does **not**:

* convert a mass into a mass flow rate;
* renormalise a composition that does not sum to one;
* infer a missing value from a neighbouring quantity;
* fit, reconcile or "repair" inconsistent measurements;
* claim a reactive balance where no reaction terms are represented;
* present a model-reported source discrepancy as a composition failure.

---

## 2. The quantity taxonomy

A port's compatibility key is its **quantity**, never its unit symbol. The
taxonomy in `composition/quantities.py` is a single registry covering both
models, because the two existing registries barely overlap.

| Quantity | Morris | Zieliński | Notes |
|---|---|---|---|
| `mass` | `MASS` | `MASS` | the **only** shared quantity with values in both models |
| `mass_flow` | `MASS_FLOW` | — | Zieliński has no flow quantity at all |
| `mass_fraction` | `MASS_FRACTION` | — | |
| `amount` / `amount_flow` | yes | — | |
| `volume` / `volume_flow` | — | yes | not a balance quantity in Chapter 4 |
| `time` | — (carried in a flow's unit) | yes | |
| `absorbance` | — | yes | instrument-relative; no mass conversion exists |
| `dimensionless` | — | yes | **not** Morris's `1` |
| `molar_concentration`, `activity`, `ph`, … | — | yes | |

### 2.1 The `%` collision

`%` is registered in both source models with the *same conversion factor* and
*incompatible meanings*:

* Morris: `%` **is** a mass fraction and enters `Σw = 1`;
* Zieliński: `%` is a generic percent (40 % glucose, 16 % NH₄OH).

Units are therefore keyed by the pair `(quantity, symbol)`. A symbol-only
lookup does not exist in the registry: there is no code path by which `%` on one
side of a connection could be read as `%` on the other.

### 2.2 Base units differ for the one shared quantity

Mass is the one quantity both registries implement, and their base units differ
(`kg` in Morris, `g` in Zieliński). The composition registry declares the bridge
once, explicitly: `g → kg` is a factor of `1e-3` through the mass base unit.
Neither model performs this conversion itself; the composition layer does, and
records the factor in the value's `conversion` field.

---

## 3. The six value states

`ValueState` is the mechanism that keeps "absent" from becoming "zero". Both
source models enforce this structurally — Zieliński's `Quantity.__post_init__`
raises if an `unknown` quantity carries a value, and Morris makes `Unknown` a
separate type from `Quantity` precisely so a missing measurement cannot be
written as a measured zero. The composition layer reuses the same discipline.

| State | carries a number | meaning |
|---|---|---|
| `NUMBER` | yes | a measured or computed number |
| `ZERO` | yes | a number **stated** as zero |
| `RANGE` | no | reported as an interval; never collapsed |
| `NOT_REPORTED` | no | the model does not report this at all |
| `UNRESOLVED` | no | the model ran and could not determine it |
| `UNKNOWN` | no | declared unavailable in the source, with a reason |

`ZERO` is separate from `NUMBER` even though both hold `0.0`, because a stated
zero is evidence and a computed zero is not. `ModelValue.__post_init__`
enforces every combination, so a non-numeric state cannot be given a number and
a numeric state cannot lack one.

A value's `reason` field is mandatory in practice for the three "model was
silent" states: it is the gap, and it is what the results panel shows instead of
a number.

---

## 4. Ports

A `PortDefinition` states, per port:

| Field | Why it exists |
|---|---|
| `quantity` | the compatibility key |
| `unit` | resolved **as a unit of `quantity`**, never by symbol alone |
| `component` | which conserved entity, where one applies |
| `components` | every component present in the value |
| `temporal_basis` | `INVENTORY`, `RATE`, `INSTANT`, `TRAJECTORY_POINT`, `DURATION`, `NOT_APPLICABLE` |
| `required` | whether the model cannot run without it |
| `provenance_requirement` | `NONE`, `EXPLAINED`, or `CITED` |
| `attribution_required` | a control-volume total that must be attributable to named components |
| `solvable` | the model will determine this rather than read it |
| `unavailable_reason` | why the port cannot be represented |

A port with `unavailable_reason` set is still published — so the gap is visible
and countable — but it cannot be connected. The Zieliński specific growth rate
(`1/h`, which the model's own unit registry does not define) is the one such
port in the current model set.

---

## 5. Connection rules

A connection from output port `A` to input port `B` is accepted only if **all**
of the following hold. Each failure has its own diagnostic code.

| Rule | Code when violated |
|---|---|
| `A.direction` is `output`, `B.direction` is `input` | `connection.direction_invalid` |
| `A.quantity` **is** `B.quantity` | `connection.quantity_mismatch` |
| a linear conversion exists within that quantity | `connection.unit_not_convertible` |
| temporal bases agree, or differ only in a reported way | `connection.quantity_mismatch` |
| if either names a component, both name the same one | `connection.component_mismatch` |
| if the target names a component, the source names one too | `connection.component_unattributed` |
| if the target is an attributable total, the source carries a component identity | `connection.component_unattributed` |
| the target model's capability covers the boundary | `capability.unsupported` / `capability.reactive_balance_refused` |
| the source model authorises any conversion performed | `capability.conversion_model_absent` |
| no self-loop | `connection.self_loop` |
| at most one connection per input port | `connection.multiple_inputs` |

### 5.1 Quantity is not unit

`kg` and `kg/h` are rejected by `connection.quantity_mismatch`, not by a unit
check. A quantity change is not a unit change: converting `kg` to `kg/h` would
change what the number *is*, not how it is written. The only bridge would be an
operating interval, and no conversion model in either registry supplies one.

### 5.2 Component identity

Morris's central abstraction is a conserved entity that can carry an
independent balance. The Zieliński model publishes **no** component identity:
its `StreamKind` vocabulary names process roles, and no stream carries a
component amount or a mass fraction.

So:

* a port with no component identity cannot supply a port that names a component;
* a port with no component identity cannot supply an attributable total;
* two ports naming different components cannot be connected.

Both refusals are `connection.component_unattributed` or
`connection.component_mismatch`, and both name what to do instead.

### 5.3 Reactive boundaries

`morris2011.material_balance` declares `non_reacting_only: true` and
`reaction_terms: ()`. Its chapter is *"Fundamentals of Material Balances with
Applications to **Non-Reacting Systems**"* and `BalanceSystem` has no field in
which a reaction term could be declared.

Any connection that would draw a Morris control volume around a boundary the
source model does not represent as non-reacting is refused with
`capability.reactive_balance_refused`. The refusal is not a blanket ban on
Morris → Morris: brass mixing is non-reacting and runs.

---

## 6. Execution

### 6.1 Ordering

Kahn's algorithm. Ties are broken by canvas position (top-to-bottom, then
left-to-right), falling back to declaration order. The plan is deterministic:
the same graph always produces the same order.

A cycle is rejected with `order.cycle_detected`, naming the participating
instances, the cycle itself, and the connections that close it. v0.1 has no
iterative solve, so a recycle loop cannot be expressed.

### 6.2 Execution status is not diagnostic severity

A model that runs to completion and reports five *error-severity findings about
its own source* has not failed. The composition layer therefore separates:

* **execution status** — did the model produce a result?
* **diagnostic severity** — how serious is this remark?

`ModelDiagnostic.EXECUTION_FAILURE_CODES` is the set of codes that mean "the
model did not produce its result". Only those set an instance's status to
`FAILED`. Everything else — including error-severity source discrepancies — is
surfaced at its own severity without failing the run.

This is why the Zieliński instance in the example graph reports 5 errors and
`success_with_warnings` at the same time, and both facts are true.

### 6.3 Failure propagation

A `FAILED` instance publishes nothing. Any instance whose inputs depend on it
is not executed, and receives `execution.dependent_skipped` naming the
upstream instance. Running it anyway would present a result computed from
missing data.

### 6.4 Representatives are labelled

When Morris reports an under-determined system, it returns the canonical member
of a one-parameter family for its pivot variables and names its free variables.
The composition layer passes both through:

* free variables are published as `UNRESOLVED` with their reason;
* pivot variables are published with `extra.determination = "representative"`
  and a `method` note stating the family's dimension.

A representative is never presented as a determined value, and it is never
injected into a downstream model without the note travelling with it.

---

## 7. Provenance

Every value carries a `provenance_chain`: a tuple of `ProvenanceRecord` objects,
oldest first. A record states its `kind` (`source`, `transfer`, `derivation`,
`assumption`, `gap`), its `producer_model` and `producer_version`, where it was
produced, and — for a transfer — the connection id and the two ports.

Chaining is append-only. A value that crosses three connections carries four
records, and the first still names the model that originally produced the
number. The diagnostics view renders the whole chain.

---

## 8. Reproducibility

`CompositionResult.reproducibility` is a SHA-256 over the plan digest and every
numeric output in execution order, with values rendered by `repr` so that
`0.7000000000000001` and `0.7` hash differently. `ExecutionPlan.digest` covers
the graph, the model versions and the manifest versions.

Neither digest includes a timestamp, a path, a process id or a duration, so two
runs of the same inputs produce the same digest — and any changed number changes
it. `tests/test_acceptance.py` pins both directions.

---

## 9. The runner interface

`python -m composition.runner --graph <in> --result <out>`

| Exit code | Meaning |
|---|---|
| 0 | validated and executed |
| 1 | did not validate |
| 2 | validated, execution failed |
| 3 | input unusable |
| 4 | runner error |

A result file is written in every case except a catastrophic runner error. The
editor checks the exit code first and the file second; a disagreement between
them is reported as a failure.

---

## 10. Godot boundary

GDScript never evaluates a scientific expression. It:

1. renders ports from the model manifests;
2. records the user's connections;
3. serialises the graph document;
4. invokes the runner and checks its exit code;
5. reads and displays the result document.

The material-balance solver is not reimplemented in GDScript, and no quantity,
unit or residual is computed there.

---

## 11. Assumptions this layer makes

| id | Assumption | Basis |
|---|---|---|
| SPEC-1 | A connection is legal only when quantities match exactly. | audit §3, §4 |
| SPEC-2 | Mass is the only quantity with values in both models. | audit §6.1 |
| SPEC-3 | No conversion model exists for mass ↔ mass flow. | Morris README; Zieliński's ranges |
| SPEC-4 | Morris may not be drawn around a reactive boundary. | Chapter 4 title; `BalanceSystem` has no reaction field |
| SPEC-5 | A model-reported source discrepancy is not an execution failure. | Morris sec. 4.7; Zieliński's cross-check design |
| SPEC-6 | An under-determined pivot value is a labelled representative, never a determined one. | Morris sec. 4.7.2 |
| SPEC-7 | Both models are deterministic. | Morris README; Zieliński's fixed topological order |

## 12. Known limitations

1. **No iterative solve.** Cycles are refused. A recycle loop needs an
   iteration contract, which is out of scope for v0.1.
2. **No unit conversion is performed by the composition layer except within a
   single quantity.** A quantity change requires a declared conversion model on
   the source manifest, and neither model declares one.
3. **One value per input port.** Multiple connections into one port are
   refused rather than resolved.
4. **The Zieliński model publishes no component identity**, so no edge from it
   to a Morris control volume can be legal. This is a property of the source
   models, not a gap in the composition layer.
5. **Evidence replay is not prediction.** The Zieliński instance restates the
   paper's reported numbers. Predictive mode with no declared inputs resolves
   0 of 23 targets, which is the model's designed behaviour.
