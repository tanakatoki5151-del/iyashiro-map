import test from 'node:test';
import assert from 'node:assert/strict';
import { createVeilFeatureStore, buildVeilLayerForLocationProfile } from './veil-location-profile-adapter.mjs';

const anchor = {
  anchorId: 'qa-1',
  anchorType: 'representative_point',
  lat: 35.67,
  lng: 139.68,
  precisionClass: 'address_point',
  source: 'fixture',
  sourceDate: '2026-08-15',
  acquiredAt: '2026-08-15T00:00:00Z',
  uncertaintyMeters: 20,
  cellId: 'g1-1',
};
const resolver = {
  resolvePoint() {
    return {
      status: 'ok',
      cellId: 'g1-1',
      row: 1,
      col: 1,
      center: { lat: 35.67, lon: 139.68 },
      municipality: { code: '13113', name: '渋谷区' },
    };
  },
  candidateCells() { return [{ cellId: 'g1-1' }, { cellId: 'g1-2' }]; },
};
const baseMatch = [{ cellId: 'g1-1', intersectsCell: true, errorBandIntersectsCell: false }];
function run(features, coverage = {}) {
  return buildVeilLayerForLocationProfile({
    queryAnchor: anchor,
    resolver,
    featureStore: createVeilFeatureStore(features),
    laneCoverage: coverage,
    versions: { spatialCoreSha: 'sha', veilDatasetVersion: 'test' },
  });
}

test('relocated roles remain separate while same chain counts once', () => {
  const r = run([
    {
      featureId: 'old',
      lane: 'LOST_TABOO',
      geometry: { type: 'Point', coordinates: [139.68, 35.67] },
      spatialMatches: baseMatch,
      geometryRole: 'historical_original',
      evidenceStatus: 'confirmed_positive',
      independenceGroup: 'chain-1',
    },
    {
      featureId: 'current',
      lane: 'FOLKLORE',
      geometry: { type: 'Point', coordinates: [139.68, 35.67] },
      spatialMatches: baseMatch,
      geometryRole: 'current_location',
      evidenceStatus: 'confirmed_positive',
      independenceGroup: 'chain-1',
    },
  ]);
  assert.equal(r.veil.cards.LOST_TABOO.features.length, 1);
  assert.equal(r.veil.cards.FOLKLORE.features.length, 1);
  assert.equal(r.veil.convergence.independentSeriesCount, 1);
  assert.equal(r.veil.convergence.convergenceStatus, 'none');
});

test('town-chome modern incident renders only as context, never target or distance ring', () => {
  const r = run([{
    featureId: 'incident',
    lane: 'MODERN_INCIDENTS',
    geometry: { type: 'Point', coordinates: [139.68, 35.67] },
    spatialMatches: baseMatch,
    locationAccuracy: 'town_chome_only',
    geometryRole: 'facility_site',
    evidenceStatus: 'source_backed_review',
    personName: 'MUST_NOT_LEAK',
    apartmentUnit: 'MUST_NOT_LEAK',
  }]);
  const f = r.veil.cards.MODERN_INCIDENTS.features[0];
  assert.equal(f.relationType, 'district_context');
  assert.equal(f.intersects, false);
  assert.equal(f.nearestRing, 'context');
  assert.equal(JSON.stringify(r).includes('MUST_NOT_LEAK'), false);
});

test('coarse physical series is forced to area context and never target-local', () => {
  const r = run([{
    featureId: 'physical',
    lane: 'PHYSICAL',
    geometry: { type: 'Point', coordinates: [139.68, 35.67] },
    spatialMatches: baseMatch,
    sourceNativeResolutionMeters: 1000,
    evidenceStatus: 'confirmed_positive',
    geometryRole: 'mapped_model_cell',
  }]);
  const f = r.veil.cards.PHYSICAL.features[0];
  assert.equal(f.geometryRole, 'area_context');
  assert.equal(f.spatialInterpretation, 'area_context');
  assert.equal(f.publicPrecision, 'area_context');
  assert.equal(f.relationType, 'area_context');
  assert.equal(f.intersects, false);
  assert.equal(f.nearestRing, 'context');
  assert.equal(r.veil.convergence.independentSeriesCount, 0);
});

test('source-reference archaeology point is context-only even if indexed in target cell', () => {
  const r = run([{
    featureId: 'arch-reference',
    lane: 'LOST_TABOO',
    geometry: { type: 'Point', coordinates: [139.68, 35.67] },
    spatialMatches: baseMatch,
    locationAccuracy: 'source_point_reference',
    publicPrecision: 'reference_point_context',
    evidenceStatus: 'source_backed_review',
    canonicalSourceIdentity: 'TOKYO_SHINAGAWA_ARCH_0026',
  }]);
  const f = r.veil.cards.LOST_TABOO.features[0];
  assert.equal(f.relationType, 'reference_point_context');
  assert.equal(f.intersects, false);
  assert.equal(f.nearestRing, 'context');
  assert.equal(r.veil.cards.LOST_TABOO.featureCountByRing.target, 0);
  assert.equal(r.veil.cards.LOST_TABOO.featureCountByRing['100'], 0);
  assert.equal(r.veil.convergence.independentSeriesCount, 0);
});

test('source access pending remains distinct from no-hit', () => {
  const r = run([], {
    FOLKLORE: { coverageStatus: 'source_access_pending' },
    LOST_TABOO: { coverageStatus: 'defined_sources_no_hit' },
  });
  assert.equal(r.veil.cards.FOLKLORE.status, 'source_access_pending');
  assert.equal(r.veil.cards.LOST_TABOO.status, 'defined_sources_no_hit');
});

test('complete-for-defined-sources coverage maps to public defined-sources-no-hit', () => {
  const r = run([], { FOLKLORE: { coverageStatus: 'complete_for_defined_sources' } });
  assert.equal(r.veil.cards.FOLKLORE.coverageStatus, 'complete_for_defined_sources');
  assert.equal(r.veil.cards.FOLKLORE.status, 'defined_sources_no_hit');
});

test('two independent non-context series produce candidate convergence', () => {
  const r = run([
    {
      featureId: 'a',
      lane: 'FOLKLORE',
      geometry: { type: 'Point', coordinates: [139.68, 35.67] },
      spatialMatches: baseMatch,
      evidenceStatus: 'confirmed_positive',
      independenceGroup: 'a',
    },
    {
      featureId: 'b',
      lane: 'LOST_TABOO',
      geometry: { type: 'Point', coordinates: [139.6801, 35.67] },
      spatialMatches: baseMatch,
      evidenceStatus: 'source_backed_review',
      independenceGroup: 'b',
    },
  ]);
  assert.equal(r.veil.convergence.independentSeriesCount, 2);
  assert.equal(r.veil.convergence.convergenceStatus, 'candidate');
});

test('missing independence identity is fail-closed and cannot inflate convergence', () => {
  const r = run([
    {
      featureId: 'a',
      lane: 'FOLKLORE',
      geometry: { type: 'Point', coordinates: [139.68, 35.67] },
      spatialMatches: baseMatch,
      evidenceStatus: 'confirmed_positive',
    },
    {
      featureId: 'b',
      lane: 'LOST_TABOO',
      geometry: { type: 'Point', coordinates: [139.6801, 35.67] },
      spatialMatches: baseMatch,
      evidenceStatus: 'confirmed_positive',
    },
  ]);
  assert.equal(r.veil.convergence.independentSeriesCount, 0);
  assert.equal(r.veil.convergence.unresolvedIndependenceCount, 2);
  assert.equal(r.veil.convergence.convergenceStatus, 'none');
});

test('current memorial cannot be asserted as historical original', () => {
  assert.throws(() => createVeilFeatureStore([{
    featureId: 'bad-current',
    lane: 'LOST_TABOO',
    geometry: { type: 'Point', coordinates: [139.68, 35.67] },
    spatialMatches: baseMatch,
    geometryRole: 'current_memorial',
    historicalOriginalLocation: true,
    evidenceStatus: 'source_backed_review',
  }]), /historical original/);
});

test('Global Spatial Contract sourceDate is required on queryAnchor', () => {
  const { sourceDate, ...withoutSourceDate } = anchor;
  assert.throws(() => buildVeilLayerForLocationProfile({
    queryAnchor: withoutSourceDate,
    resolver,
    featureStore: createVeilFeatureStore([]),
  }), /queryAnchor\.sourceDate required/);
});
