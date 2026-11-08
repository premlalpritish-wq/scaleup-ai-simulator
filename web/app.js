(() => {
  'use strict';
  const localTestOrigin = new URLSearchParams(location.search).get('api');
  const isLoopback = ['localhost','127.0.0.1','[::1]'].includes(location.hostname);
  const localTestApi = localTestOrigin && isLoopback && /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?\/?$/.test(localTestOrigin)
    ? localTestOrigin : '';
  const API = String(localTestApi || window.SCALEUP_API_BASE || '').replace(/\/$/, '');
  if (API && location.protocol === 'https:' && new URL(API).protocol !== 'https:') {
    throw new Error('The configured execution API must use HTTPS on a hosted page.');
  }
  const $ = (id) => document.getElementById(id);
  const startupBegan = performance.now();
  const startupLog = [];
  window.scaleupStartupLog = startupLog;
  function diagnostic(message, details={}) {
    const entry={at:new Date().toISOString(),elapsedMs:Math.round(performance.now()-startupBegan),message,...details};
    startupLog.push(entry);
    const panel=$('startup-log');
    if(panel) panel.textContent=startupLog.map(x=>`[${x.at} +${x.elapsedMs}ms] ${x.message}${x.url?` | ${x.url}`:''}${x.status?` | HTTP ${x.status}`:''}${x.bytes!=null?` | ${x.bytes} bytes`:''}${x.contentType?` | ${x.contentType}`:''}${x.error?` | ${x.error}`:''}`).join('\n');
    console[details.level==='error'?'error':'info']('[ScaleUp startup]',entry);
  }
  function timedStage(name, limitMs, promiseFactory) {
    const started=performance.now(); diagnostic(`START ${name}`,{limitMs});
    let timer;
    return Promise.race([
      Promise.resolve().then(promiseFactory).then(value=>{diagnostic(`SUCCESS ${name}`,{elapsedMs:Math.round(performance.now()-started)});return value;},error=>{diagnostic(`FAIL ${name}`,{elapsedMs:Math.round(performance.now()-started),error:String(error?.message||error),level:'error'});throw error;}),
      new Promise((_,reject)=>{timer=setTimeout(()=>{const error=new Error(`Timed out after ${Math.round(limitMs/1000)}s during ${name}.`);diagnostic(`FAIL ${name}`,{elapsedMs:Math.round(performance.now()-started),error:error.message,level:'error'});reject(error);},limitMs);})
    ]).finally(()=>clearTimeout(timer));
  }
  diagnostic('START application script');
  window.addEventListener('error',event=>diagnostic('FAIL main-thread script/runtime error',{error:event.message,source:event.filename,line:event.lineno,column:event.colno,level:'error'}));
  window.addEventListener('unhandledrejection',event=>diagnostic('FAIL unhandled main-thread promise rejection',{error:String(event.reason?.stack||event.reason),level:'error'}));
  if(typeof PerformanceObserver!=='undefined') try { new PerformanceObserver(list=>list.getEntries().forEach(e=>diagnostic('RESOURCE',{url:e.name,durationMs:Math.round(e.duration),transferSize:e.transferSize,encodedBodySize:e.encodedBodySize,decodedBodySize:e.decodedBodySize,initiatorType:e.initiatorType,responseStatus:e.responseStatus??null}))).observe({type:'resource',buffered:true}); } catch(error) { diagnostic('WARN resource timing observer unavailable',{error:String(error)}); }
  const state = { graph: null, model: null, compatibility: null, context: null, payload: null, values: [], index: 0, playing: false, stale: false, timer: null, requests: 0, mode: 'live', executor: null, catalogue: null, selected: '', selectionEpoch: 0, replay: null };
  const labels = {initial_biomass_concentration:'Initial dry biomass',initial_complex_substrate_concentration:'Initial complex substrate',initial_dissolved_oxygen:'Initial dissolved oxygen',initial_glycerol_concentration:'Initial glycerol',initial_culture_volume:'Initial culture volume',feed_glycerol_concentration:'Feed glycerol',feed_complex_substrate_concentration:'Feed complex substrate',feed_flow_rate:'Feed flow rate',feed_start_time:'Feed start time'};
  const safe = (v) => String(v ?? '—');
  async function api(path, options) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);
    let response;
    try { response = await fetch(`${API}/api/${path}`, {...(options || {}), signal:controller.signal}); }
    catch(error) {
      if(controller.signal.aborted) throw new Error('The execution service did not respond within 180 seconds. It may be waking from sleep or unavailable; no previous result is reused.');
      throw new Error(`Could not reach the HTTPS execution service: ${error.message || 'network error'}. No previous result is reused.`);
    } finally { clearTimeout(timeout); }
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
  function setStatus(message, kind='') { const el=$('run-status'); el.textContent=message; el.className=`run-status ${kind}`.trim(); if(kind==='error') diagnostic(`FAIL UI status: ${message}`,{level:'error'}); }
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
    const isPrecomputed=state.mode==='precomputed';
    $('result-chip').textContent=isPrecomputed?'PRECOMPUTED':'PYTHON RESULT'; $('result-chip').className=`status-chip ${isPrecomputed?'precomputed':'ready'}`; $('play-button').disabled=false; $('reset-button').disabled=false; $('timeline').disabled=false; $('timeline-hint').textContent=`${state.values.length.toLocaleString()} ${isPrecomputed?'stored reference':'returned'} trajectory points`;
    showPoint(0); if(document.querySelector('.tab.active')?.dataset.panel==='report') renderPanel('report');
  }
  function fromBrowserPython(result) {
    const instance=state.graph.instances[0].instance_id, trajectories={};
    for (const output of result.outputs || []) {
      const trajectory=output.extra?.trajectory;
      if (trajectory) trajectories[`${instance}/${output.port_id}`]=trajectory;
    }
    const timeAxis=Object.values(trajectories)[0]?.time_axis?.values || [];
    trajectories[`${instance}/simulation_time`]={values:timeAxis};
    const digest=result.summary?.input_digest || '';
    return {
      execution_status:result.ok?'completed':'failed',result_kind:result.ok?'computed':'none',
      simulation_id:`pyodide:${digest.slice(0,12) || 'run'}`,trajectories,
      result:{status:(result.diagnostics||[]).some(d=>d.severity==='warning')?'success_with_warnings':'success',reproducibility:digest,solver_report:result.summary?.solver_report},
      diagnostics:result.diagnostics||[],scientific_validation_status:result.summary?.reproduction_status,
      model_versions:[{model_id:result.summary?.model_id||'ganjave',model_version:result.summary?.model_version||'0.1.0',equations_version:result.summary?.equations_version}],
      composition_report:{execution_model:'client-side Pyodide/WebAssembly',summary:result.summary},provenance:result.provenance,
    };
  }
  async function run() {
    if(state.selected!=='ganjave'||state.mode!=='pyodide'){setStatus('This model has no live browser execution action. No simulation was run.','error');clearCurrent();return;}
    const runEpoch=state.selectionEpoch;
    const button=$('run-button'); button.disabled=true; setStatus('Validating this graph against registered contracts and compatibility rules…'); clearCurrent();
    let inputSnapshot='';
    try {
      for (const input of document.querySelectorAll('#input-fields input')) {
        if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw new Error(`${input.getAttribute('aria-label')} must be a finite number.`);
        state.graph.literal_inputs[input.dataset.key].value=Number(input.value);
      }
      inputSnapshot=JSON.stringify(state.graph.literal_inputs||{});
      let payload;
      if (state.mode==='pyodide') {
        setStatus('Running the Ganjave Python model in this browser. First run may take a few seconds…');
        const instance=state.graph.instances[0];
        const inputs=Object.fromEntries(Object.entries(state.graph.literal_inputs||{}).map(([key,item])=>[key.slice(instance.instance_id.length+1),{value:item.value,unit:item.unit,via:item.method||item.reason||'declared graph input'}]));
        const raw=await state.executor.run(inputs,instance.parameters?.simulation||{});
        if(runEpoch!==state.selectionEpoch||state.selected!=='ganjave')return;
        if(!raw.ok) throw Object.assign(new Error(raw.error||'The Ganjave model refused this run.'),{body:raw});
        payload=fromBrowserPython(raw);
      } else {
        const validation=await jsonPost('validate',{graph:state.graph});
        if(!validation.valid) throw new Error((validation.diagnostics||[]).map(d=>d.message).filter(Boolean).join(' ') || 'The composition engine refused this graph.');
        setStatus('Waiting for the registered Python runner. A sleeping free service may take time to wake; the server enforces a 120-second model limit…');
        payload=await jsonPost('simulations',{graph:state.graph});
        if(payload.execution_status!=='completed'||payload.result_kind!=='computed') throw new Error((payload.diagnostics||[]).map(d=>d.message).join(' ')||'The runner did not report a completed computed result.');
      }
      if(runEpoch!==state.selectionEpoch||state.selected!=='ganjave')return;
      if(inputSnapshot!==JSON.stringify(state.graph.literal_inputs||{})) throw new Error('Inputs changed while this run was in progress. The result was discarded and no prior trajectory is shown as current.');
      acceptResult(payload); setStatus(`${state.mode==='pyodide'?'Computed in this browser with Python/WebAssembly':'Computed by '+(state.model?.model_id || state.graph.instances[0].model_id)} · ${payload.simulation_id}`, 'ok');
    } catch(error) {
      if(runEpoch!==state.selectionEpoch||state.selected!=='ganjave')return;
      clearCurrent(); const diagnostics=error.body?.diagnostics || error.body?.result?.diagnostics || [];
      const detail=diagnostics.map(d=>d.message).filter(Boolean).join(' ');
      setStatus(detail || error.message || 'The model service is unavailable. No previous result is shown as current.', 'error');
      if(document.querySelector('.tab.active')?.dataset.panel==='report') renderPanel('report');
    } finally {if(runEpoch===state.selectionEpoch&&state.selected==='ganjave')button.disabled=false;}
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
      panelHtml('Registry-derived model palette',`<p>Model metadata comes from the generated composition registry report. Registration is not scientific validation. Browser execution is available only for Ganjave; Zieliński is a stored literature replay; Zieliński literature replay · replay only, not a predictive model; Morris is instance-parameterized; Baez is inspection-only and absent from the registry.</p><ul>${all.map(m=>`<li><b>${esc(m.model_id)}</b> · ${esc(m.model_version)}<br>${esc(m.title||'Title unknown at model level')}<br>Execution view: ${esc(m.browser_mode)} · scientific status: ${esc(m.scientific_status?.state||'unknown')}<br>Capabilities: ${esc(m.capabilities?.join('; ')||'unknown at model level')}<br>Ports: ${esc(m.ports_dependence)} · ${esc(JSON.stringify(m.port_counts))}</li>`).join('')}</ul><h4>Inspection-only artifact (not registered)</h4><p>${esc((state.catalogue?.inspection_only||[]).map(x=>`${x.model_id}: ${x.registration} — ${x.reason}`).join(' ')||'None')}</p><h4>Compatibility rules · ${esc(state.compatibility?.contract_version||'')}</h4><p>${esc(state.compatibility?.claim_scope||'')}</p><ul>${(state.compatibility?.boundaries||[]).map(b=>`<li><b>${esc(b.source_model)} → ${esc(b.target_model)}: ${esc(b.stance)}</b> · ${b.permitted?'permitted':'refused'}${b.enforced_by_engine?' · enforced by engine':''}<br>${esc(b.reason)}<details><summary>Evidence and remediation</summary><p>${esc((b.evidence||[]).join(' · '))}</p><p>${esc(b.remediation||'')}</p></details></li>`).join('')}</ul><p>Compatibility report status: ${esc(JSON.stringify(state.compatibility?.validation_status||{}))}</p>`); return;
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
  async function fetchJsonAsset(path, stage) {
    const url=new URL(path,document.baseURI);
    return timedStage(stage,12000,async()=>{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),11000);try{const response=await fetch(url,{signal:controller.signal});const type=response.headers.get('content-type')||'';if(!response.ok)throw new Error(`HTTP ${response.status} (${type})`);const raw=await response.text();diagnostic(`SUCCESS ${stage}`,{url:url.href,status:response.status,contentType:type,bytes:new TextEncoder().encode(raw).byteLength});return JSON.parse(raw);}catch(error){throw new Error(`${stage} failed for ${url.href}: ${controller.signal.aborted?'request timed out':error.message||error}`);}finally{clearTimeout(timer);}});
  }
  function catalogEntry(id) { return state.catalogue?.models?.find(m=>m.model_id===id)||state.catalogue?.inspection_only?.find(m=>m.model_id===id); }
  function showView(view) {
    $('ganjave-workspace').hidden=view!=='ganjave';$('zielinski-view').hidden=view!=='zielinski';$('registry-view').hidden=!['morris','baez'].includes(view);
    $('execution-mode').hidden=view!=='ganjave';
  }
  function drawReplay() {
    const points=state.replay?.points||[];if(points.length<2)throw new Error('Recorded Zieliński replay evidence is missing or incomplete.');
    const svg=$('replay-chart'),W=760,H=300,L=58,R=20,T=16,B=42, ymax=60;
    const X=i=>L+i*(W-L-R)/(points.length-1),Y=v=>T+(ymax-v)*(H-T-B)/ymax;
    const grid=[];for(let v=0;v<=60;v+=10)grid.push(`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" class="chart-grid"/><text x="${L-10}" y="${Y(v)+4}" text-anchor="end" class="chart-label">${v}</text>`);
    const path=points.map((p,i)=>`${i?'L':'M'}${X(i)},${Y(p.value)}`).join(' ');
    svg.innerHTML=`${grid.join('')}<line x1="${L}" x2="${L}" y1="${T}" y2="${H-B}" class="chart-axis"/><line x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}" class="chart-axis"/><path d="${path}" class="chart-line"/>${points.map((p,i)=>`<circle cx="${X(i)}" cy="${Y(p.value)}" r="4" class="chart-point" data-index="${i}"><title>${p.hour} h: ${p.value} OD600 · digitized</title></circle>`).join('')}<text x="${W/2}" y="${H-8}" text-anchor="middle" class="chart-label">Culture time (h)</text><text x="16" y="${H/2}" transform="rotate(-90 16 ${H/2})" text-anchor="middle" class="chart-label">OD600</text>`;
    const p=points[Number($('replay-timeline').value)||0];if(p){$('replay-readout').textContent=`${p.hour} h · OD600 ${num(p.value,2)}`;$('replay-hour').textContent=`${p.hour} h`;$('replay-od').textContent=num(p.value,2);svg.querySelectorAll('.chart-point').forEach((el,i)=>el.classList.toggle('selected',i===Number($('replay-timeline').value)));}
  }
  function renderZielinskiReplay() {
    showView('zielinski');const r=state.replay,source=r.source,points=r.points;
    $('replay-source').textContent=`${source.citation} · ${source.figure} · printed p. ${source.printed_page} (PDF p. ${source.pdf_page}).`;
    $('replay-timeline').max=String(points.length-1);$('replay-timeline').value='0';drawReplay();
    const c=r.evidence_summary;
    $('replay-provenance').innerHTML=`<p><b>Stored composition result:</b> ${esc(r.run_id)} · ${esc(r.status)} · digest <code>${esc(r.digest)}</code>.</p><p><b>Data origin:</b> ${esc(source.figure)} was digitized from the published image. ${esc(source.method)} Declared uncertainty: ±${esc(source.uncertainty.od600)} OD600 and ±${esc(source.uncertainty.time_h)} h.</p><p><b>Recorded evidence counts:</b> ${esc(c.observed_reference_values)} observed/reference values, ${esc(c.digitized_values)} digitized values, ${esc(c.computed_values)} accounting calculations, ${esc(c.unknown_values)} unknowns and ${esc(c.unresolved_targets)} unresolved targets. Predictive values: ${esc(c.predicted_values)}. Graph marked predictive: ${esc(c.graph_is_predictive)}.</p><p><b>Scientific status:</b> <code>${esc(r.scientific_status)}</code>. Replaying this evidence is not a model validation or prediction for a new batch.</p><p><b>Source:</b> <a href="${esc(source.doi_url)}" target="_blank" rel="noopener">${esc(source.citation)}</a>; ${esc(source.figure)} at printed page ${esc(source.printed_page)} (PDF page ${esc(source.pdf_page)}).</p><p><b>Known cross-check:</b> the digitized plateau is ~53.67 OD600; the paper separately reports 54.4 in section 4.2. Both remain visible in the source replay; this view does not reconcile them.</p><p><b>Unresolved:</b> induction time is not stated in the paper and cannot be recovered from Fig. 3.</p>`;
    $('replay-results').innerHTML=`<p>Values below are loaded from the stored composition runner result. No solver runs in this view.</p>${r.summary.slice(0,12).map(x=>`<div class="kv"><span>${esc(x.label)}</span><span>${esc(x.display)} <small>· ${esc(x.provenance)} · ${esc(x.source_ref||'source not specified')}</small></span></div>`).join('')}<details><summary>Replay diagnostics (${r.diagnostics.length})</summary><ul>${r.diagnostics.map(d=>`<li>${esc(d.severity)} · ${esc(d.code)}: ${esc(d.message)}</li>`).join('')||'<li>No diagnostics recorded.</li>'}</ul></details>`;
    $('api-state').textContent='Stored evidence replay · no execution';$('selected-model-title').textContent='Zieliński · literature evidence replay';$('model-tag').textContent='Zieliński · replay only';$('footer-version').textContent='Stored Python composition-runner record';$('execution-label').textContent='EVIDENCE REPLAY · NOT LIVE';$('execution-description').textContent='Inspect digitized and reported values from one published experiment. This view does not predict a new batch.';$('model-selector-status').textContent='Stored replay only; no model execution or input editing is available.';setStatus('Stored Zieliński evidence replay loaded. This is not a live simulation.');
  }
  function renderRegistryOnly(id) {
    const m=catalogEntry(id);if(!m)throw new Error(`Registry metadata for ${id} is unavailable.`);showView(id==='baez2014-oxygen-induced'?'baez':'morris');
    const baez=id==='baez2014-oxygen-induced';$('registry-title').textContent=m.title||id;
    $('registry-description').innerHTML=`<p>${esc(m.source_paper||'Citation is marked unknown in the registry.')}</p><p>${esc(baez?m.disclaimer:'This model is registered, but its model-level port surface is parameterized by the declared instance. No browser execution implementation is available in this demo.')}</p>`;
    const caps=baez?m.equations.map(e=>`${e.label}: ${e.printed_expression} → ${e.output_key} (${e.output_unit})`):[`Composition registration: ${m.model_id}@${m.model_version}`,`Port dependence: ${m.ports_dependence}`,`Ports: input ${m.port_counts?.input??'unknown'} · output ${m.port_counts?.output??'unknown'}`,`Capabilities: ${m.capabilities?.join('; ')||'unknown at model level'}`,`Unknown registry fields: ${m.unknown_fields?.join(', ')||'none'}`];
    $('registry-metadata').innerHTML=`<ul>${caps.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>${baez?`<p>Required inputs: ${esc(m.equations[0].required_run_inputs.join(', '))}. Source: ${esc(m.equations[0].source_reference)}.</p><h4>Explicit exclusions</h4><ul>${m.excluded_capabilities.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}`;
    $('registry-caveat').textContent=baez?'Baez is inspection-only and is not registered in the composition engine. The displayed single printed equation is not an interactive prediction; no form or Run action is provided.':`Registry status: ${m.scientific_status?.state||'unknown'}. Morris is available in the composition registry, but there is no fixed model-level port set or browser execution path here. Port counts shown above are registry summary counts for this instance-parameterized registration, not a complete fixed port declaration.`;
    $('api-state').textContent=baez?'Inspection only · not registered':'Registered · browser run unavailable';$('selected-model-title').textContent=m.title||id;$('model-tag').textContent=baez?'Baez · inspection only':'Morris · instance-parameterized';$('footer-version').textContent='Registry metadata only';$('execution-label').textContent='NO BROWSER EXECUTION';$('execution-description').textContent='This selection exposes verified registry or inspection metadata only; no simulation is executed.';$('model-selector-status').textContent=baez?'Not composition-registered; one printed formula is documented, not run.':'Registered model; browser execution and fixed port metadata are not available.';setStatus(baez?'Inspection metadata loaded; no model execution is available.':'Morris registry metadata loaded; browser execution is not available.');
  }
  async function resumeGanjave(epoch) {
    const current=()=>epoch===state.selectionEpoch&&state.selected==='ganjave';
    await state.executor.ready;if(!current())return;
    state.graph=await fetchJsonAsset('data/ganjave_fed_batch.json','Ganjave graph load');if(!current())return;
    if(!state.model?.manifest){const manifest=await state.executor.manifest();if(!current())return;if(!manifest.ok)throw new Error(manifest.error||'The browser runtime could not load the Ganjave contract.');state.model={model_id:'ganjave',model_version:'0.1.0',manifest:manifest.manifest};}
    state.mode='pyodide';state.context={notes:state.graph.notes||'Scientific limitations are declared in the model contract and run diagnostics.'};renderInputs();
    $('execution-mode').hidden=false;$('execution-banner-title').textContent='PYTHON RUNTIME READY.';$('execution-banner-copy').textContent='Run the bundled Ganjave model locally. Failed execution never loads a stored trajectory.';$('execution-label').textContent='PYTHON RUNTIME READY';$('execution-description').textContent='Ganjave runs in browser-local Python/WebAssembly; results appear only after a successful computation.';$('api-state').textContent='Python/WebAssembly ready';$('footer-version').textContent='Pyodide 314.0.7 · client-side Python';$('model-tag').textContent='ganjave · 0.1.0';$('selected-model-title').textContent='Ganjave et al. · 2022';$('run-button').disabled=false;$('model-selector-status').textContent='Ganjave is the only interactive model execution in this browser build.';setStatus('Python/WebAssembly ready. Runs execute the bundled Ganjave Python model in this browser.');renderPanel('evidence');
  }
  async function selectModel(id) {
    const epoch=++state.selectionEpoch;state.selected=id;state.mode='none';state.payload=null;state.values=[];state.graph=null;$('run-button').disabled=true;clearCurrent();$('model-selector').value=id;
    if(id==='zielinski2019.rhi_process'){try {if(!state.replay)state.replay=await fetchJsonAsset('data/zielinski_replay_view.json','Zieliński evidence replay data');if(epoch!==state.selectionEpoch)return;renderZielinskiReplay();}catch(error){showView('zielinski');$('model-selector-status').textContent=error.message;setStatus(`Stored evidence replay could not be loaded: ${error.message}`,'error');}return;}
    if(id==='morris2011.material_balance'||id==='baez2014-oxygen-induced'){renderRegistryOnly(id);return;}
    if(id==='ganjave'){showView('ganjave');try{if(state.executor&&!state.executor.stopped)await resumeGanjave(epoch);else await bootPyodide(epoch);}catch(error){if(epoch!==state.selectionEpoch)return;$('api-state').textContent='Browser Python unavailable';$('run-button').disabled=true;$('execution-mode').hidden=false;$('execution-banner-title').textContent='BROWSER EXECUTION UNAVAILABLE.';$('execution-banner-copy').textContent='No stored trajectory is substituted.';setStatus(`Browser Python could not start: ${error.message}. No stored trajectory is shown as live.`, 'error');$('input-fields').innerHTML='<p class="warning">The model inputs could not be loaded. This page does not substitute a stored trajectory when live browser execution fails.</p>';}}
  }
  async function bootPyodide(epoch=state.selectionEpoch) {
    const current=()=>epoch===state.selectionEpoch&&state.selected==='ganjave';
    setStatus('Loading Ganjave graph and browser Python runtime…');
    const graphUrl=new URL('data/ganjave_fed_batch.json',document.baseURI);
    state.graph=await timedStage('Ganjave graph fetch and JSON parse',10000,async()=>{
      const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),9000);const started=performance.now();diagnostic('START fetch Ganjave graph',{url:graphUrl.href,timeoutMs:9000});
      try { const response=await fetch(graphUrl,{signal:controller.signal});const contentType=response.headers.get('content-type')||'';if(!response.ok)throw new Error(`HTTP ${response.status} ${contentType}`);const text=await response.text();diagnostic('SUCCESS fetch Ganjave graph',{url:graphUrl.href,status:response.status,contentType,bytes:new TextEncoder().encode(text).byteLength,elapsedMs:Math.round(performance.now()-started)});return JSON.parse(text); }
      catch(error){const detail=controller.signal.aborted?'Timed out after 9s':String(error?.message||error);diagnostic('FAIL fetch Ganjave graph',{url:graphUrl.href,elapsedMs:Math.round(performance.now()-started),error:detail,level:'error'});throw new Error(`Ganjave graph request failed: ${detail}`);}
      finally{clearTimeout(timer);}
    });
    if(!current())return;
    state.mode='pyodide';
    state.context={notes:state.graph.notes||'Scientific limitations are declared in the model contract and run diagnostics.'};
    $('execution-mode').hidden=true;$('execution-label').textContent='LOADING PYTHON RUNTIME';$('execution-description').textContent='Loading the local Python runtime and model contract. No trajectory is loaded until a browser-side run completes.';
    $('api-state').textContent='Loading Python/WebAssembly';$('footer-version').textContent='Pyodide 314.0.7 · client-side Python';$('model-tag').textContent='ganjave · 0.1.0';
    renderInputs();setStatus('Loading the Python/WebAssembly runtime and Ganjave model source…');
    const {PyodideGanjaveClient}=await timedStage('Pyodide client module import',10000,()=>import('./pyodide/client.mjs'));
    if(!current())return;
    state.executor=new PyodideGanjaveClient({onStatus:message=>{if(current())setStatus(message);},onDiagnostic:entry=>diagnostic(entry.message,{source:entry.source,...entry})});
    await state.executor.ready;
    if(!current())return;
    setStatus('Confirming the loaded Ganjave model registry…');
    const manifest=await timedStage('Ganjave registry manifest response',15000,()=>state.executor.manifest());
    if(!current())return;
    if(!manifest.ok) throw new Error(manifest.error||'The browser runtime could not load the Ganjave contract.');
    state.model={model_id:'ganjave',model_version:'0.1.0',manifest:manifest.manifest};
    $('execution-mode').hidden=false;$('execution-banner-title').textContent='PYTHON RUNTIME READY.';$('execution-banner-copy').textContent='Run the bundled Ganjave Python model locally in this browser. No stored trajectory is substituted when execution is unavailable.';$('execution-label').textContent='PYTHON RUNTIME READY';$('execution-description').textContent='The bundled Python model is ready to run in WebAssembly on this device. A trajectory appears only after the model returns a successful computation.';
    $('run-button').disabled=false;setStatus('Python/WebAssembly ready. Runs execute the bundled Ganjave model in this browser.');$('timeline-hint').textContent='Run the model to load its computed time axis';$('selected-model-title').textContent='Ganjave et al. · 2022';$('model-selector-status').textContent='Ganjave is the only interactive model execution in this browser build.';renderPanel('evidence');
  }
  async function boot() {
    setStatus('Loading registry-driven model catalogue…');
    setupTabs();setupOrbit();$('run-button').addEventListener('click',run);$('play-button').addEventListener('click',play);$('reset-button').addEventListener('click',()=>{stop();showPoint(0)});const retry=$('retry-api');if(retry)retry.addEventListener('click',()=>location.reload());
    $('timeline').addEventListener('input',e=>{stop();showPoint(Math.round(Number(e.target.value)/1000*(state.values.length-1)));});
    $('replay-timeline').addEventListener('input',drawReplay);
    $('model-selector').addEventListener('change',e=>selectModel(e.target.value));
    $('about-button').addEventListener('click',()=>{document.querySelector('[data-panel="models"]').click();document.querySelector('.control-column').scrollIntoView({behavior:'smooth',block:'start'});});
    state.catalogue=await fetchJsonAsset('data/model_catalog.json','Composition registry catalogue');
    if(state.catalogue.registry_issues?.length)throw new Error('The generated registry catalogue contains registry issues; refusing to present model capabilities.');
    state.models=state.catalogue.models;state.compatibility=state.catalogue.compatibility;
    const registered=state.catalogue.models.map(m=>`<option value="${esc(m.model_id)}">${esc(m.model_id)} · ${esc(m.browser_mode==='pyodide_live'?'live in-browser Python':m.browser_mode==='stored_evidence_replay'?'literature evidence replay':'registered · no browser runner')}</option>`).join('');
    const inspection=state.catalogue.inspection_only.map(m=>`<option value="${esc(m.model_id)}">${esc(m.model_id)} · inspection only (not registered)</option>`).join('');$('model-selector').innerHTML=registered+inspection;
    const requested=new URLSearchParams(location.search).get('model'),defaultId=state.catalogue.models.find(m=>m.browser_mode==='stored_evidence_replay')?.model_id||state.catalogue.models[0]?.model_id;
    const id=catalogEntry(requested)?requested:defaultId;await selectModel(id);
  }
  boot().catch(error=>{$('api-state').textContent='Browser Python unavailable';$('footer-version').textContent='No simulation result loaded';$('model-tag').textContent='Runtime unavailable';$('run-button').disabled=true;setStatus(`Application initialization failed: ${error.message}. No stored trajectory is shown as live.`, 'error');diagnostic('FAIL application initialization',{error:String(error?.stack||error),level:'error'});});
})();
