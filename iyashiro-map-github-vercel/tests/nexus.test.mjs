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

test("renders the NEXUS property assessment page", async () => {
  const worker = await loadWorker("nexus-page");
  const response = await worker.fetch(new Request("http://localhost/nexus", { headers: { accept: "text/html" } }), env, ctx);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /NEXUS 物件判定/);
  assert.match(html, /月の固定費13万円以内/);
  assert.match(html, /正式モデルと単純中央値も混ぜません/);
});

test("passes policy gates and returns transparent town market context", async () => {
  const worker = await loadWorker("nexus-pass-market");
  const response = await worker.fetch(new Request("http://localhost/api/nexus?total=98000&area=28.71&floor=2&currentness=confirmed&identity=exact&town=%E6%9D%B1%E3%81%8C%E4%B8%98%E4%B8%80%E4%B8%81%E7%9B%AE"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.policyPass, true);
  assert.equal(payload.decisionState, "READY_FOR_LAND_CHECK");
  assert.equal(payload.gates.every((gate) => gate.status === "pass"), true);
  assert.equal(payload.snapshot.canonicalUnits, 270);
  assert.equal(payload.snapshot.marketKnownTotals, 257);
  assert.equal(payload.marketContext.town, "東が丘一丁目");
  assert.equal(payload.marketContext.medianTotalJPY, 116000);
  assert.equal(payload.marketContext.comparisonLabel, "町丁目の単純中央値よりかなり低い");
});

test("keeps failed gates separate instead of hiding them in one score", async () => {
  const worker = await loadWorker("nexus-fail");
  const response = await worker.fetch(new Request("http://localhost/api/nexus?total=141000&area=24.98&floor=3&currentness=unknown&identity=exact&town=%E4%B8%89%E5%AE%BF%E4%BA%8C%E4%B8%81%E7%9B%AE"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.policyPass, false);
  assert.equal(payload.decisionState, "OUTSIDE_POLICY");
  assert.equal(payload.gates.find((gate) => gate.gateId === "monthly_total").status, "fail");
  assert.equal(payload.gates.find((gate) => gate.gateId === "fixed_per_sqm").status, "fail");
  assert.equal(payload.gates.find((gate) => gate.gateId === "floor").status, "pass");
  assert.equal(payload.marketContext.sampleQuality, "THIN");
});
