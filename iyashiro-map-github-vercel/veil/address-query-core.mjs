import { VEIL_LANES, geometryDistanceMeters } from "./feature-distance-core.mjs";

const PUBLIC_STATUSES = new Set([
  "confirmed_positive",
  "source_backed_review",
  "defined_sources_no_hit",
  "source_access_pending",
  "unknown",
  "not_measured",
  "not_searched",
  "false_positive_for_target",
  "context_only",
]);

const COUNTABLE_CONFIRMED = new Set(["confirmed_positive"]);
const COUNTABLE_CANDIDATE = new Set(["source_backed_review"]);
const NON_COUNTING = new Set(["context_only", "false_positive_for_target"]);

const LANE_PUBLIC_FIELDS = Object.freeze({
  FOLKLORE: [
    "featureId", "globalFeatureId", "subtype", "publicTitle", "publicSummary",
    "earliestSourcePeriod", "sourceFamilyCount", "geometryRole", "matchClass",
    "distanceMeters", "spatialConfidence", "historicalToponymCrosswalkStatus",
    "reviewStatus", "sourcePointers", "nearestRing",
  ],
  MODERN_INCIDENTS: [
    "featureId", "globalFeatureId", "eventType", "publicDateOrPeriod", "publicSummary",
    "matchClass", "distanceMeters", "spatialConfidence", "independentSourceFamilyCount",
    "reviewStatus", "sourcePointers", "nearestRing",
  ],
  LOST_TABOO: [
    "featureId", "globalFeatureId", "subtype", "publicTitle", "publicSummary",
    "historicalOriginalPeriod", "geometryRole", "relocationChainSummary", "matchClass",
    "distanceMeters", "errorBufferMeters", "spatialConfidence", "reviewStatus",
    "sourcePointers", "nearestRing",
  ],
  PHYSICAL: [
    "featureId", "globalFeatureId", "measurementSeriesId", "measurementType", "valueOrClass",
    "unit", "sourceNativeResolution", "sampleMethod", "observationEpoch", "distanceToObservation",
    "spatialInterpretation", "sourcePointer", "nearestRing",
  ],
});

function asStringArray(value, name) {
  if (!Array.isArray(value)) throw new Error(`${name} must be an array`);
  const result = value.map((x) => String(x));
  if (result.some((x) => !/^g\d+-\d+$/.test(x))) throw new Error(`invalid ${name} cellId`);
  return [...new Set(result)];
}

function validateFeature(feature) {
  if (!feature || typeof feature !== "object") throw new Error("feature object required");
  if (typeof feature.featureId !== "string" || !feature.featureId) throw new Error("featureId required");
  if (!VEIL_LANES.includes(feature.lane)) throw new Error(`invalid VEIL lane: ${feature.lane}`);
  if (!feature.geometry) throw new Error("feature geometry required");
  if (!PUBLIC_STATUSES.has(feature.reviewStatus ?? feature.evidenceStatus ?? "unknown")) {
    throw new Error(`invalid review/evidence status for ${feature.featureId}`);
  }
  if (typeof feature.independenceGroup !== "string" || !feature.independenceGroup) {
    throw new Error(`independenceGroup required for ${feature.featureId}`);
  }
  if (!Array.isArray(feature.spatialIndexCellIds) || feature.spatialIndexCellIds.length === 0) {
    throw new Error(`spatialIndexCellIds required for ${feature.featureId}`);
  }

  const accuracy = feature.locationAccuracy ?? feature.spatialConfidence ?? null;
  if (
    feature.lane === "MODERN_INCIDENTS" &&
    accuracy === "town_chome_only" &&
    ["building_match", "parcel_or_feature_match"].includes(feature.matchClass)
  ) {
    throw new Error(`town-chome incident cannot be promoted to precise match: ${feature.featureId}`);
  }
  if (
    feature.lane === "LOST_TABOO" &&
    ["current_memorial", "current_shrine", "relocated_current"].includes(feature.geometryRole) &&
    feature.historicalOriginalLocation === true
  ) {
    throw new Error(`current location cannot be asserted as historical original: ${feature.featureId}`);
  }
}

function normalizeFeature(feature) {
  validateFeature(feature);
  const spatialIndexCellIds = asStringArray(feature.spatialIndexCellIds, "spatialIndexCellIds");
  const targetCellIds = feature.targetCellIds ? asStringArray(feature.targetCellIds, "targetCellIds") : [];
  const errorBandCellIds = feature.errorBandCellIds ? asStringArray(feature.errorBandCellIds, "errorBandCellIds") : [];

  let spatialInterpretation = feature.spatialInterpretation ?? null;
  if (feature.lane === "PHYSICAL") {
    const resolution = Number(feature.sourceNativeResolutionMeters ?? feature.sourceNativeResolution ?? NaN);
    if (Number.isFinite(resolution) && resolution > 100) spatialInterpretation = "area_context";
  }

  return Object.freeze({
    ...feature,
    spatialIndexCellIds: Object.freeze(spatialIndexCellIds),
    targetCellIds: Object.freeze(targetCellIds),
    errorBandCellIds: Object.freeze(errorBandCellIds),
    spatialInterpretation,
  });
}

function normalizeCoverage(coverageByLane = {}) {
  return Object.fromEntries(VEIL_LANES.map((lane) => {
    const raw = coverageByLane[lane] ?? {};
    return [lane, Object.freeze({
      coverageStatus: raw.coverageStatus ?? (lane === "PHYSICAL" ? "not_measured" : "not_searched"),
      sourceCoveragePeriod: raw.sourceCoveragePeriod ?? null,
      sourceFamiliesChecked: Object.freeze([...(raw.sourceFamiliesChecked ?? [])]),
      lastDatasetVersion: raw.lastDatasetVersion ?? null,
    })];
  }));
}

export function createVeilFeatureStore(features = [], options = {}) {
  if (!Array.isArray(features)) throw new Error("features must be an array");
  const byId = new Map();
  const byCell = new Map();
  for (const input of features) {
    const feature = normalizeFeature(input);
    if (byId.has(feature.featureId)) throw new Error(`duplicate featureId: ${feature.featureId}`);
    byId.set(feature.featureId, feature);
    for (const cellId of feature.spatialIndexCellIds) {
      const ids = byCell.get(cellId) ?? [];
      ids.push(feature.featureId);
      byCell.set(cellId, ids);
    }
  }
  const coverage = normalizeCoverage(options.coverageByLane);
  const versions = Object.freeze({
    veilDatasetVersion: options.veilDatasetVersion ?? "fixture-unversioned",
    sourceRegistryVersion: options.sourceRegistryVersion ?? "unknown",
    publicSummarySchemaVersion: options.publicSummarySchemaVersion ?? "1",
  });

  return Object.freeze({
    retrieveByCellIds(cellIds) {
      const seen = new Set();
      const result = [];
      for (const cellId of cellIds) {
        for (const id of byCell.get(cellId) ?? []) {
          if (seen.has(id)) continue;
          seen.add(id);
          result.push(byId.get(id));
        }
      }
      return result;
    },
    coverageForLane(lane) {
      return coverage[lane];
    },
    versions,
    featureCount: byId.size,
  });
}

function nearestRingForFeature(feature, targetCellId, distanceMeters, radiiM) {
  if (feature.targetCellIds.includes(targetCellId)) return "TARGET";
  if (feature.errorBandCellIds.includes(targetCellId)) return "TARGET_ERROR_BAND";
  return radiiM.find((radius) => distanceMeters <= radius + 1e-9) ?? null;
}

function publicFeature(feature, distanceMeters, nearestRing) {
  const derived = {
    ...feature,
    distanceMeters,
    distanceToObservation: distanceMeters,
    nearestRing,
    reviewStatus: feature.reviewStatus ?? feature.evidenceStatus ?? "unknown",
  };
  const allowlist = LANE_PUBLIC_FIELDS[feature.lane];
  const result = {};
  for (const key of allowlist) result[key] = derived[key] ?? null;
  return result;
}

function laneStatus(features, coverageStatus) {
  if (features.some((f) => f.reviewStatus === "confirmed_positive")) return "confirmed_positive";
  if (features.some((f) => f.reviewStatus === "source_backed_review")) return "source_backed_review";
  if (coverageStatus === "complete_for_defined_sources") return "defined_sources_no_hit";
  if (coverageStatus === "source_access_pending") return "source_access_pending";
  if (coverageStatus === "not_measured") return "not_measured";
  if (coverageStatus === "not_searched") return "not_searched";
  return "unknown";
}

function countByRing(features) {
  const counts = { TARGET: 0, TARGET_ERROR_BAND: 0, "100": 0, "300": 0, "500": 0 };
  for (const feature of features) {
    const key = String(feature.nearestRing);
    if (Object.hasOwn(counts, key)) counts[key] += 1;
  }
  return counts;
}

function convergenceForFeatures(internalMatches) {
  const groups = new Map();
  for (const match of internalMatches) {
    const status = match.reviewStatus ?? match.evidenceStatus ?? "unknown";
    if (NON_COUNTING.has(status)) continue;
    const existing = groups.get(match.independenceGroup) ?? {
      independenceGroup: match.independenceGroup,
      featureIds: [],
      lanes: new Set(),
      confirmed: false,
      candidate: false,
    };
    existing.featureIds.push(match.featureId);
    existing.lanes.add(match.lane);
    if (COUNTABLE_CONFIRMED.has(status)) existing.confirmed = true;
    if (COUNTABLE_CANDIDATE.has(status)) existing.candidate = true;
    groups.set(match.independenceGroup, existing);
  }

  const series = [...groups.values()].map((group) => ({
    seriesId: group.independenceGroup,
    featureIds: [...new Set(group.featureIds)],
    lanes: [...group.lanes].sort(),
    status: group.confirmimed ? "confirmed" : group.candidate ? "candidate" : "context_only",
  }));
  const confirmed = series.filter((s) => s.status === "confirmed").length;
  const candidate = series.filter((s) => s.status === "candidate").length;
  const independentSeriesCount = confirmed + candidate;
  return {
    independentSeriesCount,
    confirmedIndependentSeriesCount: confirmed,
    candidateIndependentSeriesCount: candidate,
    series,
    convergenceStatus:
      confirmed >= 2 ? "confirmed" :
      confirmed + candidate >= 2 ? "candidate" :
      independentSeriesCount === 0 ? "none" : "context_only",
  };
}

function regionForMunicipalityIndex(index) {
  if (index >= 1 && index <= 23) return "Tokyo23";
  if (index >= 24 && index <= 41) return "Yokohama";
  if (index >= 42 && index <= 48) return "Kawasaki";
  return "unknown";
}

export function queryVeilPoint(
  {
    lat,
    lon,
    rawInput = null,
    normalizedAddress = null,
    geocodePrecision = "coordinate",
    geocoderVersion = null,
  },
  {
    resolver,
    store,
    spatialCoreVersion = "regional-catalog-v4",
    spatialCoreSha,
    radiiM = [100, 300, 500],
  },
) {
  if (!resolver || !store) throw new Error("resolver and store are required");
  const cell = resolver.resolvePoint(lat, lon);
  if (cell.status !== "ok") return { query: { rawInput, lat, lon }, cell };

  const normalizedRadii = [...new Set(radiiM)].sort((a, b) => a - b);
  const maxRadius = normalizedRadii.at(-1) ?? 500;
  const candidateCellIds = resolver.candidateCells(lat, lon, maxRadius).map((x) => x.cellId);
  const candidates = store.retrieveByCellIds(candidateCellIds);
  const internalMatches = [];
  const publicMatches = [];

  for (const feature of candidates) {
    const distanceMeters = geometryDistanceMeters({ lat, lon }, feature.geometry);
    const nearestRing = nearestRingForFeature(feature, cell.cellId, distanceMeters, normalizedRadii);
    if (nearestRing === null) continue;
    const internal = { ...feature, distanceMeters, nearestRing };
    internalMatches.push(internal);
    publicMatches.push({ lane: feature.lane, value: publicFeature(feature, distanceMeters, nearestRing) });
  }

  publicMatches.sort((a, b) => (a.value.distanceMeters ?? 0) - (b.value.distanceMeters ?? 0));
  const lanes = Object.fromEntries(VEIL_LANES.map((lane) => {
    const coverage = store.coverageForLane(lane);
    const featuresForLane = publicMatches.filter((x) => x.lane === lane).map((x) => x.value);
    return [lane, {
      status: laneStatus(featuresForLane, coverage.coverageStatus),
      ...coverage,
      featureCountByRing: countByRing(featuresForLane),
      features: featuresForLane,
    }];
  }));

  return {
    query: {
      rawInput,
      normalizedAddress,
      geocodeLatitude: lat,
      geocodeLongitude: lon,
      geocodePrecision,
      geocoderVersion,
    },
    cell: {
      cellId: cell.cellId,
      gridRow: cell.row,
      gridCol: cell.col,
      centerLatitude: cell.center.lat,
      centerLongitude: cell.center.lon,
      municipalityCode: cell.municipality.code,
      municipalityName: cell.municipality.name,
      region: regionForMunicipalityIndex(cell.municipality.index),
      spatialCoreVersion,
      spatialCoreSha,
    },
    lanes,
    convergence: convergenceForFeatures(internalMatches),
    ...store.versions,
  };
}
