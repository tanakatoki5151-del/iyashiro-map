import assert from "node:assert/strict";
import test from "node:test";

import { normalizeAssessment, requestComparison } from "../app/components/integration/api.ts";

function fact({ id, distanceM, coverageState = "complete", decisionStatus = "pass_current_evidence" }) {
  return {
    factId: id,
    coverage: { state: coverageState, absenceClaimAllowed: false, note: "fixture coverage" },
    finding: {
      status: coverageState === "complete" ? "confirmed" : "review",
      value: { distanceM, decisionStatus, nearestName: "fixture" },
    },
    policy: { defaultEffect: "hard_gate" },
    sources: [{ title: "fixture source" }],
  };
}

function payload({ threshold = 500, facts = [], decisionStatus = "review", layers = {} } = {}) {
  return {
    policy: { distanceThresholdM: threshold, includeShrines: false },
    decision: { status: decisionStatus, hardGates: [], reviews: [], summary: "fixture" },
    resolution: {
      query: { lat: 35.6, lon: 139.7 },
      primaryCellId: "g200-200",
      sigmaM: 35,
      coverage: { status: "PARTIAL", coveredWeight: 0.8, note: "fixture location coverage" },
    },
    profile: {
      cell: { cellId: "g200-200", center: { lat: 35.6, lon: 139.7 } },
      layers: { ORBIT: { availability: "available" }, ...layers },
      rankings: {
        sourceFirst: { rank: null, coverage: "unknown" },
        robustness: { rank: null, coverage: "unknown" },
        v15Pure: { rank: null, coverage: "unknown" },
        ryumyakPure: { rank: null, coverage: "unknown" },
      },
      facts,
    },
  };
}

function layer(view, id) {
  return view.layers.find((item) => item.id === id);
}

test("source-limited outside distance remains UNKNOWN and partial", () => {
  const view = normalizeAssessment(payload({
    threshold: 500,
    facts: [fact({ id: "temple", distanceM: 700, coverageState: "source_limited", decisionStatus: "unknown" })],
  }), "fixture");
  assert.equal(layer(view, "orbit").status, "unknown");
  assert.equal(layer(view, "orbit").availability, "partial");
});

test("selected threshold, not the source default threshold, controls layer veto", () => {
  const sourceFact = fact({ id: "temple", distanceM: 400, decisionStatus: "fail" });
  const at300 = normalizeAssessment(payload({ threshold: 300, facts: [sourceFact] }), "fixture");
  const at500 = normalizeAssessment(payload({ threshold: 500, facts: [sourceFact] }), "fixture");
  assert.notEqual(layer(at300, "orbit").status, "hard_veto");
  assert.equal(layer(at500, "orbit").status, "hard_veto");
});

test("R3 current-evidence and no-lens availability remain distinct", () => {
  const pass = normalizeAssessment(payload({
    layers: { R3_PERSONAL_GATE: { availability: "available", currentEvidenceDecision: "pass_current_evidence" } },
  }), "fixture");
  const missing = normalizeAssessment(payload({
    layers: { R3_PERSONAL_GATE: { availability: "unknown_no_lens_record", currentEvidenceDecision: "unknown" } },
  }), "fixture");
  assert.equal(layer(pass, "r3").status, "pass");
  assert.equal(layer(pass, "r3").availability, "available");
  assert.equal(layer(missing, "r3").status, "unknown");
  assert.equal(layer(missing, "r3").availability, "unknown");
});

test("all-null V15 object is unavailable and null ranks remain UNKNOWN", () => {
  const view = normalizeAssessment(payload({
    layers: { V15_3: { rank: null, zone: null, regime: null } },
  }), "fixture");
  assert.equal(layer(view, "v153").availability, "unavailable");
  assert.ok(view.rankings.every((ranking) => ranking.status === "unknown"));
});

test("out-of-scope and location coverage are preserved", () => {
  const view = normalizeAssessment(payload({ decisionStatus: "out_of_scope" }), "fixture");
  assert.equal(view.status, "out_of_scope");
  assert.equal(view.location.coverageStatus, "PARTIAL");
  assert.equal(view.location.coveredWeight, 0.8);
  assert.equal(view.location.coverageNote, "fixture location coverage");
});

test("comparison keeps candidate identity, null ranks, and failures visible", async () => {
  const originalFetch = globalThis.fetch;
  let submitted;
  globalThis.fetch = async (_input, init) => {
    submitted = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({
      requestedCount: 2,
      completedCount: 1,
      failedCount: 1,
      results: [{
        candidateId: "server-a",
        clientCandidateId: "local-a",
        property: { name: "候補A" },
      }],
      ordering: [{
        candidateId: "server-a",
        clientCandidateId: "local-a",
        candidateOrdinal: 0,
        displayOrder: 1,
        rank: null,
        sourceRank: null,
        tie: true,
        rankingBasis: "none_no_cell_addressable_source_first",
        tier: "review",
        reasons: ["fixture review"],
      }],
      failures: [{
        clientCandidateId: "local-b",
        candidateOrdinal: 1,
        error: "fixture_error",
        status: 422,
        message: "fixture failed",
      }],
      notes: [],
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const policy = { distanceThresholdM: 500, includeShrines: false };
  const candidates = [
    {
      localId: "local-a",
      label: "保存A",
      savedAt: "2026-08-23T00:00:00Z",
      request: { address: "A", policy },
      assessment: { raw: { schemaVersion: "iyashiro-assessment/3.0", comparisonToken: "token-a" } },
    },
    {
      localId: "local-b",
      label: "保存B",
      savedAt: "2026-08-23T00:00:00Z",
      request: { address: "B", policy },
      assessment: { raw: { schemaVersion: "iyashiro-assessment/3.0", comparisonToken: "token-b" } },
    },
  ];
  try {
    const view = await requestComparison(candidates);
    assert.deepEqual(submitted.tokens, ["token-a", "token-b"]);
    assert.equal(submitted.snapshots, undefined);
    assert.equal(submitted.candidates, undefined);
    assert.equal(view.rows[0].id, "local-a");
    assert.equal(view.rows[0].label, "候補A");
    assert.equal(view.rows[0].displayOrder, 1);
    assert.equal(view.rows[0].sourceRank, undefined);
    assert.equal(view.rows[0].tie, true);
    assert.equal(view.failures[0].label, "保存B");
    assert.equal(view.failures[0].message, "fixture failed");
    assert.match(view.summary[0], /1件失敗/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("repeated factors from weighted cells keep unique gate identities", () => {
  const input = payload();
  input.decision.hardGates = [
    { factor: "temple", reason: "cell a", cellId: "g1-1" },
    { factor: "temple", reason: "cell b", cellId: "g1-2" },
  ];
  const view = normalizeAssessment(input, "fixture");
  assert.equal(view.gates.length, 2);
  assert.equal(new Set(view.gates.map((gate) => gate.id)).size, 2);
});
