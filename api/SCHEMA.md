# Hosted execution API schema

Base URL: the HTTPS origin assigned to `scaleup-ai-api`. All JSON objects use UTF-8. CORS accepts only the exact origin configured by `SCALEUP_CORS_ORIGIN`.

## Endpoints

| Method and path | Response |
|---|---|
| `GET /api/health` | `{status, service, runner_version}` |
| `GET /api/models` | `{models, runner_version}` from the Python adapter registry |
| `GET /api/models/{model_id}/contract` | Registered model manifest and declared input/output metadata |
| `GET /api/connections` | Compatibility policy from `composition.cross_model` |
| `GET /api/cross-paper-context/{model_id[@version]}` | Project-derived related papers, gaps, and compatibility assessment |
| `GET /api/default-graph` | Default graph document read from `composition/examples/ganjave_fed_batch.json` |
| `POST /api/validate` | `{valid, graph_id, diagnostics, plan, composition_report}`; invalid graphs return HTTP 422 |
| `POST /api/simulations` | Synchronous execution response described below; model failures return HTTP 422 with diagnostics |
| `GET /api/simulations/{simulation_id}` | The completed or failed execution response |
| `GET /api/simulations/{simulation_id}/report` | `{simulation_id, composition_report, provenance, diagnostics}` |

## Research explorer endpoints

The same service also serves the research explorer page and its API. The page is
static and reads documents only; it never computes a scientific value.

| Method and path | Response |
|---|---|
| `GET /` | 302 redirect to `/research/` |
| `GET /research/` | The explorer page (`text/html`); also `/research/app.js`, `/research/style.css`, `/research/config.js` |
| `GET /api/research/case` | The shipped pecan case: problem, sources, 25 claims with provenance, 18 protocol steps, 44 research gaps, readiness flags, verification block including an independent quote re-check |
| `GET /api/research/case/report.md` | Markdown report of the case |
| `GET /api/research/case/artifacts/{name}` | Allow-listed case artifact JSON (`problem_spec`, `literature_manifest`, `research_encoded`, `model_spec`, `composition_graph`, `simulation_result`, `workflow_result`) |
| `POST /api/research/analysis` | `{status, execution_status, analysis_id, applicability, input, problem, diagnostics, verification, result}`. HTTP 200 only when the workflow executed (exit 0); 422 when it refused or failed, with `result: null` |
| `GET /api/research/runs/{analysis_id}` | The stored analysis |
| `GET /api/research/runs/{analysis_id}/report.md` | Markdown report of that analysis |
| `GET /api/research/runs/{analysis_id}/artifacts/{name}` | Allow-listed artifact of that run |
| `POST /api/research/feedback` | `{received, persisted, storage, note}` — states whether the message was stored on this server |

### Analysis request

```json
{
  "problem": "Extract total RNA from pecan (Carya illinoinensis) embryos.",
  "organism": "Carya illinoinensis",
  "tissue": "embryo",
  "molecule": "total RNA",
  "downstream": "small RNA sequencing",
  "constraints": "polyphenol-rich",
  "extraction_method": "TRIzol kit",
  "details": "ground in liquid nitrogen",
  "observations": "brown pellet"
}
```

`problem` is required (1–4,000 characters). Every other field is optional and
bounded (200/300/400/4,000 characters). Unknown fields are rejected with
`unknown_field`. `problem`, `organism`, `tissue`, `molecule`, `downstream` and
`constraints` become the problem specification; `extraction_method`, `details`
and `observations` are recorded in the run document and the report under
`recorded_not_used_as_evidence` and do not affect the model.

A refusal is a structured answer, not an error page: `applicability` carries
`{applicable, code, reason, note}` with codes `problem_blocked`,
`evidence_not_applicable` or `corpus_unavailable`, and `result` is `null`. The
service never substitutes a result from a different problem.

The analysis endpoint shares the graph runner's execution slot and rate limit; it
retains at most `SCALEUP_RESEARCH_RETENTION` (default 5) analyses in memory plus
their temporary directories, and removes the oldest on eviction. Feedback is
written to `SCALEUP_FEEDBACK_DIR/feedback.jsonl` when that variable is set; when
it is not, the response says the message was not stored. No third-party service
is contacted by any of these endpoints, and no API key is involved.


### Validate and simulate request

```json
{
  "graph": {
    "contract_version": "0.1.0",
    "graph_id": "ganjave_fed_batch",
    "instances": [],
    "connections": [],
    "literal_inputs": {}
  }
}
```

The graph must satisfy the existing composition contract. The API refuses unknown model identifiers and versions before execution. It does not accept module names, source code, shell arguments, model package paths, or local file paths.

### Simulation response

The response carries both the existing composition result and a normalized browser view:

```json
{
  "simulation_id": "UUID",
  "execution_status": "completed | failed",
  "graph_id": "graph identity",
  "model_versions": {"instance_id": "registered version"},
  "input_configuration": {"literal_inputs": {}, "instance_parameters": {}},
  "time_axis": {"quantity": "time", "unit": "h", "values": []},
  "trajectories": {"instance_id/port_id": {"quantity": "...", "unit": "...", "time_axis": {}, "values": []}},
  "quantity_definitions": {},
  "diagnostics": [],
  "composition_report": {},
  "provenance": {},
  "scientific_validation_status": {"execution_success": true, "models": {}, "interpretation": "Execution success does not imply scientific validation."},
  "result_kind": "computed | none",
  "result": {}
}
```

`trajectories` is a projection of the existing `ModelValue.extra.trajectory` data; it does not calculate new values. Its `time_axis`, quantity, and unit are copied from the model output. The nested `result` field is the composition runner's serialized response. A failed execution has `execution_status: failed` and `result_kind: none`; previous successful results are never substituted.

## Limits and service behavior

Defaults are environment-configurable: JSON body 256 KiB; 2 graph instances; 64 connections; 256 literal inputs; 48-hour duration; 5,001 requested output times; solver `h_max` 0.001–1 h, `rtol` 1e-8–1e-3, `atol` 1e-12–1e-4, `max_steps` 1–200,000, and `max_range_rejections` 1–60; one active model execution; 20 requests per visitor IP per minute on Render (30 locally); 32 simultaneous HTTP handlers; 15-second idle socket timeout; 16 cached worker responses and 5 most recent simulation results in process memory. On Render only, the API uses the host-provided `X-Forwarded-For` client address for rate limiting; direct local requests use the socket IP. The API clears the composition worker cache after validation/execution. Model workers retain their existing 120-second worker timeout. Runs are synchronous and are not cancelable. Simulation IDs and run records disappear when the service restarts; fetch the result immediately and retain it client-side if needed.

Errors have the shape `{ "error": { "code": "...", "message": "...", "details": null } }`. Runner diagnostics are returned for contract, compatibility, worker, and solver failures. Server traceback fields and absolute project paths are removed from public responses. No third-party runtime package is required.
