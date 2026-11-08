import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const read = (path) => readFile(new URL(path, root), 'utf8');
const app = await read('app.js');
const html = await read('index.html');
const catalog = JSON.parse(await read('data/model_catalog.json'));
const replay = JSON.parse(await read('data/zielinski_replay_view.json'));

const registered = new Map(catalog.models.map((m) => [m.model_id, m]));
assert.deepEqual([...registered.keys()].sort(), ['ganjave', 'morris2011.material_balance', 'zielinski2019.rhi_process']);
assert.equal(catalog.registry_issues.length, 0);
assert.equal(registered.get('ganjave').browser_mode, 'pyodide_live');
assert.equal(registered.get('zielinski2019.rhi_process').browser_mode, 'stored_evidence_replay');
assert.equal(registered.get('morris2011.material_balance').ports_dependence, 'instance_parameterised');
assert.equal(registered.get('morris2011.material_balance').port_counts.input, 0, 'unknown model-level Morris port counts must not be invented');
assert.equal(catalog.inspection_only[0].model_id, 'baez2014-oxygen-induced');
assert.equal(catalog.inspection_only[0].registration, 'not_registered_in_composition_registry');
assert.match(catalog.inspection_only[0].disclaimer, /does not establish scientific validity/i);
assert.equal(catalog.compatibility.contract_version, '0.1.0');
assert.ok(catalog.compatibility.boundaries.some((b) => b.stance === 'refused_dimensional_only' && !b.permitted));
assert.ok(catalog.compatibility.boundaries.some((b) => b.stance === 'permitted_forward_cascade' && b.permitted));

assert.equal(replay.scientific_status, 'not_yet_validated');
assert.equal(replay.status, 'success_with_warnings');
assert.equal(replay.points.length, 19);
assert.ok(replay.points.every((p, i) => p.hour === i + 1 && Number.isFinite(p.value) && p.provenance === 'digitized'));
assert.ok(replay.points.every((p) => p.source_ref.includes('Fig. 3') && p.chain.some((c) => c.source_ref.includes('doi:10.1016/j.pep.2019.02.002'))));
assert.equal(replay.evidence_summary.predicted_values, 0);
assert.equal(replay.evidence_summary.graph_is_predictive, false);

assert.match(html, /id="model-selector"/);
assert.match(html, /id="zielinski-view"/);
assert.match(html, /STORED LITERATURE EVIDENCE REPLAY · NOT A LIVE SIMULATION/);
assert.match(app, /browser_mode==='stored_evidence_replay'/);
assert.match(app, /if\(id==='zielinski2019\.rhi_process'\)/);
assert.match(app, /This model has no live browser execution action/);
assert.match(app, /runEpoch!==state\.selectionEpoch/);
assert.match(app, /data\/model_catalog\.json/);
assert.match(app, /data\/zielinski_replay_view\.json/);
assert.match(app, /state\.compatibility\?\.boundaries/);
assert.match(await read('tests/pyodide-live.html'), /index\.html\?model=ganjave/);

console.log('PASS — registry IDs, capability boundaries, compatibility source, replay provenance/status, no-live replay behavior, selector isolation guards, and Ganjave smoke route');
