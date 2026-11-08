const STAGE_LIMITS_MS = {
  'Starting the browser Python worker': 15000,
  'Downloading Pyodide runtime assets': 90000,
  'Initializing Pyodide WebAssembly': 60000,
  'Loading bundled Python module': 15000,
  'Importing the Ganjave Python model and registry': 30000,
  'Ganjave Python runtime and model registry ready': 30000,
};

export class PyodideGanjaveClient {
  constructor({ timeoutMs = 180000, onStatus = () => {}, onDiagnostic = () => {} } = {}) {
    this.timeoutMs = timeoutMs;
    this.onStatus = onStatus;
    this.onDiagnostic = onDiagnostic;
    this.stage = 'Starting the browser Python worker';
    this.stageStarted = performance.now();
    this.worker = new Worker(new URL('./worker.mjs', import.meta.url), { type: 'module' });
    this.nextId = 1;
    this.pending = new Map();
    this.stopped = false;
    this.isReady = false;
    this.log(`START ${this.stage}`);
    this.ready = new Promise((resolve, reject) => {
      this.readyResolve = resolve;
      this.readyReject = reject;
    });
    this.overallTimer = setTimeout(() => this.failStage(`Overall startup safety limit reached after ${Math.round(this.timeoutMs / 1000)}s; the active stage was “${this.stage}”.`), this.timeoutMs);
    this.setStageTimer(this.stage);
    this.worker.addEventListener('message', (event) => this.onMessage(event.data));
    this.worker.addEventListener('error', (event) => {
      event.preventDefault();
      this.failStage(`Worker script error: ${event.message || 'unknown error'}${event.filename ? ` (${event.filename}:${event.lineno || 0}:${event.colno || 0})` : ''}`);
    });
    this.worker.addEventListener('messageerror', () => this.failStage('Worker message could not be decoded.'));
  }

  log(message) {
    this.onDiagnostic({ source: 'main', message, elapsedMs: Math.round(performance.now()) });
  }

  setStageTimer(stage) {
    clearTimeout(this.stageTimer);
    const key = Object.keys(STAGE_LIMITS_MS).find((candidate) => stage.startsWith(candidate));
    const limit = STAGE_LIMITS_MS[key] || 30000;
    this.stage = stage;
    this.stageStarted = performance.now();
    this.log(`START ${stage} (limit ${Math.round(limit / 1000)}s)`);
    this.onStatus(`${stage}…`);
    this.stageTimer = setTimeout(() => {
      this.failStage(`Timed out after ${Math.round(limit / 1000)}s in stage “${stage}”. Check the Network and Console evidence below.`);
    }, limit);
  }

  failStage(message) {
    if (this.stopped) return;
    const elapsed = Math.round(performance.now() - this.stageStarted);
    this.log(`FAIL ${this.stage} after ${elapsed}ms — ${message}`);
    this.onDiagnostic({ source: 'network', message: 'Resource timing snapshot follows.', resources: performance.getEntriesByType('resource').map((entry) => ({ name: entry.name, durationMs: Math.round(entry.duration), transferSize: entry.transferSize, encodedBodySize: entry.encodedBodySize, decodedBodySize: entry.decodedBodySize, initiatorType: entry.initiatorType })) });
    this.stop(new Error(`${message} No stored result is substituted.`));
  }

  onMessage(message) {
    if (message.type === 'diagnostic') {
      this.onDiagnostic(message.entry);
      return;
    }
    if (message.type === 'stage') {
      clearTimeout(this.stageTimer);
      this.log(`SUCCESS ${this.stage} (${Math.round(performance.now() - this.stageStarted)}ms)`);
      this.setStageTimer(message.stage || this.stage);
      return;
    }
    if (message.type === 'ready') {
      clearTimeout(this.stageTimer);
      clearTimeout(this.overallTimer);
      this.isReady = true;
      this.log(`SUCCESS ${this.stage} (${Math.round(performance.now() - this.stageStarted)}ms)`);
      this.readyResolve();
      return;
    }
    if (message.type === 'init_error') {
      this.failStage(message.error || 'Worker initialization failed.');
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pending.delete(message.id);
    if (message.error) pending.reject(new Error(message.error));
    else pending.resolve(message.result);
  }

  stop(error) {
    if (this.stopped) return;
    this.stopped = true;
    this.worker.terminate();
    clearTimeout(this.stageTimer);
    clearTimeout(this.overallTimer);
    this.readyReject(error);
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
      this.pending.delete(id);
    }
  }

  async request(body) {
    await this.ready;
    if (this.stopped) throw new Error('The browser Python worker has stopped. Reload the page to start a fresh run.');
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const limit = Math.min(this.timeoutMs, 120000);
      const timer = setTimeout(() => {
        this.stop(new Error(`Browser Python ${body.op || 'request'} timed out after ${Math.round(limit / 1000)}s during “${this.stage}”. No prior trajectory is reused.`));
      }, limit);
      this.pending.set(id, { resolve, reject, timer });
      this.worker.postMessage({ id, ...body });
    });
  }

  manifest() { return this.request({ op: 'manifest' }); }
  run(inputs, parameters) { return this.request({ op: 'run', inputs, parameters }); }
  close() { this.stop(new Error('Browser Python execution was stopped.')); }
}
