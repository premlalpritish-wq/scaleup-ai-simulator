# Integrating the insulin production simulation with its model library

Date: 2026-10-29. Project: `D:\Godot\Scaleup AI\pilot` (`project.godot`, main scene
`res://scenes/workshop.tscn`, the only Godot project registered in
`%APPDATA%/Godot/projects.cfg`). The working tree carries uncommitted changes from
earlier work; nothing here was committed or pushed.

This report answers one question per library entry: **can it join the insulin production
simulation without changing meaning, units or conservation behaviour, and if not, why?**
Every verdict below is the project's own compatibility engine's, read from
`python -m composition.runner --describe-connections`. No biology, parameter value or
conversion factor was invented for this audit, and no model was modified.

---

## 1. What was mapped

| Layer | Where | What it is |
|---|---|---|
| Simulation under audit | `Models/Zielinski`, graph `composition/replay/zielinski_replay.json`, scene `scenes/replay3d.tscn` | Zielinski et al. (2019) recombinant human insulin process, *E. coli* 20. Registered as `zielinski2019.rhi_process@1.0.0` |
| Model library (source of truth) | `composition/composition/adapters/__init__.py` → `composition.registry` → `--list-models` | The only place a model is registered. Three registrations |
| Library presentation (Godot) | `scripts/model_registry.gd`, `scripts/model_palette.gd`, `scripts/main.gd` | The **Models** panel above the graph canvas: every registered model, one Add button each |
| Compatibility authority | `composition/composition/cross_model.py` → `--describe-connections` | Nine ordered model pairs with stance, evidence, unresolved items and remediation |
| Other presentations (unchanged) | `scripts/compatibility_panel.gd` (workshop), `scripts/cross_paper_panel.gd` (replay §6), `web/` + `docs/` catalogue | Already rendered the engine's verdicts before this work |

There is no `AGENTS.md` or `CONTRIBUTING.md` in the project. The conventions are carried by
`README.md`, `reports/`, and the doc comment at the head of every script; this work follows
them (no rules in a panel, no scientific calculation in GDScript, every absence stated
rather than filled in).

---

## 2. Model-by-model record

### 2.1 `zielinski2019.rhi_process@1.0.0` — the insulin process itself

| | |
|---|---|
| Subsystem | The whole process, as the model's own 15 operations: fermentation (N01), biomass harvest (N02), cell lysis and inclusion-body isolation (N03), inclusion-body dissolution (N04), renaturation (N05), citraconylation (N06), trypsinisation (N07), DEAE Sepharose (N08), decitraconylation (N09), zinc precipitation and zinc-salt dissolution (N10), Q Sepharose (N11), carboxypeptidase B treatment (N12), RP-HPLC (N13), Sephadex G-25 buffer exchange (N14), final product characterisation (N15) |
| Ports | 139 input / 57 output, **fixed** at model level. 196 values in total |
| Quantities and units | `volume` (mL, L), `mass_concentration` (g/L, mg/mL, ug/mL), `mass` (g), `time` (h, min, d), `temperature` (°C), `ph`, `dimensionless` (OD600, %, fold), `molar_concentration` (mM, M), `volume_flow` (mL/min), `conductivity` (mS), `relative_centrifugal_force` (xg), `absorbance` (AU), `absorbance_per_volume` (AU/mL), `absorbance_per_mass` (g/AU), `activity` (IU), `activity_per_volume` (IU/L), `molar_mass` (Da), `wavelength` (nm), `concentration_factor` (fold) |
| Time scale / conditions | One published batch. 4 L working volume in a 7.5 L nominal fermenter; one stated temperature; the induction time is **not** reported |
| Assumptions / boundary | An **evidence replay**, not a predictive simulator. It restates reported values, applies the accounting identities the paper supports, and declares eight absent models. Predictive execution fails closed (23 unresolved targets with no inputs supplied) |
| Dependencies | None in this project. It declares eight absent models and refuses to invent them |
| Connectability | **Integrated as-is.** It is the simulation's own model: `scenes/replay3d.tscn` executes its graph through the same `CompositionRunner` boundary the editor uses. It needs no adapter, because nothing crosses into it |

### 2.2 `ganjave@0.1.0` — cybernetic fed-batch growth (2022)

| | |
|---|---|
| Subsystem | Fed-batch *E. coli* growth and substrate consumption: biomass, glycerol, complex substrate, dissolved oxygen, culture volume |
| Ports | 9 input / 6 output, **fixed**. Units `g/L` (8), `L` (2), `%` (2), `mL/h` (1), `h` (2) |
| Quantities | `mass_concentration`, `volume`, `dimensionless`, `volume_flow`, `time` |
| Time scale / conditions | 24 h fed-batch on the model's own strain, medium, scale and feed recipe (equations (8)–(16); Table 2 parameters loaded as fitted) |
| Assumptions / boundary | A single well-mixed bulk volume. Declares `component_identity` **unsupported**, so it publishes no conserved entities |
| Dependencies | None. It is the model the default workshop scene runs live |
| Connectability | **Incompatible** with the insulin simulation — see §3 |

### 2.3 `morris2011.material_balance@0.1.0` — non-reacting control volume (2011)

| | |
|---|---|
| Subsystem | Material balance over **non-reacting** control volumes. Not an organism model |
| Ports | 0 at model level: **instance-parameterised**. The port surface exists only once a control volume is declared, so the registry reports 0/0 and seven unknown fields (`title`, `source_paper`, `doi`, `capabilities`, `ports`, `variables`, `units`, `assumptions`) with the model's own reason attached |
| Quantities | `mass`, `mass_flow`, `mass_fraction`, `amount`, `amount_flow` only |
| Time scale / conditions | None declared at model level; properties of the declared instance |
| Assumptions / boundary | Conservation with no reaction term. It has nowhere to declare a yield, a rate constant or a reaction |
| Dependencies | None. It is composable with **itself**, and only with itself |
| Connectability | **Incompatible** with the insulin simulation — see §3 |

### 2.4 `baez2014` (`Models/Baez`) — oxygen-induced expression (2014)

| | |
|---|---|
| Subsystem | One printed formula from the paper, published as an inspectable artefact |
| Ports | None. It is **not registered** in the composition layer, and its manifest states `registered_in_composition_registry: false` |
| Quantities / units | One equation with declared run inputs and an output unit, per `Models/Baez/manifest.json` |
| Assumptions / boundary | Explicitly excludes a growth, oxygen or GFP predictive model. Two of its own tests are known-failing stale counts (hard-coded expectations of 2 workers / 2 registered models, written before Ganjave was added) |
| Connectability | **Needs clarification / not evaluable.** No adapter, no port surface and no registered identity, so there is nothing for the engine to classify. It must not be wired in on the strength of sounding like an oxygen model |

---

## 3. Classification against the insulin simulation

The engine emits nine ordered pairs. Only two are permitted, and **both are same-model**;
no cross-model boundary is permitted anywhere in this project.

| Library entry | Class | Decisive engine verdict (`--describe-connections`) |
|---|---|---|
| `zielinski2019.rhi_process@1.0.0` | **Integrate** (as-is, into its own simulation) | It *is* the simulation. `zielinski → zielinski` is refused (`refused_no_supplyable_port`): its ports are one reported experiment's operating conditions, not a stream another run could take |
| `ganjave@0.1.0` | **Flag incompatible** | `ganjave ⇄ zielinski2019.rhi_process` — `refused_dimensional_only`, basis `documented_incompatibility`: "Both models describe an *Escherichia coli* fed-batch culture, and neither quantity nor unit is what stands between them. They are two different experiments: different strain, different construct, different medium, different scale, different objective, five years apart." Its own `ganjave → ganjave` forward cascade *is* permitted, on the declared residual-glycerol assumption — but that is a same-model cascade, not compatibility with the insulin process |
| `morris2011.material_balance@0.1.0` | **Flag incompatible** | `morris ⇄ zielinski` — `refused_component_identity`, basis `documented_incompatibility`, already **enforced by the engine** (CG-08 / CG-09): "Zielinski publishes process roles, not conserved chemical entities… A Zielinski quantity forwarded into a Chapter 4 balance would therefore be relabelled as a component, which is an invented assumption that silently determines the answer." Its `morris → morris` boundary is permitted |
| `baez2014` | **Needs clarification / data** | No boundary names it, because it is not registered. Reported as *not evaluated*, never as compatible |

**Integrate with adapter: none.** No unit, state or interface conversion is documented
anywhere in this project that would make one of these entries a legitimate partner for the
insulin process, so none was written. The Ganjave refusal names what would have to exist
first — "A model built to be matched to both — declaring a shared component set, an
explicit dry-to-wet biomass basis, a scale relationship and a common medium" — and it does
not exist here. Writing that adapter now would be predicting the answer, which is exactly
what the engine refuses to do.

---

## 4. What was implemented

The gap was in the **model library presentation of the composition editor**. Every other
surface already rendered the engine's verdicts (the workshop's `CompatibilityPanel`, the
replay's cross-paper section, the web catalogue's Models tab); the **Models panel above the
graph canvas showed none**. That made it the one place where a model the engine refuses
could be placed into the active simulation with nothing on screen saying so.

1. **`scripts/model_registry.gd` — one mapping, no rules.** `accept_connections()` takes
   the `--describe-connections` payload. `integration_status(model_id, counterparts)` maps
   two fields the engine emits — `permitted` and `evidence_basis` — to four states:
   `integrate`, `incompatible`, `needs_clarification` (refused with `evidence_limited`, i.e.
   the policy failed closed and made *no judgement*), and `not_evaluated` (the engine said
   nothing about this model). Same-model boundaries are carried separately in
   `own_model_pairs`, so a model that may be chained to its own instances is never presented
   as compatible with anything else. Every sentence shown is the engine's own `reason`,
   verbatim. `compatibility_loaded()` is deliberately not called `has_connections()` —
   `Node` already defines that name, and the collision was a parse error.
2. **`scripts/model_palette.gd` — the column.** Each row now carries a `compatibility:` line
   with the engine's state and the start of its reason, coloured by state, with the whole
   reason, the evidence basis and the engine's own remediation in the tooltip — and in the
   Add button's tooltip, so the reason is in view at the moment of placement. The header
   counts states (`3 registered · 3 incompatible`). `set_active_models()` narrows the
   question to the models already in the graph. The panel also states the position's scope:
   the engine classifies *registered* models, so an artefact with no adapter produces no
   boundary at all and its absence from the list is not a verdict about it (the engine's own
   `claim_scope` and `validation_status` are in that line's tooltip). Listing such an
   artefact anyway would have been the tempting fix and is exactly what
   `_check_unregistered_models_are_absent` forbids.
3. **`scripts/main.gd` — asks once, and keeps the library and the graph consistent.** The
   editor requests `--describe-connections` after discovery (deferred, so it cannot
   interleave with the registry's own request chain), hands the payload to the registry, and
   calls `set_active_models()` whenever the graph's model set changes — add, delete, load
   example, new graph. The request is issued here rather than inside `ModelRegistry`
   because the workshop and replay scenes drive that same runner with their own request
   sequencing, and a third caller inside the registry would interleave with theirs.
4. **`composition/tests/godot/palette_graph_run.gd` — check 18.** Forty-nine new assertions
   drive the real scene: the engine was consulted; every row carries a decided state
   credited to `composition.cross_model.describe`; the row text and tooltip contain the
   engine's own label and basis; narrowing to one counterpart yields only that counterpart's
   pairs and no permitted one; a model the engine never classified is `not_evaluated`, never
   compatible; Ganjave's same-model cascade is recorded as same-model. The fixed startup
   wait rose from 6 s to 12 s to cover the extra interpreter invocation.
5. **`composition/tests/test_acceptance.py` — guard.** A new test asserts the window asks
   `describe_connections()`, that the registry reads `permitted` / `evidence_basis`, and that
   the palette duplicates neither (`evidence_basis` and `stance` must not appear in
   `model_palette.gd`). Same shape as the existing palette guards.

No model, equation, parameter, solver setting, registration, compatibility rule or
scientific status was changed. No model was added to or removed from any graph, and the
workshop and replay scenes were not edited.

---

## 5. Changed files

| File | Change |
|---|---|
| `scripts/model_registry.gd` | New "compatibility boundary" section: `accept_connections()`, `compatibility_loaded()`, `connection_scope()`, `boundaries_for()`, `integration_status()`, `integration_summary()`, `integration_colour()`, the `connections_loaded` signal and the four `INTEGRATION_*` state constants. Additive; the existing discovery, manifest and contract paths are untouched |
| `scripts/model_palette.gd` | A `compatibility:` line per row, coloured by state, with the engine's reason, evidence basis and remediation in the tooltip and in the Add button's tooltip; a state tally in the header; `set_active_models()`, `status_for()`, and `integration` on each `model_entries()` record |
| `scripts/main.gd` | `_request_compatibility()` (deferred, once, after discovery), `_sync_palette_to_graph()`, and the connections branch in `_on_runner_finished`; synced on add, delete, example load and new graph |
| `scripts/workshop.gd` | One accessor: `is_stale()` returned `_awaiting != ""` instead of `_stale` (see §6) |
| `composition/tests/godot/palette_graph_run.gd` | New check 18 (49 assertions); the fixed startup wait raised from 6 s to 12 s for the extra interpreter invocation |
| `composition/tests/test_acceptance.py` | New guard test `test_the_model_library_reads_compatibility_from_the_engine` |
| `reports/MODEL_LIBRARY_INTEGRATION.md` | This report |

Nothing under `Models/`, `composition/composition/`, `web/`, `docs/` or `staging/` was
modified. No registration, compatibility rule, equation, parameter or scientific status
changed.

---

## 6. Pre-existing defect found while running the suite

`scripts/workshop.gd` is an uncommitted file (it is not in `HEAD`), and its harness-facing
accessor was:

```gdscript
func is_stale() -> bool:
	return _awaiting != ""
```

`_awaiting` is the "a request is in flight" flag and is cleared at the top of every result
handler, so `is_stale()` returned `false` at exactly the moments the acceptance suite asks
it — after an input edit and after a failed run. Two assertions in
`composition/tests/godot/workshop_graph_run.gd` were therefore unable to fail:
`changing an input did not mark results stale` and `a failed run left its results looking
current`. The workshop harness reported `144 checks, 2 FAILED` before this work and after
the library changes alone; `busy()` already answers the in-flight question, so the accessor
now returns `_stale` and the harness reaches `144 checks passed`.

This is a fix to an accessor, not to the scene's behaviour: no panel, run path or result is
affected. It is recorded because two of the assertions it unblocks are the "a stale result
must not look current" checks this project's honesty rules depend on.

---

## 7. Checks run

All commands run from the project root unless stated. Godot is
`D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe`
(4.7.2.stable.official.ed1daf0bf); Python is 3.14.7.

| Check | Command | Result |
|---|---|---|
| Godot parse of every edited script | `godot --headless --check-only --script res://scripts/<file>.gd` for `model_registry`, `model_palette`, `main`, and the palette harness | clean, no parse errors |
| Model library + graph editor (the edited scene) | `godot --headless --path . --script res://composition/tests/godot/palette_graph_run.gd` | **274 checks passed** (was 220; +49 from check 18, +5 for the scope statement in check 18's item 7) |
| GDScript → Python contract boundary | `… --script res://composition/tests/godot/contract_boundary.gd` | **840 checks passed** |
| Simulation workshop (unchanged scene) | `… --script res://composition/tests/godot/workshop_graph_run.gd` | **144 checks passed** after the §6 accessor fix; `144 checks, 2 FAILED` before it |
| Ganjave graph run | `… --script res://composition/tests/godot/ganjave_graph_run.gd` | **51 checks passed** |
| Insulin replay / cross-model context | `… --script res://composition/tests/godot/replay_cross_paper.gd` | **81 checks passed** |
| The insulin model itself | `cd Models/Zielinski && python -m pytest tests -q` | **223 tests, no failures** |
| Composition acceptance suite | `cd composition && python -m pytest tests/test_acceptance.py -q -p no:cacheprovider` | **121 tests, no failures** (121 progress marks, zero `F`) |
| The new guard and its neighbours | `python -m pytest tests/test_acceptance.py -q -k "model_library_reads_compatibility or palette_keeps_no_second_list or palette_harness_asserts_no_scientific_compatibility or godot_harness_asserts_no_scientific_compatibility or default_scene_is_the_workshop"` | **5 passed** |
| Web catalogue still agrees with the engine | `python scripts/build_web_model_catalog.py --check` | **PASS** — catalogue matches registry and compatibility engine; replay matches runner result and digitized trajectory |
| Web model-selector regression | `node web/tests/model_selector_regression.mjs` | **PASS** |

Not run, and why: the Morris, Ganjave and API suites, the Pyodide parity/bundle harnesses and
the Godot Web export. None of them reads `scripts/model_registry.gd`,
`scripts/model_palette.gd`, `scripts/main.gd`, `scripts/workshop.gd` or the palette harness,
and no model, equation, adapter or web file changed — the web catalogue check above is the
one thing that could have drifted, and it passed.

The workshop harness was red before this work for a reason unrelated to it; that is §6.

---

## 8. What remains blocked on missing definitions or data

**The literature route has already been tried for these gaps.** `python -m composition.evidence`
(`composition/composition/evidence/`, `verdict_authority: "definitive"`) searched five declared
targets — `specific_growth_rate`, `stationary_phase_od600`, `glucose_limitation_od600`,
`dissolved_oxygen`, `induction_time` — against the ingested papers, and returned **3 findings,
all `incompatible`**:

| Finding | Candidate | Verdict reason |
|---|---|---|
| CF-001 | Senn et al. 1994, Monod `Ks` = 88 µg/L | Strain `ML30` wild type vs `E. coli 20 IBA 1`; no construct vs `pIBAINS`; continuous chemostat vs batch with pH-stat feeding |
| CF-002 | Smaluch et al. 2023, `µ` = 0.61 h⁻¹ | Strain `MG1655` vs `E. coli 20`; `M9` vs `GMS` medium; microfluidic single-cell cultivation vs batch; and a single-cell rate is not the population rate the 2019 process observed |
| CF-003 | Mikiewicz et al. 2017 (same strain, vector, medium, mode, 7.5 L Bioflo Celligen 310) | Reports **no kinetic parameter of any kind**; and the passage it relies on occurs in the Zielinski paper itself, so it is not independent (`CFL-01`, `not_independent_of_target`) |

The search's own conclusion: *"No source reports a kinetic parameter for E. coli 20 carrying
pIBAINS in GMS medium. The closest-matched publication, from the same institute and the same
strain/vector/medium, reports no kinetics at all."*

So "find more papers" is not an unexplored option for these five targets — it has been run, and
the best-matched paper in the set supplies no kinetics. The remaining honest routes are to
**measure and fit** kinetics for this strain (the held-out evaluation machinery already exists
for judging such a fit), or to **declare** the missing values as `assumed` quantities with a
rationale — which the model supports by design and which converts "fails closed" into "predicts
under a stated assumption", at the cost of the prediction no longer being paper-backed.

Note the scope of that: closing these gaps makes `zielinski2019.rhi_process` predictive. It does
**not** create a cross-model port. The refusals in §3 are about experiment identity, not missing
parameters, so better kinetics for E. coli 20 still leave `ganjave ⇄ zielinski` refused.

- **`baez2014` is not evaluable and stays out.** It has no adapter, no registered identity
  and no fixed port surface, so the engine has nothing to classify. Registering it would
  require an adapter written against its one printed formula — a separate decision with its
  own evidence burden, and it was not taken here.
- **The insulin model's eight declared absent models remain absent.** No library entry
  supplies growth kinetics, oxygen transfer, an AU calibration or a purification recovery,
  and the engine documents why each candidate is refused. Nothing in this change made them
  look available.
- **The dry-to-wet biomass model that could carry a quantity between Ganjave and Zielinski
  does not exist.** The engine names the four things it would have to declare: a shared
  component set, an explicit biomass basis, a scale relationship and a common medium. Until
  such a model exists, "integrate with adapter" stays empty — no conversion factor was
  invented to fill it.
- **Known seam, deliberately not changed:** `scripts/build_web_model_catalog.py` still maps
  browser capability with a hand-written per-model dict (`ganjave → pyodide_live`,
  `zielinski2019.rhi_process → stored_evidence_replay`, …), and a newly registered model
  falls through to `not_available` there. The complaint the Godot palette was fixed for
  applies to that dict too; it is outside this change and is recorded rather than silently
  patched.

---