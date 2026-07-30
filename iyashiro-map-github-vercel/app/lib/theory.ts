import { clamp, pointAt, round } from "./geo";
import { getElevation } from "./png";

type Terrain = {
  tpi: number | null;
  mad: number;
  relief: number;
  coverage: number;
};
type Line = {
  angle: number;
  quality: number;
  bothSides: boolean;
};
export type TheoryScale = {
  scale: number;
  highCross: number;
  lowCross: number;
  ordinaryCross: number;
  highLines: number;
  lowLines: number;
  centerTpi: number | null;
  relief: number;
  coverage: number;
};
export type NearbyBest = {
  lat: number;
  lng: number;
  distanceMeters: number;
  detailScore: number;
  originalScore: number;
  confidence: number;
  label: string;
};
export type TheoryResult = {
  /** Backward-compatible alias for detailScore. */
  score: number;
  label:
    | "イヤシロチ候補"
    | "ケガレチ候補"
    | "普通地"
    | "高低混在"
    | "通常・弱い傾向"
    | "判定材料不足";
  originalScore: number;
  originalFit: number;
  auxiliaryTerrainScore: number;
  detailScore: number;
  neighborhoodScore: number | null;
  internalConfidence: number;
  highEvidence: number;
  lowEvidence: number;
  ordinaryEvidence: number;
  nearbyBest: NearbyBest | null;
  sourceMode: "precomputed-100m" | "live-analysis";
  reasons: string[];
  caveat: string;
  scales: TheoryScale[];
};

const SCALES = [
  { meters: 300, threshold: 2 },
  { meters: 1_000, threshold: 5 },
  { meters: 3_000, threshold: 10 },
] as const;
const DIRECTIONS = Array.from({ length: 12 }, (_, i) => i * 15);
const RING = Array.from({ length: 8 }, (_, i) => i * 45);
const mean = (v: number[]) =>
  v.length ? v.reduce((sum, value) => sum + value, 0) / v.length : 0;
function median(values: number[]) {
  if (!values.length) return 0;
  const v = [...values].sort((a, b) => a - b);
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}
const union = (values: number[]) =>
  1 - values.reduce((remaining, value) => remaining * (1 - value), 1);
function angleDiff(a: number, b: number) {
  const raw = Math.abs(a - b) % 180;
  return Math.min(raw, 180 - raw);
}

async function localTerrain(
  lat: number,
  lng: number,
  scale: number,
  elevation: (lat: number, lng: number) => Promise<number | null>,
): Promise<Terrain> {
  const inner = RING.map((angle) => {
    const p = pointAt(lat, lng, Math.max(35, scale / 6), angle);
    return elevation(p.lat, p.lng);
  });
  const outer = RING.map((angle) => {
    const p = pointAt(lat, lng, scale / 2, angle);
    return elevation(p.lat, p.lng);
  });
  const [center, innerRaw, outerRaw] = await Promise.all([
    elevation(lat, lng),
    Promise.all(inner),
    Promise.all(outer),
  ]);
  const i = innerRaw.filter((v): v is number => v !== null);
  const o = outerRaw.filter((v): v is number => v !== null);
  const all = [...(center === null ? [] : [center]), ...i, ...o];
  const coverage = all.length / 17;
  if (center === null || i.length < 5 || o.length < 5) {
    return { tpi: null, mad: 0, relief: 0, coverage };
  }
  const med = median(o);
  return {
    tpi: (center + mean(i)) / 2 - mean(o),
    mad: median(o.map((value) => Math.abs(value - med))),
    relief: Math.max(...all) - Math.min(...all),
    coverage,
  };
}

function crossing(lines: Line[]) {
  const merged: Line[] = [];
  for (const line of [...lines].sort((a, b) => b.quality - a.quality)) {
    if (merged.every((candidate) => angleDiff(candidate.angle, line.angle) > 18)) {
      merged.push(line);
    }
  }
  const pairs: number[] = [];
  for (let a = 0; a < merged.length; a += 1) {
    for (let b = a + 1; b < merged.length; b += 1) {
      const angle = angleDiff(merged[a].angle, merged[b].angle);
      if (angle < 25 || angle > 155) continue;
      pairs.push(
        Math.sqrt(merged[a].quality * merged[b].quality) *
          Math.sin((angle * Math.PI) / 180),
      );
    }
  }
  return {
    evidence: clamp(union(pairs.sort((a, b) => b - a).slice(0, 3)), 0, 1),
    count: merged.length,
  };
}

function crossingBetween(first: Line[], second: Line[]) {
  const pairs: number[] = [];
  for (const a of first) {
    for (const b of second) {
      const angle = angleDiff(a.angle, b.angle);
      if (angle < 25 || angle > 155) continue;
      pairs.push(
        Math.sqrt(a.quality * b.quality) *
          Math.sin((angle * Math.PI) / 180),
      );
    }
  }
  return clamp(union(pairs.sort((a, b) => b - a).slice(0, 3)), 0, 1);
}

async function analyzeScale(
  lat: number,
  lng: number,
  scale: number,
  absoluteThreshold: number,
  elevation: (lat: number, lng: number) => Promise<number | null>,
): Promise<TheoryScale> {
  const center = await localTerrain(lat, lng, scale, elevation);
  if (center.tpi === null || center.relief < 3 || center.coverage < 0.7) {
    return {
      scale,
      highCross: 0,
      lowCross: 0,
      ordinaryCross: 0,
      highLines: 0,
      lowLines: 0,
      centerTpi: center.tpi,
      relief: center.relief,
      coverage: center.coverage,
    };
  }
  const highs: Line[] = [];
  const lows: Line[] = [];
  await Promise.all(
    DIRECTIONS.map(async (angle) => {
      const offsets = [-1.5, -0.5, 0.5, 1.5];
      const anchors = await Promise.all(
        offsets.map(async (offset) => {
          const p = pointAt(
            lat,
            lng,
            Math.abs(offset) * scale,
            offset < 0 ? angle + 180 : angle,
          );
          return {
            offset,
            terrain: await localTerrain(p.lat, p.lng, scale, elevation),
          };
        }),
      );
      for (const kind of ["high", "low"] as const) {
        const selected = anchors.filter(({ terrain }) => {
          if (
            terrain.tpi === null ||
            terrain.relief < 3 ||
            terrain.coverage < 0.65
          ) return false;
          const threshold = Math.max(
            absoluteThreshold * 0.35,
            0.15 * Math.max(0.5, terrain.mad),
          );
          return kind === "high"
            ? terrain.tpi >= threshold
            : terrain.tpi <= -threshold;
        });
        const bothSides =
          selected.some(({ offset }) => offset < 0) &&
          selected.some(({ offset }) => offset > 0);
        if (selected.length < 3 || !bothSides) continue;
        const prominence = mean(
          selected.map(({ terrain }) => {
            const threshold = Math.max(
              absoluteThreshold * 0.35,
              0.15 * Math.max(0.5, terrain.mad),
            );
            return clamp(Math.abs(terrain.tpi ?? 0) / (threshold * 2), 0, 1);
          }),
        );
        const fullSpan =
          selected.some(({ offset }) => offset === -1.5) &&
          selected.some(({ offset }) => offset === 1.5);
        const quality =
          0.25 * (selected.length / 4) +
          0.3 +
          0.2 * (fullSpan ? 1 : 0.75) +
          0.25 * prominence;
        if (quality < 0.55) continue;
        (kind === "high" ? highs : lows).push({
          angle,
          quality: clamp(quality, 0, 1),
          bothSides,
        });
      }
    }),
  );
  const high = crossing(highs);
  const low = crossing(lows);
  const ordinary = crossingBetween(highs, lows);
  return {
    scale,
    highCross: high.evidence,
    lowCross: low.evidence,
    ordinaryCross: ordinary,
    highLines: high.count,
    lowLines: low.count,
    centerTpi: center.tpi,
    relief: center.relief,
    coverage: center.coverage,
  };
}

export async function analyzeTheory(lat: number, lng: number) {
  const memo = new Map<string, Promise<number | null>>();
  const elevation = (sampleLat: number, sampleLng: number) => {
    const key = `${sampleLat.toFixed(6)},${sampleLng.toFixed(6)}`;
    const cached = memo.get(key);
    if (cached) return cached;
    const request = getElevation(sampleLat, sampleLng, 13);
    memo.set(key, request);
    return request;
  };
  const scales = await Promise.all(
    SCALES.map(({ meters, threshold }) =>
      analyzeScale(lat, lng, meters, threshold, elevation),
    ),
  );
  const highEvidence = clamp(
    union(scales.map((scale) => scale.highCross * 0.72)),
    0,
    1,
  );
  const lowEvidence = clamp(
    union(scales.map((scale) => scale.lowCross * 0.72)),
    0,
    1,
  );
  const ordinaryEvidence = clamp(
    union(scales.map((scale) => scale.ordinaryCross * 0.72)),
    0,
    1,
  );
  const difference = highEvidence - lowEvidence;
  let label: TheoryResult["label"] = "判定材料不足";
  if (
    highEvidence >= 0.42 &&
    difference >= 0.12 &&
    highEvidence >= ordinaryEvidence - 0.03
  )
    label = "イヤシロチ候補";
  else if (
    lowEvidence >= 0.42 &&
    difference <= -0.12 &&
    lowEvidence >= ordinaryEvidence - 0.03
  )
    label = "ケガレチ候補";
  else if (
    ordinaryEvidence >= 0.38 &&
    ordinaryEvidence >= Math.max(highEvidence, lowEvidence) - 0.05
  )
    label = "普通地";
  else if (
    highEvidence >= 0.32 &&
    lowEvidence >= 0.32 &&
    Math.abs(difference) < 0.12
  ) label = "高低混在";
  else if (Math.max(highEvidence, lowEvidence, ordinaryEvidence) >= 0.25)
    label = "通常・弱い傾向";
  const coverage = mean(scales.map((scale) => scale.coverage));
  const evidenceScales =
    scales.filter(
      (scale) =>
        Math.max(scale.highCross, scale.lowCross, scale.ordinaryCross) >= 0.25,
    ).length / 3;
  const internalConfidence = Math.round(
    100 *
      clamp(
        0.35 * coverage +
          0.4 * Math.max(highEvidence, lowEvidence, ordinaryEvidence) +
          0.25 * evidenceScales,
        0,
        1,
      ),
  );
  const originalScore = clamp(
    Math.round(50 + 50 * difference * (1 - 0.38 * ordinaryEvidence)),
    0,
    100,
  );
  const scaleWeights = [0.45, 0.35, 0.2];
  const relativePosition = scales.reduce((sum, scale, index) => {
    if (scale.centerTpi === null) return sum;
    const normalizer = Math.max(1, scale.relief * 0.22);
    return (
      sum +
      scaleWeights[index] *
        clamp(scale.centerTpi / normalizer, -1, 1)
    );
  }, 0);
  const averageRelief = mean(scales.map((scale) => scale.relief));
  const reliefSuitability = clamp(92 - Math.max(0, averageRelief - 45), 20, 96);
  const auxiliaryTerrainScore = clamp(
    Math.round(
      0.8 * clamp(50 + 45 * relativePosition, 0, 100) +
        0.2 * reliefSuitability,
    ),
    0,
    100,
  );
  const detailScore = clamp(
    Math.round(0.8 * originalScore + 0.2 * auxiliaryTerrainScore),
    0,
    100,
  );
  const originalFit = Math.round(
    100 * Math.max(highEvidence, lowEvidence, ordinaryEvidence),
  );
  const result: TheoryResult = {
    score: detailScore,
    label,
    originalScore,
    originalFit,
    auxiliaryTerrainScore,
    detailScore,
    neighborhoodScore: null,
    internalConfidence,
    highEvidence: round(highEvidence),
    lowEvidence: round(lowEvidence),
    ordinaryEvidence: round(ordinaryEvidence),
    nearbyBest: null,
    sourceMode: "live-analysis",
    reasons: [
      `高位×高位 ${Math.round(highEvidence * 100)}／低位×低位 ${Math.round(lowEvidence * 100)}／高位×低位 ${Math.round(ordinaryEvidence * 100)}`,
      `3縮尺で高位線候補 ${scales.reduce((s, v) => s + v.highLines, 0)}本、低位線候補 ${scales.reduce((s, v) => s + v.lowLines, 0)}本`,
      `原典ロジック80%＋補助地形20%で地点詳細点 ${detailScore}`,
      `標高データ充足率 ${Math.round(coverage * 100)}%`,
    ],
    caveat:
      "内部信頼度は地形幾何への当てはまりであり、科学的な発生確率や効能の確率ではありません。",
    scales: scales.map((scale) => ({
      ...scale,
      highCross: round(scale.highCross),
      lowCross: round(scale.lowCross),
      ordinaryCross: round(scale.ordinaryCross),
      centerTpi:
        scale.centerTpi === null ? null : round(scale.centerTpi, 2),
      relief: round(scale.relief, 1),
      coverage: round(scale.coverage),
    })),
  };
  return result;
}
