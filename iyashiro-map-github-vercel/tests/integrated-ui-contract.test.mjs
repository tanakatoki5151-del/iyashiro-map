import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const apiUrl = new URL("../app/components/integration/api.ts", import.meta.url);
const resultUrl = new URL("../app/components/integration/result-views.tsx", import.meta.url);

test("adapter recognizes fixed v3 profile layer and ranking keys", async () => {
  const api = await readFile(apiUrl, "utf8");
  for (const key of [
    "V15_3",
    "RYUMYAK",
    "ORBIT",
    "R3_PERSONAL_GATE",
    "HISTORY_P8",
    "LEGACY_CONTEXT",
    "sourceFirst",
    "robustness",
    "v15Pure",
    "ryumyakPure",
  ]) {
    assert.ok(api.includes(key), "missing fixed v3 key: " + key);
  }
});

test("fact envelope arrays feed ORBIT/history without treating policy-off facts as vetoes", async () => {
  const api = await readFile(apiUrl, "utf8");
  assert.match(api, /Array\.isArray\(profile\?\.facts\)/);
  assert.match(api, /orbitFactIds/);
  assert.match(api, /historyFactIds/);
  assert.match(api, /effect === "hard_gate"/);
  assert.match(api, /absenceClaimAllowed === false/);
});

test("source-limited and review facts never collapse to pass", async () => {
  const api = await readFile(apiUrl, "utf8");
  assert.match(api, /"source_limited"/);
  assert.match(api, /\["unknown", "review", "not_checked", "unavailable"\]/);
  assert.match(api, /normalizedSourceStatus === "unknown"/);
});

test("resolution reads v3 query, primaryCellId, sigmaM, and cell center", async () => {
  const api = await readFile(apiUrl, "utf8");
  assert.match(api, /resolutionRoot\?\.query/);
  assert.match(api, /profile\?\.cell/);
  assert.match(api, /primaryCellId/);
  assert.match(api, /"sigmaM"/);
});

test("null canonical ranks are shown as UNKNOWN and HCL context-only data is visible", async () => {
  const [api, results] = await Promise.all([
    readFile(apiUrl, "utf8"),
    readFile(resultUrl, "utf8"),
  ]);
  assert.match(api, /found === undefined \? "unavailable" : "unknown"/);
  assert.match(results, /ranking\.status === "unknown" \? "UNKNOWN"/);
  assert.match(results, /adapter\.contextOnly/);
  assert.match(results, /context only/);
});
