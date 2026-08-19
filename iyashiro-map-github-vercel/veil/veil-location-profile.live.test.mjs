import test from 'node:test';
import assert from 'node:assert/strict';
import { loadVerifiedCanonicalCatalog, VEIL_CANONICAL_SOURCE } from './canonical-catalog-contract.mjs';
import { createVeilCanonicalResolver } from './address-grid-core.mjs';
import { createVeilFeatureStore, buildVeilLayerForLocationProfile } from './veil-location-profile-adapter.mjs';

const actualPath = process.env.VEIL_CANONICAL_CATALOG_PATH;

test('actual canonical catalog + Shinagawa-style source reference stays context-only end-to-end', { skip: !actualPath }, async () => {
  const verified = await loadVerifiedCanonicalCatalog(actualPath);
  const resolver = createVeilCanonicalResolver(verified.safeCatalog);

  // Mirrors the B08 Shinagawa archaeology shadow contract: the source point is
  // an indexing/reference coordinate, not a site polygon or burial geometry.
  const queryAnchor = {
    anchorId: 'B08-SHINAGAWA-R01-LIVE',
    anchorType: 'representative_point',
    lat: 35.619753,
    lng: 139.725531,
    precisionClass: 'address_point',
    source: 'B08_SHINAGAWA_SHADOW_FIXTURE',
    sourceDate: '2026-08-15',
    acquiredAt: '2026-08-15T00:00:00Z',
    uncertaintyMeters: 0,
  };

  const resolved = resolver.resolvePoint(queryAnchor.lat, queryAnchor.lng);
  assert.equal(resolved.status, 'ok');
  assert.equal(resolved.cellId, 'g245-268');
  assert.equal(resolved.municipality.code, '13109');

  const featureStore = createVeilFeatureStore([{
    featureId: 'VEIL-TOKYO-SHINAGAWA-ARCH-0026-R01-LIVE',
    lane: 'LOST_TABOO',
    subtype: 'archaeology_catalog_context',
    geometry: { type: 'Point', coordinates: [139.725531, 35.619753] },
    // Intentionally poison the upstream match as intersecting. Publicization
    // must still fail closed because this is only a source reference point.
    spatialMatches: [{
      cellId: 'g245-268',
      intersectsCell: true,
      errorBandIntersectsCell: false,
    }],
    geometryRole: 'area_context',
    locationAccuracy: 'source_point_reference',
    publicPrecision: 'reference_point_context',
    spatialInterpretation: 'catalog_reference_point_not_site_extent',
    evidenceStatus: 'source_backed_review',
    canonicalSourceIdentity: 'TOKYO_SHINAGAWA_ARCH_0026',
    publicTitle: '上大崎貝塚',
    publicSummary: 'archaeology catalog reference point fixture',
  }]);

  const result = buildVeilLayerForLocationProfile({
    queryAnchor,
    resolver,
    featureStore,
    laneCoverage: {
      LOST_TABOO: {
        coverageStatus: 'partial',
        sourceFamiliesChecked: ['TOKYO_SHINAGAWA_ARCH_0026'],
        lastDatasetVersion: 'VEIL-B08-CANONICAL-INTEGRATION-TOKYO-PAYLOAD-20260815',
      },
    },
    versions: {
      spatialCoreVersion: 'regional-catalog-v4',
      spatialCoreSha: verified.sha256,
      veilDatasetVersion: 'VEIL-B08-CANONICAL-INTEGRATION-TOKYO-PAYLOAD-20260815',
      sourceRegistryVersion: 'B08',
      publicSummarySchemaVersion: '1',
    },
  });

  const feature = result.veil.cards.LOST_TABOO.features[0];
  assert.equal(result.spatialContext.cellId, 'g245-268');
  assert.equal(result.spatialContext.spatialCoreSha, VEIL_CANONICAL_SOURCE.sha256);
  assert.equal(feature.relationType, 'reference_point_context');
  assert.equal(feature.intersects, false);
  assert.equal(feature.nearestRing, 'context');
  assert.equal(result.veil.cards.LOST_TABOO.featureCountByRing.target, 0);
  assert.equal(result.veil.cards.LOST_TABOO.featureCountByRing['100'], 0);
  assert.equal(result.veil.convergence.independentSeriesCount, 0);
  assert.equal(result.veil.convergence.convergenceStatus, 'context_only');
});
