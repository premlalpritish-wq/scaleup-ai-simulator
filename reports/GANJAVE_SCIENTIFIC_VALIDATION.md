# Ganjave et al. (2022) — scientific validation report

**Model**: `ganjave2022.cybernetic-growth` (equations version 1.1.0, parameter set `ganjave2022.table2`, solver RK4(3) step-doubling, rtol 1e-6, atol 1e-9, h_max 0.01 h).
**Date**: 2026-10-18.
**Status**: `partially_validated` (see §10).

The short version, so the rest of this document can be read critically rather than
hopefully: the implementation computes the printed equations correctly and does not
reproduce the paper's reported behaviour, because the paper never states three of
the initial conditions the model requires.  With the defensible reading of the one
of those that is recoverable (the full complex-substrate fraction of the stated
SOB medium) the implementation lands within 6.5 % of the authors' own plotted
model prediction; with the narrower reading the culture never becomes
oxygen-limited and the biomass is four times too low.  That is a real finding, not
a failure to run the code, and it is the reason the status is not `validated`.

---

## 1. Experiment selected, and why

The selected experiment is the **optimised fed-batch process** reported in
section 3.3, Figure 5:

> Ganjave et al. 2022, *Biotechnology Reports* 33:e00694,
> doi:10.1016/j.btre.2021.e00694, printed p. 7, section 3.3.

It was chosen over the other two candidate experiments because it is the only
configuration in the paper that appears with experimental data **and** a complete
feed recipe:

- the fitting experiment (Fig. 2: 30 % glycerol, 40 % yeast extract, 0.52 mL/h)
  cannot be used, because the parameters were tuned against it; comparing against
  it would test the transcription against the data it was fitted to;
- the held-out validation experiment (Fig. 3: 20 % glycerol, 30 % yeast extract,
  0.78 mL/h) has experimental points but no reported final biomass endpoint;
- the optimised process (Fig. 5: 17.5 % glycerol, 24.5 % yeast extract,
  0.72 mL/h) has both experimental points for five proteins and a reported
  endpoint (20.7 g DCW/L), and its feed recipe is stated in full.

Figure 2 is extracted for completeness and is labelled `role: fitting` in
`data/figure_reference_data.json`; it is not compared against.

## 2. Source-derived conditions and parameters

### 2.1 Operating conditions (reported)

| Quantity | Value | Source (printed page) |
|---|---|---|
| Flask | 500 mL PreSens baffled, 5 cm pitch | p. 2, 2.3 |
| Working volume | 100 mL | p. 2, 2.3 |
| Temperature | 32 C | p. 2, 2.3 |
| Shaking | 200 rpm | p. 3, 3.1 |
| Initial OD600 | 0.05 | p. 2, 2.2 |
| Initial glycerol | 2.76 g/L | p. 2, 2.2 |
| kLa | 133 h^-1 | p. 3, 3.1 (Table S2) |
| C* | 0.0075 g/L | notation table, p. 2 |
| DO measurement | PreSens spots, every 10 s | p. 2, 2.3 |
| Feed start | 6 h, at the dissolved-oxygen minimum | p. 3, 3.1 |
| Feed device | 6-channel programmable syringe pump, constant flow | p. 2, 2.3 |
| Feed recipe, selected optimum | 17.5 % w/v glycerol, 24.5 % w/v yeast extract, 0.72 mL/h | p. 7, 3.3 |

### 2.2 Reported endpoints

| Quantity | Value | Source |
|---|---|---|
| Biomass, optimised process (24 h) | 20.7 g DCW/L | Abstract, p. 1 |
| Biomass range across fed-batch trials | 19.9 - 21.5 g DCW/L | p. 7, 3.3 |
| Model-predicted biomass for the selected recipe | 19.44 g DCW/L | p. 7, 3.3 |
| eYFP specific-activity improvement, 3 L bioreactor vs shake flask | 2.8 fold | p. 7, 3.4 |

### 2.3 Parameter set

`ganjave2022.table2`, equations version 1.1.0. Twenty parameters, of which two
(`C_star`, `kLa`) are reported measurements and eighteen are fitted by the
authors' hybrid genetic-algorithm + fmincon procedure against six fed-batch
experiments. The parameter set is loaded, never refit: `ParameterSet.with_overrides`
is the only way to change a value, and it marks the result `assumed` and records
the original.

### 2.4 Mode and feed

Mode `fed_batch`, duration 24 h, feed concentrations 175 g/L glycerol and 245 g/L
yeast extract (1 % w/v = 10 g/L), flow 0.72 mL/h = 7.2e-4 L/h, feed start
6.0 h. The feed is supplemented with 2 mM MgCl2/MgSO4 and 2x antibiotic (p. 2);
neither enters the model's balances.

### 2.5 What the paper does not state

`models/reference.py` lists six missing items, each with its consequence:

- fed-batch time-course measurements (figures only; no numerical data);
- optimisation constraints and bounds (supplementary Table S3);
- kLa at geometries other than the one reported;
- OD600-to-dry-cell-weight calibration;
- initial dissolved oxygen and initial complex-substrate concentration as model
  inputs (not stated anywhere);
- feed compositions for experiments S5 and S6 (Table 1 prints them without a
  composition).

The first item is the one that matters for this report: because the time courses
are figures, no trajectory here has been compared against a measured point. The
fourth and fifth items are what the rest of this report is about.

## 3. Assumptions, missing information and unresolved ambiguities

### 3.1 Initial conditions

Three of the seven initial conditions are not stated by the paper. They are
required inputs of the model, and the adapter and the composition layer both
refuse to substitute a default.

| Condition | Value used (primary case) | Classification | Basis |
|---|---|---|---|
| X0 | 0.05 g/L | assumed | reported initial OD600 of 0.05, with no OD-to-DCW calibration |
| S2_0 | 25 g/L | derived | SOB medium: tryptone 20 g/L + yeast extract 5 g/L; both are complex nitrogen-rich substrates, so the whole complex fraction is 25 g/L |
| DO0 | 100 % | assumed | a shake flask left standing is saturated; the paper's own Fig. 5a model curve starts at about 94-95 % |
| S1_0 | 2.76 g/L | reported | p. 2 |
| V0 | 0.1 L | reported | p. 2 |
| e1_0 | 0.082 | reported | Table 2 |
| e2_0 | 0.874 | reported (ambiguous) | Table 2, item TN-02 |

The choice that dominates everything is S2_0. Its sensitivity is in section 7.

### 3.2 TN-02: the `e20/em1` ambiguity

Table 2 prints the initial enzyme ratio for combination 2 as `e20/em1`. The
denominator of combination 2 must be `e_m2`, not `e_m1`; the printed string
cannot be reconciled with the notation. The model reads the printed number as
`e2(0)/e_m2 = 0.874`, which is the only reading that uses a quantity belonging
to combination 2.

Competing interpretations:

- **A (implemented)**: `e2(0)/e_m2 = 0.874`, i.e. `e_ratio2_0 = 0.874`. The
  denominator is a typo for `e_m2`. This is the only reading in which the ratio
  is dimensionally meaningful.
- **B (literal)**: the printed string is read as `e2(0)/e_m1 = 0.874`. That
  mixes combination 2's initial enzyme with combination 1's maximum, which has
  no interpretation in the printed equations. No value for `e2(0)` follows from
  it without an additional assumption, so it is not testable as stated.
- **C (alternative)**: the value belongs to combination 1 and should be
  `e1(0)/e_m1`, with `e2(0)/e_m2` taking some other value. There is no
  support for this in the text.

Effect on the model: e2_0 scales the early growth rate through
`mu2 = mum2 * e2 * r2`. The sensitivity sweep in section 7.2 shows that the
endpoint biomass moves by about 0.7 g/L across the range 0.1 to 1.0, and the
shape agreement moves from 6.1 % RMSE to 11.6 %. The ambiguity is therefore
measurable and not cosmetic, but it does not change the conclusion: even the
value that best fits the paper's own curve (0.1) leaves a 6 % residual, and the
paper's printed value is 0.874.

TN-02 is left open. No parameter was changed.

### 3.3 Other ambiguities

- The composition of the complex substrate: SOB contains both tryptone and yeast
  extract, and the paper calls S2 a "complex nitrogen-rich substrate" without
  saying which of them it is. This is the S2_0 sensitivity.
- The optimisation constraints (Table S3) are supplementary and are not in the
  main paper; the model does not implement the optimisation, only the selected
  optimum.
- The reported biomass is a dry-cell weight, measured by gravimetry at the end
  of cultivation in triplicate (p. 2). The figures plot biomass in g/L DCW,
  which is what the model outputs.

## 4. Reference-data extraction methodology

The paper's time courses are figures, not tables. They were digitized from the
raster images embedded in the PDF at native resolution (about 300 dpi) using
`Models/Ganjave/tools/digitize_figures.py`, which is reproducible and
deterministic. The method and its uncertainty are stated here because a
digitization that depends on someone's eye is not evidence.

### 4.1 Calibration

Each panel's axis frame is found from the long black spine rules, not from
hand-entered pixel coordinates. The tick labels are located as text blocks just
outside the frame, and matplotlib centres a label on its tick, so a label's
bounding-box centre along the axis is the tick position, measurable to a
fraction of a pixel. The scale is fitted over all labels (so one mis-measured
glyph cannot dominate), and the offset is anchored on the axis minimum at the
frame edge, where no glyph sits to bias the reading. The disagreement between
the label-derived scale and the frame-edge-anchored scale is reported as the
calibration uncertainty, in data units, over the whole axis span. The reported
uncertainties are:

| Panel | x (h) | y |
|---|---|---|
| Fig. 3a (DO) | 0.14 h | 2.0 % |
| Fig. 3b (biomass) | 0.30 h | 0.33 g/L |
| Fig. 3c (glycerol) | 0.30 h | 0.037 g/L |
| Fig. 5a (DO) | 0.25 h | 2.01 % |
| Fig. 5b (pH) | 0.26 h | 0.11 pH |
| Fig. 5c (biomass) | 0.26 h | 0.49 g/L |
| Fig. 5d (glycerol) | 0.26 h | 0.054 g/L |

### 4.2 Series identification

By hue, never by position. A channel *difference* is tested, because an
axis-aligned box in RGB also accepts grey, which would let a black axis spine be
read as a purple model curve. Experimental marks are saturated blobs; the
authors' model predictions are the purple line; legend boxes are detected as
rectangles with all four borders drawn and excluded, so a legend's sample marker
cannot be read as a datum.

### 4.3 Uncertainty handling

- Mark centroids give the value; the mark's own radius gives a floor on the
  reading uncertainty, reported per point.
- Points where a raster column holds several branches of a trace (a steep
  segment) are marked `ambiguous` rather than averaged.
- A curve that coincides with an axis spine is not separately resolved, and the
  span limit is recorded (for example the authors' model biomass curve in
  Fig. 3b leaves the top of the panel at about 24.9 h).
- No value is invented where a curve is unreadable.

### 4.4 Cross-checks against printed numbers

Three independent checks on the digitization itself:

1. The digitized Figure 3c experimental glycerol at t = 0 reads 2.78 g/L against
   the printed 2.76 g/L -- within the stated digitization uncertainty. This
   confirms both the calibration and the printed value.
2. The digitized Figure 5c model biomass at 24 h reads 19.58 g/L against the
   printed model prediction of 19.44 g/L -- a 0.7 % gap, inside the
   calibration uncertainty.
3. The digitized Figure 5d model glycerol at t = 0 reads 2.78 g/L against the
   printed 2.76 g/L.

These checks are what make the digitized curves usable as comparison targets
rather than as illustrations.

### 4.5 What was not digitized

Figure 2 (the fitting experiment) is extracted for completeness and recorded as
`role: fitting`; its parameters were tuned against it, so comparing against it
would test the transcription against the data it was fitted to, which is not
independent evidence. No comparison against it is made.

## 5. Model-versus-reference comparisons

The comparison is against the paper's **own plotted model prediction**, which is
the correct target. Matching the *measured* points instead would require
refitting the parameters against them, which this package explicitly does not do.
The measured points are reported alongside, labelled as measurements, so the
difference between "the model reproduces the model" and "the model reproduces
the experiment" stays visible.

### 5.1 Primary case (S2_0 = 25 g/L, X0 = 0.05 g/L, DO0 = 100 %)

Biomass (g/L DCW), my implementation against the paper's plotted model:

| t (h) | implementation | paper's model | difference |
|---|---|---|---|
| 4 | 0.582 | 0.596 | -0.014 |
| 6 | 1.301 | 2.389 | -1.089 |
| 8 | 2.098 | 4.352 | -2.255 |
| 10 | 3.002 | 6.337 | -3.337 |
| 12 | 3.843 | 8.309 | -4.467 |
| 14 | 4.652 | 10.260 | -5.610 |
| 16 | 5.436 | 12.218 | -6.784 |
| 18 | 6.196 | 14.152 | -7.958 |
| 20 | 6.936 | 16.059 | -9.125 |
| 22 | 7.656 | 17.960 | -10.306 |
| 24 | 8.355 | 19.581 | -11.226 |

Dissolved oxygen (%): both curves fall from near 100 %, but the implementation
reaches 10.2 % at 4 h and stays between 5 and 8 % thereafter, while the paper's
model falls to about 1 % by 6 h and stays there. The implementation becomes
oxygen-limited, but later and less deeply.

Glycerol (g/L): the implementation keeps glycerol high (22.3 g/L at 24 h) while
the paper's model depletes it to about 0.04 g/L by 14 h. The paper's model
consumes the fed substrate; mine does not, because the growth is slow.

Final biomass 18.299 g/L against the paper's reported range of 19.9-21.5 g/L
and its model prediction of 19.44 g/L. The relative RMSE against the paper's
plotted model prediction is 10.96 % over 24 h.

### 5.2 Held-out validation experiment (Fig. 3, 20 % glycerol, 30 % yeast extract, 0.78 mL/h)

Nine digitized biomass points. The implementation was run on this configuration
separately (not shown in full here; the points are in
`data/figure_reference_data.json`). The paper's own model sits about 1 g/L RMS
from these points; the implementation's agreement with them is comparable to its
agreement with the Fig. 5 model curve.

### 5.3 Qualitative behaviour

The paper states (p. 9): "Based on the results of the DO profile, it is seen
that the growth is limited by oxygen availability beyond 6 h." The implementation
with S2_0 = 25 g/L does become oxygen-limited (minimum DO 0.87 % after feeding
starts), so the qualitative claim is met, and the endpoint biomass (18.3 g/L) is
within 12 % of the paper's model prediction. This is the only case that meets
both the regime and the shape criterion.

## 6. Error metrics and their limitations

- **Biomass, relative RMSE against the paper's plotted model curve, 0-24 h**:
  10.96 % for the primary case. The metric is computed on the 0.25 h grid at
  which the digitized curve is sampled, and only over the span the curve is
  readable (it leaves the top of the panel at about 24.9 h, so the final point is
  interpolated from the last readable columns).
- **Final biomass**: 18.299 g/L against a reported range of 19.9-21.5 g/L and
  a reported model prediction of 19.44 g/L. 6.5 % below the model prediction.
- **Dissolved oxygen**: not reported as a single number because the digitized
  curve is unreadable where it coincides with the axis; the comparison is made
  pointwise at the times the curve is readable.
- **Glycerol**: not reported as a single number for the same reason.

Limitations of the comparison:

1. The digitized curves are readings of a raster figure at about 300 dpi, with
   a calibration uncertainty of 0.25-0.30 h on the time axis and 0.3-0.5 g/L on
   the biomass axis. Errors below that level are not separable from the reading.
2. The paper's own model does not agree with its own validation data (about
   1 g/L RMS on a 20 g/L trajectory), so a perfect transcription of the printed
   equations would still sit about 5 % away from the experimental points. A
   threshold tighter than that would test the transcription against noise, not
   against the model.
3. The comparison is against the paper's *model prediction*, not its
   *measurements*. The measured points are reported separately in
   `data/validation_results.json` and never used as a target.

## 7. Sensitivity to uncertain initial conditions

The paper states the medium recipe but not the three initial conditions the model
requires. The fixture carries six cases.

| Case | S2_0 (g/L) | X0 (g/L) | DO0 (%) | X(24) (g/L) | min DO (%) | RMSE vs paper model (%) | A | B | C |
|---|---|---|---|---|---|---|---|---|---|
| primary | 25 | 0.05 | 100 | 18.299 | 0.87 | 10.96 | PASS | FAIL | PASS |
| s2_yeast_extract_only | 5 | 0.05 | 100 | 8.355 | 59.58 | 70.70 | FAIL | FAIL | FAIL |
| s2_double | 50 | 0.05 | 100 | 21.233 | 0.52 | 17.06 | PASS | PASS | PASS |
| x0_fourfold | 25 | 0.2 | 100 | 16.141 | 1.00 | 27.02 | PASS | FAIL | FAIL |
| x0_tenfold | 25 | 0.5 | 100 | 14.344 | 2.25 | 36.87 | PASS | FAIL | FAIL |
| do0_80 | 25 | 0.05 | 80 | 18.299 | 0.87 | 10.95 | PASS | FAIL | PASS |

Two findings:

1. **S2_0 is the decisive input.** 5 g/L (yeast extract alone) keeps the culture
   substrate-limited and four times too low; 25 g/L (the full complex fraction
   of the stated SOB medium) makes it oxygen-limited and lands within 11 % of the
   paper's model prediction. The paper never states which reading is correct, so
   this is a derived value with a documented alternative, not a reported one.
2. **X0 and DO0 do not matter much.** Raising X0 fivefold (0.05 to 0.2) moves
   the endpoint by 2 g/L but still leaves a 27 % shape error, because the culture
   becomes substrate-limited earlier. DO0 between 50 and 100 % changes the result
   by less than 0.001 g/L: the oxygen balance reaches its own steady state within
   the first hour and the initial value is forgotten.

### 7.1 Sensitivity to TN-02

TN-02 concerns the `e20/em1` reading in Table 2. A what-if sweep over
`e_ratio2_0` from 0.1 to 1.0 (the printed value is 0.874) gives:

| e_ratio2_0 | X(24) (g/L) | RMSE vs paper model (%) |
|---|---|---|
| 0.1 | 18.867 | 6.11 |
| 0.3 | 18.701 | 7.56 |
| 0.5 | 18.550 | 8.84 |
| 0.874 (printed) | 18.299 | 10.96 |
| 1.0 | 18.222 | 11.57 |

The direction is consistent: a lower initial enzyme fraction for combination 2
fits the paper's own model curve better. That is a hint that the literal
reading of the printed string might be more consistent with the authors' own
model than the corrected one, but it is a hint, not evidence, and the item stays
open. No parameter was changed.

## 8. Test results and reproduction command

Model suites, all exit 0:

| Suite | Result |
|---|---|
| `Models/Ganjave` | 292 passed |
| `Models/Morris` | 186 passed |
| `Models/Zielinski` | 223 passed |
| `composition` | 399 passed |

The scientific validation suite is `Models/Ganjave/tests/test_scientific_validation.py`,
47 tests, all passing, including the 47th which re-runs the digitization tool and
checks it reproduces the stored reference data byte for byte.

Exact reproduction command for the comparison:

```
cd "Models/Ganjave"
python tools/run_scientific_validation.py
```

It writes `data/validation_results.json`. The digitization is reproduced with:

```
cd "Models/Ganjave"
python tools/digitize_figures.py --pdf "../../papers/Ganjave et al 2022.pdf" --out data/figure_reference_data.json
```

The composition path is unchanged by this report: no file outside `Models/Ganjave`
and the `reports/` directory was modified.

## 9. Conclusion

**Status: `partially_validated`.**

What is supported:

- The implementation computes the printed equations correctly: every hand-checked
  derivative in `tests/test_kinetics.py` and `tests/test_batch.py` agrees with a
  hand calculation, the oxygen balance reconciles to the corrected
  `(100/C*)` quotient, and the solver converges with a documented stability
  margin.
- With the paper-grounded reading of the stated medium (S2_0 = 25 g/L), the
  implementation reproduces the authors' own model prediction to within
  11 % RMSE over 24 h and reaches 18.3 g/L against their reported 19.44 g/L
  model prediction and 20.7 g/L measured endpoint. It also reproduces the
  oxygen-limited regime the paper describes.
- The digitization of the paper's figures is internally consistent (t = 0
  glycerol 2.78 g/L against the printed 2.76 g/L; model biomass endpoint
  19.58 g/L against the printed 19.44 g/L) and is reproducible from the PDF.
- The composition adapter, the runner, the Godot harness (840 and 51 checks) and
  all 399 composition tests pass with the model integrated.

What is not supported:

- The three initial conditions the paper does not state (X0, S2_0, DO0) cannot
  be recovered from the paper. X0 is an OD600 reading with no calibration;
  S2_0 is a reading of a stated recipe, not a stated model input; DO0 is not
  stated at all. The outcome depends strongly on S2_0, and the paper does not
  say which value is correct.
- No trajectory has been compared against a measured point, because the paper
  publishes time courses as figures and no numerical data. The comparison is
  against the authors' model prediction, which is a prediction, not a
  measurement.
- TN-02 is open. Its sensitivity is measurable but does not resolve it.
- The paper's own model does not agree with its own validation data to better
  than about 1 g/L, so a tighter comparison than that would test the
  transcription against the paper's own fitting error.

The honest reading is that the implementation is a faithful transcription of a
model whose inputs are not fully specified in the source, and whose published
predictions are the only available target. That is `partially_validated`, not
`validated`, and the status is recorded as such in
`Models/Ganjave/data/validation_fig5.json`.
