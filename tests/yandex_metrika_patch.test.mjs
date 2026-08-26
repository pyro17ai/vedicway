import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeTotals,
  patchSource,
} from '../seo_agent/mcp/patch-yandex-metrika.mjs';

test('Metrika totals accept the documented flat response and the legacy nested shape', () => {
  assert.deepEqual(normalizeTotals([1, 2, 3]), [1, 2, 3]);
  assert.deepEqual(normalizeTotals([[1, 2, 3]]), [1, 2, 3]);
  assert.deepEqual(normalizeTotals(undefined), []);
});

test('the pinned package patch replaces both broken totals readers', () => {
  const source = [
    '  function getToken() {',
    'const metrics = data.totals?.[0] || [];',
    'const totals = data.totals?.[0] || [];',
  ].join('\n');
  const patched = patchSource(source);

  assert.doesNotMatch(patched, /data\.totals\?\.\[0\] \|\| \[\]/);
  assert.match(patched, /normalizeTotals\(data\.totals\)/);
});
