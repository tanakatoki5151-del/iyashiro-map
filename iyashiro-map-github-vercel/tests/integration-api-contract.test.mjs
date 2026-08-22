import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const read = (relative) => readFile(path.join(root, relative), "utf8");

test("canonical round-nearest grid reproduces frozen fixtures", async () => {
  const source = await read("app/lib/integration-api/grid.ts");
  const number = (name) => Number(new RegExp(`export const ${name} = ([^;]+);`).exec(source)?.[1].replaceAll("_", ""));
  const aLat = number("A_LAT");
  const bLat = number("B_LAT");
  const aLon = number("A_LON");
  const bLon = number("B_LON");
  assert.equal(aLat, 35.839647862019405);
  assert.equal(bLat, -0.0008983111749910168);
  assert.equal(aLon, 139.43);
  assert.equal(bLon, 0.0011042452218025757);
  for (const [lat, lon, expected] of [
    [35.488309, 139.473853, "g391-40"],
    [35.4638474, 139.4772939, "g418-43"],
    [35.452226, 139.483567, "g431-49"],
    [35.532848911, 139.680900636, "g342-227"],
  ]) {
    assert.equal(`g${Math.round((lat - aLat) / bLat)}-${Math.round((lon - aLon) / bLon)}`, expected);
  }
  assert.match(source, /resolveTheoreticalCells/);
  assert.match(source, /resolutionStability/);
});

test("v3 route surface and async dynamic params are present", async () => {
  const routes = [
    "app/api/v3/resolve/route.ts",
    "app/api/v3/cells/[cellId]/profile/route.ts",
    "app/api/v3/properties/intake/route.ts",
    "app/api/v3/assess/route.ts",
    "app/api/v3/compare/route.ts",
    "app/api/v3/house-compass/route.ts",
    "app/api/v3/releases/route.ts",
  ];
  await Promise.all(routes.map((route) => stat(path.join(root, route))));
  const dynamicRoute = await read(routes[1]);
  assert.match(dynamicRoute, /params: Promise<\{ cellId: string \}>/);
  assert.match(dynamicRoute, /await params/);
});

test("property intake keeps the bounded SSRF boundary", async () => {
  const source = await read("app/lib/integration-api/property-intake.ts");
  for (const marker of [
    'from "node:dns/promises"',
    'from "node:net"',
    'redirect: "manual"',
    "MAXIMUM_REDIRECTS = 3",
    "FETCH_TIMEOUT_MS = 8_000",
    "MAXIMUM_HTML_BYTES = 1_250_000",
    "isPrivateOrLocalAddress",
    "SUPPORTED_PROPERTY_HOSTS",
  ]) assert.ok(source.includes(marker), marker);
});

test("policy is non-compensatory and unknown remains review", async () => {
  const source = await read("app/lib/integration-api/policy.ts");
  assert.match(source, /hardGateNonCompensatory: true/);
  assert.match(source, /unknownDisposition: "review"/);
  assert.match(source, /status: "hard_veto"/);
  assert.match(source, /status: "review"/);
  const profile = await read("app/lib/integration-api/profile.ts");
  assert.match(profile, /absenceClaimAllowed: false/);
  assert.match(profile, /aiScoringAllowed: false/);
  assert.match(profile, /Source-firstはArea Family順位/);
});

test("HCL bounded engine forbids aggregate prediction scores", async () => {
  const source = await read("app/lib/integration-api/hcl-engine.ts");
  assert.match(source, /totalScore: null/);
  assert.match(source, /majorityVote: false/);
  assert.match(source, /healthWealthPrediction: false/);
});


test("compact comparison contract is current-release bound and excludes raw PII", async () => {
  const assessment = await read("app/lib/integration-api/assessment.ts");
  const start = assessment.indexOf("function comparisonTokenPayload(");
  const end = assessment.indexOf("function signComparisonToken(", start);
  assert.ok(start >= 0 && end > start);
  const material = assessment.slice(start, end);
  assert.match(material, /iyashiro-comparison-candidate\/1\.1/);
  assert.match(material, /COMPARISON_TOKEN_TTL_MS/);
  assert.match(material, /name: value\.property\.name/);
  assert.match(material, /address: value\.property\.address/);
  for (const forbidden of [
    "property: value.property",
    "houseCompass",
    "value.property.url",
    "value.property.memo",
    "value.profile",
    "birthDate",
    "currentAddress",
  ]) assert.equal(material.includes(forbidden), false, forbidden);
  assert.match(assessment, /assertCurrentEvidenceRelease\(snapshot\.evidenceRelease/);
  assert.match(assessment, /assertCurrentEvidenceRelease\([\s\S]*record\.evidenceRelease/);
  assert.match(assessment, /stale_evidence_release/);
  assert.match(assessment, /profileIncludedInResponse: false/);
});

test("preview signing fallback is domain-separated and production-disabled", async () => {
  const source = await read("app/lib/integration-api/comparison-secret.ts");
  assert.match(source, /hkdfSync/);
  assert.match(source, /VERCEL_ENV !== "preview"/);
  assert.match(source, /iyashiro\/comparison-token\/v1/);
  assert.match(source, /VERCEL_URL/);
  assert.match(source, /VERCEL_PROJECT_ID/);
  assert.doesNotMatch(source, /return ["'][^"']{32,}["']/);
});

test("address refinement and conservative IPv6 boundary are wired", async () => {
  const address = await read("app/lib/integration-api/address-evidence.ts");
  assert.match(address, /addressEvidenceCanBeRefinedBy/);
  assert.match(address, /extracted\.stem === authoritative\.stem/);
  const network = await read("app/lib/integration-api/network-safety.ts");
  assert.match(network, /globallyRoutableUnicast/);
  assert.match(network, /\["2001::", 23\]/);
  assert.match(network, /\["2002::", 16\]/);
  assert.match(network, /\["3fff::", 20\]/);
});


test("release catalog is readiness-gated and exposes no internal source pointers", async () => {
  const catalog = await read("app/lib/integration-api/release-catalog.ts");
  assert.match(catalog, /await integratedDataRuntimeAvailable\(\)/);
  assert.match(catalog, /integrated_data_unavailable/);
  assert.match(catalog, /evidenceReleaseFromMetadata/);
  assert.match(catalog, /manifestValidated: true/);
  assert.doesNotMatch(catalog, /allExpectedRowsVerified/);
  assert.doesNotMatch(catalog, /sources:/);
  assert.doesNotMatch(catalog, /pointer/);
  const route = await read("app/api/v3/releases/route.ts");
  assert.match(route, /export async function GET/);
  assert.match(route, /Cache-Control": "no-store"/);
});

test("OpenAPI v3 internal references recursively resolve", async () => {
  const document = JSON.parse(await read("public/openapi-v3.json"));
  const references = [];
  const visit = (value, location = "$") => {
    if (!value || typeof value !== "object") return;
    if (typeof value.$ref === "string" && value.$ref.startsWith("#/")) references.push([location, value.$ref]);
    for (const [key, nested] of Object.entries(value)) visit(nested, `${location}.${key}`);
  };
  const resolve = (reference) => reference
    .slice(2)
    .split("/")
    .map((part) => part.replaceAll("~1", "/").replaceAll("~0", "~"))
    .reduce((value, key) => value && Object.hasOwn(value, key) ? value[key] : undefined, document);

  visit(document);
  assert.ok(references.length > 0);
  for (const [location, reference] of references) {
    assert.notEqual(resolve(reference), undefined, `${location}: ${reference}`);
  }
  assert.deepEqual(Object.keys(document).sort(), ["components", "info", "openapi", "paths", "servers"]);
});

test("release catalog response fixture conforms to its OpenAPI schema", async () => {
  const document = JSON.parse(await read("public/openapi-v3.json"));
  const runtime = await read("app/lib/integrated-data/runtime.ts");
  const generatedAt = /generatedAt:\s*"([^"]+)"/.exec(runtime)?.[1];
  const releaseId = /releaseId:\s*"([^"]+)"/.exec(runtime)?.[1];
  const sourceSchemaVersion = /schemaVersion:\s*"([^"]+)"/.exec(runtime)?.[1];
  assert.match(generatedAt ?? "", /^\d{4}-\d{2}-\d{2}$/);
  assert.ok(releaseId);
  assert.ok(sourceSchemaVersion);

  const resolve = (reference) => reference
    .slice(2)
    .split("/")
    .map((part) => part.replaceAll("~1", "/").replaceAll("~0", "~"))
    .reduce((value, key) => value && Object.hasOwn(value, key) ? value[key] : undefined, document);
  const validate = (schema, value, location = "response") => {
    if (schema.$ref) return validate(resolve(schema.$ref), value, location);
    if (Object.hasOwn(schema, "const")) assert.deepEqual(value, schema.const, location);
    const accepted = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
    const actual = value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
    if (accepted.length > 0) assert.ok(accepted.includes(actual), `${location}: ${actual}`);
    if (actual === "string") {
      if (schema.pattern) assert.match(value, new RegExp(schema.pattern), location);
      if (schema.format === "date") assert.match(value, /^\d{4}-\d{2}-\d{2}$/, location);
      if (schema.format === "date-time") {
        assert.match(value, /T/, location);
        assert.ok(Number.isFinite(Date.parse(value)), location);
      }
    }
    if (actual === "object") {
      for (const key of schema.required ?? []) assert.ok(Object.hasOwn(value, key), `${location}.${key}`);
      for (const [key, nested] of Object.entries(schema.properties ?? {})) {
        if (Object.hasOwn(value, key)) validate(nested, value[key], `${location}.${key}`);
      }
      if (schema.additionalProperties === false) {
        for (const key of Object.keys(value)) assert.ok(Object.hasOwn(schema.properties ?? {}, key), `${location}.${key}`);
      }
    }
  };

  const fixture = {
    schemaVersion: "iyashiro-release-catalog/1.0",
    checkedAt: "2026-08-23T12:00:00.000Z",
    readiness: { status: "ready", manifestValidated: true },
    current: {
      evidence: { releaseId, sha256: "0".repeat(64), dataContract: "integrated-cell-profile/3.0" },
      generatedAt,
      sourceSchemaVersion,
    },
  };
  const schema = document.components.schemas.ReleaseCatalog;
  validate(schema, fixture);
  assert.equal(document.components.schemas.ReleaseCatalogCurrent.properties.generatedAt.format, "date");
  assert.throws(() => validate(schema, {
    ...fixture,
    current: { ...fixture.current, generatedAt: "2026-08-23T00:00:00.000Z" },
  }));
});
