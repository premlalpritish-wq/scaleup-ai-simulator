import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const workerPath = path.join(webRoot, 'pyodide', 'worker.mjs');
const workerSource = await readFile(workerPath, 'utf8');
const manifestMatch = workerSource.match(/const BUNDLED_PYTHON_FILES\s*=\s*\[([\s\S]*?)\n\];/);
assert.ok(manifestMatch, 'worker bundle manifest must exist');
const manifest = [...manifestMatch[1].matchAll(/\{\s*urlPath:\s*'([^']+)',\s*runtimePath:\s*'([^']+)'\s*\}/g)]
  .map((match) => ({ urlPath: match[1], runtimePath: match[2] }));
assert.equal(manifest.length, 17, 'the worker must declare exactly 17 bundled files');
assert.match(workerSource, /new URL\(urlPath, import\.meta\.url\)/, 'asset URLs must resolve relative to pyodide/worker.mjs');
assert.match(workerSource, /`\/scaleup\/\$\{runtimePath\}`/, 'fetched files must be written under the declared /scaleup runtime layout');
assert.equal(new Set(manifest.map((entry) => entry.urlPath)).size, 17, 'bundle URL paths must be unique');
assert.equal(new Set(manifest.map((entry) => entry.runtimePath)).size, 17, 'Pyodide runtime paths must be unique');
for (const { urlPath, runtimePath } of manifest) {
  const expectedUrlPath = runtimePath.startsWith('runner/') ? runtimePath : `model/${runtimePath}`;
  assert.equal(urlPath, expectedUrlPath, `${runtimePath} must map from its actual bundle directory`);
}
const fetchIndex = workerSource.indexOf('await boundedFetch(url, urlPath)');
const writeIndex = workerSource.indexOf('pyodide.FS.writeFile(target, bytes)');
const importIndex = workerSource.indexOf('pyodide.runPython(`');
assert.ok(fetchIndex >= 0 && fetchIndex < writeIndex && writeIndex < importIndex, 'every asset must be fetched and written before Python imports run');

const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const target = path.resolve(webRoot, `.${pathname}`);
    assert.ok(target.startsWith(`${webRoot}${path.sep}`), 'request must stay within web root');
    const bytes = await readFile(target);
    response.writeHead(200, { 'Content-Type': target.endsWith('.json') ? 'application/json' : 'text/plain; charset=utf-8' });
    response.end(bytes);
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><title>Not Found</title>');
  }
});

await new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(0, '127.0.0.1', resolve);
});
try {
  const { port } = server.address();
  const workerUrl = `http://127.0.0.1:${port}/pyodide/worker.mjs`;
  for (const { urlPath, runtimePath } of manifest) {
    const requestUrl = new URL(urlPath, workerUrl);
    const expectedUrlPath = `/pyodide/${urlPath}`;
    assert.equal(requestUrl.pathname, expectedUrlPath, `${urlPath} resolves from the worker directory`);

    const sourceFile = path.join(webRoot, 'pyodide', ...urlPath.split('/'));
    const sourceStat = await stat(sourceFile);
    assert.ok(sourceStat.isFile(), `manifest source exists: ${sourceFile}`);
    const response = await fetch(requestUrl);
    assert.equal(response.status, 200, `${requestUrl} must be served successfully`);
    const contentType = response.headers.get('content-type') || '';
    const bytes = new Uint8Array(await response.arrayBuffer());
    assert.ok(bytes.byteLength > 0, `${urlPath} response must not be empty`);
    assert.equal(Buffer.compare(Buffer.from(bytes), await readFile(sourceFile)), 0, `${urlPath} response must match the bundled file`);
    if (urlPath.endsWith('.py')) {
      assert.match(contentType, /text\/plain/, `${urlPath} must be served as source text`);
      assert.doesNotMatch(Buffer.from(bytes).toString('utf8'), /^\s*<!doctype html/i, `${urlPath} must not be an HTML 404 page`);
    } else {
      assert.match(contentType, /application\/json/, `${urlPath} must be served as JSON`);
      assert.doesNotThrow(() => JSON.parse(Buffer.from(bytes).toString('utf8')), `${urlPath} must contain valid JSON`);
    }
    const expectedRuntimePath = `/scaleup/${runtimePath}`;
    assert.ok(expectedRuntimePath.startsWith('/scaleup/'), `${runtimePath} must be written beneath /scaleup`);
    console.log(`PASS ${requestUrl.pathname} → HTTP 200 ${contentType} ${bytes.byteLength} bytes → ${expectedRuntimePath}`);
  }
} finally {
  await new Promise((resolve) => server.close(resolve));
}
console.log('PASS — all 17 worker manifest entries exist, map to the worker-relative URL, and return the intended bundle bytes');
