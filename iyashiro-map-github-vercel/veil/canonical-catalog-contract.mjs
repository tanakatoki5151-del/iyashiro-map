import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

export const VEIL_CANONICAL_SOURCE = Object.freeze({
  fileName: 'regional-catalog-v4.json',
  driveFileId: '17p0FtJjuRX5LLpSwp7jp1pImKM7-x-S8',
  sha256: '8756f7bff8e917355e87c0aa7d5fe156d2340356ac030eecfd51ab1ed91c511f',
  cellCount: 120_662,
  municipalityCount: 48,
  regionCounts: Object.freeze({ tokyo23: 62_553, yokohama: 43_785, kawasaki: 14_324 }),
});

export const VEIL_CANONICAL_GRID = Object.freeze({
  rows: 624,
  columns: 462,
  originNorth: 35.839647862019405,
  originWest: 139.43,
  latitudeStep: 0.0008983111749910168,
  longitudeStep: 0.0011042452218025757,
  stepMeters: 100,
});

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label} mismatch: ${actual} != ${expected}`);
}

function decodeMembership(base64) {
  if (typeof base64 !== 'string' || !base64) throw new Error('municipality membership is required');
  const membership = Buffer.from(base64, 'base64');
  assertEqual(membership.length, VEIL_CANONICAL_GRID.rows * VEIL_CANONICAL_GRID.columns, 'membership length');
  return membership;
}

export function verifyCanonicalCatalogBuffer(buffer, options = {}) {
  if (!Buffer.isBuffer(buffer)) throw new TypeError('buffer must be a Buffer');
  const expectedSha = options.expectedSha ?? VEIL_CANONICAL_SOURCE.sha256;
  const actualSha = sha256(buffer);
  assertEqual(actualSha, expectedSha, 'canonical SHA-256');

  const catalog = JSON.parse(buffer.toString('utf8'));
  const g = catalog?.grid ?? {};
  for (const [key, expected] of Object.entries(VEIL_CANONICAL_GRID)) {
    if (key === 'stepMeters') continue;
    assertEqual(g[key], expected, `grid.${key}`);
  }
  assertEqual(catalog?.cellCount, VEIL_CANONICAL_SOURCE.cellCount, 'cellCount');
  assertEqual(catalog?.municipalityCount, VEIL_CANONICAL_SOURCE.municipalityCount, 'municipalityCount');
  if (!Array.isArray(catalog?.municipalities)) throw new Error('municipalities array is required');
  assertEqual(catalog.municipalities.length, VEIL_CANONICAL_SOURCE.municipalityCount, 'municipalities.length');

  const membership = decodeMembership(catalog?.data?.municipality);
  const actualByIndex = new Map();
  let nonzero = 0;
  for (const index of membership) {
    if (!index) continue;
    nonzero += 1;
    actualByIndex.set(index, (actualByIndex.get(index) ?? 0) + 1);
  }
  assertEqual(nonzero, VEIL_CANONICAL_SOURCE.cellCount, 'membership nonzero count');

  for (const municipality of catalog.municipalities) {
    if (!Number.isInteger(municipality?.index)) throw new Error('municipality index must be integer');
    assertEqual(actualByIndex.get(municipality.index) ?? 0, Number(municipality.cellCount), `municipality ${municipality.index} cellCount`);
  }

  const sumRange = (start, end) => {
    let total = 0;
    for (let index = start; index <= end; index += 1) total += actualByIndex.get(index) ?? 0;
    return total;
  };
  const regionCounts = {
    tokyo23: sumRange(1, 23),
    yokohama: sumRange(24, 41),
    kawasaki: sumRange(42, 48),
  };
  for (const [region, expected] of Object.entries(VEIL_CANONICAL_SOURCE.regionCounts)) {
    assertEqual(regionCounts[region], expected, `regionCounts.${region}`);
  }

  // Explicit allowlist view. The source contains legacy Iyashiro arrays, but
  // VEIL adapters receive only spatial identity and municipality membership.
  const safeCatalog = {
    grid: { ...g, stepMeters: VEIL_CANONICAL_GRID.stepMeters },
    cellCount: catalog.cellCount,
    municipalityCount: catalog.municipalityCount,
    municipalities: catalog.municipalities.map(({ index, code, name, cellCount }) => ({ index, code, name, cellCount })),
    data: { municipality: catalog.data.municipality },
  };

  return Object.freeze({
    sha256: actualSha,
    regionCounts: Object.freeze(regionCounts),
    safeCatalog: Object.freeze(safeCatalog),
  });
}

export async function loadVerifiedCanonicalCatalog(path, options = {}) {
  const buffer = await readFile(path);
  return verifyCanonicalCatalogBuffer(buffer, options);
}
