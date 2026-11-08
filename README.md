# ScaleUp AI Simulator

A Godot + Python workbench for composing scientific process models, with a 3D
evidence-replay view of the Zieliński et al. (2019) recombinant human insulin
process.

It has three parts:

| Part | Where | What it is |
|---|---|---|
| **Composition layer** | `composition/` | A typed, auditable layer that connects independent models through declared ports and runs them in dependency order. It is *import-only*: it never writes into a model package. |
| **Graph editor** | `scenes/composition.tscn` | A Godot window for editing composition graphs and running them against the Python runner. |
| **3D evidence replay** | `scenes/replay3d.tscn` | An orbitable schematic of the fermentation vessel plus the model's published growth and purification data. |
| **Scientific Gap Discovery** | section 8 of the replay | What scientific models and experimental evidence the insulin simulation is missing, which existing papers touch each gap, and what to look for next. |
| **Prompt to simulation** | `scenes/prompt_simulation.tscn` | Describe the Zielinski insulin run in words; the local interpreter maps it to real model ports, validates the configuration and executes the existing replay. |
| **Research to simulation** | `scenes/research_workflow.tscn` | Start from a problem document instead of a model: acquire literature from a local corpus, verify every quote and number, build an evidence-constrained model, and execute it through the same composition runner. |
| **Pecan evidence workflow** | `scenes/pecan_workflow.tscn` | The compiled pecan case as a clickable step graph: green nodes are direct pecan evidence, amber nodes are analogue hypotheses, grey is method review. Clicking a step shows its action, verbatim passage, source DOI, classification and unknowns. An evidence audit, not a simulator. Opened from the workshop header. |
| **Pecan 3D process replay** | `scenes/pecan_replay.tscn` | An animated physical simulation of the TRIzol extraction bench: the tissue clump is carried into the tube, TRIzol is dispensed with a visible stream and rising level, the tube is shaken with rising bubbles, the tube is moved into the rotor and spun, two phases separate, and the upper phase is aspirated and dispensed into a second tube. Play/pause/scrub, orbit and click objects for their evidence. Every motion is illustrative: the paper reports no volumes, speeds or durations, and none is displayed. |
| **Research explorer (browser)** | `web/research/` | The same pecan case in a browser, for a researcher with nothing installed: evidence with provenance and hypothesis status, research gaps, a protocol form that runs the real workflow, and Markdown/PDF export. Served at `/research/` by `python -m api.app`. |

`python -m composition.gaps --check` verifies the Scientific Gap Discovery
analysis against the model, compatibility records and paper library. The full
write-up, example payload and test results are in
[`reports/SCIENTIFIC_GAP_DISCOVERY.md`](reports/SCIENTIFIC_GAP_DISCOVERY.md).

**Prompt to simulation** is reached from the workshop header. It uses a local,
deterministic interpreter rather than a cloud LLM, and validates every mapped
parameter against the Zielinski manifest before executing. See
[`reports/PROMPT_TO_SIMULATION.md`](reports/PROMPT_TO_SIMULATION.md).

**Research to simulation** is the stage before a model exists. It takes a problem
document, discovers and acquires papers from a local corpus (no network client),
verifies that every encoded claim is a verbatim quote from the acquired text and
that every number appears in its own quote, builds an **evidence-constrained
protocol audit**, and runs that model through the existing composition runner.
Direct target-organism evidence and analogous-species evidence are kept separate;
the spruce and pigeonpea protocols enter only as hypotheses, and the parameters
the pecan paper never prints stay unknown. The model reports no RNA yield, RIN or
degradation rate, because the sources do not state one. The workflow, the pecan
artifacts and the verified results are documented in
[`reports/RESEARCH_TO_SIMULATION_ARCHITECTURE.md`](reports/RESEARCH_TO_SIMULATION_ARCHITECTURE.md).

**Research explorer (browser)** puts that worked example in front of a researcher
who has nothing installed. `python -m api.app` serves the page at `/research/` and
the small API behind it: the case overview, an evidence explorer that keeps direct
and analogous claims apart, the research gaps, a protocol form that runs the same
workflow, and Markdown/PDF export with a feedback form. It needs no API key and
sends nothing to a third party. Deployment, privacy notice and verification are in
[`reports/RESEARCH_EXPLORER.md`](reports/RESEARCH_EXPLORER.md).

The two scientific models live under `Models/` and are untouched by the
composition layer:

* `Models/Morris` — deterministic material-balance engine after Morris, Geiger &
  Fine (2011), Chapter 4.
* `Models/Zielinski` — evidence-traceable model of Zieliński et al. (2019).

---

## ⚠️ Read this before drawing conclusions from the 3D view

**The Zieliński model is an evidence replay, not a predictive simulator.**

It restates numbers that were read out of a published paper and applies the
accounting identities that paper supports. It reports **no growth kinetics, no
oxygen-transfer data, no AU calibration and no purification model**, and it
declares those absences explicitly rather than inventing them.

Consequently the 3D scene:

* **does not predict** growth, dissolved oxygen, fluid dynamics, mixing,
  oxygen transfer or scale-up performance;
* **does not compute** a spatial field — there is no concentration, velocity or
  temperature field in the model to compute. The liquid colour is a
  legend-mapped encoding of one published bulk number, and the scene says so;
* **does not animate** the liquid level — the working volume is reported once and
  no feed or evaporation is reported;
* **never substitutes zero or a guess** for a missing quantity. The panel *What
  this model cannot tell us* shows the unresolved items with the model's own
  explanation for each.

Running the model in predictive mode resolves nothing, which is the correct
outcome, not a failure.

---

## Requirements

| Tool | Version | Notes |
|---|---|---|
| **Godot** | **4.7.2-stable** | The project declares the `4.7` feature set. Developed and verified on 4.7.2-stable. |
| **Python** | **3.11 or newer** | Declared by all three `pyproject.toml` files. Verified on 3.14.7. |
| **pytest** | 8 or newer | Only needed to run the tests. Verified on 9.1.1. |

**There are no third-party runtime dependencies.** Everything in the
application uses the Python standard library only.

---

## Setup

```bash
git clone https://github.com/premlalpritish-wq/scaleup-ai-simulator.git
cd scaleup-ai-simulator
```

Optionally create a virtual environment (recommended, not required):

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

Install the test dependency:

```bash
python -m pip install "pytest>=8"
```

Nothing needs to be installed for the application itself — the models and the
composition layer are imported straight from the repository.

### Opening in Godot

1. Launch Godot 4.7.2 and choose **Import**.
2. Select `project.godot` at the repository root.
3. On first open, let Godot complete its import pass (it regenerates everything
   under `.godot/`). No asset in this project requires a manual import.

The main scene is the graph editor.

### Configuring the Python executable

The application shells out to `python` and resolves it from your `PATH`. The
composition package is found automatically relative to the project root, and
`PYTHONPATH` is exported to the subprocess by the application itself — you do
**not** need to set it.

If `python` is not on your `PATH` (for example, only `py` or `python3` is), two
one-line edits are needed. This is a known rough edge, not a design:

| File | Line | Change |
|---|---|---|
| `scripts/main.gd` | ~42 | `_python_path = "python"` → your interpreter |
| `scripts/replay3d.gd` | ~117 | `CompositionRunner.new("python", …)` → your interpreter |

---

## Running it

### The graph editor

The **Models** panel above the canvas lists every model the composition layer
has registered — read from `python -m composition.runner --list-models`, never
from a list kept in the editor. Press **Add** on a row, fill in what that model
declares it needs, and the instance appears on the canvas.

Nothing is defaulted on your behalf. A required input with no value blocks the
Add button and quotes the model's own reason for having no default. Units come
from the contract, so a value can only be typed in a unit its quantity actually
has.

Each row also carries the compatibility engine's standing for that model, read
from `python -m composition.runner --describe-connections`: the engine's own
reason on the row, and its evidence basis and remediation in the tooltip. A model
the engine refuses says so before it is added, and the verdicts narrow to the
models already in the graph. The editor holds no rule of its own — change a
verdict in `composition/cross_model.py` and the rows change with it. The panel
also says that its verdicts cover registered models only: an artefact with no
adapter produces no boundary in the engine's payload, so leaving it out of the
list is not a judgement about it.

Below it, **Ingested papers** lists every paper folder under `Models/`, read from
`python -m composition.runner --describe-papers`. Each entry names its source and
states whether it can execute and whether the engine has a position on it, with
the recorded reason when it does not. Nothing in that list has an **Add** button:
a paper with no model is shown so that it cannot be silently absent, not so that
it can be run.

Two shapes of model, because the models themselves differ:

| Shape | What the form asks for |
|---|---|
| **Fixed port set** (Zieliński, Ganjave) | The input ports the manifest marks `required`, with their declared quantity, unit and the model's own explanation. Optional ports are behind a toggle. |
| **Declared per instance** (Morris) | A control volume. The model publishes no model-level ports until one exists, so the form offers a blank declaration and every declaration the project already ships, with their provenance. |

Press **Run** to validate and execute the loaded graph. Press **Validate only**
to produce an execution plan without running anything.

Choose a graph from the **Load example** menu. Each shipped example has a
documented exit code; rejected examples are meant to fail, and their failure
messages are the demonstration.

**Zieliński replay** opens a separate scene that re-plays one published batch.
It is a predefined experiment, not a simulation — see the warning at the top of
this file — and it is not how you reach a model.

### The 3D evidence replay

Press the **3D replay** button in the editor toolbar, or run
`scenes/replay3d.tscn` directly. The scene executes the model on load; it takes
a second or two.

| Control | What it does |
|---|---|
| **Run model** | Re-executes the model and reloads its published values |
| **Pause / Resume** | Freezes or resumes the replay clock |
| **Reset** | Returns to the documented initial state (culture time 0, camera home) |
| **Playback speed** | 0.5× / 1× / 2× / 4× |
| **Back to graph editor** | Returns to the graph editor scene |
| left-drag on the 3D view | Orbit the camera |
| mouse wheel | Zoom |

The default view is organised in six sections:

1. **Reactor and operating conditions** — the vessel, and the stated operating
   conditions.
2. **Culture growth over time** — culture time, the density reading, and the
   published growth curve with its declared uncertainty.
3. **Purification results** — the instrument signal after each purification
   step.
4. **What this model cannot tell us** — the unresolved quantities, each with the
   model's own reason, and a button to investigate it.
5. **Detailed evidence and technical diagnostics** *(collapsed)* — every one of
   the 196 published values with its exact field names, its method, its source
   and its full provenance chain.
6. **Related research and connected knowledge** — the other models and papers
   this project has already ingested, and what the compatibility engine says
   about composing them with this replay. Open by default: each related model
   is a card showing its title, versioned reference, source paper, what it
   shares with this paper, the permitted / conditionally permitted / refused /
   unresolved verdict read from the engine's declared position, the evidence,
   and — for refused pairs — the specific difference, what would resolve the
   gap, and what to do instead. Clicking **Inspect scientific context** opens
   the full assessment in place. Every card states that the model is context
   only: none of them drives this replay, and the replay's graph declares no
   connections.

Every displayed value carries a plain-language provenance label — *stated in the
source*, *read from a published figure*, *calculated from the available data*,
or *not established by the available evidence*.

---

### Investigating a missing quantity

An unknown quantity used to be a dead end: the screen said what was missing and
stopped. Under each one there is now an **Investigate** button.

**Section 5, "Detailed evidence and technical diagnostics", has two panels that
open to show real content.** "All data and evidence" lists every published value
with its field name, value, unit and provenance; selecting a row shows its
method, source and provenance chain. "Run status and technical details" shows
exit code, status, run id, graph id, versions, the graph digest and every
diagnostic with its code, origin and location. Both were permanently hidden by a
single missing `body.visible` assignment; see §13.

The table's first column shows the variable name (`inoculum_volume`) rather than
the full identifier (`node:N01#inoculum_volume`). The full identifier stays in
the row and in its tooltip, and is what selection, provenance and evidence
lookups use — see §14.

Pressing it opens a panel that shows:

- which model, version and run this was checked against, with the run's graph
  digest and a statement of what that digest does and does not cover;
- what is missing and what it blocks, in the model's own words;
- what was searched, and what the search returned;
- each candidate finding — the extracted value with its unit, the publisher's
  citation, a DOI, a section locator, and the **verbatim quoted passage** it came
  from;
- the conditions it was measured under, and how they differ from the target
  process dimension by dimension (strain, construct, medium, mode, temperature,
  pH, scale, measurement basis), with critical dimensions marked;
- whether the source is **independent** of the target publication;
- a verdict: **incompatible conditions**, **needs checking**, or **compatible but
  not yet validated**;
- what the candidate would *not* settle even if it were adopted;
- any conflicting evidence, left explicitly unresolved;
- a checkable list of the ten validation criteria, showing which passed;
- an action to **propose a separate model or parameter set**.

The catalogue is static curated data, not a search engine. It is produced by
`python -m composition.evidence` and read by the scene through the same verified
GDScript → Python boundary the model run uses.

**For the growth-rate gap the answer is no.** A literature search found two
published kinetic constants, and both are incompatible — one measured on a
different strain in a continuous chemostat, one a single-cell rate measured at
microlitre scale. The panel says the gap is unresolved and points at the only
route that would actually close it: build a separate, explicitly parameterised
model fitted to batch data from this strain.

A third source — same institute, same strain, same vector, same medium — looked
like a perfect match until each condition was bound to the passage it was read
from. Its supporting text turns out to appear **verbatim in the Zieliński paper
itself**. It is the target paper's own content reached through a second paper,
so it cannot corroborate the target paper, and it is flagged as **not
independent**.

That check exists because an earlier version of this workflow recorded the
target process once and then wrote the candidate's conditions as strings
identical to it. Every dimension then "matched", which looked like verification
but was a tautology — both sides were written by the same person. Each condition
now carries the verbatim passage it was transcribed from, in its own source, so
agreement is a claim about two independently checkable passages. See
`composition/composition/evidence/sourcing.py`.

Nothing here merges a value into the model. The model still reports every one of
these quantities as unknown, and `Models/Zielinski` is unmodified.

### Model registry

`python -m composition.registry` reports every model the composition layer can
reach, as machine-readable JSON:

```bash
cd composition && python -m composition.registry        # exit 2 if any issue found
```

Each model is recorded with a stable id and version, its citation and DOI
*where the artefact declares them*, the path to its specification, SHA-256
digests of the files actually read (with an explicit statement of what the
digest covers), its ports, variables and units, and the experimental conditions
the model itself says it needs.

Registration is bookkeeping. It records that an artefact exists, is identified
and can be hashed — **not** that the model is correct, independently supported,
or executable. Every entry carries that disclaimer.

Fields the artefact does not state stay explicitly `unknown`, with the reason
attached. Nothing is inferred: Morris declares no DOI, so the registry records
no DOI rather than deriving one from the author name.

`zielinski2019.rhi_process@1.0.0` registers fully (196 ports, 8 declared
missing models). `morris2011.material_balance@0.1.0` registers with eight
explicit unknowns, because its interface is parameterised per instance rather
than fixed. See §12.7 of `composition/VALIDATION_REPORT.md` for the full list.

The evidence catalogue resolves its model through the registry, so a
compatibility verdict that does not resolve to an exact registered version is
reported as **provisional** rather than definitive.

---

## Running the tests

Four independent suites. Run each from its own package directory — each
`tests/conftest.py` puts the package on `sys.path` for you, so no `PYTHONPATH`
is required.

```bash
# composition layer (includes the research-to-simulation workflow tests)
cd composition && python -m pytest tests          # 790

# Morris 2011 material balance
cd Models/Morris    && python -m pytest tests     # 186

# Zielinski 2019 insulin process
cd Models/Zielinski && python -m pytest tests     # 223

# Ganjave 2022 fed-batch culture
cd Models/Ganjave   && python -m pytest tests     # 331
```

**Total: 1,530 tests.** The three model suites and the pre-existing composition
tests are unchanged; 20 of the composition tests are the research workflow
(exercised against the shipped pecan corpus, offline).

On Windows, pytest's default temporary directory may not be writable. Pinning it
inside the repository avoids five environment-only setup errors:

```bash
cd composition && python -m pytest tests --basetemp .artifacts/pytest-basetemp
```

The Godot half of the research-to-simulation boundary is a separate harness; it
launches the real scene and the real Python workflow:

```bash
godot --headless --path . --script res://composition/tests/godot/research_workflow_scene.gd   # 75 checks
godot --headless --path . --script res://composition/tests/godot/research_workflow_entry.gd   # 15 checks
```

To regenerate the Zieliński reference artifacts (optional; they are not tracked):

```bash
cd Models/Zielinski && python run_model.py
```

---

## Repository layout

```
project.godot            Godot project file; main scene is the graph editor
scenes/
  composition.tscn       graph editor
  replay3d.tscn          3D evidence replay
  prompt_simulation.tscn prompt -> model configuration -> execution
  research_workflow.tscn problem -> literature -> verified model -> execution
scripts/                 all GDScript (UI and the GDScript -> Python boundary)
composition/
  composition/           the composition layer
    evidence/            candidate literature evidence for unresolved quantities
      sourcing.py        conditions bound to a passage in their own source
      conflicts.py       conflict detection and the records examined
      target_source.json Zielinski 2019 passages, with printed-page references
    registry/            deterministic model registry (id, version, digests)
    workflow/            problem parsing, literature, extraction, encoding,
                         model construction and orchestration
      fixtures/pecan/    five real open-access sources, exact passages, problem
    adapters/            morris, zielinski, ganjave and the generated rna model
  examples/              example graphs with pinned exit codes
  tests/                 790 tests
  replay/                the standalone graph the 3D scene executes
  workflow_runs/pecan/   the shipped pecan run: every stage's artifact
Models/
  Morris/                material-balance model + 186 tests
  Zielinski/             insulin process model + 223 tests
  Ganjave/               fed-batch culture model + 331 tests
```

`scripts/runner.gd` is the only place where GDScript talks to the scientific
engine. No scientific calculation happens in GDScript.

---

## Known limitations

**Of the Zieliński model** (see the warning at the top of this file): it is an
evidence replay. The paper reports no kinetics, no oxygen-transfer data, no AU
calibration and no purification model, so the model refuses to invent them.
Not one of its twenty equation outputs can legally feed a Morris control volume:
there is no component identity across the boundary, it is a reactive boundary,
and the quantities differ.

**Of the composition layer:**

* Cycles are rejected outright; there is no iterative solve.
* One value per input port.
* Each model runs in its own interpreter subprocess, because both ship a
  top-level `models` package that cannot coexist in one process.
* An under-determined system returns a representative value for its pivot
  variables, labelled as such.

**Of the research-to-simulation workflow:**

* Discovery reads a **local corpus** (`sources.json` plus the files it names). There
  is no Europe PMC/PubMed/Crossref client, no download queue and no live search;
  a search result would still not be evidence.
* PDF text is read only when `pypdf` happens to be importable. JATS XML and plain
  text use the standard library. A missing PDF reader is reported as an
  acquisition failure, not worked around.
* Passage *selection* is curated: `passages.json` supplies the exact quotes and
  their step mapping. The workflow verifies each quote and number against the
  acquired text, and it enforces that a source's declared role caps the
  specificity a claim may claim, so an analogue paper cannot be relabelled as
  direct target evidence. It does not search arbitrary text for arbitrary claims.
* The generated model is **not** added to the global registry: it exists for one
  research run and is injected into `run_graph` for that run only. No registered
  model or example graph changes.
* The model is an evidence-constrained protocol audit. It publishes counts and
  ratios; it does not predict RNA yield, RIN, purity or degradation, and the
  spruce/pigeonpea protocols remain unvalidated transfer hypotheses.
* The workflow scene requires the desktop build: it invokes the Python runner in
  a subprocess, which the Web export cannot do. The scene says so instead of
  showing an empty result.
* The workflow builds its graph and runs its model in Python. GDScript only passes
  a problem path and renders the returned document.

**Of the editor:**

* Node layout in the graph canvas is not yet usable for a large graph —
  `zoom_to_fit` runs against node sizes that are still being computed, so some
  saved graphs open clipped. This is presentation only and does not affect
  validation, execution or results.
* The **Zieliński replay** button opens a separate, predefined-experiment
  replay scene. It is deliberately not the way to reach a model; every
  registered model is added from the palette instead.
* Saving from the editor rewrites integer literals as floats, which changes the
  reproducibility digest without changing any scientific content.
* The Godot-side UI acceptance checks (77 assertions) and replay behaviour
  regression (18 assertions) were written as temporary harnesses during
  development and are **not currently committed**. Only the Python tests
  ship with this repository.

## Not distributed

The reference PDFs under `papers/` and inside each model package are
publications by other authors and are deliberately excluded, along with all
generated output. Nothing in the application or the test suites reads them: the
citation tests verify against `Models/Zielinski/models/data/paper_pages.json`,
which holds the extracted page text. All 651 tests pass with every PDF absent.