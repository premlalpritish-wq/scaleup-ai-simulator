# Zieliński 3D Replay — Cross-Paper Scientific Context

**Date:** 2026-10-20
**Scope:** what the Zieliński 3D replay now shows about the rest of the ScaleUp
AI research library, what that other research contributes, and what the
compatibility engine says about composing it with the replayed batch.
**Focus model:** `zielinski2019.rhi_process@1.0.0`
**Status of the claims below:** this is an *assembly of the project's own
records*. It is not a scientific validation of any model, it proposes no
connection, and it upgrades no `reproduction_status`. A connection that runs
demonstrates that software carried a quantity across a boundary; it says
nothing about whether the resulting number is the right one.

---

## 1. What the replay now shows

The replay's right column gains a sixth section, **Related research and
connected knowledge**, built by a reusable `CrossPaperPanel` from two payloads
the scene loads through the same verified GDScript → Python boundary the model
run uses:

| Payload | Command | What it carries |
|---|---|---|
| the authoritative compatibility position | `python -m composition.runner --describe-connections` | every ordered pair of registered models, its stance, its evidence, what is unresolved |
| the assembled context | `python -m composition.runner --describe-cross-paper-context zielinski2019.rhi_process` | the other registered models, what each addresses, what it shares with the focus model, the papers examined against the focus model's declared gaps |

The panel holds **no model list, no quantity pair, no verdict and no paper of
its own**. Every verdict badge, stance and permitted flag is read from the
connections payload, matched on the ordered pair; every model description is
read from the registry and the models' own manifests. A rule changed in
`composition/composition/cross_model.py` reaches the panel without anything in
GDScript being edited.

**The panel is open by default**, so opening the replay visibly connects it to
the rest of the project's research without any click.

### What each card shows

For every registered model other than the focus model:

- the model's own title (or its identifier, when the model declares no
  model-level title — never a phrase the panel composed);
- the exact `model_id@model_version` reference, the declared source paper and
  DOI, each with its provenance (a field the artefact does not state is shown
  as *not declared*, with the registry's own reason);
- what process or scientific question it addresses, in its own words;
- what it shares with the focus paper;
- the verdict for each direction: **permitted**, **conditionally permitted**,
  **refused**, or **unresolved** — read from the engine's stance and evidence
  basis;
- the evidence supporting the assessment;
- for refused pairs: the specific difference, the quantity pairs the policy
  names with their own reasons, what would resolve the gap, and what to do
  instead;
- a standing note that the model is **context only — not connected** to this
  replay.

Clicking **Inspect scientific context** on a card opens the full assessment —
both directions, per-pair detail, assumptions, evidence and remediation — in
the same scene, without leaving the replay.

---

## 2. The models shown

The registry lists three models. The focus model is the replayed one; the
panel shows the other two.

### 2.1 `ganjave@0.1.0` — Ganjave et al. (2022) cybernetic fed-batch model

| Field | Value | Origin |
|---|---|---|
| Title | Ganjave et al. (2022) cybernetic growth and fed-batch model | the model's own manifest |
| Source paper | Ganjave et al. 2022, *Biotechnology Reports* 33:e00694, doi:10.1016/j.btre.2021.e00694 | the model's own `source_ref` |
| DOI | *not declared* (the artefact declares no DOI; none is inferred) | the registry's tracking |
| Declared capabilities | batch simulation over eq. (8)–(11); fed-batch simulation over eq. (12)–(16); full state trajectories with solver report and run provenance; structured diagnostics on every failure | the model's own manifest |
| Declared unsupported | component identity (S2 is a lumped mixture with one fitted yield; X is a total dry-cell weight; no port carries components); no protein-expression, inclusion-body or purification model; paper reproduction not validated | the model's own manifest |

**What it shares with the Zieliński paper** (from the engine's declared
reason):

> Both models describe an *Escherichia coli* fed-batch culture. Both publish
> dimensionless, mass_concentration, time, volume and volume_flow, so a
> connection between them would be mechanically constructible for these
> quantities — which is why the refusal is semantic, never dimensional.

**Compatibility decision: refused, both directions** — stance
`refused_dimensional_only`, evidence basis `documented_incompatibility`.

- **Ganjave → Zieliński.** *Fundamental difference:* neither quantity nor
  unit is what stands between them. They are two different experiments:
  different strain, different construct, different medium, different scale,
  different objective, five years apart. A matching quantity here is a
  coincidence of the vocabulary, not a shared physical quantity.
- **Zieliński → Ganjave.** *Fundamental difference:* the two cultures share an
  organism and nothing else. Nothing in either paper declares a relationship
  between them: not a component set, not a biomass basis, not a scale
  relationship, and not a medium.

**Quantity pairs the policy names**, each with its own reason and standing:

| Pair | What stands between them | What would resolve it |
|---|---|---|
| mass_concentration → mass_concentration | dry-cell weight vs wet biomass; residual glycerol vs medium components; a lumped complex substrate vs defined components. No substance is shared, and the two differ by a conversion factor neither paper prints. | a strain- and construct-matched model declaring the biomass basis on both sides |
| volume → volume | a working volume after 24 h of feeding in a 3 L vessel vs charges made at t = 0 in a 7.5 L fermenter | a vessel-scaled model that declares the working-volume relationship it is using |
| dimensionless → dimensionless | one contract quantity, at least four different meanings (OD600, refolding yield, inclusion-body fraction, probe saturation) | distinct contract quantities, or a declared conversion carrying the missing calibration (C\*, an OD600-to-DCW factor, a yield basis) |
| time → time | a 24 h integration horizon vs unit-operation residence times | a model that consumes a batch horizon and declares how it apportions it across steps |

**What it could legitimately contribute** — as context, never as a driver of
this replay: the capability to integrate growth, substrate and dissolved-oxygen
dynamics over a fed batch (eq. 8–16 with full state trajectories), which is
precisely the kind of process understanding the Zieliński model declares
itself unable to supply (see §4). That capability cannot currently be
connected to this replay: see the difference above.

**What prevents direct composition** — the two cultures are different
experiments. The engine's unresolved field states what would have to exist
first:

> A model built to be matched to both — declaring a shared component set, an
> explicit dry-to-wet biomass basis, a scale relationship and a common medium
> — could carry quantities between them honestly. No such model exists here.

**Is this a proven physical incompatibility?** No. The refusal is the engine's
documented position on the *interfaces as declared*, and it is presented as
such: the same cultures could be connected by a future matched model. The
panel's verdict column reads **refused**, and the gap section names the
missing model — it does not claim the two papers are scientifically unrelated.

### 2.2 `morris2011.material_balance@0.1.0` — a non-reacting material-balance engine

| Field | Value | Origin |
|---|---|---|
| Title | *not declared* (the title is declared per instance, not per model) | the registry's tracking |
| Source paper | *not declared* (declared per instance) | the registry's tracking |
| What it addresses | Morris, Geiger & Fine (2011), *Fundamentals of Material Balances with Applications to Non-Reacting Systems*, Chapter 4: conservation equations sum(inflow) − sum(outflow) − accumulation = 0, with no reaction term | the composition layer's declared evidence for this model |
| Ports | declared per instance (no model-level port set) | the model requires an instance `system` declaration |

The panel shows this model honestly: it has no model-level title, paper or
DOI, and its row says so rather than inventing a phrase. Its description is
lent from the project's own cited evidence for it.

**What it shares with the Zieliński paper** (computed from the declared
vocabularies):

> Both publish mass, so a connection between them would be mechanically
> constructible for these quantities; the refusal is semantic, not
> dimensional.

The overlap is why this boundary is interesting: the two models' quantity
vocabularies intersect (mass), so a connection is mechanically
constructible — and the engine still refuses it.

**Compatibility decision: refused, both directions** — stance
`refused_component_identity`, evidence basis `documented_incompatibility`,
**enforced by the engine's own component rules (CG-08/CG-09)**.

- **Morris → Zieliński.** *Fundamental difference:* Zieliński publishes
  process roles, not conserved chemical entities: no stream of its own carries
  a component amount or a mass fraction. A Morris port either names a
  component (and the names will not agree) or is a control-volume total whose
  every entering unit must be attributable to one (and it is not). A Zieliński
  quantity forwarded into a Chapter 4 balance would therefore be relabelled as
  a component, which is an invented assumption that silently determines the
  answer.
- **Zieliński → Morris.** *Fundamental difference:* the same refusal, and a
  stronger one — Morris is a non-reacting control volume, so drawing a balance
  across a boundary whose model publishes neither component identity nor
  reaction terms is the case CG-09 names explicitly as numerically valid and
  physically wrong. Zieliński's own manifest declares component_identity
  unsupported, in those words.

**What it could legitimately contribute** — as context: a non-reacting
control-volume material balance could in principle cross-check mass recovery
across the purification steps this replay shows (the replay reports wet
biomass, inclusion bodies and a mass deviation from theory — all material
quantities). That cross-check cannot currently run: the streams would need
declared component identity.

**What prevents direct composition** — component identity. The engine's
remediation: *declare the component mapping explicitly, with a justification
and a component definition, or do not connect the ports.*

---

## 3. What the engine permits — and why none of it connects two papers

The compatibility engine permits exactly **two ordered pairs, both
same-model**:

| Pair | Standing | Premise |
|---|---|---|
| `morris2011.material_balance → morris2011.material_balance` | **permitted** | conservation across adjacent non-reacting control volumes is the premise the balance engine exists to apply (Morris 2011, Ch. 4). Shipped example: `brass_batch_chain.json`. |
| `ganjave → ganjave` | **permitted (forward cascade)**, under a stated assumption | a forward cascade is a sequential use, not a fixed point. Ganjave's contract declares exactly one upstream-supplyable port for it (`initial_glycerol_concentration`), on the assumption that the upstream value is residual glycerol in this medium. |

The panel reports these as what they are — **boundaries within one paper, not
connections between different papers** — and states beside them that this
replay declares **0 connections**. The Ganjave cascade additionally carries
the engine's own caveat, shown as a required assumption rather than hidden:

> The cascade is permitted under the model's declared assumption, not
> validated by it: nothing in the paper seeds a second culture from the first.

A permitted verdict is never rendered as an implemented connection anywhere in
the panel: every related model's record carries
`connection_in_replay: false`, and each card says *context only — not
connected*.

---

## 4. The focus model's own declared gaps, and the papers examined against them

The replay already showed what the Zieliński model cannot resolve. The new
panel lists those gaps alongside the **ingested papers that were examined
against them** — papers, not registered models, and none connected to the
replay:

| Finding | Paper | Quantity | Value | Verdict | Independence |
|---|---|---|---|---|---|
| CF-001 | Senn et al. (1994), *Biochim Biophys Acta* 1201(3):424–436 | Monod Ks (half-saturation glucose concentration) | 88 µg/L (range 40–88) | incompatible conditions | independent |
| CF-002 | Smaluch et al. (2023), *Eng Life Sci* 23(1):e2100157 | specific growth rate, single cell | 0.61 /h (range 0.19–0.61) | incompatible conditions | independent |
| CF-003 | Mikiewicz et al. (2017), *PLoS ONE* 12(3):e0172600 | growth-phase operating density ranges | OD600 25–35 | incompatible conditions | **not independent** — the supporting text also appears in the Zieliński paper |

CF-003 is the closest-matched publication that exists — same institute, same
host strain, same vector, same medium, same fermenter, same pH-stat strategy —
and it still supplies no kinetic parameter. Its verdict is *incompatible
conditions*, and its independence is flagged rather than hidden: it cannot
corroborate the target paper because its supporting passage is the target
paper's own text reached through a second paper.

The gaps themselves (growth kinetics, oxygen transfer, induction time) are
listed from the model's own declaration. The panel's answer to each is the
same as the evidence panel's: the only route that would close them is a
separate, explicitly parameterised model fitted to batch data from this
strain — not an import from another registered model.

---

## 5. Evidence sources

Every sentence in the panel traces to a record the project keeps:

| Source | Used for |
|---|---|
| `composition.registry` (`python -m composition.registry`) | model identity, titles, source papers, DOIs, port surfaces, capabilities, assumptions, scientific status — each tracked with its provenance; unknown fields shown as unknown |
| the models' own manifests (`--describe-model`) | summary, capabilities, unsupported capabilities, assumptions |
| `composition.cross_model` (`--describe-connections`) | the authoritative compatibility position: every ordered pair, stance, evidence, unresolved, remediation, assumptions, evidence basis |
| `composition.evidence.catalogue` (`python -m composition.evidence`) | the focus model's declared gaps and the examined papers, with citations, DOIs, verbatim quotes, verdicts and independence |
| `Models/Zielinski/scaleup_ai` | the process graph whose ports the adapter publishes, with their provenance |
| `composition/composition/dimensions.py` | the declared quantity vocabularies of all three models, kept as data |
| `composition/composition/adapters/ganjave_contract.py` | what Ganjave will and will not accept on an input port, in the model's own words |
| Morris, Geiger & Fine (2011), Ch. 4 | the one permitted boundary; the non-reactivity of the balance |
| Ganjave et al. (2022), *Biotech. Reports* 33:e00694 | organism, scale, eq. (8)–(16), Table 2, C\* = 0.0075 g/L |
| Zieliński et al. (2019), *Protein Expr. Purif.* 157:63–69, doi:10.1016/j.pep.2019.02.002 | organism, strain, scale, medium, and every Zieliński port's own provenance |

---

## 6. Remaining gaps

1. **No cross-paper connection is implemented, and none is proposed.** Every
   related model is context. The two permitted boundaries are same-model; the
   replay graph declares no connections; the panel says so on every card.
2. **The Ganjave ↔ Zieliński gap is a missing model, not a missing fact.** A
   strain- and construct-matched model declaring a shared component set, a
   dry-to-wet biomass basis, a scale relationship and a common medium could
   carry quantities between them honestly. Building that model is a scientific
   task, not a composition-layer task, and it is not attempted here.
3. **The Morris boundary is a missing component declaration.** A non-reactive
   boundary with an explicitly declared component set (and its justification)
   would allow a material-balance cross-check of the purification train.
   Until then the engine's CG-08/CG-09 refusals stand.
4. **The focus model's own gaps remain open.** Growth kinetics, oxygen
   transfer and induction time are still unknown; the examined papers do not
   supply them under matching conditions, and the model's policy is to keep
   them unknown rather than adopt an unmatched value.
5. **Ganjave's model-level DOI is not declared.** The panel shows the
   citation from the model's own `source_ref` and states that no DOI is
   declared; none is inferred from the author or title.
6. **Morris has no model-level title, paper or DOI.** The panel names it by
   its identifier and lends the project's cited evidence for it, rather than
   inventing a description.

---

## 7. Tests

### New: `composition/tests/test_cross_paper.py` — 30 tests

| Class | Covers |
|---|---|
| `TestThePayloadComesFromProjectRecords` | the focus reference; every other registered model is shown; versions preserved; titles/papers are the models' own; scientific status not upgraded; an unresolvable reference fails without substituting |
| `TestVerdictsComeFromTheCompatibilityEngine` | every pair matches `cross_model`'s declared boundary; Ganjave refused both directions with context, difference, evidence, unresolved and remediation; Morris engine-enforced; per-pair reasons survive; the embedded connections section equals the CLI output |
| `TestPermittedIsNotImplemented` | the two permitted pairs are same-model only; no related model is presented as connected; the replay scope declares no connections; the graph on disk declares none; the graph still runs and publishes 196 values |
| `TestRefusalsShowContextDifferenceAndResolution` | the shared organism/process domain; the specific clash; the shared context is quoted, not invented; what would resolve the gap |
| `TestUnresolvedIsNotPresentedAsIncompatibility` | `evidence_limited` is marked as such; no refusal claims the models are permanently or physically unrelated; the matched-model resolution survives |
| `TestExaminedPapersAreContextNotModels` | citations, verdicts and independence survive; the papers are marked as not models; the focus model's declared gaps are listed; a model without the catalogue gets an honest scope |
| `TestNothingScientificChanged` | no equations or solver settings in the payload; registry records unchanged; the rule registry unchanged |

### New: `composition/tests/godot/replay_cross_paper.gd` — 81 checks

Drives the **real replay scene** through its own subprocess load, and asserts
from the panel's accessors: the panel is present and shows at least one other
registered model; the model list matches the registry command exactly; the
focus reference is versioned; verdicts equal the authoritative payload; the
permitted pairs are same-model and the replay declares none; refused pairs show
context, difference, evidence and remediation; unresolved reads as unresolved;
evidence and versions are preserved; the replay is still labelled an evidence
replay; the replay graph still runs unconnected and publishes 196 values.

### Regression

| Suite | Result |
|---|---|
| `composition` (pytest) | **648 passed** (618 before + 30 new) |
| `Models/Zielinski` | 223 passed — unchanged |
| `Models/Morris` | 186 passed — unchanged |
| `Models/Baez` | 193 passed, **2 failed** — the same pre-existing failures (stale hard-coded model counts), unrelated and untouched |
| `palette_graph_run.gd` | 220 checks passed — unchanged |
| `contract_boundary.gd` | 840 checks passed — unchanged |
| `ganjave_graph_run.gd` | 51 checks passed — unchanged |
| `workshop_graph_run.gd` | 144 checks passed — unchanged |
| `ui_visibility_probe.gd` | ran clean — unchanged |

No equation, solver setting, model parameter, graph document or validation
status was changed. The only engine-adjacent edit is additive:
`cross_model.Boundary` now exposes `evidence_basis` and `assumptions` in its
serialised form, so the authoritative output distinguishes a documented
incompatibility from an absence of a judgement — a distinction the panel
displays rather than makes.

---

## 8. Reproducing

```powershell
cd "D:\Godot\Scaleup AI\pilot\composition"

# the assembled context for the replay
python -m composition.runner --describe-cross-paper-context zielinski2019.rhi_process --result "$env:TEMP\context.json"

# the authoritative compatibility position
python -m composition.runner --describe-connections --result "$env:TEMP\connections.json"

# the new tests
python -m pytest tests/test_cross_paper.py -o addopts= -q            # 30

# through the real replay scene
cd ..
& "D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe" `
  --headless --path . --script res://composition/tests/godot/replay_cross_paper.gd
```

### Files

| Path | Role |
|---|---|
| `composition/composition/cross_paper.py` | assembles the cross-paper context from the registry, the manifests, `cross_model` and the evidence catalogue; the `--describe-cross-paper-context` entry point |
| `composition/composition/cross_model.py` | the authoritative position — read, not restated; `Boundary` gains `evidence_basis` and `assumptions` in its serialised form |
| `composition/composition/runner.py` | `--describe-cross-paper-context`; `--describe-connections` gains `--result` |
| `scripts/cross_paper_panel.gd` | the reusable panel: renders the two payloads, holds no rules of its own |
| `scripts/replay3d.gd` | the replay scene: loads both payloads through the same boundary and shows the panel as section 6 |
| `composition/tests/test_cross_paper.py` | 30 tests |
| `composition/tests/godot/replay_cross_paper.gd` | 81 UI checks against the real replay scene |
