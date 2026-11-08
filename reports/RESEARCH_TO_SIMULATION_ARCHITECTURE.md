# Research-to-simulation workflow: architecture and verified results

Date: 2026-11-02
Status: implemented and verified. Sections 1–7 record the pre-implementation
inspection and are kept as written; sections 8–13 record what was built, what was
found, what was fixed, and what was measured.


## 1. What the repository already has

The brief assumed that problem ingestion, literature acquisition, PDF extraction
and scientific encoding already existed as product infrastructure. They do not.
The inspection below records what actually exists, so the new workflow connects
to it rather than duplicating or replacing it.

### 1.1 Problem / prompt ingestion

| File | What it does | Reusable for the new workflow? |
|---|---|---|
| `composition/composition/prompt.py` | A deterministic, local interpreter for the **Zielinski insulin process only**. It maps a sentence to real Zielinski ports, asks for clarification, and never invents a value or generates Python. | The *pattern* (local rules, explicit clarification, no LLM, no defaults) is reusable. The parser is not general: it recognises one process and one model. |
| `composition/tests/test_prompt_simulation.py` | Proves the prompt layer maps only to real ports and refuses out-of-range requests. | Reuse the test patterns. |
| `scripts/prompt_simulation.gd`, `scenes/prompt_simulation.tscn` | The existing staged UI: input → interpretation → validation → execution → result. | Reuse as the UI pattern. It is Zielinski-specific. |

There is **no** general `problem_spec` schema, no text-to-problem extractor and
no JSON problem ingestion.

### 1.2 Literature discovery and acquisition

| File | What it does | Gap |
|---|---|---|
| `composition/composition/evidence/papers.py` | An index of paper folders already under `Models/`; each entry says whether a model encodes it and, if not, why. It is an audit index, not a search client. | No search, no download, no acquisition state. |
| `composition/composition/evidence/catalogue.py` | Hand-curated candidate findings with verbatim quotes and source ids, scored against Zielinski ports. | Curated for the insulin process; not a general encoder. |
| `composition/composition/evidence/sourcing.py` | The correct provenance pattern: a condition carries the source's wording, a verbatim quote and a source id; identical strings are not treated as independent verification. | Reuse the *principle*; the dimensions are fermentation-specific. |
| `composition/composition/evidence/conflicts.py`, `standalone.py` | Conflict vocabulary and standalone-paper model records. | Not a literature client. |

There is **no** Europe PMC / PubMed / Crossref client, no download queue, no
acquisition manifest and no document store in the product. The scripts in
`.test-tmp/` (`extract_papers.py`, `gen_pages.py`, `to_txt.py`) are ad-hoc
developer helpers, not product infrastructure, and they are not imported by the
application.

### 1.3 PDF / full-text extraction

There is no in-product extractor. `pypdf` 6.20.1 and PyMuPDF 1.28.2 happen to be
installed on this machine, but `README.md` promises **no third-party runtime
dependencies**. The new workflow therefore treats PDF extraction as optional:
JATS XML and plain text are handled with the standard library; a PDF is read
through `pypdf` only when it is importable, and the absence of `pypdf` is
reported as an explicit acquisition failure rather than papered over.

### 1.4 Scientific encoding

`composition/composition/evidence/catalogue.py` and `sourcing.py` establish the
right discipline: a claim is tied to a source id and a verbatim passage, and two
independently worded passages are not assumed equivalent. They encode the
Zielinski fermentation, not plant RNA extraction.

There is no general claim schema, no quote verification step, no separation of
target-organism evidence from analogous-species evidence, and no explicit
`hypothesis` / `unresolved` claim states.

### 1.5 Model construction and composition

| File | What it does | Reuse |
|---|---|---|
| `composition/composition/contracts.py` | Authoritative graph, port, value, provenance, diagnostic and result schemas. Six value states, provenance chains, fail-closed semantics. | **Reuse unchanged.** |
| `composition/composition/engine.py` | Validates ports, units, compatibility, ordering and executes adapters. | **Reuse unchanged.** |
| `composition/composition/adapters/` | `morris`, `zielinski`, `ganjave` adapters plus the subprocess `JsonWorker` boundary. Registration is a row in `REGISTRATIONS`. | **Reuse the adapter/worker pattern.** Add one adapter. |
| `composition/composition/compatibility.py`, `cross_model.py` | Compatibility classifications and cross-model connection rules. | **Reuse unchanged.** The new graph has one instance and no cross-model edge. |
| `composition/composition/registry/` | Tracked-field provenance (`DECLARED` / `DERIVED` / `UNKNOWN`) and deterministic package digests. | **Reuse the vocabulary.** The workflow's model spec uses the same three-state discipline. |
| `composition/composition/runner.py` | `run_graph`, `run_prompt`, introspection CLIs, exit codes 0/1/2/3/4. | **Reuse `run_graph`.** Add one workflow command. |
| `composition/composition/quantities.py` | Quantity/unit registry. `dimensionless` with unit `1` is available for counts and ratios. | **Reuse unchanged.** |

### 1.6 Python execution boundary

`scripts/runner.gd` is the only GDScript → Python boundary. It resolves
`res://` / `user://`, exports `PYTHONPATH`, invokes `python -m composition.runner`,
reads the result file, and treats a missing or malformed document as failure.
`OS.execute` is synchronous on desktop. The new workflow must go through this
file, not around it.

### 1.7 Godot UI

`scenes/workshop.tscn` is the main scene. `scripts/workshop.gd` owns the header
and navigation; `_on_prompt_pressed` opens `scenes/prompt_simulation.tscn`.
`scripts/prompt_simulation.gd` builds its UI programmatically and follows the
staged pattern. The new workflow gets its own scene and one header button; the
existing scenes are not redesigned.

## 2. The central gap

The task calls for:

1. problem extraction,
2. literature discovery and acquisition,
3. full-text/PDF extraction,
4. scientific encoding,
5. model construction and composition,
6. Python execution,
7. Godot results.

Steps 1–4 do not exist as product infrastructure. Steps 5–7 do, and are
substantial and tested. The implementation therefore adds a **workflow layer**
that supplies 1–4 and hands a normal composition graph to the existing runner
for 5–7. It does not modify the contracts, engine, compatibility rules or
existing models.

This is a gap, not a blocker: the existing composition boundary is sufficient to
execute a newly constructed model without changing it.

## 3. Proposed data flow (and the honesty boundary)

```
problem.json / problem text
        │  deterministic local parser; unknown fields stay unknown
        ▼
problem_spec.json
        │  local corpus provider (offline fixtures or a user-supplied corpus)
        ▼
literature_manifest.json  ──►  source_texts/<source_id>.txt
        │  JATS XML / plain text (stdlib); PDF via optional pypdf
        ▼
research_encoded.json
        │  every claim quotes its source verbatim; quote is located and verified
        │  claim specificity: target organism | analogous species | method review
        ▼
model_spec.json
        │  protocol steps; reported parameters only where the quote states them
        │  target-specific gaps and analogue hypotheses kept separate
        ▼
composition_graph.json
        │  one instance of the new evidence-audit adapter; no cross-model edge
        ▼
python -m composition.runner --graph ... --result ...
        │  existing contract validation, execution and provenance
        ▼
simulation_result.json  ──►  Godot research workflow scene
```

The model is an **evidence-constrained protocol audit**, not a kinetic yield or
degradation simulator. It counts what the literature establishes, what is
transferred by analogy, and what remains unknown. It does not invent a pecan RNA
yield, degradation rate, RIN, or parameter that no source states.

## 4. Files to add or modify

### New package: `composition/composition/workflow/`

| File | Purpose |
|---|---|
| `__init__.py` | Public entry points. |
| `schema.py` | Dataclasses for problem, source, claim, protocol step, model spec and run result. Three-state values (`reported` / `derived` / `unknown`). |
| `problem.py` | Deterministic problem parser for the pecan case; explicit unknowns. |
| `literature.py` | Local corpus discovery/acquisition, source hashing and metadata. No live API in tests. |
| `extract.py` | JATS XML and text extraction with section locators; optional `pypdf`. |
| `encoding.py` | Verbatim quote verification, claim construction, target-vs-analogue separation. |
| `model_builder.py` | Protocol steps, unknowns, analogue hypotheses and model spec. |
| `execute.py` | Orchestrates the pipeline, writes artifacts, builds the graph, calls `run_graph`, writes the combined result. |
| `fixtures/pecan/` | Real open-access sources, metadata, exact passages and problem statement. |

### New model adapter

| File | Purpose |
|---|---|
| `composition/composition/adapters/rna.py` | Adapter for the evidence-audit model. |
| `composition/composition/_workers/rna_worker.py` | Subprocess evaluator; reads the model spec and returns counts/ratios. |
| `composition/workflow/model_package/pyproject.toml` | Contract-visible package marker used by `adapter_for`. |
| `composition/composition/adapters/__init__.py` | Add one registration row. |

### Modified

| File | Change |
|---|---|
| `composition/composition/runner.py` | Add `--run-workflow` and `--workflow-out`; reuse `run_graph`. |
| `scripts/runner.gd` | Add `run_research_workflow(...)`; no other boundary change. |
| `scripts/workshop.gd` | Add one header button and navigation callback. |
| `scenes/research_workflow.tscn` + `scripts/research_workflow.gd` | New results scene. |
| `README.md` | Document the workflow and its limits. |

### Explicitly not changed

`contracts.py`, `engine.py`, `compatibility.py`, `cross_model.py`,
`quantities.py`, the registry schema, the three existing model packages, and the
existing composition/replay/prompt scenes.

## 5. Baseline tests (before changes)

All suites were green on the working tree:

| Suite | Collected | Result |
|---|---|---|
| `composition/tests` | 770 | passed |
| `Models/Zielinski/tests` | 223 | passed |
| `Models/Morris/tests` | 186 | passed |
| `Models/Ganjave/tests` | 331 | passed |

Total: 1,510 passing tests. The working tree already contained uncommitted
changes before this task; they were not reverted or overwritten.

## 6. Pecan evidence plan

The bundled corpus is real, open-access full text (JATS XML) from Europe PMC:

| Source | DOI | Role |
|---|---|---|
| `PMC11430883` | `10.3390/foods13182934` | **Target organism** — pecan (*Carya illinoinensis*) embryo total RNA by TRIzol kit, DNase I, gel/NanoDrop. |
| `PMC10857598` | `10.3390/plants13030389` | **Analogue** — modified CTAB protocol for Norway spruce, with exact buffer, incubation, chloroform, LiCl, wash and DNase parameters. |
| `PMC10707625` | `10.1371/journal.pone.0291949` | **Analogue** — modified CTAB and Trizol protocols for polyphenol/polysaccharide-rich pigeonpea. |
| `PMC11069240` | `10.1186/s13007-024-01198-z` | **Method review** — modified CTAB for secondary-metabolite-rich plants. |
| `PMC10416385` | `10.1186/s13007-023-01063-5` | **Method review** — CTAB-TRIzol for 39 difficult plant species. |

The pecan paper names the kit and says the manufacturer's protocol was followed;
it does **not** print the lysis volumes, incubation times, centrifugation speeds,
elution volume, yield or RIN. The workflow must report those as unknown. The
spruce and pigeonpea protocols are exact but are different species, so they enter
the model as **analogue hypotheses**, never as pecan measurements.

## 7. Acceptance criteria

1. The pecan problem parses without inventing missing fields.
2. Every encoded claim carries a source id and a verbatim quote that is found in
   the acquired text.
3. Target-organism evidence and analogue-species evidence are visually and
   structurally distinct.
4. No pecan yield, degradation rate, RIN or protocol parameter is invented.
5. A real composition graph runs through the existing `run_graph`, with exit code
   0 and deterministic output.
6. The run writes inspectable artifacts for every stage.
7. The Godot scene invokes the workflow through `scripts/runner.gd` only.
8. The four existing suites remain green.

## 8. Implementation as built

The workflow is implemented; the sections above were written before it ran and
are kept because they record what was inspected. This section records what now
exists and what was verified.

### 8.1 Python

| File | What it does |
|---|---|
| `composition/composition/workflow/problem.py` | Parses a problem document into a `ProblemSpec`. Fields it cannot find stay `unknown`; a missing organism or molecule blocks the run with exit code 3. |
| `composition/composition/workflow/literature.py` | Local corpus discovery (role, relevance terms, score, reasons) and acquisition (read bytes, SHA-256, extract text, record status). No network client. |
| `composition/composition/workflow/extract.py` | JATS XML and plain text with section locators, standard library only; PDF only when `pypdf` happens to be importable, otherwise an explicit acquisition failure. |
| `composition/composition/workflow/encoding.py` | Verbatim quote verification (exact substring after whitespace normalisation, with character offsets), numeric verification ("every number must appear in its own quote"), claim kinds, specificity, and the **source-role ceiling**. |
| `composition/composition/workflow/model_builder.py` | Protocol steps, reported/unknown parameters, analogue hypotheses, readiness flags, and the one-instance graph. |
| `composition/composition/workflow/execute.py` | Orchestrates stages 1–5, writes one artifact per stage, injects the generated-model adapter into `run_graph`. |
| `composition/composition/adapters/rna.py` | Adapter for the generated model: manifest and `ModelValue` translation only. |
| `composition/composition/_workers/rna_worker.py` | Subprocess evaluator. Counts claims/steps/unknowns from the model spec and returns them; it contains no RNA science, no yield equation and no degradation term. |
| `composition/composition/adapters/__init__.py` | One registration row for the adapter *class*, not for the generated model id. |
| `composition/composition/runner.py` | `--run-workflow` / `--workflow-out`; `run_graph(..., adapters=…)`. |
| `composition/composition/workflow/fixtures/pecan/` | Five real open-access JATS sources, their metadata, 25 exact passages, and the problem statement. |

`composition/workflow_runs/pecan/` holds a fresh run: `problem_spec.json`,
`literature_manifest.json`, `research_encoded.json`, `model_spec.json`,
`composition_graph.json`, `simulation_result.json`, `workflow_result.json` and
`source_texts/`.

### 8.2 Godot

| File | What it does |
|---|---|
| `scenes/research_workflow.tscn` + `scripts/research_workflow.gd` | The results screen. Builds no graph, runs no model, computes no claim: it calls one bridge method and renders the document that run wrote, plus the literature manifest artifact the payload names. |
| `scripts/runner.gd` → `run_research_workflow(problem_path, out_dir, result_path)` | The only new boundary call: `python -m composition.runner --run-workflow … --workflow-out … --result …`. A Web build reports the workflow as unavailable rather than pretending it ran. |
| `scripts/workshop.gd` → **Research workflow** header button | Opens the new scene. Nothing else in the workshop changed. |

The screen shows, in this order: problem specification → research acquisition
(status, selected/not selected with reasons) → source documents (role, DOI,
extraction, SHA-256, text path) → evidence verification (quotes and numbers
verified, failures, role-ceiling enforcement) → direct versus analogous evidence
(counts plus every step with its `evidence_status` and hypothesis flag) → model
readiness → unknown parameters → assumptions and hypotheses → execution status →
simulation outputs → warnings and diagnostics → artifact locations.


## 9. Scientific validation (what was actually checked)

Tests passing is not scientific validation, so the artifacts were checked
independently of the suite:

| Check | Method | Result |
|---|---|---|
| Quotes are real | For every claim, slice the acquired text at its recorded `locator.start`/`locator.end` and compare with the claim's `quote` | 25 of 25 exact matches |
| Numbers are in their quote | Re-read each parameter's `value_text` and confirm it occurs in the claim's quote | 66 of 66 |
| Direct evidence comes from the pecan paper | Every step whose `evidence_status` starts with `direct_target` cites `pecan_miRNome` only, has `hypothesis = false`, and no analogue or review source appears | 6 direct steps, 6 direct claims |
| Analogue evidence is labelled | Every `analogous_*` step has `hypothesis = true` and appears in `model.hypotheses` with "has not been validated on the target organism" | 11 analogue steps, 17 analogue claims |
| Missing quantities stay missing | `readiness.quantitative_yield_available_for_target = false`, `protocol_complete_for_target = false`; 18 parameter-level unknowns, 45 step-level unknowns, 4 explicit assumptions | no yield, RIN or degradation output exists |
| The adapter computes from evidence | A perturbed model spec (5 claims removed, one readiness flag flipped) changed the published counts accordingly | outputs track the spec; no fixed constants |
| Analogue cannot become direct | A spruce passage relabelled `target_organism` was **accepted** by the first implementation; a source-role ceiling was added and the case now fails the run | gap found and closed (see §10) |

What is *not* validated: no pecan RNA yield, RIN, purity or degradation value is
predicted or measured by this model, and the spruce/pigeonpea protocols remain
unvalidated transfer hypotheses. The model audits evidence coverage; it is not a
kinetic or yield model.

## 10. Defects found and fixed during verification

1. **The worker could not emit its own result on Windows.** `rna_worker.py`
   wrote `json.dumps(..., ensure_ascii=False)` to stdout. The real paper text
   contains `µ`, so the child raised `UnicodeEncodeError` under the cp1252
   console encoding and the workflow exited 2 with "the model worker produced no
   output at all". The worker now emits ASCII-escaped JSON, matching the
   convention `JsonWorker` already uses on the way in (it sends
   `json.dumps(request)` with default escaping). Three tests failed before this
   fix; none after.
   The previously committed `workflow_runs/pecan` artifacts had been produced
   through that broken path: strings read `20 Î¼L` instead of `20 µL`. The
   directory was regenerated from the fixture after the fix.
2. **Analogue evidence could silently become direct evidence.** `specificity`
   was taken verbatim from `passages.json` and never compared with the role the
   corpus declares for that source. A Norway-spruce passage relabelled
   `target_organism` was accepted as a direct pecan claim (demonstrated before
   the fix). `encoding.encode(..., source_roles=…)` now enforces a ceiling — a
   claim may be *weaker* than its source's role but never stronger — and a
   target-organism claim must name the requested organism. `run_workflow`
   always supplies the roles, and `research_encoded.json` records
   `verification.source_role_check = "enforced"`. Three regression tests were
   added.

## 11. Godot verification

Godot 4.7.2 is installed, so the integration was executed, not only inspected:

| Harness | What it proves |
|---|---|
| `composition/tests/godot/research_workflow_scene.gd` | Loads the real scene, presses **Run workflow** for the shipped pecan problem, and checks the document the run wrote: exit code 0, every artifact file present, 25/25 quotes and 66/66 numbers, the 6 / 17 claim split, 18 unresolved parameters, the six direct steps citing only `pecan_miRNome`, no `predicted_yield`/`RIN`/`degradation` port, and that the screen displays the target organism, both evidence classes, the hypothesis labels, the outputs, an artifact path, and real `µL` text that survived the Python → Godot boundary. |
| `composition/tests/godot/research_workflow_entry.gd` | Instantiates the real `workshop.gd`, builds its header, finds the **Research workflow** button (label, tooltip, enabled, exactly one connection, handler present), then opens `scenes/research_workflow.tscn` as the current scene and checks that scene's run button, status label, default problem document and runner method. The workshop scene as a whole is driven by `workshop_graph_run.gd` in the composition suite, so this check does not duplicate registry introspection. |


## 12. Measured results

Every number below comes from a run on this machine (Python 3.14.7, pytest 9.1.1,
Godot 4.7.2-stable, Windows).

| Suite | Command | Result |
|---|---|---|
| Composition | `cd composition && python -m pytest tests --basetemp .artifacts/pytest-basetemp` | **790 passed, 0 failed, 0 errors, 0 skipped** (501 s) |
| — research workflow file | `python -m pytest tests/test_research_workflow.py` | **20 passed** |
| Morris 2011 | `cd Models/Morris && python -m pytest tests` | **186 passed** (1.3 s) |
| Zielinski 2019 | `cd Models/Zielinski && python -m pytest tests` | **223 passed** (6.0 s) |
| Ganjave 2022 | `cd Models/Ganjave && python -m pytest tests` | **331 passed** (91.5 s) |
| **Python total** | | **1,530 tests, all passing** |
| Godot scene | `godot --headless --path . --script res://composition/tests/godot/research_workflow_scene.gd` | **75 checks, 0 failures** |
| Godot entry point | `… --script res://composition/tests/godot/research_workflow_entry.gd` | **15 checks, 0 failures** |

Notes on what those counts mean:

* The composition suite ran the existing Godot acceptance harnesses
  (`contract_boundary.gd`, `palette_graph_run.gd`, `workshop_graph_run.gd`)
  because Godot was found on this machine. The workshop harness drives the
  Ganjave simulation through the real runner, so the **existing** simulation
  workflow is still exercised after the workshop header change.
* Without a pinned `--basetemp`, five tests error at setup with
  `PermissionError: [WinError 5] Access is denied:
  C:\Users\…\AppData\Local\Temp\pytest-of-…`. That is the host's temporary
  directory, not the implementation: the same five pass with the basetemp pinned
  inside the repository.
* The pecan run is reproducible: `test_workflow_is_deterministic` runs the
  workflow twice into different directories and compares the problem, encoded,
  model, graph, execution and diagnostics sections; the artifact that ships under
  `composition/workflow_runs/pecan/` was regenerated this way from
  `composition/composition/workflow/fixtures/pecan/`.

### Artifacts of the shipped run

```
composition/workflow_runs/pecan/
  problem_spec.json        the parsed problem; fields it could not find are unknown
  literature_manifest.json discovery reasons, selection, acquisition hashes
  source_texts/*.txt       the five extracted documents the claims point into
  research_encoded.json    25 verified claims, 18 steps, verification block
  model_spec.json          model kind, readiness, unknowns, hypotheses, assumptions
  composition_graph.json   one instance, no connections, spec carried in parameters
  simulation_result.json   the composition engine's own result document
  workflow_result.json     the combined document the Godot scene renders
```

## 13. What is demonstrated, and what is not

**Demonstrated end to end.** A problem document goes in; the workflow discovers
and acquires five real papers from a local corpus, verifies 25 verbatim quotes
and 66 numbers, builds an evidence-constrained model, executes it through the
existing composition engine, and writes artifacts; the Godot scene triggers that
run through `scripts/runner.gd` and displays the actual result. Reproducible from
the fixtures with one command.

**Not demonstrated, and not claimed.**

1. **Live literature search or download.** Discovery is a local corpus provider.
   Adding a Europe PMC client would be a new feature, not a fix.
2. **Automatic claim extraction from arbitrary full text.** Passages are curated
   in `passages.json`; the workflow verifies them rather than mining them.
3. **A predictive pecan RNA model.** No yield, RIN, purity or degradation value
   exists in the sources, so none is produced. This is the intended result.
4. **Cross-species validation.** The spruce and pigeonpea protocols are
   hypotheses; nothing was run in a lab.
5. **Web export.** The workflow scene needs the desktop build because it runs
   Python in a subprocess.

No remaining blocker prevents the workflow from being reproduced or inspected.

