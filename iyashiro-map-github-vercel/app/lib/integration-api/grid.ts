import type { WeightedCell } from "./types";

export const A_LAT = 35.839647862019405;
export const B_LAT = -0.0008983111749910168;
export const A_LON = 139.43;
export const B_LON = 0.0011042452218025757;
export const GRID_ROWS = 624;
export const GRID_COLS = 462;
export const CANONICAL_CELL_COUNT = 120_662;
export const GRID_DATUM = "JGD2011";
export const GRID_EPSG = 6668;

const HALF_LAT = Math.abs(B_LAT) / 2;
const HALF_LON = Math.abs(B_LON) / 2;
const MERIDIAN_M_PER_DEG = 110_940;

export const GEOCODE_SIGMA_M = {
  GSI_JUKYO_BASE_NUMBER: 50,
  ISJ_GAIKU: 35,
  USER_COORDINATE: 5,
  PROPERTY_PAGE_ADDRESS: 65,
} as const;

export type GeocodeRouteId = keyof typeof GEOCODE_SIGMA_M;

export type AddressGeocodeRouteId = Exclude<GeocodeRouteId, "USER_COORDINATE">;

export function inferGeocodeRoute(
  hasCoordinate: boolean,
  addressEvidenceRoute: AddressGeocodeRouteId = "GSI_JUKYO_BASE_NUMBER",
): GeocodeRouteId {
  return hasCoordinate ? "USER_COORDINATE" : addressEvidenceRoute;
}

export function boundedGeocodeSigmaM(routeId: GeocodeRouteId, requestedSigmaM: number | null): number {
  return Math.max(requestedSigmaM ?? GEOCODE_SIGMA_M[routeId], GEOCODE_SIGMA_M[routeId]);
}

export function inTheoreticalGrid(row: number, col: number): boolean {
  return Number.isInteger(row) && Number.isInteger(col) && row >= 0 && row < GRID_ROWS && col >= 0 && col < GRID_COLS;
}

export function parseCellId(value: string): { row: number; col: number } | null {
  const match = /^g(\d{1,3})-(\d{1,3})$/.exec(value);
  if (!match) return null;
  const row = Number(match[1]);
  const col = Number(match[2]);
  return inTheoreticalGrid(row, col) ? { row, col } : null;
}

export function cellId(row: number, col: number): string {
  return `g${row}-${col}`;
}

export function cellOf(lat: number, lon: number): { row: number; col: number } {
  return {
    row: Math.round((lat - A_LAT) / B_LAT),
    col: Math.round((lon - A_LON) / B_LON),
  };
}

export function cellCenter(row: number, col: number): { lat: number; lon: number } {
  return { lat: A_LAT + B_LAT * row, lon: A_LON + B_LON * col };
}

export function cellBounds(row: number, col: number): { south: number; north: number; west: number; east: number } {
  const center = cellCenter(row, col);
  return {
    south: center.lat - HALF_LAT,
    north: center.lat + HALF_LAT,
    west: center.lon - HALF_LON,
    east: center.lon + HALF_LON,
  };
}

function metersPerDegreeLon(lat: number): number {
  return 111_320 * Math.cos((lat * Math.PI) / 180);
}
export function coordinateDistanceM(
  left: { lat: number; lon: number },
  right: { lat: number; lon: number },
): number {
  const radians = Math.PI / 180;
  const deltaLat = (right.lat - left.lat) * radians;
  const deltaLon = (right.lon - left.lon) * radians;
  const a = Math.sin(deltaLat / 2) ** 2 +
    Math.cos(left.lat * radians) * Math.cos(right.lat * radians) * Math.sin(deltaLon / 2) ** 2;
  return 6_371_008.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}


export function edgeMarginM(lat: number, lon: number): number {
  const { row, col } = cellOf(lat, lon);
  const bounds = cellBounds(row, col);
  return Math.min(
    (bounds.north - lat) * MERIDIAN_M_PER_DEG,
    (lat - bounds.south) * MERIDIAN_M_PER_DEG,
    (bounds.east - lon) * metersPerDegreeLon(lat),
    (lon - bounds.west) * metersPerDegreeLon(lat),
  );
}

// Abramowitz-Stegun 7.1.26; sufficient for cell probability mass calculation.
function erf(value: number): number {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value);
  const t = 1 / (1 + 0.3275911 * x);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return sign * y;
}

function phi(value: number): number {
  return 0.5 * (1 + erf(value / Math.SQRT2));
}

export function resolveTheoreticalCells(
  lat: number,
  lon: number,
  sigmaM: number,
  options: { minimumWeight?: number; span?: number; maximumCells?: number } = {},
): Omit<WeightedCell, "valid">[] {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(sigmaM) || sigmaM <= 0) return [];
  const minimumWeight = Math.max(0, options.minimumWeight ?? 1e-12);
  const cellScaleM = Math.min(
    Math.abs(B_LAT) * MERIDIAN_M_PER_DEG,
    Math.abs(B_LON) * metersPerDegreeLon(lat),
  );
  const inferredSpan = Math.ceil((4 * sigmaM) / cellScaleM);
  const span = Math.max(2, Math.min(25, Math.trunc(options.span ?? inferredSpan)));
  const maximumCells = Math.max(1, Math.min(100, Math.trunc(options.maximumCells ?? 25)));
  const origin = cellOf(lat, lon);
  const sigmaLat = sigmaM / MERIDIAN_M_PER_DEG;
  const sigmaLon = sigmaM / metersPerDegreeLon(lat);
  const candidates: Omit<WeightedCell, "valid">[] = [];
  for (let deltaRow = -span; deltaRow <= span; deltaRow += 1) {
    for (let deltaCol = -span; deltaCol <= span; deltaCol += 1) {
      const row = origin.row + deltaRow;
      const col = origin.col + deltaCol;
      if (!inTheoreticalGrid(row, col)) continue;
      const bounds = cellBounds(row, col);
      const latMass = phi((bounds.north - lat) / sigmaLat) - phi((bounds.south - lat) / sigmaLat);
      const lonMass = phi((bounds.east - lon) / sigmaLon) - phi((bounds.west - lon) / sigmaLon);
      const weight = latMass * lonMass;
      if (weight < minimumWeight) continue;
      const center = cellCenter(row, col);
      const centerDistanceM = Math.hypot(
        (center.lat - lat) * MERIDIAN_M_PER_DEG,
        (center.lon - lon) * metersPerDegreeLon(lat),
      );
      candidates.push({ cellId: cellId(row, col), row, col, weight, centerDistanceM });
    }
  }
  candidates.sort((a, b) => b.weight - a.weight || a.cellId.localeCompare(b.cellId));
  return candidates.slice(0, maximumCells);
}

export function resolutionStability(primaryWeight: number): "STABLE" | "LEANING" | "AMBIGUOUS" | "UNRESOLVED" {
  if (primaryWeight >= 0.95) return "STABLE";
  if (primaryWeight >= 0.75) return "LEANING";
  if (primaryWeight >= 0.5) return "AMBIGUOUS";
  return "UNRESOLVED";
}
