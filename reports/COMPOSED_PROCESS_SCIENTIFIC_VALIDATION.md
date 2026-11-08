# Composed-Process Scientific Validation

**Outcome: no composed-process validation was possible, and the single-model evaluation
that was possible FAILED its pre-registered criterion.**

Two separate findings, deliberately not merged:

1. **Composition.** No cross-model composition is scientifically available to validate.
   Every cross-model boundary in this repository is refused and both permitted
   boundaries are same-model. Full argument and evidence in
   [`COMPOSED_PROCESS_VALIDATION_PLAN.md`](COMPOSED_PROCESS_VALIDATION_PLAN.md) §1–4.
2. **Model.** The strongest defensible evaluation the repository does support — the
   Ganjave implementation against the paper's own held-out experimental measurements —
   **fails** the criterion that was written before the run.

A successful execution is not a successful validation. The runs here succeeded
(`status: success_with_warnings`, determinism exactly 0) and the evaluation still fails.

---

## 1. Question

> Given the parameter set printed in Ganjave et al. (2022) Table 2, **never refitted**,
> and the feed recipe of the paper's own held-out validation experiment (Fig. 3: 20 %
> glycerol, 30 % yeast extract, 0.78 mL/h), does this implementation predict the biomass
> trajectory the authors **measured** in that experiment?

The parameters were estimated from Fig. 2 (30 % / 40 % / 0.52 mL/h). Fig. 3's caption
states its data "was not used for estimation of model parameters", and its feed differs
from both the fitting experiment and the model-selected optimum. It is a genuine
out-of-sample test of the trajectory.

**This is not the task's stated question.** The task asked about a *composition*. This
question is about a *model*, and no result below transfers to composed processes.

## 2. System

| | |
|---|---|
| Model | `ganjave` 0.1.0, cybernetic growth model |
| Equations | Ganjave et al. (2022) eq. (8)–(16), as printed |
| Parameters | Table 2 as printed, loaded as fitted. **Not refitted, not reloaded, not tuned.** |
| Solver | RK4, `rtol` 1e-6, `atol` 1e-9, `h_max` 0.01 h (from the reported kLa = 133 h⁻¹) |
| Graph | **One instance, zero connections.** |
| Duration | 27 h (to admit every observed time; not a fit) |
| Execution path | `python -m composition.runner` — the normal ScaleUp AI pipeline |

### The graph has no connections, and that is the finding

A composition needs a boundary between two models. There are nine ordered pairs in
`cross_model.py`; two are permitted and **both are same-model**:

- **Morris → Morris** — conservation across adjacent non-reacting control volumes.
  Cannot describe a cultivation: Morris has nowhere to declare a yield, and no source
  supplies one for this system. Encoding one would be writing a new model.
- **Ganjave → Ganjave** — forward cascade on residual glycerol. The rule text already
  says it: *"permitted under the model's declared assumption, **not validated by it**:
  nothing in the paper seeds a second culture from the first."* Confirmed against the
  PDF — the paper cultivates five proteins as **five parallel shake flasks**, not a
  sequential train.

The seven cross-model pairs are refused: Morris↔Ganjave on disjoint quantity
vocabularies, Morris↔Zieliński on component identity, Ganjave↔Zieliński because a
matching `mass_concentration` in g/L between two different *E. coli* cultures is a
coincidence of vocabulary, and Zieliński→Zieliński because it declares no supplyable port.

Adding a second instance to make the graph look composed would have produced a
`success` and a `permitted` disposition. That is the failure this task exists to catch,
and it was not done.

## 3. Evidence

49 experimental observations, all digitised from the paper's raster figures with
per-point calibration and uncertainty. **No observation is a model output.**

| Dataset | Paper | n | Cultures | Feed | Role |
|---|---|---|---|---|---|
| `fig3b` biomass | **Fig. 3b**, p. 6 | 9 | PDGF | 20 % / 30 % / 0.78 mL/h | **primary** |
| `fig3c` glycerol | **Fig. 3c**, p. 6 | 5 | PDGF | 20 % / 30 % / 0.78 mL/h | secondary |
| `fig5c` biomass | **Fig. 5c**, p. 7 | 35 | 5 proteins | 17.5 % / 24.5 % / 0.72 mL/h | secondary |

Each point carries `reading_uncertainty` + `calibration_uncertainty` = **0.7125 g/L**
(Fig. 3b) or **≈0.85 g/L** (Fig. 5c), per the digitisation's own convention.

**Excluded by construction:** Fig. 2, the fitting experiment. Comparing against it would
be circular.

### A traceability defect found and corrected

`figure_reference_data.json` keys the held-out experiment as figure `"5"` and the
selected optimum as `"6"`. In the paper they are **Fig. 3** and **Fig. 5**. Anyone
auditing a citation would have looked up the wrong figure. The new dataset carries
`paper_figure` on every point, and `build_evaluation_dataset.py` asserts the mapping
against each figure's printed caption and feed recipe — so a divergence fails the build
rather than shipping.

## 4. Assumptions

Every value classified; see `data/ganjave2022/frozen_configuration.json`.

| Value | Value | Class | Basis |
|---|---|---|---|
| S1₀ glycerol | 2.76 g/L | **reported** | printed p. 2 |
| V₀ | 0.1 L | **reported** | printed p. 2 |
| Feed recipe (both scenarios) | — | **reported** | Fig. 3 / Fig. 5 captions |
| S2₀ | 25 g/L | **derived** | SOB = tryptone 20 + yeast extract 5 g/L; the whole complex fraction |
| X₀ | 0.05 g/L | **assumed** | paper prints OD 600 and no calibration |
| DO₀ | 100 % | **assumed** | not stated; air-saturated flask |

Three of the six initial conditions are not derivable from the paper. All three are
carried into sensitivity analysis (§7) rather than hidden in a fixed value.

## 5. Protocol

`data/ganjave2022/evaluation_protocol.json`, written before the primary scenario was run.

| Criterion | Threshold | Justification |
|---|---|---|
| **E** held-out trajectory | RMSE ≤ 1.5 g/L | 2.1× the reference data's own 0.7125 g/L resolution; the paper's own model sits ~1 g/L RMS from this data |
| **F** no worse than the authors' model | ratio ≤ 1.5 | Transcription fidelity against the same points; cannot be satisfied by tuning |
| **G** oxygen-limited regime | min DO(6–24 h) < 10 % | Paper-stated (p. 9), not implementation-stated |
| **H** agreement with reported uncertainty | ≥ 60 % within 2σ | 2σ = 1.425 g/L; unanimity would test against the paper's own fitting error |
| **I** reported endpoint range | 19.9 ≤ X ≤ 21.5 g/L | The paper's own measurement (p. 7), carried unchanged from the pre-registered fixture where it had already failed once |
| **J** determinism | rel. diff ≤ 1e-9 | Implementation property |

**Data separation:** zero calibration. Every parameter comes from the paper's Table 2.

**Contamination disclosure.** The primary scenario had **not** been run when these were
written. The secondary scenario's 24 h endpoint (18.299 g/L) *had* been seen during an
unrelated pipeline probe, so it is reported as a disclosed, secondary comparison and no
pass is claimed from it. The primary scenario is unaffected.

## 6. Results

### Primary — held-out Fig. 3b, 8 compared observations — **FAIL**

| Criterion | Observed | Threshold | Verdict |
|---|---|---|---|
| **E** held-out trajectory | **RMSE 2.520 g/L** | ≤ 1.5 | **FAIL** |
| F no worse than authors' model | ratio **1.140** | ≤ 1.5 | PASS |
| G oxygen-limited regime | min DO **0.478 %** | < 10 % | PASS |
| H agreement within 2σ | **6/8 = 0.75** | ≥ 0.60 | PASS |
| J determinism | **0.0** | ≤ 1e-9 | PASS |

Supporting: MAE 1.537, bias **+1.359 g/L** (systematic over-prediction), nRMSE 22.6 %.

| t (h) | observed | predicted | residual | 2σ | verdict |
|---|---|---|---|---|---|
| 3.964 | 1.265 | 1.447 | +0.182 | 1.425 | ok |
| 5.977 | 3.208 | 3.479 | +0.271 | 1.425 | ok |
| 12.006 | 6.736 | 9.164 | **+2.429** | 1.425 | **out** |
| 16.026 | 13.082 | 12.864 | −0.217 | 1.425 | ok |
| 18.036 | 15.185 | 14.690 | −0.495 | 1.425 | ok |
| 20.046 | 15.636 | 16.500 | +0.864 | 1.425 | ok |
| 24.072 | 18.714 | 20.079 | +1.365 | 1.425 | ok |
| 26.080 | 15.369 | 21.843 | **+6.474** | 1.425 | **out** |

**Substrate is excellent.** Glycerol (Fig. 3c, 4 points): **RMSE 0.037 g/L**, 4/4 within
1σ. The growth model reproduces the substrate trajectory to three hundredths of a gram
per litre while getting biomass a couple of grams per litre out. That asymmetry matters:
it argues the *dynamics* are right and something about *how much substrate becomes
biomass* is not.

### The failure is dominated by one physically impossible observation

The `t = 26.080 h` mark reads **15.369 g/L**, *below* the 18.714 g/L read at 24.072 h.
The model has no lysis and no decay term, so biomass is monotonic by construction — and
the digitised curve for the same culture does not decline either. This was identified as
an anomaly **before** the run and its handling pre-declared in the protocol.

Reported both ways, as pre-declared:

| Analysis | n | RMSE | Within 2σ |
|---|---|---|---|
| **Primary (all compared points)** | 8 | **2.520** | 0.750 |
| Excluding the declared anomaly | 7 | 1.128 | 0.857 |

**Excluding it would satisfy criterion E.** The primary analysis is the pre-registered
one, and it **FAILS**. The excluded figure is reported as a *diagnosis* — the failure is
attributable to a probable digitisation artefact in the reference data, not to the model —
and **not** as a verdict. Switching to the favourable subset after seeing which way the
residual pointed would be precisely the post-hoc reselection the protocol forbids.

Resolving this properly requires re-digitising Fig. 3b at the 26 h mark, which is outside
the frozen analysis and would need its own protocol.

### Secondary — selected optimum Fig. 5c, 34 observations — **FAIL** (disclosed)

| Criterion | Observed | Threshold | Verdict |
|---|---|---|---|
| **I** reported endpoint range | **18.299 g/L** | [19.9, 21.5] | **FAIL** |
| F no worse than authors' model | ratio 0.936 | ≤ 1.5 | PASS |
| G oxygen-limited regime | min DO 0.869 % | < 10 % | PASS |
| H agreement within 2σ | 27/34 = 0.794 | ≥ 0.60 | PASS |

Across five cultures the model tracks the authors' own curve *better* than the authors'
curve tracks the measurements (ratio 0.936) — the implementation is a faithful
transcription. But the **endpoint is below every one of the five cultures**:

| Culture | last t (h) | observed | predicted | residual |
|---|---|---|---|---|
| PDGF | 22.07 | 18.886 | 17.723 | −1.163 |
| FDH | 24.09 | 21.717 | 18.325 | **−3.392** |
| G. Can. ADH | 24.08 | 20.311 | 18.323 | **−1.988** |
| L. Kefir ADH | 23.09 | 18.442 | 18.028 | −0.414 |
| EYFP | 24.12 | 19.290 | 18.333 | −0.956 |

Measured endpoints span 18.44–21.72 g/L, consistent with the paper's reported
19.9–21.5 g/L. Our prediction of 18.30 g/L sits under all five.

### A finding the criteria did not anticipate: the ranking is inverted

Under this implementation the **held-out** recipe (Fig. 3) is predicted to yield *more*
biomass (20.02 g/L) than the **model-selected optimum** (18.30 g/L). The measurements go
the other way: the selected optimum yielded 19.9–21.5 g/L, the held-out experiment read
18.71 g/L.

The paper's optimisation chose its recipe *because* the fitted model preferred it. If the
implementation inverts that ordering, the selection itself is not reproduced — which is a
stronger problem than any single-point error, and one no criterion in the protocol was
written to catch. It is recorded here as an observation, not as a scored criterion.

## 7. Sensitivity

Each condition the paper does not state, varied on the primary scenario. Reported
separately; **not** merged into the primary metrics or the verdict.

| Case | Change | 24 h biomass | RMSE | Bias | within 2σ |
|---|---|---|---|---|---|
| primary | S2₀ 25, X₀ 0.05, DO₀ 100 | 20.016 | 2.520 | +1.359 | 0.750 |
| `s2_yeast_extract_only` | S2₀ = 5 g/L | 10.601 | **5.363** | −4.645 | **0.125** |
| `s2_double` | S2₀ = 50 g/L | 20.512 | 2.824 | +1.870 | 0.625 |
| `x0_fourfold` | X₀ = 0.2 g/L | 21.537 | 3.609 | +2.934 | **0.250** |
| `x0_tenfold` | X₀ = 0.5 g/L | 16.874 | 2.493 | +1.268 | 0.375 |
| `do0_80` | DO₀ = 80 % | 20.016 | 2.520 | +1.359 | 0.750 |

Three things follow, and the second matters most:

1. **The medium reading dominates.** S2₀ = 5 g/L gives RMSE 5.36 and only 12.5 % of
   points within 2σ. The paper does not state this value and does not resolve which
   reading is right.
2. **No sensitivity case rescues criterion E.** Every one fails RMSE ≤ 1.5, and four of
   five fall below the 0.60 agreement threshold. **The failure is not an artefact of one
   assumed value** — it survives every plausible reading of the paper's unspecified
   conditions.
3. **DO₀ is irrelevant**, as the fixture predicted: DO 0 = 80 % and 100 % agree to four
   decimal places, because the culture's own demand sets the profile, not its start.

## 8. Limitations

- **No composition was evaluated.** The task's objective is unmet, and no result here
  speaks to composed processes.
- **The reference data is digitised, not tabulated.** The paper publishes no numerical
  time courses and no replicate error bars. Every observation carries a reading
  uncertainty of ~0.7–0.9 g/L, and one mark is demonstrably misread. Conclusions about
  agreement are bounded by what a raster figure can resolve.
- **Three initial conditions are not derivable** from the source, and the outcome depends
  strongly on one of them (S2₀).
- **TN-02 remains open** (the `e20/em1` printing ambiguity in Table 2). Its sensitivity
  is measurable but does not resolve it, and it is untouched here.
- **Two scenarios, one strain, one scale, one medium.** Nothing here supports a claim
  beyond these conditions.
- **Protein expression is not modelled.** Biomass is protein-independent in this model,
  so all five constructs share one predicted trajectory; the spread across cultures is
  experimental variance the model does not attempt to reproduce.
- **The endpoint criterion was already failed once** in the pre-existing fixture. It is
  carried unchanged rather than re-selected, and it fails again.

## 9. Conclusion

**The predefined criteria FAILED.** Not softened, not re-scoped, not re-thresholded after
seeing the result.

| Question | Answer |
|---|---|
| Does a scientifically defensible **composition** predict an independently reported process? | **Not answerable — none exists.** Documented, not manufactured. |
| Does this implementation reproduce the paper's **held-out measurements**? | **No**, by the pre-registered margin: RMSE 2.52 g/L against a ≤ 1.5 g/L criterion. |
| Is it a faithful **transcription** of the printed equations? | **Yes** — ratio 1.14 against the authors' own model, determinism exactly 0, substrate trajectory to 0.037 g/L. |
| Is the Ganjave **model** validated? | **No.** `reproduction_status` remains `not_yet_validated`. Nothing in this report changes it. |
| Is any **composed process** validated? | **No.** None was evaluated, and none could be. |
| Does this support **general predictive accuracy**? | **No.** One strain, one medium, one scale, two feed recipes, one 27 h run. |

The honest summary: **this is a good transcription of a model that does not fully
reproduce its own held-out measurements.** The failure is not marginal — it survives
every sensitivity case — but it is also narrowly located: the substrate trajectory is
essentially exact, the growth phase and oxygen limitation are reproduced, the
transcription is faithful, and the growth-phase trajectory itself tracks the authors'
model to within 14 %. What is wrong is the amount of biomass the model produces from the
substrate it consumes, and the sign of that error flips between the two feed recipes
tested.

## 10. Reproduction

```powershell
# 1. Rebuild the dataset from the digitisation (asserts the figure mapping)
python composition/tools/build_evaluation_dataset.py

# 2. Run the frozen configuration through the normal pipeline
python composition/tools/evaluate_heldout_biomass.py

# 3. Re-verify: structure, digests, metrics recomputed from stored predictions
python -m pytest composition/tests/test_evaluation_dataset.py `
    composition/tests/test_heldout_validation.py -q

# 4. Full regression
cd composition; python -m pytest tests -q
```

| Artefact | Path |
|---|---|
| Dataset (49 observations) | `data/ganjave2022/observations.json` |
| Provenance record | `data/ganjave2022/PROVENANCE.md` |
| Frozen configuration | `data/ganjave2022/frozen_configuration.json` |
| Protocol (pre-registered) | `data/ganjave2022/evaluation_protocol.json` |
| Results + SHA-256 of every input | `data/ganjave2022/results/evaluation_results.json` |
| Per-run graphs and results | `data/ganjave2022/results/runs/` *(gitignored, ~200 MB of dense trajectories, regenerable)* |
| Plan (composition finding) | `reports/COMPOSED_PROCESS_VALIDATION_PLAN.md` |

`evaluation_results.json` records a SHA-256 for the frozen configuration, the dataset, the
protocol, the digitisation and the parameter file. Changing the parameters, the data, the
graph or a threshold changes the digest, and `test_every_digest_still_matches` fails.

Exact command for every run:

```powershell
python -m composition.runner --graph <run>.graph.json --result <run>.result.json
```

---

## 11. Tests and regression

### New — 62 tests, no outcome hard-coded

| File | Tests | Covers |
|---|---|---|
| `test_evaluation_dataset.py` | 23 | dataset structure; observation/prediction separation; figure-number mapping asserted against printed captions and feed recipes; per-point uncertainty; nothing interpolated or tabulated; builder reproduces the committed file byte-for-byte and refuses a broken mapping |
| `test_heldout_validation.py` | 39 | input digests; model/version/parameter pinning; classification of every initial condition; blinding disclosure; thresholds read from the protocol, never from the code; every metric recomputed from stored points; verdict re-derived; pipeline re-run end to end; composition finding intact |

**No test asserts that a criterion passes.** Each re-derives the recorded verdict from
the stored predictions and the protocol's thresholds, and fails only if a recorded verdict
does not follow from the data. If the model improves, the recomputed verdict changes and
the digest guard demands a deliberate re-run; if it degrades, the recorded failure stands
rather than a threshold moving.

Three tests exist specifically to catch dishonest reporting:

- `test_no_criterion_thresholds_were_loosened_against_the_recorded_result` — the
  thresholds in the results must be the thresholds in the frozen protocol.
- `test_the_excluded_anomaly_would_change_the_verdict_and_is_still_reported` — excluding
  the artefact flips criterion E; the primary analysis must still decide, and the
  favourable number must still be visible in the report as a diagnosis.
- `test_the_combined_graph_is_never_claimed_validated` — no scenario may report a
  composed graph as validated.

### Regression — all at or above baseline

| Suite | Baseline | Now |
|---|---|---|
| Composition | 503 | **565** (+62) |
| `contract_boundary.gd` | 840 | **840** |
| `ganjave_graph_run.gd` | 51 | **51** |
| `palette_graph_run.gd` | 220 | **220** |
| Morris | 186 | **186** |
| Zieliński | 223 | **223** |
| Baez | 193 passed / 2 failed | **193 passed / 2 failed** |

The two Baez failures are the pre-existing stale counts in
`Models/Baez/tests/test_exclusions.py` — hard-coded expectations of 2 workers and 2
registered models, written before Ganjave was added. Unrelated, untouched, reported
separately.

**Nothing was changed to reach a passing suite.** No equation, parameter, solver setting,
contract or compatibility rule was modified. The model fails criterion E and criterion I,
and the tests record that.

### Defects found and fixed during this work

1. **`figure_reference_data.json` figure keys do not match the paper** — dataset key `"5"`
   is paper Fig. 3, key `"6"` is paper Fig. 5. Corrected in the new dataset and asserted.
2. **The authors' curve returned `NaN`** past its readable span, poisoning the
   non-finite samples into the metrics and silently scoring an unevaluable criterion F as
   a *failure*. Non-finite samples are now dropped, unreadable times are recorded, and an
   unevaluable criterion is **inconclusive**, never `fail`.
3. **`NaN` was written into the results JSON**, which is not valid JSON and is rejected by
   strict parsers including Godot's. All output now goes through a `json_safe` pass that
   writes `null`.
4. **A prior report contradicted its own data.** `GANJAVE_SCIENTIFIC_VALIDATION.md` states
   "No trajectory has been compared against a measured point"; `validation_results.json`
   contains exactly that comparison. The data is correct. Recorded in the plan rather than
   rewritten, because rewriting a pre-registered fixture would destroy its audit trail.

