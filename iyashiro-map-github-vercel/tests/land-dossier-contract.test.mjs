import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const read = (relative) => readFile(path.join(root, relative), "utf8");

const mapPath = "app/map-app.tsx";
const panelPath = "app/components/land-dossier-panel.tsx";
const dossierPath = "app/lib/integration-api/dossier.ts";
const profilePath = "app/lib/integration-api/profile.ts";
const typesPath = "app/lib/land-dossier-types.ts";
const routePath = "app/api/v3/dossier/route.ts";

test("the root map sends both a pin and an address to the one dossier API", async () => {
  const map = await read(mapPath);

  assert.match(map, /fetch\(\s*["']\/api\/v3\/dossier\?/);
  assert.match(map, /parameters\.set\("lat", String\(target\.lat\)\)/);
  assert.match(map, /parameters\.set\("lng", String\(target\.lng\)\)/);
  assert.match(map, /parameters\.set\("q", target\.query\)/);
  assert.doesNotMatch(map, /["']\/api\/(?:diagnose|lookup)(?:\?|["'])/);
});

test("the normal dossier UI fixes the two definitive land pillars", async () => {
  const [map, panel, dossier, types] = await Promise.all([
    read(mapPath),
    read(panelPath),
    read(dossierPath),
    read(typesPath),
  ]);
  const normalUi = map + "\n" + panel;

  assert.match(panel, /data-pillar="1"/);
  assert.match(panel, /土地そのもの・一本目/);
  assert.match(dossier, /title: "イヤシロジ（＝テライン仮説）"/);
  assert.match(types, /title: "イヤシロジ（＝テライン仮説）"/);

  const visibleModelVersions = [...panel.matchAll(/modelVersion="([^"]+)"/g)]
    .map((match) => match[1]);
  assert.deepEqual(visibleModelVersions, ["V15.3", "V10"]);
  assert.match(panel, /現在の判定/);
  assert.match(panel, /過去版との比較/);
  assert.match(dossier, /const findings = candidates\.flatMap/);
  assert.match(dossier, /hasCandidateVariation/);
  assert.match(dossier, /候補区画の凍結判定幅/);

  assert.match(panel, /data-pillar="2"/);
  assert.match(panel, /土地そのもの・二本目/);
  assert.match(dossier, /ryumyak:\s*\{\s*title: "龍脈"/s);
  assert.match(dossier, /順位表が異なるため合算しません/);

  for (const archived of ["V11", "V12", "V13", "V14"]) {
    assert.doesNotMatch(normalUi, new RegExp(`\\b${archived}\\b`), `${archived} leaked into the normal UI`);
  }
});

test("archived V11-V14 layers stay out of normal profile and NEXUS UIs", async () => {
  const [profileUi, nexusUi] = await Promise.all([
    read("app/profile/profile-client.tsx"),
    read("app/nexus/nexus-client.tsx"),
  ]);

  assert.doesNotMatch(profileUi, /V11 歴史・地形/);
  assert.match(profileUi, /layer\?\.layerId !== "v11Terrain"/);
  assert.match(nexusUi, /layer\?\.layerId !== "v11Terrain"/);
  for (const archived of ["V11", "V12", "V13", "V14"]) {
    assert.doesNotMatch(
      profileUi + "\n" + nexusUi,
      new RegExp(`["']${archived}\\s`),
    );
  }
});

test("the dossier exposes every requested reading section and missing-information view", async () => {
  const [panel, types] = await Promise.all([read(panelPath), read(typesPath)]);

  assert.match(panel, /data-dossier-section=\{section\.id\}/);
  for (const section of ["terrain", "water", "ground", "history", "facilities"]) {
    assert.match(types, new RegExp(`\\b${section}\\b`), `missing section type: ${section}`);
  }
  assert.match(panel, /data-dossier-section="place-name"/);
  assert.match(panel, /地名・土地名の由来/);
  assert.match(panel, /data-dossier-section="missing-information"/);
  assert.match(panel, /data-testid="missing-information"/);
  assert.match(panel, /次に何を調べるかまで表示します/);
});

test("500 m hard avoids remain non-compensatory and unknown never becomes safe", async () => {
  const [dossier, panel, types] = await Promise.all([
    read(dossierPath),
    read(panelPath),
    read(typesPath),
  ]);

  assert.match(dossier, /const THRESHOLD_M = 500 as const/);
  assert.match(dossier, /const CELL_CENTER_MAX_POSITION_ERROR_M = 71 as const/);
  assert.match(types, /thresholdM: 500/);
  assert.match(dossier, /distanceM! <= THRESHOLD_M/);
  assert.match(dossier, /distanceM! - item\.uncertaintyM <= THRESHOLD_M/);
  assert.match(dossier, /fullyChecked && boundaryRisks\.length === 0/);
  for (const fact of ["temple", "cemetery", "large_hospital", "strong_history", "p8"]) {
    assert.match(
      dossier,
      new RegExp(`aggregateFact\\(candidates, resolution, "${fact}",[\\s\\S]*?hardGate: true`),
      `missing 500 m hard avoid: ${fact}`,
    );
  }
  assert.match(dossier, /hardAvoids\.some\(\(item\) => item\.status === "avoid"\)/);
  assert.match(dossier, /hardAvoids\.every\(\(item\) => item\.status === "current_clear"\)/);
  assert.match(dossier, /:\s*"review"/);
  assert.match(dossier, /後段の点数で相殺しません/);
  assert.match(panel, /未取得・未接続・確認範囲外を、安全や問題なしとは扱いません/);
});

test("the dossier GET route accepts coordinates or an address and fails closed on incomplete input", async () => {
  await stat(path.join(root, routePath));
  const route = await read(routePath);

  assert.match(route, /export async function GET\(request: Request\)/);
  assert.match(route, /searchParams\.get\("lat"\)/);
  assert.match(route, /trimmed\(searchParams\.get\("lng"\)\) \?\? trimmed\(searchParams\.get\("lon"\)\)/);
  assert.match(route, /trimmed\(searchParams\.get\("q"\)\) \?\? trimmed\(searchParams\.get\("address"\)\)/);
  assert.match(route, /rawLat === null \|\| rawLng === null/);
  assert.match(route, /await buildLandDossier\(\{\s*lat:/s);
  assert.match(route, /await buildLandDossier\(\{\s*address,/s);
  assert.match(route, /"location_required"/);
  assert.match(route, /"Cache-Control": "no-store"/);
});

test("OpenAPI documents the land dossier query aliases and response", async () => {
  const document = JSON.parse(await read("public/openapi-v3.json"));
  const operation = document.paths?.["/api/v3/dossier"]?.get;
  assert.ok(operation, "GET /api/v3/dossier is not documented");

  const parameters = new Map(operation.parameters.map((parameter) => [parameter.name, parameter]));
  assert.deepEqual([...parameters.keys()], ["lat", "lng", "lon", "q", "address", "label"]);
  for (const name of parameters.keys()) {
    assert.equal(parameters.get(name).in, "query");
    assert.equal(parameters.get(name).required, false);
  }
  assert.equal(parameters.get("lat").schema.minimum, -90);
  assert.equal(parameters.get("lat").schema.maximum, 90);
  assert.equal(parameters.get("lng").schema.minimum, -180);
  assert.equal(parameters.get("lng").schema.maximum, 180);
  assert.equal(
    operation.responses["200"].content["application/json"].schema.$ref,
    "#/components/schemas/LandDossier",
  );
  assert.equal(document.components.schemas.LandDossier.properties.stageOne.$ref,
    "#/components/schemas/LandDossierStageOne");
  assert.equal(document.components.schemas.LandDossierStageOne.properties.thresholdM.const, 500);
});

test("the rendered pillar summary never names archived intermediate versions", async () => {
  const dossier = await read(dossierPath);

  const visibleIyashiroSummary = dossier.match(
    /iyashiroji:\s*\{[\s\S]*?summary:\s*[\s\S]*?current:\s*v153/,
  )?.[0] ?? "";
  for (const archived of ["V11", "V12", "V13", "V14"]) {
    assert.doesNotMatch(
      visibleIyashiroSummary,
      new RegExp(`\\b${archived}\\b`),
      `${archived} leaked into the rendered pillar summary`,
    );
  }
});

test("the initial overlay is truthfully labeled as a legacy comparison", async () => {
  const map = await read(mapPath);

  assert.match(map, /key: "theory", label: "従来地形仮説（比較）"/);
  assert.match(map, /従来地形仮説（V10正本ではありません）：\$\{cell\.label\}/);
  assert.equal(
    [...map.matchAll(/bubblingMouseEvents: false/g)].length,
    2,
  );
  assert.match(map, /従来地形仮説の分類/);
  assert.match(map, /凍結済みのV10正本そのものではありません/);
  assert.doesNotMatch(map, /key: "theory", label: "V10比較用地図"/);
});

test("V15.3 displays zone as an identifier and regime as the Japanese terrain class", async () => {
  const dossier = await read(dossierPath);

  assert.match(dossier, /label: "V15\.3区画ID", value: zoneIds\.join/);
  assert.match(dossier, /label: "地形・地勢区分", value: regimes\.join/);
  assert.match(
    dossier,
    /primaryRank === null \? "未収録" : primaryRank \+ "位"/,
  );
  assert.match(
    dossier,
    /"、地形・地勢区分は"[\s\S]*japanese\(primary\.regime\)/,
  );
  assert.doesNotMatch(dossier, /未収録位/);
  assert.doesNotMatch(
    dossier,
    /"位、地形区分は"[\s\S]*japanese\(primary\.zone\)/,
  );
});

test("V15.3 and RYUMYAK availability are independent and primary-cell only", async () => {
  const [dossier, shape] = await Promise.all([
    read(dossierPath),
    read("app/lib/integration-api/profile-shape.ts"),
  ]);

  assert.match(shape, /function hasMeaningfulV153Data/);
  assert.match(shape, /function hasMeaningfulRyumyakData/);
  assert.match(
    shape,
    /hasR3LensRecord && hasMeaningfulV153Data\(v153\) \? v153 : null/,
  );
  assert.match(
    shape,
    /hasR3LensRecord && hasMeaningfulRyumyakData\(ryumyak\) \? ryumyak : null/,
  );
  assert.match(dossier, /function hasV153AxisRecord[\s\S]*hasMeaningfulV153Data/);
  assert.match(dossier, /function hasRyumyakAxisRecord[\s\S]*hasMeaningfulRyumyakData/);
  assert.match(
    dossier,
    /primaryCandidate && hasRyumyakAxisRecord\(primaryCandidate\)[\s\S]*status: primary \? "available" : "unknown"/,
  );
});

test("fact cards only inherit sources related to their own layer", async () => {
  const [dossier, profile] = await Promise.all([
    read(dossierPath),
    read(profilePath),
  ]);

  assert.match(profile, /function sourcePointers\(layer: string\)/);
  assert.match(
    profile,
    /layer === "ORBIT"[\s\S]*PROJECT_ORBIT[\s\S]*PROJECT_ORBIT_FACILITIES/,
  );
  assert.match(
    profile,
    /if \(!relevantProjects\.has\(project\)\) return \[\]/,
  );
  assert.match(profile, /sources: sourcePointers\(definition\.layer\)/);
  assert.doesNotMatch(profile, /sources: sourcePointers\(\)/);
  assert.match(dossier, /return "関連する根拠資料は未特定"/);
  assert.doesNotMatch(
    dossier,
    /sourceTitle\([^\n]+, "統合土地データ"\)/,
  );
});
test("the public dossier omits internal raw evidence and non-web pointers", async () => {
  const [route, types, document] = await Promise.all([
    read(routePath),
    read(typesPath),
    read("public/openapi-v3.json").then(JSON.parse),
  ]);
  const dossier = await read(dossierPath);


  assert.match(route, /function toPublicDossier\(dossier: LandDossier\)/);
  assert.match(route, /delete result\.rawEvidence/);
  assert.match(route, /url\.protocol === "https:" \|\| url\.protocol === "http:"/);
  assert.match(dossier, /function httpPointer\(value: unknown\)/);
  assert.match(dossier, /url\.protocol === "https:" \|\| url\.protocol === "http:"/);
  assert.match(dossier, /pointer: httpPointer\(source\.pointer\)/);
  assert.match(types, /rawEvidence\?:/);
  assert.doesNotMatch(
    document.components.schemas.LandDossier.required.join(","),
    /rawEvidence/,
  );
  assert.equal(
    document.components.schemas.LandDossier.properties.rawEvidence,
    undefined,
  );
});

test("address suggestions prevent stale results and support keyboard navigation", async () => {
  const map = await read(mapPath);

  assert.match(map, /role="combobox"/);
  assert.match(map, /aria-activedescendant=/);
  assert.match(map, /event\.key === "ArrowDown"/);
  assert.match(map, /event\.key === "Enter"/);
  assert.match(map, /searchAbort\.current\?\.abort\(\)/);
  assert.match(map, /const requestId = \+\+dossierRequestId\.current/);
  assert.ok(
    [...map.matchAll(/requestId !== dossierRequestId\.current/g)].length >= 3,
    "dossier fetch and both geolocation callbacks must discard stale requests",
  );
  assert.match(map, /clearTimeout\(searchTimer\.current\);\s*searchTimer\.current = null/);
  assert.match(map, /caught as Error\)\.name !== "AbortError"/);
  assert.match(map, /dossierSheetRef\.current\?\.focus\(\)/);
  assert.match(map, /tabIndex=\{-1\}/);
  assert.doesNotMatch(map, /placeholder="住所・駅名・施設名/);
});
