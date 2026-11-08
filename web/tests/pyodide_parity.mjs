import assert from 'node:assert/strict';
import fsSync from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { loadPyodide } from '../pyodide/runtime/pyodide.mjs';
import { validateWorkerRequest } from '../pyodide/policy.mjs';

const root = process.cwd();
const pyodide = await loadPyodide({ indexURL: path.resolve('web/pyodide/runtime') + path.sep });
assert.equal(pyodide.version, '314.0.7');
const bundledModelFiles = [
  'models/__init__.py', 'models/batch.py', 'models/composition.py', 'models/diagnostics.py',
  'models/dimensions.py', 'models/fed_batch.py', 'models/initial.py', 'models/kinetics.py',
  'models/simulation.py', 'models/solver.py', 'schemas/__init__.py', 'schemas/parameters.py',
  'schemas/provenance.py', 'schemas/state.py', 'schemas/units.py', 'data/reference_parameters.json',
];
for (const relative of bundledModelFiles) {
  assert.deepEqual(await fs.readFile(`web/pyodide/model/${relative}`), await fs.readFile(`Models/Ganjave/${relative}`), `public browser copy drifted from source: ${relative}`);
}
assert.deepEqual(await fs.readFile('web/pyodide/runner/ganjave_worker.py'), await fs.readFile('composition/composition/_workers/ganjave_worker.py'), 'browser worker copy drifted from the registered worker');
const validPolicyRequest = { op: 'run', inputs: {}, parameters: { mode: 'fed_batch', duration_h: 24, solver: { max_steps: 200000, max_range_rejections: 60 } } };
validateWorkerRequest(validPolicyRequest);
for (const [name, invalid] of [
  ['path field', { ...validPolicyRequest, model_root: '/etc' }],
  ['arbitrary input', { ...validPolicyRequest, inputs: { python_code: { value: 1 } } }],
  ['over-budget duration', { ...validPolicyRequest, parameters: { ...validPolicyRequest.parameters, duration_h: 49 } }],
  ['over-budget steps', { ...validPolicyRequest, parameters: { ...validPolicyRequest.parameters, solver: { max_steps: 200001 } } }],
]) assert.throws(() => validateWorkerRequest(invalid), undefined, `policy must reject ${name}`);
function listFiles(directory) {
  return fsSync.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? listFiles(file) : [file];
  });
}
const siteAssets = ['index.html', 'app.js', 'config.js', 'scene3d.js', 'scene.css', 'style.css', 'data/ganjave_fed_batch.json', 'data/precomputed_ganjave_reference.json', 'tests/static-fallback.html', 'tests/pyodide-live.html'];
if (process.argv.includes('--check-pages-copy')) {
  for (const file of [...siteAssets, ...listFiles('web/pyodide').map((value) => path.relative('web', value))]) {
    assert.deepEqual(await fs.readFile(`docs/${file}`), await fs.readFile(`web/${file}`), `Pages deployment copy drifted: ${file}`);
  }
}

// Mirror the browser worker's exact virtual filesystem: model packages are
// copied to /scaleup/models, /scaleup/schemas, and /scaleup/data. Testing only
// from /model would hide mistakes in the browser bundle's model_root.
pyodide.FS.mkdirTree('/scaleup');
for (const relative of [...bundledModelFiles, 'runner/ganjave_worker.py']) {
  const source = relative.startsWith('runner/')
    ? path.join('web/pyodide', relative)
    : path.join('web/pyodide/model', relative);
  const target = `/scaleup/${relative}`;
  pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf('/')));
  pyodide.FS.writeFile(target, new Uint8Array(await fs.readFile(source)));
}

async function run(request) {
  pyodide.globals.set('REQUEST_JSON', JSON.stringify(request));
  const raw = pyodide.runPython('_parity_request(REQUEST_JSON)');
  return JSON.parse(raw);
}

pyodide.runPython(`
import importlib.util, json, sys
sys.path.insert(0, '/scaleup')
spec = importlib.util.spec_from_file_location('parity_ganjave_worker', '/scaleup/runner/ganjave_worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
def _parity_request(raw):
    request = json.loads(raw)
    request['model_root'] = '/scaleup'
    return json.dumps(worker.handle(request), separators=(',', ':'), default=str)
`);
const manifest = await run({ op: 'manifest' });
assert.equal(manifest.ok, true, `browser bundle manifest failed: ${manifest.error}`);
assert.equal(manifest.manifest.model_id, 'ganjave');

function tolerance(a, b) { return Math.abs(a - b) <= 1e-9 + 1e-8 * Math.max(Math.abs(a), Math.abs(b)); }

async function compare(label, request, artifactPath, resultKey) {
  const refDoc = JSON.parse(await fs.readFile(artifactPath, 'utf8'));
  const reference = refDoc.results[resultKey];
  const actual = await run(request);
  assert.equal(actual.ok, true, `${label}: Pyodide worker returned an error`);
  assert.equal(actual.summary.equations_version, reference.raw_summary.equations_version);
  assert.equal(actual.summary.reproduction_status, reference.raw_summary.reproduction_status);
  assert.deepEqual(actual.summary.solver_report, reference.raw_summary.solver_report, `${label}: solver report differs`);
  const comparisons = [];
  for (const expected of reference.outputs) {
    const port = expected.ref.port_id;
    const expectedTrajectory = expected.value.extra?.trajectory;
    const got = actual.outputs.find((entry) => entry.port_id === port);
    if (!expectedTrajectory || !got?.extra?.trajectory) continue;
    const a = got.extra.trajectory.values;
    const b = expectedTrajectory.values;
    assert.equal(a.length, b.length, `${label}/${port}: point count differs`);
    let maxAbs = 0;
    for (let i = 0; i < a.length; i++) {
      maxAbs = Math.max(maxAbs, Math.abs(a[i] - b[i]));
      assert.ok(tolerance(a[i], b[i]), `${label}/${port}[${i}] exceeds abs 1e-9 + rel 1e-8`);
    }
    comparisons.push({ port, points: a.length, maxAbs });
  }
  const actualTimes = actual.outputs.find((entry) => entry.extra?.trajectory)?.extra?.trajectory?.time_axis?.values || [];
  const expectedTimes = reference.outputs.find((entry) => entry.value.extra?.trajectory)?.value.extra.trajectory.time_axis.values || [];
  assert.equal(actualTimes.length, expectedTimes.length, `${label}: time-axis point count differs`);
  let timeMaxAbs = 0;
  for (let i = 0; i < actualTimes.length; i++) {
    timeMaxAbs = Math.max(timeMaxAbs, Math.abs(actualTimes[i] - expectedTimes[i]));
    assert.ok(tolerance(actualTimes[i], expectedTimes[i]), `${label}/time_axis[${i}] exceeds abs 1e-9 + rel 1e-8`);
  }
  comparisons.push({ port: 'time_axis', points: actualTimes.length, maxAbs: timeMaxAbs });
  assert.ok(comparisons.length >= 6, `${label}: expected to compare five state trajectories and the time axis`);
  return { label, result: 'PASS', pointCount: actual.summary.points, finalBiomass: actual.outputs.find((o) => o.port_id === 'biomass_concentration').value, inputDigest: actual.summary.input_digest, comparisons };
}

const baselineGraph = JSON.parse(await fs.readFile('composition/examples/ganjave_fed_batch.json', 'utf8'));
const baselineInputs = Object.fromEntries(Object.entries(baselineGraph.literal_inputs).map(([key, value]) => [key.split('/')[1], { value: value.value, unit: value.unit, via: value.method }]));
const baseline = await compare('fed-batch baseline', {
  op: 'run', model_root: '/model', inputs: baselineInputs,
  parameters: baselineGraph.instances[0].parameters.simulation,
}, 'composition/.artifacts/gj_cli_result.json', '0');

const changedInputValue = 22.304932188278407;
const changed = await compare('batch changed-input case (initial glycerol)', {
  op: 'run', model_root: '/model',
  inputs: {
    initial_glycerol_concentration: { value: changedInputValue, unit: 'g/L', via: 'native composition runner upstream stage' },
    initial_biomass_concentration: { value: 0.05, unit: 'g/L', via: 'declared literal' },
    initial_complex_substrate_concentration: { value: 5, unit: 'g/L', via: 'declared literal' },
    initial_dissolved_oxygen: { value: 100, unit: '%', via: 'declared literal' },
  },
  parameters: { mode: 'batch', duration_h: 6 },
}, 'composition/.artifacts/gj_stale_check.json', '1');

const errorRun = await run({
  op: 'run', model_root: '/model',
  inputs: { initial_biomass_concentration: { value: -1, unit: 'g/L' }, initial_complex_substrate_concentration: { value: 5, unit: 'g/L' }, initial_dissolved_oxygen: { value: 100, unit: '%' } },
  parameters: { mode: 'batch', duration_h: 6 },
});
assert.equal(errorRun.ok, false, 'invalid initial biomass must be refused');
assert.equal(errorRun.outputs.length, 0, 'invalid input must not yield a trajectory');

const budgetRun = await run({
  op: 'run', model_root: '/model', inputs: baselineInputs,
  parameters: { ...baselineGraph.instances[0].parameters.simulation, solver: { max_steps: 1 } },
});
assert.equal(budgetRun.ok, false, 'a one-step solver budget must fail rather than truncate a trajectory');
assert.equal(budgetRun.outputs.length, 0, 'solver-budget failure must not produce a trajectory');

console.log(JSON.stringify({
  pyodideRuntime: '314.0.7',
  pyodidePython: pyodide.runPython('import sys; sys.version.split()[0]'),
  tolerance: 'abs 1e-9 + rel 1e-8', baseline, changed,
  browserWorkerLayout: 'PASS — model packages, registry, and parameter data imported from /scaleup',
  deploymentCopyCheck: process.argv.includes('--check-pages-copy') ? 'PASS' : 'SKIPPED — use --check-pages-copy when docs/ is synchronized',
  refusalChecks: { invalidInput: 'PASS — no output trajectory', solverBudget: 'PASS — no truncated trajectory' },
  policyGuards: 'PASS — arbitrary path, unregistered input, >48 h duration, and >200,000 steps refused',
}, null, 2));
