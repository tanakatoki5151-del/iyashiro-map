import { clamp, offsetPoint, round } from "./geo";
import {
  colorDistance,
  getElevation,
  sampleRasterPixel,
  type Pixel,
} from "./png";

export type RiskItem = {
  key: string;
  label: string;
  score: number | null;
  detail: string;
  status: "known" | "unknown" | "error";
  source: string;
};
export type ModernResult = {
  score: number;
  label:
    | "低リスク"
    | "低〜中リスク"
    | "要確認"
    | "高リスク"
    | "非常に高リスク";
  landRisk: number;
  completeness: number;
  provisional: boolean;
  waterRisk: number | null;
  slopeRisk: number | null;
  groundRisk: number | null;
  reasons: string[];
  items: RiskItem[];
};

export const MODERN_RASTER_SOURCES = {
  flood:
    "https://disaportaldata.gsi.go.jp/raster/01_flood_l2_shinsuishin_data/{z}/{x}/{y}.png",
  innerWater:
    "https://disaportaldata.gsi.go.jp/raster/02_naisui_data/{z}/{x}/{y}.png",
  highTide:
    "https://disaportaldata.gsi.go.jp/raster/03_hightide_l2_shinsuishin_data/{z}/{x}/{y}.png",
  tsunami:
    "https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png",
  landslide:
    "https://disaportaldata.gsi.go.jp/raster/05_dosekiryukeikaikuiki/{z}/{x}/{y}.png",
  wetland:
    "https://cyberjapandata.gsi.go.jp/xyz/swale/{z}/{x}/{y}.png",
} as const;

const WATER_PALETTE: Array<{
  color: [number, number, number];
  score: number;
  label: string;
}> = [
  { color: [247, 245, 169], score: 20, label: "0.5m未満相当" },
  { color: [255, 216, 192], score: 55, label: "0.5〜3m相当" },
  { color: [255, 183, 183], score: 80, label: "3〜5m相当" },
  { color: [255, 145, 145], score: 95, label: "5〜10m相当" },
  { color: [242, 133, 201], score: 100, label: "10〜20m相当" },
  { color: [220, 122, 220], score: 100, label: "20m以上相当" },
];

function classifyWater(pixel: Pixel | null) {
  if (!pixel || pixel.a < 8) return null;
  const nearest = WATER_PALETTE.map((entry) => ({
    ...entry,
    distance: colorDistance(pixel, entry.color),
  })).sort((a, b) => a.distance - b.distance)[0];
  return nearest.distance <= 115 ? nearest : null;
}

async function waterItem(
  key: string,
  label: string,
  template: string,
  lat: number,
  lng: number,
): Promise<RiskItem> {
  try {
    const classified = classifyWater(
      await sampleRasterPixel(template, lat, lng, 15),
    );
    return classified
      ? {
          key,
          label,
          score: classified.score,
          detail: classified.label,
          status: "known",
          source: "国土交通省 ハザードマップポータル",
        }
      : {
          key,
          label,
          score: null,
          detail: "未着色（区域外または未整備の区別不可）",
          status: "unknown",
          source: "国土交通省 ハザードマップポータル",
        };
  } catch {
    return {
      key,
      label,
      score: null,
      detail: "取得できませんでした",
      status: "error",
      source: "国土交通省 ハザードマップポータル",
    };
  }
}

async function slopeItem(lat: number, lng: number): Promise<RiskItem> {
  const d = 35;
  const n = offsetPoint(lat, lng, 0, d);
  const s = offsetPoint(lat, lng, 0, -d);
  const e = offsetPoint(lat, lng, d, 0);
  const w = offsetPoint(lat, lng, -d, 0);
  const z = await Promise.all([
    getElevation(n.lat, n.lng, 14),
    getElevation(s.lat, s.lng, 14),
    getElevation(e.lat, e.lng, 14),
    getElevation(w.lat, w.lng, 14),
  ]);
  if (z.some((value) => value === null)) {
    return {
      key: "slope",
      label: "傾斜",
      score: null,
      detail: "標高データ不足",
      status: "unknown",
      source: "国土地理院 数値標高モデル",
    };
  }
  const dzdx = ((z[2] as number) - (z[3] as number)) / (2 * d);
  const dzdy = ((z[0] as number) - (z[1] as number)) / (2 * d);
  const degrees =
    (Math.atan(Math.sqrt(dzdx ** 2 + dzdy ** 2)) * 180) / Math.PI;
  const score =
    degrees >= 40
      ? 80
      : degrees >= 30
        ? 60
        : degrees >= 15
          ? 35
          : degrees >= 5
            ? 10
            : 0;
  return {
    key: "slope",
    label: "傾斜",
    score,
    detail: `${round(degrees, 1)}°`,
    status: "known",
    source: "国土地理院 数値標高モデル",
  };
}

const JCODE_RISK: Record<number, number> = {
  0: 100, 1: 5, 2: 10, 3: 10, 4: 10, 5: 10, 6: 10, 7: 10, 8: 15,
  9: 15, 10: 55, 11: 35, 12: 35, 13: 75, 14: 90, 15: 75, 16: 50,
  17: 50, 18: 70, 19: 85, 20: 90, 21: 15, 22: 100, 23: 100, 24: 100,
};
function arvRisk(arv: number) {
  if (arv < 1) return 0;
  if (arv < 1.4) return 20;
  if (arv < 1.6) return 40;
  if (arv < 2) return 65;
  return 85;
}

async function groundItem(lat: number, lng: number): Promise<RiskItem> {
  try {
    const endpoint = new URL(
      "https://www.j-shis.bosai.go.jp/map/api/sstrct/V4/meshinfo.geojson",
    );
    endpoint.searchParams.set("position", `${lng},${lat}`);
    endpoint.searchParams.set("epsg", "4326");
    const response = await fetch(endpoint, {
      headers: { accept: "application/geo+json,application/json" },
    });
    if (!response.ok) throw new Error(String(response.status));
    const data = (await response.json()) as {
      features?: Array<{
        properties?: {
          JCODE?: string | number;
          JNAME?: string;
          ARV?: string | number;
        };
      }>;
    };
    const p = data.features?.[0]?.properties;
    if (!p) throw new Error("no feature");
    const jcode = Number(p.JCODE);
    const arv = Number(p.ARV);
    return {
      key: "ground",
      label: "地盤・微地形",
      score: Math.max(
        JCODE_RISK[jcode] ?? 50,
        Math.round((Number.isFinite(arv) ? arvRisk(arv) : 50) * 0.9),
      ),
      detail: `${p.JNAME ?? `区分${jcode}`}／増幅率 ${Number.isFinite(arv) ? round(arv, 2) : "不明"}`,
      status: "known",
      source: "防災科研 J-SHIS V4（250mメッシュ）",
    };
  } catch {
    return {
      key: "ground",
      label: "地盤・微地形",
      score: null,
      detail: "J-SHISデータを取得できませんでした",
      status: "error",
      source: "防災科研 J-SHIS V4（250mメッシュ）",
    };
  }
}

async function coloredZoneItem(
  key: "landslide" | "wetland",
  lat: number,
  lng: number,
): Promise<RiskItem> {
  const wetland = key === "wetland";
  const pixel = await sampleRasterPixel(
    wetland
      ? MODERN_RASTER_SOURCES.wetland
      : MODERN_RASTER_SOURCES.landslide,
    lat,
    lng,
    15,
  );
  if (!pixel || pixel.a < 8) {
    return {
      key,
      label: wetland ? "明治期の低湿地" : "土砂災害",
      score: null,
      detail: wetland
        ? "該当着色なし、またはデータ範囲外"
        : "未着色（区域外または未整備の区別不可）",
      status: "unknown",
      source: wetland
        ? "国土地理院 明治期の低湿地"
        : "国土交通省 ハザードマップポータル",
    };
  }
  const score = wetland ? 65 : pixel.r > 180 && pixel.g < 120 ? 100 : 80;
  return {
    key,
    label: wetland ? "明治期の低湿地" : "土砂災害",
    score,
    detail: wetland
      ? "低湿地の着色あり（位置誤差を含む）"
      : score === 100
        ? "特別警戒相当の着色あり"
        : "警戒相当の着色あり",
    status: "known",
    source: wetland
      ? "国土地理院 明治期の低湿地"
      : "国土交通省 ハザードマップポータル",
  };
}

export async function analyzeModern(lat: number, lng: number) {
  const items = await Promise.all([
    waterItem("flood", "洪水浸水", MODERN_RASTER_SOURCES.flood, lat, lng),
    waterItem(
      "innerWater",
      "内水浸水",
      MODERN_RASTER_SOURCES.innerWater,
      lat,
      lng,
    ),
    waterItem("highTide", "高潮", MODERN_RASTER_SOURCES.highTide, lat, lng),
    waterItem("tsunami", "津波", MODERN_RASTER_SOURCES.tsunami, lat, lng),
    coloredZoneItem("landslide", lat, lng),
    slopeItem(lat, lng),
    groundItem(lat, lng),
    coloredZoneItem("wetland", lat, lng),
  ]);
  const scores = (keys: string[]) =>
    items
      .filter((item) => keys.includes(item.key))
      .map((item) => item.score)
      .filter((score): score is number => score !== null);
  const waterScores = scores(["flood", "innerWater", "highTide", "tsunami"]);
  const waterRisk = waterScores.length ? Math.max(...waterScores) : null;
  const slopeScores = scores(["slope", "landslide"]);
  const slopeRisk = slopeScores.length ? Math.max(...slopeScores) : null;
  const groundScores = scores(["ground", "wetland"]);
  const groundRisk = groundScores.length ? Math.max(...groundScores) : null;
  const known = [waterRisk !== null, slopeRisk !== null, groundRisk !== null];
  const completeness = Math.round(
    (known.filter(Boolean).length / known.length) * 100,
  );
  const water = waterRisk ?? 50;
  const slope = slopeRisk ?? 40;
  const ground = groundRisk ?? 50;
  const landRisk = Math.round(
    Math.max(
      0.5 * water + 0.25 * slope + 0.25 * ground,
      0.9 * water,
      0.9 * slope,
      0.7 * ground,
    ),
  );
  const score = clamp(100 - landRisk, 0, 100);
  const label: ModernResult["label"] =
    score >= 80
      ? "低リスク"
      : score >= 60
        ? "低〜中リスク"
        : score >= 40
          ? "要確認"
          : score >= 20
            ? "高リスク"
            : "非常に高リスク";
  const reasons = items
    .filter((item) => item.score !== null)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 3)
    .map((item) => `${item.label}: ${item.detail}`);
  const unknownCount = items.filter((item) => item.score === null).length;
  if (unknownCount)
    reasons.push(`未判定データ ${unknownCount}項目（安全扱いしていません）`);
  const result: ModernResult = {
    score,
    label,
    landRisk,
    completeness,
    provisional: completeness < 60 || unknownCount > 0,
    waterRisk,
    slopeRisk,
    groundRisk,
    reasons,
    items,
  };
  return result;
}
