import test from "node:test";
import assert from "node:assert/strict";
import {
  VEIL_CANONICAL_SOURCE,
  loadVeilCanonicalCatalogFromFile,
} from "./canonical-catalog-loader.mjs";
import {
  centerForCell,
  createVeilCanonicalResolver,
} from "./address-grid-core.mjs";

const livePath = process.env.VEIL_CANONICAL_CATALOG_PATH;

test("SHA-fixed Drive canonical catalog projects to VEIL-safe spatial-only input", { skip: !livePath }, async () => {
  const loaded = await loadVeilCanonicalCatalogFromFile(livePath);
  assert.equal(loaded.integrity.sha256, VEIL_CANONICAL_SOURCE.sha256);
  assert.equal(loaded.catalog.cellCount, 120_662);
  assert.equal(loaded.catalog.municipalityCount, 48);
  assert.equal(loaded.catalog.municipalities.length, 48);
  assert.deepEqual(Object.keys(loaded.catalog.data), ["municipality"]);
  assert.deepEqual(Object.keys(loaded.catalog).sort(), [
    "cellCount", "data", "grid", "municipalities", "municipalityCount",
  ]);

  const text = JSON.stringify(loaded.catalog);
  for (const forbidden of [
    "originalScore", "originalFit", "labelCode", "confidence", "highEvidence",
    "lowEvidence", "ordinaryEvidence", "detailScore", "neighborhoodScore", "labels",
  ]) {
    assert.equal(text.includes(`"${forbidden}"`), false, `retained ${forbidden}`);
  }

  const regionCounts = {
    tokyo23: loaded.catalog.municipalities.slice(0, 23).reduce((n, m) => n + m.cellCount, 0),
    yokohama: loaded.catalog.municipalities.slice(23, 41).reduce((n, m) => n + m.cellCount, 0),
    kawasaki: loaded.catalog.municipalities.slice(41, 48).reduce((n, m) => n + m.cellCount, 0),
  };
  assert.deepEqual(regionCounts, VEIL_CANONICAL_SOURCE.regionCounts);

  const resolver = createVeilCanonicalResolver(loaded.catalog);
  for (const cellId of [
    "g194-226", "g195-224", "g199-227", "g187-221", "g233-217",
    "g188-216", "g199-219", "g239-220", "g244-243", "g169-281",
  ]) {
    const center = centerForCell(cellId);
    const resolved = resolver.resolvePoint(center.lat, center.lon);
    assert.equal(resolved.status, "ok", `${cellId} should be canonical`);
    assert.equal(resolved.cellId, cellId);
  }
});
