# Hosted web demo deployment

Status: implementation and local API validation are ready for deployment; no services have been created, no public URLs exist, and there is no deployed health-check result.

## Architecture and provider

The browser frontend is a static site in `web/`. It draws the shake flask with a small WebGL renderer and gets the default graph, registered contracts, compatibility context and related-paper context from the Python API. It uses no Godot or Python installation in the visitor's browser. The API in `api/app.py` calls the existing Python composition runner and adapters; it does not contain a second copy of the scientific equations.

The repeatable two-service deployment is configured for Render in `render.yaml`: a static site for the frontend and one Docker web service for the Python execution API. The API CORS origin and frontend API base URL are linked through Render's `RENDER_EXTERNAL_URL` service environment values. Render's pricing page currently lists static sites as always free and the 1 CPU / 2 GB web service plan (`1c-2g`) at **$25/month**. The Hobby workspace lists 5 GB monthly bandwidth included and $0.15/GB after that. The API is configured for one concurrent scientific run. This is a provider-plan estimate, not a measured bill; actual charges depend on the account and traffic. [Render pricing](https://render.com/pricing), [Render compute plan specifications](https://render.com/docs/compute-plans)

Render's free web instance is 0.1 CPU / 512 MB RAM and idles out after 15 minutes, taking about a minute to wake. The Blueprint instead selects the paid 1 CPU / 2 GB plan to keep the synchronous scientific request off the documented free-tier resources. No queue is added. The API enforces its own 120-second per-model worker timeout, single-run execution slot, request/rate limits and solver bounds. [Render free-service behavior](https://render.com/docs/free), [Render request behavior and TLS](https://render.com/docs/web-services)

## URLs and verification

- Public demo URL: **not yet assigned**.
- API URL: **not yet assigned**.
- Deployed health check: **not run**.
- Hosting account, connected Git repository, billing authorization, and deployed-service credentials are not available in this workspace. The Blueprint is prepared, but creating the selected API service will incur the published compute charge once it is running. No service was created.

## Live, static, and replayed information

- **Live computed:** Ganjave model trajectories and outputs returned by `composition.runner`, including culture volume, biomass concentration, dissolved oxygen and model time. The API returns input configuration, model version, diagnostics, solver/result data, scientific validation status, composition report and provenance.
- **Project metadata:** contracts, model registry, compatibility policy, default graph and cross-paper research context are assembled from the checked-in project sources by the Python service.
- **Visual representation:** the vessel shell is schematic. The liquid height maps the returned `culture_volume` quantity to the 500 mL flask. It does not claim physical fluid dynamics or spatial gradients.
- **Replay:** the Zieliński material is labelled as a literature replay, not sent through the predictive simulation route.
- A successful execution does not upgrade a model's scientific reproduction status. For the default Ganjave graph, the model response says `reproduction_status: not_yet_validated`.

## Local checks

- API suite: **8 passed**, including registry/contracts, project compatibility and related-paper context, invalid graph/solver bounds, registered-model refusal, a real Ganjave 24-hour run, failed-run invalidation, response path redaction, and trusted proxy client-IP behavior.
- Python model regression suites: Morris **186 passed**; Ganjave suite **passed**. Zieliński suite passed with its nested whole-suite subprocess test deselected; running that one test alone fails because Windows reports `WinError 6` while Python creates the nested pytest process. The Baez exclusion suite has the two pre-existing failures caused by stale assertions that assume only Morris and Zieliński are registered; they still list those exact two models while the pre-existing working-tree change registers Ganjave. Those assertions were not changed.
- Composition regression suite: **36 failures**. The captured failures include Windows `WinError 6` subprocess handle errors and existing acceptance assertions that expect a different main scene/model registry than the current working tree. These source tests and the user's existing changes were left untouched.
- Browser acceptance: `web/tests/workflow.html` loads the real app, changes an input, runs the actual API model, checks returned time-series readouts and the stale-input marker, and rejects an unregistered model id. It could not be executed because loopback socket access was denied in this sandbox; it has not been represented as a pass.
- Godot acceptance: Godot 4.7.2 is installed, but web export failed before a preset/template could be selected. The current user profile path is not writable here, and Godot browser acceptance was not claimed.

## Security and operating limits

The API accepts a graph JSON object only. Its model identifiers and versions must be in the server registry. Requests cannot choose module imports, Python source, commands or filesystem paths. The API has body, graph-size, duration, output-count, solver-step, concurrency and per-client rate limits. It bounds HTTP handler threads and response caches, redacts absolute server paths and tracebacks, and responds with structured errors. HTTPS termination and automatic certificates are provided by the Render web service; the static site also receives HTTPS. CORS is set to the exact deployed frontend origin.

Simulation records are kept in process memory (20 most recent) and disappear on service restart; each result is returned in the original POST response. Execution is synchronous and cannot be canceled. There is no queue, user account system, or secret key in source. The API's in-memory rate limit does not provide persistent abuse tracking across restarts.

## Deploy and rollback

1. Connect this Git repository to Render and create the Blueprint from `render.yaml`.
2. Select the configured `1c-2g` API plan. Review the account's current billing before confirming resource creation.
3. Confirm the Blueprint's `SCALEUP_CORS_ORIGIN` and `API_BASE_URL` resolve to the two deployed service URLs, then wait for the API `/api/health` check to report `status: ok`.
4. Open the static HTTPS URL in Chromium. Run the browser acceptance page at `/tests/workflow.html` only after the API URL and exact CORS origin are in place; then verify one valid run and one rejected graph against the deployed service.
5. To roll back, use Render's deploy rollback to the prior successful deploy for each service, or redeploy the last known good commit. Roll back the API and frontend together if their response schema differs.

The local, repeatable checks are `python -m pytest api/tests -q` and the browser workflow page. To run the local API, set `SCALEUP_CORS_ORIGIN=http://127.0.0.1:8000`, then run `python -m api.app`; serve `web/` at port 8000 and open `web/tests/workflow.html`. The sandbox used for this task denied loopback sockets, so this local browser workflow is prepared but not verified here.

## Remaining limitations

There is no public URL, API URL, successful deployed health check, or browser result against an actual deployed service yet. Hosting credentials and approval to incur the $25/month API service charge are needed to create the Render service. The exported Godot viewer could not be tested because this checkout has no web export preset or installed Godot templates. The current API is intentionally synchronous, process-local and sized for a small partner demo, not a durable high-availability service.
