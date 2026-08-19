import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import {
  VEIL_CANONICAL_SOURCE,
  loadVerifiedCanonicalCatalog,
  verifyCanonicalCatalogBuffer,
} from './canonical-catalog-contract.mjs';

const actualPath = process.env.VEIL_CANONICAL_CATALOG_PATH;

test('actual SHA-fixed canonical source passes full spatial contract', { skip: !actualPath }, async () => {
  const verified = await loadVerifiedCanonicalCatalog(actualPath);
  assert.equal(verified.sha256, VEIL_CANONICAL_SOURCE.sha256);
  assert.deepEqual(verified.regionCounts, VEIL_CANONICAL_SOURCE.regionCounts);
  assert.equal(verified.safeCatalog.cellCount, 120_662);
  assert.equal(verified.safeCatalog.municipalityCount, 48);
});

test('tampered bytes fail closed on SHA before use', async () => {
  if (!actualPath) return;
  const original = await readFile(actualPath);
  const tampered = Buffer.concat([original, Buffer.from('\n')]);
  assert.throws(() => verifyCanonicalCatalogBuffer(tampered), /canonical SHA-256 mismatch/);
});

test('safe catalog view does not expose legacy score arrays', { skip: !actualPath }, async () => {
  const verified = await loadVerifiedCanonicalCatalog(actualPath);
  const text = JSON.stringify(verified.safeCatalog);
  for (const forbidden of ['originalScore', 'originalFit', 'labelCode', 'confidence', 'ranking']) {
    assert.equal(text.includes(`"${forbidden}"`), false);
  }
});
