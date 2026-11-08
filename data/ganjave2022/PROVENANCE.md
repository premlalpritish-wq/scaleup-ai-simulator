# Provenance: `data/ganjave2022/`

Where every evaluation number came from, and what had to be believed to get there.

## The chain

```
papers/Ganjave et al 2022.pdf                (not distributed; other authors' work)
        |  Models/Ganjave/tools/digitize_figures.py
        v
Models/Ganjave/data/figure_reference_data.json     raster figures -> calibrated marks
        |  composition/tools/build_evaluation_dataset.py
        v
data/ganjave2022/observations.json                 49 observations, paper figure numbers
        |  composition/tools/evaluate_heldout_biomass.py
        |    via: python -m composition.runner     (the normal pipeline)
        v
data/ganjave2022/results/evaluation_results.json  predictions, residuals, verdicts
```

Each arrow is a committed, re-runnable script. `test_the_builder_reproduces_the_committed_file`
asserts the middle arrow is byte-for-byte reproducible; `test_every_digest_still_matches`
pins the inputs the last arrow consumed.

## Source

| | |
|---|---|
| Citation | S. D. Ganjave, H. Dodia, A. V. Sunder, S. Madhu, P. P. Wangikar, *High cell density cultivation of E. coli in shake flasks for the production of recombinant proteins*, Biotechnology Reports 33 (2022) e00694 |
| DOI | 10.1016/j.btre.2021.e00694 |
| PDF | `papers/Ganjave et al 2022.pdf` — **not distributed** (`.gitignore`; it is another author's publication) |

The citation is verifiable without the PDF: `figure_reference_data.json` carries each
figure's printed caption and feed recipe, and `validation_fig5.json` carries printed
quotes with page locators. `build_evaluation_dataset.py` asserts against those, so the
mapping breaks loudly rather than silently.

## Figure numbering: a defect found and corrected

| `figure_reference_data.json` key | Paper figure | How it was established |
|---|---|---|
| `"5"` | **Fig. 3** | Caption: *"Model validation: Goodness of fit of the model with the experimental data that was not used for estimation of model parameters."* Feed 20 % / 30 % / 0.78 mL/h, matching the Fig. 3 caption verbatim. |
| `"6"` | **Fig. 5** | Caption: *"Model prediction for the optimised feeding strategy, with five proteins cultivated in the same run."* Feed 17.5 % / 24.5 % / 0.72 mL/h, matching the Fig. 5 caption verbatim. Panel (b) plots pH and draws no model curve — the model has no pH term. |

The upstream keys do **not** match the paper's figure numbers. Anyone checking a
traceable citation against the PDF would have looked up the wrong figure.
`observations.json` carries `paper_figure` on every point, and the builder fails if the
mapping's caption or feed no longer agrees.

## What is in `observations.json`

| Set | Paper | n | Cultures | Quantity | Uncertainty |
|---|---|---|---|---|---|
| `fig3b` | Fig. 3b, p. 6 | 9 | PDGF | biomass, g/L DCW | 0.7125 |
| `fig3c` | Fig. 3c, p. 6 | 5 | PDGF | glycerol, g/L | 0.7125 |
| `fig5c` | Fig. 5c, p. 7 | 35 | 5 proteins | biomass, g/L DCW | ≈0.85 |

Per point: `t_h`, `value`, `combined_uncertainty`, `reading_uncertainty`,
`calibration_uncertainty`, `culture`, `kind`, `digitized`, `tabulated`, `trace`.

Uncertainty is `reading + calibration`, the digitisation's own convention
(0.2773 + 0.4352 = 0.7125 g/L), matching `Models/Ganjave/data/validation_results.json`
so the two artefact sets are not silently reporting different intervals.

## Observations are not predictions, and the file says so

- Every point carries `kind: "experimental_observation"`, `digitized: true`,
  `tabulated: false`.
- The authors' model curve lives in `model_predictions[]` with `is_measurement: false`.
- `test_the_authors_model_curve_is_not_in_any_point_list` asserts the string
  `Model_predicted` never appears inside `observation_sets`.

**Why this matters concretely:** the `Model_predicted` series carries one or two
`marks` — but they are curve pixels, not data points, with reading uncertainties of
10.8 and 2.69 g/L against a trajectory spanning 20 g/L. Reading them as measurements
would invent data with worse-than-useless precision.
`test_the_curve_pixels_would_be_absurd_as_measurements` asserts that absurdity still
holds, so if a future digitisation fixes it, the split gets revisited rather than
silently invalidated.

## What was excluded, and why

**Paper Fig. 2** (printed p. 5; 30 % glycerol, 40 % yeast extract, 0.52 mL/h) is the
**fitting** experiment: the caption reads "Model fitting", and Table 2's parameters were
estimated from it. Comparing against it is circular. It is recorded in
`excluded.fitting_experiment` so its absence is a decision on the record.

## Known limitations of the reference data

1. **Raster readings, not measurements.** The paper publishes no numerical time courses.
   Every point is a marker centre recovered from a figure, with its own uncertainty.
2. **One mark is demonstrably wrong.** `fig3b:PDGF:8` at t = 26.080 h reads
   15.369 g/L, *below* the 18.714 g/L read 2 h earlier. The model has no lysis or decay
   term, so biomass is monotonic by construction, and the digitised curve for the same
   culture does not decline either. Identified before the run; its handling is
   pre-declared in the protocol and reported both ways. **It is not deleted.**
3. **No replicate error bars.** The paper reports none for these series, so none is
   claimed. `fig5c`'s five cultures give an experimental spread, which is used as
   context rather than as a per-point uncertainty.
4. **The initial-origin mark** (`t = −0.057 h`, −0.081 g/L) is excluded by the comparison
   window `[0, duration]`, not by hand; its value is consistent with zero within
   uncertainty.

## Configuration and protocol

| File | Role |
|---|---|
| `frozen_configuration.json` | Model, versions, parameters, solver, initial conditions with classifications, feed recipes, unit conversions, duration. Records the blinding disclosure. |
| `evaluation_protocol.json` | Metrics, thresholds with justifications, decision rule, sensitivity cases, pre-declared anomaly handling. Written before the primary scenario was run. |

`results/evaluation_results.json` records a SHA-256 of the configuration, the dataset,
the protocol, the digitisation and `reference_parameters.json`. Change any of them and
`test_every_digest_still_matches` fails, so a result can never outlive its inputs.

## Regenerating

```powershell
python composition/tools/build_evaluation_dataset.py   # dataset
python composition/tools/evaluate_heldout_biomass.py    # predictions + verdicts
```

The per-run graph and result documents under `results/runs/` are gitignored: ~200 MB of
dense solver trajectories, fully regenerable from the two commands above.
