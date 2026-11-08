# Data Request to the Authors

**To:** Prof. Pramod P. Wangikar (corresponding author) — `wangikar@iitb.ac.in`
**Copy:** Dr. Hardik Dodia (data curation, per the CRediT statement) — `dodia.hardik@iitb.ac.in`
*(addresses should be confirmed against the current institutional directory before sending)*
**From:** [name, affiliation, contact]
**Date:** [date of sending]
**Subject:** Request for underlying numerical time-course data — *Biotechnology Reports* 33 (2022) e00694

---

Dear Professor Wangikar,

I am re-implementing the cybernetic growth model in your paper *"High cell density
cultivation of E. coli in shake flasks for the production of recombinant proteins"*
(Biotechnology Reports 33 (2022) e00694, doi:10.1016/j.btre.2021.e00694) and comparing
our implementation against your reported results as an independent validation.

Our implementation reproduces the printed equations closely — over the span where your
Fig. 3b model curve is inside the plot frame, our trajectory sits a near-constant
0.90 ± 0.24 g DCW/L above yours, with no growth in that difference over time. Our
qualitative results (the oxygen-limited regime after feeding begins) reproduce. But we
cannot evaluate the fit numerically, because **the paper publishes time courses only as
figures** and there is no data-availability statement or repository deposit.

Your Fig. 3b is described as *"Model validation: Goodness of fit of the model with the
experimental data that was not used for estimation of model parameters."* We read it as
nine experimental markers, and the last of them — at approximately 26 h, about
15.4 g DCW/L — sits below the 24 h marker at about 18.7 g DCW/L. Read literally, the
measured biomass falls over that interval. The model has no lysis or decay term, so it
cannot do that, and your plotted curve for the same experiment leaves the top of the
axis before that point. We have treated the point as genuine rather than as a plotting
artefact, and it is the single observation that dominates our error metric.

I am not asking you to re-check your results. I am asking for the numbers, so that the
comparison can be made against measurements instead of against a rendering.

## What I am asking for

### 1. The held-out validation experiment (Table 1, row 8; Fig. 3) — highest priority

Experimental time courses for the PDGF culture run at 20 % glycerol / 30 % yeast
extract / 0.78 mL/h:

| Quantity | As plotted in Fig. 3 |
|---|---|
| Biomass (g DCW/L) | panel b |
| Dissolved oxygen (%) | panel a |
| Residual glycerol (g/L) | panel c |

Any format is fine — CSV, Excel, or a table pasted into the reply. If the data exist
only for biomass, biomass alone would resolve most of my questions.

### 2. Three specific questions about the held-out experiment

1. **The final sampling time.** Was there a sample at approximately 26 h? The protocol
   section says cultivation continued for *"10–12 h post-induction"* with induction at
   12 h, which would extend past 24 h. If the 26 h value is real, was there any
   observation-based reason for biomass to fall — for example a later harvest time than
   the endpoint reported elsewhere, or a dilution step not shown on the axis?

2. **The initial complex-substrate concentration (S2 at t = 0).** The paper states the
   medium (SOB: tryptone 20 g/L + yeast extract 5 g/L) but never states the value used
   as the model's S2 input. I have assumed 25 g/L (the whole complex fraction), with 5
   g/L as the alternative reading. This single value dominates the predicted endpoint in
   my implementation — it moves the 24 h biomass between roughly 10.6 and 20.5 g/L.
   **Which value did you use?**

3. **The initial biomass.** The paper reports an initial OD600 of 0.05 but prints no
   OD600-to-DCW calibration. What DCW did you use for X at t = 0?

### 3. Table 2 clarification, if convenient

Table 2 prints the initial enzyme ratio for combination 2 as **e20/e1m**. The
denominator of combination 2 should be e2m. We have read it as e2(0)/e2m = 0.874. A
one-line confirmation would remove an ambiguity we currently carry as unresolved.

### 4. Optional, if easily available

- The fitted model's output time courses for the six fitting experiments (Figs. 2 and
  S3–S7) and for the second validation experiment (Fig. S8). These would let us check
  the transcription across all eight runs rather than one.
- Any MATLAB implementation or fitting scripts. Reproducing your `fmincon` objective
  [eq. (17)–(18)] exactly would let us confirm the parameter values independently.

## What I am not asking for

I am not asking for the fitted parameter values again — Table 2 is complete and we use
it as printed, without refitting. And I am not asking for a change to the paper. If the
Fig. 3b marker at 26 h is a plotting artefact rather than a measurement, knowing that is
useful to me; if it is a measurement, knowing that is useful too. Either answer is
informative, and I will report whichever I get.

## Licensing

I intend to publish the recovered data, if any, in a public repository alongside a
reproduction of our comparison, under CC BY 4.0, with full citation to your paper. If you
would prefer a different licence, or would prefer that the data be cited rather than
redistributed, please say so and I will follow that.

Thank you for your time.

Yours sincerely,

[Name]
[Affiliation]
[Email]

---

## Notes for the sender

- **Attach `reports/GANJAVE_SOURCE_DATA_RECOVERY.md`** or summarise §2 of it: this request
  is only credible because the search that preceded it is documented. The recipient
  should be able to see that the supplementary file was actually retrieved and inspected,
  not assumed to be empty.
- **If no reply arrives**, the correct next step is a renewed evaluation protocol against
  whatever independent data can be obtained — not a re-run of the existing one. The
  current protocol is spent: its primary criterion failed, and reusing it with different
  data would be a silent relaxation.
