import townMarketV1 from "./town-market-v1";

export type NexusMarketSampleQuality = "ROBUST" | "REVIEW" | "THIN";

export type NexusTownMarketContext = {
  schemaVersion: "1.0";
  asOfJST: string;
  town: string;
  sampleCount: number;
  uniqueBuildings: number;
  sampleQuality: NexusMarketSampleQuality;
  medianTotalJPY: number;
  p25TotalJPY: number;
  p75TotalJPY: number;
  medianFixedPerSqmJPY: number;
  propertyTotalJPY: number | null;
  differenceFromMedianJPY: number | null;
  differenceFromMedianPct: number | null;
  comparisonLabel: string | null;
  warnings: string[];
};

type TownRow = (typeof townMarketV1.towns)[number];

function toKanjiNumber(value: number) {
  const digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
  if (value < 10) return digits[value];
  if (value === 10) return "十";
  if (value < 20) return `十${digits[value - 10]}`;
  if (value < 100) {
    const tens = Math.floor(value / 10);
    const ones = value % 10;
    return `${digits[tens]}十${ones ? digits[ones] : ""}`;
  }
  return String(value);
}

export function normalizeTownKey(raw: string | null | undefined) {
  if (!raw) return "";
  let value = raw.normalize("NFKC").replace(/[\s　]/g, "").trim();
  value = value.replace(/^東京都/, "");
  value = value.replace(/^.+?[区市](?=.)/, "");
  value = value.replace(/(\d+)丁目/g, (_, number) => `${toKanjiNumber(Number(number))}丁目`);
  return value;
}

function quality(row: TownRow): NexusMarketSampleQuality {
  if (row.n >= 5 && row.uniqueBuildings >= 4) return "ROBUST";
  if (row.n >= 3 && row.uniqueBuildings >= 2) return "REVIEW";
  return "THIN";
}

function comparisonLabel(differencePct: number) {
  if (differencePct <= -0.15) return "町丁目の単純中央値よりかなり低い";
  if (differencePct <= -0.05) return "町丁目の単純中央値よりやや低い";
  if (differencePct < 0.05) return "町丁目の単純中央値付近";
  if (differencePct < 0.15) return "町丁目の単純中央値よりやや高い";
  return "町丁目の単純中央値よりかなり高い";
}

export function findTownMarket(town: string | null | undefined, propertyTotalJPY: number | null): NexusTownMarketContext | null {
  const key = normalizeTownKey(town);
  if (!key) return null;

  const row = townMarketV1.towns.find((candidate) => normalizeTownKey(candidate.key) === key);
  if (!row) return null;

  const differenceFromMedianJPY = propertyTotalJPY === null ? null : propertyTotalJPY - row.medianTotalJPY;
  const differenceFromMedianPct = differenceFromMedianJPY === null ? null : differenceFromMedianJPY / row.medianTotalJPY;
  const sampleQuality = quality(row);
  const warnings = [
    "これは公開募集の単純中央値です。成約賃料、現在空室、正式Championモデルの個別予測ではありません。",
    "広さ、築年、徒歩、間取り、階数を揃えた比較ではありません。最初の検算として使います。",
  ];
  if (sampleQuality === "THIN") warnings.push("標本が薄いため、この町丁目だけで高い・安いを断定しません。");
  if (sampleQuality === "REVIEW") warnings.push("一定の参考にはなりますが、建物構成の偏りを追加確認します。");

  return {
    schemaVersion: "1.0",
    asOfJST: townMarketV1.asOfJST,
    town: row.key,
    sampleCount: row.n,
    uniqueBuildings: row.uniqueBuildings,
    sampleQuality,
    medianTotalJPY: row.medianTotalJPY,
    p25TotalJPY: row.p25TotalJPY,
    p75TotalJPY: row.p75TotalJPY,
    medianFixedPerSqmJPY: row.medianFixedPerSqmJPY,
    propertyTotalJPY,
    differenceFromMedianJPY,
    differenceFromMedianPct,
    comparisonLabel: differenceFromMedianPct === null ? null : comparisonLabel(differenceFromMedianPct),
    warnings,
  };
}

export const NEXUS_MARKET_AGGREGATE_SNAPSHOT = {
  asOfJST: townMarketV1.asOfJST,
  canonicalUnitsWithKnownTotal: townMarketV1.canonicalUnitsWithKnownTotal,
  townSegments: townMarketV1.towns.length,
  semantics: townMarketV1.semantics,
} as const;
