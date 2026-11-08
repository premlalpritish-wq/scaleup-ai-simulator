/* ScaleUp research explorer — a reader of the existing Python workflow.
 *
 * There is no scientific logic in this file. It fetches the pecan case, renders
 * the evidence and gaps it receives, posts the researcher's protocol to the
 * service, and renders whatever the real workflow returned. When the service is
 * absent, it says so and shows nothing.
 */
(() => {
  'use strict';

  const configured = String(window.SCALEUP_RESEARCH_API_BASE || '').replace(/\/$/, '');
  let insecure = false;
  if (configured) {
    try {
      insecure = location.protocol === 'https:' && new URL(configured).protocol !== 'https:';
    } catch (error) {
      insecure = true;
    }
  }
  const API = insecure ? '' : configured;
  if (insecure) {
    document.getElementById('service-text').textContent =
      'This page is served over HTTPS but the configured API is not, so the configured ' +
      'origin will not be used. No analysis can run until config.js points at an HTTPS service.';
  }
  const $ = (id) => document.getElementById(id);
  const state = { case: null, analysis: null, filter: 'all', busy: false };

  const apiUrl = (path) => `${API}${path}`;
  const asText = (value) => (value === null || value === undefined ? '' : String(value));

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : String(value));
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function badge(kind, label) {
    return el('span', { class: `badge ${kind}`.trim() }, label);
  }

  function stat(value, key, cls) {
    return el('div', { class: `stat ${cls || ''}`.trim() },
      el('span', { class: 'n' }, value === null || value === undefined ? '—' : String(value)),
      el('span', { class: 'k' }, key));
  }

  function yesNo(value) {
    return value === true ? 'yes' : value === false ? 'no' : '—';
  }

  function num(value) {
    if (value === null || value === undefined || value === '') return '—';
    const parsed = Number(value);
    return Number.isFinite(parsed)
      ? parsed.toLocaleString(undefined, { maximumFractionDigits: 4 })
      : String(value);
  }

  async function api(path, options) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120000);
    let response;
    try {
      response = await fetch(apiUrl(path), {
        ...options,
        signal: controller.signal,
        mode: API ? 'cors' : 'same-origin',
      });
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error('The service did not respond within 120 seconds. No result is shown; nothing was substituted.');
      }
      throw new Error(`Could not reach the Python service (${error.message || 'network error'}). This page cannot run the workflow without it.`);
    } finally {
      clearTimeout(timer);
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = body?.error?.message || `Request failed (${response.status})`;
      const failure = new Error(message);
      failure.body = body;
      failure.status = response.status;
      throw failure;
    }
    return body;
  }

  function setService(kind, message) {
    const dot = document.querySelector('#service-state .dot');
    if (dot) dot.className = `dot ${kind}`;
    $('service-text').textContent = message;
  }

  // ------------------------------------------------------------------ case

  function renderProblem(problem, origin) {
    const box = $('overview-problem');
    clear(box);
    box.append(el('h3', {}, 'Problem specification'));
    box.append(el('p', { class: 'claim' }, asText(problem.question) || '(no problem statement recorded)'));
    const rows = el('dl', { class: 'meta' });
    for (const [label, tracked] of [
      ['Organism', problem.organism],
      ['Material', problem.tissue],
      ['Target molecule', problem.molecule],
    ]) {
      const value = tracked?.value ?? null;
      rows.append(el('div', {},
        el('strong', {}, label + ': '),
        value === null ? '(unknown)' : String(value),
        tracked?.state ? ` — ${tracked.state}` : ''));
    }
    rows.append(el('div', {}, el('strong', {}, 'Problem id: '), asText(problem.problem_id)));
    rows.append(el('div', {}, el('strong', {}, 'Read from: '), origin));
    if ((problem.downstream || []).length) {
      rows.append(el('div', {}, el('strong', {}, 'Downstream: '), problem.downstream.join(', ')));
    }
    if ((problem.constraints || []).length) {
      rows.append(el('div', {}, el('strong', {}, 'Constraints: '), problem.constraints.join(', ')));
    }
    if ((problem.unknowns || []).length) {
      rows.append(el('div', {}, el('strong', {}, 'Unknown at ingestion: '), problem.unknowns.join(', ')));
    }
    box.append(rows);
  }

  function renderSummary(target, summary) {
    clear(target);
    target.append(
      stat(summary.direct_claims, 'direct claims', 'good'),
      stat(summary.analogue_claims, 'analogue claims', 'warn'),
      stat(summary.method_review_claims, 'method-review claims'),
      stat(summary.step_count, 'protocol steps'),
      stat(summary.unresolved_parameter_count, 'unresolved parameters', 'warn'),
      stat(summary.reported_parameter_count, 'reported parameters'),
      stat(yesNo(summary.protocol_complete_for_target), 'target protocol complete'),
      stat(yesNo(summary.quantitative_yield_available_for_target), 'target yield available', 'bad'),
    );
  }

  function renderSources(sources) {
    const body = document.querySelector('#sources-table tbody');
    clear(body);
    for (const source of sources) {
      const title = el('div', {}, el('strong', {}, asText(source.title) || asText(source.source_id)));
      title.append(el('div', { class: 'muted small' },
        `${asText(source.journal)} ${asText(source.year)} · ${asText(source.license)}`));
      const roleClass = source.role === 'target_organism'
        ? 'direct'
        : source.role === 'analogous_protocol' ? 'analogue' : 'method_review';
      body.append(el('tr', {},
        el('td', {}, title),
        el('td', {}, badge(roleClass, asText(source.role))),
        el('td', {}, asText(source.doi)),
        el('td', {}, asText(source.pmcid)),
        el('td', {}, asText(source.extraction_method))));
    }
  }

  function renderLists(caseData) {
    const capabilities = $('capabilities');
    const limitations = $('limitations');
    clear(capabilities);
    clear(limitations);
    for (const item of caseData.capabilities || []) capabilities.append(el('li', {}, item));
    for (const item of caseData.limitations || []) limitations.append(el('li', {}, item));
  }


  // -------------------------------------------------------------- evidence

  function evidenceCard(claim) {
    const card = el('article', { class: `evidence ${claim.evidence_class}`, id: `claim-${claim.claim_id}` });
    const classLabel = claim.evidence_class === 'direct'
      ? 'direct evidence'
      : claim.evidence_class === 'analogue' ? 'analogous species' : 'method review';
    card.append(el('div', { class: 'badges' },
      badge(claim.evidence_class, classLabel),
      badge('', claim.claim_type),
      claim.hypothesis ? badge('hypothesis', 'hypothesis — not validated on pecan') : null));
    card.append(el('p', { class: 'claim' }, asText(claim.claim_text) || asText(claim.claim_id)));
    card.append(el('blockquote', {}, asText(claim.quote)));

    const source = claim.source || {};
    const meta = el('div', { class: 'meta' });
    const sourceCell = el('div', {}, el('strong', {}, 'Source: '));
    if (source.url) {
      sourceCell.append(el('a', { href: source.url, target: '_blank', rel: 'noopener noreferrer' }, asText(source.title)));
    } else {
      sourceCell.append(asText(source.title));
    }
    meta.append(sourceCell);
    meta.append(el('div', {}, el('strong', {}, 'DOI: '), asText(source.doi) || '—'));
    meta.append(el('div', {}, el('strong', {}, 'PMCID: '), asText(source.pmcid) || '—'));
    meta.append(el('div', {}, el('strong', {}, 'Organism: '), asText(claim.organism) || '—'));
    meta.append(el('div', {}, el('strong', {}, 'Section: '), asText(claim.section) || '—'));
    meta.append(el('div', {}, el('strong', {}, 'Step: '),
      `${asText(claim.supports_step)}${claim.step_label ? ' — ' + claim.step_label : ''}`));
    if (claim.value !== null && claim.value !== undefined) {
      meta.append(el('div', {}, el('strong', {}, 'Reported value: '), `${num(claim.value)} ${asText(claim.unit)}`));
    }
    if (claim.uncertainty) {
      meta.append(el('div', {}, el('strong', {}, 'Uncertainty: '), claim.uncertainty));
    }
    const locator = claim.locator || {};
    meta.append(el('div', {}, el('strong', {}, 'Verified at offsets: '),
      `${num(locator.start)}–${num(locator.end)}`));
    card.append(meta);
    return card;
  }

  function renderEvidence() {
    if (!state.case) return;
    const list = $('evidence-list');
    clear(list);
    const all = state.case.claims || [];
    const claims = all.filter((claim) => state.filter === 'all' || claim.evidence_class === state.filter);
    $('evidence-count').textContent = `${claims.length} shown of ${all.length}`;
    if (!claims.length) {
      list.append(el('p', { class: 'muted' }, 'No claim of this class is present in the case.'));
      return;
    }
    for (const claim of claims) list.append(evidenceCard(claim));
  }

  // ------------------------------------------------------------------ gaps

  function gapCard(gap) {
    const card = el('article', { class: 'gap', id: `gap-${gap.gap_id}` });
    card.append(el('h4', {}, `${asText(gap.step_label)} — ${asText(gap.parameter)}`));
    card.append(el('div', { class: 'badges' },
      badge('', gap.class === 'unresolved_parameter' ? 'unresolved parameter' : 'open question'),
      badge(gap.evidence_class === 'direct' ? 'direct' : 'analogue',
        gap.evidence_class === 'direct' ? 'step is direct evidence' : 'step is a hypothesis'),
      badge('', asText(gap.evidence_status))));
    card.append(el('p', { class: 'why' }, asText(gap.why)));
    card.append(el('p', { class: 'muted small' },
      `Evidence for the step: ${(gap.source_ids || []).join(', ') || 'none'}; ` +
      `${(gap.claim_ids || []).length} claim(s). ${asText(gap.basis)}`));
    if ((gap.hypothesis_references || []).length) {
      const refs = el('ul', { class: 'refs' }, el('li', {}, 'Analogous values exist, as hypotheses only:'));
      for (const reference of gap.hypothesis_references) {
        refs.append(el('li', {},
          `${asText(reference.step_label)}: ${num(reference.value)} ${asText(reference.unit)} ` +
          `(from ${(reference.source_ids || []).join(', ')})`));
      }
      card.append(refs);
    } else {
      card.append(el('p', { class: 'muted small' }, 'No analogue value is available either.'));
    }
    return card;
  }

  function renderGaps() {
    if (!state.case) return;
    const list = $('gap-list');
    clear(list);
    const gaps = state.case.gaps || [];
    const summary = $('gap-summary');
    clear(summary);
    summary.append(
      stat(gaps.filter((gap) => gap.class === 'unresolved_parameter').length, 'unresolved parameters', 'warn'),
      stat(gaps.filter((gap) => gap.class === 'open_question').length, 'open questions'),
      stat(gaps.filter((gap) => (gap.hypothesis_references || []).length).length, 'gaps with an analogue value', 'warn'),
      stat(gaps.length, 'total gaps'),
    );
    for (const gap of gaps) list.append(gapCard(gap));
  }


  // -------------------------------------------------------------- analysis

  const SAMPLE = {
    organism: 'Carya illinoinensis',
    tissue: 'embryo',
    molecule: 'total RNA',
    downstream: 'small RNA sequencing, transcriptome sequencing',
    problem: 'Extract high-quality total RNA from pecan (Carya illinoinensis) embryos for small RNA and transcriptome sequencing. Pecan embryos are oil-rich and polyphenol-rich, and the tissue is recalcitrant to standard extraction.',
    extraction_method: 'TRIzol kit, manufacturer protocol followed',
    constraints: 'recalcitrant tissue, polyphenol-rich, high quality',
    details: '',
    observations: '',
  };

  function setFormStatus(message, kind) {
    const node = $('form-status');
    node.textContent = message || '';
    node.className = `form-status ${kind || ''}`.trim();
  }

  function setAnalysisStatus(message, kind) {
    const node = $('analysis-status');
    node.textContent = message;
    node.className = `analysis-status ${kind || ''}`.trim();
  }

  function readForm() {
    const read = (id) => ($(id).value || '').trim();
    return {
      organism: read('f-organism'),
      tissue: read('f-tissue'),
      molecule: read('f-molecule'),
      downstream: read('f-downstream'),
      problem: read('f-problem'),
      extraction_method: read('f-method'),
      constraints: read('f-constraints'),
      details: read('f-details'),
      observations: read('f-observations'),
    };
  }

  function fillForm(values) {
    $('f-organism').value = values.organism || '';
    $('f-tissue').value = values.tissue || '';
    $('f-molecule').value = values.molecule || '';
    $('f-downstream').value = values.downstream || '';
    $('f-problem').value = values.problem || '';
    $('f-method').value = values.extraction_method || '';
    $('f-constraints').value = values.constraints || '';
    $('f-details').value = values.details || '';
    $('f-observations').value = values.observations || '';
  }

  function renderInput(target, input) {
    clear(target);
    const used = input?.used || {};
    const recorded = input?.recorded_not_used || {};
    target.append(el('p', { class: 'muted small' },
      'Everything below is what you submitted. The first list became the problem specification; the second was recorded in the report only.'));
    target.append(el('h4', {}, 'Used by the workflow'));
    const usedList = el('ul');
    for (const [key, value] of Object.entries(used)) {
      if (value === '' || value === null || (Array.isArray(value) && !value.length)) continue;
      usedList.append(el('li', {}, el('strong', {}, key.replace(/_/g, ' ') + ': '),
        Array.isArray(value) ? value.join(', ') : String(value)));
    }
    target.append(usedList.children.length
      ? usedList
      : el('p', { class: 'muted small' }, 'Nothing discrete was supplied; the workflow read the problem statement.'));
    target.append(el('h4', {}, 'Recorded, not used as evidence'));
    const recordedList = el('ul');
    for (const [key, value] of Object.entries(recorded)) {
      recordedList.append(el('li', {}, el('strong', {}, key.replace(/_/g, ' ') + ': '), String(value)));
    }
    target.append(recordedList.children.length
      ? recordedList
      : el('p', { class: 'muted small' }, 'No extra context was supplied.'));
  }

  function renderDiagnostics(target, diagnostics) {
    clear(target);
    if (!diagnostics || !diagnostics.length) {
      target.append(el('li', {}, 'No diagnostic was recorded.'));
      return;
    }
    for (const diagnostic of diagnostics) {
      target.append(el('li', {},
        el('strong', {}, `[${asText(diagnostic.severity)}] ${asText(diagnostic.code)}: `),
        asText(diagnostic.message)));
    }
  }

  function renderArtifacts(target, artifacts) {
    clear(target);
    const entries = Object.entries(artifacts || {});
    if (!entries.length) {
      target.append(el('p', { class: 'muted' }, 'No artifact was written for this run.'));
      return;
    }
    for (const [name, url] of entries) {
      target.append(el('a', { href: apiUrl(url), download: `${name}.json`, rel: 'noopener' }, name));
    }
  }


  function renderCompleted(payload) {
    const result = payload.result;
    const body = document.querySelector('#outputs-table tbody');
    clear(body);
    for (const output of result.execution?.outputs || []) {
      body.append(el('tr', {},
        el('td', {}, asText(output.port_id)),
        el('td', {}, num(output.value)),
        el('td', {}, asText(output.unit)),
        el('td', { class: 'muted small' }, asText(output.method))));
    }
    renderSummary($('analysis-summary'), result.summary || {});
    const hypotheses = $('analysis-hypotheses');
    clear(hypotheses);
    if (!(result.hypotheses || []).length) {
      hypotheses.append(el('li', { class: 'muted' }, 'No hypothesis was recorded.'));
    }
    for (const hypothesis of result.hypotheses || []) hypotheses.append(el('li', {}, hypothesis));
    renderInput($('analysis-input'), payload.input);
    renderDiagnostics($('analysis-diagnostics'), payload.diagnostics);
    renderArtifacts($('analysis-artifacts'), result.artifacts);

    const link = $('run-report-link');
    link.href = apiUrl(`/api/research/runs/${payload.analysis_id}/report.md`);
    link.hidden = false;

    setAnalysisStatus(
      `Analysis ${payload.analysis_id} completed. The workflow ran and its model executed ` +
      'through the composition engine. The outputs above are its computed values; the ' +
      'hypotheses below are not pecan measurements.',
      'ok');
  }

  function renderRefusal(payload) {
    $('refusal-message').textContent = asText(payload.message) || 'No result was produced.';
    const applicability = payload.applicability || {};
    $('refusal-note').textContent = [applicability.reason, applicability.note].filter(Boolean).join(' ');
    renderDiagnostics($('refusal-diagnostics'), payload.diagnostics);
    $('run-report-link').hidden = true;
    setAnalysisStatus(
      applicability.applicable === false
        ? 'The workflow refused this problem. Nothing was simulated and no result is available.'
        : 'The workflow ran but its model execution failed. No output is available.',
      'error');
  }

  function renderAnalysis(payload) {
    state.analysis = payload;
    const completed = payload.status === 'completed' && Boolean(payload.result);
    $('analysis-output').hidden = !completed;
    $('analysis-refusal').hidden = completed;
    if (completed) renderCompleted(payload);
    else renderRefusal(payload);
    $('analysis').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function onRun(event) {
    event.preventDefault();
    if (state.busy) return;
    const body = readForm();
    if (!body.problem) {
      setFormStatus('Describe the current problem first. An empty problem statement is not a request.', 'error');
      $('f-problem').focus();
      return;
    }
    state.busy = true;
    const button = $('run-button');
    button.disabled = true;
    setFormStatus('Sending the problem to the Python service…');
    setAnalysisStatus(
      'Running the research workflow (problem → literature → verified claims → model → engine)…',
      'busy');
    try {
      const payload = await api('/api/research/analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setFormStatus('The workflow returned a result. See section 5.', 'ok');
      renderAnalysis(payload);
    } catch (error) {
      if (error.status === 422 && error.body && error.body.status) {
        setFormStatus('The workflow refused or failed. The reason is in section 5.', 'error');
        renderAnalysis(error.body);
      } else {
        setFormStatus(error.message, 'error');
        setAnalysisStatus(error.message, 'error');
      }
    } finally {
      state.busy = false;
      button.disabled = false;
    }
  }

  async function onFeedback(event) {
    event.preventDefault();
    const status = $('feedback-status');
    const message = ($('f-feedback').value || '').trim();
    if (message.length < 10) {
      status.textContent = 'Write at least a sentence of feedback.';
      status.className = 'form-status error';
      $('f-feedback').focus();
      return;
    }
    status.textContent = 'Sending…';
    status.className = 'form-status';
    try {
      const payload = await api('/api/research/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          role: ($('f-role').value || '').trim(),
          case_id: 'pecan_rna_extraction',
          analysis_id: state.analysis?.analysis_id || '',
        }),
      });
      status.textContent = payload.note || 'Feedback received.';
      status.className = `form-status ${payload.persisted ? 'ok' : ''}`.trim();
    } catch (error) {
      status.textContent = error.message;
      status.className = 'form-status error';
    }
  }


  // ------------------------------------------------------------------- boot

  function showCaseFailure(error) {
    setService('error', error.message);
    const box = $('overview-problem');
    clear(box);
    box.append(el('h3', {}, 'The pecan case could not be loaded'));
    box.append(el('p', {}, error.message));
    const help = el('p', { class: 'muted' },
      'This page is static HTML; it reads the case and runs the workflow through the Python ' +
      'service. Deploy ');
    help.append(el('code', {}, 'api/Dockerfile'));
    help.append(document.createTextNode(
      ' as a Python web service (that service serves /research/ itself), or set '));
    help.append(el('code', {}, 'window.SCALEUP_RESEARCH_API_BASE'));
    help.append(document.createTextNode(
      ' in config.js to that service. No sample evidence or results are shown in its place.'));
    box.append(help);
    clear($('case-summary'));
    const evidence = $('evidence-list');
    clear(evidence);
    evidence.append(el('p', { class: 'muted' }, 'Evidence is unavailable until the service answers.'));
    const gaps = $('gap-list');
    clear(gaps);
    gaps.append(el('p', { class: 'muted' }, 'Gaps are unavailable until the service answers.'));
    clear($('capabilities'));
    clear($('limitations'));
    setAnalysisStatus(
      'No analysis can run: the Python service is not reachable from this page.',
      'error');
    $('run-button').disabled = true;
  }

  async function loadCase() {
    setService('pending', 'Connecting to the Python service…');
    try {
      const caseData = await api('/api/research/case');
      state.case = caseData;
      renderProblem(caseData.problem || {}, caseData.origin || '');
      renderSummary($('case-summary'), caseData.summary || {});
      renderLists(caseData);
      renderSources(caseData.sources || []);
      renderEvidence();
      renderGaps();
      const recheck = caseData.verification?.quote_recheck || {};
      setService('ok',
        `Connected. Case read from ${caseData.origin}. Quotes re-verified: ` +
        `${recheck.checked ?? '?'} checked, ${recheck.failed ?? '?'} failed.`);
      $('case-report-link').href = apiUrl('/api/research/case/report.md');
    } catch (error) {
      showCaseFailure(error);
    }
  }

  function wire() {
    $('protocol-form').addEventListener('submit', onRun);
    $('sample-button').addEventListener('click', () => {
      fillForm(SAMPLE);
      setFormStatus('The shipped pecan example is loaded. Press Run analysis.', 'ok');
    });
    $('reset-button').addEventListener('click', () => {
      fillForm({});
      setFormStatus('');
      setAnalysisStatus('No analysis has run in this session.');
      $('analysis-output').hidden = true;
      $('analysis-refusal').hidden = true;
      $('run-report-link').hidden = true;
    });
    $('feedback-form').addEventListener('submit', onFeedback);
    $('print-button').addEventListener('click', () => window.print());
    for (const chip of document.querySelectorAll('.chip[data-filter]')) {
      chip.addEventListener('click', () => {
        state.filter = chip.dataset.filter;
        for (const other of document.querySelectorAll('.chip[data-filter]')) {
          const active = other === chip;
          other.classList.toggle('active', active);
          other.setAttribute('aria-pressed', String(active));
        }
        renderEvidence();
      });
    }
  }

  wire();
  if (insecure) {
    showCaseFailure(new Error(
      'This page is served over HTTPS, but config.js points at a non-HTTPS API origin. ' +
      'That origin was not used, so the case cannot be read and no analysis can run.'));
  } else {
    loadCase();
  }
})();

