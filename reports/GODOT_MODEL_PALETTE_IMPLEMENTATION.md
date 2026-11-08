# Godot Model Palette — Implementation Report

**Date:** 2026-10-19
**Resolves:** causes A and B of `reports/GODOT_MODEL_VISIBILITY_DIAGNOSIS.md`.
Cause C (Baez deliberately unregistered) is unchanged, by design.

---

## 1. What changed

A user can now open the main scene, pick **Morris**, **Zieliński** or **Ganjave**
from a palette, configure what that model declares it needs, press **Run**, and
read the outputs — with no command line and no model-specific replay button.
The palette's contents come from `python -m composition.runner --list-models`.
There is no list of model ids anywhere in the new GDScript.

### New files

| File | What it is |
|---|---|
| `scripts/model_palette.gd` | `ModelPalette`. Renders one row per registered model and emits `instance_requested`. |
| `scripts/instance_form.gd` | `InstanceForm`. Contract-driven configuration dialog. Emits `configured`. |
| `scripts/structured_editor.gd` | `StructuredEditor`. Generic recursive editor for a JSON-shaped declaration. |
| `composition/tests/godot/palette_graph_run.gd` | Acceptance harness, 149 checks, driving the real main scene. |

### Modified files

| File | Change |
|---|---|
| `scripts/main.gd` | Builds and places the palette; wires the form; `_on_instance_requested` completed to six arguments and now writes literal inputs to the graph document; new `_invalidate_results()`; the palette stub and its `_on_add_confirmed` are gone; the replay button is relabelled. |
| `composition/tests/test_acceptance.py` | Three new tests (harness run, no second model-id list, harness scope guard). |
| `README.md` | The "Add model" placeholder note is replaced with how the palette works. |
| `composition/VALIDATION_REPORT.md` | §6.3 item 3 updated from "is a stub" to "is restored". |
| `reports/GODOT_MODEL_VISIBILITY_DIAGNOSIS.md` | A "Resolved" banner at the top pointing here. |
| `composition/tests/godot/ui_visibility_probe.gd` | (from the previous task) updated to report the palette instead of the removed dialog. |

### Deliberately not changed

`scenes/replay3d.tscn`, `scripts/replay3d.gd`, `composition/replay/zielinski_replay.json`,
every file under `Models/`, and the whole `composition/composition/` package.
No equation, parameter, solver, contract, refusal rule or validation status was
touched. Baez is not registered and still cannot be added.

---

## 2. How the three requirements are met

### 2.1 Discovery, not a list

`ModelPalette.refresh()` iterates `_registry.model_ids()`, which is exactly what
`--list-models` returned. A regression test asserts that
`scripts/model_palette.gd` contains none of the three model ids as literals, so
the failure mode this risks — a palette that quietly drops the next model
someone registers — is caught.

**An empty registry and a failed discovery are different facts and are reported
differently.** An empty list says *"No models are registered with the
composition layer"*; a failure shows the runner's own message and a red row. A
model whose package is unreachable is drawn in red with its path and its **Add**
button disabled.

**The name shown is the artefact's.** A model that publishes a model-level
manifest shows its own `title`. Morris does not — it declines to publish one
until an instance exists — so its row shows its identifier rather than a phrase
the palette composed. That is the same rule `ModelRegistry.known_models()` keeps
about labels, and it is why a Morris row reads
`morris2011.material_balance` rather than "Morris material balance".

### 2.2 Graph-instance creation

`InstanceForm` emits `configured`; `ModelPalette` relays it as
`instance_requested`; `main.gd:_on_instance_requested` does the work:

```gdscript
var inst := _document.add_instance(model_id, model_version, label, role, position, parameters)
for port_id in literals.keys():
    _document.set_literal(instance_id, str(port_id), (literals[port_id] as Dictionary).duplicate(true))
_canvas.add_node(inst)
```

It goes through `GraphDocument` and `ProcessCanvas` like every other path. The
id comes from `GraphDocument._next_instance`, so it is stable and unique. No
separate execution path exists: **Run** is still `main.gd:_on_run_pressed` →
`_run_runner` → `CompositionRunner.run_graph` → `python -m composition.runner`.

### 2.3 Contract-driven configuration

| Sourced from | Used for |
|---|---|
| `manifest.ports` where `required == true` | the required-input rows, in the model's order |
| `manifest.ports[].quantity`, `.unit`, `.label`, `.description`, `.provenance_requirement` | each row, rendered as the model wrote it |
| `ModelRegistry.units_for(quantity)` (from `--describe-contract`) | the unit picker — a value can only be typed in a unit its quantity has |
| `ModelRegistry.canonical_quantity()` | marks a port whose quantity this contract does not define |
| `port.unavailable_reason` | a port the model says cannot be connected is shown read-only, not hidden |

**Nothing is invented.** A required input left blank blocks the Add button and
quotes the model's own sentence for having no default. A port with no
contract-defined quantity is read-only rather than offered with a made-up unit.

The one place a user must supply a value the UI does not offer is Ganjave's run
duration — and that is the model refusing, not the form:

> `parameters.duration_h is required: a duration is an input of the run, not
> something this worker may choose … No value was substituted`

The form offers an empty **Model parameters** block with an *add field* button
and editable keys, so the user can write `simulation.duration_h` themselves.

### 2.4 The two model shapes

* **Fixed port set** (Zieliński 196 ports, Ganjave 15): the manifest's ports,
  required first, optional behind a toggle.
* **Declared per instance** (Morris): the adapter refuses a manifest until the
  instance carries a control volume, so the form says so, in the model's words,
  and offers a blank declaration plus every Morris declaration the project
  already ships — read live from `res://composition/examples/*.json`, with each
  one's own `source_ref`, assumptions and reasons travelling with it. The user
  can then edit any field.

The form blocks only on what the model refuses without: no `system`, no streams,
or no components. Whether the balance is *solvable* is the engine's question and
is left to the engine; the form does not second-guess it.

---

## 3. Beyond the brief: stale results

Adding an instance, drawing a connection, deleting an instance, loading a graph
or starting a new one now clears the Results, Validation and Provenance panels
through `main.gd:_invalidate_results(reason)`, which also sets
`_results_are_current = false`. Before this, a run stayed on screen as though
current after the node that produced it had been deleted. Required by
Task 4 ("Failed executions cannot leave stale results appearing current").

The replay button is now captioned **"Zieliński replay"** with a tooltip that
says what it is: a *predefined experiment replay, not a simulation*, whose growth
curve is *digitised from their Figure 3*. The scene itself is untouched.

---

## 4. Tests

### Godot harnesses — all from the repository root

```powershell
$godot = "D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe"

& $godot --headless --path . --script res://composition/tests/godot/palette_graph_run.gd
& $godot --headless --path . --script res://composition/tests/godot/contract_boundary.gd
& $godot --headless --path . --script res://composition/tests/godot/ganjave_graph_run.gd
& $godot --headless --path . --script res://composition/tests/godot/ui_visibility_probe.gd
```

| Harness | Result | Status |
|---|---|---|
| `palette_graph_run.gd` | `palette-graph-run: 149 checks passed` (exit 0) | **new** |
| `contract_boundary.gd` | `contract-boundary: 840 checks passed` (exit 0) | **unchanged** |
| `ganjave_graph_run.gd` | `ganjave-graph-run: 51 checks passed` (exit 0) | **unchanged** |
| `ui_visibility_probe.gd` | palette reports the three models, exit 0 | updated |

The existing contract-boundary harness was **not modified**.

### Python suites

```powershell
cd composition      ; python -m pytest tests -o addopts= --tb=no -q   # 402 passed
cd Models\Morris    ; python -m pytest tests -o addopts= --tb=no -q   # 186 passed
cd Models\Zielinski ; python -m pytest tests -o addopts= --tb=no -q   # 223 passed
cd Models\Baez      ; python -m pytest tests -o addopts= --tb=no -q   # 193 passed, 2 failed
```

| Suite | Before | After |
|---|---|---|
| `composition` | 399 passed | **402 passed** (+3 new) |
| `Models/Morris` | 186 passed | 186 passed |
| `Models/Zielinski` | 223 passed | 223 passed |
| `Models/Baez` | 193 passed, 2 failed | 193 passed, 2 failed — *unchanged, pre-existing* |

The two Baez failures (`test_no_adapter_worker_was_added_for_this_model`,
`test_the_composition_registry_lists_only_the_pre_existing_models`) are the
stale hard-coded counts identified in the diagnosis: they expect exactly two
workers and exactly two registered models, written before Ganjave was
registered. They are untouched here, and still correct in what they assert —
Baez is absent.

### What the 149 checks cover

All ten required behaviours, driving the real scene:

| # | Requirement | Where |
|---|---|---|
| 1 | Palette population from the registry | `_check_palette_populates_from_the_registry` — rows equal `model_ids()`, one Add button each, every reference is `id@version` |
| 2 | Morris, Zieliński, Ganjave present | `_check_the_three_registered_models_are_offered` |
| 3 | Unregistered Baez absent | `_check_unregistered_models_are_absent` — also scans every id for `baez` |
| 4 | Selection creates a graph instance | `_check_selection_creates_a_graph_instance` — presses the palette's Add, then the form's OK; asserts document, canvas and selection |
| 5 | Correct model id and version | `_check_the_graph_carries_the_exact_reference` |
| 6 | Contract-driven configuration | `_check_configuration_is_contract_driven` — exactly the manifest's required ports; blocked when blank; values reach `literal_inputs` with unit and `source_ref` |
| 7 | Execution and output display per model | `_check_morris_runs_through_the_ui` (ports from the instance), `_check_zielinski_runs_through_the_ui` (196 ports, 196 outputs, still unresolved-heavy so it did not become predictive), `_check_ganjave_runs_through_the_ui` (15 ports, 6 outputs, trajectory, `reproduction_status: not_yet_validated`) |
| 8 | Changed input → changed result | `_check_a_changed_input_changes_the_result` — `initial_biomass_concentration` 0.05 → 0.5 g/L moves `biomass_concentration` |
| 9 | Failure handling, stale invalidation | `_check_failure_and_stale_result_handling` — results invalidated on edit; a removed required input is refused and the diagnostic names it; a shape error never reaches the runner |
| 10 | Replay preserved | `_check_the_zielinski_replay_is_preserved` — scene and graph exist, the scene still disclaims simulation, the toolbar button exists and says "predefined" and "digitized", and the replay graph still publishes 196 values |

The harness presses real buttons and calls the real Run handler. It never calls
Python directly, so a green run is a claim about the UI.

### Three new Python tests

* `test_godot_can_add_and_run_every_registered_model_from_the_palette` — runs the
  harness; skips loudly, with the manual command, if Godot is absent.
* `test_the_palette_keeps_no_second_list_of_model_ids` — asserts none of the
  three ids appears in `model_palette.gd` and that `REGISTRATIONS` is unchanged.
* `test_the_palette_harness_asserts_no_scientific_compatibility` — the harness
  must not claim scientific validity.

---

## 5. Live verification

From `ui_visibility_probe.gd`, the real main scene at launch:

```
--- the model palette ---
  ganjave@0.1.0                 available=true dependence=fixed    name=Ganjave et al. (2022) cybernetic growth and fed-batch model
  morris2011.material_balance@0.1.0 available=true dependence=instance name=morris2011.material_balance
  zielinski2019.rhi_process@1.0.0  available=true dependence=fixed    name=Recombinant human insulin from Escherichia coli 20 (Zielinski et al. 2019)
  has_load_error: false
```

Toolbar: `Run` · `Validate only` · `Load example:` · `New graph` ·
`Zieliński replay` · `Save graph` · `Open graph...`

---

## 6. Known limitations

1. **Morris needs a control volume before it shows any ports.** This is the
   model's own refusal, not a UI choice. The form makes it explicit and offers a
   real starting point, but a user who declines both options gets a blocked
   form rather than an empty node — which is the honest outcome.
2. **The unit picker is a dropdown, not free text.** A value in a unit the
   contract does not define for that quantity cannot be entered. That is the
   contract's rule; the engine still enforces and diagnoses it independently.
3. **Zieliński's optional section holds 139 rows.** It is behind a toggle and
   scrolls. Adding 196 widgets costs a little memory; nothing else was done
   about it because capping the list would mean hiding ports the model declared.
4. **`execution.mode` is not offered as a dropdown.** Choosing `evidence_replay`
   versus `predictive` is a typed-in parameter. A dropdown would mean
   hard-coding mode names in GDScript, which is the same mistake as hard-coding
   model ids; the form shows the model's declared capabilities instead. The
   default is the adapter's own and is applied by the adapter, not by the form.
5. **The graph runs synchronously.** `runner.gd` already said so and this work did
   not change it. A long run freezes the window.
6. **Node layout for a tall graph is still clipped.** Pre-existing
   (`VALIDATION_REPORT.md` §6.2 item 2), untouched.
7. **Node dragging does not invalidate results.** A position change does not
   change what a run means, so it is deliberately not treated as an edit.
8. **The 139 Zieliński optional inputs are editable but were not all exercised.**
   The harness drives the three models' required inputs, Ganjave's optional
   inputs, and Morris's imported declaration. The Zieliński optional rows are
   built and rendered but no test types into them.
9. **Two Baez tests still fail.** Pre-existing and untouched; see §4.

---

## 7. Reproducing

```powershell
cd "D:\Godot\Scaleup AI\pilot"
$godot = "D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe"

# the UI acceptance harness
& $godot --headless --path . --script res://composition/tests/godot/palette_graph_run.gd

# the Python side, which runs that harness itself
cd composition ; python -m pytest tests/test_acceptance.py -k "palette or godot"
```

Godot 4.7.2 is installed at `D:\Godot\Godot_v4.7.2-stable_win64.exe\` and is
**not on `PATH`**; `composition/tests/test_acceptance.py::_find_godot()` finds it
there. `reports/GANJAVE_GODOT_EXECUTION.md` §2 still claims Godot is not
installed; that is stale and this report supersedes it.