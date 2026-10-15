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
| **composition total** | **128 passed** |

The acceptance suite is organised as one class per criterion with a
`CG_COVERAGE` table that the suite checks for completeness, so a criterion
cannot be added without a class or a class without tests. The contract suite
pins the JSON boundary so a graph file's round trip is part of the public
interface rather than an internal detail.

### 2.3 Combined

| | |
|---|---|
| existing model suites | 409 |
| composition suite | 128 |
| **total** | **537 passed** |

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
cd composition && python -m pytest tests

# existing model suites, reported separately
cd Models/Morris    && python -m pytest tests   # 186
cd Models/Zielinski && python -m pytest tests   # 223

# the runner directly
cd composition
python -m composition.runner --graph examples/brass_batch_chain.json --result out.json

# the Godot editor
godot --path .
```

---

*Previous: [`COMPOSITION_AUDIT.md`](COMPOSITION_AUDIT.md) ·
[`COMPOSITION_SPEC.md`](COMPOSITION_SPEC.md)*
