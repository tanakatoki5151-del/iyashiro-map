const EARTH_RADIUS_M = 6_371_008.8;
const DEG = Math.PI / 180;

export const VEIL_LANES = Object.freeze([
  "FOLKLORE",
  "MODERN_INCIDENTS",
  "LOST_TABOO",
  "PHYSICAL",
]);

function assertFinite(value, name) {
  if (!Number.isFinite(value)) throw new TypeError(`${name} must be finite`);
}

function assertPosition(position) {
  if (
    !Array.isArray(position) ||
    position.length < 2 ||
    !Number.isFinite(position[0]) ||
    !Number.isFinite(position[1])
  ) {
    throw new Error("invalid GeoJSON position");
  }
}

export function haversineMeters(aLat, aLon, bLat, bLon) {
  for (const [value, name] of [
    [aLat, "aLat"],
    [aLon, "aLon"],
    [bLat, "bLat"],
    [bLon, "bLon"],
  ]) {
    assertFinite(value, name);
  }
  const phi1 = aLat * DEG;
  const phi2 = bLat * DEG;
  const dPhi = (bLat - aLat) * DEG;
  const dLambda = (bLon - aLon) * DEG;
  const h =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

function project(position, originLat, originLon) {
  assertPosition(position);
  const [lon, lat] = position;
  const meanLat = ((lat + originLat) / 2) * DEG;
  return {
    x: (lon - originLon) * DEG * EARTH_RADIUS_M * Math.cos(meanLat),
    y: (lat - originLat) * DEG * EARTH_RADIUS_M,
  };
}

function segmentDistanceToOrigin(a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const denom = dx * dx + dy * dy;
  if (denom === 0) return Math.hypot(a.x, a.y);
  const t = Math.max(0, Math.min(1, -(a.x * dx + a.y * dy) / denom));
  return Math.hypot(a.x + t * dx, a.y + t * dy);
}

function lineDistance(coordinates, originLat, originLon) {
  if (!Array.isArray(coordinates) || coordinates.length === 0) {
    throw new Error("empty line coordinates");
  }
  const points = coordinates.map((p) => project(p, originLat, originLon));
  if (points.length === 1) return Math.hypot(points[0].x, points[0].y);
  let best = Infinity;
  for (let i = 1; i < points.length; i += 1) {
    best = Math.min(best, segmentDistanceToOrigin(points[i - 1], points[i]));
  }
  return best;
}

function pointInRingAtOrigin(projectedRing) {
  let inside = false;
  for (let i = 0, j = projectedRing.length - 1; i < projectedRing.length; j = i++) {
    const a = projectedRing[i];
    const b = projectedRing[j];
    if (segmentDistanceToOrigin(a, b) <= 1e-9) return true;
    const intersects =
      (a.y > 0) !== (b.y > 0) &&
      0 < ((b.x - a.x) * (0 - a.y)) / (b.y - a.y) + a.x;
    if (intersects) inside = !inside;
  }
  return inside;
}

function ringBoundaryDistance(projectedRing) {
  if (projectedRing.length < 2) throw new Error("polygon ring too short");
  let best = Infinity;
  for (let i = 0; i < projectedRing.length; i += 1) {
    const a = projectedRing[i];
    const b = projectedRing[(i + 1) % projectedRing.length];
    best = Math.min(best, segmentDistanceToOrigin(a, b));
  }
  return best;
}

function polygonDistance(rings, originLat, originLon) {
  if (!Array.isArray(rings) || rings.length === 0) throw new Error("empty polygon");
  const projected = rings.map((ring) => {
    if (!Array.isArray(ring) || ring.length < 3) throw new Error("invalid polygon ring");
    return ring.map((p) => project(p, originLat, originLon));
  });

  const insideOuter = pointInRingAtOrigin(projected[0]);
  const insideHole = projected.slice(1).some(pointInRingAtOrigin);
  if (insideOuter && !insideHole) return 0;

  let best = Infinity;
  for (const ring of projected) best = Math.min(best, ringBoundaryDistance(ring));
  return best;
}

export function geometryDistanceMeters(query, geometry) {
  const lat = query?.lat;
  const lon = query?.lon;
  assertFinite(lat, "query.lat");
  assertFinite(lon, "query.lon");
  if (!geometry || typeof geometry.type !== "string") {
    throw new Error("geometry required");
  }

  const c = geometry.coordinates;
  switch (geometry.type) {
    case "Point":
      assertPosition(c);
      return haversineMeters(lat, lon, c[1], c[0]);
    case "MultiPoint":
      if (!Array.isArray(c) || c.length === 0) throw new Error("empty MultiPoint");
      return Math.min(...c.map((p) => geometryDistanceMeters(query, { type: "Point", coordinates: p })));
    case "LineString":
      return lineDistance(c, lat, lon);
    case "MultiLineString":
      if (!Array.isArray(c) || c.length === 0) throw new Error("empty MultiLineString");
      return Math.min(...c.map((line) => lineDistance(line, lat, lon)));
    case "Polygon":
      return polygonDistance(c, lat, lon);
    case "MultiPolygon":
      if (!Array.isArray(c) || c.length === 0) throw new Error("empty MultiPolygon");
      return Math.min(...c.map((poly) => polygonDistance(poly, lat, lon)));
    default:
      throw new Error(`unsupported geometry type: ${geometry.type}`);
  }
}

function validateFeature(feature) {
  if (!feature || typeof feature.featureId !== "string" || !feature.featureId) {
    throw new Error("featureId required");
  }
  if (!VEIL_LANES.includes(feature.lane)) {
    throw new Error(`invalid VEIL lane: ${feature.lane}`);
  }
  if (!feature.geometry) throw new Error("feature geometry required");
}

function sanitizeFeature(feature, distanceM, matchedRadiiM) {
  // Keep the API-facing object explicit. Do not spread arbitrary research/raw
  // fields into the public response.
  return {
    featureId: feature.featureId,
    lane: feature.lane,
    subtype: feature.subtype ?? null,
    geometryRole: feature.geometryRole ?? null,
    evidenceStatus: feature.evidenceStatus ?? null,
    locationAccuracy: feature.locationAccuracy ?? null,
    publicSummary: feature.publicSummary ?? null,
    distanceM,
    matchedRadiiM,
  };
}

export function evaluateFeaturesForAddress(
  query,
  candidateFeatures,
  radiiM = [100, 300, 500],
) {
  if (!Array.isArray(candidateFeatures)) throw new TypeError("candidateFeatures must be an array");
  const normalizedRadii = [...new Set(radiiM)].sort((a, b) => a - b);
  for (const radius of normalizedRadii) {
    if (!Number.isFinite(radius) || radius < 0) throw new Error("invalid radius");
  }

  const matches = [];
  for (const feature of candidateFeatures) {
    validateFeature(feature);
    const distanceM = geometryDistanceMeters(query, feature.geometry);
    const matchedRadiiM = normalizedRadii.filter((radius) => distanceM <= radius + 1e-9);
    if (matchedRadiiM.length === 0) continue;
    matches.push(sanitizeFeature(feature, distanceM, matchedRadiiM));
  }

  matches.sort(
    (a, b) =>
      a.distanceM - b.distanceM ||
      a.lane.localeCompare(b.lane) ||
      a.featureId.localeCompare(b.featureId),
  );

  return {
    query: { lat: query.lat, lon: query.lon },
    radiiM: normalizedRadii,
    matches,
    byRadius: Object.fromEntries(
      normalizedRadii.map((radius) => [
        String(radius),
        matches.filter((match) => match.matchedRadiiM.includes(radius)),
      ]),
    ),
  };
}
