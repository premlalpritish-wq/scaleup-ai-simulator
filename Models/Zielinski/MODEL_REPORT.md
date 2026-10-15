# Model report — Zieliński et al. (2019) recombinant human insulin process

**Source.** M. Zieliński, A. Romanik-Chruścielewska, D. Mikiewicz, N. Łukasiewicz,
I. Sokołowska, J. Antosik, A. Sobolewska-Ruta, A. Bierczyńska-Krzysik, P. Zaleski,
A. Płucienniczak, *Expression and purification of recombinant human insulin from
E. coli 20 strain*, **Protein Expression and Purification 157 (2019) 63–69**,
doi:10.1016/j.pep.2019.02.002.

Page citations below use the **printed journal page** (63–69). The article PDF runs
pp. 1–7; the offset is enforced in code by `EvidenceRef.__post_init__`, so a
mismatched citation raises rather than silently pointing at the wrong page.

---

## 1. What this model is, and what it is not

This is a **validated representation of a published process and its numerical
evidence**. It is not a validated predictive simulator, and it does not pretend to be
one.

The distinction is enforced in the data model rather than in prose. Every quantity
carries a `provenance` class and a `basis`:

| provenance | basis | meaning |
|---|---|---|
| `reported` | `observed_reference` | stated in the paper, with page and source wording |
| `digitized` | `observed_reference` | read from a published figure, with declared uncertainty |
| `derived` | `computed` | produced by a registered, transparent equation |
| `assumed` | `assumed_input` | supplied by the implementer for a stated purpose |
| `unknown` | `unresolved` | not available; carries a reason, never a default |

A run reports `graph_is_predictive`. Evidence replay reports `false`, and a test
(`test_evidence_replay_produces_no_predictions`) fails if that ever changes. The
engine has two modes with a hard wall between them:

- **Evidence replay** seeds from observed values, then evaluates only equations whose
  inputs actually resolve. Reported values are never re-emitted as engine output.
- **Predictive execution** starts from caller-supplied inputs only. Reported values are
  invisible in this mode, so a replayed observation cannot masquerade as a simulation.

Running predictive mode with no inputs resolves **nothing** and reports 23 unresolved
targets. That is the correct result, not a defect.

---

## 2. Process graph

15 typed operation nodes joined by 17 directed material streams. Every stream records
its producer, its consumer and its lineage, so any intermediate traces back to the
operation that created it.

| # | Node | Operation | Fig. 1 block | Streams in → out |
|---|---|---|---|---|
| 1 | `N01` Fermentation | `FERMENTATION` | E. coli 20 cells culture | `S01_inoculum` → `S02_culture_broth` |
| 2 | `N02` Biomass harvest | `HARVEST` | (harvest step, §2.5) | `S02` → `S03_wet_biomass` |
| 3 | `N03` Cell lysis and inclusion-body isolation | `LYSIS` | Inclusion bodies isolation | `S03` → `S04_inclusion_bodies` |
| 4 | `N04` Inclusion-body dissolution | `DISSOLUTION` | Inclusion bodies dissolution | `S04` → `S05_denatured_solution` |
| 5 | `N05` Protein renaturation | `RENATURATION` | Renaturation | `S05` → `S06_renatured_precursor` |
| 6 | `N06` Citraconylation | `CHEMICAL_MODIFICATION` | Citraconylation reaction | `S06` → `S07_citraconylated` |
| 7 | `N07` Trypsinization | `PROTEOLYSIS` | Trypsinization reaction | `S07` → `S08_digested` |
| 8 | `N08` DEAE Sepharose purification | `CHROMATOGRAPHY` | DEAE Sepharose chromatography | `S08` → `S09_deae_fraction` |
| 9 | `N09` Decitraconylation | `CHEMICAL_MODIFICATION` | Decitraconylation | `S09` → `S10_citrately_blocked` |
| 10 | `N10` Zinc precipitation and zinc-salt dissolution | `PRECIPITATION` | Insulin precipitation + zinc salt dissolving | `S10` → `S11_insulin_precipitate`, `S12_dissolved_zinc_salt` |
| 11 | `N11` Q Sepharose purification | `CHROMATOGRAPHY` | Q Sepharose chromatography | `S12` → `S13_q_fraction` |
| 12 | `N12` Carboxypeptidase B treatment | `PROTEOLYSIS` | Carboxypeptidase B reaction | `S13` → `S14_cpb_treated` |
| 13 | `N13` RP-HPLC purification | `CHROMATOGRAPHY` | HPLC chromatography | `S14` → `S15_rp_hplc_fraction` |
| 14 | `N14` Sephadex G-25 buffer exchange | `CHROMATOGRAPHY` | Sephadex G-25 chromatography | `S15` → `S16_g25_fraction` |
| 15 | `N15` Final product characterization | `CHARACTERIZATION` | *(not in Fig. 1)* | `S16` → `S17_final_product` |

**Three deliberate deviations from the paper's own figure**, each recorded in the model:

- Fig. 1 has 14 boxes; the specified node list has 15. Fermentation and harvest are
  separated (harvest is described in §2.5 but has no Fig. 1 box), and final product
  characterization is added as the analytical endpoint of §3 / §4.13.
- §4.13 calls purification a "three-step procedure consisting of DEAE/Q Sepharose and
  RP-HPLC". The separately reported Sephadex G-25 operation (§2.17, §4.12) is retained
  as node 14 rather than folded into the three-step summary.
- `S11_insulin_precipitate` has no consumer: the precipitate is a storable intermediate
  (§2.12 allows 30 days at 4 °C) that is redissolved within the same node.

---

## 3. Quantitative findings

### 3.1 Fermentation reference case (D1)

All of §2.4 is encoded as reported operating conditions: 50 mL GMS inoculum, 18 h at
30 °C, Bioflo Celligen 310 7.5 L fermenter with 4 L starting medium, 37 °C, growth
15–16 h, glucose 70–120 mg/dL during initial exponential feeding and 30–50 mg/dL during
pH-stat feeding, 12 mg/mL proline feed, 16% NH₄OH pH control, OD₆₀₀ max 54.4.

Ranges are stored **as ranges** (`15–16 h`, `70–120 mg/dL`, `25–35 OD₆₀₀`, …). They are
never collapsed to a point value, because collapsing one would be an undeclared
assumption. The engine refuses any equation that would need one — `UnresolvedPointValue`
is a structured failure, not a silent substitution. Note that "room temperature" appears
as a condition note rather than as 20 °C, because the paper states no set point.

Two transparent calculations, both cross-checked against the paper's own per-litre
statements:

| Quantity | Equation | Computed | Paper's own statement | Check |
|---|---|---|---|---|
| Wet biomass per litre | `224 g / 4 L` | **56 g/L** | 56 g from 1 L (§4.2) | exact |
| Inclusion bodies per litre | `58 g / 4 L` | **14.5 g/L** | 14.5 g from 1 L (§4.3) | exact |
| Inclusion bodies as fraction of wet biomass | `58 / 224` | 0.2589 | — | descriptive only |

The agreement is exact, which is a useful independent confirmation that the two
statements in §4.2 and §4.3 are consistent with the 4 L culture volume.

**No kinetics.** There is no Monod model, no biomass differential equation, no
oxygen-transfer model and no substrate-uptake model. The paper reports no μmax, no Ks,
no maintenance coefficient, no air flow, no agitation rate and no dissolved-oxygen trace.
Fitting a curve through the single published batch would be a fitted mechanistic model
rather than a sourced one, so it is not done.

### 3.2 Figure 3 growth trajectory (digitized, replay only)

Figure 3 was digitized from the embedded raster rather than estimated by eye:
gridline calibration, colour isolation, and a vertical-thickness profile to separate the
~14 px circular markers from the ~5–8 px line. All 19 recovered markers land within
0.07 h of integer hours, and the gridlines align with the printed axis labels — a strong
independent check on the calibration. Declared uncertainty: **±0.1 h, ±0.5 OD₆₀₀**
(dominated by centroid bias on steep segments and JPEG compression).

| t (h) | 1–6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17–19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OD₆₀₀ | ~0.37 | 0.73 | 1.47 | 2.57 | 4.79 | 7.41 | 13.88 | 24.39 | 33.82 | 43.16 | 52.20 | ~53.67 |

This is a **replay of one published batch**. No kinetic parameter is derived from it and
it is never used to predict another batch. Machine-readable copy with full method
description: `models/data/fig3_growth_trajectory.json`.

### 3.3 Dissolution and refolding (D2)

Reported: 12 mM NaHCO₃, 0.2 mM EDTA, pH ≈ 11.9 then 10.8, 45 min, 17.9 g inclusion-body
aliquot → 5460 AU; refolding 18 h (methods) / 18–19 h (results); room-temperature yield
95–96%, yield at 7–8 °C ~99%; 5450 AU after refolding.

The two reported yields are stored as **measured reference values, not a yield
function**. No function of temperature is fitted. This matters because §4.5 itself states
that refolding *"was shown to depend on the redox potential and the pH value, but not on
the temperature"* — which contradicts reading temperature as the causal predictor.

### 3.4 Downstream operations (D3)

The paper's formulas are preserved verbatim with their original variable definitions and
units. Each is marked executable or not:

| Formula (§) | Text | Status |
|---|---|---|
| ZnCl₂ dose (2.12) | `2 × V cm3 solution/100` | **executed** |
| Aprotinin (2.9) | `V trypsin/21` | **executed** |
| EDTA (2.13) | `total protein after DEAE/190` | **executed** |
| Water for Zn-salt dissolution (2.13) | `total protein after DEAE/7` | **executed** |
| CPB dose (2.15) | `10 µl for every 150 AU` | **executed** |
| Citraconic anhydride (2.8) | `0.2 × V solution (dm3) × A280 nm` | **refused** — A280 is a raw absorbance with no stated path length, and `0.2 × dm³ × absorbance` does not reduce to a volume |
| Trypsin (2.9) | `A280 nm × V solution (dm3)/75` | **refused** — same ambiguity; divisor 75 carries no unit |
| Ethanolamine (2.8) | `3 × V citraconic anhydride` | **refused** — blocked upstream by the anhydride formula |

The three refused formulas surface as explicit unresolved targets
(`N06:citraconic_anhydride_volume`, `N06:ethanolamine_volume`, `N07:trypsin_volume`).
The paper's *absolute* figures for those steps (1 mL anhydride, 3 mL ethanolamine,
70 µL trypsin) are recorded as reported conditions alongside them.

**Stage absorbance accounting.** Total AU is computed as volume × concentration only:

| Stage | Volume | Concentration | Total AU | Provenance |
|---|---|---|---|---|
| DEAE Sepharose | 250 mL | 8.57 AU/mL | **2142.50 AU** | derived from §4.7 |
| Q Sepharose | 226 mL | 2.77 AU/mL | **626.02 AU** | derived from §4.10 |
| RP-HPLC | 97 mL | 2.42 AU/mL | **234.74 AU** | derived from §4.11 |
| Sephadex G-25 | 31 mL | 3.59 AU/mL | **111.29 AU** | derived from §4.12 |

**AU is never equated with mass, molarity, IU or insulin content.** §2.18 states the
spectrophotometer was calibrated *with water*: no path length, no extinction coefficient.
The AU scale is therefore instrument-relative. Every AU quantity in the model carries an
explicit caveat, and the unit registry has no conversion from AU to grams, IU or molar
concentration — `is_convertible("AU", "g")` is `False` by construction, not by convention.

Consequently **no per-stage recovery efficiency is reported**. An AU ratio between stages
is not a recovery: the protein composition changes, and the AU basis differs between
"total protein at 280 nm" and the insulin-containing fraction. This is recorded as an
unresolved dependency rather than filled in.

### 3.5 Final product (D4)

| Quantity | Value | Provenance |
|---|---|---|
| Average activity | 2700 IU per litre of culture medium | reported (§4.13, §5) |
| Purity | up to ~99% | reported (Fig. 7 caption) |
| UHPLC retention time | 3.748 min | reported (Fig. 7 caption) |
| Measured molecular mass (ESI-MS) | 5807.5 Da (±0.05, from stated precision) | reported (§4.13, Fig. 8) |
| Theoretical average mass | 5807.63 Da (±0.005, from stated precision) | reported (§4.13) |
| Deviation | −0.13 Da ± 0.055 | **derived**, uncertainty propagated |
| Relative deviation | −22.4 ppm | **derived** |

**No statistical claim is made about the −0.13 Da deviation.** The measured mass is
printed to ±0.05 Da and the theoretical value to ±0.005 Da, giving a
reporting-precision interval of ±0.055 Da, which the engine propagates onto the derived
deviation. The paper reports no replicates, no standard and no error bars, so this is an
arithmetic difference, not a test — and the model states that explicitly rather than
implying agreement or disagreement. `AT-017` enforces this: a mutation that inserts the
word "statistically significant" into the message fails the suite.

These are **reference outcomes, not predictions**. The engine has no equation that
produces any of them, and a predictive query for final activity or insulin mass fails
closed with the missing model named.

---

## 4. Contradictions in the source

These are reported, quantified and **left unresolved**. Resolving any of them silently
would be a modelling decision the paper does not support.

### 4.1 Zinc-salt dissolution volume — formula vs reported value

§2.13 specifies the water volume as post-DEAE protein ÷ 7. With the reported post-DEAE
protein of 2142.5 AU that is **306.07 mL**. §4.9 reports **285 mL** of water — 7.4% lower.

The same paragraph reports 9.2 mL of 1 M Tris to reach 30 mM, which implies a total
volume of **306.7 mL**. That matches the formula and not the 285 mL figure. On the
reported 285 mL path the achieved Tris concentration is 31.27 mM against a 30 mM target.

The `/7` and `/190` formulas are therefore not independent: `/190` reproduces the reported
11.3 mL of EDTA almost exactly (11.28 mL), so the same post-DEAE AU figure is consistent
with one formula and not the other.

### 4.2 Carboxypeptidase B dose

§2.15 states 10 µl per 150 AU of main-fraction protein. The main fraction (§4.10) is
226 mL at 2.77 AU/mL = 626.02 AU, which implies **41.73 µl**. §2.15 states **50 µl** was
added — 20% more. The paper does not say whether the dose was rounded up or derived from
a different batch.

### 4.3 Refolding yield vs AU balance

§4.4 reports 5460 AU after dissolution; §4.5 reports 5450 AU after renaturation, an
implied **99.82%**. The same section states a room-temperature yield of 95–96%, which
would imply only 5187–5242 AU. Both statements are retained; neither is adjusted, and the
model does not guess which basis each figure uses.

### 4.4 Induction order

§2.4 describes glucose starvation at OD₆₀₀ 25–35, then pH-stat feeding, then induction
followed by 4–5 h to OD₆₀₀ 50–60. The digitized Fig. 3 curve crosses OD₆₀₀ 25 at ~13.1 h
and OD₆₀₀ 50 at ~15.7 h. A 4–5 h post-induction phase ending at 15.7 h places induction
at **10.7–11.7 h — before the glucose limitation**, inverting the described sequence.
The induction time is never stated and cannot be recovered from the figure.

### 4.5 Fermentation duration is ambiguous

§2.4 reports "Cells were grown for 15–16 h at 37 °C" *and* "After induction, the
culture was grown for 4–5 h until OD₆₀₀ nm was about 50–60". Whether 15–16 h is the
total batch duration or the pre-induction duration is not stated, and the readings differ
by 4–5 h. The digitized Fig. 3 axis ends at 19 h, which is consistent with a ~19–21 h
total under the second reading but does not settle it. Both durations are stored as
reported intervals; neither is adjusted.

### 4.6 Refolding duration: methods vs results

§2.7 says the precursor was "allowed to fold during the subsequent 18 h period";
§4.5 says "The refolding process was completed after 18–19 h". The exact 18 h from the
methods and the 18–19 h interval from the results are stored separately, and no
refolding rate is derived from either.

### 4.7 Digitized plateau vs reported maximum

The digitized Fig. 3 plateau is ~53.67 OD₆₀₀; §4.2 reports a maximum of 54.4. The 0.73
difference is slightly outside the declared ±0.5 digitization uncertainty. Both values
are retained.

---

## 5. What the model deliberately does not compute

Eight models are declared absent, each with the inputs it would need. A predictive query
for any dependent quantity fails closed and names them.

| Declared model | Would enable | Missing inputs |
|---|---|---|
| `kinetics.growth_ode` | OD₆₀₀ / biomass prediction | μmax, Ks, maintenance coefficient, O₂ limitation onset |
| `kinetics.monod_substrate` | glucose uptake, feed volume | Ks, Yx/s, pump rate, pH-stat response |
| `transfer.oxygen_kla` | dissolved-oxygen profile | kLa, air flow, agitation, vvm, DO trace |
| `folding.renaturation_kinetics` | refolding yield/time prediction | rate constant, redox potential, equilibrium, aggregate fraction |
| `calibration.au_to_mass` | AU → grams | ε₂₈₀, path length, protein-specific A280 factor |
| `recovery.stage_yield` | per-stage recovery | AU→mass calibration, stage composition, selectivity |
| `activity.iu_from_au` | activity from absorbance | AU→mass calibration, specific activity, assay calibration |
| `scaleup.effect_of_scale` | scale-up correlation | kLa at scale, pH-stat response, feed profile, shear |

Also absent, by rule: invented reaction kinetics, mechanistic folding simulation, CFD /
mixing / oxygen-transfer / heat-transfer simulation, unvalidated scale-up predictions,
invented purification recoveries, and any inference of insulin mass or final IU from AU.

Two quantities are recorded as `unknown` with an explicit reason even though they might
look computable:

- **`dissolved_protein_concentration`** — §2.6 gives the buffer composition but no volume,
  and §4.4 reports 5460 AU without a concentration.
- **`induction_time`** — never stated.

---

## 6. Acceptance

223 tests pass (`python -m pytest tests -q`). `tests/test_acceptance_criteria.py`
implements AT-001 … AT-026 against the acceptance specification, each criterion
mapped to a named test class via an explicit `AT_COVERAGE` table that the suite
checks for completeness.

### The acceptance tests were verified by mutation

A test that cannot fail proves nothing. Each acceptance criterion was checked by
breaking the model deliberately and confirming the suite catches it. All 13 effective
mutations were caught:

| Mutation | Caught by |
|---|---|
| evidence replay reports predictions | AT-006 |
| `unknown` quantities may carry a value | AT-005 |
| reported range silently collapsed to its midpoint | AT-007 |
| scale-up refusal removed entirely (regex + keywords + capability map) | AT-019 |
| AU redefined as mass-interchangeable | AT-020 |
| digitized points relabelled as reported measurements | AT-021 |
| digitized uncertainty removed | AT-021 |
| **285 mL water volume silently changed to match the formula** | AT-007 |
| **50 µL CPB dose silently changed to match the formula** | AT-007 |
| discrepancy warning renamed to a remark | AT-007 |
| refolding duration claim deleted | AT-007 |
| significance language inserted into a message | AT-017 |
| propagated uncertainty removed / mass-deviation sign flipped / stage AU rescaled / dimension check disabled | AT-017, AT-012, AT-020 |

The two mutations marked in bold exposed a **real gap**: nothing in the acceptance suite
originally pinned the *reported* source values, so a contradiction could have been
"resolved" by quietly editing 285 mL to 306.07 mL and every arithmetic check would still
have passed. `TestAT007ConflictingEvidencePreserved.PINNED_REPORTED` now pins the values
the paper actually states, so the conflict cannot be edited away.

### Citation fidelity is mechanically verified, not trusted

`tests/test_paper_fidelity.py` checks the model's citations against text extracted from
the article PDF (`models/data/paper_pages.json`, regenerable with
`models.source.rebuild_paper_pages()`):

Every reported scalar, range endpoint, formula number, formula subject reagent and
`original_text` quote is checked against text extracted from the article PDF
(`models/data/paper_pages.json`, regenerable via `models.source.rebuild_paper_pages()`):

- **131 reported scalar values** — every one is found verbatim on the page it cites.
- **Every reported range** — both endpoints found on the cited page.
- **Every preserved formula** — every number in it, and its subject reagent, is found on
  the cited page.
- **Every `original_text` quote** — checked token-wise against the article, tolerating
  only the typography differences the PDF extraction introduces (thousands separators,
  subscript spacing, `×` vs `x`).

So a citation cannot silently drift onto the wrong page or invent a number without a
test failing.

### Serialization round trip

`scaleup_ai/serialize.py` reconstructs live objects from the JSON payloads — graph,
quantities, evidence, provenance, source expressions, assumptions, missing parameters,
validation messages, run results and unresolved fields. `AT-025` verifies the graph and
run survive a round trip field-for-field, and that a **rehydrated graph can rebuild the
engine and reproduce the identical replay** — the strongest form of the check.

The record's declared equation registry and missing-model list are rebuilt from the live
registries on load rather than trusted from the file, so a tampered record cannot claim
an equation exists when it does not, and a serialized `basis` that contradicts its
`provenance` is rejected.

### Structural integrity is tested, not assumed

- `Quantity(provenance=UNKNOWN, value=0.0)` **raises** — unknown values cannot be filled in.
- A `value` and a `value_range` are mutually exclusive; a reported range is never collapsed.
- A numeric quantity without a unit raises; an unregistered unit raises.
- pH is never linearly convertible.
- Every registered executable equation is evaluated against its own declared input keys,
  which catches an equation whose arithmetic disagrees with its signature.
- Graph cycles are detected (Kahn's algorithm), duplicate ids and dangling streams are rejected.
- Repeated runs produce byte-identical artifacts.

Three integrity defects were found and fixed during implementation rather than being
left in place:

- a fabricated `0 %` isopropanol for the DEAE wash buffer — the paper simply does not
  state one, and absence is not zero;
- numeric "room temperature" values substituted for a set point the paper never gives;
- `topological_order` treated a node consuming a stream it also produced as dependency-
  free, so a genuine cycle was silently accepted rather than raising. Replaced with a
  correct Kahn's algorithm.

All three now appear as condition notes, absences, or a real cycle check.

Two further defects surfaced while implementing the acceptance tests: `ExecutionEngine`
defaulted `predictive_capabilities`/`keyword_models` to an empty **tuple** while calling
`.items()` on them, so any engine constructed without those keyword arguments crashed;
and `ProcessNode` had no `get`/`require` accessors that `MaterialStream` already had.

---

## 7. Layout and usage

```
scaleup_ai/            canonical core, paper-agnostic
  units.py             dimension-checked unit registry
  provenance.py        EvidenceRef / Quantity / Assumption / MissingParameter
  process.py           ProcessNode / MaterialStream / ProcessGraph
  equations.py         executable equation registry + declared missing models
  engine.py            deterministic evaluator, two modes, fails closed
  serialize.py         JSON round trip (graph, quantities, runs, records)
  report.py            JSON / CSV / Markdown serialization
models/
  source.py            citation, PDF→printed page mapping, evidence helper
  zielinski_2019.py    the process model: nodes, streams, quantities, wiring
  data/                digitized Fig. 3 trajectory + extracted article text
tests/                 223 tests, including AT-001..AT-026
out/                   generated artifacts
run_model.py           CLI
```

```bash
python run_model.py                    # build, run both modes, write out/
python -m pytest tests -q              # 223 passed
```

Artifacts written to `out/`:

| File | Contents |
|---|---|
| `graph.json` | the process definition |
| `evidence_record.json` | graph + equation registry + declared missing models + both runs + interpretation note |
| `quantities.csv` | one row per declared quantity with full provenance, page, method, uncertainty |
| `computed.csv` | one row per computed value with equation and expanded inputs |
| `run_summary.md` | generated digest |

`scaleup_ai` is intended as the shared ScaleUp AI core. It is model-agnostic by
construction — no Zieliński-specific type is defined in it — so it can be hoisted to a
shared location when further models land without creating a parallel representation.