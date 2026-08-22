import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const files = {
  page: new URL("../app/integrated/page.tsx", import.meta.url),
  client: new URL("../app/components/integration/integrated-copilot.tsx", import.meta.url),
  results: new URL("../app/components/integration/result-views.tsx", import.meta.url),
  api: new URL("../app/components/integration/api.ts", import.meta.url),
  types: new URL("../app/components/integration/types.ts", import.meta.url),
  css: new URL("../app/integrated/integrated.module.css", import.meta.url),
};

async function source(key) {
  return readFile(files[key], "utf8");
}

test("/integrated is a server page with a non-async client boundary", async () => {
  const [page, client] = await Promise.all([source("page"), source("client")]);
  assert.match(page, /export const metadata/);
  assert.match(page, /<IntegratedCopilot \/>/);
  assert.match(client, /^"use client";/);
  assert.doesNotMatch(client, /export default async function IntegratedCopilot/);
});

test("assess and compare use the v3 server APIs without local ranking fallback", async () => {
  const [api, results] = await Promise.all([source("api"), source("results")]);
  assert.match(api, /fetch\("\/api\/v3\/assess"/);
  assert.match(api, /fetch\("\/api\/v3\/compare"/);
  assert.match(api, /const tokens = candidates\.map/);
  assert.match(api, /assessment\.raw\.comparisonToken/);
  assert.match(results, /ローカルで順位を推測しません/);
  assert.match(results, /tier → 正本sourceRank/);
});

test("distance policy is 300/500/650, defaults to 500, and shrine is opt-in", async () => {
  const [client, types] = await Promise.all([source("client"), source("types")]);
  assert.match(client, /\[300, 500, 650\]/);
  assert.match(types, /distanceThresholdM: 500/);
  assert.match(types, /includeShrines: false/);
  assert.match(client, /神社も距離ゲートへ含める/);
  assert.match(client, /既定OFF/);
});

test("all requested independent views and fact layers are explicit", async () => {
  const api = await source("api");
  for (const label of [
    "Source-first",
    "Robustness",
    "Pure V15.3",
    "Pure RYUMYAK",
    "R3 統合ゲート",
    "V15.3 地形仮説",
    "RYUMYAK 龍脈",
    "ORBIT 周辺施設",
    "歴史・土地履歴",
    "HOUSE COMPASS LAB",
  ]) {
    assert.ok(api.includes(label), "missing label: " + label);
  }
});

test("UNKNOWN and unavailable API states are not presented as safe", async () => {
  const [client, results] = await Promise.all([source("client"), source("results")]);
  assert.match(client, /UNKNOWNは安全ではありません/);
  assert.match(client, /代替の架空結果は表示しません/);
  assert.match(results, /未取得・未接続は、安全や問題の不存在を意味しません/);
  assert.match(results, /API未提供/);
});

test("address, coordinates, property URL, manual correction, HCL, and candidate comparison are present", async () => {
  const client = await source("client");
  for (const token of [
    'id="candidate-address"',
    'id="candidate-latitude"',
    'id="candidate-longitude"',
    'id="property-url"',
    "物件情報を手動で補正",
    "HOUSE COMPASS LAB 入力",
    "<CandidateShelf",
    "<ComparisonResult",
  ]) {
    assert.ok(client.includes(token), "missing UI token: " + token);
  }
});

test("styles include mobile layouts, visible focus, and reduced-motion handling", async () => {
  const css = await source("css");
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media \(max-width: 780px\)/);
  assert.match(css, /@media \(max-width: 430px\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});
