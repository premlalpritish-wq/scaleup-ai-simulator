# Cross-Model Composition Assessment

**Date:** 2026-10-19
**Scope:** which combinations of the registered models can be composed, which
must be rejected, and why.
**Models assessed:** `morris2011.material_balance@0.1.0`,
`zielinski2019.rhi_process@1.0.0`, `ganjave@0.1.0`.
**Status of the claims below:** this is an assessment of *interfaces*. It does
not validate any model scientifically, and nothing here upgrades a
`reproduction_status`. A connection that runs demonstrates that software carried
a quantity across a boundary; it says nothing about whether the resulting
number is the right one.

---

## 1. Headline

Nine ordered pairs. **Two are permitted. Seven are refused**, in three distinct
ways, and only one of those three needed a new rule.

| Pair | Verdict | Was it already refused? |
|---|---|---|
| Morris → Morris | **permitted** | — it already worked |
| Ganjave → Ganjave | **permitted** (forward cascade) | — it already worked |
| Morris ↔ Ganjave (both directions) | no shared quantity exists | mechanically impossible |
| Morris ↔ Zieliński (both directions) | refused: component identity | **yes**, CG-08 / CG-09 |
| Zieliński ↔ Ganjave (both directions) | refused: dimensionally legal, scientifically unsupported | **no — this was the hole** |
| Zieliński → Zieliński | refused: no supplyable port | no |

**The material finding is §4:** every Zieliński ↔ Ganjave pairing passed the
engine's mechanical checks and *executed to `success_with_warnings`*. A reader
of that result document had no way to tell that the connection meant nothing.

---

## 2. Compatibility matrix

`D` = dimensionally possible; `E` = executed before this change; `R` = executed after.

| Source ↓ / Target → | Morris | Zieliński | Ganjave |
|---|---|---|---|
| **Morris** | **PERMITTED** — conservation across adjacent non-reacting control volumes. `brass_batch_chain.json`, 3 connections, runs. | REFUSED `connection.component_mismatch` / `capability.reactive_balance_refused` (pre-existing) | IMPOSSIBLE — no shared quantity |
| **Zieliński** | REFUSED `connection.component_unattributed` (pre-existing) | REFUSED `connection.cross_model_refused` — no supplyable port (new) | REFUSED `connection.cross_model_refused` (new) |
| **Ganjave** | IMPOSSIBLE — no shared quantity | REFUSED `connection.cross_model_refused` (new) | **PERMITTED** — forward cascade on the model's own declared assumption |

### Per-candidate detail, Zieliński ↔ Ganjave

Every row below is a real pair of published ports that passed the engine's
quantity check, unit conversion, direction check and component check.

| # | Source → Target | Quantities | Before | After | Why |
|---|---|---|---|---|---|
| C | `ganjave/biomass_concentration` → `zielinski/node:N01#wet_biomass_g_per_L_reported` | g/L → g/L | **E** | **R** | Dry-cell weight vs wet biomass; ~3× definitional difference, neither paper prints it |
| D | `ganjave/culture_volume` → `zielinski/node:N01#starting_medium_volume` | L → L | **E** | **R** | Working volume at t=24 h after feeding vs medium charged at t=0; 0.113 L vs 4.0 L |
| F | `ganjave/simulation_time` → `zielinski/node:N01#growth_duration` | h → h | **E** | **R** | 24 h integration horizon vs a unit-operation residence time |
| G | `ganjave/dissolved_oxygen` → `zielinski/node:N01#dissolved_oxygen` | % → 1 | **E** | **R** | One `dimensionless`, four different meanings |
| I | `zielinski/node:N02#wet_biomass_g_per_L` → `ganjave/initial_biomass_concentration` | g/L → g/L | failed at *run* time | **R before run** | Wet biomass is not dry-cell weight |
| K | `zielinski/stream:S09_deae_fraction#fraction_volume` → `ganjave/initial_culture_volume` | mL → L | **E** | **R** | A chromatography eluate volume is not a reactor working volume |
| J | `zielinski/stream:S02_culture_broth#od600_plateau_max` → `ganjave/initial_dissolved_oxygen` | OD600 → % | refused (unit) | refused (unit) | Optical density is not a dissolved-oxygen percentage |
| L | `zielinski/node:N05#implied_refolding_yield_pct` → `ganjave/initial_dissolved_oxygen` | % → % | **E** | **R** | A refolding yield is not an oxygen saturation reading |
| A | `morris/out:D:total` → `zielinski/node:N01#wet_biomass_from_inputs` | kg → g | refused | refused | Component mismatch (pre-existing) |
| B | `zielinski/stream:S03_wet_biomass#wet_biomass_total` → `morris/in:C:total` | g → kg | refused | refused | Component unattributed + reactive-balance refusal (pre-existing) |
| H | `ganjave/glycerol_concentration` → `zielinski/node:N01#glucose_feed_concentration` | g/L → % | refused | refused | Quantity mismatch (pre-existing) |

---

## 3. How each candidate was judged

Every candidate was put through the same six questions. Where a question has no
answer from a source, that is recorded rather than filled in.

### 3.1 Dimensional compatibility

Taken from the declared quantity vocabularies, never from a unit:
`composition/composition/dimensions.py` maps each model's own vocabulary onto
the contract's `Quantity` enum.

| Model | Publishes (outputs) | Accepts (inputs) |
|---|---|---|
| Morris | `mass`, `mass_fraction` | `mass`, `mass_flow`, `mass_fraction`, `amount`, `amount_flow` |
| Zieliński | `mass`, `mass_concentration`, `volume`, `time`, `dimensionless`, `absorbance`, `absorbance_per_volume`, `activity`, `molar_concentration`, `molar_mass` | 17 quantities incl. all of the above |
| Ganjave | `mass_concentration`, `dimensionless`, `volume`, `time` | `mass_concentration`, `dimensionless`, `volume`, `time`, `volume_flow` |

**Morris and Ganjave share nothing.** The sets are disjoint, so that boundary
is not a refusal but an impossibility — there is no port pair to construct.
This confirms, from the declared data, what `ganjave_contract.cross_model_notes`
had asserted in prose.

### 3.2 Semantic compatibility

Equal quantity and convertible unit were treated as necessary and nowhere near
sufficient. Each refusal in §2 records the specific clash:

- **Substance**: dry-cell weight ≠ wet biomass; residual glycerol ≠ culture
  glycerol; a lumped complex substrate fitted with one yield ≠ a defined medium
  component.
- **Basis**: a refolding yield per cent ≠ a dissolved-oxygen percentage of a
  probe's saturation reading.
- **Clock**: a batch integration horizon ≠ a step residence time.
- **Clock and vessel**: a volume at t=24 h after feeding ≠ a charge at t=0 in a
  different vessel.

### 3.3 Organism, strain and process context

| | Morris | Zieliński | Ganjave |
|---|---|---|---|
| Organism | **none — a generic non-reacting control volume** | *E. coli* 20 | *E. coli* |
| Construct | none | recombinant human insulin | cybernetic fed-batch, Table 2 parameters |
| Working volume | declared per instance | 4 L in a 7.5 L fermenter | ~0.113 L in a 3 L bioreactor |
| Medium | declared per instance | LB / yeast extract / peptone | glycerol / yeast extract, fitted |
| Component identity | **required** — refuses without it | **declares it unsupported** | **declares it unsupported** |

Morris is not an organism model and must never be treated as one. Neither
biological model publishes a component set, which is why both are refused into
a Morris control volume (CG-08, CG-09 — pre-existing rules).

### 3.4 Required initial and operating conditions

Each model refuses to run without declaring its own:

- **Ganjave** requires `initial_biomass_concentration`,
  `initial_complex_substrate_concentration` and `initial_dissolved_oxygen`, and
  refuses to choose a run duration — *"a duration is an input of the run, not
  something this worker may choose"*. Two of the three required inputs accept
  **no upstream model at all** (`ganjave_contract.INPUT_CONTRACT`).
- **Zieliński** declares **zero** required ports, so a zero-configuration
  instance is legitimate and runs in its own `evidence_replay` mode.
- **Morris** declares nothing until the instance carries a control volume.

No connection was implemented to satisfy any of these; each is satisfied by
declaring the value on the instance, with its own source reference.

### 3.5 Evidence

Every refusal cites at least two sources in its diagnostic
(`detail.evidence`):

| Source | Used for |
|---|---|
| Morris, Geiger & Fine (2011), *Fundamentals of Material Balances with Applications to Non-Reacting Systems*, Ch. 4 | the one permitted boundary; the non-reactivity of the balance |
| Zieliński et al. (2019), *Protein Expression and Purification* 157:63–69, doi:10.1016/j.pep.2019.02.002 | organism, strain, scale, medium, and every Zieliński port's own provenance |
| Ganjave et al. (2022), *Biotechnology Reports* 33:e00694, doi:10.1016/j.btre.2021.e00694 | organism, scale, eq. (8)–(16), Table 2, and C\* = 0.0075 g/L |
| `Models/Ganjave/models/composition.py` | the model's own declaration of ports, required inputs and unsupported capabilities |
| `composition/composition/dimensions.py` | the declared quantity vocabularies |
| `composition/composition/adapters/ganjave_contract.py` | what Ganjave will and will not accept, in its own words |

### 3.6 Unresolved assumptions

Recorded per boundary in `unresolved` and surfaced in the diagnostic's
`detail.unresolved`. The principal one, for every refused biological boundary:

> A model built to be matched to both — declaring a shared component set, an
> explicit dry-to-wet biomass basis, a scale relationship and a common medium —
> could carry quantities between them honestly. No such model exists here.

---

## 4. What was wrong, and what was implemented

### 4.1 The hole: dimensionally legal, scientifically unsupported

Five candidate connections passed every mechanical check and ran. A worked
example — the acceptance criterion's case:

```
ganjave_fed_batch/biomass_concentration -> zielinski_rhi/node:N01#wet_biomass_g_per_L_reported
before:  status=success_with_warnings   connection codes: [] (none)
after:   status=invalid                  code: connection.cross_model_refused
```

`before` is the danger: a success, with a connection in the result document and
no indication it meant nothing.

### 4.2 Implemented: a declared, enforced cross-model policy

**New — `composition/composition/cross_model.py`.** The whole position as data:
nine boundaries, each with a stance, a reason, cited evidence, unresolved
questions and a remediation. Rules classify **quantities, never port ids**, so
they cannot go stale when a model publishes a new port. An unclassified pair
fails closed with a reason that says exactly that.

Inspectable:

```powershell
cd composition; python -m composition.runner --describe-connections
```

**New — `connection.cross_model_refused` diagnostic.** An error, with
`detail.evidence`, `detail.unresolved`, `detail.stance` and a remediation.

**Engine hook.** `CompositionEngine._validate_cross_model` runs **last**, and
only when nothing above has already refused the connection. Two consequences,
both deliberate: a connection with a more specific mechanical reason keeps it
(no duplicate refusals — verified by `test_a_boundary_the_engine_owns_is_not_
reported_twice`), and the semantic rule sees exactly the set of connections that
passed everything else.

**New — two shipped example graphs**, visible in the Godot *Load example* menu:

* `rejected_cross_model_dcw.json`
* `rejected_cross_model_fraction_volume.json`

Both exit 1, execute nothing, and carry their reason in the status. The second
runs the rule in the opposite direction, to show it is not directional.

### 4.3 Implemented: provenance that survives a hop

The permitted boundary had a provenance gap. The *injected input* carried
`[source, transfer]`, but the **output that re-publishes it named only the
second instance**. A propagated quantity whose chain stopped at the receiving
instance is a propagated quantity with no evidence of where it was propagated
from.

`composition/adapters/morris.py::_carried_chains` now propagates the upstream
record onto outputs that are *literally the injected value*:

```
out:A:w:Cu    source(brass_charge) > transfer(c2) > source(brass_alloying)
out:A:w:Zn    source(brass_charge) > transfer(c3) > source(brass_alloying)
out:A:total   source(brass_alloying)                      <- computed
out:E:Cu      source(brass_alloying)                      <- solved
out:residual:total  source(brass_alloying)                <- computed
```

**A stream total is deliberately excluded.** `out:<stream>:total` is the sum
the balance computed; crediting it to an upstream total would assert the
balance closed — which is precisely what a material balance exists to test.
Every other output keeps its own record alone, because the adapter computes no
dependency map and inventing one would assert a provenance it cannot show.

**No value changed.** `test_propagation_does_not_change_any_value` compares the
forwarded value against the mirrored one; a full byte-comparison of every
output of `brass_batch_chain.json` against the pre-change run is in the
verification log below.

---

## 5. The one place the existing suite overruled me

The first draft of the policy refused **both** self-pairs on the reasoning that
"v0.1 has no iterative solve, so a coupled instance needs a fixed point it
cannot reach". Running the suite produced seven failures in
`test_ganjave_composition.py::TestFailurePropagation`, which cascades residual
glycerol from one culture into the next.

**The suite was right and the rule was wrong.** A forward chain is ordered once
and never iterates; only a cycle needs a solve. Ganjave's own contract already
declares `initial_glycerol_concentration` upstream-supplyable for this exact
purpose, with the assumption *"the upstream value must be glycerol, in this
medium"*.

The position is now:

| Self-pair | Verdict | Reason |
|---|---|---|
| Morris → Morris | permitted | conservation is Chapter 4's premise |
| Ganjave → Ganjave | **permitted** | forward cascade, on the model's declared assumption |
| Zieliński → Zieliński | refused | Zieliński declares **no** supplyable port; its ports are one reported experiment's operating conditions |

The Ganjave cascade is permitted **under an assumption, not as a validated
coupling**: nothing in the paper seeds a second culture from the first. Its
`unresolved` field says so, and
`TestSameModelOnBothSides::test_the_cascade_still_runs_and_is_not_refused`
guards that it still runs and is not refused.

This is recorded because it is the kind of generalisation that looks reasonable
and is wrong. Two tests now exist that would fail if it were reintroduced.

---

## 6. Tests

### New: `composition/tests/test_cross_model.py` — 46 tests

| Class | Covers |
|---|---|
| `TestThePermittedBoundary` | the boundary runs; exactly two boundaries are permitted; **provenance survives the hop**; a computed total is *not* credited; propagation changed no value |
| `TestBoundariesTheEngineAlreadyRefuses` | Morris↔Zieliński refused by CG-08/CG-09, with **no duplicate** diagnostic; Morris and Ganjave share no quantity |
| `TestDimensionallyLegalButUnsupported` | **the acceptance case**, 5 real candidates × 4 assertions: refused before execution, no instance runs, the reason is in the model's own words, the evidence and remediation are attached |
| `TestSameModelOnBothSides` | the corrected Ganjave cascade (§5); Zieliński's refusal |
| `TestTheShippedRefusals` | both examples refuse, state what they demonstrate, execute nothing |
| `TestTheDeclaredPosition` | `--describe-connections` prints; every boundary has a reason and cites something; every ordered pair of *registered* models is declared; unclassified pairs fail closed; rules classify quantities not ports; **no boundary claims to have been validated** |
| `TestTheModelsOwnPositionsSurvive` | Ganjave's two non-supplyable inputs still refuse an upstream; a declared *literal* is still accepted for them; the replay graph still publishes 196 values; Baez is not registered |

### Extended: `composition/tests/godot/palette_graph_run.gd` — 149 → **174 checks**

* `_check_the_permitted_connection_runs_through_the_ui` — loads
  `brass_batch_chain` **through the example picker**, presses the real **Run**
  button, asserts the connection is on the canvas, and asserts the forwarded
  `out:A:w:Cu` chain names the upstream instance, the connection id and the
  local solve.
* `_check_a_refused_connection_is_refused_through_the_ui` — loads both new
  examples **through the picker**, presses **Run**, asserts
  `connection.cross_model_refused`, error severity, the phrase "scientifically
  unsupported", a non-empty remediation, evidence, and **no instance executed**.

### Regression

| Suite | Before | After |
|---|---|---|
| `composition` | 402 passed | **448 passed** (+46) |
| `Models/Morris` | 186 passed | 186 passed |
| `Models/Zielinski` | 223 passed | 223 passed |
| `Models/Baez` | 193 passed, **2 failed** | 193 passed, **2 failed** — unchanged, pre-existing |
| `contract_boundary.gd` | 840 passed | 840 passed — **unmodified** |
| `ganjave_graph_run.gd` | 51 passed | 51 passed — **unmodified** |
| `palette_graph_run.gd` | 149 passed | 174 passed |

The two Baez failures are the stale hard-coded counts
(`workers == [morris, zielinski]`, registry lists exactly two models) written
before Ganjave was registered. They are unrelated to this task and untouched.
What they assert — that Baez is absent — still holds.

---

## 7. What was not done, and why

* **Baez was not registered.** It is absent from `REGISTRATIONS`, has no
  adapter, no worker, no contract and no graph, and
  `TestTheModelsOwnPositionsSurvive::test_baez_is_not_registered_and_stays_out`
  asserts it. Assessing an interface requires the interface.
* **No conversion factor, parameter, initial condition or default was
  invented.** Notably, the dry-to-wet biomass ratio that would make C legal
  exists in neither paper, so C stays refused.
* **No published equation was modified.** The only adapter touched is
  `morris.py`, and only its provenance chain — verified byte-for-byte against
  every output value.
* **No contract was weakened.** The new rule can only add refusals. It is
  skipped when anything else has already refused, so no existing diagnostic
  changed.
* **No validation status was upgraded.** `test_no_boundary_claims_to_have_been
  validated` enforces this, and Ganjave's result still carries
  `reproduction_status: not_yet_validated`.

---

## 8. Open questions

1. **Is the Ganjave forward cascade scientifically defensible, or only
   permitted?** It is currently permitted under the model's own assumption. A
   worked example — feeding one 24 h batch into a second — is not in either
   paper. Someone with process knowledge should decide whether the assumption
   is acceptable or whether the cascade should be downgraded to a warning.
2. **Should `dimensionless` be split?** One contract quantity carries optical
   density, refolding yield, probe saturation and specific growth rate. That is
   the root cause of candidate G and L. Splitting it would let the engine refuse
   them mechanically — but it is a contract change with wide blast radius, and
   the semantic rule now covers it correctly.
3. **Zieliński's 139 input ports are all operating conditions and reported
   measurements.** None is upstream-supplyable, which is why the self-pair is
   refused. If a future Zieliński model exposed a genuine stream, that verdict
   would need revisiting with the new source in hand.
4. **The Morris provenance rule is deliberately narrow.** It propagates only
   where an output is literally the value that arrived. A dependency map from
   the balance would let it say more, and would be worth having — but deriving
   one from an engine that does not publish it would be inventing provenance.
5. **The replay scene is unaffected** and still publishes the Zieliński model's
   196 values over its own fixed graph, with no connections. It is not a
   cross-model composition and is not treated as one.

---

## 9. Reproducing

```powershell
cd "D:\Godot\Scaleup AI\pilot\composition"

# the whole declared position, as data
python -m composition.runner --describe-connections

# the refusals, as shipped examples
python -m composition.runner --graph examples/rejected_cross_model_dcw.json --result "$env:TEMP\a.json"
python -m composition.runner --graph examples/rejected_cross_model_fraction_volume.json --result "$env:TEMP\b.json"

# the permitted boundary, with its provenance
python -m composition.runner --graph examples/brass_batch_chain.json --result "$env:TEMP\c.json"

# the suite
python -m pytest tests/test_cross_model.py -o addopts= -q        # 46

# the same two refusals through the Godot UI
cd ..
D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe `
  --headless --path . --script res://composition/tests/godot/palette_graph_run.gd
```

### Files

| Path | Role |
|---|---|
| `composition/composition/cross_model.py` | the declared position, as data |
| `composition/composition/diagnostics.py` | `CONNECTION_CROSS_MODEL_REFUSED` |
| `composition/composition/engine.py` | `_validate_cross_model`, called last and only on an otherwise-legal connection |
| `composition/composition/runner.py` | `--describe-connections` |
| `composition/composition/adapters/morris.py` | `_carried_chains` — provenance across a hop |
| `composition/examples/rejected_cross_model_dcw.json` | shipped refusal, mass_concentration |
| `composition/examples/rejected_cross_model_fraction_volume.json` | shipped refusal, volume, reverse direction |
| `composition/tests/test_cross_model.py` | 46 tests |
| `composition/tests/godot/palette_graph_run.gd` | +25 UI checks |