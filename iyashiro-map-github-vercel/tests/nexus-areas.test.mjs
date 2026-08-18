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

test("renders the 25-area land-first research matrix", async () => {
  const worker = await loadWorker("nexus-areas");
  const response = await worker.fetch(new Request("http://localhost/nexus/areas", { headers: { accept: "text/html" } }), env, ctx);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /住む地域の研究マップ/);
  assert.match(html, /25地域/);
  assert.match(html, /居住おすすめ順位ではありません/);
  assert.match(html, /上原三丁目/);
  assert.match(html, /東が丘一丁目/);
  assert.match(html, /Raw 3,000件/);
});

test("keeps research maturity separate from recommendation", async () => {
  const worker = await loadWorker("nexus-areas-semantics");
  const response = await worker.fetch(new Request("http://localhost/nexus/areas", { headers: { accept: "text/html" } }), env, ctx);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /A〜Dは研究成熟度/);
  assert.match(html, /未調査、該当なしを安全へ読み替えません/);
  assert.match(html, /市場 Reference/);
});
