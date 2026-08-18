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

test("summarizes all 240 discovery points without residence ranking", async () => {
  const worker = await loadWorker("discovery-summary");
  const response = await worker.fetch(new Request("http://localhost/api/nexus/discovery-wave1-summary"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.frame.samples, 240);
  assert.equal(payload.frame.municipalities, 48);
  assert.equal(payload.frame.eligibleRyumyakSamples, 235);
  assert.equal(payload.frame.noEligibleZoneControls, 5);
  assert.equal(payload.semantics.residenceRanking, false);
  assert.equal(payload.semantics.syntheticTotalScore, false);
  assert.equal(payload.coverage.v10Available, 240);
  assert.equal(payload.coverage.underlandAvailable, 240);
  assert.equal(payload.coverage.ecoscapeAvailable, 240);
  assert.ok(payload.byStratum.A_LOCAL_TOP);
  assert.ok(payload.byStratum.E_LOCAL_BOTTOM_CONTROL);
  assert.ok(payload.researchQueues.convergence.count >= 0);
  assert.ok(payload.researchQueues.contradiction.count >= 0);
  assert.ok(payload.researchQueues.counterexample.count >= 0);
  assert.ok(payload.researchQueues.uncertainty.count >= 48);
  assert.equal("residenceRank" in payload, false);
  assert.equal("totalScore" in payload, false);
});
