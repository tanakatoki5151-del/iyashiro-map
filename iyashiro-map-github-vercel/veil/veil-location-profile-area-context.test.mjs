import test from 'node:test';
import assert from 'node:assert/strict';
import { createVeilFeatureStore, buildVeilLayerForLocationProfile } from './veil-location-profile-adapter.mjs';

const queryAnchor = {
  anchorId: 'area-context-fixture',
  anchorType: 'representative_point',
  lat: 35.619753,
  lng: 139.725531,
  precisionClass: 'address_point',
  source: 'fixture',
  sourceDate: '2026-08-15',
  acquiredAt: '2026-08-15T00:00:00Z',
  uncertaintyMeters: 20,
  cellId: 'g245-268',
};
const resolver = {
  resolvePoint() {
    return {
      status: 'ok',
      cellId: 'g245-268',
      row: 245,
      col: 268,
      center: { lat: 35.619753, lon: 139.725531 },
      municipality: { code: '13109', name: '品川区' },
    };
  },
  candidateCells() { return [{ cellId: 'g245-268' }]; },
};

test('explicit area_context remains context even when spatial index match says intersects', () => {
  const featureStore = createVeilFeatureStore([{
    featureId: 'VEIL-TOKYO-SHINAGAWA-ARCH-0026-R01',
    lane: 'LOST_TABOO',
    subtype: 'archaeology_catalog_context',
    geometry: { type: 'Point', coordinates: [139.725531, 35.619753] },
    spatialMatches: [{ cellId: 'g245-268', intersectsCell: true, errorBandIntersectsCell: false }],
    geometryRole: 'area_context',
    locationAccuracy: 'source_point_reference',
    spatialInterpretation: 'catalog_reference_point_not_site_extent',
    publicPrecision: 'reference_point_context',
    evidenceStatus: 'source_backed_review',
    canonicalSourceIdentity: 'TOKYO_SHINAGAWA_ARCH_0026',
  }]);
  const result = buildVeilLayerForLocationProfile({ queryAnchor, resolver, featureStore });
  const feature = result.veil.cards.LOST_TABOO.features[0];
  assert.equal(feature.relationType, 'area_context');
  assert.equal(feature.nearestRing, 'context');
  assert.equal(feature.intersects, false);
  assert.equal(result.veil.cards.LOST_TABOO.featureCountByRing.target, 0);
  assert.equal(result.veil.convergence.independentSeriesCount, 0);
  assert.equal(result.veil.convergence.convergenceStatus, 'context_only');
});
