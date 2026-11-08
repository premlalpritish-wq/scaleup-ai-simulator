# Paper → model coverage audit

Date: 2026-10-29. Project: `D:\Godot\Scaleup AI\pilot`.

## 1. Scope and method

Every PDF under `Models/` was inspected: **15 author folders, 15 papers**. Page text was
extracted with `pymupdf` (`Model/…/*.pdf` → text) and each paper's organism, strain,
construct, medium, mode, scale and reported quantities were read from its own text. Nothing
below is inferred from a title or an abstract line alone; where a number is quoted it is the
paper's own.

Each paper was then asked three questions, in this order:

1. **Is it already encoded?** Does a model package exist for it, and is that package
   registered in the composition layer (`composition/composition/adapters/__init__.py`)?
2. **Could it support a defensible model?** Does it report quantities for a process whose
   organism/strain/construct/medium/mode/scale can be stated, with the values traceable to
   passages?
3. **Could that model run in the insulin simulation?** The engine's rule, applied unchanged:
   port quantities must be dimensionally *and semantically* compatible, and the
   organism/strain/process context must match. A matching unit is necessary and never
   sufficient.

The target process throughout is `zielinski2019.rhi_process@1.0.0`: *E. coli* 20 IBA 1
(`F- lambda-ara Δ(pro lac) rpsL thi recA cytR`, a CSH50R derivative), plasmid pIBAINS,
GMS medium, 4 L working volume in a 7.5 L Bioflo Celligen 310, batch with pH-stat glucose
feeding, 30 °C.

## 2. Corpus inventory

| Folder | Paper | Pages | Model package | Registered |
|---|---|---|---|---|
| `Baez` | Baez, Majdalani & Shiloach 2014 — oxygen-induced recombinant protein expression | 7 | `Models/Baez/baez2014` + `manifest.json` | **No** (explicitly `registered_in_composition_registry: false`) |
| `Baez and Shiloach` | Baez & Shiloach 2013 — *E. coli* avoids high dissolved-oxygen stress via SoxRS and MnSOD | 9 | none | — |
| `Bhattacharya` | Bhattacharya & Dubey 1997 — dissolved oxygen and oxygen mass transfer vs overexpression | 6 | none | — |
| `Farrell` | Farrell et al. 2015 — DO-controlled fed-batch cultivation for recombinant subunit vaccine | 5 | none | — |
| `Ganjave` | Ganjave et al. 2022 — cybernetic growth and fed-batch model | 10 | `Models/Ganjave` | **Yes** — `ganjave@0.1.0` |
| `Krause` | Krause, Neubauer & Neubauer 2016 — the fed-batch principle for the molecular biology lab (**review**) | 13 | none | — |
| `Lemuth` | Lemuth et al. 2008 — global transcription and metabolic flux analysis, glucose-limited fed-batch | 14 | none | — |
| `Lin` | Lin et al. 2000 — maximum specific uptake capacities for glucose and oxygen | 11 | none | — |
| `Marish` | Marisch et al. 2013 — comparative analysis of industrial K-12 and B strains, high-glucose batch | 16 | none | — |
| `Mikiewicz` | Mikiewicz et al. 2017 — soluble insulin analogues from an *E. coli* expression system | 19 | none | — |
| `Morris` | Morris, Geiger & Fine 2011 — material balances | 104 | `Models/Morris` | **Yes** — `morris2011.material_balance@0.1.0` |
| `nanchen` | Nanchen, Schicker & Sauer 2006 — nonlinear dependency of intracellular fluxes on growth rate | 9 | none | — |
| `Siew and Zhang` | Siew & Zhang 2021 — downstream processing of recombinant human insulin from inclusion bodies (**review**) | 27 | none | — |
| `Simensen` | Simensen et al. 2022 — experimental determination of *E. coli* biomass composition | 17 | none | — |
| `Zielinski` | Zielinski et al. 2019 — expression and purification of recombinant human insulin from *E. coli* 20 | 7 | `Models/Zielinski` | **Yes** — `zielinski2019.rhi_process@1.0.0` |

Four of the fifteen papers have a model package; three of those four are registered. The
corpus grew from 4 folders to 15 since the previous audit of this project, and no
paper-to-model index existed before this document.

> **Updated 2026-10-30 — see §10.** This section records the state at the audit.
> The follow-up step implemented standalone models for three further papers
> (Lin, Nanchen and Simensen), so the corpus now has **seven** model packages:
> three registered and four standalone. §10 supersedes the "four of fifteen"
> count here and states which papers are executable standalone, which are
> evidence-only, and which can connect to the insulin simulation.

---
## 3. Already encoded (4 papers)

| Paper | Model | What the model encodes | Status |
|---|---|---|---|
| Zielinski et al. 2019 | `zielinski2019.rhi_process@1.0.0` | The whole insulin process as 15 operations and 17 streams, 196 ports, with page-level provenance on every number; evidence replay + fail-closed prediction | Registered. **This is the insulin simulation.** Declares 8 absent models |
| Ganjave et al. 2022 | `ganjave@0.1.0` | Cybernetic fed-batch growth: biomass, glycerol, complex substrate, dissolved oxygen, culture volume (9 in / 6 out). Equations (8)–(16), Table 2 parameters | Registered. `component_identity` declared unsupported |
| Morris, Geiger & Fine 2011 | `morris2011.material_balance@0.1.0` | Non-reacting control-volume balances over declared component sets | Registered. Instance-parameterised: no model-level port surface |
| Baez, Majdalani & Shiloach 2014 | `Models/Baez/baez2014` | One printed formula, as an inspectable artefact, with the paper's exclusions stated | Package present, **not registered**; inspection-only |

The Baez package cites only its own 2014 paper. Its companion **Baez & Shiloach 2013 is not
referenced anywhere in it**, so that paper is not encoded.

---

## 4. Ingested, not encoded (11 papers)

| Paper | Reports | Determination | Reason |
|---|---|---|---|
| Baez & Shiloach 2013 | dO₂ shifted 30 % → 300 %; the parental strain shows no significant growth-parameter change; SoxRS activated and MnSOD induced; the SOD-deficient strain fails to resume growth | **Cannot support a target model.** Context evidence only | *E. coli* **MG1655**, chemostat/batch physiology. No quantity in it is a measurement of *E. coli* 20 in GMS. Its finding is mechanistic (oxygen-stress protection), not a parameter the insulin process consumes |
| Bhattacharya & Dubey 1997 | DO optimum **0.22 mmol/L**; **kLa 61 h⁻¹** uninduced / **84 h⁻¹** induced; OUR rises on induction; **2.67 U mg⁻¹ h⁻¹** at 1 mM IPTG, max **6.7 × 10³ U mg⁻¹** ≈3 h post-induction | **Refused — different construct and product** | Recombinant *E. coli* **K-12/JM109** expressing **MspI methylase**, not pIBAINS/human insulin. Its kLa and DO values are the most transferable numbers in the corpus, but transferring them would substitute another construct's oxygen demand for this one's — the exact error the engine refuses |
| Farrell et al. 2015 | DO-stat nutrient feeding holds a DO setpoint; high cell density and titre; kLa-matched scale-down consistent at **2 L, 20 L, 200 L**; DO-stat → pre-determined feed transition | **Refused — different strains, different feed control** | Two unnamed recombinant *E. coli* strains (BL21/K-12/B cited), subunit-vaccine candidates, **DO-stat** feeding rather than the pH-stat cascade the 2019 process uses. A scale-down *method* is not a parameter of this process |
| Krause et al. 2016 | **Review.** Controlled glucose release in ready-made media improves cell yield and folding in shaken *E. coli* cultures; lower growth rates improve active-protein yield | **Cannot support a model.** Review-level | Aggregates results across many strains, vectors and media. No single process with one strain and one medium to declare; adopting any number would be picking an unspecified one |
| Lemuth et al. 2008 | Time series of whole-genome transcription during a carbon-limited fed-batch at constant feed; hunger vs starvation response; high-affinity transporters; ¹³C flux | **Refused — different strain and quantity class** | *E. coli* **K-12 W3110**. Reports transcript levels and intracellular fluxes, not the process quantities the insulin model consumes (no growth kinetics for *E. coli* 20, no kLa, no induction time) |
| Lin et al. 2000 | Maximum specific uptake capacities for glucose and oxygen vs μ; **qO₂ capacity ≈5 mmol g⁻¹ h⁻¹** at the end of fed-batch; μ fell to ≈0.02 h⁻¹; a dynamic uptake model replacing unstructured kinetics | **Refused — different strain and, critically, wrong quantity** | *E. coli* **W3110/K-12**. Supplies *uptake capacities in mmol g⁻¹ h⁻¹*, not the oxygen-transfer coefficient (`MP-OXYGEN-TRANSFER`) the insulin model lacks. The quantity does not match even before the strain does |
| Marisch et al. 2013 | Batch cultures of **BL21, RV308, HMS174** on high glucose: cell dry mass and growth rate highest for BL21; acetate much higher in K-12 than B strains; 347 of 3882 genes altered | **Refused — different strains and process** | Three industrial production strains, none of them *E. coli* 20; high-glucose batch, not pH-stat fed-batch. A host-comparison study |
| Mikiewicz et al. 2017 | **Same institute and same process route as the target**: pIBAINS, *E. coli* 20, GMS, 7.5 L Bioflo Celligen 310, inclusion bodies, trypsin cleavage, refolding, RP-HPLC — but for **four insulin analogues** (GKR/GEKR/AKR/SR) as an SOD::INS fusion | **Already assessed; refused — non-independent and no kinetics** | Recorded in the evidence catalogue as **CF-003**: it reports no μ, Ks or ms, and the passage it was cited for occurs in the **Zielinski 2019 text itself** (`CFL-01`, `not_independent_of_target`). It is the closest-matched paper in the corpus and still cannot carry a value into the model |
| Nanchen et al. 2006 | ¹³C intracellular fluxes across a broad range of growth rates in 10 mL parallel **chemostats**; physiological variables change monotonically with dilution rate | **Refused — different mode** | *E. coli* **W3110/MG1655/ML30** in continuous culture. A chemostat μ is not the μ of a pH-stat fed-batch batch phase, and the quantities are internal fluxes |
| Siew & Zhang 2021 | **Review** of downstream processing of recombinant human insulin/analogues from inclusion bodies: proinsulin recovery, IB washing, solubilisation, oxidative sulfitolysis, CNBr cleavage, chromatography, pH precipitation, zinc crystallisation, refolding, enzymatic cleavage, formulation | **Cannot support a model.** Review-level, and its one target-process link is the target paper | The route matches the 2019 process, but the numbers are aggregated across many strains, constructs and plants. **Its only mention of "E. coli 20" is in its reference list, citing Zielinski 2019** — the same self-citation shape as `CFL-01`. Using it as purification-recovery evidence would be reading the target paper back through a review |
| Simensen et al. 2022 | Experimentally determined *E. coli* **biomass composition** (protein, RNA, DNA, …) for constraint-based models; a protocol for condition-specific biomass determination; states that composition depends on **organism, strain and growth condition** | **Candidate input to a future spanning model — not a model, and not usable now** | *E. coli* **MG1655/K-12**, 3 L Eppendorf BioFlo **115**, 1 L M9 + 2 % glucose — not *E. coli* 20 in GMS in a Celligen 310. Its own abstract warns that the biomass objective function is strain- and condition-specific, which is the reason the engine refuses cross-context substitution. It could inform a *declared component set* for a bridge model, but that model does not exist and building it is a scientific decision, not a wiring step |

**Summary of the eleven:** three are reviews or aggregations (Krause 2016, Siew & Zhang 2021 —
plus Farrell 2015 is a method/scale-down paper), eight report measurements for a **different
strain, construct, medium, mode or scale** from *E. coli* 20 in GMS, and exactly one
(Mikiewicz 2017) describes the target process — and is already recorded as non-independent
with no kinetics.

---

## 5. Why no new model was created and none was registered

The condition in the task is "useful findings **not yet encoded**", and the audit's outcome is
that none of the eleven clears the second and third questions in §1:

* **No paper reports a quantity for the target process that the model does not already
  have.** Ten of eleven are a different strain, construct, medium, mode or scale; the
  eleventh (Mikiewicz 2017) is the target process but reports no kinetic parameter and is
  already recorded as non-independent. There is therefore no finding to encode — and adopting
  Bhattacharya's `kLa = 84 h⁻¹` because the *unit* fits is exactly what the engine's
  separation of dimensional from semantic compatibility exists to prevent.
* **Registering a model for a non-target process would cost more than it gives.** A
  registration is not free: it needs a manifest, a port surface, an adapter, tests, **and** a
  declared compatibility position against every other model (`cross_model.py` declares all
  nine ordered pairs explicitly). A model built from Lin 2000's uptake capacities would add
  four new ordered pairs to that authority, every one of them refused, and would appear in
  the library as a component that can never be used in this simulation. That is noise in a
  library whose whole design is that every entry means something.
* **The papers that could unlock composition are not papers.** The refused
  `ganjave ⇄ zielinski` boundary could be crossed by a spanning model declaring a shared
  component set, an explicit dry-to-wet biomass basis, a scale relationship and a common
  medium. Simensen 2022 could inform the *first* of those four, for *E. coli* generally — and
  its own abstract states that biomass composition is organism-, strain- and
  growth-condition-specific, which is exactly why it cannot simply be lifted. The other three
  declarations appear in none of the fifteen papers.

So the deliverable here is the index and the reasons, not a model. That is the outcome the
task asks for when a paper "cannot support a defensible model".

## 6. What would change the answer

1. **A kinetic dataset for *E. coli* 20 + pIBAINS in GMS** — the only route to
   `MP-GROWTH-KINETICS`. Not in any of the fifteen papers, and not found by the evidence
   catalogue's own search (see `reports/MODEL_LIBRARY_INTEGRATION.md` §8).
2. **A declared assumption**, recorded as `Provenance.ASSUMED` with a rationale: legitimate,
   labelled, and it converts "fails closed" into "predicts under a stated assumption". A
   product decision rather than a scientific claim.
3. **A spanning model** carrying the four declarations above — the only way to compose two
   papers' processes, and new modelling work. Simensen 2022 (component set) and Siew & Zhang
   2021 (purification route) are the two papers in this corpus that could contribute; neither
   is sufficient, and neither is a measurement of this process.

## 7. Corpus hygiene notes

* `Models/Marish/` holds **Marisch** et al. 2013 — the folder misspells the first author, so
  any lookup keyed on folder name would fail to find it.
* Naming is inconsistent: `nanchen` is lowercase; `Baez and Shiloach` and `Siew and Zhang`
  carry two authors; the rest are single surnames.
* Three of the fifteen are reviews or methods papers (Krause 2016 and Siew & Zhang 2021 are
  reviews; Farrell 2015 is a scale-down method). Treating any of them as a source of process
  parameters is a category error, and two of the three would additionally reimport the target
  paper's own content through a reference list.
* The corpus grew from 4 folders to 15 with no index. This document is that index; the check
  below keeps it from drifting again.

---

## 8. Checks

| Check | Command | Result |
|---|---|---|
| Corpus index agrees with the tree and the registry | `cd composition && python -m composition.evidence.papers --check` | **PASS** — 15 papers recorded: `encoded 3`, `encoded_unregistered 1`, `refused 7`, `not_supportable 3`, `candidate_input 1` |
| Corpus index is served to the editor | `python -m composition.runner --describe-papers` | **PASS** — 15 paper records, each with folder, citation, determination, reason, package, registration |
| The guard can actually fail | `python -m pytest tests/test_paper_coverage.py` | **21 passed** — including three that build a corpus with an unrecorded folder, a vanished folder and an invented registration, and assert each is caught, plus two that assert the library keeps no copy of the corpus |
| Evidence catalogue unchanged and still builds | `python -m composition.evidence --result <tmp>` | **5 targets, 3 findings, `incompatible: 3`** — identical to before this audit |
| Evidence suite | `python -m pytest tests/test_evidence_catalogue.py` | **62 passed** |
| Web catalogue still agrees with the engine | `python scripts/build_web_model_catalog.py --check` | **PASS** |
| Model library, graph editor + corpus section | `godot --headless --path . --script res://composition/tests/godot/palette_graph_run.gd` | **447 passed** (274 before this change; +173 from check 19) |
| GDScript → Python contract boundary | `… --script res://composition/tests/godot/contract_boundary.gd` | **840 passed** |
| Simulation workshop | `… --script res://composition/tests/godot/workshop_graph_run.gd` | **144 passed** |
| Composition acceptance suite | `cd composition && python -m pytest tests/test_acceptance.py` | see the final summary |

Note on running the Python suites here: `pytest`'s own `tmp_path` base directory is
access-denied on this machine (`WinError 5` on `%TEMP%\pytest-of-preni`), so the suites were
run with `--basetemp .artifacts/basetemp-<name>`, which is the repository's existing
convention (`.artifacts/basetemp-*` directories are already present).

No model, adapter, equation, parameter, registration or compatibility rule was changed, and no
pair was added to `cross_model.py`. The library's separation of *registered/placeable* from
*visible/evidence-only* is described in §9; the editor can now show a paper that has no model
without that paper becoming runnable.




## 9. How the corpus is represented in the model library

All fifteen papers are now visible in the composition editor's model library, and the
separation the task asks for is structural rather than cosmetic.

**Two lists, two meanings.** The panel has:

* the **Models** list — the registered models, each with an Add button, each with the
  compatibility engine's verdict. This is exactly the registry: `model_entries()` equals
  `--list-models` and nothing else, which the harness has asserted since before this change;
* the **Ingested papers** list — every paper folder under `Models/`, each with its source
  citation, its determination, its execution status, its integration status and the audit's
  reason. **No row in it has an Add button**, so no paper can be placed as a node, and none
  of them is in `model_entries()`.

**Where each fact comes from.** The papers list is read with a new introspection verb,
`--describe-papers`, which returns `composition.evidence.papers.audit()` — the same index the
`--check` guard validates. Nothing about a paper is decided by the editor: the determination
and the reason are the index's own fields, the execution status restates the record's own
`registered` / `model_package`, and the integration status is `integration_status()`, which is
the engine's position for a registered model and *no position at all* for the rest.

**What a reader sees per paper**, colour-coded:

| Line | Registered paper (Zielinski, Ganjave, Morris) | Evidence-only paper (the other twelve) |
|---|---|---|
| folder + determination | `Zielinski` · `encoded` | `Bhattacharya` · `refused` |
| source | the paper's citation | the paper's citation |
| execution | "executable — registered as `zielinski2019.rhi_process@1.0.0`, so it can be placed from the model list above" | "evidence only — no executable model exists for this paper; its findings are recorded, not run" (or "not executable here" for Baez, whose package exists but is deliberately unregistered) |
| integration | the engine's own verdict and reason | "no engine position — the compatibility engine classifies registered models; nothing was assessed for this paper" |
| audit reason | the recorded reason | the recorded reason |

Each registered model row also gained a `source:` line naming the paper it encodes, so the
model → paper link is visible from both directions.

**Why this is not a compatibility change.** No model was registered, no pair was added to
`cross_model.py`, and no verdict was touched. The papers list carries no compatibility claim
for anything unregistered — the engine classifies registered models, and a paper outside that
set gets `not_evaluated` with a reason saying so, exactly as the engine's own four-state
mapping already specifies. The library's existing scope line ("compatibility covers the
registered models only") remains true, and the harness still asserts it.

**Guards.** `palette_graph_run.gd` check 19 (173 assertions) drives the real scene and asserts:
the corpus index was actually read; every entry reached the panel with a source, a
determination, an execution status and a reason; **no paper card contains an Add button**; no
paper folder appears in the placeable model list; each registered model is named by exactly
one entry that says it can execute and credits the engine; and every paper without a
registered model is reported `not_evaluated` rather than given a verdict. On the Python side
`tests/test_paper_coverage.py` adds two guards that the library holds no copy of the corpus:
the window must call `describe_papers()`, and neither the palette nor the harness may quote a
corpus folder name or a `Models/` path literal.



---

## 10. Update 2026-10-30 — quantitative findings encoded, and what stays evidence

The audit above catalogued every paper. This section records the step that asked,
for each paper with no model, whether the paper prints an explicit quantitative
model, equation or dataset, and implemented it where the answer was yes.

The question is **not** "could this paper join the insulin simulation". A
standalone model needs no compatibility with anything: it needs the paper's own
equations or table and the paper's own context. That is why three papers this
audit marked `refused` or `candidate_input` now have runnable models: they were
refused *for composition*, which is a different question from *encodability*.

### 10.1 What was found, paper by paper

| Folder | Explicit quantitative content in the paper | Decision |
|---|---|---|
| `Lin` | The Appendix is titled "THE COMPLETE SIMULATION MODEL": seven differential equations, the initial-value equations and the subsidiary chain (pp. 356-357), plus Table I's parameter set (p. 348) and the pulse method, equation (1) (p. 351) | **Standalone equation model** — `Models/Lin/lin2000` |
| `nanchen` | Pirt's chemostat relation, equation (3) (p. 1167), with the paper's own fitted maintenance coefficient and maximal molar yield in Table 1 (p. 1167) | **Standalone equation model** — `Models/nanchen/nanchen2006` |
| `Simensen` | Table 1 (p. 9): the measured macromolecular biomass composition in `g gCDW-1`, three columns, every SD and marker printed | **Standalone dataset model** — `Models/Simensen/simensen2022` |
| `Baez and Shiloach` | Growth rates and mRNA fold-changes in prose; the paper's contribution is the SoxRS/OxyR *mechanism*, with no printed equation or table | Evidence-only — mechanism, not a model |
| `Bhattacharya` | Reported optima and readings in prose (2.67 and 6.7e2 U mg-1 p-1 h-1; OUR 0.135/0.095 mM L-1 h-1; kLa 61 and 84 h-1; DO 0.22 mmol/L). No printed equation, and the only series are figures | Evidence-only — readings without an equation or a tabulated dataset |
| `Farrell` | A DO-stat control strategy and a kLa-matched scale-down model, described in prose with OD600/titre readings; no printed equation and no tabulated dataset | Evidence-only — a control strategy, not a printed model |
| `Krause` | A review of the fed-batch principle | Evidence-only — review |
| `Lemuth` | Transcriptome and 13C flux analysis; the paper uses models published elsewhere (Chassagnole) and plots fluxes, tabulating no rate model | Evidence-only — flux measurements from another model, no printed equation here |
| `Marish` | Comparative strain characterisation; yields and growth rates in prose and figures, no printed equation | Evidence-only — comparative measurements |
| `Mikiewicz` | Insulin-analogue constructs and a downstream process; the one "model" it names is a program based on Sillero's published model, not printed here | Evidence-only — construct/process study, model cited not printed |
| `Siew and Zhang` | A review of downstream processing of recombinant human insulin | Evidence-only — review |

Three of these determinations changed from the audit above: `Lin` was `refused`,
`nanchen` was `refused`, and `Simensen` was `candidate_input`. The determinations
are now `encoded_unregistered` for all three, because a model package exists and
is deliberately not registered.

### 10.2 The three-way split

`python -m composition.evidence.papers --check` reports:

```
execution:
  composable       3  Ganjave, Morris, Zielinski
  standalone       4  Baez, Lin, Simensen, nanchen
  evidence_only    8  Baez and Shiloach, Bhattacharya, Farrell, Krause, Lemuth,
                      Marish, Mikiewicz, Siew and Zhang
```

* **Composable (3)** — registered with the composition layer, so they can be
  placed in a graph: `zielinski2019.rhi_process@1.0.0` (the insulin simulation
  itself), `ganjave@0.1.0`, `morris2011.material_balance@0.1.0`.
* **Executable standalone (4)** — run on their own paper's experiment and are
  deliberately not registered: `baez2014`, `lin2000`, `nanchen2006`,
  `simensen2022`.
* **Evidence-only (8)** — no runnable model exists, and the index records why.

### 10.3 Which papers can actually connect to the insulin simulation

**Only the three registered models can.** The four standalone models cannot, and
that is a deliberate, checked separation rather than an omission:

* none of the four declares a port, an adapter registration or a compatibility
  claim (`test_no_standalone_package_is_registered_with_the_composition_layer`);
* each paper's own context differs from `zielinski2019.rhi_process` in strain,
  construct, medium, reactor, scale, mode and temperature — the four packages
  record that context with page-level citations and state the mismatch in their
  manifests and in `context.TARGET_PROCESS_NOTE`;
* `python -m composition.registry` still lists exactly the three composed models.

No parameter was transferred across those boundaries, and no compatibility
verdict was created. `composition.cross_model` is unchanged.

### 10.4 Where each entry now links

Every `Paper` record links to exactly one of three things, derived rather than
stored twice:

| Link kind | Means | Count |
|---|---|---|
| `composed_model` | `model_id` in the adapter registry | 3 |
| `standalone_model` | a package in `composition.evidence.standalone` | 4 |
| `evidence_only` | `paper:<folder>#<determination>` — this index's own record | 8 |

`composition.evidence.papers.audit()` fails (`--check`) when any paper links
nowhere, when a package is neither registered nor a known standalone model, when
a paper claims both, or when a standalone entry names a folder the index does not
record.

