import cuolegaTerrainGrid from "@/public/data/cuolega-grid-v2.json";
import denentoshiTerrainGrid from "@/public/data/denentoshi-shibuya-futako-grid-v2.json";
import type { TheoryResult } from "./theory";

export type PrecomputedCell = {
  lat: number;
  lng: number;
  bounds: [[number, number], [number, number]];
  label: TheoryResult["label"];
  labelCode: number;
  originalScore: number;
  originalFit: number;
  highEvidence: number;
  lowEvidence: number;
  ordinaryEvidence: number;
  auxiliaryTerrainScore: number;
  detailScore: number;
  neighborhoodScore: number;
  confidence: number;
  nearbyBestIndex: number;
  nearbyBestDistanceMeters: number | null;
};

type Hotspot = {
  lat: number;
  lng: number;
  detailScore: number;
  originalScore: number;
  confidence: number;
  label: string;
  nearestStation?: string;
  stationDistanceMeters?: number;
};

type TerrainGrid = {
  generatedAt: string;
  center: {
    lat: number;
    lng: number;
    name: string;
    address: string;
    stepMeters: number;
    radiusMeters?: number;
    bufferMeters?: number;
  };
  region?: {
    id: string;
    kind: string;
    name: string;
    stepMeters: number;
    radiusMeters?: number;
    bufferMeters?: number;
  };
  bounds: [[number, number], [number, number]];
  cells: PrecomputedCell[];
  hotspots: Hotspot[];
};

const grids = [
  cuolegaTerrainGrid as unknown as TerrainGrid,
  denentoshiTerrainGrid as unknown as TerrainGrid,
];
const cuolegaGrid = grids[0];

export const CUOLEGA_GRID_META = {
  center: {
    lat: cuolegaGrid.center.lat,
    lng: cuolegaGrid.center.lng,
    name: cuolegaGrid.center.name,
    address: cuolegaGrid.center.address,
  },
  radiusMeters: cuolegaGrid.center.radiusMeters ?? 4_500,
  stepMeters: cuolegaGrid.center.stepMeters,
  bounds: cuolegaGrid.bounds,
  generatedAt: cuolegaGrid.generatedAt,
  cellCount: cuolegaGrid.cells.length,
};

export const PRECOMPUTED_GRID_META = grids.map((grid) => ({
  id: grid.region?.id ?? "cuolega",
  name: grid.region?.name ?? grid.center.name,
  bounds: grid.bounds,
  generatedAt: grid.generatedAt,
  cellCount: grid.cells.length,
  stepMeters: grid.center.stepMeters,
}));

export function distanceMeters(
  firstLat: number,
  firstLng: number,
  secondLat: number,
  secondLng: number,
) {
  const radians = Math.PI / 180;
  const meanLat = ((firstLat + secondLat) / 2) * radians;
  const north = (firstLat - secondLat) * 111_320;
  const east =
    (firstLng - secondLng) * 111_320 * Math.max(0.2, Math.cos(meanLat));
  return Math.hypot(north, east);
}

export function isInCuolegaGrid(lat: number, lng: number) {
  return (
    distanceMeters(
      lat,
      lng,
      cuolegaGrid.center.lat,
      cuolegaGrid.center.lng,
    ) <=
    (cuolegaGrid.center.radiusMeters ?? 4_500) +
      cuolegaGrid.center.stepMeters
  );
}

function includesPoint(grid: TerrainGrid, lat: number, lng: number) {
  const [[south, west], [north, east]] = grid.bounds;
  return lat >= south && lat <= north && lng >= west && lng <= east;
}

function findPrecomputedEntry(lat: number, lng: number) {
  let nearest:
    | { cell: PrecomputedCell; grid: TerrainGrid }
    | null = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const grid of grids) {
    if (!includesPoint(grid, lat, lng)) continue;
    for (const cell of grid.cells) {
      const distance = distanceMeters(lat, lng, cell.lat, cell.lng);
      if (distance < nearestDistance) {
        nearest = { cell, grid };
        nearestDistance = distance;
      }
    }
  }
  return nearest &&
    nearestDistance <= nearest.grid.center.stepMeters
    ? nearest
    : null;
}

export function findPrecomputedCell(lat: number, lng: number) {
  return findPrecomputedEntry(lat, lng)?.cell ?? null;
}

export function precomputedTheoryAt(
  lat: number,
  lng: number,
): TheoryResult | null {
  const entry = findPrecomputedEntry(lat, lng);
  if (!entry) return null;
  const { cell, grid } = entry;
  const hotspot =
    cell.nearbyBestIndex >= 0
      ? grid.hotspots[cell.nearbyBestIndex]
      : null;
  const regionName = grid.region?.name ?? grid.center.name;
  return {
    score: cell.detailScore,
    label: cell.label,
    originalScore: cell.originalScore,
    originalFit: cell.originalFit,
    auxiliaryTerrainScore: cell.auxiliaryTerrainScore,
    detailScore: cell.detailScore,
    neighborhoodScore: cell.neighborhoodScore,
    internalConfidence: cell.confidence,
    highEvidence: cell.highEvidence,
    lowEvidence: cell.lowEvidence,
    ordinaryEvidence: cell.ordinaryEvidence,
    nearbyBest:
      hotspot && cell.nearbyBestDistanceMeters !== null
        ? {
            ...hotspot,
            distanceMeters: cell.nearbyBestDistanceMeters,
          }
        : null,
    sourceMode: "precomputed-100m",
    reasons: [
      `原典交会：高位×高位 ${Math.round(cell.highEvidence * 100)}／低位×低位 ${Math.round(cell.lowEvidence * 100)}／高位×低位 ${Math.round(cell.ordinaryEvidence * 100)}`,
      `原典ロジック点 ${cell.originalScore}／補助地形点 ${cell.auxiliaryTerrainScore}`,
      `原典80%＋補助地形20%で地点詳細点 ${cell.detailScore}`,
      `半径500mの周辺点 ${cell.neighborhoodScore}`,
      `${regionName}を100m間隔で事前計算`,
    ],
    caveat:
      "判定信頼度はDEMから高位線・低位線を抽出できた安定度であり、効能の確率ではありません。",
    scales: [],
  };
}

export function precomputedCellsInBounds(
  west: number,
  south: number,
  east: number,
  north: number,
) {
  return grids.flatMap((grid) =>
    grid.cells.filter(
      (cell) =>
        cell.lng >= west &&
        cell.lng <= east &&
        cell.lat >= south &&
        cell.lat <= north,
    ),
  );
}
