# Scientific Gap Discovery — implementation report

**Feature.** In the Zielinski insulin replay, section **8 — Scientific Gap
Discovery** answers: *what scientific models and experimental evidence are still
missing, what does the project's library already contribute, and what should be
looked for next?*

The analysis is local and read-only. It uses the existing Python execution
boundary and adds no cloud model, external API or paid service.

---

## 1. What is generated

`python -m composition.gaps` produces a deterministic JSON document with a
SHA-256 digest. The example for the current repository is
`composition/examples/zielinski_gap_discovery.json`.

Current result:

| measure | value |
|---|---:|
| gaps identified | 12 |
| fully resolved by the existing library | 0 |
| partly informed by an existing paper | 2 |
| still unresolved | 12 |
| potentially composition-enabling | 4 |
| assessed papers | 7 |

The twelve gaps cover all seven requested classes:

| class | gaps |
|---|---|
| model parameters | missing growth/substrate-uptake parameters; missing dissolution volume |
| experimental measurements | AU calibration; A280 values and path length |
| biological context | no target-context characterisation of *E. coli* 20 IBA 1 / pIBAINS |
| process conditions | GMS medium composition; induction time; homogenizer pressure/passes |
| mathematical relationships | oxygen transfer/uptake; renaturation kinetics |
| independent validation | one published batch, no independent validation record |
| composition blockers | no shared quantity/component mapping |

The two gaps partly informed by the library are:

* **growth/substrate uptake** — Ganjave, Baez, Lin and Nanchen supply related
  growth, feed or maintenance relationships, but in different strain, medium,
  mode or temperature contexts;
* **oxygen transfer/uptake** — Baez reports aeration/agitation and a
  dissolved-oxygen step, and Lin reports oxygen-uptake capacity, but neither
  supplies a target-context `kLa`, OUR/OTR relationship or oxygen balance.

No assessment is upgraded. Every classification is copied from
`composition.compatibility`.

---

## 2. Where the facts come from

| source | used for |
|---|---|
| `Models/Zielinski/out/graph.json` | declared `missing_parameters`, their reasons and blocked targets; node/stream counts; assumptions |
| `Models/Zielinski/MODEL_REPORT.md` | digitization uncertainty, no-kinetics scope statement |
| `Models/Zielinski/out/run_summary.md` | source discrepancies (induction order, refolding yields, failed cross-checks) |
| `composition/composition/compatibility.py` | the seven assessments, classifications, blockers, evidence checks, permitted connections |
| `composition/composition/evidence/papers.py` | corpus records and determinations |
| `composition/composition/evidence/catalogue.py` | the project's existing literature investigation (reused; not repeated) |
| `Models/*/manifest.json`, `MODEL_REPORT.md` | paper contributions and their stated limits |

The module never writes under `Models/`, never edits an equation and never
changes a replay value. A test hashes the watched files before and after two
analyses and asserts they are unchanged.

---

## 3. Godot integration

Open the Zielinski replay (`scenes/replay3d.tscn`, reached from the
**Zielinski replay** button in the main window), scroll to section **8 —
Scientific Gap Discovery**, then press **Analyse simulation**.

The panel shows:

* **A. Simulation analysis** — target, gap count, fully addressed, partly
  informed, still unresolved, composition-enabling, papers assessed;
* **B. Knowledge gaps** — an expandable item per gap with explanation, why it
  matters, relevant variables, existing evidence and missing information;
* **C. Existing literature matches** — citation, relevance, contribution,
  what remains missing and the unchanged compatibility classification;
* **D. Research recommendation** — needed information, why, what a suitable
  paper must report, search terms and what ScaleUp could do next;
* **E. Refresh analysis** — re-runs the same local analysis.

**Copy search terms** writes the selected gap's terms to the system clipboard.

---

## 4. Commands run

```bash
# analysis and its self-check
PYTHONPATH=composition python -m composition.gaps --check
# PASS -- 12 gaps, 0 fully addressed, 2 partially informed,
#         12 unresolved, 4 composition-enabling

# regenerate the example payload
PYTHONPATH=composition python -m composition.gaps \
  --write composition/examples/zielinski_gap_discovery.json --check

# focused tests
PYTHONPATH=composition python -m pytest \
  composition/tests/test_scientific_gap_discovery.py -q
# 10 passed

# existing compatibility suite (unchanged)
PYTHONPATH=composition python -m pytest \
  composition/tests/test_compatibility.py -q
# 35 passed

# the Zielinski model itself (unchanged)
python -m pytest Models/Zielinski/tests -q
# 223 passed

# Godot panel payload + real Python bridge
godot --headless --path . \
  --script res://composition/tests/godot/test_scientific_gap_panel.gd
# 21 checks passed, 0 failures

# Godot replay-scene integration
godot --headless --path . \
  --script res://composition/tests/godot/test_scientific_gap_scene.gd
# 7 checks passed, 0 failures
```

The full `test_acceptance.py` suite was not completed inside the 30-second
command limit; the focused suites above cover the compatibility records and the
new feature. The existing replay-scene harness also exceeds the command limit in
this environment, so the new scene harness checks reachability without waiting
for the asynchronous model run.

No screenshot was produced: the available Godot run is headless, so it has no
rendered viewport. The headless harness verifies the same panel and payload that
the scene builds.

---

## 5. Limits

* The literature search is **recorded, not extended**. The module reuses
  `composition.evidence.catalogue` and gives labelled search queries for
  external research. It does not browse, download papers or call an API.
* Every gap is unresolved by the current seven-paper library. That is a finding,
  not a UI omission: no assessed paper supplies target-context evidence.
* A paper that is merely relevant is listed as `relevant_context` or
  `partially_addresses`; it is never moved into `evidence_compatible`.
