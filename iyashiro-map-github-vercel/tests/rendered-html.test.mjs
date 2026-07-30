import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { decode } from "fast-png";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

test("renders development preview metadata", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  assert.match(await response.text(), developmentPreviewMeta);
});

test("renders the Japanese map experience", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("page", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /イヤシロ土地判定マップ/);
  assert.match(html, /東京23区・横浜市・川崎市/);
  assert.match(
    html,
    /クオレガ4\.5km圏と田園都市線沿線の100m事前計算色を表示しています/,
  );
});

test("ships the instant wide-area colour overlay", async () => {
  const bytes = await readFile(
    new URL("../public/data/iyashiro-overview.png", import.meta.url),
  );
  const image = decode(bytes);
  assert.equal(image.width, 743);
  assert.equal(image.height, 1003);
  assert.ok(bytes.byteLength > 100_000);
});

test("ships the Cuolega 100m precomputed terrain grid", async () => {
  const data = JSON.parse(
    await readFile(
      new URL("../public/data/cuolega-grid-v2.json", import.meta.url),
      "utf8",
    ),
  );
  const bytes = await readFile(
    new URL("../public/data/cuolega-grid-v2.png", import.meta.url),
  );
  const image = decode(bytes);

  assert.equal(data.schemaVersion, "2.0");
  assert.equal(data.center.radiusMeters, 4_500);
  assert.equal(data.center.stepMeters, 100);
  assert.equal(data.cells.length, 6_361);
  assert.ok(data.hotspots.length > 0);
  assert.ok(
    data.cells.every(
      (cell) =>
        cell.detailScore ===
        Math.round(cell.originalScore * 0.8 + cell.auxiliaryTerrainScore * 0.2),
    ),
  );
  assert.equal(image.width, 910);
  assert.equal(image.height, 910);
  assert.ok(bytes.byteLength > 20_000);
});

test("ships the Den-en-toshi 100m precomputed terrain corridor", async () => {
  const data = JSON.parse(
    await readFile(
      new URL(
        "../public/data/denentoshi-shibuya-futako-grid-v2.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const bytes = await readFile(
    new URL(
      "../public/data/denentoshi-shibuya-futako-grid-v2.png",
      import.meta.url,
    ),
  );
  const image = decode(bytes);

  assert.equal(data.schemaVersion, "2.0");
  assert.equal(data.region.id, "denentoshi");
  assert.equal(data.region.bufferMeters, 1_000);
  assert.deepEqual(
    data.region.stations.map((station) => station.name),
    ["渋谷", "池尻大橋", "三軒茶屋", "駒沢大学", "桜新町", "用賀", "二子玉川"],
  );
  assert.equal(data.cells.length, 2_109);
  assert.ok(data.hotspots.length > 0);
  assert.ok(
    data.cells.every(
      (cell) =>
        cell.detailScore ===
        Math.round(cell.originalScore * 0.8 + cell.auxiliaryTerrainScore * 0.2),
    ),
  );
  assert.equal(image.width, 910);
  assert.equal(image.height, 910);
  assert.ok(bytes.byteLength > 10_000);
});

test("exposes a machine-readable health endpoint", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("health", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("http://localhost/api/health", {
      headers: { accept: "application/json" },
    }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.status, "ok");
  assert.deepEqual(payload.scope, ["東京23区", "横浜市", "川崎市"]);
});
