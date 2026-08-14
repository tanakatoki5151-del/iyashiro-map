import test from "node:test";
import assert from "node:assert/strict";
import { createVeilFeatureStore, queryVeilPoint } from "./address-query-core.mjs";

const resolver = {
  resolvePoint() {
    return {
      status: "ok",
      cellId: "g195-224",
      row: 195,
      col: 224,
      center: { lat: 35.664, lon: 139.677 },
      municipality: { index: 13, code: "13113", name: "渋谷区" },
    };
  },
  candidateCells() {
    return [
      { cellId: "g195-224" },
      { cellId: "g195-225" },
      { cellId: "g196-224" },
    ];
  },
};

const baseCoverage = {
  FOLKLORE: {
    coverageStatus: "complete_for_defined_sources",
    sourceFamiliesChecked: ["official_local_history"],
  },
  MODERN_INCIDENTS: { coverageStatus: "source_access_pending" },
  LOST_TABOO: { coverageStatus: "partial" },
  PHYSICAL: { coverageStatus: "not_measured" },
};

test("prefilter retrieval -> exact distance -> lane cards is one deterministic pipeline", () => {
  const store = createVeilFeatureStore([
    {
      featureId: "f1",
      lane: "FOLKLORE",
      geometry: { type: "Point", coordinates: [139.677, 35.664] },
      spatialIndexCellIds: ["g195-224"],
      targetCellIds: ["g195-224"],
      independenceGroup: "story-a",
      reviewStatus: "confirmed_positive",
      publicTitle: "fixture",
      publicSummary: "safe public text",
      sourcePointers: ["s1"],
    },
    {
      featureId: "f2",
      lane: "LOST_TABOO",
      geometry: { type: "Point", coordinates: [139.6775, 35.664] },
      spatialIndexCellIds: ["g195-224"],
      independenceGroup: "story-a",
      reviewStatus: "confirmed_positive",
      geometryRole: "historical_original",
      publicSummary: "same underlying chain",
      sourcePointers: ["s2"],
    },
    {
      featureId: "f3",
      lane: "MODERN_INCIDENTS",
      geometry: { type: "Point", coordinates: [139.68, 35.664] },
      spatialIndexCellIds: ["g195-225"],
      independenceGroup: "incident-b",
      reviewStatus: "source_backed_review",
      matchClass: "district_context",
      locationAccuracy: "town_chome_only",
      personName: "MUST_NOT_LEAK",
      apartmentUnit: "MUST_NOT_LEAK",
      rawSourcePayload: "MUST_NOT_LEAK",
      publicSummary: "event class only",
      sourcePointers: ["s3"],
    },
  ], {
    coverageByLane: baseCoverage,
    veilDatasetVersion: "fixture-v1",
    sourceRegistryVersion: "sr-v1",
    publicSummarySchemaVersion: "1",
  });

  const out = queryVeilPoint(
    { lat: 35.664, lon: 139.677 },
    { resolver, store, spatialCoreSha: "sha" },
  );
  assert.equal(out.lanes.FOLKLORE.status, "confirmed_positive");
  assert.equal(out.lanes.MODERN_INCIDENTS.status, "source_backed_review");
  assert.equal(out.lanes.PHYSICAL.status, "not_measured");
  assert.equal(out.lanes.FOLKLORE.features[0].nearestRing, "TARGET");
  assert.equal(out.convergence.independentSeriesCount, 2);
  assert.equal(out.convergence.confirmedIndependentSeriesCount, 1);
  assert.equal(out.convergence.candidateIndependentSeriesCount, 1);
  assert.equal(out.convergence.series.find((x) => x.seriesId === "story-a").featureIds.length, 2);

  const json = JSON.stringify(out);
  for (const privateTerm of [
    "MUST_NOT_LEAK", "personName", "apartmentUnit", "rawSourcePayload",
  ]) {
    assert.equal(json.includes(privateTerm), false);
  }
});

test("town-chome-only modern incident cannot become building/parcel hit", () => {
  assert.throws(() => createVeilFeatureStore([{
    featureId: "x",
    lane: "MODERN_INCIDENTS",
    geometry: { type: "Point", coordinates: [139.677, 35.664] },
    spatialIndexCellIds: ["g195-224"],
    independenceGroup: "x",
    reviewStatus: "source_backed_review",
    locationAccuracy: "town_chome_only",
    matchClass: "building_match",
  }]), /town-chome/);
});

test("current memorial cannot be asserted as historical original", () => {
  assert.throws(() => createVeilFeatureStore([{
    featureId: "x",
    lane: "LOST_TABOO",
    geometry: { type: "Point", coordinates: [139.677, 35.664] },
    spatialIndexCellIds: ["g195-224"],
    independenceGroup: "x",
    reviewStatus: "source_backed_review",
    geometryRole: "current_memorial",
    historicalOriginalLocation: true,
  }]), /historical original/);
});

test("coarse physical series is forced to area context", () => {
  const store = createVeilFeatureStore([{
    featureId: "p",
    lane: "PHYSICAL",
    geometry: { type: "Point", coordinates: [139.677, 35.664] },
    spatialIndexCellIds: ["g195-224"],
    independenceGroup: "p",
    reviewStatus: "context_only",
    measurementSeriesId: "m",
    measurementType: "mappedClass",
    sourceNativeResolutionMeters: 250,
    spatialInterpretation: "observed_anomaly",
  }], { coverageByLane: baseCoverage });
  const out = queryVeilPoint(
    { lat: 35.664, lon: 139.677 },
    { resolver, store, spatialCoreSha: "sha" },
  );
  assert.equal(out.lanes.PHYSICAL.features[0].spatialInterpretation, "area_context");
  assert.equal(out.convergence.independentSeriesCount, 0);
});

test("complete no-hit and source-access-pending remain distinct", () => {
  const store = createVeilFeatureStore([], { coverageByLane: baseCoverage });
  const out = queryVeilPoint(
    { lat: 35.664, lon: 139.677 },
    { resolver, store, spatialCoreSha: "sha" },
  );
  assert.equal(out.lanes.FOLKLORE.status, "defined_sources_no_hit");
  assert.equal(out.lanes.MODERN_INCIDENTS.status, "source_access_pending");
});
