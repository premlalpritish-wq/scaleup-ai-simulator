(() => {
  'use strict';
  const apiOverride = new URLSearchParams(location.search).get('api');
  const API = String(apiOverride || window.SCALEUP_API_BASE || '').replace(/\/$/, '');
  const $ = (id) => document.getElementById(id);
  const state = { graph: null, model: null, compatibility: null, context: null, payload: null, values: [], index: 0, playing: false, stale: false, timer: null, requests: 0 };
  const labels = {initial_biomass_concentration:'Initial dry biomass',initial_complex_substrate_concentration:'Initial complex substrate',initial_dissolved_oxygen:'Initial dissolved oxygen',initial_glycerol_concentration:'Initial glycerol',initial_culture_volume:'Initial culture volume',feed_glycerol_concentration:'Feed glycerol',feed_complex_substrate_concentration:'Feed complex substrate',feed_flow_rate:'Feed flow rate',feed_start_time:'Feed start time'};
  const safe = (v) => String(v ?? '—');
  async function api(path, options) {
    const response = await fetch(`${API}/api/${path}`, options || {});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = body.error?.message || body.diagnostics?.map(d => d.message).join(' ') || body.result?.diagnostics?.map(d => d.message).join(' ') || `Request failed (${response.status})`;
      const e = new Error(error); e.body = body; e.status = response.status; throw e;
    }
    return body;
  }
  const jsonPost = (path, value) => api(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  const esc = (s) => safe(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (v, digits=3) => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined,{maximumFractionDigits:digits}) : '—';
  function modelInputs() {
    const instance = state.graph.instances[0];
    return Object.entries(state.graph.literal_inputs || {}).filter(([key]) => key.startsWith(`${instance.instance_id}/`)).map(([key, item]) => ({key, port:key.slice(instance.instance_id.length+1), item}));
  }
  function renderInputs() {
    const root = $('input-fields'); root.replaceChildren();
    for (const {key,port,item} of modelInputs()) {
      const field = document.createElement('div'); field.className='field';
      const label=document.createElement('label'); label.htmlFor=`input-${port}`; label.textContent=labels[port] || port.replaceAll('_',' ');
      const control=document.createElement('div'); control.className='field-control';
      const input=document.createElement('input'); input.id=`input-${port}`; input.type='number'; input.step='any'; input.value=item.value; input.dataset.key=key; input.setAttribute('aria-label',`${label.textContent} (${item.unit})`);
      const unit=document.createElement('span'); unit.className='field-unit'; unit.textContent=item.unit || '';
      control.append(input,unit); field.append(label,control);
      const note=document.createElement('div'); note.className='field-note'; note.textContent=item.method || item.reason || item.source_ref || 'Declared graph input'; field.append(note);
      input.addEventListener('input',()=>{const n=Number(input.value); if(input.value.trim()!=='' && Number.isFinite(n)){state.graph.literal_inputs[key].value=n; markStale();}});
      root.append(field);
    }
  }
  function setStatus(message, kind='') { const el=$('run-status'); el.textContent=message; el.className=`run-status ${kind}`.trim(); }
  function markStale() {
    if (!state.payload) return;
    state.stale=true; $('stale-notice').hidden=false; $('result-chip').textContent='STALE RESULT'; $('result-chip').className='status-chip stale';
    if(document.querySelector('.tab.active')?.dataset.panel==='report') renderPanel('report');
  }
  function pathValue(instance, port) { return state.payload?.trajectories?.[`${instance}/${port}`]; }
  function pointValues() {
    const inst=state.graph.instances[0].instance_id;
    const t=pathValue(inst,'simulation_time')?.values || pathValue(inst,'culture_volume')?.time_axis?.values || [];
    const v=pathValue(inst,'culture_volume')?.values || [];
    const b=pathValue(inst,'biomass_concentration')?.values || [];
    const o=pathValue(inst,'dissolved_oxygen')?.values || [];
    const n=Math.min(t.length,v.length,b.length,o.length);
    return Array.from({length:n},(_,i)=>({t:Number(t[i]),v:Number(v[i]),b:Number(b[i]),o:Number(o[i])})).filter(p=>[p.t,p.v,p.b,p.o].every(Number.isFinite));
  }
  function showPoint(index) {
    if (!state.values.length) return;
    state.index=Math.max(0,Math.min(state.values.length-1,index)); const p=state.values[state.index];
    $('time-value').textContent=num(p.t,2); $('biomass-value').textContent=num(p.b,3); $('oxygen-value').textContent=`${num(p.o,2)}%`; $('volume-readout').textContent=`${num(p.v,4)} L`; $('volume-metric').textContent=`${num(p.v,4)} L`;
    window.scaleupScene?.setVolume(p.v,0.5);
    $('timeline').value=state.values.length>1?String(Math.round(state.index/(state.values.length-1)*1000)):'0';
    $('time-start').textContent=`${num(state.values[0].t,1)} h`; $('time-end').textContent=`${num(state.values.at(-1).t,1)} h`; $('duration-value').textContent=num(state.values.at(-1).t,1);
  }
  function clearCurrent() {
    stop(); state.payload=null; state.values=[]; state.index=0; state.stale=false; $('stale-notice').hidden=true;
    $('result-chip').textContent='NO CURRENT RUN'; $('result-chip').className='status-chip'; $('play-button').disabled=true; $('reset-button').disabled=true; $('timeline').disabled=true;
    $('time-value').textContent='0.0'; $('duration-value').textContent='—'; $('time-end').textContent='—'; $('timeline-hint').textContent='Run the model to load its computed time axis';
    $('biomass-value').textContent='—'; $('oxygen-value').textContent='—'; $('volume-metric').textContent='—'; $('volume-readout').textContent='—'; window.scaleupScene?.setVolume(null,0.5);
  }
  function stop(){state.playing=false;clearInterval(state.timer);state.timer=null;$('play-button').textContent='▶';}
  function play(){if(state.playing){stop();return}if(state.values.length<2)return;state.playing=true;$('play-button').textContent='Ⅱ';state.timer=setInterval(()=>{if(state.index>=state.values.length-1){stop();return}showPoint(state.index+Math.max(1,Math.round(state.values.length/300)));},35);}
  function acceptResult(payload) {
    state.payload=payload; state.values=pointValues(); state.stale=false; $('stale-notice').hidden=true;
    if (!state.values.length) throw new Error('The Python runner completed without returning the required culture_volume, biomass_concentration, dissolved_oxygen, and simulation_time trajectories. The result cannot drive this view.');
    $('result-chip').textContent='PYTHON RESULT'; $('result-chip').className='status-chip ready'; $('play-button').disabled=false; $('reset-button').disabled=false; $('timeline').disabled=false; $('timeline-hint').textContent=`${state.values.length.toLocaleString()} returned trajectory points`;
    showPoint(0); if(document.querySelector('.tab.active')?.dataset.panel==='report') renderPanel('report');
  }
  async function run() {
    const button=$('run-button'); button.disabled=true; setStatus('Validating this graph against registered contracts and compatibility rules…'); clearCurrent();
    try {
      for (const input of document.querySelectorAll('#input-fields input')) {
        if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw new Error(`${input.getAttribute('aria-label')} must be a finite number.`);
        state.graph.literal_inputs[input.dataset.key].value=Number(input.value);
      }
      const validation=await jsonPost('validate',{graph:state.graph});
      if(!validation.valid) throw new Error((validation.diagnostics||[]).map(d=>d.message).filter(Boolean).join(' ') || 'The composition engine refused this graph.');
      setStatus('Running the registered Python scientific model…');
      const payload=await jsonPost('simulations',{graph:state.graph});
      if(payload.execution_status!=='completed'||payload.result_kind!=='computed') throw new Error((payload.diagnostics||[]).map(d=>d.message).join(' ')||'The runner did not report a completed computed result.');
      acceptResult(payload); setStatus(`Computed by ${state.model?.model_id || state.graph.instances[0].model_id} · ${payload.simulation_id}`, 'ok');
    } catch(error) {
      clearCurrent(); const diagnostics=error.body?.diagnostics || error.body?.result?.diagnostics || [];
      const detail=diagnostics.map(d=>d.message).filter(Boolean).join(' ');
      setStatus(detail || error.message || 'The model service is unavailable. No previous result is shown as current.', 'error');
      if(document.querySelector('.tab.active')?.dataset.panel==='report') renderPanel('report');
    } finally {button.disabled=false;}
  }
  function panelHtml(title, html){$('details-panel').innerHTML=`<h3>${esc(title)}</h3>${html}`;}
  function renderPanel(key) {
    const graph=state.graph, inputs=modelInputs();
    if(key==='evidence') {
      let rows=inputs.map(({port,item})=>`<div class="kv"><span>${esc(labels[port]||port)}</span><span>${esc(item.value)} ${esc(item.unit)} · ${esc(item.method||item.reason||item.source_ref||'declared graph input')}</span></div>`).join('');
      panelHtml('Input evidence & provenance',`<p>The operating assumptions below are read directly from the default composition graph. They remain inputs to the model and are not promoted to measurements by execution.</p>${rows}<h4>Model source</h4><p>${esc(state.model?.manifest?.source_ref || graph.source_ref || 'Source citation is declared by the registered model manifest.')}</p><p class="warning">${esc(graph.notes||'')}</p>`); return;
    }
    if(key==='gaps') {
      const gaps=state.context?.gaps || state.context?.focus_gaps || [];
      const list=Array.isArray(gaps)?gaps:[];
      panelHtml('Research gaps & limitations',list.length?`<ul>${list.map(g=>`<li><b>${esc(g.title||g.name||g.quantity||g.gap||'Open question')}</b> — ${esc(g.reason||g.description||g.finding||JSON.stringify(g))}</li>`).join('')}</ul>`:`<p>${esc(state.model?.manifest?.summary||'Gap context is supplied by the project cross-paper assessment.')}</p><p class="warning">${esc(state.graph?.notes||'Scientific limitations are carried by the model manifest and run diagnostics.')}</p>`); return;
    }
    if(key==='models') {
      const all=state.models||[];
      panelHtml('Registered model palette',`<p>Model implementations are selected by the server-side registry. Browser requests cannot name Python modules or filesystem paths.</p><ul>${all.map(m=>`<li><b>${esc(m.model_id||m.id)}</b> · ${esc(m.model_version||m.version||'version recorded in registry')}<br>${esc(m.model_id==='zielinski2019.rhi_process'?'Zieliński literature replay · replay only, not a predictive model':m.title||m.summary||m.description||'Registered scientific model')}</li>`).join('')}</ul><h4>Compatibility engine</h4><pre>${esc(JSON.stringify(state.compatibility?.boundaries||state.compatibility?.connections||state.compatibility,null,2).slice(0,5000))}</pre>`); return;
    }
    if(key==='research') {
      const ctx=state.context||{}; const items=ctx.examined_papers||ctx.papers||ctx.related_papers||[];
      panelHtml('Related papers · project context',items.length?items.map(p=>`<div class="kv"><span>${esc(p.title||p.citation||p.paper||'Paper')}</span><span>${esc(p.doi||p.source_ref||p.assessment||p.summary||'Project cross-paper assessment')}</span></div>`).join(''):`<p>Related-paper context is generated by the project's Python cross-paper and compatibility assessments. ${esc(ctx.notes||ctx.summary||'')}</p><pre>${esc(JSON.stringify(ctx,null,2).slice(0,5000))}</pre>`); return;
    }
    if(key==='report') {
      if(!state.payload){panelHtml('Latest run report',`<p class="warning">${esc($('run-status').textContent)}</p><p>No current simulation result is loaded. A failed request does not reuse an earlier trajectory.</p>`);return;}
      const stale=state.stale?'<p class="warning">This run belongs to the previous input values and is stale.</p>':'';
      panelHtml('Run report & diagnostics',`${stale}<div class="kv"><span>Simulation</span><span>${esc(state.payload.simulation_id)}</span></div><div class="kv"><span>Run status</span><span>${esc(state.payload.result?.status)} · ${esc(state.payload.result_kind)}</span></div><div class="kv"><span>Validation</span><span>${esc(JSON.stringify(state.payload.scientific_validation_status))}</span></div><div class="kv"><span>Model versions</span><span>${esc(JSON.stringify(state.payload.model_versions))}</span></div><div class="kv"><span>Provenance digest</span><span>${esc(state.payload.result?.reproducibility||'recorded in model report')}</span></div><h4>Diagnostics & limitations</h4><ul>${(state.payload.diagnostics||[]).map(d=>`<li>${esc(d.severity)} · ${esc(d.code)}: ${esc(d.message)} ${esc(d.remediation||'')}</li>`).join('')||'<li>No diagnostics returned.</li>'}</ul><details><summary>Composition report and provenance JSON</summary><pre>${esc(JSON.stringify({composition_report:state.payload.composition_report,provenance:state.payload.provenance},null,2))}</pre></details>`);return;
    }
  }
  function setupTabs() {document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t===tab));renderPanel(tab.dataset.panel);}));}
  function setupOrbit() {
    if (window.scaleupScene?.error) setStatus('This browser cannot initialize WebGL for the 3D vessel view.', 'error');
  }
  async function boot() {
    setupTabs();setupOrbit();$('run-button').addEventListener('click',run);$('play-button').addEventListener('click',play);$('reset-button').addEventListener('click',()=>{stop();showPoint(0)});
    $('timeline').addEventListener('input',e=>{stop();showPoint(Math.round(Number(e.target.value)/1000*(state.values.length-1)));});
    $('about-button').addEventListener('click',()=>{document.querySelector('[data-panel="models"]').click();document.querySelector('.control-column').scrollIntoView({behavior:'smooth',block:'start'});});
    try {
      const [health,models,graph,compat]=await Promise.all([api('health'),api('models'),api('default-graph'),api('connections')]);
      state.models=models.models||[];state.graph=graph.graph;state.compatibility=compat;
      const id=state.graph.instances[0].model_id, version=state.graph.instances[0].model_version||'';
      [state.model,state.context]=await Promise.all([api(`models/${encodeURIComponent(id)}/contract`),api(`cross-paper-context/${encodeURIComponent(id+(version?`@${version}`:''))}`)]);
      $('api-state').textContent='Python execution service online';$('footer-version').textContent=`Composition runner ${health.runner_version}`;$('model-tag').textContent=`${id} · ${version}`;
      renderInputs();$('run-button').disabled=false;setStatus('Default graph and registered model contracts loaded.');$('timeline-hint').textContent='Run the model to load its computed time axis';renderPanel('evidence');
    } catch(error) {$('api-state').textContent='Execution service unavailable';$('footer-version').textContent='API unavailable';$('model-tag').textContent='Not connected';setStatus(`${error.message} Configure web/config.js with the API base URL.`, 'error');$('input-fields').innerHTML='<p class="warning">The default graph and model metadata could not be loaded from the execution API.</p>';}
  }
  boot();
})();
