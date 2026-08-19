import test from "node:test";
import assert from "node:assert/strict";
import {
  BLOCKED_LEGACY_FIELDS,
  VEIL_CANONICAL_COUNTS,
  VEIL_CANONICAL_GRID,
  cellIdFromRowCol,
  centerForCell,
  createVeilCanonicalResolver,
  rowColForPoint,
} from "./address-grid-core.mjs";

function fixtureCatalog() {
  const g = VEIL_CANONICAL_GRID;
  const membership = Buffer.alloc(g.rows * g.columns);

  // Exactly 120,662 valid synthetic centers so the canonical fail-closed
  // count gate is exercised. Real production membership comes only from the
  // SHA-fixed regional-catalog-v4 source.
  for (let i = 0; i < VEIL_CANONICAL_COUNTS.cellCount; i += 1) {
    membership[i] = 1;
  }

  const setMunicipality = (cellId, index) => {
    const match = /^g(\d+)-(\d+)$/.exec(cellId);
    const row = Number(match[1]);
    const col = Number(match[2]);
    membership[row * g.columns + col] = index;
  };

  setMunicipality("g194-226", 13); // Uehara 2 validation cell
  setMunicipality("g195-224", 13); // Uehara 3 validation cell
  setMunicipality("g169-281", 1);  // Ichibancho validation cell

  const municipalities = Array.from({ length: 48 }, (_, i) => ({
    index: i + 1,
    code: String(i + 1).padStart(5, "0"),
    name: `m${i + 1}`,
    cellCount: 0,
  }));
  municipalities[0] = { index: 1, code: "13101", name: "千代田区", cellCount: 1143 };
  municipalities[12] = { index: 13, code: "13113", name: "渋谷区", cellCount: 1516 };

  return {
    grid: { ...g },
    cellCount: VEIL_CANONICAL_COUNTS.cellCount,
    municipalityCount: VEIL_CANONICAL_COUNTS.municipalityCount,
    municipalities,
    data: {
      municipality: membership.toString("base64"),
      // Deliberate poison pills. The VEIL resolver must never expose/use these.
      originalScore: "DO_NOT_USE",
      labelCode: "DO_NOT_USE",
      confidence: "DO_NOT_USE",
    },
    labels: ["DO_NOT_USE"],
  };
}

test("cell center round-trips to canonical cell id", () => {
  const cellId = "g194-226";
  const center = centerForCell(cellId);
  assert.deepEqual(rowColForPoint(center.lat, center.lon), { row: 194, col: 226 });
  assert.equal(cellIdFromRowCol(194, 226), cellId);
});

test("off-center point uses nearest canonical center rather than floor partition", () => {
  const g = VEIL_CANONICAL_GRID;
  const rowFloat = 260.75;
  const colFloat = 22.25;
  const lat = g.originNorth - rowFloat * g.latitudeStep;
  const lon = g.originWest + colFloat * g.longitudeStep;

  // A floor-based shadow join would incorrectly assign g260-22. The canonical
  // grid stores cell centers, so the resolver must choose the nearest center.
  assert.deepEqual(rowColForPoint(lat, lon), { row: 261, col: 22 });
});

test("resolver returns only municipality/grid identity", () => {
  const resolver = createVeilCanonicalResolver(fixtureCatalog());
  const center = centerForCell("g194-226");
  const result = resolver.resolvePoint(center.lat, center.lon);

  assert.equal(result.status, "ok");
  assert.equal(result.cellId, "g194-226");
  assert.equal(result.municipality.code, "13113");
  const serialized = JSON.stringify(result);
  for (const key of BLOCKED_LEGACY_FIELDS) {
    assert.equal(serialized.includes(`"${key}"`), false, `leaked ${key}`);
  }
});

test("100/300/500 prefilter rings are monotonic and contain target cell", () => {
  const resolver = createVeilCanonicalResolver(fixtureCatalog());
  const center = centerForCell("g194-226");
  const rings = resolver.neighborhoodRings(center.lat, center.lon);

  assert.equal(rings["100"].some((x) => x.cellId === "g194-226"), true);
  assert.ok(rings["100"].length <= rings["300"].length);
  assert.ok(rings["300"].length <= rings["500"].length);
});

test("outside points fail closed", () => {
  const resolver = createVeilCanonicalResolver(fixtureCatalog());
  assert.deepEqual(resolver.resolvePoint(36.5, 140.5), { status: "outside_grid" });
});

test("catalog count mismatch is rejected", () => {
  const bad = fixtureCatalog();
  bad.cellCount -= 1;
  assert.throws(() => createVeilCanonicalResolver(bad), /cellCount mismatch/);
});
