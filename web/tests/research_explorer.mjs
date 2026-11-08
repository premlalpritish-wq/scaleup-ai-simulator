#!/usr/bin/env node
/**
 * Browser acceptance test for the research explorer.
 *
 * Starts the real Python service, drives the real page in headless Chrome over
 * the DevTools protocol, runs an analysis through the form, checks the rendered
 * outputs and then checks a refusal. No stubs: the page talks to the Python
 * workflow.
 *
 *   node web/tests/research_explorer.mjs
 *
 * Environment:
 *   CHROME      path to a Chrome/Chromium binary (default: Windows Chrome path)
 *   PYTHON      interpreter used for `python -m api.app` (default: python)
 *   RESEARCH_PORT  port for the temporary service (default: 8123)
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const PORT = Number(process.env.RESEARCH_PORT || 8123);
const BASE = `http://127.0.0.1:${PORT}`;
const CHROME = process.env.CHROME
  || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PYTHON = process.env.PYTHON || 'python';

const checks = [];
const failures = [];
function check(condition, message) {
  checks.push(message);
  if (!condition) {
    failures.push(message);
    console.log(`FAIL: ${message}`);
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(label, fn, timeoutMs = 30000, intervalMs = 250) {
  const started = Date.now();
  let last;
  while (Date.now() - started < timeoutMs) {
    try {
      last = await fn();
      if (last) return last;
    } catch (error) {
      last = error;
    }
    await sleep(intervalMs);
  }
  throw new Error(`timed out waiting for ${label} (last: ${last})`);
}

class CDP {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 0;
    this.pending = new Map();
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.nextId;
    this.socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, 60000);
    });
  }
}

async function main() {
  if (!existsSync(CHROME)) {
    console.log(`Skipping browser run: no Chrome at ${CHROME}. Set CHROME to a binary.`);
    return 1;
  }
  check(true, `Chrome found at ${CHROME}`);

  const server = spawn(PYTHON, ['-m', 'api.app'], {
    cwd: ROOT,
    env: { ...process.env, PORT: String(PORT), HOST: '127.0.0.1' },
    stdio: 'ignore',
  });
  const profile = mkdtempSync(path.join(tmpdir(), 'scaleup-explorer-'));
  const chrome = spawn(CHROME, [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { stdio: 'ignore' });

  try {
    await waitFor('the Python service', async () => (await fetch(`${BASE}/api/health`)).ok, 30000);

    const portFile = path.join(profile, 'DevToolsActivePort');
    await waitFor('DevToolsActivePort', () => existsSync(portFile), 20000);
    const [debugPort] = readFileSync(portFile, 'utf8').split('\n');
    const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
    const target = targets.find((item) => item.type === 'page');
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve);
      socket.addEventListener('error', reject);
    });
    const cdp = new CDP(socket);
    const evaluate = async (expression) => {
      const { result, exceptionDetails } = await cdp.send('Runtime.evaluate', {
        expression, returnByValue: true, awaitPromise: true,
      });
      if (exceptionDetails) {
        throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
      }
      return result.value;
    };

    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url: `${BASE}/research/` });
    await waitFor('the case to render', async () =>
      (await evaluate("document.querySelector('#evidence-count')?.textContent || ''"))
        .includes('shown of'), 60000);

    const stats = await evaluate(
      "Array.from(document.querySelectorAll('#case-summary .stat')).map(s => [" +
      "s.querySelector('.n').textContent, s.querySelector('.k').textContent])");
    const hasStat = (value, label) => stats.some((pair) => pair[0] === value && pair[1] === label);
    check(hasStat('6', 'direct claims'), 'the case shows six direct claims');
    check(hasStat('17', 'analogue claims'), 'the case shows seventeen analogue claims');
    check(hasStat('no', 'target yield available'),
      'the case states that no target yield is available');
    check(await evaluate("document.querySelectorAll('#evidence-list .evidence').length") === 25,
      'all 25 claims are rendered');
    check(await evaluate("document.querySelectorAll('#evidence-list .evidence.direct').length") === 6,
      'direct evidence cards are marked as direct');
    check(await evaluate("document.querySelectorAll('#evidence-list .evidence.analogue').length") === 17,
      'analogue evidence cards are marked as analogous');
    check((await evaluate("document.querySelector('#evidence-list .evidence.analogue').textContent"))
      .includes('hypothesis'), 'analogue cards carry a hypothesis badge');
    check(await evaluate("document.querySelectorAll('#gap-list .gap').length") > 0,
      'the research gaps are rendered');
    check((await evaluate("document.querySelector('#service-text').textContent"))
      .includes('Quotes re-verified'), 'the page reports the quote re-check');

    await evaluate("document.querySelector('.chip[data-filter=\"analogue\"]').click()");
    check((await waitFor('the analogue filter', async () =>
      (await evaluate("document.querySelector('#evidence-count').textContent")))) === '17 shown of 25',
      'the class filter narrows the evidence list to analogous claims');
    await evaluate("document.querySelector('.chip[data-filter=\"all\"]').click()");


    // Run an analysis through the form.
    await evaluate(`(() => {
      const set = (id, value) => {
        const field = document.getElementById(id);
        field.value = value;
        field.dispatchEvent(new Event('input', { bubbles: true }));
      };
      set('f-organism', 'Carya illinoinensis');
      set('f-tissue', 'embryo');
      set('f-molecule', 'total RNA');
      set('f-method', 'TRIzol kit');
      set('f-observations', 'brown pellet after precipitation');
      set('f-problem', 'Extract high-quality total RNA from pecan (Carya illinoinensis) embryos for small RNA sequencing.');
      document.getElementById('run-button').click();
      return true;
    })()`);

    await waitFor('the analysis to finish', async () => {
      const state = await evaluate("document.getElementById('analysis-status').className");
      return state.includes('ok') || state.includes('error');
    }, 180000);

    const status = await evaluate("document.getElementById('analysis-status').textContent");
    check(status.includes('completed'), 'the analysis completed in the browser');
    check(await evaluate("document.getElementById('analysis-output').hidden") === false,
      'the computed-output panel is shown');
    check(await evaluate("document.getElementById('analysis-refusal').hidden") === true,
      'no refusal panel is shown for a pecan problem');
    const rows = await evaluate(
      "Array.from(document.querySelectorAll('#outputs-table tbody tr')).map(r => r.textContent.replace(/\\s+/g,' ').trim())");
    check(rows.length === 11, `eleven outputs are rendered (saw ${rows.length})`);
    check(rows.some((row) => row.startsWith('claim_count') && row.includes('25')),
      'the rendered claim_count is 25');
    check(rows.some((row) => row.startsWith('direct_target_claim_count') && row.includes('6')),
      'the rendered direct_target_claim_count is 6');
    check(rows.some((row) => row.startsWith('quantitative_yield_available_for_target') && row.includes('0')),
      'the rendered yield-availability output is 0');
    check(!rows.some((row) => /predicted_yield|degradation_rate|yield_ug|\brin\b/.test(row)),
      'no yield, RIN or degradation output is rendered');
    const input = await evaluate("document.getElementById('analysis-input').textContent");
    check(input.includes('brown pellet after precipitation'),
      'the observation is shown as recorded input');
    check(input.includes('Recorded, not used as evidence'),
      'the input panel separates what the workflow used from what it only recorded');
    check((await evaluate("document.getElementById('analysis-hypotheses').textContent"))
      .includes('not been validated'), 'the hypotheses are labelled as unvalidated');
    check(await evaluate("document.querySelectorAll('#analysis-artifacts a').length") > 0,
      'the run artifact links are shown');
    check(await evaluate("document.getElementById('run-report-link').hidden") === false,
      'the run report download is enabled');

    // A problem outside the corpus must be refused, with no result.
    await evaluate(`(() => {
      const set = (id, value) => { document.getElementById(id).value = value; };
      set('f-organism', 'Zea mays');
      set('f-tissue', 'leaf');
      set('f-problem', 'Extract total RNA from maize (Zea mays) leaves for RNA-seq.');
      document.getElementById('run-button').click();
      return true;
    })()`);
    await waitFor('the refusal', async () =>
      (await evaluate("document.getElementById('analysis-refusal').hidden")) === false, 180000);
    const refusal = await evaluate("document.getElementById('analysis-refusal').textContent");
    check(refusal.includes('No result was produced'), 'the refusal panel is shown');
    check(refusal.includes('Carya illinoinensis'),
      'the refusal explains which corpus is available');
    check(await evaluate("document.getElementById('analysis-output').hidden") === true,
      'no outputs are shown for a refused problem');
  } catch (error) {
    failures.push(String(error));
    console.log(`FAIL: ${error}`);
  } finally {
    chrome.kill();
    server.kill();
    await sleep(1500);
    try {
      rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    } catch (error) {
      // A still-closing Chrome can keep the profile locked on Windows; the
      // temporary directory is not part of the result.
    }
  }

  console.log(`\nRESEARCH EXPLORER BROWSER CHECKS: ${checks.length - failures.length} passed, ${failures.length} failed`);
  return failures.length ? 1 : 0;
}

process.exitCode = await main();

