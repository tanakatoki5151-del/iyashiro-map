import { findTownMarket, NEXUS_MARKET_AGGREGATE_SNAPSHOT, type NexusTownMarketContext } from "./market";

export const NEXUS_POLICY_VERSION = "NEXUS_POLICY_V2_20260818" as const;

export const NEXUS_POLICY = {
  totalMonthlyFixedMaxJPY: 130_000,
  minimumAreaSquareMeters: 15,
  allowedFloors: [2, 3] as const,
  fixedRentPerSqmMaxJPY: 5_000,
} as const;

export const NEXUS_SNAPSHOT = {
  asOfJST: "2026-08-18",
  rawObservations: 329,
  canonicalUnits: 270,
  buildings: 222,
  eligibleUnits: 83,
  primaryTargetUnits: 56,
  discoveryUnits: 27,
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
  value: number | null;
  threshold: string;
  explanation: string;
};

export type NexusPolicyAssessment = {
  schemaVersion: "1.1";
  policyVersion: typeof NEXUS_POLICY_VERSION;
  evaluatedAt: string;
  snapshot: typeof NEXUS_SNAPSHOT;
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
): NexusPolicyGate {
  if (value === null) return { gateId, label, status: "unknown", value, threshold, explanation: "値が未入力のため判定できません。" };
  const pass = predicate(value);
  return { gateId, label, status: pass ? "pass" : "fail", value, threshold, explanation: pass ? passText : failText };
}

export function assessNexusProperty(rawInput: NexusPolicyInput): NexusPolicyAssessment {
  const total = finiteOrNull(rawInput.totalMonthlyFixedJPY);
  const area = finiteOrNull(rawInput.areaSquareMeters);
  const floor = finiteOrNull(rawInput.floor);
  const fixedRentPerSqm = total !== null && area !== null && area > 0 ? total / area : null;
  const currentness = rawInput.currentness ?? "unknown";
  const identity = rawInput.identity ?? "unknown";
  const town = rawInput.town?.trim() || null;
  const marketContext = findTownMarket(town, total);

  const gates: NexusPolicyGate[] = [
    numberGate("monthly_total", "月の固定費", total, "130,000円以下", (value) => value <= NEXUS_POLICY.totalMonthlyFixedMaxJPY, "家賃と管理費などの固定費が上限内です。", "月の固定費が13万円を超えています。"),
    numberGate("area", "広さ", area, "15㎡以上", (value) => value >= NEXUS_POLICY.minimumAreaSquareMeters, "最低面積を満たしています。", "15㎡未満です。"),
    numberGate("floor", "階数", floor, "2階または3階", (value) => NEXUS_POLICY.allowedFloors.includes(value as 2 | 3), "希望する階数です。", "2階または3階ではありません。"),
    numberGate("fixed_per_sqm", "固定費の㎡単価", fixedRentPerSqm, "5,000円/㎡以下", (value) => value <= NEXUS_POLICY.fixedRentPerSqmMaxJPY, "広さに対する固定費が上限内です。", "広さに対する固定費が5,000円/㎡を超えています。"),
  ];

  const anyFail = gates.some((gate) => gate.status === "fail");
  const anyUnknown = gates.some((gate) => gate.status === "unknown");
  const policyPass = !anyFail && !anyUnknown;

  let decisionState: NexusPolicyAssessment["decisionState"];
  if (anyFail) decisionState = "OUTSIDE_POLICY";
  else if (anyUnknown) decisionState = "NEEDS_INPUT";
  else if (currentness === "confirmed" && identity === "exact") decisionState = "READY_FOR_LAND_CHECK";
  else decisionState = "POLICY_PASS_RECHECK_REQUIRED";

  const nextActions: string[] = [];
  if (anyUnknown) nextActions.push("家賃・管理費・広さ・階数の不足項目を埋める");
  if (total !== null && !town) nextActions.push("町丁目を入れるか住所から自動取得し、公開募集の単純中央値と比べる");
  if (town && !marketContext) nextActions.push("この町丁目は集計対象外または表記差の可能性があるため、住所を確認する");
  if (marketContext?.sampleQuality === "THIN") nextActions.push("町丁目の標本が薄いため、周辺町丁目や正式モデルの既存判定も併用する");
  if (policyPass && identity !== "exact") nextActions.push("建物名・住所・号室が同じ部屋を指しているか確認する");
  if (policyPass && currentness !== "confirmed") nextActions.push("現在も募集されているか、申込み可能かを確認する");
  if (policyPass && rawInput.address?.trim()) nextActions.push("住所を100mセルへつなぎ、土地の各調査カードを確認する");
  if (policyPass && currentness === "confirmed" && identity === "exact") nextActions.push("総初期費用・契約条件・入居可能日を確認する");
  if (anyFail) nextActions.push("条件外として保管し、相場の参考データにだけ使う");

  return {
    schemaVersion: "1.1",
    policyVersion: NEXUS_POLICY_VERSION,
    evaluatedAt: new Date().toISOString(),
    snapshot: NEXUS_SNAPSHOT,
    input: { ...rawInput, town, totalMonthlyFixedJPY: total, areaSquareMeters: area, floor, currentness, identity },
    fixedRentPerSqm,
    gates,
    marketContext,
    policyPass,
    decisionState,
    nextActions,
    warnings: [
      "条件を通過しても、現在空室・申込み可能・おすすめ確定を意味しません。",
      "町丁目の市場比較は公開募集の単純中央値です。正式Championモデルの個別予測や成約賃料ではありません。",
      "掲載が見つからないことは、募集がないことの証明ではありません。",
      "土地情報は家賃条件へ混ぜず、別カードとして確認します。未調査や該当なしを安全へ置き換えません。",
    ],
  };
}
