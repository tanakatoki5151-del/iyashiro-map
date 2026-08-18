import { findTownMarket, NEXUS_MARKET_AGGREGATE_SNAPSHOT, type NexusTownMarketContext } from "./market";

export const NEXUS_POLICY_VERSION = "NEXUS_POLICY_V3_20260818" as const;

export const NEXUS_POLICY = {
  totalMonthlyFixedMaxJPY: 170_000,
  minimumAreaSquareMeters: 15,
  allowedFloors: [1, 2, 3] as const,
} as const;

export const NEXUS_MARKET_COVERAGE = {
  researchTownSegments: 73,
  publicTownSegments: NEXUS_MARKET_AGGREGATE_SNAPSHOT.townSegments,
  canonicalUnitsWithKnownTotal: NEXUS_MARKET_AGGREGATE_SNAPSHOT.canonicalUnitsWithKnownTotal,
  medianUnitsPerResearchTown: 3,
  researchTownsBelowFiveUnits: 59,
  sparseResearchTowns: 60,
  localBenchmarkReadyTowns: 0,
  initialScaleTargetRaw: 3_000,
  initialScaleTargetCanonical: 1_500,
  productScaleTargetRaw: 5_000,
  productScaleTargetCanonical: 2_500,
} as const;

export const NEXUS_EXTERNAL_BENCHMARKS = [
  {
    benchmarkId: "LIFULL_2026_07_TOKYO23_SINGLE",
    publisher: "LIFULL HOME'S",
    period: "2026-07",
    scope: "東京23区・シングルタイプ",
    askingMonthlyJPY: 136_075,
    inquiryMonthlyJPY: 100_457,
    role: "MACRO_CALIBRATION_ONLY",
    sourceUrl: "https://lifull.com/news/49546/",
    note: "掲載物件と問い合わせ物件の月次集計。町丁目や個別物件の予測値ではありません。",
  },
  {
    benchmarkId: "ATHOME_2026_06_RENT_METHOD",
    publisher: "アットホーム",
    period: "2026-06",
    scope: "主要都市・面積帯別募集家賃",
    askingMonthlyJPY: null,
    inquiryMonthlyJPY: null,
    role: "DEFINITION_AND_TREND_CHECK",
    sourceUrl: "https://www.athome.co.jp/corporate/news/data/market/chintai-yachin-202606/",
    note: "重複物件をユニーク化し、賃料＋管理費・共益費等を家賃として集計しています。",
  },
] as const;

export const NEXUS_SNAPSHOT = {
  asOfJST: "2026-08-18",
  rawObservations: 332,
  canonicalUnits: 270,
  buildings: 222,
  eligibleUnits: 196,
  primaryTargetUnits: 168,
  discoveryUnits: 28,
  marketKnownTotals: NEXUS_MARKET_AGGREGATE_SNAPSHOT.canonicalUnitsWithKnownTotal,
  marketTownSegments: NEXUS_MARKET_AGGREGATE_SNAPSHOT.townSegments,
  temporalSequence2Units: 20,
  firstTemporalDueJST: "2026-08-19",
} as const;

export type NexusCurrentness = "confirmed" | "stale" | "unknown";
export type NexusIdentity = "exact" | "partial" | "unknown";
export type NexusGateStatus = "pass" | "fail" | "unknown";

export type NexusPolicyInput = {
  propertyName?: string | null;
  address?: string | null;
  town?: string | null;
  sourceUrl?: string | null;
  totalMonthlyFixedJPY?: number | null;
  areaSquareMeters?: number | null;
  floor?: number | null;
  currentness?: NexusCurrentness;
  identity?: NexusIdentity;
};

export type NexusPolicyGate = {
  gateId: "monthly_total" | "area" | "floor" | "fixed_per_sqm";
  label: string;
  status: NexusGateStatus;
  hardGate: boolean;
  value: number | null;
  threshold: string;
  explanation: string;
};

export type NexusPolicyAssessment = {
  schemaVersion: "1.3";
  policyVersion: typeof NEXUS_POLICY_VERSION;
  evaluatedAt: string;
  snapshot: typeof NEXUS_SNAPSHOT;
  marketCoverage: typeof NEXUS_MARKET_COVERAGE;
  externalBenchmarks: typeof NEXUS_EXTERNAL_BENCHMARKS;
  input: NexusPolicyInput;
  fixedRentPerSqm: number | null;
  gates: NexusPolicyGate[];
  marketContext: NexusTownMarketContext | null;
  policyPass: boolean;
  decisionState: "OUTSIDE_POLICY" | "NEEDS_INPUT" | "POLICY_PASS_RECHECK_REQUIRED" | "READY_FOR_LAND_CHECK";
  nextActions: string[];
  warnings: string[];
};

function finiteOrNull(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberGate(
  gateId: NexusPolicyGate["gateId"],
  label: string,
  value: number | null,
  threshold: string,
  predicate: (value: number) => boolean,
  passText: string,
  failText: string,
  hardGate = true,
): NexusPolicyGate {
  if (value === null) {
    return { gateId, label, status: "unknown", hardGate, value, threshold, explanation: hardGate ? "値が未入力のため判定できません。" : "値が未入力のため参考値を計算できません。" };
  }
  const pass = predicate(value);
  return { gateId, label, status: pass ? "pass" : "fail", hardGate, value, threshold, explanation: pass ? passText : failText };
}

export function assessNexusProperty(rawInput: NexusPolicyInput): NexusPolicyAssessment {
  const total = finiteOrNull(rawInput.totalMonthlyFixedJPY);
  const area = finiteOrNull(rawInput.areaSquareMeters);
  const floor = finiteOrNull(rawInput.floor);
  const fixedRentPerSqm = total !== null && area !== null && area > 0 ? total / area : null;
  const currentness = rawInput.currentness ?? "unknown";
  const identity = rawInput.identity ?? "unknown";
  const townOrAddress = rawInput.town?.trim() || rawInput.address?.trim() || null;
  const marketContext = findTownMarket(townOrAddress, total);

  const gates: NexusPolicyGate[] = [
    numberGate(
      "monthly_total",
      "月の固定費",
      total,
      "170,000円以下",
      (value) => value <= NEXUS_POLICY.totalMonthlyFixedMaxJPY,
      "家賃と管理費などの固定費が上限内です。",
      "月の固定費が17万円を超えています。",
    ),
    numberGate(
      "area",
      "広さ",
      area,
      "15㎡以上",
      (value) => value >= NEXUS_POLICY.minimumAreaSquareMeters,
      "最低面積を満たしています。",
      "15㎡未満です。",
    ),
    numberGate(
      "floor",
      "階数",
      floor,
      "1階・2階・3階",
      (value) => NEXUS_POLICY.allowedFloors.includes(value as 1 | 2 | 3),
      "希望する階数です。",
      "1〜3階ではありません。",
    ),
    numberGate(
      "fixed_per_sqm",
      "固定費の㎡単価",
      fixedRentPerSqm,
      "参考表示のみ",
      () => true,
      "比較用の参考値です。V3では除外条件に使いません。",
      "比較用の参考値です。",
      false,
    ),
  ];

  const hardGates = gates.filter((gate) => gate.hardGate);
  const anyFail = hardGates.some((gate) => gate.status === "fail");
  const anyUnknown = hardGates.some((gate) => gate.status === "unknown");
  const policyPass = !anyFail && !anyUnknown;

  let decisionState: NexusPolicyAssessment["decisionState"];
  if (anyFail) decisionState = "OUTSIDE_POLICY";
  else if (anyUnknown) decisionState = "NEEDS_INPUT";
  else if (currentness === "confirmed" && identity === "exact") decisionState = "READY_FOR_LAND_CHECK";
  else decisionState = "POLICY_PASS_RECHECK_REQUIRED";

  const nextActions: string[] = [];
  if (anyUnknown) nextActions.push("家賃・管理費・広さ・階数の不足項目を埋める");
  if (total !== null && !townOrAddress) nextActions.push("住所または町丁目を入れ、内部募集サンプルと外部公式統計を確認する");
  if (townOrAddress && !marketContext) nextActions.push("この町丁目は内部標本がないため、外部公式統計と追加掲載から相場を補う");
  if (marketContext?.sampleQuality === "THIN") nextActions.push("町丁目標本が薄いため、周辺地域・外部公式統計・追加掲載を併用する");
  if (policyPass && identity !== "exact") nextActions.push("建物名・住所・号室が同じ部屋を指しているか確認する");
  if (policyPass && currentness !== "confirmed") nextActions.push("現在も募集されているか、申込み可能かを確認する");
  if (rawInput.address?.trim()) nextActions.push("住所を100mセルへつなぎ、土地研究の未調査・注意事項を確認する");
  if (policyPass && currentness === "confirmed" && identity === "exact") nextActions.push("総初期費用・契約条件・入居可能日を確認する");
  if (anyFail) nextActions.push("条件外として保管し、市場や地域研究の参考データにだけ使う");

  return {
    schemaVersion: "1.3",
    policyVersion: NEXUS_POLICY_VERSION,
    evaluatedAt: new Date().toISOString(),
    snapshot: NEXUS_SNAPSHOT,
    marketCoverage: NEXUS_MARKET_COVERAGE,
    externalBenchmarks: NEXUS_EXTERNAL_BENCHMARKS,
    input: { ...rawInput, town: rawInput.town?.trim() || null, totalMonthlyFixedJPY: total, areaSquareMeters: area, floor, currentness, identity },
    fixedRentPerSqm,
    gates,
    marketContext,
    policyPass,
    decisionState,
    nextActions,
    warnings: [
      "条件を通過しても、現在空室・申込み可能・おすすめ確定を意味しません。",
      "町丁目比較は257住戸の内部募集サンプルです。73研究町丁目の中央値は3住戸で、59町丁目が5住戸未満のため、地域相場の完成版とは扱いません。",
      "外部ポータル統計は全体水準と傾向の検算に使い、NEXUSの個別住戸データや正式モデルへ無造作に混ぜません。",
      "募集賃料は成約賃料ではありません。掲載が見つからないことは、募集がないことの証明ではありません。",
      "土地情報は家賃条件へ混ぜず、別カードとして確認します。未調査や該当なしを安全へ置き換えません。",
    ],
  };
}
