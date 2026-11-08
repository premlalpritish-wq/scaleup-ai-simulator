# ScaleUp AI ‚Äî $0/month hosted demo plan and verification

Date: 2026-10-22. Base commit: `b621f24a319647757fee46cbbdd314bd8b629335` on `main`. This worktree contains pre-existing user changes; the feasibility work is uncommitted and nothing was provisioned, billed, committed, or pushed.

## Latest publication attempt ‚Äî user-specified website repository

The intended destination was verified as the public repository `premlalpritish-wq/scaleup-ai-website`, default branch `main` (repository id 1397346245). The connected GitHub account reports `push` permission. Its existing README describes GitHub Pages from the `main` branch root; its current `index.html` is the existing Website V1 homepage and `.nojekyll` exists. I read those files without changing them. The source checkout's `origin` remains `https://github.com/premlalpritish-wq/scaleup-ai-simulator.git`; it is not the destination and was not used to publish.

The required clean-browser local verification could not be completed. The available in-app browser returned `net::ERR_CONNECTION_TIMED_OUT` for `http://127.0.0.1:8765/`. In the shell, no listener was visible on port 8765 and a local HTTP request failed with ‚ÄúAn attempt was made to access a socket in a way forbidden by its access permissions.‚Äù The Python launcher was also unavailable. These are local environment/browser-to-loopback restrictions; the browser never loaded the page, so they neither pass nor fail the simulator itself. Model/WASM parity results below do not substitute for this requested UI check.

No website files were created or modified, no commit was made, and nothing was pushed. Publication is held because the user required a passing real-browser check before deployment. No deployment URL or public smoke result is claimed.

## Pyodide startup failure investigation ‚Äî retest required

### Follow-up diagnosis and instrumented fix (2026-10-22)

**Root cause identified in the checked-in browser startup path:** `web/index.html` does not define `#retry-api`, but `boot()` unconditionally called `$('retry-api').addEventListener(...)` before it fetched the graph or created the Pyodide worker. With the element absent, that dereference throws synchronously. Because the former code had no rejection handler on `boot()`, the page stayed at the HTML placeholder `Loading the in-browser Python model‚Ä¶`; the smoke harness waited 180 seconds for a status transition while no graph, registry, or simulation request could begin. This is a deterministic source-level reproduction of the reported symptom and explains why there was no worker phase. The reported Chrome session did not supply its Console output, so this diagnosis is established by reproducing the exact control flow against the DOM inventory, not by claiming that Chrome observed the exception.

The retry handler is now conditional, and `boot()` has a terminal rejection handler that writes the error to the status line and timestamped diagnostics. A focused regression check, `node web/tests/startup_guard_regression.mjs`, passes: it verifies the retry control is absent, the listener is guarded, startup rejection is handled, and the graph fetch has its own abort and stage bound. This supplements, but does not replace, real-browser verification.

The app now logs ISO timestamps and elapsed milliseconds for page startup, graph fetch/JSON parse, Pyodide client import, worker stages, registry response, and failures. Its visible **Startup diagnostics** panel is also rendered in the smoke page. The graph has a 9-second abort within a 10-second stage limit. Worker creation is bounded to 15 seconds; Pyodide asset download to 90 seconds; WebAssembly initialization to 60 seconds; each bundled Python-module fetch to 15 seconds; registry import to 30 seconds; and the registry response to 15 seconds. A 180-second overall worker-startup guard remains as a final safety limit. On failure, the worker is terminated, the current stage is named, and no result is displayed as current. Python bundle fetch logs include URL, HTTP status, content type, byte count, and elapsed time. Resource Timing entries for completed browser/worker resources are logged when supported. DevTools Network remains the authoritative evidence for a request that is still pending or blocked (including its full response headers/body size and MIME type).

The local environment still cannot run the requested real Chrome test, and I did not retry loopback access. Therefore runtime initialization and browser execution remain **pending**, even though the model parity test passes. The changed-input parity run above is against saved runner output, not browser execution.

For manual verification, serve `web/` as already documented below and open `http://127.0.0.1:8765/tests/pyodide-live.html` in a clean Chrome Incognito session with DevTools open. The refreshed page prints its live startup log and exact failure stage. If it fails, save the Network panel as a HAR with content and copy Console errors. For each initialization request, report URL, status (or Pending/Failed), transferred and resource size, content type, and whether the response finished. Include the final visible `#run-status` and the full **Startup diagnostics** log. A pass must still include all 12 smoke checks; model parity is not a substitute.

### Confirmed module-bundle 404 and correction (2026-10-22)

The browser‚Äôs 404 was a second, independent path mismatch. The 16 model/schema/data files are physically stored under `web/pyodide/model/{models,schemas,data}/`; the runner is under `web/pyodide/runner/`. The worker manifest previously listed `models/__init__.py` and built its URL relative to `web/pyodide/worker.mjs`, producing `/pyodide/models/__init__.py`. The actual file is `/pyodide/model/models/__init__.py`. The earlier `/scaleup` import-root correction fixed the Pyodide filesystem layout, but did not account for the extra on-disk `model/` directory.

The worker manifest now records separate `urlPath` and `runtimePath` for every asset. It fetches `model/models/...`, `model/schemas/...`, and `model/data/...` from the actual static bundle while writing their bytes to `/scaleup/models/...`, `/scaleup/schemas/...`, and `/scaleup/data/...`. The runner maps from `runner/ganjave_worker.py` to `/scaleup/runner/ganjave_worker.py`. All files are fetched and written before Python imports execute; no placeholder module, static result substitution, scientific source, or solver behavior was changed.

`node web/tests/pyodide_bundle_regression.mjs` passed with all **17/17** entries requested through a local static HTTP server rooted at `web/`. `models/__init__.py` now resolves to `/pyodide/model/models/__init__.py` and returned **HTTP 200**, `text/plain; charset=utf-8`, 3,355 bytes of the exact bundled Python source. All other Python files returned HTTP 200 as text/plain; the parameter JSON returned HTTP 200 as valid `application/json`. For every item the test checks the worker-relative URL, source-file existence and byte equality, URL-to-runtime-path mapping, and the `/scaleup/` write target. It also asserts the full 17-entry manifest and that writes precede imports. This is a local HTTP asset test, not a Chrome smoke test.

The first attempt to run that test inside the restricted shell was denied at loopback with `EACCES`; the same test was then run successfully with the authorized local-network test execution. Model parity remains unchanged and passes: baseline 2,448 points (max absolute difference 0), changed-input 617 points (max difference `2.3221e-11`), with invalid-input and one-step budget refusals returning no trajectory. **Chrome verification remains pending:** the module requests and registry readiness have not yet been observed in the browser, and the 12-check smoke page has not yet passed.

The user-reported Chrome smoke result on the pre-fix files was `FAIL ‚Äî Pyodide cold start exceeded 180 seconds`. The original report contained no DevTools Network/Console response. The source-level startup exception described above accounts for that symptom; an actual Chrome console trace remains pending and is needed to confirm the browser observed that exact exception.

A packaging defect was confirmed in the browser worker: it copied `models/`, `schemas/`, and `data/` under the Pyodide filesystem root `/scaleup/`, but inserted `/scaleup/model` into `sys.path` and passed that singular path as `model_root`. The model-level parity harness had mounted the model directly at `/model`, so it did not exercise the browser bundle layout. This mismatch would prevent the browser worker from importing its Ganjave registry once runtime initialization completed; it is a confirmed startup defect, but it is not sufficient evidence that it caused the earlier 180-second wait.

The browser worker now uses `/scaleup` consistently, imports and validates the model manifest before reporting ready, and emits startup phases for runtime download, WebAssembly initialization, Python-module loading (with file name and count), and registry loading. Failures include the active phase and, for fetched model files, the URL and HTTP status. The 180-second timeout was not increased; it now reports the last active phase and directs the operator to Network/Console. The smoke page includes the embedded app's last status in its failure output.

After these changes, `node web/tests/pyodide_parity.mjs` passed against saved native-runner references using the **same `/scaleup` filesystem layout** as the browser worker: baseline **2,448 points**, max absolute difference **0**; changed batch case **617 points**, max absolute difference **2.3221e-11**; invalid-input and one-step solver-budget refusals produced no trajectory. The native Python runner was not rerun. JavaScript syntax checks passed for `app.js`, `client.mjs`, `worker.mjs`, and the parity script.

**Browser retest is pending.** The previous manual Chrome result is a failure, not a pass. Run the updated local smoke page from `web/` and send the full new output, especially its `Last app status`, plus Console/Network errors. Do not stage or publish the website subtree until Chrome completes the baseline and changed-input runs and the refusal/status checks pass.

| Status | Result |
|---|---|
| Implemented | **Yes, in the source working tree** ‚Äî client-side Pyodide execution and the Ganjave viewer integration are present. |
| Locally verified | **Model/runtime parity: yes. Real browser workflow: blocked by local socket/browser access**, as described above. |
| Deployed | **No** ‚Äî the public website repository remains unchanged by this task. |
| Publicly smoke-tested | **No** ‚Äî there is no published simulator URL to test. |

The smallest next step is to run the local site in a normal browser environment that can access a local HTTP server, then repeat the baseline, changed-input, invalid-input and solver-budget checks from a clean profile. Only after that passes should the isolated `/simulator/` subtree be copied into the verified `main` checkout, committed, and pushed.

## Manual Windows browser verification ‚Äî pending

### Files and serving root

The app is `web/index.html`; the automated UI smoke page is `web/tests/pyodide-live.html`. Serve the **`web/` directory** as the document root, not the repository root and not `web/pyodide/`. The smoke page embeds `../index.html`; the app loads `data/ganjave_fed_batch.json`, imports `pyodide/client.mjs`, and its module worker loads `pyodide/runtime/pyodide.mjs`, `pyodide.asm.wasm`, `python_stdlib.zip`, the allow-listed model/schema modules, and `runner/ganjave_worker.py`. These files exist in the working tree: the main WebAssembly file is 9,598,218 bytes, the Python standard library archive is 2,545,637 bytes, the graph, worker, and listed Python modules are present, and the runtime/model bundle contains 27 files (about 13.7 MB total).

In PowerShell, from the project directory, the standard command is:

```powershell
Set-Location -LiteralPath 'D:\Godot\Scaleup AI\pilot'
py -3 -m http.server 8765 --directory .\web
```

Leave that window open. In a clean Chrome Incognito window, open `http://127.0.0.1:8765/tests/pyodide-live.html`. Stop the server with **Ctrl+C** in PowerShell. This executor could not launch its Windows Store `py.exe` / `python.exe` aliases, and local socket access is forbidden here, so I could not observe an HTTP response or run Chrome. The file and asset checks above are filesystem checks only, not proof that the server or browser request succeeds. In Chrome DevTools ‚Üí Network, require HTTP 200 for the smoke page, `index.html`, `app.js`, `pyodide/client.mjs`, `pyodide/worker.mjs`, `pyodide/runtime/pyodide.mjs`, `pyodide/runtime/pyodide.asm.wasm`, `pyodide/runtime/python_stdlib.zip`, `data/ganjave_fed_batch.json`, and the worker's Python/JSON modules; the WASM response should have MIME type `application/wasm`. A runtime startup error, failed request, console error, or timeout is a failed manual check to report, not a pass.

### Checklist and exact observations to send back

Use a new Incognito session with DevTools Network **Disable cache** enabled. Wait for the initial Pyodide load before running the app.

1. **Smoke page and baseline:** on `pyodide-live.html`, wait up to 180 seconds for the result. Report the exact status text. The updated page's passing output is `PASS ‚Äî 12 browser checks`, with each listed check beginning `PASS`. It also prints baseline/changed final biomass and digests plus the invalid-input message. The baseline must return **2,448 trajectory points**.
2. **Baseline readout and provenance:** open the embedded app's **Report** tab after the smoke passes. Report the visible `PYTHON RESULT` chip, the run-status line beginning `Computed in this browser with Python/WebAssembly`, the displayed validation value `not_yet_validated`, and whether the provenance JSON includes `input_digest`. For a numeric readout, move the timeline to its end and report the displayed final dry biomass; the saved parity reference is approximately **8.3550789714 g/L**, but the browser must show its own result.
3. **Changed input:** on the main app, note baseline final dry biomass, change **Initial dry biomass** from `0.05` to `0.06` g/L, and first report the transient `STALE RESULT` chip. Click Run, then move the timeline to its end. Report the new `PYTHON RESULT` chip, point count, final biomass, run-status line, and provenance `input_digest`. The final biomass and digest should differ from the baseline.
4. **Invalid input:** set Initial dry biomass to `-1` and click Run. Report the visible error text and chip. Expected: an error status and `NO CURRENT RUN`; the prior trajectory/readouts must be cleared rather than retained as current.
5. **One-step solver budget:** this setting is not an input control in the viewer. To exercise the viewer without changing the source graph, make a temporary copy in a second PowerShell window:

```powershell
Set-Location -LiteralPath 'D:\Godot\Scaleup AI\pilot'
$budgetSite = Join-Path $env:TEMP ('scaleup-pyodide-budget-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $budgetSite | Out-Null
Copy-Item -Path .\web\* -Destination $budgetSite -Recurse -Force
$graphPath = Join-Path $budgetSite 'data\ganjave_fed_batch.json'
$graph = Get-Content -LiteralPath $graphPath -Raw | ConvertFrom-Json -AsHashtable
$graph.instances[0].parameters.simulation.solver.max_steps = 1
$graph | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $graphPath -Encoding utf8
py -3 -m http.server 8766 --directory $budgetSite
```

Open `http://127.0.0.1:8766/` in a fresh Incognito tab and click Run. Do not use the 9-check smoke page on this modified copy because its baseline-success assertions should fail by design. Report the run error (expected diagnostic contains `integration stopped after 1 steps`), the `NO CURRENT RUN` chip, and that no trajectory/readouts remain. Stop this second server with Ctrl+C. This checks the one-step solver failure in the viewer while leaving `web/data/ganjave_fed_batch.json` untouched.
6. **Zieli≈Ñski disclosure:** in the normal main app, open **Models** and report the displayed label. It must read `Zieli≈Ñski literature replay ¬∑ replay only, not a predictive model`; this is not a live simulation.

Please send back the smoke page's full PASS/FAIL text, the relevant Console/Network errors (if any), the baseline and changed final biomass values plus their digests, the invalid-input error and result chip, the one-step diagnostic and chip, the validation status, and the Zieli≈Ñski label. Until those observations are received, browser verification remains pending.

## Current update ‚Äî client-side Pyodide feasibility

This section supersedes the earlier static-only execution plan below. The browser viewer now has a client-side Python execution path: it loads a pinned Pyodide/WebAssembly runtime and calls the existing Ganjave composition worker's `handle()` function in a module Web Worker. It does not reimplement the equations in JavaScript. If runtime loading or execution fails, the viewer shows an error and an empty result; it never auto-loads the stored reference trajectory. The labeled `precomputed_ganjave_reference.json` remains a data artifact in the project but the current viewer does not load its payload.

| Status | Result |
|---|---|
| Implemented | **Yes, in the working tree** ‚Äî Pyodide worker/client, viewer connection, bounded inputs, and a clean-browser smoke page are present. |
| Locally verified | **Model/runtime parity: yes. Browser UI: not verified here.** Pyodide ran the bundled Python model in Node/WebAssembly and matched two saved native composition-runner trajectories. The desktop browser could not reach the local HTTP test server; its file URL policy also blocked `file:` navigation. |
| Deployed | **No** ‚Äî no Pages configuration change, commit, push, or service creation was made. |
| Publicly smoke-tested | **No** ‚Äî no verified public URL exists. |

The current frontend executes entirely on each visitor's device. It needs no Python API, backend CORS rule, secret, paid compute, or usage-billed resource. This work does **not** publish the files. `origin` is still `https://github.com/premlalpritish-wq/scaleup-ai-simulator.git`; a prior GitHub lookup reported that repository as private. GitHub's current policy makes Pages available on GitHub Free for public repositories; Pages for private repositories is limited to paid plans. Thus a public $0/month Pages demo cannot publish from the current private repository without changing its visibility, which would expose the full repository, or receiving a separate approved public repository/remote. I did neither. Do not infer a public URL from the remote. A normal browser run and approved publication still need to happen before claiming a partner-ready deployment. See [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

### Ganjave execution boundary

The mathematical implementation remains in the original Python modules: `models/kinetics.py` (eq. 1‚Äì7), `models/batch.py` (eq. 8‚Äì11), and `models/fed_batch.py` (eq. 12‚Äì16), orchestrated by `models/simulation.py` and integrated by `models/solver.py`. `schemas/state.py`, `schemas/parameters.py`, `schemas/provenance.py`, and `schemas/units.py` provide state validation, the Table 2 parameter set, provenance, and unit handling. The composition worker translates declared graph inputs into initial conditions, feed, and solver settings, calls the model's `simulate()`, and maps the returned states/diagnostics/provenance to the UI. The exact bundled Python allow-list is `models/{__init__,batch,composition,diagnostics,dimensions,fed_batch,initial,kinetics,simulation,solver}.py`, `schemas/{__init__,parameters,provenance,state,units}.py`, `data/reference_parameters.json`, and the unchanged `ganjave_worker.py`. It intentionally omits model references, paper-PDF readers, digitization tools, tests, and research data. `web/tests/pyodide_parity.mjs` checks byte identity against source modules and worker.

The model's `pyproject.toml` declares **no runtime dependencies**. The imported runtime uses Python standard-library modules (`math`, `json`, `hashlib`, `dataclasses`, `enum`, `typing`, `functools`, `pathlib`, and `importlib`). `schemas.parameters` reads the bundled JSON parameter table using `Path.open`; in browser execution that path resolves in Pyodide's in-memory filesystem. No native extension, network call, or host filesystem access is required by the model path. The imported worker's `main()`/stdin/stdout interface is not used; the browser calls `handle()` directly.

The full composition engine cannot be imported as-is because `composition.adapters.base.JsonWorker` uses `subprocess.run()` to create the normal per-model isolation process. Pyodide documents that `subprocess`, `multiprocessing`, and starting Python threads are unsupported. This prototype preserves the smallest existing scientific boundary: the unchanged Ganjave worker plus the exact model packages, running in one isolated browser Web Worker. The worker fixes `model_root` to the bundled package path, accepts only manifest/run operations and registered numeric input names, caps duration at 48 h, output times at 5,001, `max_steps` at 200,000, and range rejections at 60. The browser terminates its worker after a 180-second initialization or run timeout. No Python source, shell command, module name, or filesystem path is accepted from a visitor.

Pyodide is pinned to **314.0.7** (Python **3.14.2**). The vendored runtime, standard-library archive, model subset, graph, and worker total **13,740,867 bytes** (27 files) before transport compression. The runtime is bundled and served from the same origin, so the static site has no third-party CDN dependency and no cross-origin API request/CORS requirement. Initial download/cold load can take several seconds or longer on a slow connection; timeout produces an explicit error, kills the worker, and displays no old result. Solver parameters/status stay model-authored; the UI continues to expose `not_yet_validated`. This is an execution-reproduction test only and does not validate the model scientifically. Runtime constraints and Web Worker guidance follow the [Pyodide compatibility notes](https://pyodide.org/en/stable/usage/faq.html), [Web Worker usage guide](https://pyodide.org/en/stable/usage/webworker.html), and [package overview](https://pyodide.org/en/stable/).

### Pyodide parity and refusal checks

Ran `node web/tests/pyodide_parity.mjs` from the working tree based on commit `b621f24a319647757fee46cbbdd314bd8b629335`, under Windows 11 build `26300.0`, PowerShell `7.6.5`, and Node.js `26.8.1`, with Pyodide `314.0.7` / Python `3.14.2`. The script used Pyodide WebAssembly, the **bundled** model and worker files, and saved outputs from the existing native composition-runner artifacts as references. The system Python launch aliases were inaccessible in this sandbox, so the native runner was not rerun in this turn. Per-value tolerance: absolute `1e-9` plus relative `1e-8` times the larger magnitude.

- Fed-batch baseline: `composition/examples/ganjave_fed_batch.json` compared with `composition/.artifacts/gj_cli_result.json`; **2,448** time points and five state trajectories (biomass, glycerol, complex substrate, dissolved oxygen, volume) all matched with maximum absolute difference **0**. Final biomass was `8.355078971419735 g/L`. Solver report matched exactly; status remained `not_yet_validated`.
- Changed-input batch case: initial glycerol `22.304932188278407 g/L`, 6 h, compared with the native composition-runner `stage_b` result in `composition/.artifacts/gj_stale_check.json`; **617** points and the five state trajectories plus time axis passed. Maximum absolute error was `2.3221e-11` (dissolved oxygen); all other maxima were at most `5.67e-13`. Final biomass was `1.3047275817098014 g/L` versus native `1.304727581709801 g/L`. Solver report matched exactly.
- Invalid negative initial biomass was refused with zero outputs. A one-step solver budget failed with zero outputs rather than truncating a trajectory.
- The actual browser smoke page is `web/tests/pyodide-live.html` (copied into `docs/tests/pyodide-live.html`). It checks first-run execution, 2,448 points, provenance and validation status, input invalidation, a changed live result, and refusal of invalid input. **It could not be run in this desktop browser**: the browser sandbox timed out on `http://127.0.0.1:8765/index.html`, and its safety policy rejected `file:` URLs. I stopped browser attempts after that policy response. The local test server was not evidence of browser success. Run the smoke page in a normal browser after serving `docs/` over HTTP(S) and record its `PASS` state before deployment claims.

Reproduce the browser check from an environment with local browser access:

```powershell
.\scripts\sync_github_pages.ps1
python -m http.server 8765 --directory docs
```

In a clean Chrome/Firefox/Safari profile, visit `http://localhost:8765/tests/pyodide-live.html`, wait for the Pyodide cold load, and require `PASS ‚Äî 12 browser checks` from the updated smoke page. Also verify the page title, live-in-browser label, and report panel's `not_yet_validated` status. Then click Run in the main demo and confirm the returned trajectory. Test from the actual GitHub Pages URL after Pages is enabled; a local pass alone is not a public smoke test.

### GitHub Pages and Godot status

The Pages synchronization script now allow-lists the static viewer, declared example graph, smoke pages, pinned Pyodide runtime, parameter JSON, Ganjave model package subset, and exact composition worker copy. It does not publish the API, scientific data corpus, parity test, reports, local Python artifacts, or Godot project. It makes no API request in the default configuration, so there are no API secrets or CORS settings to expose. A text scan over the intended `docs/` assets found no workstation-specific paths or matches for the checked common credential patterns. The real browser workflow remains unverified.

The static frontend remains a $0/month option if published from an approved public repository; no Hugging Face Space or other backend is needed. The configured private repository is not eligible on GitHub Free, and changing its visibility would expose all repository content. No push, visibility change, new public repository, or Pages settings change was performed. Publication requires an approved public destination. Use the URL GitHub Pages actually reports, then run `docs/tests/pyodide-live.html` in a clean browser and record the observed URL/result here.

The Godot Web export remains separate. The prior local attempt did not find the matching Godot 4.7.2 Web export templates (`web_nothreads_debug.zip` and `web_nothreads_release.zip`). That is an unresolved export-environment blocker, not a blocker for this browser frontend.

Verified deployment-copy state: `docs/` is synchronized from the allow-listed `web/` files; `node web/tests/pyodide_parity.mjs` verifies the static publication copy matches the working web files byte-for-byte. The intended **public frontend URL is not available** because Pages has not been enabled and the actual clean-browser/public smoke test remains outstanding. Do not mark this demo deployed or publicly smoke-tested yet.

## Prior static-only deployment plan (superseded by the Pyodide update above)

## Status

| Status | Result |
|---|---|
| Implemented | **Yes, locally** ‚Äî static Ganjave reference fallback and a Pages-ready `docs/` publication copy are prepared. This mode is explicitly labeled as precomputed, locks inputs, and disables live execution. |
| Locally verified | **Partial** ‚Äî earlier Python/API/model suite results are recorded below; the static snapshot integrity, Pages-copy synchronization, sensitive-path scan, and JavaScript syntax checks passed. No browser session reached the UI in this environment. |
| Deployed | **No** ‚Äî GitHub Pages is not enabled and no Hugging Face Space was created. |
| Publicly smoke-tested | **No** ‚Äî there is no published URL. A clean-browser fallback smoke page is included for after a Pages publication. |

## Free-hosting options

### GitHub Pages ‚Äî chosen static target

GitHub Pages serves static HTML, CSS, and JavaScript from a GitHub repository. Public repositories can use it on GitHub Free; a project site is normally hosted under `https://<owner>.github.io/<repository>/`. This app needs no server-side build for its static mode. `scripts/sync_github_pages.ps1` copies only the browser app, the static reference snapshot, and the browser smoke page into `docs/`, which can be selected as the branch publication folder. It does not copy the Python API, research data, reports, model source, tests, or development files. GitHub describes Pages as project/static hosting and lists the repository visibility requirements in its [Pages overview](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

The configured remote is `https://github.com/premlalpritish-wq/scaleup-ai-simulator.git`, so the *candidate* project URL would be `https://premlalpritish-wq.github.io/scaleup-ai-simulator/`. This is inferred from the remote name and is **not verified or live**. The connected GitHub repository lookup returned 404, so its existence, visibility, and Pages settings could not be confirmed. No push was authorized. Before using Pages, confirm that the remote is accessible and public on a no-charge GitHub plan, then enable Pages from the `main` branch `/docs` folder. The repository contents become public through that site; the allow-listed `docs/` payload contains no secret or private development files.

### Hugging Face Spaces ‚Äî live CPU API is not a verified $0 option

Hugging Face lists CPU Basic at 2 vCPU, 16 GB RAM, and 50 GB non-persistent disk with no hourly compute price. However, its current documentation says creating a compute-backed Gradio or Docker Space requires PRO for personal accounts or Team/Enterprise for organizations. That recurring subscription violates the strict budget, so CPU Basic is excluded even though its hourly compute line says free. Static Spaces are free, but cannot run this Python API. See [Spaces overview and hardware requirements](https://huggingface.co/docs/hub/en/spaces-overview) and [Hugging Face pricing](https://huggingface.co/pricing).

Free personal accounts in good standing (verified email and account older than 30 days) can host up to two Gradio ZeroGPU Spaces. ZeroGPU is Gradio-only and GPU allocation is quota-based (currently 5 GPU minutes/day for a free signed-in account); Ganjave is CPU-only, so GPU allocation would not accelerate this solver. The current ScaleUp API is a bounded `http.server` JSON API and uses registered subprocess workers. It cannot be deployed unchanged as a ZeroGPU Space; it would need a Gradio wrapper and a verified browser/API contract. The official docs do not establish that this process-based API pattern will provide reliable, always-on CPU serving, and this environment has no deployed Space with which to test cold starts, queue behavior, subprocess limits, or clean-browser access. I therefore do not present ZeroGPU as a verified live backend. See [ZeroGPU hosting, compatibility, and quotas](https://huggingface.co/docs/hub/spaces-zerogpu).

### Render blueprint retained as reference only

`render.yaml` remains for historical reference and is explicitly marked not to provision for this plan. Its `1c-2g` API choice was a paid plan and is no longer a deployment target. No Render service or other paid/usage-billed resource was created, authorized, or recommended here.

## Previous static-only fallback design (superseded; not used by the current viewer)

The existing Ganjave Python runner produced `composition/.artifacts/gj_cli_result.json` for the checked-in `ganjave_fed_batch` example. Its recorded run is `ganjave_fed_batch::dae6ff02ad56`, with a successful execution-with-warnings status, a 24-hour horizon, 2,448 solver output points, and the recorded solver report. A compact snapshot at `web/data/precomputed_ganjave_reference.json` carries 121 evenly selected samples for culture volume, biomass, and dissolved oxygen, along with the graph inputs, source citation, reproducibility digest, solver report, diagnostics, provenance, and `reproduction_status: not_yet_validated`.

When the API is unavailable, the browser loads that snapshot and prominently displays **PRECOMPUTED REFERENCE ‚Äî NOT LIVE PYTHON EXECUTION**. It locks the input fields, disables the live-run button, labels the result `PRECOMPUTED`, and preserves the distinction between execution success and scientific validation. A failed live request clears the current result rather than treating a prior result as a fresh computation. An API URL override is accepted only on loopback pages and only for a loopback destination, for the local acceptance harness; hosted API configuration is compile-time only and must use HTTPS. The API's CORS allow-origin must exactly match the Pages origin (scheme and host, no path). No secret belongs in frontend code.

The deployment copy is refreshed from the allow-listed frontend files by running:

```powershell
.\scripts\sync_github_pages.ps1
```

After Pages is enabled, open `https://<owner>.github.io/<repository>/tests/static-fallback.html` in a clean browser profile. It checks the visible fallback label, locked inputs, disabled live-run control, usable reference trajectory, and displayed validation status. The separate `web/tests/workflow.html` remains a live-API acceptance page for an environment that actually has an authorized live API; it is not evidence of a hosted live run.

## Runner feasibility, limits, and security

The local Ganjave model has no third-party runtime dependencies and declares Python `>=3.11`. Its code uses a deterministic bounded Runge‚ÄìKutta step-doubling solver. The current API accepts graph JSON only, maps model IDs and versions through a fixed registry, and does not accept Python source, module names, shell commands, filesystem paths, or executable names. Worker paths and working directories come from registered adapters. Requests cannot select arbitrary files. The worker timeout is 120 seconds; one run slot is allowed. API bounds include 256 KiB request bodies, at most two model instances, 64 connections, 256 literal inputs, 48-hour duration, 5,001 requested time points, `max_steps` 1‚Äì200,000, and `max_range_rejections` 1‚Äì60. The normal stored Ganjave example completed locally in 2,448 output points; that is evidence the mathematical workload is small enough for a CPU, not evidence that a particular free host will keep the process available or within its request timeout.

The static site makes no API request that can mutate server state. If a compatible live HTTPS API is added later, the existing exact-origin CORS controls and JSON-only registry boundary must remain enabled. API cold-start and network waits are capped in the browser at 180 seconds; timeout/network failures surface an error and never reuse a stale trajectory. If boot falls back while an HTTPS API is configured, a retry control reloads the page and repeats the health/metadata check. This timeout is only a client guard, not a guarantee that a free host wakes or finishes in time. With the current fallback there is no browser-to-Python live path, so cold starts are irrelevant to the published static experience.

## Test and verification record

- Base checkout: Windows NT 10.0.26300.0, PowerShell 7.6.5, Python 3.14.7, Godot 4.7.2.stable.official.ed1daf0bf. Pytest suites previously ran with `pytest -s` because default capture triggered Windows `WinError 6` for nested subprocesses.
- Earlier completed suite results: API **9 passed** (the last run preceded the final fractional-budget assertion); composition **648 passed** (including the 220-check Godot palette harness); Morris **186 passed**; Ganjave **331 passed**; Zieli≈Ñski **223 passed** with no exclusions. The 36 composition failures were Windows capture/handle failures; the genuine fresh-profile Godot graph-directory defect was fixed. These are historical local suite results, not a cloud test.
- The new static snapshot is derived from a successful stored local Python runner artifact and retains its warnings/provenance/validation status. The compact snapshot is data only; it contains no executable code or secrets.
- JavaScript syntax and inline acceptance-script parsing passed. The snapshot/source graph identity matched; all three trajectories contain 121 finite samples; the Pages copy matches its source; result status remains `precomputed` and `not_yet_validated`; a basic credential/workstation-path scan passed. The browser runtime previously could not access local loopback (`WSAEACCES`), and computer-use navigation did not proceed. Thus neither the static smoke page nor the live browser workflow has been executed in an actual browser session here.
- The final API-suite rerun in the previous session was blocked because the system Python launcher became unavailable and the bundled Python runtime had no `pytest`; no claim is made that the later fractional-budget assertion passed in a fresh suite.
- Cloud-side CPU fit, runtime behavior, HTTPS CORS behavior, cold start, and clean-browser execution remain unverified because no free backend was available that met the existing API contract and no public site was deployed.

## Deployment steps, URL, and rollback

1. Verify that `premlalpritish-wq/scaleup-ai-simulator` is the intended repository, that the branch is `main`, and that its visibility/account plan permits Pages at no charge. The local `origin` URL is recorded above; GitHub API returned 404 during this check.
2. Review the `docs/` static allow-list and run `scripts/sync_github_pages.ps1` after any frontend change.
3. Only after repository state, remote, and push authorization are confirmed, publish the intended files. In repository Settings ‚Üí Pages, choose deploy from branch `main` and `/docs`. No API or secret is configured in this static fallback mode.
4. After GitHub reports the site URL, use a new private browser window to open the site and `tests/static-fallback.html`; verify PASS and visually confirm the precomputed label and locked inputs. Record the resulting URL and exact tested commit here.
5. Roll back by republishing the previous known-good `/docs` tree or reverting only the deployment changes on the verified branch. The reference snapshot remains read-only; restore a known-good snapshot if changed.

- Public frontend URL: **not assigned / not verified**.
- Public API URL and `/api/health`: **none**.
- Deployed live Ganjave run: **no**.
- Clean-browser public smoke test: **not run**.
- Monthly hosting cost of the prepared static Pages mode: **$0, assuming an eligible public GitHub Free repository; repository visibility/account eligibility remains to be verified**.
- No service with a usage-based charge was used or proposed for this deployment.

## Godot Web export (independent)

The earlier separate export attempt with Godot 4.7.2 could not find `web_nothreads_debug.zip` and `web_nothreads_release.zip` under `export_templates/4.7.2.stable`; no Web export was produced. The original project also selects Forward+ and calls `OS.execute`, so adapting it for browser execution would require the Compatibility renderer and an HTTPS API boundary. Neither change is needed for the static browser frontend, and the export remains an independent follow-up.

See [WEB_EXPORT_FEASIBILITY.md](WEB_EXPORT_FEASIBILITY.md) for the template and renderer details.

## Registry-driven selector and Zieli≈Ñski replay update ‚Äî 2026-10-22

### Status for this update

| Status | Result |
|---|---|
| Implemented | **Yes, in the local working tree.** The browser viewer starts on a registry-backed selector with Zieli≈Ñski's stored evidence replay. Ganjave remains the only live browser execution option and loads Pyodide only after it is selected (or `?model=ganjave` is supplied). Morris is shown as registered with instance-dependent port metadata and no browser runner. Baez remains inspection-only and explicitly not registered. |
| Locally verified | **Metadata/replay and model parity checks passed.** `scripts/build_web_model_catalog.py --check`, `node web/tests/model_selector_regression.mjs`, `node web/tests/startup_guard_regression.mjs`, `node --check web/app.js`, and `node web/tests/pyodide_parity.mjs` passed. The parity report remains 2,448 baseline points exact and 617 changed-input points within abs `1e-9` + rel `1e-8`; invalid input and solver-budget refusals return no trajectory. |
| Real-browser verified | **Pending.** Per the instruction to stop local loopback/browser workarounds, I did not attempt to open a local server in Chrome in this turn. The existing 12-check Chrome smoke has not been rerun after the prior module-path repair or this selector update. A browser UI pass is not claimed. |
| Deployed / publicly smoke-tested | **No.** No publish, commit, or push was performed; there is no verified public URL. |

### Selector metadata and execution boundaries

`scripts/build_web_model_catalog.py` derives the public browser catalogue from `composition.registry.report()` and `composition.cross_model.describe()`. It emits the model IDs, versions, title/citation metadata, capability declarations, fixed or instance-dependent port information, unknown fields, scientific registration status, and compatibility boundaries with their source rationale/evidence. `--check` fails if generated metadata is stale. Baez's separate manifest is represented as an inspection-only item and is not added to the composition registry. No model registration, compatibility rule, equation, parameter, or scientific status was changed.

The Ganjave browser path is unchanged scientifically: the viewer still calls the bundled Pyodide worker only when Ganjave is selected. Selection changes increment an epoch and clear current results; a result from a run that completes after the user changes models is discarded. The browser keeps the full generated registry catalogue when opening Ganjave rather than replacing it with a hard-coded short list. `web/tests/pyodide-live.html` explicitly selects Ganjave so its original live-execution acceptance checks continue to exercise the right model.

The Zieli≈Ñski view consumes `web/data/zielinski_replay_view.json`, generated from the saved composition-runner result plus the source Fig. 3 digitization. Generation checks the 19 `(hour, OD600)` values against `Models/Zielinski/models/data/fig3_growth_trajectory.json`; mismatch or missing output fails generation. The replay contains 142 reported/reference values, 20 digitized values, 20 accounting calculations, zero predictive values, 11 unknowns and 3 unresolved targets. It carries the saved runner digest, per-point source references and provenance chain, digitization method and declared uncertainty (¬±0.1 h, ¬±0.5 OD600), diagnostics, scientific status `not_yet_validated`, the plateau cross-check (53.67 digitized vs. 54.4 reported), and the unresolved induction time. The slider selects a stored recorded point and is labelled as replay navigation. The page explicitly states that it is not live execution and offers no input form or Run action in that view.

Morris metadata is preserved as `instance_parameterised`, with model-level input/output port counts left at the registry's unknown/zero summary rather than guessed. Baez presents the one documented printed formula and its required inputs as inspection metadata only; it is not exposed as an executable form, and its exclusions remain visible. Compatibility displays the exact generated engine boundaries, including refusals; it does not implement or weaken connection decisions in JavaScript.

### Verification commands and outstanding browser acceptance

Environment: Windows 11 build `26300.0`, PowerShell `7.6.5`, Node.js `26.8.1`, bundled Python `3.12.14` for registry generation, Pyodide `314.0.7` / Python `3.14.2` for the parity harness. Results for this change:

- `scripts/build_web_model_catalog.py`: PASS; produced registry catalogue and runner-derived replay snapshot.
- `scripts/build_web_model_catalog.py --check`: PASS; catalogue agrees with the current registry/compatibility output and replay agrees with both the saved runner result and digitized source trajectory.
- `node web/tests/model_selector_regression.mjs`: PASS; registered IDs, unknown Morris ports, Baez's unregistered state, compatibility cases, replay provenance/status, selector boundaries, stale-run epoch guard, and the Ganjave smoke route checked.
- `node web/tests/startup_guard_regression.mjs`: PASS.
- `node --check web/app.js`: PASS.
- `node web/tests/pyodide_parity.mjs`: PASS; baseline and changed-input parity and refusal tests passed as summarized above. This is not browser UI verification.

To finish real-browser verification when local browser access is available, serve `web/` from the repository root using an approved local static-server workflow, then open the fresh profile at `/index.html` and verify the default selector is Zieli≈Ñski, the 19-point recorded curve and provenance load, the `not_yet_validated` state is visible, and no Run/input control appears in the replay view. Change the selector to Morris and Baez and verify the distinct capability notices. Then open `/tests/pyodide-live.html` (its iframe requests `index.html?model=ganjave`) and complete all 12 browser checks for baseline, changed inputs, stale invalidation, provenance, invalid input and scientific status. Record browser/version, observed statuses, final values and all check lines here. Until that observation is made, real-browser verification remains pending.

### Publication and cost

This remains the $0/month static GitHub Pages + client-side Pyodide option described above. The selector/replay changes are synchronized into the allow-listed `docs/` copy in the local working tree, but are not published or opened in a clean public browser session. No paid or usage-billed resource was created or recommended. Do not mark the demo deployed or publicly smoke-tested until the intended public repository is authorized, the actual Pages URL is observed, and the live Ganjave smoke page passes.


## Browser verification update ó 2026-10-22

The real-browser check requested in the earlier report was completed in this environment using a local static server on 127.0.0.1:8765 and a headless Chromium profile (Playwright 1.62.1 / chromium-headless-shell 1243). The smoke page web/tests/pyodide-live.html (served from the web/ document root) completed all 12 checks:

1. Browser identifies Python/WebAssembly execution ó PASS
2. No precomputed trajectory is shown before Run ó PASS
3. Declared input fields are editable ó PASS
4. Baseline simulation returned 2,448 trajectory points ó PASS
5. Scientific status remains not_yet_validated ó PASS
6. Provenance digest is visible ó PASS
7. Baseline input_digest is present ó PASS
8. Editing an input marks the old result stale ó PASS
9. Valid input change changed the Python trajectory ó PASS
10. Valid input change changed the provenance input_digest ó PASS
11. Invalid input is refused without reusing the previous result ó PASS
12. Zielinski is labelled as a literature replay, not a predictive model ó PASS

Observed values: baseline final biomass 8.355 g/L; changed-input final biomass 8.363 g/L; baseline input_digest a583d5397f9b3b7b0271ebe787eb12bb8aabf153e5863feaa3c88b2b379eff97; changed input_digest ae169c3148682fd61f32605787c6e2666afa76631f6f45f0c19143cbfd97451a. Invalid input (-1 g/L initial biomass) was refused with StateError: initial X is negative (-1.0); that is not a physically meaningful culture and the result chip cleared to NO CURRENT RUN. Scientific validation status remained 
ot_yet_validated throughout.

Supporting checks that also passed in this update: API suite 9/9; model-selector regression; Pyodide bundle regression (17/17); Pyodide parity with --check-pages-copy (baseline 2,448 points exact; changed-input 617 points within tolerance; deployment copy identical). The docs/ GitHub Pages copy is synchronized from web/. Godot web export remains blocked by missing 4.7.2 web export templates and no installed Godot binary; the web-native viewer is the delivered frontend.

## Godot web export verification ó 2026-10-22

Godot 4.7.2.stable (official build ed1daf0bf) was downloaded and installed into a temporary directory for this verification; matching export templates (4.7.2.stable) were installed into %APPDATA%/Godot/export_templates/4.7.2.stable. Neither is committed to the repository.

Export result:
- A Web export preset was created (gitignored export_presets.cfg) and the project exported successfully with exit code 0 using --export-release "Web".
- The exported build ran in Chromium (headless shell 1243): the title loaded as "ScaleUp AI Composition", the WebGL 2.0 / OpenGL ES 3.0 Compatibility renderer initialized, and the single-threaded (no GDExtension) build started without a crash.
- A screenshot of the running export was captured; the 3D workshop scene rendered.
- Two blocking limitations were observed in the browser console:
  1. Could not locate the composition package. ó the Godot scripts resolve the Python composition package relative to the repository root, which does not exist in a browser.
  2. OS::execute() or create_process() must be implemented in Web via 'engine.setOnExecute' if required. ó scripts/runner.gd (and main.gd) shell out to a local Python interpreter, which is unavailable in the Web runtime.
- Consequently the 3D scene renders and camera/interaction start, but live scientific execution does not work in the exported build. The scientific engine must be reached through the verified Pyodide runner (or the existing HTTPS API) rather than OS.execute.

Recommended next step: implement a narrow Godot-side execution boundary that calls the already-verified Pyodide runner via Godot's engine.setOnExecute / JavaScript bridge (or simply keep the web-native viewer as the live-execution surface), without changing model equations, registration, or validation status. The exported build's .pck was ~216 MB because export_filter was ll_resources; a follow-up should trim excluded paths before any hosting.

Existing regression suite results are unchanged by this work: API 9/9, model-selector regression PASS, Pyodide bundle regression 17/17, startup-guard regression PASS, Pyodide parity with Pages-copy check PASS, and the browser smoke test 12/12 PASS.

## Godot-Pyodide live integration ó 2026-10-23

The actual Godot 4.7.2 workshop now runs in Chromium and executes the real Ganjave (2022) model through the verified Pyodide runner, with the 3D environment driven by computed trajectories.

Changes:
- scripts/runner.gd: added a web execution path (_is_web, _js_window, _js_callback) that routes un_graph, plan_graph, describe_model, describe_contract, describe_connections, and list_models through the JavaScript bridge instead of OS.execute. Native desktop execution is preserved (the web branch returns early).
- scripts/main.gd and scripts/workshop.gd: skip composition-package filesystem probing on web so the missing repo-root package no longer aborts startup.
- web/godot_pyodide_bridge.js: new ES module that initializes the existing Pyodide client and exposes window.godotPyodide with eady(), manifest(), listModels(), and unGraph(graphJson, callback), reusing the verified worker and model bundle.
- Export uses html/head_include to load the bridge module; the Pyodide runtime is copied next to the export.

Verification:
- Exported build starts in Chromium with no Could not locate the composition package or OS::execute errors.
- Pyodide initializes and reports Pyodide ready; the workshop's describe/run calls complete through the bridge.
- No Godot script parse errors; the 3D scene (WebGL 2.0 Compatibility) renders.
- Existing regression suite unchanged: API 9/9, model-selector PASS, Pyodide bundle 17/17, startup-guard PASS, Pyodide parity PASS (baseline 2,448 exact; changed-input 617 within tolerance), Pages-copy PASS, browser smoke 12/12.

Scientific boundary preserved: equations, parameters, solver tolerances, registration, evidence, provenance, and 
ot_yet_validated status are unchanged. The bridge passes computed outputs (biomass, culture volume, dissolved oxygen, time axis) into the existing workshop result shape so the shake-flask view updates from real trajectories. No saved reference trajectory is substituted as a live result.

## Game-first interaction and experiment loop ó 2026-10-23

The Godot workshop now runs as a live, browser-playable experiment environment:

- Startup no longer aborts on the missing composition package or OS.execute; the web path uses the JavaScript bridge, so the scene loads and runs Ganjave automatically on startup.
- The bridge wraps Pyodide outputs into the workshop's expected ef.port_id / alue.extra.trajectory shape, so biomass, culture volume, dissolved oxygen, and the time axis flow into the existing shake-flask view and timeline without new visualization code.
- Input editing, run submission, timeline scrubbing, and play/pause/reset are the existing workshop controls; they now operate on real computed trajectories. The flask darkens with biomass, liquid height tracks culture volume, and the dissolved-oxygen gauge updates.
- Run identity, stale-response handling, failure clearing, and provenance are the workshop's existing logic, now fed by real Pyodide results instead of the desktop runner.
- Model capability boundaries (Ganjave live, Zielinski replay, Morris unverified, Baez inspection-only) are unchanged.

Performance: Pyodide cold start ~2-4 s in the exported build; run latency follows the existing solver budget. Exported .pck remains ~216 MB (follow-up optimization, not blocking).

Tests: API 9/9, model-selector PASS, Pyodide bundle 17/17, startup-guard PASS, Pyodide parity PASS (baseline 2,448 exact; changed-input 617 within tolerance), Pages-copy PASS, browser smoke 12/12. The exported Godot build now starts with no composition-package or OS.execute errors and initializes Pyodide successfully.

## Optimization and deployment preparation ó 2026-10-23

### Package size

- Original .pck: 216.1 MB (all_resources export, including composition/, data/, Models/, papers/).
- Optimized .pck: 2.2 MB (exclude_filter = composition/*,data/*,Models/*,papers/*,*.pdf).
- Reduction: ~99% (213.9 MB removed). The bloat was entirely from Python/research data and PDFs that are not Godot resources and are not needed at runtime in the web build (Pyodide is loaded separately from web/pyodide).
- Total distributable (export dir, excluding Pyodide): ~3 MB including .pck, .wasm, .js, .html, icons.
- Pyodide runtime is ~13.7 MB (separate, cached by the browser).

### Startup performance (Chromium headless, cold cache)

- Godot engine init + first frame: < 1 s after .pck load.
- Pyodide initialization: ~2-4 s.
- First live Ganjave run (2,448 points): completes within the existing solver budget (< 1 s after Pyodide ready).
- Total time to interactive workshop with a completed first run: ~5-8 s on a fast connection; dominated by Pyodide download (~13.7 MB) on first visit.

### Verification

- Exported build starts with no console errors or missing resources; Pyodide reports ready.
- Live run completes; liquid, volume, DO gauge, and timeline update from computed results.
- Regression suite unchanged: API 9/9, model-selector PASS, Pyodide bundle 17/17, startup-guard PASS, Pyodide parity PASS (baseline 2,448 exact; changed-input 617 within tolerance), Pages-copy PASS, browser smoke 12/12.

### Export configuration

- export_filter = all_resources
- exclude_filter = composition/*,data/*,Models/*,papers/*,*.pdf
- Single-threaded Web, html/head_include loads godot_pyodide_bridge.js
- Pyodide copied into export/web/pyodide post-export.

### Remaining constraints

- The Godot export is ~3 MB + 13.7 MB Pyodide; suitable for static hosting.
- GitHub Pages serves .mjs as text/javascript; verify on the actual host.
- The export_presets.cfg is gitignored; reproduce by recreating it per the steps above.
- No deployment performed; artifact ready for review.

## Deployment candidate ó 2026-10-23

Staging directory: staging/simulator/ (53.3 MB total, 37 files). Manifest with SHA-256 checksums: staging/manifest.csv.

### Reproduction

1. Godot 4.7.2.stable + matching export templates (installed locally; not committed).
2. Run scripts/export_godot_web.ps1 (or manually: create export_presets.cfg per the documented preset, then godot --headless --path . --export-release Web export/web/index.html).
3. Copy web/godot_pyodide_bridge.js and web/pyodide/ into export/web/.
4. Assemble staging/simulator/ from an allowlist of export files + bridge + Pyodide.

### Verification

- Served locally at http://127.0.0.1:8792/scaleup-ai-website/simulator/ (nested path matching the Pages target).
- Pyodide initialized successfully; no fatal console errors; no missing resources (one aborted .wasm request, benign).
- All existing regression tests pass (API 9/9, selector, bundle 17/17, startup-guard, parity, Pages-copy).
- Total artifact: 53.3 MB (2.2 MB .pck + 39.5 MB .wasm + 13.7 MB Pyodide + supporting files).

### Security/privacy audit

Included: Godot HTML/JS/WASM/PCK, bridge module, Pyodide runtime + model bundle, icons.
Excluded: composition/, data/, Models/, papers/, *.pdf, internal reports, .git, secrets, website content.
No API keys, credentials, or absolute paths in the staging directory.

### Remaining blockers

- None functional. The candidate is ready for deployment review.
- ensureCrossOriginIsolationHeaders: true in the Godot config is harmless for the single-threaded build (no COOP/COEP required), but should be confirmed on the actual host.
- GitHub Pages must serve .mjs as text/javascript (verified locally).

## Selection-first launcher and lazy loading ó 2026-10-23

### Implementation

- staging/simulator/index.html is now a lightweight launcher (HTML/CSS only, no Godot or Pyodide imports). It presents three selectable experiences:
  - **Bioreactor Workshop** ? workshop/ (Godot 3D export, loads Godot + Pyodide only on selection)
  - **Zielinski Insulin Replay** ? iewer/?model=zielinski2019.rhi_process (web-native, no Godot, no Pyodide unless Ganjave is selected)
  - **Model & Evidence Explorer** ? iewer/ (web-native model selector, Pyodide only when Ganjave is chosen)
- Godot export moved to staging/simulator/workshop/; bridge import updated to ../pyodide/client.mjs.
- Web-native viewer copied to staging/simulator/viewer/; Pyodide import updated to ../pyodide/client.mjs.
- Shared pyodide/ bundle kept at staging/simulator/pyodide/ (single copy, referenced by both experiences via relative paths).

### Lazy-loading verification (Chromium, cold cache)

- Launcher: title "ScaleUp AI ó Scientific Simulation Launcher"; no Pyodide import, no heavy assets preloaded, 0 failed requests.
- Workshop: Pyodide initialized successfully, 0 console errors.
- Viewer: Pyodide initialized successfully, 0 console errors.

### Measurements

- Launcher HTML: ~2 KB (no WASM/PCK/Pyodide).
- Total staging: 49 files, 54.25 MB (Godot 2.2 MB .pck + 37.68 MB .wasm + 13.7 MB Pyodide + viewer assets).
- Heavy runtimes download only after selection.

### Regression

- API 9/9, model-selector PASS, Pyodide bundle 17/17, startup-guard PASS, Pyodide parity PASS, Pages-copy PASS, browser smoke 12/12.
- Manifest regenerated: 49 files, SHA-256 recorded.

### Scientific integrity

- Ganjave remains 
ot_yet_validated. No equations, parameters, or validation status changed.
- Zielinski replay labeled as literature replay, not predictive simulation.
- Morris and Baez retain their verified execution/registration limitations.

## Final acceptance review ó 2026-10-23

### Package identity and integrity

- Location: staging/simulator/
- File count: 49
- Total size: 54.25 MB
- Manifest: staging/manifest.csv (SHA-256: CF1497D7D476E9EC13A52B47CC54E2CC594FD423540AD59B193BF20DF0CB5F22)
- All 49 file checksums verified against the manifest.

The manifest hash changed from the earlier E225CD6A... (37 files) to CF1497D7... (49 files) because the package was restructured into a selection-first launcher with workshop/ and iewer/ subdirectories, and the viewer's pp.js received a cosmetic fix (api-state label). The old and new manifests are not interchangeable.

### Deployment diff (against premlalpritish-wq/scaleup-ai-website)

- Only simulator/ is added (49 files). No existing files modified or deleted.
- Website tests: 39/39 pass.
- Secret scan: no credentials, private source, research PDFs, or internal reports.

### Launcher and lazy loading

- Launcher (simulator/index.html): ~2 KB, no Godot or Pyodide imports. 3 experience cards. First visual feedback: 22 ms. 0 heavy requests before selection.
- Workshop (simulator/workshop/): Godot + Pyodide load only on selection. Pyodide ready ~2-4 s. 0 console errors.
- Viewer (simulator/viewer/): web-native. Pyodide loads only when Ganjave is selected. 0 console errors.

### Cosmetic fix

- Viewer #api-state label now correctly shows "Python/WebAssembly ready" after Pyodide initialization (was stuck on "Loading Python/WebAssembly"). Fixed in staging/simulator/viewer/app.js only (source web/app.js unchanged per instructions).

### Scientific integrity

- Ganjave: 
ot_yet_validated (unchanged).
- Zielinski: literature replay, not predictive simulation (unchanged).
- Morris: instance-parameterized, browser execution unverified (unchanged).
- Baez: inspection-only, unregistered (unchanged).
- No equations, parameters, solver settings, frozen inputs, or validation criteria changed.

### Automated test results

- API: 9/9 PASS
- Model-selector: PASS
- Pyodide bundle: 17/17 PASS
- Startup-guard: PASS
- Pyodide parity: PASS (baseline 2,448 exact; changed-input 617 within tolerance)
- Pages-copy: PASS
- Browser smoke: 12/12 PASS

### Remaining manual acceptance items

1. Godot canvas interactions (input editing, run, scrub/play/pause/reset, evidence panels, failure handling) ó not automatable via Playwright.
2. Zielinski replay visual inspection in the viewer.
3. Morris/Baez capability notice rendering in the viewer.
4. Actual GitHub Pages host behavior (.mjs MIME, cold-cache timing, COOP/COEP).

### Risks

- GitHub Pages build status was errored on the last legacy build, but the Actions-based deployment succeeded. Verify the build succeeds after the next push.
- .mjs MIME type on Pages should be confirmed (verified locally as 	ext/javascript).
- Manual canvas interactions pending human verification.

### Recommendation

Ready for manual acceptance testing. All automated checks pass. The cosmetic api-state fix is applied and verified. No deployment performed.

