import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const app = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');

// Regression: the optional retry control is absent from index.html. An
// unconditional addEventListener used to throw before graph/runtime startup.
assert.doesNotMatch(html, /id=["']retry-api["']/);
assert.match(app, /const retry=\$\('retry-api'\);\s*if\(retry\)retry\.addEventListener/);
assert.match(app, /boot\(\)\.catch\(error=>/);

// Startup is stage-bounded and the graph request has an explicit abort path.
assert.match(app, /timedStage\('Ganjave graph fetch and JSON parse',10000/);
assert.match(app, /setTimeout\(\(\)=>controller\.abort\(\),9000\)/);
console.log('PASS — absent optional retry control cannot abort browser startup');
console.log('PASS — early graph fetch has an explicit 9s abort and 10s stage bound');
