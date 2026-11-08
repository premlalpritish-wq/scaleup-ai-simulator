# ScaleUp Research Explorer — pecan RNA MVP

Date: 2026-11-02
Status: implemented and verified on this machine. The browser page is served by
the Python service itself; the scientific work is the existing research workflow.

## 1. What this is

A browser page (`/research/`) plus a small HTTP surface that let a plant-science
researcher, with no installation, read the completed pecan RNA case and run the
existing workflow on a protocol they describe.

It is a **thin user-facing layer**:

| Layer | Where | What it does |
|---|---|---|
| Page | `web/research/index.html`, `app.js`, `style.css`, `config.js` | Renders documents it receives. No scientific logic, no mock data, no analytics. |
| Adapter | `api/research.py` | Calls `composition.workflow.execute.run_workflow` (the same entry point as the CLI and the Godot scene), re-verifies every quote, and projects the run's artifacts into a browser shape. |
| HTTP | `api/app.py` | Adds `/api/research/*` and serves `/research/*` from an allow-list. The graph endpoints are untouched. |
| Engine | `composition/composition/workflow/*` | Unchanged. Problem parsing, local literature acquisition, quote verification, model construction and execution. |

## 2. Interface

| Section | Contents | Source of the data |
|---|---|---|
| 1. Case overview | Problem statement, organism/material/target molecule with their `reported`/`unknown` state, evidence counts, capabilities, limitations, corpus table | `GET /api/research/case` (shipped run) |
| 2. Protocol input | Organism, material/tissue, target molecule, downstream, current problem (required), extraction method, constraints, additional details, observations. Every field except the problem statement may be empty. | Posted to `POST /api/research/analysis` |
| 3. Evidence explorer | One card per claim: class filter (all / direct / analogue / method review), claim text, verbatim quote, source title, DOI, PMCID, section, step, offsets, reported value, uncertainty, hypothesis badge | `claims` in the case document |
| 4. Research gaps | Every unresolved parameter and open question, with why it cannot be closed from this corpus, the evidence that supports its step, and any analogue value (labelled a hypothesis) | `gaps` in the case document |
| 5. Run analysis | Refusal notice, or the computed outputs table plus an evidence summary, hypotheses, the submitted input split into "used" and "recorded, not used as evidence", diagnostics and artifact links | `POST /api/research/analysis` |
| 6. Export & feedback | Markdown report download, browser print/save-as-PDF, feedback form, privacy notice | `…/report.md`, `POST /api/research/feedback` |

### What the workflow consumes, and what it only records

`problem`, `organism`, `tissue`, `molecule`, `downstream` and `constraints`
become the problem specification. `extraction_method`, `details` and
`observations` are written to the run's problem document and to the report, and
the response says `recorded_not_used_as_evidence`. They do not change the model,
because the workflow verifies curated passages rather than mining arbitrary text.
The page states this next to the fields and in section 5; it is not hidden.

## 3. Scientific honesty rules (and where they are enforced)

| Rule | Enforcement |
|---|---|
| No predictive yield, RIN, purity or degradation | The model never had such outputs. `api/tests/test_research_api.py` asserts no `predicted_yield`, `degradation_rate`, `yield_ug` or `rin` port exists and that `quantitative_yield_available_for_target` is `0`. |
| Analogous evidence is never shown as direct | The encoder's source-role ceiling caps a claim's specificity at its source's declared role; a claim about another species is a `hypothesis`. The case endpoint asserts that every `direct` claim comes from `pecan_miRNome` with role `target_organism`, and the UI colours and labels the classes differently. |
| No fabricated values or recommendations | Unknown parameters stay `unknown` with the encoder's own reason. The gap text explains *why it cannot be closed*; it contains no dose, volume or "you should". A test rejects the word "should" in every gap. |
| No live literature search | Stated in the limitations that the page renders. Discovery reads the bundled five-paper corpus. |
| Nothing is served unverified | Before the case is served, every quote is sliced out of the acquired text at its recorded offsets and compared. A mismatch returns HTTP 503 `case_unverified` and no evidence. A test tampers with a copy of the artifacts to prove it. |
| Refusals are not answers | A problem outside the corpus, or one with no organism/molecule, returns HTTP 422 with `applicability.applicable = false`, the workflow's own reason and diagnostics, and `result: null`. No pecan result is substituted. |
| No API keys, no third-party uploads | The service needs no key. The page loads no third-party script. The privacy notice states that a submitted problem goes to this deployment's Python service and nowhere else. |

## 4. HTTP API

| Method and path | Response |
|---|---|
| `GET /` | 302 to `/research/` |
| `GET /research/` | The page (`text/html`) |
| `GET /api/research/case` | Case document: problem, sources, 25 claims with provenance, 18 steps, 44 gaps, readiness, verification block including the independent quote re-check |
| `GET /api/research/case/report.md` | Markdown report of the case |
| `GET /api/research/case/artifacts/{name}` | Allow-listed artifact JSON (`problem_spec`, `literature_manifest`, `research_encoded`, `model_spec`, `composition_graph`, `simulation_result`, `workflow_result`) |
| `POST /api/research/analysis` | `{status, execution_status, analysis_id, applicability, input, problem, diagnostics, verification, result}`. 200 when the workflow executed (exit 0); 422 when it refused or failed, with `result: null` |
| `GET /api/research/runs/{id}` | The stored analysis document |
| `GET /api/research/runs/{id}/report.md` | Markdown report of that analysis |
| `GET /api/research/runs/{id}/artifacts/{name}` | Allow-listed artifact of that run |
| `POST /api/research/feedback` | `{received, persisted, storage, note}` — it says whether the message was stored |

Limits reuse the existing service bounds: 256 KiB JSON body, 4,000 characters per
text field, one shared execution slot, 30 requests per IP per minute, five
retained analyses in memory (evicted oldest-first, with their temporary
directories removed). Analyses disappear when the service restarts.


## 5. Running it locally

```bash
python -m api.app                 # http://localhost:8080/research/  (HOST/PORT honoured)
```

The service serves the page and the API from one origin, so there is nothing to
configure. For the composition demo, `web/` is still served separately; this page
only needs `web/research/`, which the service reads directly from the repository.

## 6. Deployment

### A. One Python service (recommended, and what this MVP is tested against)

```bash
docker build -f api/Dockerfile -t scaleup-research .
docker run -p 8080:8080 -e PORT=8080 \
  -e SCALEUP_CORS_ORIGIN=https://your-page-origin.example \
  -e SCALEUP_MAX_CONCURRENT_RUNS=1 \
  -e SCALEUP_TRUST_FORWARDED_CLIENT_IP=true \
  -e SCALEUP_FEEDBACK_DIR=/data/feedback \
  -v "$PWD/data-feedback:/data/feedback" \
  scaleup-research
```

The image copies `api/`, `composition/composition` (including the pecan fixtures),
`composition/workflow_runs` (the shipped case) and `web/research`. Open
`https://<host>/research/`.

Any Python-capable host works: the process is `python -m api.app` with only the
standard library, listening on `PORT` (default 8080). On a platform that injects
`PORT`, set `HOST=0.0.0.0` if the platform does not (the Dockerfile already does).

### B. Static page + separate Python API

If the page is published from a static host (for example GitHub Pages), set the
API origin before `app.js`:

```bash
# in the static build
printf 'window.SCALEUP_RESEARCH_API_BASE = "%s";\n' "$API_ORIGIN" > web/research/config.js
```

and set `SCALEUP_CORS_ORIGIN` on the API to the page's exact origin. An HTTPS
page refuses to call an HTTP API. With no API configured the page loads and says
the service is unreachable — it never shows sample results.

`render.yaml` remains the paid-service reference; the API service now also serves
`/research/`, so a separate static site is not required for the explorer.

## 7. Verification

```
python -m pytest api/tests -q
# 28 passed   (16 adapter/staging tests + 12 HTTP/static boundary tests)

python -m pytest composition/tests/test_research_workflow.py -q
# 20 passed

node web/tests/research_explorer.mjs
# RESEARCH EXPLORER BROWSER CHECKS: 27 passed, 0 failed

godot --headless --path . --script res://composition/tests/godot/research_workflow_scene.gd
# 75 checks passed, 0 failures
```

What each layer proves:

* **Adapter** (`test_research_api.py`): the case is the shipped run, every quote
  re-verifies at its offsets, direct evidence only ever comes from
  `pecan_miRNome`, gaps never contain a recommendation, a tampered artifact
  returns 503 instead of evidence, an analysis returns the real computed outputs
  and no yield/RIN port, a maize problem is refused with `result: null`, bad
  submissions are rejected before running, feedback reports persistence honestly,
  and public responses carry no server paths.
* **Staged deployment**: one test copies exactly the Dockerfile's runtime roots
  into an empty directory and runs `composition.runner --run-workflow` there. This
  caught a real defect — `composition/workflow/model_package` was missing from the
  image, so every manifest call failed and the graph was reported invalid. The
  recipe is fixed and the test guards it.
* **HTTP surface**: a real `BoundedThreadingHTTPServer` on an ephemeral port
  serves the page, the case, an analysis, a refusal, an artifact, the Markdown
  report and feedback, and rejects traversal. A static check asserts that every
  element id `app.js` looks up exists in `index.html`.
* **Browser** (`web/tests/research_explorer.mjs`): starts the Python service,
  drives headless Chrome over the DevTools protocol, and checks that the page
  renders 25 claims (6 direct, 17 analogue), that the class filter works, that
  submitting the form runs the workflow and renders 11 computed outputs
  (`claim_count` 25, `direct_target_claim_count` 6, yield availability 0, no
  yield/RIN/degradation row), that the submitted observation is shown as
  "recorded, not used as evidence", and that a maize problem shows the refusal
  panel with no outputs.
* **Desktop parity**: the Godot scene still passes its own 75 checks against the
  same workflow, so the browser layer did not disturb the desktop path.

Manual HTTP checks performed during development: `GET /` → 302 `/research/`;
`/research/` → `text/html`; `/api/research/case` → 25 claims, 6 direct, 17
analogue, 44 gaps; `POST /api/research/analysis` (pecan) → 200 with 11 computed
outputs; the same endpoint with `Zea mays` → 422 `evidence_not_applicable`;
feedback without a configured store → `persisted: false`;
`/research/../api/app.py` and encoded traversal → 404.

### Docker

`docker build` was **not** executed here: the Docker CLI is installed but the
daemon was not running in this environment. The staged-deployment test above
reproduces the image's runtime file list instead, and the image recipe is the
only untested step. `docker build -f api/Dockerfile .` is the exact command to
verify it on a machine with a running daemon.

## 8. Limitations

* The explorer is one case. A submitted problem is only answerable when the
  bundled corpus can support it; otherwise the workflow refuses it. There is no
  upload-your-own-corpus UI.
* The page is not a lab notebook: analyses are ephemeral and bounded.
* PDF export is the browser's print-to-PDF; the server offers Markdown.
* Feedback persistence requires the operator to configure
  `SCALEUP_FEEDBACK_DIR`; otherwise the endpoint says it was not stored.
* No authentication: rate limiting and a single execution slot are the only
  protections. Do not run it with confidential protocols on an untrusted host.
* The scientific limits are the workflow's own: no yield, RIN, purity or
  degradation prediction; analogue protocols remain unvalidated hypotheses.

