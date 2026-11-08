# Godot Model Visibility — Root-Cause Diagnosis

> **Resolved.** Causes A and B are fixed: `scripts/model_palette.gd` and
> `scripts/instance_form.gd` are restored, the palette is always visible above
> the canvas, and every registered model can be added, configured, run and
> inspected without a command line or a model-specific replay button. Cause C is
> unchanged and deliberate: Baez remains unregistered with the composition
> layer. See `reports/GODOT_MODEL_PALETTE_IMPLEMENTATION.md`. The sections below
> are kept as the record of what was wrong and where, and their file references
> describe the pre-fix state.

**Date:** 2026-10-19
**Scope:** Why the Godot application presents a Zieliński simulation when the
repository contains Morris, Zieliński, Baez and Ganjave implementations.
**Status of this document:** diagnosis only. No UI, contract, equation,
parameter or solver behaviour was changed to produce it.

---

## 1. Executive summary — confirmed root causes

There are **three independent causes**, not one. Only the first two are UI
defects; the third is a deliberate, test-enforced architectural decision.

| # | Root cause | Kind | Affected models |
|---|---|---|---|
| **A** | The model palette is gone. `scripts/model_palette.gd` was deleted and `Add model` is a dialog that says so. The registry is therefore never turned into anything a user can click. | UI defect | Morris, Ganjave (and any future model) |
| **B** | The only purpose-built, self-executing, model-specific view in the entire application is hard-wired to Zieliński (one graph constant, one instance-id constant, and a bypass of `ModelRegistry`). | UI defect / asymmetry | Zieliński is favoured; no equivalent exists for the others |
| **C** | Baez is **not registered with the composition layer at all**. It is absent from `REGISTRATIONS`, the single source of discovery. | Missing implementation (deliberate, test-enforced) | Baez |

**The headline correction to the premise:** the main scene is *not* a Zieliński
replay. `run/main_scene` is `res://scenes/composition.tscn`, a **model-agnostic
graph editor** that opens on an **empty canvas**. What happens in practice is:

* at launch the canvas has **0 instances and 0 nodes drawn**;
* the only place the discovered model list appears is a single **status-line
  string** — `Ready | models: morris2011.material_balance@0.1.0,
  zielinski2019.rhi_process@1.0.0, ganjave@0.1.0` — not a selectable list;
* the only button that produces a "simulation-like" screen is
  **`3D replay`**, whose own tooltip reads *"Open the 3D replay of the
  Zielinski process (a separate scene)"*.

So the application does not *hard-code* Zieliński as its only model. It is that
Zieliński is the **only model with a dedicated scene**, while the generic path
that would have made Morris and Ganjave equally reachable (the palette) was
removed. The visible result is a Zieliński-shaped application.

**Morris and Ganjave are already selectable in the main scene** — through the
*Load example* dropdown. That is a **discoverability problem, not missing
implementation**. Ganjave was confirmed executing through the real *Run*
button during this investigation (section 6).

---

## 2. Startup scene and navigation path

```
project.godot:14   run/main_scene="res://scenes/composition.tscn"
scenes/composition.tscn:3   ext_resource Script "res://scripts/main.gd"
```

`scripts/main.gd:37-41` — startup sequence:

```gdscript
func _ready() -> void:
    _detect_environment()   # locate <repo>/composition, set python
    _build_ui()             # ModelRegistry + CompositionRunner + panels
    _load_examples()        # populate the "Load example" dropdown
    _registry.load()        # -> python -m composition.runner --list-models
```

**No example graph is auto-loaded and no model is auto-placed.** The canvas
starts empty.

### Navigation map

```
res://scenes/composition.tscn  (MAIN)
├── toolbar "Load example:"  OptionButton          main.gd:182-185, 217-233
│      └── 8 hard-coded *.json files from res://composition/examples
│          ├── brass_batch_chain.json      → Morris ×2 + Zieliński   (runs)
│          ├── ganjave_fed_batch.json      → Ganjave                (runs)
│          ├── cycle_rejected.json         → Morris                 (refused, by design)
│          ├── failure_propagation.json    → Morris                 (fails, by design)
│          ├── incomplete_required_input.json → Morris               (fails, by design)
│          ├── rejected_au_to_mass.json    → Morris + Zieliński     (invalid, by design)
│          ├── rejected_component_mapping.json → Morris + Zieliński (invalid, by design)
│          └── rejected_mass_as_flow.json  → Morris + Zieliński     (invalid, by design)
│
├── toolbar "Add model"    Button                  main.gd:187-191  ──► STUB (cause A)
│      └── ConfirmationDialog "Model palette not implemented in this version."
│
├── toolbar "3D replay"    Button                  main.gd:198-202
│      └── change_scene_to_file("res://scenes/replay3d.tscn")   main.gd:323-324
│             └── res://scenes/replay3d.tscn → scripts/replay3d.gd
│                   • hard-bound to res://composition/replay/zielinski_replay.json  (replay3d.gd:27)
│                   • hard-bound to instance id "zielinski_replay"                  (replay3d.gd:28)
│                   • bypasses ModelRegistry / GraphDocument / ProcessCanvas        (verified: 0 references)
│             └── "Back to graph editor" → change_scene_to_file("res://scenes/composition.tscn")
│
└── toolbar "Open graph..." FileDialog (user://graphs, *.json)   main.gd:209-212, 327-335
```

**There are exactly two scenes.** `scenes/` contains only `composition.tscn`
and `replay3d.tscn`. There is no scene-switching menu, no scene list, and no
other entry point.

---

## 3. Four-model availability matrix

Legend: **PASS** = works as described · **FAIL** = does not work ·
**PARTIAL** = works but only through a reduced path · **NOT IMPLEMENTED** =
deliberately absent, with the absence recorded.

| # | Criterion | Morris | Zieliński | Baez | Ganjave |
|---|---|---|---|---|---|
| 1 | Scientific model files exist | **PASS** `Models/Morris/{models,schemas}` | **PASS** `Models/Zielinski/{models,scaleup_ai}` | **PASS** `Models/Baez/baez2014` | **PASS** `Models/Ganjave/{models,schemas}` |
| 2 | Python importable & executable | **PASS** 186 tests | **PASS** 223 tests | **PASS** `feed_rate(t=6,t_F=5,X_F=10,V_F=4)` → `0.1584 L/h`; 193/195 tests | **PASS** 331 tests |
| 3 | Composition contract exists | **PASS** `adapters/morris.py` | **PASS** `adapters/zielinski.py` | **NOT IMPLEMENTED** no adapter file exists | **PASS** `adapters/ganjave.py` + `ganjave_contract.py` |
| 4 | Adapter + worker registered | **PASS** `adapters/__init__.py:43-49` + `_workers/morris_worker.py` | **PASS** `adapters/__init__.py:50-56` + `_workers/zielinski_worker.py` | **NOT IMPLEMENTED** absent from `REGISTRATIONS` | **PASS** `adapters/__init__.py:61-67` + `_workers/ganjave_worker.py` |
| 5 | In runtime discovery output | **PASS** `--list-models` | **PASS** `--list-models` | **FAIL** absent | **PASS** `--list-models` |
| 6 | Exposed in the Godot model palette | **PARTIAL** no palette exists; reachable via 5 example graphs | **PARTIAL** same + dedicated 3D replay scene | **FAIL** no palette, no example | **PARTIAL** no palette; reachable via 1 example graph |
| 7 | Runnable example graph exists | **PASS** 5 graphs | **PASS** 3 graphs + `composition/replay/zielinski_replay.json` | **NOT IMPLEMENTED** none | **PASS** `ganjave_fed_batch.json` |
| 8 | Graph loads & validates | **PASS** `brass_batch_chain` → `success_with_warnings` | **PASS** `brass_batch_chain` → `success_with_warnings` | **n/a** | **PASS** `--plan-only` exit 0 (`ganjave_graph_run.gd` check 2) |
| 9 | Executes through the **actual Godot UI** | **PASS** via Load example + Run | **PASS** via Load example + Run, and via 3D replay | **NOT IMPLEMENTED** | **PASS** confirmed live — section 6 |
| 10 | Results / trajectories / provenance / warnings / status displayed | **PASS** Results + Provenance tabs | **PASS** Results + Provenance tabs; replay scene sections 1–5 | **NOT IMPLEMENTED** | **PASS** Results tab populated, 6/6 outputs carry an 8-record provenance chain, status `Executed with 1 warning(s)` |

### Per-model detail

**`morris2011.material_balance@0.1.0`** — `port_dependence = "instance"`.
`--describe-model` returns exit 0 with the model's own refusal:
*"instance parameters must contain a 'system' declaration … got keys []"*
(`composition/composition/adapters/morris.py`). This is correct, not a defect.
Consequence for the UI: a Morris node can only draw ports once the graph
instance carries an inline control volume, via branch 3 of
`scripts/model_node.gd:128-168` (`ports_source = "instance_parameterised"`).

**`zielinski2019.rhi_process@1.0.0`** — `port_dependence = "fixed"`,
**196 ports (139 input / 57 output)**, 8 declared missing models, 0 unknown
fields. Fully present.

**`baez2014`** — **not a member of the composition boundary at all.**
`--describe-model baez2014.oxygen_induced` exits 3 with
*"no model is registered under the id 'baez2014.oxygen_induced'. Nothing was
substituted: the composition layer does not guess which model was meant."*
(`composition/composition/adapters/__init__.py:120-133`).

**`ganjave@0.1.0`** — `port_dependence = "fixed"`, **15 ports (9 input / 6
output)**, 1 unknown field (`doi`). Fully registered and executable; it simply
has no palette entry and one example graph.

---

## 4. Model discovery and registration — where each model drops out

### The discovery chain (all of it, in order)

| Stage | File | Behaviour |
|---|---|---|
| 1 | `composition/composition/adapters/__init__.py:42-68` | `REGISTRATIONS` — a **hand-declared tuple**. Not filesystem discovery. This is the root list. |
| 2 | `composition/composition/adapters/__init__.py:92-134` | `adapter_for(model_id)` — resolves an id to an adapter; refuses with a named list of registered ids. |
| 3 | `composition/composition/adapters/__init__.py:137-159` | `known_models()` — what `--list-models` emits; `available = (root/"pyproject.toml").is_file()`. |
| 4 | `composition/composition/registry/builder.py:263-285` | `build_registry()` — iterates `REGISTRATIONS`, hashes artefacts, builds manifests. |
| 5 | `composition/composition/runner.py` | `--list-models`, `--describe-model`, `--describe-contract`, `--graph/--result`, `--plan-only`. |
| 6 | `scripts/runner.gd:85-107` | `list_models()` / `describe_model()` / `describe_contract()` — `OS.execute` on `python -m composition.runner …`, JSON parsed from merged stdout. |
| 7 | `scripts/model_registry.gd:51-58, 100-131` | `_on_list_models()` → `models` array → `_by_id` → `models_loaded`. |
| 8 | `scripts/main.gd:392-402` | `_on_models_loaded()` — **the only consumer**. Renders the ids into one status-line string. |
| 9 | `scripts/main.gd:274-286` | `_on_add_pressed()` / `_on_add_confirmed()` — **the palette. It is a stub.** |

### Findings for each question asked

* **Does the registry enumerate all available models, or use a fixed list?**
  A fixed, hand-declared list: `REGISTRATIONS` (step 1). Adding a model means
  adding a row there — as its own docstring states (line 40-41).

* **Is the palette dynamic or hard-coded?**
  **Neither — it does not exist.** `scripts/model_palette.gd` was deleted; this
  is recorded in the project's own validation report
  (`composition/VALIDATION_REPORT.md:274-276`: *"scripts/model_palette.gd was
  removed during earlier debugging and the button opens a dialog saying so.
  Example graphs are the only way to populate a graph."*) and in
  `README.md:344`.

* **Do model ids differ between Python contracts and the Godot registry?**
  **No.** The Godot side has no list of its own; it is whatever
  `--list-models` returns. There is no id drift. (Verified: the live status
  line shows exactly the three registered ids.)

* **Is Baez or Ganjave registered in Python but absent from the Godot registry?**
  **Ganjave: no, it is present everywhere** (Python registry, `--list-models`,
  the live Godot status line, and the example picker). **Baez: it is not
  registered in Python in the first place**, so there is nothing for Godot to
  miss.

* **Does scene initialisation filter models by category, status or
  compatibility?**
  **No filtering of any kind.** `_on_list_models()` (`model_registry.gd:100-131`)
  keeps every entry that is a `Dictionary` with a non-empty `model_id`, and
  discards the rest. Nothing is filtered by category, availability or
  compatibility. The Godot UI is not hiding any model.

* **Do resource paths, working directories or file extensions prevent
  discovery?**
  **No.** The probe read all 8 example files through `DirAccess.open()`;
  `PYTHONPATH` is exported by `scripts/runner.gd:120-132`; the composition
  package is located by `main.gd:44-68` relative to the project root.

### Exact drop-out point per model

| Model | Last stage reached | First stage missed |
|---|---|---|
| Morris | stage 8 (status line) + 5 example graphs | stage 9 (palette — missing for every model) |
| Zieliński | stage 8 + stage 9's replacement (dedicated scene) | — nothing; plus a private bypass of stages 6–8 |
| Ganjave | stage 8 + 1 example graph; **verified executing** | stage 9 (palette — missing for every model) |
| **Baez** | **never enters stage 1** | **`composition/composition/adapters/__init__.py:42` — the `REGISTRATIONS` tuple.** Everything downstream is unreachable by construction. |

---

## 5. Is the Zieliński result dynamically executed or replayed?

**Both — and the distinction matters.** Precisely:

### It IS dynamically executed

`scripts/replay3d.gd:617-637` builds and launches a real subprocess:

```gdscript
var argv := _runner.prepare(PackedStringArray([
    "-m", "composition.runner",
    "--graph", GRAPH_PATH,          # res://composition/replay/zielinski_replay.json
    "--result", _result_path,       # user://results/zielinski_replay.result.json
]))
var pid := OS.create_process(_runner.python_executable(), argv)
```

The scene then reads the result **off disk** (`replay3d.gd:658`,
`runner.gd:326-344`). **No number is hard-coded in GDScript.** The scene is
driven by named output ports declared as constants (`replay3d.gd:51-74`:
`KEY_CONDITIONS`, `KEY_GROWTH`, `KEY_PURIFICATION`, `KEY_ABSENT`) that name
`node:N01#starting_medium_volume`, `stream:S02_culture_broth#od600_25_crossing_h`, etc.

**Proof by perturbation (run, not inferred).** A copy of the replay graph with
`execution.mode` changed `evidence_replay → predictive`:

```
z_baseline   : status=success_with_warnings  outputs=196  resolved=174  unresolved=22
z_predictive : status=success_with_warnings  outputs=176  resolved=154  unresolved=22
```

The output set changed. The scene is reading a live model, not a cached table.

### It IS a replay in the scientific sense

The animated growth curve is a **digitised figure**, read by the Python model
from `Models/Zielinski/models/data/fig3_growth_trajectory.json` (19 marker
points, loaded at `Models/Zielinski/models/source.py:58`). The timeline widget
is a **cursor interpolated over that published series**
(`replay3d.gd:772-800`); nothing integrates an ODE. The project says this
itself, and the UI states it on screen (`replay3d.gd:2-11`, 291-299).

**Second nuance, measured:** injecting a declared literal input into the replay
graph did **not** change the reported operating conditions —

```
zielinski_replay (baseline)   starting_medium_volume = 4.0 L   wet_biomass_g_per_L = 56.0
zielinski_replay (+literal 9.9 L on node:N01#starting_medium_volume)
                              starting_medium_volume = 4.0 L   wet_biomass_g_per_L = 56.0
```

This is correct behaviour, not a bug: the model's operating conditions are
transcribed constants, and in `evidence_replay` with no declared inputs the
worker deliberately re-uses the run the manifest was built from
(`composition/composition/_workers/zielinski_worker.py:312-318`).

### It is also *structurally* a dedicated replay

`scripts/replay3d.gd` contains **zero** references to `ModelRegistry`,
`GraphDocument` or `ProcessCanvas`. It constructs its own
`CompositionRunner` (`replay3d.gd:131`) and reads the result directly. **It does
not go through the general registry/palette/canvas path at all.**

**Classification:** the Zieliński view is *dynamically executed through the
composition runner and the real Python model*, inside a *dedicated,
hard-bound replay scene that bypasses the general model registry*, displaying
*transcribed/digitised published data rather than a simulation*. Only two of
those four statements would be safe to make about any other model, and none of
them would be safe to make about the graph editor.

---

## 6. Reproduction — the actual main scene, actually launched

Godot is installed but **not on `PATH`**:
`D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe`
(4.7.2.stable.official.ed1daf0bf). `reports/GANJAVE_GODOT_EXECUTION.md:51-57`
claims "Godot not installed" — that is wrong for this machine.

A read-only probe was added to drive the **real scene and the real controls**
(no Python called directly): `composition/tests/godot/ui_visibility_probe.gd`.

```powershell
cd "D:\Godot\Scaleup AI\pilot"
D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe `
  --headless --path . --script res://composition/tests/godot/ui_visibility_probe.gd
```

### 6.1 What the main scene shows at launch

```
=== 1. MAIN SCENE AT LAUNCH (res://scenes/composition.tscn) ===
--- widgets carrying user-visible text ---
- Button  text="Run"            tooltip="Validate and execute the graph with the Python runner"
- Button  text="Validate only"  tooltip="Order the graph and produce a plan without executing anything"
- Label   "Load example:"
- ExamplePicker [OptionButton] selected=0 items=9
- Button  text="Add model"      tooltip="Place a model instance on the canvas"
- Button  text="New graph"
- Button  text="3D replay"      tooltip="Open the 3D replay of the Zielinski process (a separate scene)"
- Button  text="Save graph"
- Button  text="Open graph..."
- Label   "drag from an output port to an input port to connect them"
- TabContainer tabs=["Inspector", "Validation", "Results", "Provenance"]
- Label   "Provenance"
- Label   "Select a value in the results panel to trace it back to the model that produced it."
- Label   "Ready  |  models: morris2011.material_balance@0.1.0, zielinski2019.rhi_process@1.0.0, ganjave@0.1.0"
- ProgressBar visible=false

--- startup state ---
graph_id                 : untitled
instances on the canvas  : 0
connections on the canvas: 0
canvas nodes drawn       : 0

--- what 'Add model' actually does when pressed ---
dialog text              : Model palette not implemented in this version. Use the example graphs instead.

--- example picker contents ---
  [0] (choose an example)   [1] brass_batch_chain   [2] cycle_rejected
  [3] failure_propagation   [4] ganjave_fed_batch   [5] incomplete_required_input
  [6] rejected_au_to_mass   [7] rejected_component_mapping   [8] rejected_mass_as_flow
```

Observations:

* **The three registered models are visible only as text in the status line.**
  No widget anywhere enumerates them for selection.
* The dropdown offers **file basenames only**. A user cannot tell from the menu
  that `ganjave_fed_batch` is the Ganjave model, or that four of the eight
  entries are deliberate failures. This is the discoverability defect in its
  sharpest form.
* Pressing *Add model* yields a dialog whose text is the diagnosis itself.

### 6.2 Driving the real controls — Ganjave executes through the main scene

The probe selects `ganjave_fed_batch` **in the picker** and then invokes the
**real `_on_run_pressed()` handler** (the one the *Run* button is wired to):

```
=== 2. AFTER CHOOSING 'ganjave_fed_batch' IN THE EXAMPLE PICKER ===
graph_id                 : ganjave_fed_batch
instances on the canvas  : 1
connections on the canvas: 0
  node: ganjave_fed_batch  model=ganjave@0.1.0  label=Cybernetic fed-batch culture, 24 h
canvas nodes drawn       : 1
status line              : Loaded ganjave_fed_batch.json  (1 instance(s), 0 connection(s))

=== 3. AFTER PRESSING THE REAL 'Run' BUTTON ===
status line              : Executed with 1 warning(s)  [ganjave_fed_batch]
result payload status    : success_with_warnings
error_count / warnings   : 0 / 1
  instance ganjave_fed_batch (model ganjave): status=success_with_warnings
      outputs=6  with provenance chain=6
    biomass_concentration          = 8.35507897141973  g/L  (derived)
    glycerol_concentration         = 22.3049321882784  g/L  (derived)
    complex_substrate_concentration= 0.08234821227136  g/L  (derived)
    dissolved_oxygen               = 67.1077473140123  %    (derived)
diagnostics surfaced     : 4
results panel tabs       : ["@TabContainer@216", "  -> ganjave_fed_batch (1 rows)"]
```

**Verdict: Ganjave is fully executable and fully displayed through the actual
main scene.** It is a discoverability problem only.

### 6.3 Perturbation — the pipeline is live, not cached

`ganjave_fed_batch.json` with one valid declared input changed
(`feed_flow_rate` 0.72 → 1.44 mL/h), same argv the scene builds:

```
biomass_concentration           8.355078971  →  13.978283844   g/L
glycerol_concentration         22.304932188  →  37.753608956   g/L
complex_substrate_concentration 0.082348212  →   0.095017197   g/L
dissolved_oxygen                67.107747314  →  40.925255319   %
culture_volume                  0.112960000  →   0.125920000   L
```

Both `success_with_warnings`, exit 0.

### 6.4 Existing harnesses, re-run

| Harness | Result |
|---|---|
| `contract_boundary.gd` | `contract-boundary: 840 checks passed` (exit 0) |
| `ganjave_graph_run.gd` | `ganjave-graph-run: 51 checks passed` (exit 0) |

`contract_boundary.gd:92-113` asserts ≥2 discovered models, that `ganjave` is
present, and — at line 113 — that **`baez2014.oxygen_induced` must NOT be
discovered**. That last assertion passing is the positive confirmation of cause C.

### 6.5 Regression status (all suites re-run)

| Suite | Result |
|---|---|
| `composition` | **399 passed** |
| `Models/Morris` | **186 passed** |
| `Models/Zielinski` | **223 passed** |
| `Models/Baez` | **193 passed, 2 failed** — see §9 |

---

## 7. Source-level summary of the failures

### Cause A — the palette (UI defect)

```gdscript
# scripts/main.gd:274-286
func _on_add_pressed() -> void:
    var dialog := ConfirmationDialog.new()
    dialog.title = "Add Model Instance"
    dialog.dialog_text = "Model palette not implemented in this version. Use the example graphs instead."
    ...
func _on_add_confirmed() -> void:
    _status.text = "Model palette not implemented. Load an example graph instead."
```

The hook a palette would have used is still there, **with no emitter anywhere**:

```gdscript
# scripts/main.gd:288-296
func _on_instance_requested(model_id, model_version, label, role, parameters) -> void:
    var inst := _document.add_instance(model_id, model_version, label, role, position, parameters)
    _canvas.add_node(inst)
```

A whole-repository search for `instance_requested` returns **exactly one hit:
this definition**. Nothing connects to it. This is dead code left behind by the
deleted palette, and it is the ready-made seam for restoring one.

Corroborating in-repo acknowledgements:
* `composition/VALIDATION_REPORT.md:274-276` — palette removed, documented.
* `README.md:344` — *"The 'Add model' palette is a placeholder; load an example graph instead."*
* `reports/GANJAVE_GODOT_EXECUTION.md:279` — *"No model palette in UI | Users must load example graphs | Documented limitation; not a regression"* — **this last judgement is wrong**; it is a regression in discoverability, it is documented as a *placeholder*, and it is the direct cause of this investigation.

### Cause B — the Zieliński asymmetry (UI defect)

```gdscript
# scripts/main.gd:198-202
replay_button.text = "3D replay"
replay_button.tooltip_text = "Open the 3D replay of the Zielinski process (a separate scene)"
replay_button.pressed.connect(_on_replay_pressed)

# scripts/replay3d.gd:27-28
const GRAPH_PATH := "res://composition/replay/zielinski_replay.json"
const INSTANCE_ID := "zielinski_replay"
```

There is no `replay_morris`, no `replay_ganjave`, and no generic
"replay whatever graph is loaded" scene. The one visualisation the project
invested in names one model.

### Cause C — Baez (not a UI defect)

```python
# composition/composition/adapters/__init__.py:42-68
REGISTRATIONS = (
    AdapterRegistration(model_id="morris2011.material_balance", ...),
    AdapterRegistration(model_id="zielinski2019.rhi_process", ...),
    AdapterRegistration(model_id="ganjave", ...),      # <- no Baez row
)
```

Deliberately excluded and actively guarded:

| Guard | File | What it asserts |
|---|---|---|
| GDScript | `composition/tests/godot/contract_boundary.gd:109-113` | `not ids.has("baez2014.oxygen_induced")` — *"Baez is deliberately unregistered."* |
| Python | `composition/tests/test_acceptance.py:1317-1335` | `assert "baez" not in completed.stdout.lower()` — *"Baez remains unregistered, which is a separate decision that has not been taken."* |
| Model self-declaration | `Models/Baez/README.md:138` | *"coupling to the Morris or Zieliński models — out of scope … no adapter is registered and no identifier is guessed"* |
| Model manifest field | `baez2014.manifest.build_manifest()["registration"]` | `{"registered_in_composition_registry": false, "reason": "…not guessed"}` |
| Model tests | `Models/Baez/tests/test_exclusions.py:304-332` | three isolation guards (see §9) |

---

## 8. Minimal changes needed to expose each model

Nothing below alters an equation, a parameter, a solver, a contract or a
connection-refusal rule.

### Morris — **UI only, no backend work**

Already registered, discovered, executable and displayed. To make it visible:

1. **Cheapest (≈20 lines).** Change `_load_examples()` (`main.gd:217-233`) to
   label each dropdown entry with the models it contains, e.g.
   `"ganjave_fed_batch  —  ganjave@0.1.0"` and
   `"brass_batch_chain  —  morris + zielinski"`, read from each file's
   `instances[].model_id`. **This alone makes Morris and Ganjave discoverable
   with zero risk.**
2. **Proper.** Restore `scripts/model_palette.gd`, driven by
   `_registry.models` / `registry.model_ids()` (`model_registry.gd:198`), and
   connect it to the existing `_on_instance_requested` seam (`main.gd:288`).
   The registry, the manifest loader and `ModelNode` all already work — this is
   purely the missing UI layer.
   *Caveat that must be honoured:* Morris is `port_dependence = "instance"`, so
   the palette must let the user supply an inline `system` control volume,
   otherwise the node will legitimately draw zero ports.

### Ganjave — **UI only, no backend work**

Already registered, discovered, executable and **confirmed running through the
main scene** (§6.2). The identical two UI changes above apply. No scientific or
composition change is needed or warranted.

### Zieliński — **nothing**

Already fully present: registered, 196 fixed ports, two example graphs, and a
dedicated scene. Optional symmetry work (a generic replay scene parameterised
by graph id) is a design change, not a defect fix, and is out of scope here.

### Baez — **five backend steps before any UI can show it**

In dependency order:

1. `composition/composition/_workers/baez_worker.py` — a subprocess worker
   calling `baez2014.feed_rate()` and the observations, returning the same
   envelope as the other two workers. (Subprocess isolation is mandatory:
   `Models/Baez` is importable standalone, but Morris and Zieliński both ship a
   top-level `models` package — `VALIDATION_REPORT.md:252-255`.)
2. `composition/composition/adapters/baez.py` — an adapter publishing a
   `ModelManifest`. Its natural ports are the four run inputs
   (`X_F` mass_concentration, `V_F` volume, `t_F` time, `t` time) and the
   output `F(t)` volume_flow. The quantity mapping must land in
   `composition/composition/quantities.py` / `dimensions.py` first.
3. `composition/composition/adapters/__init__.py:42` — add the
   `AdapterRegistration` row. **This is the line that must change**; nothing
   downstream can see Baez until it does.
4. `composition/examples/baez_*.json` — a runnable graph declaring the four
   required inputs as literals, each carrying its own `source_ref` and the
   model's stated reason for having no default.
5. Update the five guards that currently assert Baez is absent:
   `contract_boundary.gd:113`, `test_acceptance.py:1330-1335`,
   `test_exclusions.py:304,312-316,319-332`, and the Baez README/manifest text.

Each of these is a scientific-adjacent decision, not a UI one, and should not
be taken as a side effect of making a menu item appear.

---

## 9. Model-specific blockers, separated from UI defects

These are **not** bugs and must not be "fixed" by the UI work:

* **Baez's inputs are unvalued by the paper.** `X_F`, `V_F`, `t_F` and `t` have
  no defaults and no printed values (`Models/Baez/README.md:61-68`,
  280-282). Any future graph must declare them as explicit, sourced
  assumptions. There is also no growth law, no DO balance, no oxygen-transfer
  model, no FU→GFP-mass calibration and no digitised series
  (`README.md:126-138`) — seven recorded absences.
* **Morris has no model-level fixed port set** (`port_dependence = "instance"`).
  A palette must not synthesise ports for it; `ModelNode` already refuses to
  (`model_node.gd:128-136`). A naive palette would show Morris with no ports
  and look broken.
* **Neither Zieliński nor Ganjave carries component identity.** Both declare
  `component_identity` as an unsupported capability, and both state it in their
  own manifest text. Neither can legally feed a component-declaring Morris
  control volume — which is exactly why `brass_batch_chain.json` reports
  warnings rather than a clean success. **This must not be relaxed.**
* **Ganjave's `reproduction_status` is `not_yet_validated`** and must stay so.
  A run through the UI demonstrates *software integration*, not scientific
  validation. `ganjave_graph_run.gd:152-161` asserts this claim survives the
  boundary.
* **Zieliński is an evidence replay**, not a predictive model; the UI says so on
  screen and the wording must not be softened.

### Pre-existing regression found during this investigation (unrelated to the UI)

Two tests in `Models/Baez/tests/test_exclusions.py` now fail:

* `test_no_adapter_worker_was_added_for_this_model` (line 312) asserts
  `workers == ["morris_worker.py", "zielinski_worker.py"]`
* `test_the_composition_registry_lists_only_the_pre_existing_models` (line 319)
  asserts the registry lists exactly `["morris2011.material_balance",
  "zielinski2019.rhi_process"]`

Both are **stale hard-coded counts written before Ganjave was registered**. They
fail *because* Ganjave now exists, not because Baez was registered — confirmed
by `contract_boundary.gd:113` passing (Baez correctly absent) and by
`test_acceptance.py:1330-1335` passing. `reports/GANJAVE_GODOT_EXECUTION.md:47-49`
and `:234` describe them as "expected failures"; they are not expected, they are
a regression in the test suite. **Left unmodified by this diagnosis**, as the
brief requires, but flagged.

---

## 10. Evidence index

### Commands run

```powershell
# Python discovery / registry / examples
cd composition; $env:PYTHONPATH=(Get-Location).Path
python -m composition.runner --list-models
python -m composition.runner --describe-model morris2011.material_balance
python -m composition.runner --describe-model zielinski2019.rhi_process
python -m composition.runner --describe-model ganjave
python -m composition.runner --describe-model baez2014.oxygen_induced
python -m composition.registry
python -m composition.runner --graph examples/<each>.json --result <out>

# Real Godot, real main scene
D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe --headless --path . `
  --script res://composition/tests/godot/ui_visibility_probe.gd
D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe --headless --path . `
  --script res://composition/tests/godot/contract_boundary.gd
D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe --headless --path . `
  --script res://composition/tests/godot/ganjave_graph_run.gd

# Regression suites
cd composition      ; python -m pytest tests -o addopts= --tb=no -q   # 399 passed
cd Models\Morris    ; python -m pytest tests -o addopts= --tb=no -q   # 186 passed
cd Models\Zielinski ; python -m pytest tests -o addopts= --tb=no -q   # 223 passed
cd Models\Baez      ; python -m pytest tests -o addopts= --tb=no -q   # 193 passed, 2 failed
```

### File index

| Path | Relevance |
|---|---|
| `project.godot:14` | `run/main_scene="res://scenes/composition.tscn"` |
| `scenes/composition.tscn:3` | → `scripts/main.gd` |
| `scenes/replay3d.tscn:3` | → `scripts/replay3d.gd` |
| `scripts/main.gd:274-286` | **Cause A** — palette stub |
| `scripts/main.gd:288-296` | dead `_on_instance_requested` seam (0 emitters) |
| `scripts/main.gd:198-202, 323-324` | **Cause B** — Zieliński-only replay button |
| `scripts/main.gd:217-233` | example picker, filename-only labels |
| `scripts/main.gd:392-402` | the only consumer of the model list |
| `scripts/replay3d.gd:27-28` | **Cause B** — hard-bound graph + instance id |
| `scripts/replay3d.gd:617-637, 658` | real subprocess execution + result read |
| `scripts/replay3d.gd:772-800` | cursor over the published series |
| `scripts/model_registry.gd:100-131` | discovery, **no filtering** |
| `scripts/model_node.gd:94-169` | port precedence; instance-parameterised branch |
| `composition/composition/adapters/__init__.py:42-68` | **Cause C** — `REGISTRATIONS` |
| `composition/composition/adapters/__init__.py:92-134` | refusal message for unknown ids |
| `composition/composition/registry/builder.py:263-285` | `build_registry()` |
| `composition/composition/_workers/zielinski_worker.py:312-318` | replay-run reuse |
| `composition/replay/zielinski_replay.json` | the single hard-bound graph |
| `Models/Zielinski/models/source.py:58` | loads the digitised Fig. 3 data |
| `Models/Baez/README.md:138` | "no adapter is registered" |
| `Models/Baez/tests/test_exclusions.py:304-332` | isolation guards (2 stale) |
| `composition/tests/godot/contract_boundary.gd:109-113` | Baez-must-be-absent guard (passes) |
| `composition/tests/test_acceptance.py:1317-1335` | Python twin guard (passes) |
| `composition/VALIDATION_REPORT.md:274-276` | palette removal, documented |
| `composition/tests/godot/ui_visibility_probe.gd` | **added by this diagnosis** (read-only probe) |

### Files touched by this diagnosis

* **Added:** `reports/GODOT_MODEL_VISIBILITY_DIAGNOSIS.md` (this document) and
  `composition/tests/godot/ui_visibility_probe.gd` — a read-only, non-asserting
  diagnostic harness. It changes no application code, no contract and no
  model. Delete it if the repository prefers not to carry it.
* **Modified:** nothing else. No scene, script, model, equation, parameter,
  contract or existing test was changed.