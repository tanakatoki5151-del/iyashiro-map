export type ScopeResult = {
  supported: boolean;
  name: string;
  municipalityCode: string | null;
  address: string | null;
  source: "gsi-reverse" | "rough-bounds";
};

const TOKYO_WARD_CODES = new Set(
  Array.from({ length: 23 }, (_, index) => String(13101 + index)),
);
const YOKOHAMA_WARD_CODES = new Set(
  Array.from({ length: 18 }, (_, index) => String(14101 + index)),
);
const KAWASAKI_WARD_CODES = new Set(
  Array.from({ length: 7 }, (_, index) => String(14131 + index)),
);
const TOKYO_WARDS = [
  "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区",
  "江東区", "品川区", "目黒区", "大田区", "世田谷区", "渋谷区",
  "中野区", "杉並区", "豊島区", "北区", "荒川区", "板橋区", "練馬区",
  "足立区", "葛飾区", "江戸川区",
] as const;

export const clamp = (v: number, min: number, max: number) =>
  Math.min(max, Math.max(min, v));
export const round = (v: number, digits = 3) => {
  const scale = 10 ** digits;
  return Math.round(v * scale) / scale;
};

export function offsetPoint(
  lat: number,
  lng: number,
  eastMeters: number,
  northMeters: number,
) {
  return {
    lat: lat + northMeters / 111_320,
    lng:
      lng +
      eastMeters /
        (111_320 * Math.max(0.2, Math.cos((lat * Math.PI) / 180))),
  };
}

export function pointAt(
  lat: number,
  lng: number,
  distanceMeters: number,
  bearingDegrees: number,
) {
  const radians = (bearingDegrees * Math.PI) / 180;
  return offsetPoint(
    lat,
    lng,
    Math.sin(radians) * distanceMeters,
    Math.cos(radians) * distanceMeters,
  );
}

export function tilePixel(lat: number, lng: number, zoom: number) {
  const size = 2 ** zoom;
  const xFloat = ((lng + 180) / 360) * size;
  const safeLat = clamp(lat, -85.05112878, 85.05112878);
  const radians = (safeLat * Math.PI) / 180;
  const yFloat =
    ((1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2) * size;
  const x = Math.floor(xFloat);
  const y = Math.floor(yFloat);
  return {
    x,
    y,
    pixelX: clamp(Math.floor((xFloat - x) * 256), 0, 255),
    pixelY: clamp(Math.floor((yFloat - y) * 256), 0, 255),
  };
}

export function withinRoughScope(lat: number, lng: number) {
  const tokyo =
    lat >= 35.51 && lat <= 35.84 && lng >= 139.54 && lng <= 139.94;
  const yokohama =
    lat >= 35.28 && lat <= 35.61 && lng >= 139.43 && lng <= 139.76;
  const kawasaki =
    lat >= 35.47 && lat <= 35.65 && lng >= 139.43 && lng <= 139.84;
  return tokyo || yokohama || kawasaki;
}

export function scopeFromMunicipalityCode(code: string | null): ScopeResult {
  const normalized = code ? String(code).slice(0, 5) : null;
  let name = "対象範囲外";
  let supported = false;
  if (normalized && TOKYO_WARD_CODES.has(normalized)) {
    name = "東京23区";
    supported = true;
  } else if (
    normalized &&
    (YOKOHAMA_WARD_CODES.has(normalized) || normalized === "14100")
  ) {
    name = "横浜市";
    supported = true;
  } else if (
    normalized &&
    (KAWASAKI_WARD_CODES.has(normalized) || normalized === "14130")
  ) {
    name = "川崎市";
    supported = true;
  }
  return {
    supported,
    name,
    municipalityCode: normalized,
    address: null,
    source: "gsi-reverse",
  };
}

const scopeCache = new Map<string, Promise<ScopeResult>>();

export async function resolveScope(lat: number, lng: number) {
  if (!withinRoughScope(lat, lng)) {
    return {
      supported: false,
      name: "対象範囲外",
      municipalityCode: null,
      address: null,
      source: "rough-bounds" as const,
    };
  }
  const cacheKey = `${lat.toFixed(3)},${lng.toFixed(3)}`;
  const cached = scopeCache.get(cacheKey);
  if (cached) return cached;
  const request = (async () => {
    try {
      const endpoint = new URL(
        "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress",
      );
      endpoint.searchParams.set("lat", String(lat));
      endpoint.searchParams.set("lon", String(lng));
      const response = await fetch(endpoint, {
        headers: { accept: "application/json" },
      });
      if (!response.ok) throw new Error(String(response.status));
      const data = (await response.json()) as {
        results?: { muniCd?: string; lv01Nm?: string };
      };
      return {
        ...scopeFromMunicipalityCode(data.results?.muniCd ?? null),
        address: data.results?.lv01Nm ?? null,
      };
    } catch {
      return {
        supported: true,
        name: "対象範囲（境界照合は暫定）",
        municipalityCode: null,
        address: null,
        source: "rough-bounds" as const,
      };
    }
  })();
  scopeCache.set(cacheKey, request);
  if (scopeCache.size > 500) {
    scopeCache.delete(scopeCache.keys().next().value as string);
  }
  return request;
}

export function isAddressLabelInScope(label: string) {
  return (
    TOKYO_WARDS.some((ward) => label.includes(`東京都${ward}`)) ||
    label.includes("横浜市") ||
    label.includes("川崎市")
  );
}

export const formatCoordinate = (lat: number, lng: number) =>
  `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
