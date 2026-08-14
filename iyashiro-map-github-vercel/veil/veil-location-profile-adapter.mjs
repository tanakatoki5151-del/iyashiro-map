import { geometryDistanceMeters, VEIL_LANES } from './feature-distance-core.mjs';

const DEFAULT_RADII = Object.freeze([100, 300, 500]);
const PUBLIC_FEATURE_FIELDS = Object.freeze([
  'featureId','lane','subtype','eventType','publicTitle','publicSummary','geometryRole',
  'evidenceStatus','geometryStatus','locationAccuracy','relationType','distanceMeters',
  'intersects','bufferClass','nearestRing','uncertaintyMeters','publicPrecision',
  'independenceGroup','canonicalSourceIdentity','sourcePointers','reviewStatus',
  'historicalToponymCrosswalkStatus','validFrom','validTo','sourceNativeResolutionMeters',
  'spatialInterpretation','globalFeatureId','globalEventId',
]);

function cloneAllowed(input) {
  return Object.fromEntries(PUBLIC_FEATURE_FIELDS.map((key) => [key, input[key] ?? null]));
}

function validateFeature(feature) {
  if (!feature || typeof feature.featureId !== 'string' || !feature.featureId) throw new Error('featureId required');
  if (!VEIL_LANES.includes(feature.lane)) throw new Error(`invalid VEIL lane: ${feature.lane}`);
  if (!feature.geometry) throw new Error('feature geometry required');
  if (!Array.isArray(feature.spatialMatches)) throw new Error('spatialMatches required');
}

export function createVeilFeatureStore(features) {
  if (!Array.isArray(features)) throw new TypeError('features must be an array');
  const byCell = new Map();
  const byId = new Map();
  for (const feature of features) {
    validateFeature(feature);
    if (byId.has(feature.featureId)) throw new Error(`duplicate featureId: ${feature.featureId}`);
    byId.set(feature.featureId, feature);
    for (const match of feature.spatialMatches) {
      if (!match || typeof match.cellId !== 'string') throw new Error('spatialMatch.cellId required');
      const bucket = byCell.get(match.cellId) ?? [];
      bucket.push(feature.featureId);
      byCell.set(match.cellId, bucket);
    }
  }
  return Object.freeze({
    retrieveByCells(cellIds) {
      const ids = new Set();
      for (const cellId of cellIds) for (const id of byCell.get(cellId) ?? []) ids.add(id);
      return [...ids].map((id) => byId.get(id));
    },
    size: byId.size,
  });
}

function validateQueryAnchor(anchor) {
  const required = ['anchorId','anchorType','lat','lng','precisionClass','source','acquiredAt'];
  for (const key of required) {
    if (anchor?.[key] === undefined || anchor?.[key] === null || anchor?.[key] === '') throw new Error(`queryAnchor.${key} required`);
  }
  if (!Number.isFinite(anchor.lat) || !Number.isFinite(anchor.lng)) throw new Error('queryAnchor coordinates must be finite');
  if (anchor.uncertaintyMeters != null && (!Number.isFinite(anchor.uncertaintyMeters) || anchor.uncertaintyMeters < 0)) {
    throw new Error('queryAnchor.uncertaintyMeters invalid');
  }
}

function nearestDistanceRing(distanceM, radiiM) {
  return radiiM.find((radius) => distanceM <= radius + 1e-9) ?? null;
}

function targetSpatialMatch(feature, cellId) {
  return feature.spatialMatches.find((m) => m.cellId === cellId) ?? null;
}

function isCoarsePhysical(feature) {
  return feature.lane === 'PHYSICAL' && Number.isFinite(feature.sourceNativeResolutionMeters) && feature.sourceNativeResolutionMeters > 100;
}

function publicizeFeature(feature, query, targetCellId, radiiM) {
  const distanceMeters = geometryDistanceMeters(query, feature.geometry);
  const spatial = targetSpatialMatch(feature, targetCellId);
  const coarseLocation = ['town_chome_only','district_context','historical_toponym_only'].includes(feature.locationAccuracy);
  const exactTarget = !coarseLocation && Boolean(spatial?.intersectsCell);
  const bufferedTarget = !coarseLocation && !exactTarget && Boolean(spatial?.errorBandIntersectsCell);
  const radius = nearestDistanceRing(distanceMeters, radiiM);
  if (!exactTarget && !bufferedTarget && radius === null) return null;

  let relationType = exactTarget ? 'intersects' : bufferedTarget ? 'buffer_intersects' : 'distance_only';
  let geometryRole = feature.geometryRole ?? null;
  let spatialInterpretation = feature.spatialInterpretation ?? null;
  let publicPrecision = feature.publicPrecision ?? feature.locationAccuracy ?? null;
  if (coarseLocation) {
    relationType = feature.locationAccuracy === 'historical_toponym_only' ? 'historical_toponym_context' : 'district_context';
    geometryRole = geometryRole ?? 'area_context';
    publicPrecision = feature.locationAccuracy;
  }
  if (isCoarsePhysical(feature)) {
    geometryRole = 'area_context';
    spatialInterpretation = 'area_context';
    publicPrecision = 'area_context';
  }

  const nearestRing = exactTarget || bufferedTarget ? 'target' : String(radius);
  return cloneAllowed({
    ...feature,
    geometryRole,
    relationType,
    distanceMeters,
    intersects: exactTarget,
    bufferClass: bufferedTarget ? 'accepted_error_band' : null,
    nearestRing,
    publicPrecision,
    spatialInterpretation,
  });
}

function cardStatus(features, coverageStatus) {
  if (features.some((f) => f.evidenceStatus === 'confirmed_positive')) return 'confirmed_positive';
  if (features.some((f) => f.evidenceStatus === 'source_backed_review')) return 'source_backed_review';
  return coverageStatus ?? 'unknown';
}

function buildLaneCard(lane, matches, coverage, radiiM) {
  const features = matches.filter((m) => m.lane === lane);
  const rings = ['target', ...radiiM.map(String)];
  return {
    status: cardStatus(features, coverage?.coverageStatus),
    coverageStatus: coverage?.coverageStatus ?? 'unknown',
    sourceCoveragePeriod: coverage?.sourceCoveragePeriod ?? null,
    sourceFamiliesChecked: coverage?.sourceFamiliesChecked ?? [],
    lastDatasetVersion: coverage?.lastDatasetVersion ?? null,
    featureCountByRing: Object.fromEntries(rings.map((ring) => [ring, features.filter((f) => f.nearestRing === ring).length])),
    features,
  };
}

function buildConvergence(matches) {
  const grouped = new Map();
  for (const feature of matches) {
    const key = feature.independenceGroup || feature.canonicalSourceIdentity || feature.globalFeatureId || feature.globalEventId || feature.featureId;
    const group = grouped.get(key) ?? { key, lanes: new Set(), featureIds: [], confirmed: false, contextOnly: true };
    group.lanes.add(feature.lane);
    group.featureIds.push(feature.featureId);
    group.confirmed ||= feature.evidenceStatus === 'confirmed_positive';
    group.contextOnly &&= ['district_context','historical_toponym_context'].includes(feature.relationType) || feature.geometryRole === 'area_context';
    grouped.set(key, group);
  }
  const series = [...grouped.values()].map((g) => ({
    independenceGroup: g.key,
    lanes: [...g.lanes].sort(),
    featureIds: [...new Set(g.featureIds)].sort(),
    status: g.contextOnly ? 'context_only' : g.confirmed ? 'confirmed' : 'candidate',
  }));
  const nonContext = series.filter((s) => s.status !== 'context_only');
  const confirmed = nonContext.filter((s) => s.status === 'confirmed').length;
  const candidate = nonContext.filter((s) => s.status === 'candidate').length;
  let convergenceStatus = 'none';
  if (nonContext.length >= 2) convergenceStatus = confirmed >= 2 ? 'confirmed' : 'candidate';
  else if (series.length >= 2 && nonContext.length === 0) convergenceStatus = 'context_only';
  return {
    independentSeriesCount: nonContext.length,
    confirmedIndependentSeriesCount: confirmed,
    candidateIndependentSeriesCount: candidate,
    series,
    convergenceStatus,
  };
}

export function buildVeilLayerForLocationProfile({
  queryAnchor,
  resolver,
  featureStore,
  laneCoverage = {},
  versions = {},
  radiiM = DEFAULT_RADII,
}) {
  validateQueryAnchor(queryAnchor);
  if (!resolver?.resolvePoint || !resolver?.candidateCells) throw new Error('canonical resolver required');
  if (!featureStore?.retrieveByCells) throw new Error('VEIL feature store required');
  const resolved = resolver.resolvePoint(queryAnchor.lat, queryAnchor.lng);
  if (resolved.status !== 'ok') return { queryAnchor, spatialContext: { status: resolved.status }, veil: { status: 'not_applicable' } };
  if (queryAnchor.cellId && queryAnchor.cellId !== resolved.cellId) throw new Error(`queryAnchor.cellId mismatch: ${queryAnchor.cellId} != ${resolved.cellId}`);

  const maxRadius = Math.max(...radiiM);
  const prefilter = resolver.candidateCells(queryAnchor.lat, queryAnchor.lng, maxRadius);
  const cellIds = new Set([resolved.cellId, ...prefilter.map((x) => x.cellId)]);
  const candidates = featureStore.retrieveByCells(cellIds);
  const query = { lat: queryAnchor.lat, lon: queryAnchor.lng };
  const matches = candidates.map((f) => publicizeFeature(f, query, resolved.cellId, radiiM)).filter(Boolean)
    .sort((a,b) => a.distanceMeters - b.distanceMeters || a.featureId.localeCompare(b.featureId));

  const cards = Object.fromEntries(VEIL_LANES.map((lane) => [lane, buildLaneCard(lane, matches, laneCoverage[lane], radiiM)]));
  return {
    queryAnchor: { ...queryAnchor, cellId: resolved.cellId },
    spatialContext: {
      cellId: resolved.cellId,
      gridRow: resolved.row,
      gridCol: resolved.col,
      cellCenter: resolved.center,
      municipality: resolved.municipality,
      spatialCoreVersion: versions.spatialCoreVersion ?? null,
      spatialCoreSha: versions.spatialCoreSha ?? null,
    },
    veil: {
      status: 'available',
      scoringEffect: 'none',
      adapterRole: 'location_profile_veil_layer',
      datasetVersion: versions.veilDatasetVersion ?? null,
      sourceRegistryVersion: versions.sourceRegistryVersion ?? null,
      publicSummarySchemaVersion: versions.publicSummarySchemaVersion ?? null,
      cards,
      convergence: buildConvergence(matches),
    },
  };
}
