import { clamp, formatCoordinate, resolveScope, round } from "./geo";
import { analyzeModern, type ModernResult } from "./modern";
import { precomputedTheoryAt } from "./precomputed";
import { analyzeTheory, type TheoryResult } from "./theory";

export type CombinedResult = {
  score: number;
  label:
    | "資料不足・要確認"
    | "住みやすさ候補"
    | "概ね良好"
    | "要確認"
    | "慎重に確認"
    | "優先度低め";
  theoryWeight: number;
  provisional: boolean;
  cappedByMajorRisk: boolean;
  reasons: string[];
};
export type DiagnosisResult = {
  schemaVersion: "2.0";
  generatedAt: string;
  point: {
    lat: number;
    lng: number;
    coordinate: string;
    addressHint: string | null;
  };
  scope: Awaited<ReturnType<typeof resolveScope>>;
  theory: TheoryResult;
  modern: ModernResult;
  combined: CombinedResult;
  sources: Array<{ name: string; version: string; url: string }>;
  disclaimer: string;
};

function combinedLabel(score: number): CombinedResult["label"] {
  if (score >= 80) return "住みやすさ候補";
  if (score >= 65) return "概ね良好";
  if (score >= 45) return "要確認";
  if (score >= 25) return "慎重に確認";
  return "優先度低め";
}

export function combineScores(
  theory: TheoryResult,
  modern: ModernResult,
): CombinedResult {
  const usable =
    theory.label !== "判定材料不足" && theory.internalConfidence >= 30;
  const weight = usable ? 0.35 * (theory.internalConfidence / 100) : 0;
  let score = weight * theory.score + (1 - weight) * modern.score;
  const capped =
    (modern.waterRisk ?? 0) >= 80 || (modern.slopeRisk ?? 0) >= 80;
  if (capped) score = Math.min(score, 39);
  score = Math.round(clamp(score, 0, 100));
  const provisional = modern.completeness < 60 || modern.provisional;
  return {
    score,
    label: provisional ? "資料不足・要確認" : combinedLabel(score),
    theoryWeight: round(weight),
    provisional,
    cappedByMajorRisk: capped,
    reasons: [
      `現代的土地条件を ${Math.round((1 - weight) * 100)}%、イヤシロ仮説を ${Math.round(weight * 100)}%で反映`,
      capped
        ? "重大な水害・斜面リスクがあるため総合点を上限39に制限"
        : "重大リスクによる上限制限なし",
      modern.provisional
        ? "未判定データがあるため暫定評価"
        : "主要データが取得できた評価",
    ],
  };
}

export async function diagnoseLocation(
  lat: number,
  lng: number,
): Promise<DiagnosisResult> {
  const scope = await resolveScope(lat, lng);
  if (!scope.supported) {
    throw new RangeError(
      "現在の対象は東京23区・横浜市・川崎市です。この地点は対象範囲外です。",
    );
  }
  const precomputedTheory = precomputedTheoryAt(lat, lng);
  const [theory, modern] = await Promise.all([
    precomputedTheory
      ? Promise.resolve(precomputedTheory)
      : analyzeTheory(lat, lng),
    analyzeModern(lat, lng),
  ]);
  return {
    schemaVersion: "2.0",
    generatedAt: new Date().toISOString(),
    point: {
      lat,
      lng,
      coordinate: formatCoordinate(lat, lng),
      addressHint: scope.address,
    },
    scope,
    theory,
    modern,
    combined: combineScores(theory, modern),
    sources: [
      {
        name: "国土地理院 数値標高モデル",
        version: "取得時点の公開タイル",
        url: "https://maps.gsi.go.jp/development/demtile.html",
      },
      {
        name: "国土交通省 ハザードマップポータル",
        version: "取得時点の公開タイル",
        url: "https://disaportal.gsi.go.jp/hazardmapportal/hazardmap/copyright/opendata.html",
      },
      {
        name: "防災科研 J-SHIS 表層地盤",
        version: "V4（2020年版）",
        url: "https://www.j-shis.bosai.go.jp/api-sstruct-meshinfo",
      },
      {
        name: "国土地理院 明治期の低湿地",
        version: "公開タイル",
        url: "https://www.gsi.go.jp/bousaichiri/lc_meiji.html",
      },
    ],
    disclaimer:
      "イヤシロ／ケガレ判定は伝統的仮説を地形幾何として数値化した参考情報で、科学的効能や安全を保証しません。不動産判断では自治体の最新資料、現地調査、専門家確認を優先してください。",
  };
}
