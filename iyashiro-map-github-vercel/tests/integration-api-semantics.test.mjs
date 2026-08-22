import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const load = (relative) => import(pathToFileURL(path.join(root, relative)).href);

const [
  normalization,
  grid,
  policy,
  coverage,
  network,
  address,
  snapshot,
  identity,
  ordering,
  profileShape,
  comparisonToken,
  listingSafety,
  comparisonSecret,
  releaseIdentity,
] = await Promise.all([
  load("app/lib/integration-api/normalization.ts"),
  load("app/lib/integration-api/grid.ts"),
  load("app/lib/integration-api/policy-evaluation.ts"),
  load("app/lib/integration-api/coverage-gate.ts"),
  load("app/lib/integration-api/network-safety.ts"),
  load("app/lib/integration-api/address-evidence.ts"),
  load("app/lib/integration-api/snapshot-integrity.ts"),
  load("app/lib/integration-api/candidate-identity.ts"),
  load("app/lib/integration-api/comparison-ordering.ts"),
  load("app/lib/integration-api/profile-shape.ts"),
  load("app/lib/integration-api/comparison-token.ts"),
  load("app/lib/integration-api/listing-url-safety.ts"),
  load("app/lib/integration-api/comparison-secret.ts"),
  load("app/lib/integration-api/release-identity.ts"),
]);

test("numeric normalization never coerces null, boolean, arrays, or whitespace to zero", () => {
  assert.equal(normalization.finiteNumeric(null), null);
  assert.equal(normalization.finiteNumeric(false), null);
  assert.equal(normalization.finiteNumeric(""), null);
  assert.equal(normalization.finiteNumeric("   "), null);
  assert.equal(normalization.finiteNumeric(" 12.5 "), 12.5);
  assert.deepEqual(normalization.classifyOptionalNumericInput(true), { kind: "invalid", reason: "type" });
  assert.deepEqual(normalization.classifyOptionalNumericInput([1]), { kind: "invalid", reason: "type" });
  assert.deepEqual(normalization.classifyOptionalNumericInput(" "), { kind: "invalid", reason: "blank" });
  assert.deepEqual(normalization.classifyOptionalNumericInput(""), { kind: "missing" });
  assert.deepEqual(normalization.classifyOptionalNumericInput("42"), { kind: "value", value: 42 });
});

test("resolver preserves raw probability mass and bounds high-sigma candidates", () => {
  const center = grid.cellCenter(391, 40);
  assert.deepEqual(grid.cellOf(center.lat, center.lon), { row: 391, col: 40 });
  const ordinary = grid.resolveTheoreticalCells(center.lat, center.lon, 5);
  const ordinaryMass = ordinary.reduce((sum, candidate) => sum + candidate.weight, 0);
  assert.equal(ordinary[0].cellId, "g391-40");
  assert.ok(ordinaryMass > 0.99 && ordinaryMass <= 1.000001);

  const highSigma = grid.resolveTheoreticalCells(center.lat, center.lon, 500);
  const highSigmaMass = highSigma.reduce((sum, candidate) => sum + candidate.weight, 0);
  assert.ok(highSigma.length > 0 && highSigma.length <= 25);
  assert.ok(highSigmaMass > 0 && highSigmaMass < 0.95);

  const boundary = grid.resolveTheoreticalCells(
    center.lat + Math.abs(grid.B_LAT) / 2,
    center.lon + Math.abs(grid.B_LON) / 2,
    5,
  );
  assert.ok(boundary.length >= 4);
  assert.ok(boundary[0].weight < 0.5);
});

test("route evidence is server inferred and sigma can only expand", () => {
  assert.equal(grid.inferGeocodeRoute(false, "GSI_JUKYO_BASE_NUMBER"), "GSI_JUKYO_BASE_NUMBER");
  assert.equal(grid.inferGeocodeRoute(true, "PROPERTY_PAGE_ADDRESS"), "USER_COORDINATE");
  assert.equal(grid.boundedGeocodeSigmaM("GSI_JUKYO_BASE_NUMBER", 1), 50);
  assert.equal(grid.boundedGeocodeSigmaM("PROPERTY_PAGE_ADDRESS", 1), 65);
  assert.equal(grid.boundedGeocodeSigmaM("USER_COORDINATE", 1), 5);
  assert.equal(grid.boundedGeocodeSigmaM("GSI_JUKYO_BASE_NUMBER", 120), 120);
});

const observation = (overrides = {}) => ({
  distanceM: 400,
  triggered: true,
  decisionStatus: "fail",
  thresholdStatus: "inside_threshold",
  thresholdM: 500,
  coverageState: "complete",
  ...overrides,
});

test("selected policy threshold is authoritative and inclusive", () => {
  assert.equal(policy.classifyPolicyObservation(observation(), 300), "clear");
  assert.equal(policy.classifyPolicyObservation(observation(), 500), "hard_veto");
  assert.equal(policy.classifyPolicyObservation(observation(), 650), "hard_veto");
  assert.equal(policy.classifyPolicyObservation(observation({ distanceM: 500 }), 500), "hard_veto");
  assert.equal(
    policy.classifyPolicyObservation(observation({
      distanceM: 600,
      triggered: null,
      decisionStatus: "unknown",
      thresholdStatus: "outside_threshold",
      coverageState: "source_limited",
    }), 500),
    "review",
  );
  assert.equal(
    policy.classifyPolicyObservation(observation({
      distanceM: 600,
      triggered: false,
      decisionStatus: "pass_current_evidence",
      thresholdStatus: "outside_threshold",
    }), 500),
    "clear",
  );
  assert.equal(
    policy.classifyPolicyObservation(observation({ distanceM: null }), 300),
    "review",
  );
  assert.equal(
    policy.classifyPolicyObservation(observation({ distanceM: null }), 500),
    "hard_veto",
  );
});

test("shrine is excluded by default and included only by explicit policy", () => {
  assert.equal(policy.activeHardFactors(false).includes("shrine"), false);
  assert.equal(policy.activeHardFactors(true).includes("shrine"), true);
  assert.deepEqual(policy.activeHardFactors(false), [
    "temple",
    "cemetery",
    "large_hospital",
    "strong_history",
    "p8",
  ]);
});

function decision(status = "pass") {
  return {
    status,
    eligible: status !== "out_of_scope",
    hardVeto: false,
    hardGates: [],
    reviews: [],
    summary: "base",
  };
}

function resolution(status, coveredWeight) {
  return {
    primaryCellId: status === "NO_VALID_CELL" ? null : "g391-40",
    coverage: {
      status,
      coveredWeight,
      returnedTheoreticalWeight: coveredWeight,
      rejectedWeight: 0,
      omittedWeight: 1 - coveredWeight,
      note: "fixture",
    },
  };
}

test("PARTIAL and runtime-unavailable coverage can never pass", () => {
  const partial = coverage.applyResolutionCoverageGate(decision("pass"), resolution("PARTIAL", 0.8));
  assert.equal(partial.status, "review");
  assert.equal(partial.eligible, true);
  assert.ok(partial.reviews.some((finding) => finding.factor === "location_coverage"));

  const unavailable = coverage.applyResolutionCoverageGate(
    decision("out_of_scope"),
    resolution("RUNTIME_UNAVAILABLE", 0),
  );
  assert.equal(unavailable.status, "review");
  assert.equal(unavailable.eligible, false);
  assert.match(unavailable.summary, /release/);

  const outside = coverage.applyResolutionCoverageGate(
    decision("out_of_scope"),
    resolution("NO_VALID_CELL", 0),
  );
  assert.equal(outside.status, "out_of_scope");
  assert.ok(outside.reviews.some((finding) => finding.factor === "location_coverage"));
});

test("address evidence requires exact town stem and complete number tuple", () => {
  assert.equal(address.hasPointAddressPrecision("東京都新宿区"), false);
  assert.equal(address.hasPointAddressPrecision("東京都新宿区西新宿2丁目8-1"), true);
  assert.equal(
    address.addressEvidenceIsConsistent(
      "東京都新宿区西新宿2丁目8-1",
      "東京都新宿区西新宿二丁目8番1号",
    ),
    true,
  );
  assert.equal(
    address.addressEvidenceIsConsistent(
      "東京都新宿区西新宿1丁目2番",
      "東京都新宿区西新宿11丁目22番",
    ),
    false,
  );
  assert.equal(
    address.addressEvidenceIsConsistent(
      "東京都港区六本木1丁目2番3号",
      "東京都港区六本木一丁目2-3",
    ),
    true,
  );
  assert.equal(
    address.addressEvidenceIsConsistent(
      "東京都港区六本木1丁目2番3号",
      "東京都港区三田1丁目2番3号",
    ),
    false,
  );
});

test("SSRF classifier rejects mapped IPv4 and reserved IPv6", () => {
  for (const value of [
    "127.0.0.1",
    "::ffff:127.0.0.1",
    "::ffff:7f00:1",
    "0:0:0:0:0:ffff:7f00:1",
    "ff02::1",
    "100::1",
    "2001:db8::1",
    "64:ff9b::7f00:1",
    "64:ff9b:1::1",
    "100:0:0:1::1",
    "2001:2::1",
    "2001:5::1",
    "2002::1",
    "3fff::1",
    "5f00::1",
    "4000::1",
    "6000::1",
    "8000::1",
  ]) assert.equal(network.isPrivateOrLocalAddress(value), true, value);
  assert.equal(network.isPrivateOrLocalAddress("8.8.8.8"), false);
  assert.equal(network.isPrivateOrLocalAddress("2606:4700:4700::1111"), false);
});

test("snapshot HMAC rejects tampering", () => {
  const secret = "0123456789abcdef0123456789abcdef";
  const payload = { candidateId: "candidate_a", decision: { status: "review" } };
  const signature = snapshot.createSnapshotSignature(payload, secret);
  assert.equal(snapshot.snapshotSignatureMatches(payload, secret, signature), true);
  assert.equal(
    snapshot.snapshotSignatureMatches(
      { candidateId: "candidate_a", decision: { status: "pass" } },
      secret,
      signature,
    ),
    false,
  );
});

test("candidate ordinal and client id keep duplicate units distinct", () => {
  const base = { address: "東京都新宿区西新宿2丁目8-1", layout: "1LDK", clientCandidateId: "saved-a" };
  const first = identity.createCandidateId({ ...base, candidateOrdinal: 0 });
  const second = identity.createCandidateId({ ...base, candidateOrdinal: 1 });
  assert.notEqual(first, second);

  const rows = ordering.buildComparisonOrdering([
    {
      candidateId: first,
      clientCandidateId: "saved-a",
      candidateOrdinal: 0,
      sourceRank: null,
      tier: "review",
      summary: "A",
      hardGateCount: 0,
      reviewCount: 1,
    },
    {
      candidateId: second,
      clientCandidateId: "saved-b",
      candidateOrdinal: 1,
      sourceRank: null,
      tier: "review",
      summary: "B",
      hardGateCount: 0,
      reviewCount: 1,
    },
  ]);
  assert.deepEqual(rows.map((row) => row.displayOrder), [1, 2]);
  assert.deepEqual(rows.map((row) => row.rank), [null, null]);
  assert.deepEqual(rows.map((row) => row.tie), [true, true]);
  assert.deepEqual(rows.map((row) => row.clientCandidateId), ["saved-a", "saved-b"]);
});

test("profile layers retain rich V15 and RYUMYAK runtime objects", async () => {
  const runtime = await load("app/lib/integrated-data/runtime.ts");
  await runtime.ensureIntegratedReleaseReady();
  const record = await runtime.lookupIntegratedCell("g391-40");
  assert.ok(record);
  const layers = profileShape.materializeProfileLayers(record);
  assert.equal(typeof layers.V15_3, "object");
  assert.equal(typeof layers.RYUMYAK, "object");
  assert.equal(layers.V15_3.regime, "HILL_RIDGE");
  assert.equal(layers.RYUMYAK.zone, "YOKOHAMA-Z0119");
  assert.equal(layers.RYUMYAK.rank, 197);
  assert.equal(typeof layers.ORBIT, "object");
  assert.equal(typeof layers.R3_PERSONAL_GATE, "object");
  assert.equal(typeof layers.HISTORY_P8, "object");
  assert.equal(typeof layers.LEGACY_CONTEXT, "object");
});
test("address precision rejects chome-only and preserves component kinds", () => {
  assert.equal(address.hasPointAddressPrecision("東京都新宿区西新宿2丁目"), false);
  assert.equal(address.hasPointAddressPrecision("東京都新宿区西新宿2丁目8番1号"), true);
  assert.equal(
    address.addressEvidenceIsConsistent(
      "東京都新宿区西新宿2番地",
      "東京都新宿区西新宿2丁目",
    ),
    false,
  );
  assert.equal(
    address.addressEvidenceIsConsistent(
      "東京都新宿区西新宿2丁目8番1号",
      "東京都新宿区西新宿2丁目9番1号",
    ),
    false,
  );
});

test("factor aggregation emits one union result with nearest trigger and covered weight", () => {
  const baseObservation = {
    distanceM: 700,
    triggered: false,
    decisionStatus: "pass_current_evidence",
    thresholdStatus: "outside_threshold",
    thresholdM: 500,
    coverageState: "complete",
  };
  const candidates = Array.from({ length: 25 }, (_, index) => ({
    cellId: `g1-${index}`,
    weight: 0.04,
    observation: index < 7
      ? { ...baseObservation, distanceM: 100 + index * 10, triggered: true, decisionStatus: "fail", thresholdStatus: "inside_threshold" }
      : baseObservation,
  }));
  const result = policy.aggregatePolicyObservations(candidates, 500);
  assert.equal(result.classification, "hard_veto");
  assert.equal(result.affectedCellCount, 7);
  assert.equal(result.evaluatedCellCount, 25);
  assert.equal(result.cellId, "g1-0");
  assert.equal(result.distanceM, 100);
  assert.ok(Math.abs(result.affectedWeight - 0.28) < 1e-9);
});

test("full assessment material signs profile, HCL, release and comparison token", () => {
  const secret = "0123456789abcdef0123456789abcdef";
  const assessment = {
    schemaVersion: "iyashiro-assessment/3.0",
    candidateId: "candidate-a",
    sourceCandidateId: null,
    clientCandidateId: "saved-a",
    candidateOrdinal: null,
    generatedAt: "2026-08-23T00:00:00.000Z",
    evidenceRelease: { releaseId: "release-a", sha256: "abc", dataContract: "integrated-cell-profile/3.0" },
    property: { address: "東京都新宿区西新宿2丁目8番1号" },
    resolution: { coverage: { status: "VALIDATED" } },
    profile: { cell: { sourceRank: null } },
    candidateCellProfiles: [{ cellId: "g1-1", weight: 1, profile: { cell: { sourceRank: null } } }],
    policy: { distanceThresholdM: 500, includeShrines: false },
    decision: { status: "review" },
    houseCompass: { report: { tests: ["T01"] } },
    comparisonToken: "ct1.payload.signature",
    disclaimer: "fixture",
  };
  const material = snapshot.assessmentSnapshotMaterial(assessment);
  const signature = snapshot.createSnapshotSignature(material, secret);
  assert.equal(snapshot.snapshotSignatureMatches(material, secret, signature), true);
  for (const changed of [
    { ...assessment, profile: { cell: { sourceRank: 1 } } },
    { ...assessment, houseCompass: { report: { tests: ["T10"] } } },
    { ...assessment, evidenceRelease: { ...assessment.evidenceRelease, releaseId: "release-b" } },
  ]) {
    assert.equal(
      snapshot.snapshotSignatureMatches(snapshot.assessmentSnapshotMaterial(changed), secret, signature),
      false,
    );
  }
});

test("compact comparison token is bounded for 20 candidates and rejects tampering", () => {
  const secret = "0123456789abcdef0123456789abcdef";
  const payload = {
    schemaVersion: "iyashiro-comparison-candidate/1.0",
    evidenceRelease: { releaseId: "release-a", dataContract: "integrated-cell-profile/3.0" },
    padding: "x".repeat(1_000),
  };
  const token = comparisonToken.encodeComparisonToken(payload, secret);
  const decoded = comparisonToken.decodeComparisonToken(token, secret);
  assert.equal(decoded.ok, true);
  if (decoded.ok) assert.deepEqual(decoded.payload, payload);
  const tampered = token.slice(0, -1) + (token.endsWith("a") ? "b" : "a");
  assert.equal(comparisonToken.decodeComparisonToken(tampered, secret).ok, false);
  const maximumRequestBytes = Buffer.byteLength(JSON.stringify({
    tokens: Array(20).fill("x".repeat(comparisonToken.MAX_COMPARISON_TOKEN_WIRE_BYTES)),
    policy: { distanceThresholdM: 500, includeShrines: false },
  }));
  assert.ok(maximumRequestBytes < 2 * 1024 * 1024, maximumRequestBytes);
});

test("listing URL credential and fragment are classified before reflection", () => {
  assert.equal(listingSafety.containsReflectedUrlSecret(new URL("https://user:pass@suumo.jp/item")), true);
  assert.equal(listingSafety.containsReflectedUrlSecret(new URL("https://suumo.jp/item#access_token=secret")), true);
  assert.equal(listingSafety.containsReflectedUrlSecret(new URL("https://suumo.jp/item?access_token=secret")), true);
  assert.equal(listingSafety.containsReflectedUrlSecret(new URL("https://suumo.jp/item?session-id=secret")), true);
  assert.equal(listingSafety.containsReflectedUrlSecret(new URL("https://suumo.jp/item?id=123")), false);
});


test("coarse property-page address can be refined only by same-town point address", () => {
  assert.equal(
    address.addressEvidenceCanBeRefinedBy(
      "東京都新宿区西新宿2丁目",
      "東京都新宿区西新宿2丁目8番1号",
    ),
    true,
  );
  assert.equal(
    address.addressEvidenceCanBeRefinedBy(
      "東京都新宿区西新宿2丁目",
      "東京都新宿区西新宿3丁目8番1号",
    ),
    false,
  );
  assert.equal(
    address.addressEvidenceCanBeRefinedBy(
      "東京都新宿区西新宿2丁目8番1号",
      "東京都新宿区西新宿2丁目9番1号",
    ),
    false,
  );
});

test("preview automation secret is HKDF-separated and never enabled in production", () => {
  const dedicated = "d".repeat(32);
  assert.equal(
    comparisonSecret.comparisonSigningSecret({
      IYASHIRO_COMPARE_SNAPSHOT_SECRET: dedicated,
      VERCEL_ENV: "production",
    }),
    dedicated,
  );
  const base = {
    VERCEL_ENV: "preview",
    VERCEL_AUTOMATION_BYPASS_SECRET: "a".repeat(32),
    VERCEL_PROJECT_ID: "prj_iyashiro",
    VERCEL_URL: "preview-a.example.vercel.app",
  };
  const first = comparisonSecret.comparisonSigningSecret(base);
  const repeated = comparisonSecret.comparisonSigningSecret(base);
  const otherDeployment = comparisonSecret.comparisonSigningSecret({
    ...base,
    VERCEL_URL: "preview-b.example.vercel.app",
  });
  assert.ok(first && first.length === 64);
  assert.equal(first, repeated);
  assert.notEqual(first, base.VERCEL_AUTOMATION_BYPASS_SECRET);
  assert.notEqual(first, otherDeployment);
  assert.equal(comparisonSecret.comparisonSigningSecret({
    ...base,
    VERCEL_ENV: "production",
  }), null);
  assert.equal(comparisonSecret.comparisonSigningSecret({
    ...base,
    VERCEL_PROJECT_ID: undefined,
    VERCEL_PROJECT_PRODUCTION_URL: undefined,
  }), null);
});

test("release identity derives a stable digest and rejects stale evidence", () => {
  const current = releaseIdentity.evidenceReleaseFromMetadata({
    releaseId: "release-current",
    generatedAt: "2026-08-23T00:00:00.000Z",
    sources: [{ project: "R3", version: "3" }],
  });
  const reordered = releaseIdentity.evidenceReleaseFromMetadata({
    sources: [{ version: "3", project: "R3" }],
    generatedAt: "2026-08-23T00:00:00.000Z",
    releaseId: "release-current",
  });
  assert.match(current.sha256, /^[a-f0-9]{64}$/);
  assert.equal(current.sha256, reordered.sha256);
  assert.equal(releaseIdentity.evidenceReleaseMatchesCurrent(current, current), true);
  assert.equal(
    releaseIdentity.evidenceReleaseMatchesCurrent(
      { ...current, releaseId: "release-old" },
      current,
    ),
    false,
  );
  assert.equal(
    releaseIdentity.evidenceReleaseMatchesCurrent(
      { ...current, sha256: "0".repeat(64) },
      current,
    ),
    false,
  );
});

test("compact token is 24-hour bounded and contains no URL, memo, or HCL raw input", () => {
  const now = Date.parse("2026-08-23T00:00:00.000Z");
  assert.equal(
    comparisonToken.comparisonTokenWindowIsValid(
      now,
      now + comparisonToken.COMPARISON_TOKEN_TTL_MS,
      now,
    ),
    true,
  );
  assert.equal(
    comparisonToken.comparisonTokenWindowIsValid(
      now,
      now + comparisonToken.COMPARISON_TOKEN_TTL_MS + 1,
      now,
    ),
    false,
  );
  assert.equal(comparisonToken.comparisonTokenWindowIsValid(now, now, now), false);

  const minimal = {
    schemaVersion: "iyashiro-comparison-candidate/1.1",
    candidateId: "candidate-a",
    clientCandidateId: "saved-a",
    generatedAt: "2026-08-23T00:00:00.000Z",
    expiresAt: "2026-08-24T00:00:00.000Z",
    evidenceRelease: {
      releaseId: "release-current",
      sha256: "a".repeat(64),
      dataContract: "integrated-cell-profile/3.0",
    },
    property: { name: "候補A", address: "東京都新宿区西新宿2丁目8番1号" },
    resolution: {
      primaryCellId: "g391-40",
      coverage: { status: "VALIDATED", coveredWeight: 1, note: "complete" },
    },
    candidateCells: [{ cellId: "g391-40", weight: 1, profileAvailable: true }],
    policy: {
      id: "R3_DEFAULT",
      distanceThresholdM: 500,
      includeShrines: false,
      hardGateNonCompensatory: true,
      unknownDisposition: "review",
    },
    decision: { status: "review", hardGates: [], reviews: [], summary: "review" },
    rankingBasis: { id: "source_first_area_rank", scope: "area_family", rank: null, evidence: "unknown" },
  };
  const encoded = comparisonToken.encodeComparisonToken(
    minimal,
    "0123456789abcdef0123456789abcdef",
  );
  const decoded = comparisonToken.decodeComparisonToken(
    encoded,
    "0123456789abcdef0123456789abcdef",
  );
  assert.equal(decoded.ok, true);
  if (decoded.ok) {
    const serialized = JSON.stringify(decoded.payload);
    for (const forbidden of [
      "propertyUrl",
      "requestedUrl",
      "finalUrl",
      "memo",
      "houseCompass",
      "birthDate",
      "birthTime",
      "currentAddress",
      "concerns",
    ]) assert.equal(serialized.includes(forbidden), false, forbidden);
  }
  assert.ok(Buffer.byteLength(encoded) < comparisonToken.MAX_COMPARISON_TOKEN_WIRE_BYTES);
});
