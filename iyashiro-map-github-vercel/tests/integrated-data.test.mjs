import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  classifyIntegratedHardGate,
  classifyIntegratedThreshold,
} from "../app/lib/integrated-data/threshold.mjs";
import { RowPromiseLruCache } from "../app/lib/integrated-data/row-cache.mjs";

const root = new URL("../public/data/integrated/", import.meta.url);

async function readJson(relativePath) {
  return JSON.parse(await readFile(new URL(relativePath, root), "utf8"));
}

function findCell(row, cellId) {
  return row.cells.find((cell) => cell[0] === cellId) ?? null;
}

test("integrated release has exact R3 and ORBIT coverage", async () => {
  const manifest = await readJson("release-manifest.json");
  const schema = await readJson("schema.json");

  assert.equal(manifest.schemaVersion, "iyashiro-integrated-data/1.0");
  assert.equal(manifest.releaseId, "iyashiro-r3-orbit-v2-20260823");
  assert.equal(manifest.qa.status, "PASS");
  assert.equal(manifest.sources.length, 3);
  for (const source of manifest.sources) {
    assert.match(source.pointer, /^source:\/\//);
    assert.doesNotMatch(source.pointer, /^[A-Za-z]:[\\/]/);
  }
  assert.equal(manifest.coverage.totalCells, 120662);
  assert.equal(manifest.coverage.validCells, 120662);
  assert.equal(manifest.coverage.integratedCells, 120662);
  assert.equal(manifest.coverage.r3LensCells, 84060);
  assert.equal(manifest.coverage.r3PassLensCells, 20118);
  assert.equal(manifest.coverage.r3NoLensCells, 36602);
  assert.equal(manifest.coverage.orbitDistanceRows, 482648);
  assert.equal(manifest.coverage.canonicalFacilities, 31544);
  assert.equal(manifest.coverage.missingDistances, 0);
  assert.equal(manifest.coverage.missingFacilityReferences, 0);
  assert.equal(manifest.outputs.rowShardCount, 624);
  assert.equal(manifest.outputs.rowShards.length, 624);
  assert.equal(manifest.outputs.facilityShardCount, 16);
  assert.equal(manifest.qa.allGridRowsMaterialized, true);
  assert.deepEqual(
    manifest.outputs.rowShards.map((artifact) => artifact.path),
    Array.from(
      { length: 624 },
      (_, gridRow) =>
        "rows/g" + gridRow.toString().padStart(3, "0") + ".json",
    ),
  );
  assert.equal(schema.semantics.unknownIsSafe, false);
  assert.equal(schema.semantics.shrine, "context_only");
  assert.equal(schema.semantics.generalHospital, "excluded_from_ranking");
});

test("all row shards independently sum to the frozen universe", async () => {
  const manifest = await readJson("release-manifest.json");
  let cells = 0;
  let lensCells = 0;
  let passCells = 0;
  const seen = new Set();

  for (const artifact of manifest.outputs.rowShards) {
    const row = await readJson(artifact.path);
    assert.equal(row.schemaVersion, manifest.schemaVersion);
    assert.equal(row.releaseId, manifest.releaseId);
    let priorColumn = -1;
    for (const cell of row.cells) {
      assert.equal(cell.length, 10);
      assert.equal(typeof cell[0], "string");
      assert.ok(cell[1] > priorColumn);
      priorColumn = cell[1];
      assert.equal(seen.has(cell[0]), false);
      seen.add(cell[0]);
      for (const distanceIndex of [5, 6, 7, 8]) {
        assert.equal(cell[distanceIndex].length, 8);
        assert.equal(typeof cell[distanceIndex][0], "number");
        assert.equal(typeof cell[distanceIndex][1], "string");
      }
      cells += 1;
      if (cell[9] !== null) {
        lensCells += 1;
        if (cell[9][15] === true) passCells += 1;
      }
    }
  }

  assert.equal(cells, 120662);
  assert.equal(seen.size, 120662);
  assert.equal(lensCells, 84060);
  assert.equal(passCells, 20118);
});

test("facility shards independently sum to the canonical ledger", async () => {
  const manifest = await readJson("release-manifest.json");
  let facilities = 0;
  const ids = new Set();

  for (const artifact of manifest.outputs.facilityShards) {
    const shard = await readJson(artifact.path);
    assert.equal(shard.schemaVersion, manifest.schemaVersion);
    assert.equal(shard.releaseId, manifest.releaseId);
    for (const facility of shard.facilities) {
      assert.equal(facility.length, 28);
      assert.equal(typeof facility[0], "string");
      assert.equal(ids.has(facility[0]), false);
      ids.add(facility[0]);
      facilities += 1;
    }
  }

  assert.equal(facilities, 31544);
  assert.equal(ids.size, 31544);
});

test("UNKNOWN, pass-current-evidence, and fail samples remain distinct", async () => {
  const manifest = await readJson("release-manifest.json");
  const samples = manifest.qa.samples;

  const noLensMatch = /^g([0-9]+)-/.exec(samples.noLensUnknown);
  assert.ok(noLensMatch);
  const noLensRow = await readJson(
    "rows/g" +
      Number(noLensMatch[1]).toString().padStart(3, "0") +
      ".json",
  );
  const noLens = findCell(noLensRow, samples.noLensUnknown);
  assert.ok(noLens);
  assert.equal(noLens[9], null);

  for (const [key, expectedPass] of [
    ["r3PassCurrentEvidence", true],
    ["r3Fail", false],
  ]) {
    const cellId = samples[key];
    const match = /^g([0-9]+)-/.exec(cellId);
    assert.ok(match);
    const gridRow = Number(match[1]);
    const row = await readJson(
      "rows/g" + gridRow.toString().padStart(3, "0") + ".json",
    );
    const cell = findCell(row, cellId);
    assert.ok(cell);
    assert.notEqual(cell[9], null);
    assert.equal(cell[9][15], expectedPass);
  }
});

test("500 m is inside the hard gate boundary", () => {
  assert.equal(
    classifyIntegratedThreshold(499.999, 500),
    "inside_threshold",
  );
  assert.equal(classifyIntegratedThreshold(500, 500), "inside_threshold");
  assert.equal(
    classifyIntegratedThreshold(500.001, 500),
    "outside_threshold",
  );
  assert.equal(classifyIntegratedHardGate(499.999, 500, true), "fail");
  assert.equal(classifyIntegratedHardGate(500, 500, true), "fail");
  assert.equal(
    classifyIntegratedHardGate(500.001, 500, true),
    "pass_current_evidence",
  );
  assert.equal(classifyIntegratedHardGate(500.001, 500, false), "unknown");
});

test("row promise LRU caps, refreshes, rejects safely, and clears", async () => {
  const cache = new RowPromiseLruCache(2);
  const first = Promise.resolve("first");
  const second = Promise.resolve("second");
  const third = Promise.resolve("third");

  cache.set(1, first);
  cache.set(2, second);
  assert.equal(cache.size, 2);
  assert.equal(cache.get(1), first);
  cache.set(3, third);
  assert.equal(cache.size, 2);
  assert.equal(cache.get(2), undefined);
  assert.equal(cache.get(1), first);
  assert.equal(cache.get(3), third);

  const rejected = Promise.reject(new Error("expected rejection fixture"));
  await assert.rejects(rejected, /expected rejection fixture/);
  cache.set(4, rejected);
  assert.equal(cache.deleteIfSame(4, third), false);
  assert.equal(cache.deleteIfSame(4, rejected), true);
  assert.equal(cache.size, 1);

  cache.clear();
  assert.equal(cache.size, 0);
  assert.equal(cache.get(1), undefined);
  assert.equal(cache.get(3), undefined);
});
