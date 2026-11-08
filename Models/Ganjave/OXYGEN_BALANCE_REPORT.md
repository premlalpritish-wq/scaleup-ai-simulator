# OXYGEN_BALANCE_REPORT — equations (11) and (15) of Ganjave et al. (2022)

**Decision: CORRECTED WITH EVIDENCE.**

The dissolved-oxygen equations as implemented did not represent the paper's
model. The paper is internally consistent and dimensionally correct; this
package's transcription of eq. (11) and eq. (15) was wrong. The error is
corrected, the evidence is below, and the corrected equation is the only one the
package computes.

Nothing in this report is a claim that the model reproduces the paper. It is not
claimed, and §9 explains precisely what stands in the way.

---

## 1. Claim under investigation

Simulated dissolved oxygen remained near 100 % for the whole cultivation, while
the paper describes dissolved oxygen falling towards zero. Two explanations were
on the table and neither was assumed:

- **H1 — the paper contains a typographical or dimensional error**, and the
  implementation faithfully reproduced it.
- **H2 — the implementation mis-transcribed the paper.**

The evidence below supports H2 and refutes H1.

---

## 2. What the paper prints, verified from the page

Both equations are on printed page 4. They were read from a 9× rendering of the
PDF page, because — as §3 shows — the PDF's text layer cannot be trusted on this
point.

**eq. (11), batch:**

```
        d(DO)
        ----- = k_La (100 - DO) - (100 / C*) · (mu1/Y_o1 + mu2/Y_o2) · X
          dt
```

**eq. (15), fed-batch:**

```
        d(DO)
        ----- = k_La (100 - DO) - (DO)F/V - (100 / C*) · (mu1/Y_o1 + mu2/Y_o2) · X
          dt
```

The factor is a **quotient**: `100` sits above a fraction bar, `C*` below it.

| Item | As printed | Where |
|---|---|---|
| Oxygen transfer, gas → liquid | `k_La · (100 - DO)` | eq. (11), (15), p. 4 |
| Oxygen uptake, combination 1 | `mu1/Y_o1` | eq. (11), (15), p. 4 |
| Oxygen uptake, combination 2 | `mu2/Y_o2` | eq. (11), (15), p. 4 |
| DO ↔ concentration | `DO` is a *percentage* of the probe's saturation reading | Notations, p. 2 |
| `C*` | "Maximum solubility of oxygen in media (0.0075 g·l⁻¹)" | Notations, p. 2 |
| `Y_o1`, `Y_o2` | 0.925, 1.219 — "g of biomass/g of oxygen" | Table 2, p. 4 |
| `k_La` | 133 h⁻¹, gassing-out/in for the 500 mL baffled flask at 200 rpm | p. 3 |
| `K_o,1`, `K_o,2` | 0.326, 8.944 — both in `%` | Table 2, p. 4 |

Supporting definitions, also read from a rendering: the Notations table
(p. 2) prints `DO — Percentage of dissolved oxygen at time t`, and Table 2
(p. 4) prints the second initial enzyme ratio as `e20/e^m₁` (that is TN-02,
still unresolved).

---

## 3. Why this was missed, and why text extraction cannot settle it

The PDF's text layer renders eq. (11) as

```
d(DO)   100(?    ?   )
 dt = k        C*      Yo1   Yo2        X        (11)
```

There is **no solidus and no fraction bar** between the `100` and the `C*`. A
transcription taken from the extracted text reads `100C*` — a product. That is
precisely the reading this package carried, and the test
`test_the_text_layer_is_the_trap_it_was` now asserts the trap is still there, so
that a future reader knows the text layer cannot be used on this point.

The glyph geometry *can* settle it, and `models/paper_equations.py` measures it:

| Pair | Tokens | Vertical offset | Reading |
|---|---|---:|---|
| `100` vs `C*`, eq. (11) | numerator, denominator | **8.34 pt** | stacked — a quotient |
| `100` vs `C*`, eq. (15) | numerator, denominator | **8.34 pt** | stacked — a quotient |
| `Y_o1` vs `Y_o2`, eq. (11) | control pair, same line | **0.00 pt** | same baseline |

The control pair is what makes this rigorous: tokens printed side by side in
that equation agree to under a hundredth of a point, so an 8.34 pt separation
cannot be an artefact of how words are boxed.

---

## 4. Dimensional analysis, term by term

Implemented as executable unit algebra in `models/dimensions.py`, base system
M (mass), L (length), T (time) plus a `PERCENT` pseudo-dimension so that
"percentage of the saturation reading" and "dimensionless number" stay
distinguishable.

One declaration first: a yield printed as `g of biomass/g of oxygen` is a ratio
of one mass to another, so `[Y_o] = M·M⁻¹ = 1`, i.e. **dimensionless**. That is
why `mu_k/Y_ok` converts a *biomass*-specific rate into an *oxygen*-specific
rate. The identity of the two masses comes from Table 2's unit labels.

| Term | Printed as | Dimension |
|---|---|---|
| Oxygen transfer | `k_La·(100 - DO)` | `T⁻¹ %⁺¹` |
| Specific oxygen uptake, combination 1 | `mu1/Y_o1` | `T⁻¹` |
| Specific oxygen uptake, combination 2 | `mu2/Y_o2` | `T⁻¹` |
| Volumetric oxygen uptake rate `OUR` | `(mu1/Y_o1 + mu2/Y_o2)·X` | `M¹ L⁻³ T⁻¹` |
| Printed factor | `100 / C*` | `M⁻¹ L³ %⁺¹` |
| **Oxygen consumption, as printed** | `(100/C*)·OUR` | **`T⁻¹ %⁺¹`** |
| Fed-batch dilution | `(DO)·F/V` | `T⁻¹ %⁻¹·… = T⁻¹ %⁺¹` |
| **Required: `d(DO)/dt`** | — | **`T⁻¹ %⁺¹`** |
| Consumption under the product reading | `(100·C*)·OUR` | `M² L⁻⁶ T⁻¹` ✗ |

All three terms of eq. (11) — and all four of eq. (15) — are in `T⁻¹ %⁺¹` as
printed. Under the product reading the consumption term is in `M² L⁻⁶ T⁻¹` and
**cannot be added to the transfer term at all**. `Dimension.__add__` refuses
the unlike sum with an exception rather than returning a number.

**Three consistency checks, all satisfied by the printed form:**

1. **The transfer term is already the percentage form of the standard balance.**
   `k_La·(100 - DO%)` is exactly `100·k_La·(1 - DO_conc/C*)`, i.e. the
   concentration-form `k_La·(C* - DO_conc)` divided by `C*` and scaled by 100.
   The consumption term printed beside it must therefore carry that same
   `100/C*`, or the equation mixes conventions. `test_the_transfer_term_alone_
   survives_the_same_conversion` checks the identity numerically.
2. **The whole balance converts consistently.** Writing eq. (11) in g/L gives
   `dDO_conc/dt = k_La·(C* - DO_conc) - OUR`; multiplying *that* by `100/C*`
   reproduces the implemented percentage balance exactly, both terms.
   `test_the_balance_in_percentage_is_the_balance_in_concentration` asserts it.
3. **The DO representation is consistent.** `DO` is a percentage throughout:
   `K_o,1 = 0.326 %` and `K_o,2 = 8.944 %` are percentages, and `DO/(K_o,k+DO)`
   is a ratio of like quantities. `100 %` corresponds to `C* = 0.0075 g/L`
   through an explicit, tested conversion — never implicitly.

**Ambiguities the paper does not resolve, and how they were handled:**

- The paper never states the *units of the DO state variable* numerically, only
  "percentage". Handled by carrying `%` throughout and converting only through
  `schemas.units.do_percentage_to_concentration`.
- `C*` is reported without temperature, medium composition or measurement
  uncertainty. Used as printed; flagged in `MODEL_REPORT.md` §7.
- Whether the `100` in `100/C*` is "per cent" or a bare numeric factor. The
  dimensional analysis requires it to be the per-cent scaling (otherwise the term
  does not reach `%/h`), so that is the reading taken; it is stated in
  `models/dimensions.py`.

---

## 5. Competing interpretations compared

| | **A — printed quotient** | **B — product (what was implemented)** |
|---|---|---|
| Expression | `k_La(100-DO) - (100/C*)(mu1/Yo1+mu2/Yo2)X` | `k_La(100-DO) - (100·C*)(mu1/Yo1+mu2/Yo2)X` |
| Dimensional basis | both terms `%/h`; the equation is well formed | consumption term `M²L⁻⁶T⁻¹`; not addable to `%/h` |
| Supported by | the rendered page (fraction bar), the glyph geometry, the unit algebra, the internal consistency of the transfer term | a text-layer rendering that drops the fraction bar |
| Inferred | that the `100` is per-cent scaling (required dimensionally) | nothing — it is a misreading, not an interpretation |
| Transfer at the reference state | 6650 %/h | 6650 %/h |
| Consumption at the reference state | 11 139.4 %/h | 0.6266 %/h |
| Ratio | consumption ≈ 1.68 × transfer → DO **falls** | consumption ≈ 9.4e-5 × transfer → DO pinned |
| DO reachable at all | yes, down to ~0 % | no; ≥ 99.87 % for every `S2_0` tried |

Reference state: `X = 2 g/L`, `S1 = 4 g/L`, `S2 = 10 g/L`, `DO = 50 %`,
`e1 = 0.30`, `e2 = 0.60`, with the Table 2 parameters. The oxygen uptake rate at
that state is `OUR = 0.83545 g O₂·L⁻¹·h⁻¹`, giving `d(DO)/dt = -4489.4 %/h`
as corrected and `+6649.4 %/h` as it was before. All figures are computed in
`test_oxygen_balance.py` from the printed values.

**The interpretation was not chosen because it improves the result.** It was
chosen on §3 and §4 alone. §7 reports what the choice implies for agreement with
the paper as a *consequence*, and explicitly not as a reason.

---

## 6. What was changed

| File | Change |
|---|---|
| `models/batch.py` | `oxygen_consumption_term` now computes `(100.0 / c_star) * uptake * X`; raises on non-positive `C*`; module and function docstrings quote the printed equation |
| `models/fed_batch.py` | documentation only; it already called `batch.oxygen_consumption_term` |
| `models/kinetics.py` | TN-04 rewritten: it now records a **transcription error made here**, with the three lines of evidence, and is no longer `unresolved` |
| `models/dimensions.py` | **new** — the unit algebra of §4, with `Dimension.__add__` refusing unlike dimensions |
| `models/paper_equations.py` | **new** — locates the article PDF structurally and measures the printed equations' glyph geometry |
| `schemas/parameters.py` | `EQUATIONS_VERSION` 1.0.0 → 1.1.0, with an `EQUATION_CHANGES` log |
| `data/reference_parameters.json` | `equations_version` field follows; **no parameter value touched** |
| `tests/test_oxygen_balance.py` | **new** — GJ-O2-01…08 |
| `tests/test_batch.py`, `tests/test_fed_batch.py`, `tests/test_kinetics.py`, `tests/test_acceptance.py` | expectations updated to the printed quotient; one new test caught a stale inline equation in `fed_batch.dDO_dt`'s docstring |
| `README.md`, `MODEL_REPORT.md` | updated to match |

The production equation was not given a switch: there is one reading, and it is
the printed one. The transposed reading survives only in `models/dimensions.py`,
which exists to show it fails.

---

## 7. Baseline versus corrected

Identical inputs, parameters, solver settings and output times. Inputs:
`X₀ = 0.05 g/L`, `S2₀ = 5 g/L`, `DO₀ = 100 %`, `S1₀ = 2.76 g/L`,
`V₀ = 0.1 L`, `e1₀ = 0.082`, `e2₀ = 0.874`; feed 17.5 % w/v glycerol,
24.5 % w/v yeast extract, 0.72 mL/h from 6 h (the paper's selected recipe);
solver RK4(3), `rtol = 1e-6`, `atol = 1e-9`, `h_max = 0.01 h`.

### 7.1 24 h fed-batch

| Quantity | Baseline (`100·C*`) | Corrected (`100/C*`) |
|---|---|---|
| run status | ok | ok |
| initial DO | 100.00 % | 100.00 % |
| final DO | 99.993 % | 67.108 % |
| minimum DO | 99.992 % | 59.546 % |
| maximum DO | 100.000 % | 100.000 % |
| initial / final biomass | 0.0500 / 8.3514 g/L | 0.0500 / **8.3551** g/L |
| final glycerol / complex substrate | 22.320 / 0.0789 g/L | 22.305 / 0.0823 g/L |
| final volume | 0.11296 L | 0.11296 L |
| steps accepted / rejected | 2442 / 16 | 2447 / 20 |
| integration failures | none | none |
| warnings | TN-02, TN-04 | TN-02 |
| input digest | `17367e5452f97306…` | `b9cf220e45ec1c36…` |

DO at the sampled times — baseline: 100.00, 100.00, 100.00, 100.00, 99.99,
99.99, 99.99 %. Corrected: **100.00, 90.91, 72.82, 86.52, 63.87, 65.71,
67.11 %**.

The digests differ, as they must: `EQUATIONS_VERSION` is part of the digest, so
a run under the two readings cannot be confused.

**Regression.** Biomass moves by 0.04 % and glycerol by 0.07 %; the volume is
unchanged to ten digits. `test_oxygen_balance.py::TestRegression` pins the
pre-correction `growth_terms` and the batch derivative components to their exact
`repr` values and asserts that only component 3 — the oxygen term — moved.

### 7.2 Against the paper's description

The paper states (p. 3) that DO showed *"a continuous decrease … for the first
6 h, followed by a sharp rise concomitant with the depletion of glycerol. This
landmark in the DO profile was considered as the starting point for feeding"*,
and that *"upon feeding, the DO levels decreased gradually and remained close to
zero"*; and (p. 7) that *"growth is limited by oxygen availability beyond 6 h"*.

| Paper's statement | Baseline | Corrected |
|---|---|---|
| continuous DO decrease over the first 6 h | ✗ flat at 100 % | ✓ 100 → 90.9 → 72.8 % |
| sharp rise at substrate depletion | ✗ no rise | ✓ 72.8 → 86.5 % by 6 h |
| DO close to zero once feeding | ✗ ≥ 99.99 % | ✗ 59.5 % minimum — **not matched** |
| growth oxygen-limited beyond 6 h | ✗ never oxygen-limited | reachable, but substrate-limited in this run |

The corrected equation reproduces the *shape* of the landmark. It does not
reproduce the *magnitude* of "close to zero", and §9 explains why without
excusing it.

### 7.3 Was the reported regime reachable at all?

Sweeping the one initial condition that decides it (`S2_0`, which the paper does
not state), 24 h fed-batch, everything else identical:

| `S2_0` (g/L) | min DO, corrected (%) | final X, corrected (g/L) | min DO, baseline (%) | final X, baseline (g/L) |
|---:|---:|---:|---:|---:|
| 5 | 59.55 | 8.36 | 99.99 | 8.35 |
| 10 | 22.99 | 9.64 | 99.99 | 9.61 |
| 20 | 1.18 | 15.84 | 99.99 | 12.41 |
| 40 | 0.56 | 21.10 | 99.97 | 16.99 |
| 80 | 0.50 | 21.44 | 99.93 | 26.13 |
| 150 | 0.49 | 21.62 | 99.87 | 42.10 |

Under the transposed reading, DO never leaves the 99.87–100 % band at *any*
initial condition, so the regime the paper describes is structurally
unreachable. Under the printed quotient it is reached for `S2_0 ≥ 20 g/L`, and
biomass settles at 21.1–21.6 g/L for `S2_0 ≥ 40 g/L` — inside the paper's
reported range of 19.9–21.5 g DCW/L.

**This is corroboration, not validation.** `S2_0` was chosen during this
investigation, the paper does not print it, no time-course data was digitised,
and no measured point was fitted. It shows only that the corrected equation can
express the paper's regime and the transposed reading cannot.

---

## 8. Tests

`tests/test_oxygen_balance.py`, 66 tests, all passing, none skipped.

| ID | Requirement | Tests |
|---|---|---|
| GJ-O2-01 | source transcription | 10 (5 of them re-measure the PDF) |
| GJ-O2-02 | dimensional consistency | 10 |
| GJ-O2-03 | oxygen transfer | 10 |
| GJ-O2-04 | oxygen consumption, per combination | 10 |
| GJ-O2-05 | percentage ↔ concentration via `C*` | 7 |
| GJ-O2-06 | batch/fed-batch convention | 5 |
| GJ-O2-07 | regression | 8 |
| GJ-O2-08 | uncertainty preservation | 6 |
| | **total** | **66** |

No expected value is taken from the implementation under test: every quantity is
either arithmetic on the printed Table 2 numbers, a measurement of the PDF's
glyph geometry, or a value recorded from the pre-correction build and labelled
as such.

**Mutation check.** Reverting `100/C*` to `100·C*` in a scratch copy makes **11**
of these fail — GJ-O2-01 (`test_the_printed_factor_is_a_quotient`,
`test_the_transposed_factor_is_not_what_is_implemented`), GJ-O2-04 (6 tests),
GJ-O2-05 (`test_the_balance_in_percentage_is_the_balance_in_concentration`),
GJ-O2-07 (`test_only_the_oxygen_term_moved`) and GJ-O2-08
(`test_the_superseded_reading_is_not_implemented_in_production_code`).

The full suite is **287 passed, 0 skipped**; the five PDF-backed tests executed
rather than skipping, because both the article PDF and PyMuPDF are present.

---

## 9. What remains unresolved

1. **TN-02.** Table 2 prints `e20/e^m₁` where `e₂(0)/e_m₂` is meant. Confirmed
   against a rendering of the table, so it is the paper's typo rather than an
   extraction artefact. Read as the latter; the value 0.874 is used either way.
   Reported on every run. Needs the authors.
2. **No paper reproduction.** Validation level 3 is not met and cannot be with
   this paper: the time courses are figures, no numerical observations were
   recoverable, and nothing was digitised.
3. **`X₀`, `DO₀`, `S2₀` remain caller-supplied.** No OD600→DCW calibration is
   printed, so `X₀` cannot be derived from the reported OD600 of 0.05. `S2₀` in
   particular decides whether the culture is oxygen- or substrate-limited, as
   §7.3 shows.
4. **The DO-convention uncertainty is inherited.** `C*` is a single reported
   value, 0.0075 g/L, with no stated uncertainty and no temperature or depth
   correction. The equation is now correct in form; its accuracy is bounded by
   that number, not by the transcription.
5. **One reading, no switch.** The package computes the printed equation only.
   If a future decision reverses this — on the authors' say-so, say — the change
   would be a new `EQUATIONS_VERSION` with the same evidence recorded again, not
   a runtime toggle.

---

## 10. Files changed, and what was not touched

Changed, all inside `Models/Ganjave/`: `models/batch.py`,
`models/fed_batch.py`, `models/kinetics.py`, `models/dimensions.py` (new),
`models/paper_equations.py` (new), `schemas/parameters.py`,
`data/reference_parameters.json`, `tests/test_oxygen_balance.py` (new),
`tests/test_batch.py`, `tests/test_fed_batch.py`, `tests/test_kinetics.py`,
`tests/test_acceptance.py`, `README.md`, `MODEL_REPORT.md`, this file.

**Not modified:** `Models/Morris`, `Models/Zielinski`, `Models/Baez`,
`composition/`, the composition registry, and the Godot UI. Verified by
SHA-256 over 151 files in those four trees, recorded before this investigation
began and compared after: 0 added, 0 removed, 0 changed. Their suites pass
unchanged: Morris 186, Zieliński 223, composition 270.

**Not done, by instruction:** no optimisation algorithm, no protein dynamics,
no registry change, no solver rewrite, and no figure digitisation — the one
figure-adjacent question (the DO axis of Figs. 2/3/5) was not needed, because
the rendering and the unit algebra settled the transcription without it.