import assert from "node:assert/strict";
import test from "node:test";

async function loadWorker(label) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set(label, `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker;
}

const env = { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } };
const ctx = { waitUntil() {}, passThroughOnException() {} };

test("renders the Phase15 full-domain discovery page", async () => {
  const worker = await loadWorker("discovery-page");
  const response = await worker.fetch(new Request("http://localhost/nexus/discovery", { headers: { accept: "text/html" } }), env, ctx);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /全域240地点の比較探索/);
  assert.match(html, /居住おすすめ順位ではなく/);
  assert.match(html, /旧P0を優先しない/);
});

test("returns independent lenses without a residence rank or synthetic total", async () => {
  const worker = await loadWorker("discovery-api");
  const response = await worker.fetch(new Request("http://localhost/api/nexus/discovery-wave1?limit=2"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.frame.totalSamples, 240);
  assert.equal(payload.frame.municipalityCount, 48);
  assert.equal(payload.results.length, 2);
  assert.equal(payload.semantics.residenceRanking, false);
  assert.equal(payload.semantics.syntheticTotalScore, false);
  assert.equal(payload.results[0].residencePriority, null);
  assert.equal(payload.results[0].residenceRecommendation, null);
  assert.ok(payload.results[0].lenses.ryumyak);
  assert.ok(payload.results[0].lenses.v10);
  assert.ok(payload.results[0].lenses.underland);
  assert.ok(payload.results[0].lenses.ecoscape);
  assert.ok(payload.results[0].lenses.placegraph);
  assert.equal("totalScore" in payload.results[0], false);
  assert.equal("residenceRank" in payload.results[0], false);
});

test("keeps Koto in the frame with five no-RYUMYAK-zone controls", async () => {
  const worker = await loadWorker("discovery-koto");
  const response = await worker.fetch(new Request("http://localhost/api/nexus/discovery-wave1?municipality=%E6%B1%9F%E6%9D%B1%E5%8C%BA&limit=10"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.frame.filteredSamples, 5);
  assert.equal(payload.results.length, 5);
  assert.equal(payload.results.every((item) => item.stratum === "F_NO_RYUMYAK_ELIGIBLE_ZONE_CONTROL"), true);
  assert.equal(payload.results.every((item) => item.lenses.ryumyak.availability === "not_applicable"), true);
});
