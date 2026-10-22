# Browser workshop

This is a static, dependency-free visitor UI. It uses WebGL for a schematic 3D vessel and calls the registered Python API for project metadata and model execution. It does not load Godot or Python in the browser. The web demo keeps the literature replay labelled and separate from live predictive execution.

## Local use

Run the API from the repository root with `python -m api.app`, setting `SCALEUP_CORS_ORIGIN` to the exact static-site origin. Serve this directory with any static HTTP server. `config.js` defaults to same-origin; for a separate API origin, set `window.SCALEUP_API_BASE` to the API HTTPS origin in the deployment build. For a local-only override, `?api=http://127.0.0.1:8080` may be added to the page URL. Browser CORS still has to match the page origin.

## Hosted use

Render's `render.yaml` provisions the static web site and Python API. The static build script writes the deployed API origin to `config.js`; no key or secret is put in the browser bundle. See `api/SCHEMA.md` and `reports/WEB_DEMO_DEPLOYMENT.md` for routes, limits and operating constraints.

`tests/workflow.html` is a Chromium acceptance page that drives the app and real API. It expects the local API at port 8080 and the frontend at port 8000 with `SCALEUP_CORS_ORIGIN=http://127.0.0.1:8000`, or update its API override for another test endpoint.
