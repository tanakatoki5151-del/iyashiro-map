const EARTH_RADIUS_M = 6_371_008.8;

export const VEIL_CANONICAL_GRID = Object.freeze({
  rows: 624,
  columns: 462,
  originNorth: 35.839647862019405,
  originWest: 139.43,
  latitudeStep: 0.0008983111749910168,
  longitudeStep: 0.0011042452218025757,
  stepMeters: 100,
});

export const VEIL_CANONICAL_COUNTS = Object.freeze({
  cellCount: 120_662,
  municipalityCount: 48,
  tokyo23: 62_553,
  yokohama: 43_785,
  kawasaki: 14_324,
});

export const BLOCKED_LEGACY_FIELDS = Object.freeze([
  "originalScore",
  "originalFit",
  "labelCode",
  "confidence",
  "score",
  "ranking",
  "labels",
]);

function assertFiniteCoordinate(value, name) {
  if (!Number.isFinite(value)) throw new TypeError(`${name} must be finite`);
}

function assertGrid(grid) {
  const expected = VEIL_CANONICAL_GRID;
  for (const key of Object.keys(expected)) {
    if (grid?.[key] !== expected[key]) {
      throw new Error(`canonical grid mismatch at ${key}`);
    }
  }
}

export function parseCellId(cellId) {
  const match = /^g(\d+)-(\d+)$/.exec(String(cellId));
  if (!match) throw new Error(`invalid cellId: ${cellId}`);
  const row = Number(match[1]);
  const col = Number(match[2]);
  if (
    row < 0 ||
    row >= VEIL_CANONICAL_GRID.rows ||
    col < 0 ||
    col >= VEIL_CANONICAL_GRID.columns
  ) {
    throw new Error(`cellId outside canonical grid: ${cellId}`);
  }
  return { row, col };
}

export function cellIdFromRowCol(row, col) {
  if (!Number.isInteger(row) || !Number.isInteger(col)) {
    throw new TypeError("row/col must be integers");
  }
  if (
    row < 0 ||
    row >= VEIL_CANONICAL_GRID.rows ||
    col < 0 ||
    col >= VEIL_CANONICAL_GRID.columns
  ) {
    return null;
  }
  return `g${row}-${col}`;
}

export function centerForCell(cellId) {
  const { row, col } = parseCellId(cellId);
  const g = VEIL_CANONICAL_GRID;
  return {
    lat: g.originNorth - row * g.latitudeStep,
    lon: g.originWest + col * g.longitudeStep,
  };
}

export function rowColForPoint(lat, lon) {
  assertFiniteCoordinate(lat, "lat");
  assertFiniteCoordinate(lon, "lon");
  const g = VEIL_CANONICAL_GRID;
  const row = Math.round((g.originNorth - lat) / g.latitudeStep);
  const col = Math.round((lon - g.originWest) / g.longitudeStep);
  if (
    row < 0 ||
    row >= g.rows ||
    col < 0 ||
    col >= g.columns
  ) {
    return null;
  }

  // The grid origin represents cell centers. Reject points beyond the
  // half-cell envelope rather than snapping arbitrarily to an edge cell.
  const centerLat = g.originNorth - row * g.latitudeStep;
  const centerLon = g.originWest + col * g.longitudeStep;
  if (
    Math.abs(lat - centerLat) > g.latitudeStep / 2 + 1e-12 ||
    Math.abs(lon - centerLon) > g.longitudeStep / 2 + 1e-12
  ) {
    return null;
  }
  return { row, col };
}

export function haversineMeters(aLat, aLon, bLat, bLon) {
  for (const [value, name] of [
    [aLat, "aLat"],
    [aLon, "aLon"],
    [bLat, "bLat"],
    [bLon, "bLon"],
  ]) {
    assertFiniteCoordinate(value, name);
  }
  const rad = Math.PI / 180;
  const phi1 = aLat * rad;
  const phi2 = bLat * rad;
  const dPhi = (bLat - aLat) * rad;
  const dLambda = (bLon - aLon) * rad;
  const h =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

function halfCellDiagonalMeters(lat, lon) {
  const g = VEIL_CANONICAL_GRID;
  return haversineMeters(
    lat,
    lon,
    lat + g.latitudeStep / 2,
    lon + g.longitudeStep / 2,
  );
}

function decodeMembership(base64) {
  if (typeof base64 !== "string" || base64.length === 0) {
    throw new Error("municipality membership base64 is required");
  }
  const bytes = Buffer.from(base64, "base64");
  const expected = VEIL_CANONICAL_GRID.rows * VEIL_CANONICAL_GRID.columns;
  if (bytes.length !== expected) {
    throw new Error(`membership length mismatch: ${bytes.length} != ${expected}`);
  }
  return bytes;
}

function normalizeMunicipalities(municipalities) {
  if (!Array.isArray(municipalities)) throw new Error("municipalities must be an array");
  const byIndex = new Map();
  for (const item of municipalities) {
    if (!Number.isInteger(item?.index) || item.index < 1 || item.index > 255) {
      throw new Error("invalid municipality index");
    }
    byIndex.set(item.index, {
      index: item.index,
      code: String(item.code ?? ""),
      name: String(item.name ?? ""),
      cellCount: Number(item.cellCount ?? 0),
    });
  }
  return byIndex;
}

function assertNoLegacyLeak(value) {
  const json = JSON.stringify(value);
  for (const key of BLOCKED_LEGACY_FIELDS) {
    if (json.includes(`"${key}"`)) {
      throw new Error(`legacy field leaked from VEIL adapter: ${key}`);
    }
  }
}

export function createVeilCanonicalResolver(catalog) {
  assertGrid(catalog?.grid);
  if (catalog?.cellCount !== VEIL_CANONICAL_COUNTS.cellCount) {
    throw new Error("canonical cellCount mismatch");
  }
  if (catalog?.municipalityCount !== VEIL_CANONICAL_COUNTS.municipalityCount) {
    throw new Error("canonical municipalityCount mismatch");
  }

  const membership = decodeMembership(catalog?.data?.municipality);
  const nonzero = membership.reduce((n, value) => n + (value === 0 ? 0 : 1), 0);
  if (nonzero !== VEIL_CANONICAL_COUNTS.cellCount) {
    throw new Error(`membership nonzero mismatch: ${nonzero}`);
  }

  const municipalities = normalizeMunicipalities(catalog?.municipalities);
  if (municipalities.size !== VEIL_CANONICAL_COUNTS.municipalityCount) {
    throw new Error("municipality registry size mismatch");
  }

  const g = VEIL_CANONICAL_GRID;
  const offset = (row, col) => row * g.columns + col;

  function municipalityAt(row, col) {
    const index = membership[offset(row, col)];
    if (!index) return null;
    const municipality = municipalities.get(index);
    if (!municipality) throw new Error(`unknown municipality index ${index}`);
    return municipality;
  }

  function resolvePoint(lat, lon) {
    const rc = rowColForPoint(lat, lon);
    if (!rc) return { status: "outside_grid" };
    const municipality = municipalityAt(rc.row, rc.col);
    if (!municipality) {
      return {
        status: "no_canonical_cell",
        gridCellId: cellIdFromRowCol(rc.row, rc.col),
      };
    }
    const cellId = cellIdFromRowCol(rc.row, rc.col);
    const center = centerForCell(cellId);
    const result = {
      status: "ok",
      cellId,
      row: rc.row,
      col: rc.col,
      center,
      municipality,
    };
    assertNoLegacyLeak(result);
    return result;
  }

  function candidateCells(lat, lon, radiusM) {
    assertFiniteCoordinate(lat, "lat");
    assertFiniteCoordinate(lon, "lon");
    if (!Number.isFinite(radiusM) || radiusM < 0) {
      throw new TypeError("radiusM must be a non-negative finite number");
    }

    // This is deliberately a recall-preserving cell prefilter. Feature-level
    // inclusion must still use exact geometry/shortest-distance rules.
    const paddingM = halfCellDiagonalMeters(lat, lon);
    const searchM = radiusM + paddingM;
    const rowPad = Math.ceil(searchM / g.stepMeters) + 2;
    const colPad = Math.ceil(searchM / g.stepMeters) + 2;
    const anchor = rowColForPoint(lat, lon);
    if (!anchor) return [];

    const hits = [];
    for (
      let row = Math.max(0, anchor.row - rowPad);
      row <= Math.min(g.rows - 1, anchor.row + rowPad);
      row += 1
    ) {
      for (
        let col = Math.max(0, anchor.col - colPad);
        col <= Math.min(g.columns - 1, anchor.col + colPad);
        col += 1
      ) {
        const municipality = municipalityAt(row, col);
        if (!municipality) continue;
        const cellId = cellIdFromRowCol(row, col);
        const center = centerForCell(cellId);
        const centerDistanceM = haversineMeters(lat, lon, center.lat, center.lon);
        if (centerDistanceM <= searchM + 1e-9) {
          hits.push({
            cellId,
            centerDistanceM,
            municipality,
          });
        }
      }
    }
    hits.sort((a, b) => a.centerDistanceM - b.centerDistanceM || a.cellId.localeCompare(b.cellId));
    assertNoLegacyLeak(hits);
    return hits;
  }

  function neighborhoodRings(lat, lon, radiiM = [100, 300, 500]) {
    return Object.fromEntries(
      radiiM.map((radiusM) => [String(radiusM), candidateCells(lat, lon, radiusM)]),
    );
  }

  return Object.freeze({
    resolvePoint,
    candidateCells,
    neighborhoodRings,
  });
}
