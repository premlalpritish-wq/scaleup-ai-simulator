# Model report

What the ScaleUp AI material balance engine v0.1 does, what it deliberately does
not do, and what was found in the source text while building it.

Source: Morris, J. H., Geiger, J. L. & Fine, J. A., *Introduction to Chemical
Engineering: Materials, Energy, and Balance*, 4th ed., Wiley, 2011, Chapter 4,
"Fundamentals of Material Balances in Non-Reacting Systems" (printed pp. 144–240).

---

## 1. Scope

The engine solves **linear, non-reacting mass balances around one control
volume**, at steady state, with accumulation, or batchwise.

It generates, for each declared component *i*:

- steady state — `Σ(inflow of i) − Σ(outflow of i) = 0`
- accumulating — the same, with the retained material on the outflow side
- batch — `final − initial − added + removed = 0`

plus one `Σ(mass fractions) = 1` per stream carrying a mass-fraction composition,
plus any caller-supplied constraint, all solved together in one linear system
with a deterministic solver.

### Non-goals

| Not implemented | Why |
|---|---|
| Reaction kinetics, stoichiometry | Chapter 4 is explicitly the non-reacting half; reactions are Chapter 5 |
| Empirical or fitted models | A fitted correlation is not a conservation law and cannot be checked by one |
| Reconciling inconsistent measurements | §4.7: deciding which reading to distrust needs instrument history the engine does not have |
| Energy balances | Chapter 7 |
| Predictive validation | Conservation-law tests show internal consistency only |

---

## 2. Findings in the source text

Three places where the printed text does not agree with itself. The engine
reports each rather than quietly choosing a side.

### 2.1 Example 4.2 states two different copper charges

Page 153: "3600 kg of pure zinc, **14 000 kg** of pure copper, and 8500 kg of
recycled brass".

Figure 4.11 and the worked arithmetic on the same page: "Copper **14 500 kg**",
`m_D = 26 600 kg`, and `14 500 + 0.79(8500) = (26 600)(w_DCu)`.

Only 14 500 kg is consistent: `3600 + 14500 + 8500 = 26600`, whereas the prose
figure gives 26 100. The test fixture uses 14 500 kg, with a note on the
quantity.

### 2.2 Table 4.1 does not close in the direction the prose describes

Page 157: "A cursory check of the data shows that the results do not conform to
the principle of conservation of mass. For example, **less mass comes out than
enters**, and more slag exits than enters."

Inputs are S1 salt cake 415, S2 leach solution 1260, S3 ambient air 335 →
**2010 kg/min**. Outputs are S4 wet air 348, S5 salty solution 1435, S6 slurry
liquid 98, S7 slurry slag 141 → **2022 kg/min**.

So as printed the table has outputs exceeding inputs by 12 kg/min, the opposite
of the prose. The companion claim does hold: slag enters at `415 × 0.325 = 134.9`
and leaves at `141 × 1.00 = 141.0` kg/min.

`test_salt_cake_analysis_based_balance_does_not_close` pins the engine to the
table's own arithmetic and classifies the system `INCONSISTENT`, which is the
chapter's point about analysis-based balances (§4.6.3): "an analysis-based
material balance almost never shows mass conservation."

### 2.3 The salt cake `SV = 14` is not derivable from the rule stated beside it

Section 4.7.2 defines stream variables as "the sum of the number of components
over all streams", giving the example "three streams, each of which had three
components, `SV` would equal 9".

Applied to Table 4.2 — seven streams, four components (NaCl, slag, H₂O, air) —
that rule gives **28**, not the printed **14**. The same rule *does* reproduce
the other two worked figures in the chapter: 12 for the spent-gas splitter
(Example 4.15, three four-component streams) and 8 for Still I of the two-stage
distillation (Table 4.6, "two of which have three components, and one of which has
two").

The printed salt cake DOF of **+1** therefore rests on an SV this implementation
cannot reconstruct. `models/degrees_of_freedom.py` reproduces the book's counts
verbatim as `SALTCAKE_PROCESS` for regression purposes and says so in its note,
but `dof` is reported **only alongside** `n_unknowns − rank(A)`. This is not a
stylistic preference: it is the failure mode §4.7 names — "it is easy to
inadvertently write one or more non-independent equations, which creates the
impression that a sufficient number of independent equations have been written."

---

## 3. Design decisions

### 3.1 `ACCUMULATING` is a third mode

The brief asked for steady-state and batch balances. The chapter's §4.4 general
equation is `input − output = accumulation`, and Example 4.3 (`m_A = m_B + 2240`)
is an accumulating process, not a batch one — bullion and lead flow
continuously while the condensate is retained. Representing it as batch would
have been wrong, so the mode is explicit rather than folded into either.

It is never inferred: a stream's direction must be legal for the declared mode,
so an accumulating system cannot be solved by accident as a steady-state one.

### 3.2 Example 4.3 is stated per cycle, in kilograms

The book's own equations are `m_A = m_B + 2240` and
`0.0055 m_A = 0.0003 m_B + 0.948 × 2240`. A 2240 kg accumulation is not
commensurable with a rate. The fixture therefore states the whole balance as
masses over one panel cycle, and `BalanceSystem` refuses a system whose crossing
streams mix a flow with an inventory.

### 3.3 Balances are selectable

Section 4.7.2 allows "the total mass plus the number of components − 1" in place
of one balance per component, and Example 4.3 states that a lead balance "won't
help because it provides no useful information". `balances=` and
`total_balance=` make that choice explicit rather than implicit. The lead balance
is still *checked* after the solve — only its equation is not generated.

### 3.4 Bilinear terms are refused, not approximated

A component's flow in a stream described by a total and a composition is
`total × fraction`. When both are unknown this is a product of two unknowns, and
no linear balance can contain it. Such a balance is not generated; a diagnostic
names the stream and the two unknowns. Severity is `ERROR` when the balance was
requested explicitly via `balances=` and `WARNING` when it was incidental.

### 3.5 Internal streams cancel

A `BalanceSystem` is one control volume. An `INTERNAL` stream enters and leaves,
so it cancels from every balance and its unknowns are not solved — reported as
such rather than dropped. Balancing around each device means declaring one
`BalanceSystem` per device, per §4.9.

### 3.6 Constraints relate stream variables; they do not introduce them

A user constraint may reference variables the streams declare — that is how a
split fraction (§4.7.2's subsidiary relation) is written. It may not name a
variable no stream declares, because that unknown would have no unit, no kind and
no provenance.

### 3.7 Residuals are reported in the normalised basis unit

Arithmetic runs in each kind's base unit (`kg`, `kg/h`, `mol`, `mol/h`). A system
declared in `kg/min` reports residuals in `kg/h`, with `basis_unit` stated on
every residual and `convert(..., "kg/h", "kg/min")` available to recover the
declared unit. This is why the salt cake residual is −0.2 kg/h, which is the
table's −12 kg/min.

### 3.8 A component a stream does not carry contributes a declared zero

Section 4.6.3's salt cake streams show the shape of this: stream 7 is pure slag,
so its `w_NaCl` is genuinely zero. A component's balance is written over *every*
crossing stream, and a stream that does not carry that component contributes a
known zero to it — not an unknown.

The residual reports that zero explicitly rather than dropping the stream from
the ledger, so a reader can see that a zero was *decided* rather than overlooked.
The distinction that matters is between a stream that **does not mention** the
component (a declared zero) and one that **mentions it but could not resolve**
it (genuinely unknown, so the balance cannot be evaluated and no residual is
reported for that component).

`tests/test_acceptance_criteria.py` pins this: a component absent from a stream
still has its balance checked, and the check closes.

### 3.9 A total balance is refused over partially-declared streams

`total_balance=True` sums one declared total per crossing stream. A stream given
as component amounts has no declared total — its total is a *consequence* of its
component flows, not an independent variable. Emitting the equation over only
the streams that do declare one would produce something that reads as a system
wide balance while silently omitting the others; on the Example 4.1 data it
produced an equation that could not close.

It is now refused, with the offending stream ids named. Declare those streams by
total plus composition if a total balance is genuinely required.

---

## 4. What the result contract contains

`BalanceResult.to_dict()` returns: solved variables (with unit, kind, method and
the equations each entered), unresolved variables **with reasons** and never with
substitute values, all generated equations with their expressions and constants,
unknown/equation/rank counts, the DOF comparison when supplied, component
residuals, the total mass residual, per-equation residuals, the ledger,
independent/redundant/inconsistent equation ids, diagnostics, and assumptions.

### 4.1 Acceptance criteria MB-01 … MB-12

`tests/test_acceptance_criteria.py` implements all twelve, one class per
criterion, with an `MB_COVERAGE` table the suite checks for completeness so the
table cannot drift from the code. All twelve pass.

MB-04 initially **failed**, and exposed two real defects rather than a missing
test. Both are now fixed and pinned (§3.8, §3.9). MB-05 exposed a third gap:
the suite proved the *equations* were not renormalized but nothing proved the
*reported ledger* was not either, and a mutation that normalized the ledger
survived until that assertion was added.

---

## 5. Known limitations

1. **Element balances are not implemented.** Only component balances are
   generated. `Component` carries a molar mass, but nothing decomposes a species
   into elements, so a species-to-element balance would need to be supplied as a
   user constraint.
2. **Mass ↔ amount conversion is not automatic.** `BalanceBasis` must match the
   streams' kinds. The molar mass is carried for reporting but is never used to
   convert silently.
3. **Rank is tolerance-based**, via Gauss-Jordan with partial pivoting and a
   relative tolerance, not SVD. Ill-conditioned systems can be ranked
   optimistically; `rank_tolerance` is exposed on `BalanceSystem`.
4. **The least-squares path uses modified Gram-Schmidt without column
   pivoting.** It runs only to locate inconsistent data, never to produce an
   answer, so its conditioning matters little — but it should not be reused as a
   general solver.
5. **Residuals are hard tolerances, not uncertainty bounds.** A residual within
   tolerance says the numbers are *consistent*; it says nothing about whether a
   measurement error is *acceptable*. No uncertainty propagation is implemented.
   Do not read `balances_close` as a statistical claim.
6. **One control volume per `BalanceSystem`.** Recycle, bypass and multi-device
   topologies (§4.10–4.12) are out of scope; model each device separately.