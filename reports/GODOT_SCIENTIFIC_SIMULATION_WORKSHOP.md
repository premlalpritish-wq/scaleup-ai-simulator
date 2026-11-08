# Godot Scientific Simulation Workshop

**What a user gets when they open this project.**

The project no longer opens on an empty graph canvas. It opens on a three-dimensional
shake-flask fed-batch culture, running the Ganjave et al. (2022) growth model through
the normal composition runner, with every number on screen traceable to a paper, an
equation, or a declared assumption — and with a panel that says what is missing.

---

## 1. What the user sees on startup

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Shake-flask fed-batch E. coli — Ganjave et al. (2022), ganjave 0.1.0        │
│ one model, no connections        [Zielinski replay]  [Run simulation]        │
├────────────────────────────────────────────────┬─────────────────────────────┤
│ no results yet                                  │ Evidence | Gaps | Models |  │
│  ┌──────────────────────────────────────────┐    │ Report                    │
│  │            3D shake flask                 │    │                             │
│  │        on a shaking platform              │    │ (per-quantity provenance,  │
│  │   ┌────────┐                              │    │  assumptions, validation   │
│  │   │ ~~~~   │  ← liquid, well-mixed        │    │  status)                   │
│  │   │ ~~~~   │     DO gauge ▐                │    │                             │
│  │   └────────┘  ← syringe + feed line       │    │ (five categories of gap,   │
│  └──────────────────────────────────────────┘    │  each with what would      │
│  what this scene is not: well-mixed bulk only.   │  resolve it)               │
│  No cells, bubbles, gradients or flow.           │                             │
│  Biomass [g/L] 18.30  calculated                 │ (permitted and refused      │
│  Glycerol [g/L] 4.94  calculated                 │  model pairs, from the      │
│  DO [%] 65.58  calculated                        │  engine)                    │
│  Culture volume [L] 0.1130  calculated           │                             │
│  Complex substrate [g/L] 0.0463  calculated      │                             │
├────────────────────────────────────────────────┴─────────────────────────────┤
│ [Play] [Reset] ├────────●──────────────────────┤ t = 24.00 h                │
│ Feed rate [mL/h] 0.72  Feed glycerol [g/L] 175  …                           │
├──────────────────────────────────────────────────────────────────────────────┤
│ success  |  1 result(s) from the composition runner                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

The scene is a **Control** with a 3D `SubViewport` on the left and a four-tab inspector
on the right. It is `res://scenes/workshop.tscn`, and `project.godot` now points at it.

---

## 2. Which models actually drive the scene

**One: `ganjave` 0.1.0.** And that is not a simplification — it is forced by the
project's own evidence.

The compatibility engine declares nine ordered model pairs. **Two are permitted, and
both are same-model:**

| Pair | Stance |
|---|---|
| Morris → Morris | permitted (conservation, Ch. 4 premise) |
| Ganjave → Ganjave | permitted (forward cascade, on the model's declared assumption) |
| Morris ↔ Ganjave | refused — `no_shared_quantity` |
| Morris ↔ Zieliński | refused — `refused_component_identity` |
| Ganjave ↔ Zieliński | refused — `refused_dimensional_only` |
| Zieliński → Zieliński | refused — `refused_no_supplyable_port` |

**There is no permitted cross-model boundary.** The scene therefore executes a graph
with one instance and **zero connections**, and says so in its own header
("one model, no connections") and in the Models tab.

Why Ganjave and not the others:

- **Ganjave** is the only registered model that produces a *time course of biological
  quantities* — biomass, glycerol, complex substrate, dissolved oxygen, culture volume —
  over a real operating range. It is the only model a timeline can be built on.
- **Morris** is a non-reacting control-volume balance. Its examples are metal alloying.
  It has no biology, no kinetics, and no time axis to scrub.
- **Zieliński** is an **evidence replay**: its inputs are measurements transcribed from a
  published figure, and its outputs are recomputations of those inputs. It is not a
  predictive simulation and is not presented as one here.

The Ganjave forward cascade *is* permitted, and the scene deliberately does not draw it:
the project's own rule text records that it is "permitted under the model's declared
assumption, **not validated by it**: nothing in the paper seeds a second culture from the
first." Drawing a second culture would be a scene the evidence does not support.

---

## 3. What is calculated, and what is merely rendered

This is the distinction the scene is built around, and the scene states it on screen.

### Calculated — read from the runner's actual output

Every value below comes from the dense trajectory the composition runner wrote into the
result document (`value.extra.trajectory`). The scene reads that trajectory and
interpolates within it. It never computes a quantity of its own.

| Shown as | Port | Notes |
|---|---|---|
| Liquid level | `culture_volume` | Genuinely rises: `dV/dt = F` is eq. (16) |
| Liquid colour | `biomass_concentration` | A **legend**, 0–22 g/L, stated on screen |
| DO gauge height | `dissolved_oxygen` | Computed because kLa = 133 h⁻¹ and C\* = 0.0075 g/L are both printed |
| Readouts | all five | Sampled from the same trajectory |

### Rendered but not calculated — reported operating conditions

| Shown as | Basis | Caveat on screen |
|---|---|---|
| Platform turning at 200 rpm, 5 cm pitch | **Reported** (p. 3, Table S2) | The model computes no flow |
| Syringe and feed line | **Reported** hardware (Fig. 1) | The line carries no rendered flow |
| Feed meniscus falling | `flow_mL_per_h × (t − feed_start)` — arithmetic on a reported rate | Not a model output |
| 500 mL flask, 100 mL fill | **Reported** | Drawn to scale |

### Deliberately not drawn

The Ganjave model produces **well-mixed bulk scalars**. It has no spatial extent, so
the scene shows no:

- cells, particles, flocs or solids — no size distribution is published;
- bubbles, sparger plume or gas holdup — kLa is a lumped coefficient and there is no
  gas-phase state;
- concentration gradients, stratification or mixing patterns — there is **no transport
  equation in the model at all**;
- molecular motion or reaction animation;
- impeller, shaft or vortex — this is a shaken flask, and the model has no impeller.

A cell-sized speckle or a rising bubble would look better and would be a claim the
equations do not support. The flask is drawn as one well-mixed body and labelled as one,
in a permanent strip under the viewport that also says so.

---

## 4. The evidence and assumption inspector (Evidence tab)

Every visible quantity is inspectable, and **inputs and outputs are in separate
sections** because an assumed initial condition and a computed result look identical in
a table and are not remotely the same claim.

For each quantity the panel shows, where the source supports it:

- name and unit;
- **epistemic status** — reported / calculated / derived / inferred / assumed /
  caller_supplied / unknown / digitized;
- the model and version responsible;
- the source paper and exact locator (`printed p. 2, sec. 2.2`);
- the value, its provenance, and the reason it is required;
- the **provenance chain** — where a number came from, one hop at a time;
- the validation status, quoted from the model, with the note that running the
  simulation does not change it.

The panel adds two things the manifest does not carry on its own: the *provenance chain*
from the result document, and the *epistemic status* of each supplied input, derived
from the literal's own `provenance` field. Where nothing supports a field it says
`not published by this source` — distinct from an empty string, which would mean the
source said nothing on purpose.

Three conditions the paper does not state — X₀, S2₀ and DO₀ — are labelled **assumed**
or **derived**, with the reason, and are never presented as measurements.

---

## 5. The research-gap panel (Gaps tab)

A primary feature, not a warning list. Every gap answers six questions: what is
missing, why it matters *here*, what it affects, the evidence for the assessment, what
would resolve it, and whether it **blocks execution**, **limits interpretation**,
**prevents validation**, or **limits what can be simulated**.

Generated entirely from the project's own material — the manifest's `assumptions`,
`unsupported_capabilities` and `missing_information`; the required inputs of the quantity
registry; the composition report's connection dispositions; the compatibility engine's
refusals; and the last run's diagnostics. **Nothing is added from outside the ingested
literature.**

| Category | What it holds in this scene |
|---|---|
| **A** Missing model components | The model's declared unsupported capabilities; the absence of any spatial or transport model |
| **B** Missing parameters or initial conditions | Any required input the run did not supply |
| **C** Sources that cannot be connected | Every refused boundary touching the simulated model, with the engine's own reason and evidence |
| **D** Missing experimental evidence | The paper's time courses are figures — no numerical observations to validate against; any invalidated result; any refused connection |
| **E** Unresolved scientific questions | TN-02 (`e20/em1`), the caller-supplied initial conditions, anything the model records as `unresolved` |

Ranking is by **documented dependency**, not by a number: a missing required input
blocks execution; a missing model component limits what the scene may claim to
represent; missing observations prevent validation but do not stop a prediction. No
confidence score is invented for anything.

The panel says the required evidence is **absent from the project's currently ingested
sources**. It never says no research exists anywhere.

---

## 6. Model compatibility (Models tab)

Renders `--describe-connections` — the compatibility engine is the authority, and this
panel holds **no model list, no quantity pair, and no rule of its own**. A rule changed
in `cross_model.py` reaches this tab without anything here being edited.

It shows, for every ordered pair: whether it is permitted, the stance, the engine's
reason, the evidence, and what remains unresolved. Pairs touching the simulated model are
marked. The user who wonders why Morris and Zieliński are not in the flask gets an
answer with a citation.

`CompositionRunner.describe_connections()` was added to bridge this — the runner already
had the Python interface; only the GDScript side was missing.

---

## 7. Execution and staleness

The scene builds a graph document and hands it to `CompositionRunner.run_graph` — the
**normal execution path**, the same subprocess call the graph editor uses. The result
document supplies the trajectories.

When the user changes a supported input:

1. the previous results are marked **stale** — the banner says so and the readouts stay
   visible, because a reader mid-inspection is better served by a stale number labelled
   stale than by an empty flask;
2. **Run** re-validates and re-executes through the runner;
3. the trajectories, the evidence panel, the gap panel and the report all refresh;
4. if the run fails, the reason is displayed and the previous results are preserved
   **explicitly as stale** — never as current.

A failed run clears the trajectories, so the flask empties rather than continuing to
move. That is the rule that matters: **nothing is animated independently of the
model results**.

### A failure a user can actually reach

The failure path is not hypothetical. At a feed rate of **1.50 mL/h** the solver
exhausts its step budget — 200,000 steps, the smallest by then 3.8 × 10⁻⁹ h — and
stops at **t = 13.27 h of 24 h**. The model reports `ok: false`, the runner reports
`execution.model_failed`, and the scene displays the reason and clears the results
rather than leaving the previous run on screen.

That is a stiffness effect, not a typo: the extra feed drives dissolved oxygen to
near zero, and the DO balance becomes very stiff there. The scene surfaces it as
what it is — a configuration the model could not complete — and the input that caused
it stays visible so the user can change it back.

**No solver setting was changed to make this go away.** The step budget, tolerances
and `h_max` are exactly the ones the project's frozen evaluation used, and the
failure is reported rather than engineered around.

Supported inputs, all with their provenance in the field's tooltip:

| Input | Startup | Class |
|---|---|---|
| Feed rate | 0.72 mL/h | reported |
| Feed glycerol | 175 g/L | reported |
| Feed yeast extract | 245 g/L | reported |
| Feed start | 6 h | reported |
| Initial biomass X₀ | 0.05 g/L | **assumed** |
| Initial complex S2₀ | 25 g/L | **derived** |
| Initial DO | 100 % | **assumed** |

The startup values are the project's own recorded evaluation configuration
(`data/ganjave2022/frozen_configuration.json`), and a harness check compares every one
of them — value *and* classification — against that file, so a default cannot drift away
from the configuration that justified it.

---

## 8. The Zieliński replay

Still reachable from the header, still labelled. Its tooltip states that it is a
predefined experiment whose digitized figure data was transcribed from the paper, that
it is **not a predictive simulation**, and that its values are **not computed from these
models**. A harness check asserts the button exists and says both things.

The replay scene, its data and its behaviour are unchanged.

---

## 9. What gaps remain, and what prevents a more complete simulation

Stated plainly, because the scene's honesty is the point.

**Structural limits of the current evidence**

1. **No composed process is available.** Every cross-model pair is refused. A scene
   combining Morris, Zieliński and Ganjave would need a published relationship that
   none of the ingested sources states. This is the single largest limit on what the
   scene can show, and it is a limit of the evidence, not of the renderer.
2. **No spatial or transport model.** Everything is a well-mixed bulk scalar. The scene
   cannot show a gradient, a plume or a cell, and does not.
3. **No numerical observations.** The paper publishes time courses as figures. The
   simulation can be executed and still be unvalidated; the Gaps tab says so under
   category D.

**Limits of the model under simulation**

4. **Three initial conditions are not derivable** from the paper, and the outcome
   depends strongly on S2₀. The scene exposes them precisely because they are the
   scientifically interesting knobs, and labels them assumed/derived. The Gaps tab
   raises a category-B entry for each one, because the equations require a value the
   ingested source does not establish.
5. **TN-02 is unresolved** in the source: Table 2 prints `e20/em1` where the
   denominator must be `e_m2`.
6. **The model is not validated.** Its `reproduction_status` is `not_yet_validated` and
   the scene says so. Nothing here upgrades it; the project's own held-out evaluation
   **fails** its pre-registered criterion (see
   `reports/COMPOSED_PROCESS_SCIENTIFIC_VALIDATION.md` and
   `reports/GANJAVE_FAILURE_INVESTIGATION.md`).
7. **Some configurations cannot be integrated.** At high feed rates the solver runs
   out of steps (§7). The scene reports that honestly instead of extrapolating.

**Limits of the renderer**

7. The 3D vessel is a **schematic**, not a fluid simulation. It is sized from reported
   volumes and coloured from a reported legend, and it is not a claim about hydrodynamics.
8. The scene is one model, one configuration, one 24 h run. It is not a parameter
   study, and it does not claim general predictive accuracy.

---

## 10. Architecture

| File | Role |
|---|---|
| `scenes/workshop.tscn` | The default scene |
| `scripts/workshop.gd` | Controller: builds the graph, runs it, drives the view, feeds the panels |
| `scripts/shake_flask_view.gd` | **Reusable** 3D component: the flask, platform, gauge, syringe |
| `scripts/evidence_inspector.gd` | Evidence and assumption inspector |
| `scripts/research_gap_panel.gd` | Research-gap panel |
| `scripts/compatibility_panel.gd` | Model compatibility list |
| `scripts/runner.gd` | **Extended**: added `describe_connections()` |
| `project.godot` | `run/main_scene` now `res://scenes/workshop.tscn` |

Reused, not rebuilt: `CompositionRunner` (execution), `ModelRegistry` (discovery),
`InstanceForm` (configuration), `CompositionReportPanel` (the report tab), and the
compatibility engine itself.

Nothing was duplicated: the compatibility rules live only in `cross_model.py`, the
registry only in the registry, and the model execution only in the runner.

---

## 11. Tests

`composition/tests/godot/workshop_graph_run.gd` — **144 checks**, driving the **real
scene** through the **real runner**. It covers the twelve required behaviours:

| # | Behaviour | How it is checked |
|---|---|---|
| 1 | Launches into the 3D experience | `project.godot` points at the workshop; the scene is a 3D viewport with a flask, a timeline and a status indicator |
| 2 | The model list is registry-derived | the registry reports the model; the compatibility panel is engine-fed |
| 3 | Only permitted connections | the graph declares **zero** connections; no pair the engine refuses is presented as available |
| 4 | Runner outputs, not independent animation | sampling the same time twice agrees exactly; biomass moves between 1 h and 20 h; with no results the flask is empty |
| 5 | Changing an input re-runs and changes the result | feed rate 0.72 → 0.30 mL/h changes the 20 h biomass from 17.06 to 10.14 g/L; restoring 0.72 reproduces the original to 1e-4 |
| 6 | Missing inputs and refusals are visible | required inputs are declared or surfaced as a gap; refusals reach the report and the gap panel |
| 7 | Provenance and epistemic status | the inspector carries calculated / assumed / derived / reported, and never claims experimental validation |
| 8 | The gap panel identifies the gaps | all five categories present; the three unestablished required inputs are named; the validation gap is stated |
| 9 | No unsupported spatial effects, no invented defaults | the render source names the effects it excludes and implements none; every required input is declared |
| 10 | Failures and edits invalidate results | an edit marks results stale; the run the model cannot complete at 1.50 mL/h leaves nothing presented as current and shows the reason; the original configuration recovers |
| 11 | The replay stays a replay | the button exists and its tooltip says so |
| 12 | Existing suites still pass | the composition, model and Godot suites are run separately; Baez's two pre-existing failures are reported separately |

Two further checks make the scene's claims falsifiable against the project's own
records:

- **The startup defaults are compared with `data/ganjave2022/frozen_configuration.json`** —
  all five initial conditions and all four feed values, **value and classification** — so
  a default cannot drift away from the configuration that justified it.
- **The scene's own compatibility panel is the engine's**, not a copy: the permitted and
  refused pairs it shows are read from `--describe-connections` at run time.

Plus one check specifically for the honesty requirement: **the scene must remain honest
when the literature is insufficient**. It asserts the graph is single-model and
connection-free, that the refused pairs involving the simulated model are visible, that
the scene states why only one model is used, and that the Ganjave
`reproduction_status` is still `not_yet_validated` — a scene that made the model look
good must not have changed its status.

### Defects the harness found in the scene, and fixed

Two were real, and both would have made the scene lie.

1. **A failed run was presented as a success.** The result document lists a *failed*
   instance in its `results` array, so "did the run produce results?" answered "yes" for
   a run that produced nothing. The scene therefore cleared the stale flag, showed a
   success message, and displayed no values — with nothing on screen to say the run had
   failed. The test now asks whether an instance **succeeded and published outputs**.
2. **A failed run zeroed the simulation duration.** The same branch took the measured
   duration from an empty trajectory set, so the *next* run asked the model for a
   zero-hour simulation and failed for an unrelated reason. The duration is now only
   adopted when a trajectory actually measured one.

Both were found by driving the real scene, not by reading it.

### Regression — all at or above baseline

| Suite | Baseline | Now |
|---|---|---|
| Composition (Python) | 616 | **618** (+2: the workshop harness is now run from the acceptance suite) |
| `workshop_graph_run.gd` | — | **144** (new) |
| `contract_boundary.gd` | 840 | **840** |
| `ganjave_graph_run.gd` | 51 | **51** |
| `palette_graph_run.gd` | 220 | **220** |
| Morris | 186 | **186** |
| Zieliński | 223 | **223** |
| Baez | 193 passed / 2 failed | **193 passed / 2 failed** |

The two Baez failures remain the known pre-existing stale counts in
`Models/Baez/tests/test_exclusions.py` — hard-coded expectations of 2 workers and 2
registered models, written before Ganjave was added. Unrelated to this work, untouched,
and reported separately as required.

The composition engine, the compatibility rules, the model parameters, the solvers and
every model's validation status are **unchanged**. The graph editor still works and is
still reachable; it is simply no longer the first thing a user sees.

---

## 12. What this is not

- It is not a fluid or CFD simulation. The model computes no spatial quantity.
- It is not a validation. The project's own held-out evaluation of this very model
  **fails** its pre-registered criterion, and the scene says the model is
  `not_yet_validated`.
- It is not a composition. No composed process exists to show.
- It is not a claim of general predictive accuracy. One model, one strain, one medium,
  one scale, one feed recipe, 24 h.
