# Ganjave Held-Out Residual Analysis

**Companion to** [`COMPOSED_PROCESS_SCIENTIFIC_VALIDATION.md`](COMPOSED_PROCESS_SCIENTIFIC_VALIDATION.md)
and [`GANJAVE_FAILURE_INVESTIGATION.md`](GANJAVE_FAILURE_INVESTIGATION.md).

The frozen evaluation fails. This document characterises *how*, and nothing more: a
residual is a number, and no mechanism is inferred from one.

Machine-readable: [`data/ganjave2022/investigation/residuals.json`](../data/ganjave2022/investigation/residuals.json)
Plot: `data/ganjave2022/investigation/heldout_trajectory_heldout_fig3.svg`

---

## Baseline

All five frozen inputs verified unchanged before any diagnostic was run:

| Input | SHA-256 | Status |
|---|---|---|
| `frozen_configuration.json` | `23c585ee06579ab7…` | unchanged |
| `observations.json` | `48141f2947428f3a…` | unchanged |
| `evaluation_protocol.json` | `d528e214e48becd9…` | unchanged |
| `figure_reference_data.json` | `46eb120f9553bdd6…` | unchanged |
| `reference_parameters.json` | `3f53c1fdc82449c2…` | unchanged |

Re-running the frozen evaluation reproduced every reported number exactly
(RMSE 2.5204, ratio 1.1401, min DO 0.4779 %, 6/8 within 2σ, optimum endpoint
18.2993 g/L). The immutable baseline is
`data/ganjave2022/investigation/baseline_primary_result.json`.

**Nothing in the primary evaluation was altered.** No observation was removed, no
threshold was moved, no input was changed.

---

## 1. Residuals — held-out experiment (paper Fig. 3b), 8 compared observations

Residual = prediction − observation. Uncertainty is the digitisation's own combined
figure, 0.7125 g/L, so 2σ = 1.425 g/L.

| t (h) | phase | observed | predicted | residual | abs err | sq err | % of SSE | 2σ | material? | RMSE if excluded |
|---|---|---|---|---|---|---|---|---|---|---|
| 3.964 | batch | 1.2651 | 1.4467 | **+0.1816** | 0.182 | 0.033 | 0.1 % | 1.425 | no | 2.6935 |
| 5.977 | batch | 3.2082 | 3.4791 | **+0.2709** | 0.271 | 0.073 | 0.1 % | 1.425 | no | 2.6924 |
| **12.006** | fed | 6.7356 | 9.1641 | **+2.4285** | 2.429 | 5.898 | **11.6 %** | 1.425 | **yes (3.4σ)** | 2.5332 |
| 16.026 | late | 13.0815 | 12.8643 | −0.2172 | 0.217 | 0.047 | 0.1 % | 1.425 | no | 2.6931 |
| 18.036 | late | 15.1854 | 14.6901 | −0.4953 | 0.495 | 0.245 | 0.5 % | 1.425 | no | 2.6879 |
| 20.046 | late | 15.6357 | 16.5001 | +0.8644 | 0.864 | 0.747 | 1.5 % | 1.425 | no | 2.6745 |
| 24.072 | late | 18.7139 | 20.0793 | +1.3654 | 1.365 | 1.864 | 3.7 % | 1.425 | no | 2.6445 |
| **26.080** | late | 15.3687 | 21.8425 | **+6.4738** | 6.474 | 41.911 | **82.5 %** | 1.425 | **yes (9.1σ)** | **1.1281** |

`fig3b:PDGF:0` at t = −0.057 h is not compared: outside the simulated interval, by the
rule fixed in the protocol. Its value, −0.081 g/L, is consistent with zero within
uncertainty.

### Aggregate

| Metric | Value |
|---|---|
| RMSE | 2.520 g/L |
| MAE | 1.537 g/L |
| Bias (mean signed) | **+1.359 g/L** |
| nRMSE | 22.61 % of observed mean |
| Max abs residual | 6.474 g/L (t = 26.080 h) |
| Within 1σ / 2σ | 4/8, 6/8 |

---

## 2. Pattern

**Two isolated excursions, not a drift.** Six of eight residuals lie inside 1.4 g/L;
the eighth-tenths of the error sits in two points. The residual sequence is
`+0.18, +0.27, **+2.43**, −0.22, −0.50, +0.86, +1.37, **+6.47** — it alternates sign
and is small everywhere except at 12 h and 26 h.

**First material divergence: t = 12.006 h**, residual +2.429 g/L = 3.4σ. Feeding starts
at 6 h, so this is 6 h into the fed phase.

**Growth with time** (phase means):

| Phase | Window | n | mean residual | RMSE |
|---|---|---|---|---|
| batch growth | 0–6 h | 2 | +0.226 | 0.231 |
| fed-batch start | 6–12 h | 1 | +0.271 | 0.271 |
| late fed-batch | ≥12 h | 5 | **+1.737** | **2.907** |

The error is monotonic in phase. But that monotonicity is produced almost entirely by
the two excursions falling in the late phase, not by a steady divergence: the six
in-window points after 12 h include residuals of −0.22, −0.50, +0.86 and +1.37, which
are not a growing trend.

**Sign: predictions run high.** Six positive, two negative, mean +1.359 g/L.

**Endpoint consistency.** At t = 24.072 h the error is +1.365 g/L — the same sign and
very nearly the same magnitude as the mean bias. The endpoint discrepancy is consistent
with the trajectory residuals rather than being a separate late-run effect. That is a
statement about consistency, not confirmation of any mechanism.

**Concentration:** the two excursions carry 94.1 % of the squared error between them;
the 82.5 % point is an order of magnitude larger than any other.

---

## 3. The disputed observation at t = 26.080 h

The frozen protocol pre-declared this point a "probable digitisation artefact". **That
pre-declaration was wrong.** The evidence follows.

### 3.1 Colour verification

`figure_reference_data.json` classified the figure by colour. Re-extracting the image
from `papers/Ganjave et al 2022.pdf` (PDF page index 5, image 1800×1230) and sampling
the pixel at each digitised mark, using the panel's own calibration
(`composition/tools/verify_digitisation.py`):

| t (h) | digitised value | pixel colour | distance to PDGF blue |
|---|---|---|---|
| −0.057 | −0.0807 | `rgb(22, 0, 255)` | **0.0** |
| 3.964 | 1.2651 | `rgb(22, 0, 255)` | **0.0** |
| 5.977 | 3.2082 | `rgb(22, 0, 255)` | **0.0** |
| 12.006 | 6.7356 | `rgb(22, 0, 255)` | **0.0** |
| 16.026 | 13.0815 | `rgb(22, 0, 255)` | **0.0** |
| 18.036 | 15.1854 | `rgb(22, 0, 255)` | **0.0** |
| 20.046 | 15.6357 | `rgb(22, 0, 255)` | **0.0** |
| 24.072 | 18.7139 | `rgb(22, 0, 255)` | **0.0** |
| **26.080** | 15.3687 | `rgb(22, 0, 255)` | **0.0** |

The PDGF experimental series is exactly `rgb(22, 0, 255)` and the model curve is
`rgb(123, 50, 152)`. Every mark, including the disputed one, sits on the PDGF colour
with **zero** distance. **The point was not assigned to the wrong series.**

### 3.2 Visual inspection

`data/ganjave2022/investigation/fig3b_panel.png` is the panel as printed. Its legend
contains exactly two entries: "Model predicted" (purple line) and "experimental (PDGF)"
(blue markers). There is one experimental series and one model curve.

The disputed marker is a genuine blue PDGF marker, on the biomass axis, in the correct
series. It sits **below and to the right of** the model curve — it is the one point the
model visibly fails to reach.

### 3.3 What the paper's own curve does at that time

The plot frame's y-axis maximum is 20 g/L. The purple model curve **leaves the plot
through the top spine at t ≈ 25 h**. No value can be read beyond it. So at t = 26.080 h:

| | value at t = 26.080 h | residual vs observed 15.369 |
|---|---|---|
| observed | 15.369 | — |
| paper's own model curve | **> 20 g/L (clipped)** | **≥ +4.63** |
| this implementation | 21.843 | +6.47 |

**The authors' own model over-predicts at this point by at least 4.63 g/L — more than
3σ — and the paper's own figure shows it.** This implementation over-predicts by more,
but it is not alone.

### 3.4 Verdict

**The point is genuine. It stays in the primary evaluation.** It is not excluded,
down-weighted, or replaced.

It is also no longer a candidate explanation for the failure. It is evidence *about the
model*: at t ≈ 26 h the published equations, as parameterised by the authors, predict
more than 20 g/L where the culture reached about 15 g/L. The one point that dominated
the RMSE is the point at which the paper's own model is most visibly wrong.

**Corrected dataset:** none created. A correction requires an established error, and
there is none here.

---

## 4. The other excursion — t = 12.006 h

This point was not previously flagged. It is a genuine material divergence at 3.4σ, and
the paper's own model is wrong there too:

| at t = 12.006 h | value | residual vs observed 6.736 |
|---|---|---|
| observed | 6.736 | — |
| paper's own model curve | 8.136 | **+1.401** |
| this implementation | 9.164 | **+2.429** |

Both over-predict. The paper's figure shows it: the blue marker at 12 h sits visibly
below the purple line. The implementation over-predicts more, by about 1.0 g/L.

---

## 5. Comparison against the paper's own plotted curve

Full data: `data/ganjave2022/investigation/comparison_with_authors_curve.json`.

| t (h) | observed | frozen | frozen res | authors' curve | authors' res |
|---|---|---|---|---|---|
| 3.964 | 1.265 | 1.447 | +0.182 | 0.590 | −0.675 |
| 5.977 | 3.208 | 3.479 | +0.271 | 2.377 | −0.831 |
| **12.006** | 6.736 | 9.164 | **+2.429** | 8.136 | **+1.401** |
| 16.026 | 13.082 | 12.864 | −0.217 | 11.898 | −1.183 |
| 18.036 | 15.185 | 14.690 | −0.495 | 13.748 | −1.437 |
| 20.046 | 15.636 | 16.500 | +0.864 | 15.581 | −0.055 |
| 24.072 | 18.714 | 20.079 | +1.365 | 19.238 | +0.524 |
| **26.080** | 15.369 | 21.843 | **+6.474** | **>20 (clipped)** | **≥ +4.63** |

Authors' RMSE over the seven readable points: **0.989 g/L**. Ours over the same seven:
**1.128 g/L**.

**At both material excursions the paper's own model is wrong, in the same direction, by a
comparable amount.**

---

## 6. Shape of the difference from the paper's curve

Full data: `data/ganjave2022/investigation/trajectory_shape_comparison.json`.

Comparing our trajectory against the authors' plotted curve over the span where theirs
is inside the frame:

| Scenario | Window | Mean (ours − authors) | sd | Trend | R² |
|---|---|---|---|---|---|
| heldout_fig3 (Fig. 3b) | 0.5–24.5 h | **+0.897 g/L** | 0.244 | +0.0118 g/L/h | 0.11 |
| heldout_fig3, after 12 h | 12–24.5 h | **+0.935 g/L** | 0.060 | — | — |
| optimum_fig5 (Fig. 5c) | 0–25 h | +0.643 g/L | 0.702 | −0.0403 g/L/h | 0.17 |

**The difference is a near-constant offset, flat in time.** After 12 h in the held-out
scenario it is +0.935 ± 0.060 g/L — a spread of 0.06 g/L across twelve hours.

This is diagnostically important. A transcription error in a numerator, denominator,
parenthesisation or rate law changes *how a trajectory evolves* — the difference would
grow and could change sign. An offset that does not move is the signature of a **scale
term**: a yield, an initial condition, or a systematic offset in how the authors' curve
was digitised. This diagnostic locates the difference; it does not name the cause, and
it cannot separate those three.

Note also that the Fig. 5c comparison is far noisier (sd 0.70 against 0.24). That panel
carries five cultures' markers over one model curve, so the colour-based trace of the
model curve is more likely contaminated. The Fig. 3b panel — one culture, one curve —
is the cleaner comparison and the one to trust.

---

## 7. Two claims in the earlier report that this analysis corrects

Recorded rather than quietly amended.

**"Substrate is excellent."** The glycerol comparison was described as reproducing the
substrate trajectory "to three hundredths of a gram per litre". That was too
favourable. The four held-out glycerol observations are 0.049, 0.039, 0.063 and
0.064 g/L — all essentially zero, glycerol exhausted by ~6 h — each carrying ±0.095 g/L
of digitisation uncertainty. Absolute agreement of 0.037 g/L against a ±0.095 g/L
tolerance is **not** strong evidence; the relative figure is 69.6 %. The comparison
constrains only that glycerol is exhausted early, which both the model and the
experiment satisfy. It says nothing about the shape of the substrate trajectory.

**"Probable digitisation artefact" for t = 26.080 h.** Refuted in §3. The point is
genuine and the paper's own model fails there.

---

## 8. What this analysis does not establish

- **No mechanism.** Two excursions at 12 h and 26 h are measured. Attributing them
  requires the evidence set out in `GANJAVE_FAILURE_INVESTIGATION.md`, which draws on
  the model audit, the shape comparison and the paper's own curve.
- **No usable dissolved-oxygen evidence.** Criterion G compares the model's own minimum
  DO against a paper-stated regime. It is a self-consistency check, **not** experimental
  agreement: Fig. 3a contains a single detected mark with 155.8 % uncertainty, which is
  unusable, so no DO observation supports or contradicts the model's oxygen trajectory.
- **No corrected dataset.** No digitisation error was established, so none was corrected.
- **No change to the frozen evaluation.** Every number here is derived from the
  unmodified primary result.
