# Ganjave Held-Out Failure Investigation

**Why the frozen held-out evaluation fails, and what the evidence does and does not
establish.**

**Conclusion (stated first):** the failure is **not** a defect in this implementation.
At both points where the prediction materially disagrees with the measurements, **the
paper's own plotted model curve disagrees in the same direction by a comparable amount**,
and at t ≈ 26 h the paper's curve has left the plot entirely. The most defensible
reading is that the **published equations, as parameterised by the authors, do not
reproduce this experiment**, and this implementation faithfully inherits that
disagreement while sitting about 0.9 g/L above the published curve.

No model equation, parameter or threshold was changed. `reproduction_status` remains
`not_yet_validated`.

---

## 1. Frozen baseline

Preserved before any diagnostic. All five inputs verified byte-identical to the digests
recorded by the evaluation:

| Input | SHA-256 | Status |
|---|---|---|
| `frozen_configuration.json` | `23c585ee06579ab7…` | unchanged |
| `observations.json` | `48141f2947428f3a…` | unchanged |
| `evaluation_protocol.json` | `d528e214e48becd9…` | unchanged |
| `figure_reference_data.json` | `46eb120f9553bdd6…` | unchanged |
| `reference_parameters.json` | `3f53c1fdc82449c2…` | unchanged |

Re-running reproduced every reported value exactly: RMSE **2.5204**, ratio **1.1401**,
min DO **0.4779 %**, **6/8** within 2σ, optimum endpoint **18.2993** g/L. Immutable copy:
`data/ganjave2022/investigation/baseline_primary_result.json`.

**Model under investigation:** `ganjave` 0.1.0, equations 1.1.0, Ganjave et al. (2022)
eq. (8)–(16), parameters Table 2 as printed (loaded as fitted, never refitted), RK4
`rtol` 1e-6 / `atol` 1e-9 / `h_max` 0.01 h, 27 h fed-batch, no connections.

```
python -m composition.runner --graph heldout_fig3.graph.json --result heldout_fig3.result.json
```

---

## 2. The residual pattern

Full detail in [`GANJAVE_RESIDUAL_ANALYSIS.md`](GANJAVE_RESIDUAL_ANALYSIS.md). In brief:
eight compared observations, RMSE 2.520 g/L, bias **+1.359** (predictions run high),
error growing with phase but produced by **two isolated excursions** — t = 12.006 h
(+2.43, 3.4σ) and t = 26.080 h (+6.47, 9.1σ) — which together carry 94 % of the squared
error. Six of eight residuals are inside 1.4 g/L.

---

## 3. The anomalous observation — resolved, and it refutes the earlier claim

The frozen protocol pre-declared t = 26.080 h a "probable digitisation artefact".
**That was wrong, and the point stays in.**

Colour verification against the source PDF (`composition/tools/verify_digitisation.py`)
found every one of the nine marks — including this one — sitting on `rgb(22, 0, 255)`,
the PDGF blue, at **zero** distance. Visual inspection
(`data/ganjave2022/investigation/fig3b_panel.png`) confirms a genuine marker on the
biomass axis, in the correct series.

The decisive evidence is what the paper's own curve does there: **it leaves the plot
through the top spine at t ≈ 25 h** (axis maximum 20 g/L). At t = 26.080 h the observed
value is 15.369 g/L, so the paper's own model over-predicts by **at least +4.63 g/L** —
more than 3σ — and the figure shows it. This implementation over-predicts by +6.47.

| Classification | Verdict |
|---|---|
| Digitisation error | **Refuted.** Correct series, correct colour, correct axis. |
| Physically implausible reading | **Unresolved.** Biomass falls 18.71 → 15.37 g/L in the printed figure; the model has no lysis or decay term. The paper offers no explanation. |
| Evidence about the model | **Supported.** This is where the published model is most visibly wrong. |

**No corrected dataset was created**, because no error was established. Excluding the
point would drop RMSE to 1.128 g/L and turn criterion E into a pass; it was not excluded,
and no threshold was moved.

---

## 4. Model audit against the paper

Every parameter in `reference_parameters.json` was checked against Table 2 as printed
(p. 4) and the nomenclature (p. 4). **No transcription defect was found.**

| Check | Result |
|---|---|
| Parameter values and units | All 17 match Table 2 with matching units (`μ 1/h`, `K g/L`, `K_o %`, `Y g/g`, `β 1/h`). Each carries a printed quote and page locator. |
| C\* (oxygen solubility) | 0.0075 g/L — matches the nomenclature verbatim. |
| kLa | 133 h⁻¹ — matches the printed statement for the 500 mL PreSens baffled flask at 200 rpm, 5 cm pitch, 1:5 fill ratio (p. 3, Table S2). |
| Eq. (12) fed-batch biomass | Read as `dX/dt = (μ − F/V)·X`. The PDF's text layer loses the minus sign; the reading is the standard dilution form, documented in the module docstring. |
| Eq. (13)–(15) | Documented under TN-04 (oxygen consumption term) and TN-05 (feed concentration units). |
| Ambiguities | Five transcription notes (TN-01…TN-05) all recorded with statement, decision and affected equations. TN-02 (Table 2 prints `e20/em1` where the denominator must be `e_m2`) is unresolved in the paper and read as `e2(0)/e_m2 = 0.874`, with the printed string preserved. |
| Operating conditions | Feed start 6 h (p. 3); Table 1 confirms the held-out experiment is PDGF, 20 % glycerol, 30 % yeast extract, 0.78 mL/h — exactly the frozen configuration. |
| Solver | Determinism exactly 0.0 across repeat runs. No numerical discrepancy. |
| Fitting provenance | Every parameter marked `fitted`: the authors estimated them from eight fed-batch experiments (six fitting, two validation). Not measured, though printed. |

**Empirical corroboration of the audit.** If a rate law were mis-transcribed, the
difference from the paper's own curve would grow and could change sign. It does not.
Comparing our trajectory with the authors' plotted curve over the span where theirs is
inside the frame:

| Scenario | Mean (ours − authors) | sd | Trend | R² |
|---|---|---|---|---|
| held-out (Fig. 3b) | **+0.897 g/L** | 0.244 | +0.0118 g/L/h | 0.11 |
| held-out, after 12 h | **+0.935 g/L** | **0.060** | — | — |
| optimum (Fig. 5c) | +0.643 g/L | 0.702 | −0.0403 g/L/h | 0.17 |

The difference is a **near-constant offset** — +0.935 ± 0.060 g/L across twelve hours in
the late phase. That is the signature of a **scale term**, not of a wrong equation. It
rules out, as the primary explanation, a transcription defect in the kinetics.

---

## 5. Candidate mechanisms

| Mechanism | What it could explain | Evidence for | Evidence against | Can the model distinguish it? |
|---|---|---|---|---|
| **Substrate-to-biomass yield reading** | The constant ~0.9 g/L offset | A flat offset is exactly what a yield produces | Yields match Table 2 to 3 dp; offset direction differs between scenarios (below) | No — yields are not separately identifiable from a single trajectory |
| **Initial substrate S2₀** | Overall magnitude | S2₀ = 25 g/L is *our derivation*, not the paper's | Sensitivity spans 5–50 g/L; **no case rescues criterion E** | Yes — sensitivity run |
| **TN-02 enzyme-ratio reading** | Late-phase shape | Reading is documented and unresolved in the paper | Varying `e2(0)/e_m2` over 0.1–1.0 moves the endpoint only 18.22–18.87 g/L; TN-02 was already run | Yes — prior what-if |
| **Oxygen-transfer limitation** | Late-phase collapse | min DO 0.478 %; regime reproduced | **No usable DO observations exist** — Fig. 3a's only mark carries 155.8 % uncertainty | **No** — the paper publishes no readable DO data |
| **Reference-data uncertainty** | Magnitude of the excursions | Fig. 3c glycerol points are all ~0 ± 0.095 g/L; the printed decline in biomass is biologically odd | Colour-verified; on the correct axis; the paper's own curve is off-scale there | Partly |
| **Digitisation of the authors' curve** | The ~0.9 g/L offset | Calibration uncertainty is 0.435 g/L, so +0.90 is ~2σ | Would not explain the t = 12 and t = 26 excursions, where the *data* disagree with both curves | **No** — needs the authors' raw output |

### What the evidence most strongly supports

**The paper's own model shows the same excursions.**

| t (h) | observed | this implementation | paper's own curve |
|---|---|---|---|
| 12.006 | 6.736 | 9.164 (**+2.43**) | 8.136 (**+1.40**) |
| 26.080 | 15.369 | 21.843 (**+6.47**) | > 20, clipped (**≥ +4.63**) |

At both material divergences the published model over-predicts, in the same direction,
by a comparable amount. Authors' RMSE over the seven readable points: 0.989 g/L; ours
over the same seven: 1.128 g/L.

---

## 6. Structural, parametric, experimental — assessed

**Reproduced first**, as required: the sensitivity scope and results were re-run from
the frozen configuration.

| Case | Change | 24 h biomass | RMSE | bias | within 2σ |
|---|---|---|---|---|---|
| primary | S2₀ 25, X₀ 0.05, DO₀ 100 | 20.016 | 2.520 | +1.359 | 0.750 |
| `s2_yeast_extract_only` | S2₀ = 5 g/L | 10.601 | 5.363 | −4.645 | 0.125 |
| `s2_double` | S2₀ = 50 g/L | 20.512 | 2.824 | +1.870 | 0.625 |
| `x0_fourfold` | X₀ = 0.2 g/L | 21.537 | 3.609 | +2.934 | 0.250 |
| `x0_tenfold` | X₀ = 0.5 g/L | 16.874 | 2.493 | +1.268 | 0.375 |
| `do0_80` | DO₀ = 80 % | 20.016 | 2.520 | +1.359 | 0.750 |

**Cases meeting criterion E (RMSE ≤ 1.5): none.** Cases meeting criterion H (≥ 0.60):
`s2_double`, `do0_80` — and `do0_80` is numerically identical to the primary.

So parameter and initial-condition uncertainty, within the ranges the paper leaves open,
is **insufficient** to explain the failure: the failure survives every case.

| Category | Assessment |
|---|---|
| **1. Implementation error** | **Not supported as the primary cause.** Parameters, units and conditions all trace to the paper; the difference from the published curve is a flat offset, not an evolving one. A ~0.9 g/L scale difference remains unexplained but is not a kinetic defect. |
| **2. Parameter / initial-condition uncertainty** | **Real but insufficient.** S2₀ dominates the outcome and is ours, not the paper's; no case rescues criterion E. |
| **3. Reference-data uncertainty** | **Contributes to magnitude only.** The data are colour-verified and on-axis. The printed biomass *decline* from 18.71 to 15.37 g/L is biologically odd and unexplained by the paper — recorded as unresolved. |
| **4. Structural model limitation** | **Best supported.** The published equations, with the authors' own parameters, over-predict at 12 h and leave the plot by 26 h on data explicitly held out of fitting. |
| **5. Unidentifiability** | **Applies to the ~0.9 g/L offset.** Yield reading, initial-condition convention and digitisation bias all predict a flat offset; nothing here separates them. |
| **6. Insufficient evidence** | **Applies to mechanism generally.** No usable DO data, no replicates, no tabular data, and the fit was made to other experiments we cannot see. |

The evidence supports a **ranked set**, not a single cause: (4) explains the excursions,
(5) explains the residual offset, (3) leaves one genuinely odd observation unexplained,
and (2) has been ruled out as sufficient.

### A finding the criteria did not anticipate

Under this implementation the held-out recipe (Fig. 3) is predicted to yield *more*
biomass (20.02 g/L) than the model-selected optimum (18.30 g/L). The measurements go the
other way: the selected optimum yielded 19.9–21.5 g/L, the held-out experiment read
18.71 g/L. The paper's optimisation chose its recipe *because* the fitted model preferred
it, so **the ordering the optimisation selected on is not reproduced.** This is stronger
than any single-point error, and no criterion in the protocol was written to catch it.
Recorded as an observation.

---

## 7. Diagnostic runs

All clearly labelled, all outside the primary evaluation. None changed an equation, a
parameter in the production model, or a threshold. No run used the held-out data to fit
anything.

| Run | Purpose | Result |
|---|---|---|
| `verify_digitisation.py` | Is the disputed mark the right series? | All 9 marks exactly `rgb(22,0,255)`, distance 0. Series assignment correct. |
| `analyse_residuals.py` | Characterise the residual pattern | Two excursions; 94 % of SSE; bias +1.359 |
| `compare_with_authors_curve.py` | Does the paper's model fail too? | **Yes** — +1.40 at 12 h, ≥ +4.63 at 26 h (clipped) |
| `compare_trajectory_shapes.py` | Dynamics error or scale term? | **Scale term** — flat +0.90 ± 0.06 g/L after 12 h |
| Sensitivity (frozen, re-run) | Can any reading rescue it? | **No case meets criterion E** |

**No parameter-fit experiment was run.** With one held-out experiment and 8 usable
observations, a calibration study would be under-determined, and any comparison against
the same points would no longer be independent. If one is ever run it must be a separate
study with separated data and its own criteria.

---

## 8. Regression tests

**No model-behaviour regression test was added**, because no confirmed defect was
established. Adding one would encode a speculative correction, and a test requiring
RMSE < 1.5 g/L would encode a scientific conclusion rather than an invariant.

`composition/tests/test_failure_investigation.py` — **18 tests**, guarding *evidence and
invariants* this investigation established:

| Class | Guards against |
|---|---|
| `TestTheDominantObservationIsRetained` | Silently dropping the point that carries 82.5 % of the squared error — which would turn criterion E into a pass. Asserts it is in the dataset, is compared, is flagged material, and that the verdict is taken from the primary metric, not the exclusion variant. |
| `TestNothingIsInventedOffAClippedAxis` | Reading a value where the paper's curve has left the plot. Asserts the clipped row carries `None`, not a number, and that the excess over the axis is recorded as a lower bound. |
| `TestTheDigitisationRefutationIsRecorded` | Re-asserting "digitisation artefact" without contradicting the pixel evidence; the two reports losing the refutation. |
| `TestDiagnosticsAreNonIntrusive` | A diagnostic mutating the failure it is explaining. **Behavioural**: digests the frozen inputs, runs all four diagnostic tools, re-digests, asserts nothing moved. Also pins the results to the frozen baseline and asserts `reproduction_status` was not upgraded. |
| `TestTheShapeFindingIsRecorded` | The flat-offset property silently changing, which would invalidate the audit's conclusion that this is a scale term and not a kinetic error. |

Existing suites re-run, all at baseline:

| Suite | Baseline | Now |
|---|---|---|
| Composition | 565 | **583** (+18) |
| `contract_boundary.gd` | 840 | **840** |
| `ganjave_graph_run.gd` | 51 | **51** |
| `palette_graph_run.gd` | 220 | **220** |
| Morris | 186 | **186** |
| Zieliński | 223 | **223** |
| Baez | 193 passed / 2 failed | **193 passed / 2 failed** |

The two Baez failures are the known pre-existing stale counts in
`Models/Baez/tests/test_exclusions.py` — `test_no_adapter_worker_was_added_for_this_model`
and `test_the_composition_registry_lists_only_the_pre_existing_models`, hard-coded
expectations of 2 workers and 2 registered models written before Ganjave was added.
Unrelated to this investigation, untouched, reported separately as required.

---

## 9. Unresolved questions

1. **The biomass decline.** The printed figure shows PDGF biomass falling from 18.71 to
   15.37 g/L between 24 and 26 h. The model has no decline mechanism and the paper
   offers no explanation. Is this a measurement artefact the paper did not flag, a
   plotting choice, or a real effect outside the model's scope?
2. **The ~0.9 g/L offset.** Consistent with a yield reading, an initial-condition
   convention, or a digitisation bias in the authors' curve. Not separable here.
3. **What S2₀ the authors used.** Our 25 g/L is derived from the stated medium. The
   paper never prints the model's S2 input, and the outcome depends strongly on it.
4. **TN-02.** `e20/em1` remains unresolved in the paper.
5. **No DO data.** The model's oxygen trajectory cannot be checked against any
   measurement.
6. **The fitting experiments.** Eight fed-batch experiments were used; the paper
   publishes figures for only some. The parameters are opaque to us.

---

## 10. Recommended next scientific action

**Ask the authors, or obtain the underlying data.** In priority order:

1. **The numerical time courses behind Fig. 3b and Fig. 3a.** This single request would
   resolve questions 1, 5 and most of 3 — it replaces raster readings with measurements,
   removes the clipping problem, and supplies the DO data that does not currently exist.
   It would also let the t = 26 h decline be checked directly.
2. **The value of S2 used as the model's initial condition.** One number; it dominates
   the outcome and is currently our inference.
3. **Confirmation of the Table 2 `e20/em1` denominator.** A one-line clarification closes
   TN-02.

**Not recommended:** re-tuning initial conditions until the score passes. The sensitivity
analysis shows no reading of the paper's unspecified conditions rescues criterion E, and
tuning against held-out data would destroy the independence that made this evaluation
worth running.

**If a second independent experiment becomes available,** a fresh protocol — not an
amendment to this one — should pre-register criteria against it. This protocol is spent:
its primary criterion has failed, and reusing it with new data would be a silent
relaxation.

---

## 11. Statement of scientific status

| Claim | Status |
|---|---|
| The implementation is a faithful transcription of the printed equations | **Supported** by this investigation: parameters, units and conditions all trace to the paper, and the difference from the published curve is a flat scale offset, not an evolving one. |
| The implementation reproduces the published model's held-out trajectory | **Not supported** — it sits ~0.9 g/L above it. |
| The published model reproduces its own held-out experiment | **Not supported by the paper's own figure** — it over-predicts at 12 h and leaves the plot by 26 h. |
| The Ganjave model's `reproduction_status` | **`not_yet_validated`, unchanged.** Nothing here upgrades it. |
| Any composed process | **Unchanged.** No composition was evaluated; none could be. |
| General predictive accuracy | **Not claimed.** One strain, one medium, one scale, two feed recipes. |

**The frozen evaluation still fails.** Criteria E and I fail as pre-registered. The
investigation explains the failure and locates it outside this implementation; it does
not turn it into a pass, and the pass was not available to take.
