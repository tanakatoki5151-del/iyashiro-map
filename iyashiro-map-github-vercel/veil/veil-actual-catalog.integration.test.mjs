import test from 'node:test';
import assert from 'node:assert/strict';
import { loadVerifiedCanonicalCatalog, VEIL_CANONICAL_SOURCE } from './canonical-catalog-contract.mjs';
import { createVeilCanonicalResolver } from './address-grid-core.mjs';
import { createVeilFeatureStore, buildVeilLayerForLocationProfile } from './veil-location-profile-adapter.mjs';

const actualPath = process.env.VEIL_CANONICAL_CATALOG_PATH;

test('actual SHA-fixed catalog feeds resolver, feature retrieval, exact distance and LocationProfile VEIL card', { skip: !actualPath }, async () => {
  const verified = await loadVerifiedCanonicalCatalog(actualPath);
  const resolver = createVeilCanonicalResolver(verified.safeCatalog);
  const lat = 35.619753;
  const lng = 139.725531;
  const resolved = resolver.resolvePoint(lat, lng);
  assert.equal(resolved.status, 'ok');
  assert.equal(resolved.cellId, 'g245-268');
  assert.equal(resolved.municipality.code, '13109');

  const featureStore = createVeilFeatureStore([{
    featureId: 'VEIL-TOKYO-SHINAGAWA-ARCH-0026-R01',
    lane: 'LOST_TABOO',
    subtype: 'archaeology_catalog_context',
    geometry: { type: 'Point', coordinates: [lng, lat] },
    spatialMatches: [{ cellId: resolved.cellId, intersectsCell: false, errorBandIntersectsCell: false }],
    geometryRole: 'area_context',
    locationAccuracy: 'source_point_reference',
    spatialInterpretation: 'catalog_reference_point_not_site_extent',
    publicPrecision: 'reference_point_context',
    evidenceStatus: 'source_backed_review',
    canonicalSourceIdentity: 'TOKYO_SHINAGAWA_ARCH_0026',
  }]);

  const result = buildVeilLayerForLocationProfile({
    queryAnchor: {
      anchorId: 'shinagawa-b08-r01',
      anchorType: 'representative_point',
      lat,
      lng,
      precisionClass: 'address_point',
      source: 'B08-fixture',
      sourceDate: '2026-08-15',
      acquiredAt: '2026-08-15T00:00:00Z',
      uncertaintyMeters: 20,
      cellId: resolved.cellId,
    },
    resolver,
    featureStore,
    versions: {
      spatialCoreSha: verified.sha256,
      veilDatasetVersion: 'B08-shadow',
    },
  });

  assert.equal(result.spatialContext.spatialCoreSha, VEIL_CANONICAL_SOURCE.sha256);
  assert.equal(result.spatialContext.cellId, 'g245-268');
  const feature = result.veil.cards.LOST_TABOO.features[0];
  assert.equal(feature.featureId, 'VEIL-TOKYO-SHINAGAWA-ARCH-0026-R01');
  assert.equal(feature.distanceMeters, 0);
  assert.equal(feature.relationType, 'area_context');
  assert.equal(feature.nearestRing, 'context');
  assert.equal(feature.intersects, false);
  assert.equal(result.veil.convergence.independentSeriesCount, 0);
  assert.equal(result.veil.convergence.convergenceStatus, 'context_only');
  assert.equal(result.veil.scoringEffect, 'none');
});
