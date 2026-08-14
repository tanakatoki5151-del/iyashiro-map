import test from "node:test";
import assert from "node:assert/strict";
import {
  evaluateFeaturesForAddress,
  geometryDistanceMeters,
} from "./feature-distance-core.mjs";

const query = { lat: 35.67, lon: 139.68 };

test("point distance is classified into 300/500 but not 100", () => {
  const northAbout180m = [139.68, 35.67162];
  const result = evaluateFeaturesForAddress(query, [
    {
      featureId: "f-point",
      lane: "LOST_TABOO",
      subtype: "fixture",
      geometry: { type: "Point", coordinates: northAbout180m },
      publicSummary: "test",
    },
  ]);

  assert.equal(result.byRadius["100"].length, 0);
  assert.equal(result.byRadius["300"].length, 1);
  assert.equal(result.byRadius["500"].length, 1);
  assert.ok(result.matches[0].distanceM > 150);
  assert.ok(result.matches[0].distanceM < 220);
});

test("query inside polygon has exact distance zero", () => {
  const polygon = {
    type: "Polygon",
    coordinates: [[
      [139.6795, 35.6695],
      [139.6805, 35.6695],
      [139.6805, 35.6705],
      [139.6795, 35.6705],
      [139.6795, 35.6695],
    ]],
  };
  assert.equal(geometryDistanceMeters(query, polygon), 0);
});

test("polygon hole is treated as outside the feature", () => {
  const polygon = {
    type: "Polygon",
    coordinates: [
      [
        [139.6790, 35.6690],
        [139.6810, 35.6690],
        [139.6810, 35.6710],
        [139.6790, 35.6710],
        [139.6790, 35.6690],
      ],
      [
        [139.6798, 35.6698],
        [139.6802, 35.6698],
        [139.6802, 35.6702],
        [139.6798, 35.6702],
        [139.6798, 35.6698],
      ],
    ],
  };
  assert.ok(geometryDistanceMeters(query, polygon) > 0);
});

test("candidate prefilter false positives are removed by exact distance", () => {
  const result = evaluateFeaturesForAddress(query, [
    {
      featureId: "near",
      lane: "FOLKLORE",
      geometry: { type: "Point", coordinates: [139.6802, 35.6701] },
    },
    {
      featureId: "far",
      lane: "PHYSICAL",
      geometry: { type: "Point", coordinates: [139.69, 35.68] },
    },
  ]);
  assert.deepEqual(result.matches.map((x) => x.featureId), ["near"]);
});

test("public response does not spread raw/private research fields", () => {
  const result = evaluateFeaturesForAddress(query, [
    {
      featureId: "privacy",
      lane: "MODERN_INCIDENTS",
      geometry: { type: "Point", coordinates: [139.68, 35.67] },
      publicSummary: "event class only",
      personName: "MUST_NOT_LEAK",
      apartmentUnit: "MUST_NOT_LEAK",
      rawSourcePayload: "MUST_NOT_LEAK",
    },
  ]);
  const json = JSON.stringify(result);
  assert.equal(json.includes("MUST_NOT_LEAK"), false);
  assert.equal(json.includes("personName"), false);
  assert.equal(json.includes("apartmentUnit"), false);
  assert.equal(json.includes("rawSourcePayload"), false);
});

test("unsupported geometry fails closed", () => {
  assert.throws(
    () => geometryDistanceMeters(query, { type: "GeometryCollection", geometries: [] }),
    /unsupported geometry/,
  );
});
