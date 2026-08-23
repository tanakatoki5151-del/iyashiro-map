import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const read = (relative) => readFile(path.join(root, relative), "utf8");
const load = (relative) => import(pathToFileURL(path.join(root, relative)).href);

const presentation = await load("app/lib/grid-presentation.ts");

test("provisional grid assessments expose no reassuring numeric score", () => {
  const provisional = presentation.toGridAssessment({
    score: 92,
    provisional: true,
    label: "低リスク",
  });
  assert.deepEqual(provisional, {
    score: null,
    provisional: true,
    status: "unknown",
    label: "資料不足・要確認",
  });
  assert.equal(presentation.gridAssessmentNeedsReview(provisional), true);
});

test("complete grid assessments retain their actual score", () => {
  const available = presentation.toGridAssessment({
    score: 82,
    provisional: false,
    label: "低リスク",
  });
  assert.deepEqual(available, {
    score: 82,
    provisional: false,
    status: "available",
    label: "低リスク",
  });
  assert.equal(presentation.gridAssessmentNeedsReview(available), false);
});

test("grid API and map keep unknown state fail closed through rendering", async () => {
  const [route, map] = await Promise.all([
    read("app/api/grid/route.ts"),
    read("app/map-app.tsx"),
  ]);

  assert.match(route, /\.\.\.toGridAssessment\(result\.modern\)/);
  assert.match(route, /combined: toGridAssessment\(result\.combined\)/);
  assert.match(map, /const needsReview = gridAssessmentNeedsReview\(value\)/);
  assert.match(map, /const REVIEW_CELL_COLOR = "#8b928f"/);
  assert.match(map, /資料不足・要確認｜未取得データを安全扱いしません/);
  assert.match(map, /needsReview \|\| score === null[\s\S]*REVIEW_CELL_COLOR[\s\S]*safetyColor\(score\)/);
});

test("initial overlay is a legacy comparison, not mislabeled canonical V10", async () => {
  const [map, adapter, cuolega, denentoshi] = await Promise.all([
    read("app/map-app.tsx"),
    read("app/lib/location-profile/v10-adapter.ts"),
    read("public/data/cuolega-grid-v2.json").then(JSON.parse),
    read("public/data/denentoshi-shibuya-futako-grid-v2.json").then(JSON.parse),
  ]);

  assert.equal(cuolega.engine.name, "directional-line-crossing-v2");
  assert.equal(denentoshi.engine.name, "directional-line-crossing-v2");
  assert.match(adapter, /regional-catalog-v4\.json/);
  assert.match(adapter, /V10 frozen regional catalog v4/);
  assert.match(map, /LEGACY_COMPARISON_ENGINE = "directional-line-crossing-v2"/);
  assert.match(map, /key: "theory", label: "従来地形仮説（比較）"/);
  assert.match(map, /V10正本ではありません/);
  assert.match(map, /従来地形仮説の分類/);
  assert.doesNotMatch(map, /key: "theory", label: "V10比較用地図"/);
  assert.doesNotMatch(map, /V10原典/);
});
