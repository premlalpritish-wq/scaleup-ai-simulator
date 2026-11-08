# Browser workshop

This is a static visitor UI. With no API configured, it loads a pinned Pyodide/WebAssembly runtime and calls the existing Ganjave composition worker directly in a browser Web Worker. It runs the original Python modules and solver; it does not translate model equations to JavaScript. The included Ganjave reference snapshot is not auto-loaded or treated as a live result. The literature replay stays labelled and separate from predictive execution.

## Local use

Serve this directory over HTTP or HTTPS (not `file:`). `config.js` defaults to in-browser Pyodide execution. To deliberately use the separate API instead, set `window.SCALEUP_API_BASE` to its HTTPS origin in a deployment build; the page rejects an HTTP API from an HTTPS page. The browser-local mode has no CORS or API secrets because all runtime, model, and graph assets are same-origin static files.

## Hosted use

For the $0/month static plan, run `scripts/sync_github_pages.ps1` and publish the allow-listed `docs/` folder with GitHub Pages. Pyodide runs on the visitor's device with a 180-second worker request timeout and the model's existing 200,000-step solver limit. The first visit downloads the approximately 13.7 MB Pyodide runtime plus model sources; subsequent visits can use the browser cache. `render.yaml` is retained only as a historical paid-service reference and is not needed or provisioned. No key or secret is put in the browser bundle. See `reports/WEB_DEMO_DEPLOYMENT.md` for parity results, limits, and remaining publication requirements.

`tests/workflow.html` is a Chromium acceptance page that drives the app and real API. `tests/static-fallback.html` checks the free static mode and makes no live-execution claim. It must be served over HTTP(S), not opened as a `file:` URL.

## Research explorer (`research/`)

`research/` is a separate page for the pecan RNA research-to-simulation case:
case overview, evidence with provenance, research gaps, a protocol form that runs
the real workflow, Markdown/PDF export and a feedback form.

It has **no in-browser execution mode**. Every result comes from the Python
service on the same origin (`python -m api.app`, which serves `/research/` and
`/api/research/*`), because the workflow reads the bundled corpus and spawns its
worker. On a static-only host the page loads and reports that the service is
unreachable; it does not fall back to sample data. To point it at a separate
Python host, set `window.SCALEUP_RESEARCH_API_BASE` in `research/config.js` and
allow that origin in `SCALEUP_CORS_ORIGIN`.

Deployment, endpoints and verification are documented in
`reports/RESEARCH_EXPLORER.md`. `tests/research_explorer.mjs` is a headless-Chrome
acceptance test: it starts the Python service, loads the page, runs an analysis
through the form and checks the rendered outputs and a refusal
(`node web/tests/research_explorer.mjs`).
