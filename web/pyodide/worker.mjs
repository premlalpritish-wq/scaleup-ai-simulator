import { loadPyodide } from './runtime/pyodide.mjs';
import { validateWorkerRequest } from './policy.mjs';

const BUNDLED_PYTHON_FILES = [
  { urlPath: 'model/models/__init__.py', runtimePath: 'models/__init__.py' },
  { urlPath: 'model/models/batch.py', runtimePath: 'models/batch.py' },
  { urlPath: 'model/models/composition.py', runtimePath: 'models/composition.py' },
  { urlPath: 'model/models/diagnostics.py', runtimePath: 'models/diagnostics.py' },
  { urlPath: 'model/models/dimensions.py', runtimePath: 'models/dimensions.py' },
  { urlPath: 'model/models/fed_batch.py', runtimePath: 'models/fed_batch.py' },
  { urlPath: 'model/models/initial.py', runtimePath: 'models/initial.py' },
  { urlPath: 'model/models/kinetics.py', runtimePath: 'models/kinetics.py' },
  { urlPath: 'model/models/simulation.py', runtimePath: 'models/simulation.py' },
  { urlPath: 'model/models/solver.py', runtimePath: 'models/solver.py' },
  { urlPath: 'model/schemas/__init__.py', runtimePath: 'schemas/__init__.py' },
  { urlPath: 'model/schemas/parameters.py', runtimePath: 'schemas/parameters.py' },
  { urlPath: 'model/schemas/provenance.py', runtimePath: 'schemas/provenance.py' },
  { urlPath: 'model/schemas/state.py', runtimePath: 'schemas/state.py' },
  { urlPath: 'model/schemas/units.py', runtimePath: 'schemas/units.py' },
  { urlPath: 'model/data/reference_parameters.json', runtimePath: 'data/reference_parameters.json' },
  { urlPath: 'runner/ganjave_worker.py', runtimePath: 'runner/ganjave_worker.py' },
];

let activeStage = '';
let activeStageStarted = 0;
function setStage(stage) {
  if (activeStage) log(`SUCCESS ${activeStage}`, { elapsedMs: Math.round(performance.now() - activeStageStarted) });
  activeStage = stage;
  activeStageStarted = performance.now();
  log(`START ${stage}`);
  self.postMessage({ type: 'stage', stage });
}
function finishStage() {
  if (activeStage) log(`SUCCESS ${activeStage}`, { elapsedMs: Math.round(performance.now() - activeStageStarted) });
  activeStage = '';
}

function log(message, extra = {}) {
  self.postMessage({ type: 'diagnostic', entry: { source: 'worker', at: new Date().toISOString(), message, ...extra } });
}

async function boundedFetch(url, label, timeoutMs = 15000) {
  const controller = new AbortController();
  const started = performance.now();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  log(`START fetch ${label}`, { url: url.href, timeoutMs });
  try {
    const response = await fetch(url, { signal: controller.signal });
    const contentType = response.headers.get('content-type') || '';
    if (!response.ok) throw new Error(`${url.href} returned HTTP ${response.status} (${contentType || 'unknown content type'}).`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    log(`SUCCESS fetch ${label}`, { url: url.href, status: response.status, contentType, bytes: bytes.byteLength, elapsedMs: Math.round(performance.now() - started) });
    return bytes;
  } catch (error) {
    const message = controller.signal.aborted ? `Timed out after ${Math.round(timeoutMs / 1000)}s fetching ${url.href}.` : String(error?.message || error);
    log(`FAIL fetch ${label}`, { url: url.href, elapsedMs: Math.round(performance.now() - started), error: message });
    throw new Error(message);
  } finally {
    clearTimeout(timer);
  }
}

self.addEventListener('unhandledrejection', (event) => {
  log('FAIL unhandled worker promise rejection', { error: String(event.reason?.stack || event.reason) });
});
self.addEventListener('error', (event) => {
  log('FAIL worker runtime error', { error: event.message, filename: event.filename, line: event.lineno, column: event.colno });
});
if (typeof PerformanceObserver !== 'undefined') {
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) log('RESOURCE', { url: entry.name, durationMs: Math.round(entry.duration), transferSize: entry.transferSize, encodedBodySize: entry.encodedBodySize, decodedBodySize: entry.decodedBodySize, initiatorType: entry.initiatorType, responseStatus: entry.responseStatus ?? null });
    }).observe({ type: 'resource', buffered: true });
  } catch (error) {
    log('WARN resource timing observer unavailable', { error: String(error?.message || error) });
  }
}

const ready = (async () => {
  let stage = 'Starting the browser Python worker';
  try {
    stage = 'Downloading Pyodide runtime assets (JavaScript, WebAssembly, Python standard library)';
    setStage(`${stage}…`);
    const instantiateStreaming = WebAssembly.instantiateStreaming;
    const instantiate = WebAssembly.instantiate;
    if (instantiateStreaming) {
      WebAssembly.instantiateStreaming = function (...args) {
        stage = 'Initializing Pyodide WebAssembly';
        setStage(`${stage}…`);
        return instantiateStreaming.apply(this, args);
      };
    }
    WebAssembly.instantiate = function (...args) {
      stage = 'Initializing Pyodide WebAssembly';
      setStage(`${stage}…`);
      return instantiate.apply(this, args);
    };
    let pyodide;
    try {
      pyodide = await loadPyodide({ indexURL: new URL('./runtime/', import.meta.url).href });
    } finally {
      WebAssembly.instantiateStreaming = instantiateStreaming;
      WebAssembly.instantiate = instantiate;
    }

    stage = 'Loading bundled Python module';
    for (const [index, entry] of BUNDLED_PYTHON_FILES.entries()) {
      const { urlPath, runtimePath } = entry;
      const moduleStage = `${stage} ${index + 1}/${BUNDLED_PYTHON_FILES.length}: ${urlPath}`;
      setStage(moduleStage);
      const url = new URL(urlPath, import.meta.url);
      const bytes = await boundedFetch(url, urlPath);
      const target = `/scaleup/${runtimePath}`;
      const parent = target.slice(0, target.lastIndexOf('/'));
      pyodide.FS.mkdirTree(parent);
      pyodide.FS.writeFile(target, bytes);
    }

    stage = 'Importing the Ganjave Python model and registry';
    setStage(`${stage}…`);
    pyodide.runPython(`
import importlib.util, json, sys
sys.path.insert(0, '/scaleup')
_worker_path = '/scaleup/runner/ganjave_worker.py'
_spec = importlib.util.spec_from_file_location('scaleup_ganjave_worker', _worker_path)
_worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_worker)
def _scaleup_request(raw):
    request = json.loads(raw)
    request['model_root'] = '/scaleup'
    return json.dumps(_worker.handle(request), separators=(',', ':'), default=str)
`);
    const manifestRaw = pyodide.runPython(`_scaleup_request(json.dumps({'op': 'manifest'}))`);
    const manifestResult = JSON.parse(manifestRaw);
    if (!manifestResult.ok) throw new Error(manifestResult.error || 'The Ganjave registry refused to load.');
    log(`SUCCESS ${stage}`, { modelId: manifestResult.manifest?.model_id, modelRoot: '/scaleup' });
    return { pyodide, manifest: manifestResult.manifest };
  } catch (error) {
    const message = `${stage} failed: ${String(error?.message || error)}`;
    log(`FAIL ${stage}`, { error: message });
    throw new Error(message);
  }
})();

self.onmessage = async (event) => {
  const { id, op = 'run', ...body } = event.data || {};
  try {
    validateWorkerRequest({ op, ...body });
    const runtime = await ready;
    if (op === 'manifest') {
      self.postMessage({ id, result: { ok: true, manifest: runtime.manifest } });
      return;
    }
    const pyodide = runtime.pyodide;
    pyodide.globals.set('_SCALEUP_REQUEST_JSON', JSON.stringify({ op, ...body }));
    const raw = pyodide.runPython('_scaleup_request(_SCALEUP_REQUEST_JSON)');
    self.postMessage({ id, result: JSON.parse(raw) });
  } catch (error) {
    self.postMessage({ id, error: String(error?.message || error) });
  }
};

ready.then(() => {
  setStage('Ganjave Python runtime and model registry ready');
  finishStage();
  self.postMessage({ type: 'ready' });
}, (error) => {
  self.postMessage({ type: 'init_error', error: String(error?.message || error) });
});
