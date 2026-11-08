// Godot 4.7.2 web -> Pyodide bridge.
(function () {
  const state = { ready: false, client: null, error: null };
  async function init() {
    try {
      const { PyodideGanjaveClient } = await import('./pyodide/client.mjs');
      state.client = new PyodideGanjaveClient({
        onStatus: (m) => console.log('[godot-bridge]', m),
        onDiagnostic: (e) => console.log('[godot-bridge-diag]', e),
      });
      await state.client.ready;
      state.ready = true;
      console.log('[godot-bridge] Pyodide ready');
    } catch (e) {
      state.error = String(e && e.message ? e.message : e);
      console.error('[godot-bridge] init failed', e);
    }
  }
  init();
  window.godotPyodide = {
    ready: () => state.ready,
    error: () => state.error,
    manifest: async function (callback) {
      try {
        if (!state.ready) {
          for (let i = 0; i < 200 && !state.ready; i++) await new Promise(r => setTimeout(r, 100));
        }
        if (!state.ready) throw new Error(state.error || 'Pyodide not ready');
        const m = await state.client.manifest();
        callback(JSON.stringify({ ok: true, manifest: m.manifest || m }));
      } catch (e) {
        callback(JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) }));
      }
    },
    runGraph: async function (graphJson, callback) {
      try {
        if (!state.ready) {
          for (let i = 0; i < 200 && !state.ready; i++) await new Promise(r => setTimeout(r, 100));
        }
        if (!state.ready) throw new Error(state.error || 'Pyodide not ready');
        const graph = JSON.parse(graphJson || '{}');
        const instance = (graph.instances || [])[0] || {};
        const inputs = Object.fromEntries(Object.entries(graph.literal_inputs || {}).map(([key, item]) => [key.slice((instance.instance_id || '').length + 1), { value: item.value, unit: item.unit, via: item.method || item.reason || 'declared graph input' }]));
        const parameters = instance.parameters && instance.parameters.simulation ? instance.parameters.simulation : {};
        const result = await state.client.run(inputs, parameters);
        const outputs = (result.outputs || []).map((o) => ({ ref: { port_id: o.port_id }, value: { state: o.state, extra: o.extra, provenance: o.provenance, method: o.method, unit: o.unit, quantity: o.quantity } }));
        const wrapped = Object.assign({}, result, { outputs: outputs });
        callback(JSON.stringify({ ok: true, result: wrapped, graph_id: graph.graph_id }));
      } catch (e) {
        callback(JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) }));
      }
    },
    run: async function (requestJson, callback) {
      try {
        if (!state.ready) {
          for (let i = 0; i < 200 && !state.ready; i++) await new Promise(r => setTimeout(r, 100));
        }
        if (!state.ready) throw new Error(state.error || 'Pyodide not ready');
        const req = JSON.parse(requestJson || '{}');
        const result = await state.client.run(req.inputs || {}, req.parameters || {});
        callback(JSON.stringify({ ok: true, result: result }));
      } catch (e) {
        callback(JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) }));
      }
    },
    listModels: function (callback) {
      callback(JSON.stringify({ ok: true, models: ['ganjave','morris2011.material_balance','zielinski2019.rhi_process'] }));
    },
  };
})();
