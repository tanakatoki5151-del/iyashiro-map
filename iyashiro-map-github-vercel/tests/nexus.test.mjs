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

test("renders the NEXUS policy v3 page", async () => {
  const worker = await loadWorker("nexus-page-v3");
  const response = await worker.fetch(new Request("http://localhost/nexus", { headers: { accept: "text/html" } }), env, ctx);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /NEXUS 物件判定/);
  assert.match(html, /月の固定費17万円以内/);
  assert.match(html, /1〜3階/);
  assert.match(html, /内部サンプル/);
});

test("policy v3 allows first floor and does not hard-reject high sqm cost", async () => {
  const worker = await loadWorker("nexus-pass-v3");
  const response = await worker.fetch(new Request("http://localhost/api/nexus?total=155000&area=20&floor=1&currentness=confirmed&identity=exact"), env, ctx);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.policyVersion, "NEXUS_POLICY_V3_20260818");
  assert.equal(payload.policyPass, true);
  assert.equal(payload.snapshot.eligibleUnits, 196);
  assert.equal(payload.gates.find((gate) => gate.gateId === "floor").status, "pass");
  assert.equal(payload.gates.find((gate) => gate.gateId === "fixed_per_sqm").status, "pass");
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
