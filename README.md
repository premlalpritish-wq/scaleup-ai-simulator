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

Press **Run** to validate and execute the loaded graph. Press **Validate only**
to produce an execution plan without running anything.

Choose a graph from the **Load example** menu. Each shipped example has a
documented exit code; rejected examples are meant to fail, and their failure
messages are the demonstration.

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

The default view is organised in five sections:

1. **Reactor and operating conditions** — the vessel, and the stated operating
   conditions.
2. **Culture growth over time** — culture time, the density reading, and the
   published growth curve with its declared uncertainty.
3. **Purification results** — the instrument signal after each purification
   step.
4. **What this model cannot tell us** — the unresolved quantities, each with the
   model's own reason.
5. **Detailed evidence and technical diagnostics** *(collapsed)* — every one of
   the 196 published values with its exact field names, its method, its source
   and its full provenance chain.

Every displayed value carries a plain-language provenance label — *stated in the
source*, *read from a published figure*, *calculated from the available data*,
or *not established by the available evidence*.

---

## Running the tests

Three independent suites. Run each from its own package directory — each
`tests/conftest.py` puts the package on `sys.path` for you, so no `PYTHONPATH`
is required.

```bash
# composition layer
cd composition && python -m pytest tests          # 128

# Morris 2011 material balance
cd Models/Morris    && python -m pytest tests     # 186

# Zielinski 2019 insulin process
cd Models/Zielinski && python -m pytest tests     # 223
```

**Total: 537 tests.**

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
scripts/                 all GDScript (UI and the GDScript -> Python boundary)
composition/
  composition/           the composition layer
  examples/              six example graphs with pinned exit codes
  tests/                 128 tests
  replay/                the standalone graph the 3D scene executes
Models/
  Morris/                material-balance model + 186 tests
  Zielinski/             insulin process model + 223 tests
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

**Of the editor:**

* Node layout in the graph canvas is not yet usable for a large graph —
  `zoom_to_fit` runs against node sizes that are still being computed, so some
  saved graphs open clipped. This is presentation only and does not affect
  validation, execution or results.
* The "Add model" palette is a placeholder; load an example graph instead.
* Saving from the editor rewrites integer literals as floats, which changes the
  reproducibility digest without changing any scientific content.
* The Godot-side UI acceptance checks (77 assertions) and replay behaviour
  regression (18 assertions) were written as temporary harnesses during
  development and are **not currently committed**. Only the 537 Python tests
  ship with this repository.

## Not distributed

The reference PDFs under `papers/` and inside each model package are
publications by other authors and are deliberately excluded, along with all
generated output. Nothing in the application or the test suites reads them: the
citation tests verify against `Models/Zielinski/models/data/paper_pages.json`,
which holds the extracted page text. All 537 tests pass with every PDF absent.