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

test("renders the NEXUS policy v3 land-first page", async () => {
  const worker = await loadWorker("nexus-page-v3");
  const response = await worker.fetch(new Request("http://localhost/nexus", { headers: { accept: "text/html" } }), env, ctx);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /NEXUS 物件判定/);
  assert.match(html, /月の固定費17万円以内/);
  assert.match(html, /1〜3階/);
  assert.match(html, /今の270住戸だけでは、地域相場の完成版とは言いません/);
  assert.match(html, /土地研究を主軸70%/);
});

test("policy v3 allows first floor and keeps sqm cost diagnostic-only", async () => {
  const worker = await loadWorker("nexus-pass-v3");
  const response = await worker.fetch(new Request("http://localhost/api/nexus?total=155000&area=20&floor=1&currentness=confirmed&identity=exact&town=%E6%9D%B1%E3%81%8C%E4%B8%98%E4%B8%80%E4%B8%81%E7%9B%AE"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.schemaVersion, "1.3");
  assert.equal(payload.policyVersion, "NEXUS_POLICY_V3_20260818");
  assert.equal(payload.policyPass, true);
  assert.equal(payload.snapshot.rawObservations, 332);
  assert.equal(payload.snapshot.eligibleUnits, 196);
  assert.equal(payload.snapshot.primaryTargetUnits, 168);
  assert.equal(payload.gates.find((gate) => gate.gateId === "floor").status, "pass");
  assert.equal(payload.gates.find((gate) => gate.gateId === "fixed_per_sqm").hardGate, false);
  assert.equal(payload.marketContext.town, "東が丘一丁目");
});

test("policy v3 rejects only hard constraints", async () => {
  const worker = await loadWorker("nexus-fail-v3");
  const response = await worker.fetch(new Request("http://localhost/api/nexus?total=171000&area=14&floor=4&currentness=unknown&identity=exact"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.policyPass, false);
  assert.equal(payload.decisionState, "OUTSIDE_POLICY");
  assert.equal(payload.gates.find((gate) => gate.gateId === "monthly_total").status, "fail");
  assert.equal(payload.gates.find((gate) => gate.gateId === "area").status, "fail");
  assert.equal(payload.gates.find((gate) => gate.gateId === "floor").status, "fail");
});

test("returns explicit market-coverage limits and official macro benchmarks", async () => {
  const worker = await loadWorker("nexus-market-coverage");
  const response = await worker.fetch(new Request("http://localhost/api/nexus?total=98000&area=28.71&floor=2&address=%E6%9D%B1%E4%BA%AC%E9%83%BD%E7%9B%AE%E9%BB%92%E5%8C%BA%E6%9D%B1%E3%81%8C%E4%B8%981%E4%B8%81%E7%9B%AE18-20"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.marketCoverage.researchTownSegments, 73);
  assert.equal(payload.marketCoverage.medianUnitsPerResearchTown, 3);
  assert.equal(payload.marketCoverage.researchTownsBelowFiveUnits, 59);
  assert.equal(payload.marketCoverage.localBenchmarkReadyTowns, 0);
  assert.equal(payload.externalBenchmarks[0].askingMonthlyJPY, 136075);
  assert.equal(payload.externalBenchmarks[0].inquiryMonthlyJPY, 100457);
  assert.match(payload.warnings.join(" "), /地域相場の完成版とは扱いません/);
});
