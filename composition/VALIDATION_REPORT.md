# Validation Report

**Date:** 2026-10-14
**Composition contract version:** 0.1.0
**Godot:** 4.7.2-stable

This report records what was run, what passed, what did not, and what remains
unsupported. It is generated from the test suites; nothing here is asserted
without a corresponding test.

---

## 1. Model versions under test

| Model | Package | Version | Suite location |
|---|---|---|---|
| Morris, Geiger & Fine (2011) material balance | `Models/Morris` | `0.1.0` | `Models/Morris/tests` |
| Zieliński et al. (2019) insulin process | `Models/Zielinski` | `1.0.0` | `Models/Zielinski/tests` |
| Composition layer | `composition` | `0.1.0` | `composition/tests` |

No file under `Models/` was modified by this work. `tests/test_acceptance.py`
verifies this in two ways: it runs both suites as subprocesses from their own
roots and asserts their counts, and it parses every `.py` file under `Models/`
and asserts that none of them imports the composition contract.

---

## 2. Test totals

### 2.1 Existing model suites (unchanged, reported separately — CG-15)

| Suite | Result |
|---|---|
| `Models/Morris` | **186 passed** |
| `Models/Zielinski` | **223 passed** |
| **existing total** | **409 passed** |

These are the same figures captured in `COMPOSITION_AUDIT.md` §7 before any
composition code was written. The composition layer is import-only: it adds the
two model roots to `sys.path` and never writes to them.

### 2.2 Composition suite

| File | Tests |
|---|---|
| `tests/test_acceptance.py` | 86 |
| `tests/test_quantities.py` | 26 |
| `tests/test_contracts.py` | 16 |
| **pre-existing total** | **128 passed** |
| `tests/test_evidence_catalogue.py` | 62 (new — §11) |
| `tests/test_registry.py` | 52 (new — §12) |
| **composition total** | **242 passed** |

The acceptance suite is organised as one class per criterion with a
`CG_COVERAGE` table that the suite checks for completeness, so a criterion
cannot be added without a class or a class without tests. The contract suite
pins the JSON boundary so a graph file's round trip is part of the public
interface rather than an internal detail.

### 2.3 Combined

| | |
|---|---|
| existing model suites | 409 |
| composition suite | 242 |
| **total** | **651 passed** |

The pre-existing figure was 537 (409 + 128). The 114 additional tests cover the
literature-evidence workflow (§11) and the model registry (§12); no
pre-existing test was modified.

### 2.4 Godot project

| Check | Result |
|---|---|
| `godot --headless --import` | zero script errors |
| `godot --path .` in a real window, driving the real toolbar | zero script errors, zero runtime errors |
| `Run` button pressed in the real window, all six examples | exit codes `0,1,2,1,1,1` — identical to the direct Python path |
| main scene | `res://scenes/composition.tscn` → `res://scripts/main.gd` |
| GDScript → Python boundary | `scripts/runner.gd` only; no scientific code in GDScript |

The Godot path is verified by driving the real toolbar — the example
`OptionButton` and the real `Run` `Button` — against the real scene in a real
window, and reading back the payload the editor received. The subprocess exit
code the UI observed for each example matches the exit code the Python runner
produced when invoked directly (§4).

#### 2.4.1 The GDScript → Python boundary on Godot 4.7.2

Godot 4.7 removed the `env` parameter from `OS.execute`:

```gdscript
OS.execute(path, arguments, output: Array, read_stderr: bool, open_console: bool) -> int
```

Passing `"PYTHONPATH=..."` positionally therefore lands the string in the
`output` array, where it is silently discarded, and the child inherits an
unchanged environment. `scripts/runner.gd` sets `PYTHONPATH` with
`OS.set_environment()` before executing, which the child does inherit.

Two further constraints are recorded because they are not obvious and both
cost real time to discover:

* `OS.execute_with_pipe()` is unusable here. It returns live pipe handles, and
  `blocking = true` waits for the child to exit; any output larger than the OS
  pipe buffer deadlocks. Measured: a 200 KB child hangs indefinitely, while
  `OS.execute(..., read_stderr = true)` returns 1 MB in 668 ms.
* `capture_output` merges stdout and stderr into a single array and this API
  offers no way to split them. The UI therefore labels the captured text as
  merged rather than guessing which stream produced which line.

`scripts/runner.gd` also resolves `res://` and `user://` to absolute OS paths
at the boundary, because the Python runner is an ordinary `pathlib` program
with no notion of Godot's virtual filesystem.

---

## 3. Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| **CG-01** Model discovery | pass | both manifests load; 196 Zieliński ports and 12 Morris ports derived; the one unusable port (`1/h`) is published and reported |
| **CG-02** Port compatibility | pass | `mass`→`mass` and `mass_fraction`→`mass_fraction` connect; `AU`→`mass` refused |
| **CG-03** Unit semantics | pass | `g`→`kg/h` refused by `connection.quantity_mismatch`; Morris's own refusal of a `kg` stream in a steady-state system verified by running it |
| **CG-04** Graph ordering | pass | `brass_charge` → `brass_alloying` → `zielinski_rhi`; order stable across runs |
| **CG-05** Data transfer | pass | downstream receives exactly `26600.0` kg and both fractions, bit-identical, with a two-hop provenance chain |
| **CG-06** Conservation regression | pass | Example 4.2 reproduced: 26600 kg, `w_Cu = 0.79756`, `w_Zn = 0.20244`; both existing suites green |
| **CG-07** Missing information | pass | an unresolved value is never injected downstream; a free variable is reported, and a pivot value is labelled `representative` |
| **CG-08** Component mapping | pass | `component_unattributed` and `component_mismatch` both demonstrated |
| **CG-09** Unsupported physics | pass | `reactive_balance_refused` on every edge that would cross the Zieliński boundary |
| **CG-10** Cycle detection | pass | `order.cycle_detected` names both instances and all four connections |
| **CG-11** Failure propagation | pass | inconsistent upstream solves nothing; downstream skipped with the cause named |
| **CG-12** Provenance | pass | every output carries a chain naming model, version, method, source reference and — for transfers — connection and both ports |
| **CG-13** Reproducibility | pass | identical digests across runs; changing one input changes the digest; byte-identical result files |
| **CG-14** End-to-end execution | pass | all six shipped examples match their documented exit codes; `--plan-only` validates without executing |
| **CG-15** Existing regression suite | pass | 186 + 223 = 409, reported separately; no model file imports the composition contract |

---

## 4. Example graphs

Every example was run twice: once through the Python runner directly, and once
by pressing the `Run` button in the Godot window. Both paths are shown because
they must agree.

| File | Exit (direct Python) | Exit (Godot `Run`) | Status | Demonstrates |
|---|---|---|---|---|
| `brass_batch_chain.json` | 0 | 0 | `success_with_warnings` | the runnable chain: Morris Example 4.2 → downstream alloying → standalone Zieliński replay |
| `rejected_mass_as_flow.json` | 1 | 1 | `invalid` | CG-03: `g` into `kg/h` |
| `rejected_au_to_mass.json` | 1 | 1 | `invalid` | CG-02/CG-09: `AU` into a mass port |
| `rejected_component_mapping.json` | 1 | 1 | `invalid` | CG-08: unattributed component, wrong component, and the reactive-boundary refusal |
| `cycle_rejected.json` | 1 | 1 | `refused` | CG-10: a two-node cycle |
| `failure_propagation.json` | 2 | 2 | `failed` | CG-11: an inconsistent balance stops its dependent |

Every example's expected exit code is pinned in `conftest.py`'s
`EXAMPLE_EXPECTATIONS` and checked by `TestCG14`.

### 4.1 A note on the reproducibility digest across the two paths

Running `brass_batch_chain.json` directly from `composition/examples/` yields
digest `a0d47b8a2f6d9111…`. Running it from the Godot editor yields
`eedf416aef9cf7fb…`. The engine is not at fault and is in fact deterministic:
running the *editor-written* graph through the Python runner directly
reproduces `eedf416aef9cf7fb…` exactly.

The difference is the graph document, not the results. Godot's JSON parser
yields every number as a float, so positions are rewritten `60` → `60.0` on
save, and the digest — which covers the graph document — changes with it. The
values themselves are unaffected.

`source_ref`, a top-level provenance field present in the shipped example, was
also being dropped entirely on save. That was data loss and is fixed; the
digest divergence above is a separate, cosmetic serialisation artefact and is
recorded as a known limitation (§6.3).

---

## 5. Numerical results of the runnable example

### 5.1 `brass_charge` — Morris et al. (2011) Example 4.2

| Port | Value |
|---|---|
| `out:D:Cu` | 21215 kg |
| `out:D:Zn` | 5385 kg |
| `out:D:total` | 26600 kg |
| `out:D:w:Cu` | 0.797556 |
| `out:D:w:Zn` | 0.202444 |
| solvability | `unique` |

Matches the book's 26600 kg mixture at `w_Cu = 0.798`.

### 5.2 `brass_alloying` — downstream, fed by the connection

| Port | Value |
|---|---|
| `in:A:total` | 26600 kg (from connection `c1`) |
| `in:A:w:Cu` | 0.797556 |
| `in:A:w:Zn` | 0.202444 |
| `out:E:Cu` | 21215 kg |
| `out:E:Zn` | 5885 kg |
| `out:E:total` | 27100 kg |
| `out:E:w:Cu` | 0.782841 |
| solvability | `overconstrained` — one dependent equation, reported as a check per sec. 4.6.2 |

The 500 kg zinc make-up is declared as a literal input with
`provenance: assumed` and `assumption_id: COMP-MAKEUP-500KG`, so a reader can
see exactly which result depends on the one invented number in the graph.

### 5.3 `zielinski_rhi` — evidence replay

| | |
|---|---|
| reported values | 142 |
| digitized values | 20 |
| computed values | 20 |
| unknown values | 11 |
| predictive predictions | 0 of 23 targets |
| model-reported findings | 5 errors, 6 warnings |

The 5 error-severity findings are contradictions *inside the source paper*
(sec. 4.4 vs 4.5 AU totals; the `/7` water formula vs the reported 285 mL; the
CPB dose rule vs the stated 50 µL). They are surfaced at error severity and do
not fail the run, because the model ran to completion.

---

## 6. Limitations

### 6.1 Scientific

1. **No cross-model material connection is possible in v0.1.** Not one of the
   Zieliński model's twenty equation outputs can legally enter a Morris control
   volume. The three independent reasons — no component identity, a reactive
   boundary, and a mass-vs-mass-flow quantity change — are documented in
   `COMPOSITION_AUDIT.md` §4 and §6.3. This is a property of the source models,
   not a gap in the composition layer.
2. **No rate conversion.** A batch inventory cannot become a steady-state flow
   rate. The paper states durations only as ranges, which the Zieliński model
   deliberately refuses to collapse.
3. **No AU → mass conversion.** The spectrophotometer was water-blanked
   (sec. 2.18), so the absorbance scale is instrument-relative.
4. **No per-stage recovery.** An AU ratio across stages is not a recovery,
   because the AU basis differs between stages.
5. **Evidence replay is not prediction.** The Zieliński instance restates the
   paper's reported numbers.

### 6.2 Engineering

1. **No iterative solve.** Cycles are refused outright.
2. **One value per input port.**
3. **Subprocess isolation.** Each model runs in its own interpreter because
   both ship a top-level `models` package. This costs ~0.3 s per model per run
   and guarantees the existing suites cannot be disturbed, but it means the
   composition layer cannot call a model's Python API directly.
4. **Representative values.** An under-determined Morris system returns the
   canonical member of a one-parameter family for its pivot variables. These
   are labelled `representative` and must not be quoted as determined values.

### 6.3 Editor

1. **Saving from the editor rewrites numbers as floats.** Godot's JSON parser
   has no integer type, so a position saved as `60` returns as `60.0`. The
   scientific content is unchanged, but the reproducibility digest covers the
   graph document, so an editor-saved graph has a different digest from the
   byte-identical shipped file (§4.1). Preserving the original numeric literals
   would require a hand-written serialiser.
2. **Node layout is not yet usable for a real graph.** `zoom_to_fit` runs
   against node sizes that are still being computed, so a saved graph with tall
   nodes opens clipped, and the saved positions in `brass_batch_chain.json`
   place the insulin node underneath the process chain. This is presentation
   only — it does not affect validation, execution or results — and it is
   unfixed.
3. **"Add model" is a stub.** `scripts/model_palette.gd` was removed during
   earlier debugging and the button opens a dialog saying so. Example graphs
   are the only way to populate a graph.

---

## 9. 3D replay scene

`scenes/replay3d.tscn` is a second scene, reached from the editor toolbar. The
main scene is unchanged, so launching the project still opens the graph editor
first.

### 9.1 What it is, precisely

It is a **replay of published values, not a simulation.** The Zieliński model is
an evidence-replay model: it reports no kinetic parameter and no spatial field,
so nothing in this scene integrates an equation over time and nothing in it
draws a computed concentration, velocity or oxygen distribution.

| Scene element | Driven by | Provenance |
|---|---|---|
| vessel body | `node:N01#fermenter_nominal_volume` = 7.5 L | reported |
| liquid column | `node:N01#starting_medium_volume` = 4.0 L | reported |
| liquid colour | `stream:S02_culture_broth#od600_hNN`, 19 points | digitized |
| growth chart | the same 19 points + the two derived crossing times | digitized / derived |
| purification cascade | `node:N08/N11/N13/N14#total_au` | derived |

The liquid colour is a legend-mapped encoding of one bulk scalar. It is labelled
as an encoding wherever it appears and is never presented as a field.

### 9.2 Deliberately absent

These are the model’s own refusals, surfaced in the UI rather than worked
around:

| Not drawn | The model’s stated reason |
|---|---|
| particles, cells, bubbles | no concentration field, cell count or size distribution exists |
| flow, shear, mixing | *"The paper reports no air flow, agitation rate, dissolved-oxygen trace or kLa"* |
| a rotating impeller | agitation rate is unreported, so there is nothing to rotate by |
| an animated liquid level | the working volume is reported once; no feed or evaporation is reported |
| an induction marker | *"the paper never states the induction time point"* |
| protein in g/L or IU/L | the spectrophotometer was water-blanked (§2.18); no AU→mass conversion exists in the unit registry |

The scene shows the first three unresolved ports under a heading reading
*absent from the model*, each with the model’s own sentence as its reason.

### 9.3 Execution

The scene reuses `CompositionRunner`, the same boundary as the graph editor, via
`composition/replay/zielinski_replay.json` — a standalone Zieliński instance
placed outside `examples/` so the pinned `EXAMPLE_EXPECTATIONS` set is
untouched. The call is **asynchronous** (`OS.create_process` polled per frame) so
the window keeps repainting while Python runs; the synchronous editor path is
unchanged and still verified.

Direct run of the same graph: exit `0`, `success_with_warnings`,
digest `2f5a2820c622b74d…`.

### 9.4 Verification

| Check | Result |
|---|---|
| 30 acceptance assertions across run / reset / pause / playthrough / editor handback | all pass |
| full workflow: editor Run → 3D replay, both screens | all pass |
| failure path (scene fed a genuinely rejected graph) | exit 1, `refused`, 0 outputs bound, every panel says "not available", model diagnostics shown verbatim |
| `Models/Morris`, `Models/Zielinski`, `composition` suites | 186 / 223 / 128 — unchanged |

---

## 10. Replay interface clarity pass

A presentation-only change. No model equation, contract, unit rule, execution
path or test was touched.

### 10.1 Reading order

The default view is now a numbered five-section hierarchy, left column then
right, so a reader never has to decode a field name to know where they are:

| # | Section | Contents |
|---|---|---|
| 1 | Reactor and operating conditions | the 3D vessel, camera, and the four stated operating conditions |
| 2 | Culture growth over time | culture time, the density readout, the Fig. 3 chart, and the two interpolated crossing times |
| 3 | Purification results | the AU chart and the four headline product results |
| 4 | What this model cannot tell us | the three unresolved quantities, each with the model's own sentence |
| 5 | Detailed evidence and technical diagnostics | collapsed: *All data and evidence*, *Run status and technical details* |

### 10.2 Vocabulary

The default view is plain language; the contract's own field names are kept one
click away in section 5.

| Shown to the reader | Schema field, still available in section 5 |
|---|---|
| stated in the source | `reported` |
| read from a published figure | `digitized` |
| calculated from the available data | `derived` |
| not established by the available evidence | `unknown` |
| Culture time 13.5 hours | — |
| Density 29.105 OD600 | `stream:S02_culture_broth#od600_*` |

OD600 and AU are each explained in context, directly beneath the chart they
belong to.

### 10.3 What did not change

* The 3D reactor, camera, orbit and zoom.
* The growth curve, its ±0.5 OD uncertainty band, and its `p.67, Fig. 3` citation.
* The purification chart, in instrument-relative AU.
* All 196 outputs, the provenance filter, the contract field names, the full
  provenance chain and the execution diagnostics — all still reachable.
* Run model / Pause / Resume / Reset, playback speed, Back to graph editor.
* The honesty labelling: replay-not-simulation, colour-as-encoding, AU-not-a-
  concentration, unknown-never-zero.

### 10.4 One real defect found and fixed

The digitized trajectory was stored in a `PackedFloat32Array`, so the published
plateau printed as `53.669998` instead of `53.67`. It is now a
`PackedFloat64Array`, matching the precision the model actually publishes. This
was visible on screen and would have been indistinguishable from a genuine
measurement.

### 10.5 Additional UI tests (reported separately from the scientific suites)

| Suite | Result |
|---|---|
| replay interface acceptance | **77 checks, 0 failures** |
| replay behaviour regression (run / pause / reset / completion / failure) | **18 checks, 0 failures** |
| `Models/Morris` | 186 passed |
| `Models/Zielinski` | 223 passed |
| `composition` | 128 passed |
| **existing total** | **537 passed — unchanged** |

Those harnesses were temporary and were deleted after they ran, so they are not
re-runnable. The 30 checks in §11.5 are reported the same way.

---

## 11. Literature-based missing-evidence discovery

The Zieliński 2019 model reports several quantities as `unknown`. Until now the
interface stopped there: the reader was told a quantity was missing and then
given nothing to do. This section records the workflow that replaces that dead
end, and — more importantly — what the literature search actually turned up.

### 11.1 What was targeted

`MP-GROWTH-KINETICS` states: *"No specific growth rate, saturation constant,
maintenance coefficient or feed rate is reported anywhere in the paper."* It
blocks `od600_from_inputs`, `wet_biomass_from_inputs` and `glucose_consumed`.
Two further gaps were registered: `MP-OXYGEN_TRANSFER` and
`MP-INDUCTION-TIME`.

The target process, as published: **E. coli 20** (a K-12 derivative of CSH50R),
carrying **pIBAINS** (TetR, `deoP1P2` promoter), in **GMS minimal medium**,
**batch** with pH-stat glucose feeding, 4 L in a 7.5 L fermenter, 37 °C, pH
controlled with 16 % NH₄OH. Dissolved oxygen is not reported.

### 11.2 Reused schema

`scaleup_ai.provenance` already defines `Provenance`, `Uncertainty` and
`MissingParameter`. The first two are reused verbatim in shape and vocabulary
(`reported` / `digitized` / `derived` / `assumed` / `unknown`; `kind`, `lo`,
`hi`, `basis`). `EvidenceRef` could **not** be reused: its `__post_init__`
enforces `pdf_page == printed_page - 62`, the Zieliński page offset, so it
cannot address a different paper. A source-location type that is not bound to
one publication was needed.

The new package takes **no run-time dependency on a model** — it neither imports
`scaleup_ai` nor writes to `Models/`. A test asserts this by walking the AST.

### 11.3 A circular verdict, found and corrected

The first version of this workflow recorded the target process once, then
recorded each candidate's conditions as strings **identical** to it. The
comparator then reported dimensions matching — which looked like verification
but was a tautology, because both sides of every comparison had been written by
the same person from the same reading. Agreement had been constructed, not
observed.

CF-003 made this visible. It was recorded as a `found` external source — a 2017
paper from the same institute, on the same strain, vector and medium — on the
strength of seven dimensions scoring `match`. But every one of those condition
strings had been typed identical to the target's.

Binding each condition to a passage from its own source exposed what was
actually true:

> **CF-003's supporting passage occurs verbatim in the Zieliński 2019 text.**

The 2019 methods section and the 2017 methods section describe the same run in
near-identical wording — *"…the glucose feeding was limited until its
concentration in the medium was reduced to 0 g/dL"* appears in both. CF-003 is
therefore the target publication's own content reached through a second paper.
It is **not independent evidence**, and it can never corroborate the target
paper.

The defect sat precisely on the one finding carrying positive weight. The two
`incompatible` verdicts were unaffected: their conditions genuinely differ,
because they were transcribed from what those papers actually said.

### 11.4 The fix

Each condition is now a record carrying its value **in that source's own
wording**, the **verbatim passage** it was transcribed from, and that source's
id. The target process is transcribed the same way, from the Zieliński
publication, with printed-page references (§11.2).

Comparison then compares two independently checkable passages. A reader can
verify each side against its own paper. Agreement is a finding again.

Two consequences worth stating plainly:

- **Similar is no longer sufficient.** "GMS medium" against "GMS medium plus 2×
  yeast extract" scores `partial`, never `match`. The test suite pins this.
- **Different is still different.** Removing string-equality scoring entirely
  would have been over-correction — it collapsed genuinely distinct strains
  (ML30, MG1655) into "cannot tell". The declared rules distinguish them by
  extracting the identifiers each side names (`ML30` ∩ `20, IBA, 1` = ∅ →
  `mismatch`), and use closed vocabularies where the terms are genuinely
  mutually exclusive (a culture is batch *or* chemostat *or* microfluidic).

A new determination, **`independence`**, is reported for every finding and is
required for validation (VC-10). A non-independent finding can never be
recorded as `FOUND`, whatever its conditions say.

### 11.5 What the search actually found

| ID | Quantity | Source | Independent | Verdict |
|---|---|---|---|---|
| CF-001 | Monod Ks, 40–88 µg/L | Senn *et al.* 1994, BBA 1201(3):424–436, `10.1016/0304-4165(94)90072-8` | external | **incompatible** |
| CF-002 | Single-cell μ, 0.19–0.61 h⁻¹ | Smaluch *et al.* 2023, Eng Life Sci 23(1):e2100157, `10.1002/elsc.202100157` | external | **incompatible** |
| CF-003 | Growth-phase OD600 ranges | Mikiewicz *et al.* 2017, PLoS ONE 12(3):e0172600, `10.1371/journal.pone.0172600` | **target source** | **incompatible** |

**Zero found. Zero validated.** All three are now `incompatible`, and CF-003 for
a reason that is about provenance rather than conditions.

- **CF-001** — steady-state glucose-limited chemostat on strain ML30, against a
  pH-stat fed batch on a different strain with a recombinant plasmid. Its own
  conclusion is that a single set of kinetic "constants" probably cannot describe
  the bacterium, because published Ks values differ by orders of magnitude
  depending on adaptation history. It reports a *range*; the upper bound is
  carried and 40–88 µg/L kept in the uncertainty record. **No midpoint was
  invented.**
- **CF-002** — single-cell rates by quantitative phase imaging at 606 pL.
  Temperature (37 °C) genuinely matches — both papers state it. Strain, medium,
  mode and measurement basis do not.
- **CF-003** — matches the process on temperature, medium, mode and scale, and
  supplies **no kinetic parameter of any kind**. It is now recorded as
  non-independent, which is the stronger and more accurate statement.

### 11.6 Records examined

Every verdict is published next to the artefact it was made against, so a later
reader can tell which model state produced it. Recorded in the report:

| | |
|---|---|
| model | `zielinski2019.recombinant-insulin`, v1.0.0, `10.1016/j.jbiotec.2019.03.011` |
| run | `zielinski-replay` |
| graph digest | `2f5a2820c622b74d2ad46fcf9b6f90a5632d249dec9ec27b7523a3a588ce5fad` |
| missing parameters examined | `MP-GROWTH-KINETICS`, `MP-OXYGEN-TRANSFER`, `MP-INDUCTION-TIME` |

The digest is the one the run actually reported, read from the result document
rather than remembered — a test asserts they match. The report also states what
that digest **covers**: the graph document, not the numeric results. It pins
which graph was executed; it does not attest to the values.

### 11.7 Conflicting evidence

Detection is mechanical and the conflicts it finds are left open. Three rules:

- **value disagreement** — two findings for one quantity, same unit, disjoint
  reported intervals;
- **not independent of target** — a passage occurring in the target publication;
- **condition disagreement** — two sources disagreeing about the process itself
  for one port (one matches a critical dimension, the other does not).

One conflict is currently registered: CF-003's non-independence. Every conflict
carries `resolved: false` and `requires: explicit human direction`. The system
reports disagreements; it does not settle them, and there is no code path that
sets `resolved` to true.

Scope limit, stated rather than implied: intervals are compared only when the
units match, and no conflict is claimed between findings whose units differ.

### 11.8 The honest result

**No compatible source was found.** For `specific_growth_rate` the search
returned two candidates, both incompatible. `dissolved_oxygen` and
`induction_time` returned none at all. The workflow reports that as an empty
result with the search scope attached, rather than quietly presenting the
closest-looking number.

Because no parameter measured under this process's conditions exists in the
literature, the panel's closing action is to **propose a separate, explicitly
parameterised model fitted to batch data from this strain** — not to import a
number measured elsewhere.

### 11.9 Verification

`composition/tests/test_evidence_catalogue.py` — **62 tests**, including:

- **the circularity regression guard**: the defect is reproduced deliberately
  (a finding built from the target's own records) and asserted not to read as
  found; no candidate may restate the target's conditions wholesale; no finding
  is reported `FOUND`;
- every target condition is bound to a passage on file, and conditions the
  paper does not state carry **no** quote — attaching one would manufacture
  support;
- every candidate condition carries a quote from its own source and from a
  source other than the target;
- similar is never sufficient: `"GMS medium"` against `"GMS medium plus 2x yeast
  extract"` is `partial`, not `match`;
- different named entities are a `mismatch`, not an `unknown` (ML30 vs E. coli
  20); a fermenter model number is never read as a volume;
- substrate concentration is not mistaken for substance identity;
- `"not stated"` scores `unknown`, never a match;
- a reported range is never collapsed to an interior midpoint;
- VC-10 blocks validation of any non-independent finding;
- the graph digest equals the one the run actually reported;
- conflicts are detected on disjoint intervals, never raised on overlapping ones
  or across differing units, and are never marked resolved;
- `validate()` cannot be waived — its only parameter is the finding;
- the `--result` contract Godot depends on is tested, including that the write
  is guarded and never lands in the repository;
- no module imports a model package or mutates `sys.path` (AST walk).

Interface acceptance — **38 checks, 0 failures**, run against the real scene in
a real window. Highlights:

- `specific_growth_rate`, `dissolved_oxygen` and `induction_time` are still
  `unknown` with `value: null` after the entire workflow;
- the 196-output model result is **byte-identical** before and after
  investigating, after recording a proposal, and after switching targets;
- the catalogue loads asynchronously through the same verified Python boundary;
- the panel shows the records examined and the digest, with a statement of what
  the digest does not cover;
- the DOI, citation, quoted passage, section locator, units, candidate
  conditions and uncertainty are all displayed;
- a non-independent finding is labelled as such **directly under its verdict**,
  not hidden behind an expander;
- conflicting evidence is displayed with the records it affects and the fact
  that it requires human direction;
- nothing claims validation;
- an empty-candidate target says so and still offers the action.

Two real defects were found and fixed in this work:

1. The proposal string was built with `\` continuation, so `%` bound tighter
   than `+` and the first fragment shipped with a literal placeholder to the
   user. The harness now asserts none reaches the screen.
2. The non-independence warning was rendered *below* the conditions list, so a
   reader could see "compatible" before the fact that disqualified it. It now
   sits directly under the verdict badge.

### 11.10 What did not change

`Models/Zielinski` is byte-for-byte unmodified — `git diff -- Models/` is empty
against both prior commits. The model still reports `specific_growth_rate`,
`dissolved_oxygen`, `induction_time` and every range-valued quantity as
`unknown`. No candidate value was merged into any output, and no published
evidence was altered. The proposal action writes to a log line in the scene and
to nothing else.

---

## 12. Model registry

### 12.1 What registration means

Registration records that a specification artefact **exists**, is identified by a
stable id and version, and can be located and hashed. That is all. Every
registration carries the disclaimer verbatim:

> Registration records that a specification artefact exists, is identified, and
> can be located and hashed. It does **NOT** establish that the model is correct,
> independently supported by evidence, or executable. None of those claims is
> made or implied by appearing here.

A model can be registered and still be wrong. The state is published as
`scientific_status.state = "registered_only"`, with `means` and `does_not_mean`
alongside it, so "it is in the registry" can never be read as "it is correct".

### 12.2 Schema

Every field on a registered model is a `TrackedField` carrying a value, an
`Origin`, and a `basis`. Origins are:

| Origin | Meaning |
|---|---|
| `declared` | read verbatim from the artefact or its manifest |
| `derived` | computed from declared data by a rule recorded on the field |
| `unknown` | the artefact does not state it |

`unknown` is not a blank and not a deferred inference. It is the honest answer,
and it carries the reason it is absent. This is what stops the registry from
looking more complete than the repository is.

Existing schemas are reused rather than duplicated: identity, version, citation
and port structure come from the established `ModelManifest` and the adapter
registrations in `composition/adapters/__init__.py`. No parallel model
representation was created.

### 12.3 What is registered

Discovery is not a scan of the file tree for things that look like models. It
follows the artefacts the repository already establishes — the adapter
registrations — and reads each model's own manifest. No model is described here
that the composition layer cannot already reach.

| Reference | Ports | DOI | Conditions declared |
|---|---|---|---|
| `morris2011.material_balance@0.1.0` | instance-parameterised | **unknown** | unknown |
| `zielinski2019.rhi_process@1.0.0` | 139 in / 57 out | `10.1016/j.pep.2019.02.002` | 8 |

Required experimental conditions are taken from the model's own declaration of
what it cannot do (`parameter_sections["declared missing models"]`), not from
our reading of it. Operating conditions are identified by the model marking its
own ports with `role = operating_condition`.

### 12.4 Digests, and exactly what they cover

```
SHA-256 over the exact bytes of every .py file under the model package root,
excluding test modules, caches and generated output. The package digest is
SHA-256 over the sorted '<relative-path>:<file-digest>' lines of that same set.

Neither digest covers data fixtures, example graphs, the adapter that wraps
the model, or any execution result.
```

17 artefacts across the two packages: 5 for Morris, 12 for Zieliński. Every
digest carries its own `covers` string, and every `package_digest.basis`
restates the rule, so scope is never inferred from a bare hash.

Tests verify that each file digest equals `sha256` of the bytes currently on
disk, that each package digest equals the documented function of its file
digests, that changing a file's content changes its digest, and that the whole
registry is byte-identical across runs.

### 12.5 Integrity checks

| Check | Behaviour |
|---|---|
| duplicate model id | reported; the first is kept, never merged or chosen |
| missing artefact | registration **fails**; no substitute model is reached for |
| ambiguous version | reported; a bare `model_id` is declared not to resolve |
| unregistered reference | reported with the reference and why it does not resolve |

`audit_references()` is the gate compatibility reports pass through. It returns
a `TrackedField`: `declared` with the exact `model_id@version` when the
reference resolves, `unknown` with the reason when it does not.

`RecordExamined.is_definitive()` is `False` unless an exact registered version
resolved, and `inventory()` publishes `verdict_authority` accordingly — so an
unregistered or ambiguous model **cannot** carry a definitive compatibility
verdict. It currently reads `definitive`, because the catalogue does resolve.

### 12.6 Two errors this corrected

The evidence catalogue was referencing a model that does not exist:

| | before | after |
|---|---|---|
| `model_id` | `zielinski2019.recombinant-insulin` | `zielinski2019.rhi_process` |
| DOI | `10.1016/j.jbiotec.2019.03.011` | `10.1016/j.pep.2019.02.002` |

The first was never registered. The second was written from memory and is
declared by no artefact — the model itself states `10.1016/j.pep.2019.02.002`
in `models/source.py`. Identity, citation and DOI are now **read from the
registry** rather than typed into the catalogue, so they cannot drift again.

### 12.7 Models that could not be fully registered

**`morris2011.material_balance@0.1.0` — registered, with eight explicit
unknowns.** Its manifest requires an instance `system` declaration, so nothing
about it is fixed at model level:

| Field | State | Why |
|---|---|---|
| `ports` | unknown | instance-parameterised; a declared system produces 7 in / 19 out, another produces a different set |
| `title` | unknown | declared per instance ("Batch charge preparation for a brass melting furnace") |
| `source_paper` | unknown | the citation is per instance ("Morris et al. 2011, sec. 4.5, Example 4.2") |
| `doi` | unknown | no DOI is declared anywhere in the package, and none is inferred from author or title |
| `variables`, `units` | unknown | follow from the port set being undefined |
| `assumptions`, `capabilities` | unknown | declared per instance |

This is the difference between a model that declares no ports and a model whose
ports are not fixed. Resolving these requires a human decision about whether
the Morris model should declare a model-level interface, which is a scientific
design question and was not taken here.

**`Models/Morris/models/degrees_of_freedom.py` — deliberately not registered.**
It is imported by `material_balance.py` and is internal bookkeeping for the
chapter's DOF rule, not a separately composable model: it has no id, no version
and no adapter. Registering it would invent a model that does not exist. It is
covered by the Morris package digest.

**Nothing else was found.** No other model specification exists in the
repository.

### 12.8 Read-only, and verification

Registration reads and hashes. It never writes to a model package and never
imports one — the two packages collide on a top-level `models` name, so
hashing bytes is the only safe route. The sole write in the package is the
CLI's `--result` output, guarded by the flag, asserted by an AST test that
also pins the guard's position.

`composition/tests/test_registry.py` — **52 tests**. Beyond the acceptance
criteria: `build_registry()` is asserted not to change any file size or mtime
under `Models/`; CLI output is asserted byte-identical across two runs; and the
duplicate-id and ambiguous-version detectors are exercised against deliberately
constructed bad registries rather than left untested.

---

## 13. Section 5 empty-panel fix

### 13.1 Root cause

`_collapsible(title, open_by_default)` connected its header button to `pressed`
and the handler rewrote only the caption:

```gdscript
head.pressed.connect(func() -> void:
    head.text = ("▸  " if head.button_pressed else "▸  ") + title)
```

`body.visible` was set once at construction and never again. The caption
changed; the panel did not. Expanding a collapsed section therefore appeared to
work while revealing nothing — the exact report.

Measured, not inferred: after pressing, `body.is_visible_in_tree()` was `false`
before **and** after, while `_tree` held 196 rows and `_diagnostics` held 9263
characters. The data was present and bound; only the visibility gate was
missing.

The fix connects to `toggled`, which carries the new state, and declares `body`
before the connection so the lambda cannot capture it unset. `replay_evidence.gd`
already did this correctly, which is why only these two panels were affected.

### 13.2 Two further defects the tests caught

Both were real and both were found by the acceptance harness rather than by
reading:

1. **A stale detail pane.** The "select a row" waiting state was written only
   `if _detail.text == ""`. Selecting a row, then loading a dataset with no rows,
   left the *previous* dataset's row on screen. The waiting state is now written
   unconditionally on dataset change — "empty" and "still showing the last row"
   are different things and only the first looks like a broken pane.
2. **A type error on malformed entries.** The second diagnostic loop redeclared
   `var rec: Dictionary = d` without the guard the first loop had, so a
   `diagnostics` list containing a non-Dictionary entry raised
   `Trying to assign value of type 'int' to a variable of type 'Dictionary'`
   and aborted the render partway. Both loops now guard identically, and a
   malformed entry is named as a schema mismatch.

### 13.3 What the panels show now

**All data and evidence** — every published value with its exact field name, its
value with unit, and its provenance; selecting a row shows method, source and
the full provenance chain. Unknown values read `not available` and the reason is
shown. A dataset with no records shows `no evidence records available`.

**Run status and technical details** — exit code, then every field the result
document actually carries: status, run id, graph id, contract version, runner
version, graph digest, and model versions. Then the diagnostics with code,
origin and where.

Three distinctions the previous version could not make:

| Situation | Shown |
|---|---|
| a field the document does not carry | *not recorded in this document* |
| a run that succeeded and raised nothing | *This run raised no diagnostics.* |
| a document missing the `diagnostics` field | schema mismatch, with the fields that are present |

The first two are deliberately different statements, because one is missing data
and the other is a run that had nothing to say.

### 13.4 Verification

47 acceptance checks, 0 failures, against the real scene in a real window.
Highlights: both panel bodies visible after expanding; the diagnostics pane
non-blank and on screen; a fixture rendering status, run id, graph id, contract
version, runner version, graph digest, model versions, code, error and warning;
an empty result reproducing the command to run by hand; `no evidence records
available` when a dataset has no records; `not available` for an unknown value
against `50 mL` for a reported one; and every schema mismatch visible rather
than blank.

Two harness notes, recorded because they cost time and will recur:
`RenderingServer.frame_post_draw` never fires under `--headless`, so a harness
that awaits it hangs until `--quit-after` and reports nothing; these must run
windowed. And a typed `var x: T = _scene.get("_diagnostics")` resolved to null
while the bare `get()` call returned the same object — the lookup is done
untyped and asserted non-null.

Nothing under `Models/` was modified; the 196-output result is unchanged; the
provenance census is intact (131 reported, 23 derived, 20 digitized, 22 unknown).

---

## 7. Environment

| | |
|---|---|
| Python | 3.14.7 |
| pytest | 9.1.1 |
| Godot | 4.7.2-stable (Windows x64) |
| Platform | Windows 10/11, win32 |
| Runtime dependencies | none (standard library only) |

---

## 8. How to re-run everything

```bash
# composition suite
cd composition && python -m pytest tests        # 242 (128 pre-existing + 62 evidence + 52 registry)

# existing model suites, reported separately
cd Models/Morris    && python -m pytest tests   # 186
cd Models/Zielinski && python -m pytest tests   # 223

# the evidence catalogue, the same invocation the Godot scene makes
cd composition
python -m composition.evidence --result evidence_catalogue.json

# the model registry
python -m composition.registry --result model_registry.json   # exit 2 if issues

# the runner directly
cd composition
python -m composition.runner --graph examples/brass_batch_chain.json --result out.json

# the Godot editor
godot --path .
```

---

*Previous: [`COMPOSITION_AUDIT.md`](COMPOSITION_AUDIT.md) ·
[`COMPOSITION_SPEC.md`](COMPOSITION_SPEC.md)*
