# Multi-model composition in the Zielinski insulin replay

Date: 2026-10-30. Project: `D:\Godot\Scaleup AI\pilot`.

What was assessed, what was connected, what was not, and why. The short version:

> **No new dynamic connection is scientifically justified, and none was made.**
> All seven models are assessed (deliverable 1). The composed graph executes two
> independently runnable paper models in one run with full attribution (deliverable
> 5, 7). The baseline's 196 values are unchanged to the last digit (deliverable 7),
> and a graph that *does* try to connect Ganjave into the insulin process is
> refused by the engine (deliverable 4), so the separation is enforced rather than
> promised.

---

## 1. Compatibility assessment of all seven models

The authority is `composition/composition/compatibility.py`; it is data, not
prose. Run `python -m composition.compatibility` to reproduce the table below.

| # | Model | Class | Contributes | What decided it |
|---|---|---|---|---|
| 1 | **Zielinski 2019** — insulin process | **1. dynamically composable** | **yes (baseline)** | It *is* the simulation: a 15-operation process graph, 196 ports, evidence replay |
| 2 | **Ganjave 2022** — cybernetic fed-batch | 3. contextually relevant | no | Second *E. coli* fed-batch, but different substrate (glycerol), different biomass basis (dry vs wet), 3 L / 24 h vs 4 L pH-stat. `cross_model` stance: `refused_unclassified` |
| 3 | **Morris 2011** — material balances | 4. incompatible | no | A non-reacting control-volume engine, not an organism model. Zielinski publishes process roles, not conserved entities. Engine-enforced (`refused_component_identity`) |
| 4 | **Baez 2014** — oxygen-induced expression | 3. contextually relevant | no | Recombinant protein in *E. coli*, but induced by a dissolved-oxygen step instead of IPTG; W3110; 5 L / 37 °C; one printed feed equation and no ports |
| 5 | **Lin 2001** — uptake capacities | 3. contextually relevant | no | The closest scientific neighbour: it models the declining glucose/oxygen uptake capacity pH-stat feeding must manage. But W3110/RB791, 35 °C, mineral salt medium, uninduced plasmids — its states are another culture's |
| 6 | **Nanchen 2006** — maintenance and yield | 3. contextually relevant | no | Pirt's relation fitted to non-recombinant MG1655 in a 10 mL *chemostat*; the paper itself says maintenance and yield depend on temperature, medium and strain |
| 7 | **Simensen 2022** — biomass composition | 3. contextually relevant | no | A measured composition table, not a model: no inputs, no time, no dynamics, and a different condition from the target |

**Class 2 (`evidence_compatible`) is empty, and that is the finding rather than an
omission.** Every candidate fails the project's own identity dimensions (strain,
construct, medium, mode, scale) before any number could be entered as evidence, so
no comparison is implemented — a cross-condition comparison would produce a number
with no meaning. Each candidate records `evidence_check` naming what fails.

### What was inspected, on every candidate

`Inspection` carries nine axes per model — organism, operating context, inputs,
outputs, units, governing equations, parameters, time scale, assumptions — rendered
as the same nine rows in the UI. It is a field of the assessment, not a comment, so
two models can be compared row by row.

### Two findings worth stating separately

* **Ganjave and Morris verdicts are not restated here.** They are read from
  `cross_model.boundary_for(...)` at import time, and a test asserts the assessment
  equals the declared stance. If the engine's position changes, the assessment
  changes with it.
* **A matching unit is never treated as a connection.** `rejected_cross_model_insulin.json`
  contains three connections that are dimensionally perfect — `g/L → g/L`,
  `L → L`, `h → h` — and every one is refused.

## 2. New connections, and their scientific justification

**None. Zero dynamic connections were added.**

| Candidate | Dimensionally legal pair? | Why it is still not connected |
|---|---|---|
| Ganjave → Zielinski | yes (`g/L`, `L`, `h`) | Dry-cell weight is not wet biomass; a post-feed volume is not a `t = 0` charge; a 24 h integration horizon is not another process's growth duration. Refused by `cross_model`, enforced by the engine |
| Morris → Zielinski | no shared quantity | A balance cannot represent a reaction, and Zielinski publishes process roles rather than conserved components |
| Baez → Zielinski | no interface | Unregistered, publishes no ports; feeding `F(t)` would replace Zielinski's pH-stat law with another experiment's |
| Lin → Zielinski | would be `1/h`, `%`, `g/L` | Its `μ`, `qO` and `DOT` are the *state of its own culture* (W3110, 35 °C, mineral salt medium). Transferring them is exactly the cross-experiment transfer the brief forbids |
| Nanchen → Zielinski | would be `mmol/(gdw h)` | A chemostat-fitted maintenance coefficient for MG1655 is not a parameter of a fed-batch 20-IBA-1 process |
| Simensen → Zielinski | none | A static table has no dynamics and no port; Zielinski reports no biomass composition |

The two connections the project *does* permit are both same-model and predate this
work: `morris2011.material_balance -> morris2011.material_balance` and
`ganjave -> ganjave`. Neither touches the insulin process, and
`compatibility.summary()["connections_touching_target"] == []` asserts that.


## 3. Files added and changed

### New

| File | What it is |
|---|---|
| `composition/composition/compatibility.py` | The seven-model assessment as data: `Classification`, `Inspection`, `Assessment`, `ASSESSMENTS`, `permitted_connections()`, `compose_block()`, `compare_runs()`, integrity checks, CLI (`--check`, `--json`) |
| `composition/replay/zielinski_multimodel.json` | The composed graph: the insulin baseline beside an independently running Ganjave instance, **zero** connections |
| `composition/examples/rejected_cross_model_insulin.json` | Negative control: three dimensionally legal, scientifically refused connections |
| `composition/tests/test_compatibility.py` | 35 tests over the assessment |
| `composition/tests/test_multimodel_composition.py` | 18 tests over execution, attribution, baseline invariance and the refusal |
| `scripts/composition_panel.gd` | The Godot composition panel (assessment + connections + baseline-vs-composed comparison) |
| `reports/MULTIMODEL_COMPOSITION.md` | This document |

### Changed (small, additive)

| File | Change |
|---|---|
| `composition/composition/runner.py` | `--describe-compatibility`, `--compare-composition`, `compare_composition()`, and a `composition` attribution block added to every run payload |
| `composition/tests/conftest.py` | `rejected_cross_model_insulin.json` added to the documented example expectations |
| `scripts/runner.gd` | `describe_compatibility()`, `compare_composition()`, `composition_directory()` |
| `scripts/replay3d.gd` | New section 7 in the replay's right column: the composition panel, wired to its own runner |
| `scripts/main.gd` | A "Composition" tab in the workshop |

**Not changed:** `cross_model.py` (no new boundary), `adapters/__init__.py` (no
registration), `engine.py`, `contracts.py`, `report.py`, the three model packages,
`zielinski_replay.json`, and every existing example. `python -m composition.registry`
still lists exactly three models.

## 4. New adapters and tests

**No new adapter was written, because no new connection exists.** An adapter
without a permitted boundary would be dead code that implies a connection the
project refuses. The equivalent work is the assessment registry plus its checks.

Two properties are tested rather than asserted:

* `test_a_ganjave_to_insulin_connection_is_refused_by_the_engine` runs
  `rejected_cross_model_insulin.json` and requires exit 1, `status == "invalid"`,
  exactly three `connection.cross_model_refused` diagnostics each containing
  "dimensionally legal", and **no results at all** — nothing executed.
* `test_compare_runs_detects_a_real_value_difference` changes one value by
  `1e-4` and requires `identical: False`. Without it, "identical" would be a
  constant rather than a measurement.

## 5. The example composed graph

`composition/replay/zielinski_multimodel.json`:

```json
{
  "instances": [
    {"instance_id": "zielinski_baseline", "model_id": "zielinski2019.rhi_process",
     "model_version": "1.0.0", "parameters": {"execution": {"mode": "evidence_replay"}}},
    {"instance_id": "ganjave_context", "model_id": "ganjave",
     "model_version": "0.1.0", "parameters": {"simulation": {"duration_h": 24.0}}}
  ],
  "connections": [],
  "composition_scope": {"dynamic_connections_added": 0, "assessed_models": ["...seven keys..."]}
}
```

The Ganjave instance carries the same seven declared literal inputs as
`ganjave_fed_batch.json` (re-keyed, so the two files cannot drift), each with its
own `source_ref` and `method`. The insulin instance is configured exactly as in
`zielinski_replay.json`, which remains the baseline graph.



## 6. Godot interface

One new panel, used by two scenes. It renders payloads; it holds no rule.

**A. Model composition panel** (`CompositionPanel`) — every model assessed against
the process, numbered 1-5 with the brief's own classification, marked
**contributor** or **evidence only**, with its paper, its package and model id, the
one-line summary, every blocker ("why not"), and the `evidence_check` that
explains why even an evidence comparison was not attempted. Nine "what was
inspected" rows per model, collapsible; the raw record is one click away.

**B. Simulation graph** — the panel lists the validated dynamic connections the
engine permits and flags any that would touch the target. It reports "0 touching
the target" and never draws an edge the engine does not permit. Each card names the
originating paper, so a component's provenance is visible where the component is.

**C. Replay outputs** — a **Run baseline vs composed comparison** button executes
both graphs and renders: both statuses and exit codes, port counts, the differing
port list, an explicit `IDENTICAL` / `DIFFERENT` verdict, and per-instance
attribution with output counts and a contributor / co-executed marker.

Wiring: section 7 of the replay's right column; a "Composition" tab in the
workshop. The panel owns a **private** `CompositionRunner`, so its requests cannot
interleave with the scene's flag-demultiplexed introspection chain.

## 7. Execution results — baseline vs composed

```
$ python -m composition.runner --compare-composition
baseline   zielinski-replay       success_with_warnings   exit 0
composed   zielinski-multimodel   success_with_warnings   exit 0
values     196 baseline ports, 196 composed ports, 0 differing
           IDENTICAL
instances  zielinski_baseline  Zielinski et al. (2019)  contributor      196 outputs
           ganjave_context     Ganjave et al. (2022)    co-executed        6 outputs
```

What changes when the second instance is added: **only attribution**. The `ref`
and `provenance_chain` of each insulin output name the instance
(`zielinski_replay` → `zielinski_baseline`), which is why the comparison is
values-only (state, value, unit, quantity). Every one of the 196 values — reported,
digitized, computed, unknown and unresolved alike — is identical.

The 5 errors and 9 warnings in both runs are the Zielinski model's **own** findings
about its source (documented contradictions, unresolved targets). They are present
in the baseline and are unaffected by composition; the run status is
`success_with_warnings` in both cases.

The shipped individual graphs remain independently executable:
`zielinski_replay.json`, `ganjave_fed_batch.json` and `brass_batch_chain.json` are
untouched, and `test_an_individual_model_still_runs_on_its_own_graph` pins that.

## 8. Remaining limitations and incompatible models

* **The insulin process has no legal upstream or downstream model in this project.**
  Six of seven models are class 3, one is class 4, none is class 2. If that verdict
  is to change, the change has to be scientific: a model matched to 20 IBA 1 /
  pIBAINS in GMS, or an evidence source measured in that condition.
  Re-parameterising an existing paper's numbers for Zielinski would be fabrication,
  not composition.
* **Co-execution is not composition in the parameter-transfer sense.** The composed
  graph runs two models side by side with attribution; it does not make one feed the
  other. `composition.note` in every payload says so, and the panel repeats it.
* **The combined graph is not a validated system.** `report._combined_graph_block`
  keeps `independently_validated: false` for any combination; nothing here upgrades
  a model's `reproduction_status`.
* **Nanchen and Simensen are the closest to becoming useful**, and the gap is
  precise: Nanchen needs the same strain/medium/mode; Simensen needs a target
  quantity of the same kind *and* a matching condition. Neither is a coding gap.
* **The Godot scene was not executed here** (no Godot binary in this environment).
  The panel was written against the existing `CompatibilityPanel` /
  `CrossPaperPanel` patterns and the exact payload shapes the Python CLI emits and
  which are printed above; those payloads are covered by tests.
* **No web/pyodide path** was added for the new verbs. On Web the panel shows
  "could not be read", which `CompositionRunner` already returns for a Web build.

## Definition of success

Open the Zielinski replay in Godot → section 7 lists all seven models with their
classifications, each with the paper it comes from and the reason it cannot be
connected → press **Run baseline vs composed comparison** → the panel reports
`IDENTICAL` over 196 values and names each instance's paper. The original replay is
still one click away and numerically unchanged.

