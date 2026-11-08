# Ganjave et al. (2022) — Source Data Recovery

**Outcome: the numerical time courses behind Figures 3a and 3b are not published and were
not recovered.** The publisher's complete supplementary package was obtained and
inspected; it contains no time-course data, no spreadsheet, and no cached chart values.
A documented request to the authors is prepared.

**No dataset was fabricated from the existing figure.** The frozen evaluation is
unchanged and still reproduces.

Machine-readable: [`data/ganjave2022/source_data/`](../data/ganjave2022/source_data) —
`search_log.json`, `recovered_numerical_data.json`, `supplementary_inventory.json`,
`supplementary_charts.json`.

---

## 1. Frozen evaluation preserved

Verified before and after the search. All five inputs unchanged; the primary result is
bit-identical.

| Input | SHA-256 | Status |
|---|---|---|
| `frozen_configuration.json` | `23c585ee06579ab7…` | unchanged |
| `observations.json` | `48141f2947428f3a…` | unchanged |
| `evaluation_protocol.json` | `d528e214e48becd9…` | unchanged |
| `figure_reference_data.json` | `46eb120f9553bdd6…` | unchanged |
| `reference_parameters.json` | `3f53c1fdc82449c2…` | unchanged |

`heldout_fig3` primary outcome **fail**, RMSE **2.5204** — unchanged.

Recovered material is stored **separately** under `data/ganjave2022/source_data/`. The
frozen evaluation dataset was not modified, extended, or relabelled.

---

## 2. Search performed

Eleven steps, recorded in full in `search_log.json`. Summary:

| # | Action | Source | Result |
|---|---|---|---|
| 1 | Data-availability statement, repository names | Article PDF text layer, 10 pages | **Absent.** No statement; no repository named |
| 2 | Enumerate publisher supplementary files | PMC article page, "Appendix. Supplementary materials" | Exactly one: `mmc1.docx` |
| 3 | Retrieve `mmc1.docx` | Europe PMC REST `…/PMC8718739/supplementaryFiles` | **Retrieved**, 3,071,054-byte ZIP |
| 4 | Inspect every OOXML part | ZIP structure | **No** `.xlsx/.csv/.txt/.dat`. 3 tables, 11 images, 2 charts |
| 5 | Extract native OOXML charts | `word/charts/chart1–2.xml` | Both are **kLa plots**, both have **0 cached points** |
| 6 | Dump all Word tables | `word/document.xml` | S1 protein IDs, S3 optimisation bounds, **S4 kLa (24 values)** |
| 7 | List supplementary figures | — | S1–S10 as images; **Fig. 3 is main-text only** |
| 8 | Compare main-text Fig. 3 resolution | `gr3.jpg` vs PDF-embedded | PMC copy is **750×512**, *worse* than the 1400×990/1800×1230 already used |
| 9 | Europe PMC metadata for dataset links | REST `search?resultType=core` | `supplementaryLinks` **empty**; no dataset URL |
| 10 | Publisher pages directly | ScienceDirect, Elsevier API | Connection closed / HTTP 429 — **access limitation, not evidence** |
| 11 | Repository search by DOI and author | Web search | No Zenodo / figshare / GitHub / Mendeley / Dryad; lab pages carry a bare DOI |

**Access note.** The PMC direct link
(`/articles/instance/8718739/bin/mmc1.docx`) serves a JavaScript interstitial gated by a
secure cookie and cannot be fetched non-interactively. Europe PMC's REST endpoint served
the same content directly. Step 10 failed for network reasons; step 1 already established
the absence from the article text itself, so step 10 is a limitation, not a gap in the
evidence.

---

## 3. What the supplementary actually contains

From `supplementary_inventory.json` — 44 paragraphs, 3 tables, 11 images, 2 charts:

| Item | Content | Numerical? |
|---|---|---|
| Table S1 | Protein UniProt IDs, plasmid backbones | No |
| Table S3 | Optimisation bounds: glycerol 15–30 g/L, complex substrate 15–40 g/L, flow 0.4–0.9 mL/h | Ranges only |
| **Table S4** | **kLa measurements: 14 rows, 24 values** | **Yes — recovered** |
| Figures S1–S10 | Images. S3–S7 fitting experiments, S8 second validation | No |
| chart1, chart2 | kLa determination, `ln(C*/C*-C)` vs time | **0 cached points** |

The two native charts were the most promising lead: a Word chart stores the numbers it
plots in `<c:numCache>`, so a time course plotted there would have been recoverable
verbatim. Both turned out to be kLa determination plots with no cached values.

---

## 4. What was recovered

**Table S4 — 24 kLa measurements**, author-reported, not digitised, in
`recovered_numerical_data.json`.

Two transformations, both recorded on every row:

1. **Merged-cell forward fill.** Word vertical merges leave volume and RPM blank on
   continuation rows. Blanks mean *"same as above"*, not *missing*. Each record carries
   `volume_forward_filled` / `rpm_forward_filled`.
2. **Column grouping.** Left block = 2.5 cm pitch, right block = 5 cm pitch, per the
   caption.

No smoothing, conversion, averaging or imputation.

### It independently confirms a model input

| Volume | RPM | Pitch | kLa |
|---|---|---|---|
| 100 mL | 200 | 5 cm | **133.0 h⁻¹** |

This is exactly the value the frozen configuration uses, and exactly the value the
article states (p. 3, Table S2). **Recovered source data confirms a model parameter.**
That is the one open question the recovery touches, and it touches it in the direction of
*more* confidence, not less.

### What it is not

Table S4 is not a time course. It says nothing about biomass or dissolved oxygen and does
not bear on the held-out failure.

---

## 5. Which open questions are resolved

From `reports/GANJAVE_FAILURE_INVESTIGATION.md` §9:

| # | Question | Status after this recovery |
|---|---|---|
| 1 | The biomass decline (18.71 → 15.37 g/L) | **Unresolved.** No source data; the figure is the only record |
| 2 | The ~0.9 g/L offset from the paper's curve | **Unresolved.** No model output time course obtained |
| 3 | What S2₀ the authors used | **Unresolved.** Asked directly in the data request |
| 4 | TN-02 `e20/em1` denominator | **Unresolved.** Asked in the data request |
| 5 | No DO data | **Unresolved.** Fig. 3a still has no usable observations |
| 6 | The eight fitting experiments | **Partially addressed.** Their figures exist (S3–S7, S8) but carry no numbers |

**Zero of the six open questions were resolved by source data.** One new piece of
evidence was obtained, and it concerns a parameter rather than the discrepancy.

---

## 6. Does any new comparison change the interpretation of the failure?

**No.** And this is worth stating precisely, because it is the outcome the task warned
against manufacturing.

- The comparison the recovery would have improved — digitized observations against
  predictions — is exactly the one now unobtainable. No new comparison was possible.
- The one numerical fact recovered, kLa = 133 h⁻¹ at the evaluated configuration, is a
  model input the frozen configuration already used. Nothing changed.
- The highest-resolution Figure 3 available is the PDF-embedded image the digitisation
  **already used**; PMC's copy is smaller. Re-digitising would degrade it.

**The frozen evaluation still fails criteria E and I.** No comparison changed its
interpretation because no new data existed to compare. The investigation's conclusion
stands unchanged: the paper's own model curve disagrees with the held-out measurements
at the same two points, and this implementation faithfully inherits that disagreement
while sitting ~0.9 g/L above the published curve.

---

## 7. Data identity, had it been recovered

Recorded now as the standard that would have been applied, so that a future recovery is
not accepted on looser terms:

| Field | Requirement |
|---|---|
| Data class | `author_reported_measurement` — **never** `digitized` |
| Figure / panel | Recorded, with the paper's own figure numbering |
| Series identity | PDGF, held-out validation experiment, Table 1 row 8 |
| Time and quantity | Verbatim; units as the authors state them |
| Replicate status | Recorded if documented; **not inferred** |
| Uncertainty | Recorded if documented; **not invented** |
| Experimental vs model | Kept in separate collections, as the existing dataset does |
| Provenance | URL, retrieval date, file hash, licence |

A recovered dataset would be **versioned separately** and given its own protocol. It
would not be merged into `observations.json`: that file is the figure-digitised dataset
the frozen evaluation used, and changing its contents would invalidate the failure that
has been investigated.

---

## 8. Files

Recovered originals, stored unmodified:

| File | Bytes | SHA-256 |
|---|---|---|
| `PMC8718739_supplementary.zip` | 3,071,054 | `f50c75b00f2dbcfeb…` |
| `mmc1_supplementary.docx` | 2,192,379 | `2b24a4fd43bf4e94…` |
| `gr3_maintext_fig3.jpg` | 99,174 | `ff45d6279d75ea4e…` |
| `chart1.xml` | 5,554 | `e0b6a21f3b95c0ee…` |
| `chart2.xml` | 6,195 | `420751868610b2c3…` |

**Licensing.** The article is **CC BY-NC-ND 4.0**. The publisher's file is stored
unmodified with attribution; no derivative of it is redistributed. The derived records
restate numbers from it for analysis. Anyone redistributing these files must preserve
that licence and its NoDerivatives term.

Derived, machine-readable:

| File | Contents |
|---|---|
| `search_log.json` | All 11 search steps with sources and outcomes |
| `supplementary_inventory.json` | Every paragraph, table and image in `mmc1.docx` |
| `supplementary_charts.json` | The two OOXML charts, with their zero cached points |
| `recovered_numerical_data.json` | Normalised Table S4, with per-row transformation flags |
| `PROVENANCE.md` | Source-to-dataset chain and integrity hashes |

---

## 9. Tests and regression

**New:** `composition/tests/test_source_data_recovery.py` — **33 tests**, covering data
identity, provenance and processing. They assert, among other things:

- Every recovered file still hashes to what was examined.
- The supplementary contains **no** data file and the charts carry **zero** cached
  points — so the negative result stays on the record and is re-examined if it changes.
- Every recovered record is `author_reported_measurement` with `digitized: false` and
  `reading_uncertainty: null`.
- **No digitised observation from the frozen dataset appears anywhere in the recovered
  record** — the structural guard against figure readings being relabelled as source data.
- The frozen dataset still declares itself digitised.
- Each transformation is flagged per record; the merged-cell handling is not inert; the
  normaliser is idempotent.
- The kLa confirmation matches the frozen configuration's solver justification.
- All five frozen inputs still match their digests, and the primary result is unchanged
  at `fail` / RMSE 2.5204.
- The author request exists, names the corresponding author, asks for the specific
  series and open questions, states a licensing intention, and **does not ask the
  authors to change their paper**.

Two of these tests caught real gaps in my own records while being written — a search step
and a normalisation entry that named no source. Both were fixed rather than the tests
relaxed.

**Regression — all at baseline:**

| Suite | Baseline | Now |
|---|---|---|
| Composition | 583 | **616** (+33) |
| `contract_boundary.gd` | 840 | **840** |
| `ganjave_graph_run.gd` | 51 | **51** |
| `palette_graph_run.gd` | 220 | **220** |
| Morris | 186 | **186** |
| Zieliński | 223 | **223** |
| Baez | 193 passed / 2 failed | **193 passed / 2 failed** |

The two Baez failures remain the known pre-existing stale counts in
`Models/Baez/tests/test_exclusions.py`, unrelated and untouched.

No model equation, parameter or validation status was changed.

---

## 10. Deliverables and next step

| Deliverable | Status |
|---|---|
| `reports/GANJAVE_SOURCE_DATA_RECOVERY.md` | This document |
| `reports/GANJAVE_AUTHOR_DATA_REQUEST.md` | Prepared and ready to send |
| Original recovered files | Stored unmodified, CC BY-NC-ND noted |
| Machine-readable normalised dataset | Table S4 only — **no time course obtained** |
| Source-to-dataset provenance and hashes | `PROVENANCE.md` + `search_log.json` + the JSON records |
| Automated tests | `composition/tests/test_source_data_recovery.py`, 33 tests |
| Frozen evaluation reproducible and unchanged | Verified by digest, before and after |

**Next step:** send the data request. It asks for four things — the Fig. 3 time courses,
the value of S2 at t = 0, the initial DCW, and a one-line confirmation of the Table 2
enzyme-ratio denominator — with a stated licence intention and an explicit statement that
no re-analysis of the paper is being requested.

If the data arrive, they get their own dataset, their own protocol, and their own report.
The current protocol is spent and must not be reused.
