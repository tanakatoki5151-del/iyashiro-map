const GRID_NORTH_CENTER = 35.8396478620176;
const GRID_WEST_CENTER = 139.43;
const GRID_LAT_STEP = 0.00089831117499;
const GRID_LON_STEP = 0.00110424522183;

export type CanonicalCell = {
  cellId: string;
  gridRow: number;
  gridCol: number;
  centerLat: number;
  centerLng: number;
};

/**
 * Resolve the frozen PLACEGRAPH/V10 canonical ~100m grid.
 * Constants are reconstructed from the formal universe coordinates and
 * validated against the fixed Mejiro fixture (g130-240).
 */
export function resolveCanonicalCell(lat: number, lng: number): CanonicalCell {
  const gridRow = Math.round((GRID_NORTH_CENTER - lat) / GRID_LAT_STEP);
  const gridCol = Math.round((lng - GRID_WEST_CENTER) / GRID_LON_STEP);
  return {
    cellId: `g${gridRow}-${gridCol}`,
    gridRow,
    gridCol,
    centerLat: GRID_NORTH_CENTER - gridRow * GRID_LAT_STEP,
    centerLng: GRID_WEST_CENTER + gridCol * GRID_LON_STEP,
  };
}
